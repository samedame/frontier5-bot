"""download() must survive yfinance returning an empty column for one ticker of a threaded batch.

Real failures: frontier5 2026-11-02 (IEF) and the first pre-close run on 2026-11-09 (EEM), both
"1 Failed download: [...]: OperationalError('database is locked')" followed by
"DataError: no close on <date> for [...]". yfinance does not raise in that case, so the old retry loop never ran.
"""
import sys
import types
from datetime import datetime

import numpy as np
import pandas as pd
import pytest

from frontier5 import data
from frontier5.config import ALL_TICKERS

N_BARS = 500
IDX = pd.bdate_range("2024-01-01", periods=N_BARS)


def _frame(tickers, dead=()):
    """A yfinance-shaped frame: (Price, Ticker) MultiIndex columns; `dead` tickers come back as all-NaN."""
    cols = pd.MultiIndex.from_product([["Close", "High", "Low"], list(tickers)])
    vals = np.random.default_rng(1).uniform(50, 150, (N_BARS, len(cols)))
    df = pd.DataFrame(vals, index=IDX, columns=cols)
    for t in dead:
        for field in ("Close", "High", "Low"):
            df[(field, t)] = np.nan
    return df


class FakeYF(types.ModuleType):
    """download(): the first (threaded) call loses `dead` tickers; later calls follow `recovers`."""

    def __init__(self, dead, recovers=True):
        super().__init__("yfinance")
        self.dead, self.recovers, self.calls = list(dead), recovers, []

    def download(self, tickers, **kw):
        tickers = [tickers] if isinstance(tickers, str) else list(tickers)
        self.calls.append({"tickers": tickers, **kw})
        if len(self.calls) == 1:
            return _frame(tickers, dead=self.dead)
        return _frame(tickers, dead=[] if self.recovers else tickers)


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    monkeypatch.setattr(data.time, "sleep", lambda s: None)


def _install(monkeypatch, fake):
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    return fake


def test_clean_batch_makes_exactly_one_call(monkeypatch):
    fake = _install(monkeypatch, FakeYF(dead=[]))
    panel = data.download()
    assert len(fake.calls) == 1 and fake.calls[0]["threads"] is True
    assert set(ALL_TICKERS) <= set(panel.close.columns)


def test_one_dead_ticker_is_refetched_alone_without_threads(monkeypatch):
    fake = _install(monkeypatch, FakeYF(dead=["EEM"]))
    panel = data.download()
    assert len(fake.calls) == 2
    assert fake.calls[1]["tickers"] == ["EEM"] and fake.calls[1]["threads"] is False
    assert panel.close["EEM"].notna().all() and panel.high["EEM"].notna().all() and panel.low["EEM"].notna().all()
    data.validate(panel, now=datetime(2025, 11, 1, 12, 0), max_age_days=10**6)  # the check that killed the run


def test_refetch_keeps_column_order_and_other_tickers_untouched(monkeypatch):
    first = _install(monkeypatch, FakeYF(dead=["IEF"]))
    panel = data.download()
    reference = _frame(ALL_TICKERS)["Close"]
    assert list(panel.close.columns) == list(reference.columns)
    pd.testing.assert_series_equal(panel.close["SPY"], reference["SPY"].reindex(panel.close.index), check_freq=False)
    assert len(first.calls) == 2


def test_several_dead_tickers_come_back_in_one_refetch(monkeypatch):
    fake = _install(monkeypatch, FakeYF(dead=["EEM", "IEF", "GLD"]))
    panel = data.download()
    assert len(fake.calls) == 2 and sorted(fake.calls[1]["tickers"]) == ["EEM", "GLD", "IEF"]
    assert panel.close[["EEM", "IEF", "GLD"]].notna().all().all()


def test_ticker_that_never_recovers_is_still_rejected_by_validate(monkeypatch):
    fake = _install(monkeypatch, FakeYF(dead=["EEM"], recovers=False))
    panel = data.download(retries=3)
    assert len(fake.calls) == 1 + 3  # the batch plus one re-fetch per retry, then it gives up
    with pytest.raises(data.DataError, match="EEM"):
        data.validate(panel, now=datetime(2025, 11, 1, 12, 0), max_age_days=10**6)


def test_dead_spy_is_refetched_before_the_calendar_is_built(monkeypatch):
    fake = _install(monkeypatch, FakeYF(dead=["SPY"]))
    panel = data.download()
    assert len(fake.calls) == 2 and len(panel.close) == N_BARS
