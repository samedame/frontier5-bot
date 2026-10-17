"""The bot's signal engine must reproduce research/winner_strategy.py exactly."""
import os
import warnings
from pathlib import Path

import pandas as pd
import pytest

import winner_strategy as ws  # research/winner_strategy.py, copied unmodified from the research folder
from frontier5 import data, engine, signals

warnings.filterwarnings("ignore")


@pytest.mark.parametrize("extra_lag", [0, 1])
@pytest.mark.parametrize("cost_mult", [1.0, 2.0])
def test_synthetic_parity(panel, sig, extra_lag, cost_mult):
    mine = engine.portfolio_returns(engine.sleeve_returns(sig, lag=1 + extra_lag, cost_mult=cost_mult))
    ref = ws.backtest(cost_mult=cost_mult, extra_lag=extra_lag, data=(panel.close, panel.high, panel.low))
    assert (mine - ref).abs().max() < 1e-12


def _real_dir():
    for cand in (os.environ.get("FRONTIER5_PARQUET"), "../data", "data", "/mnt/user-data/uploads/research 2/data"):
        if cand and (Path(cand) / "close.parquet").exists():
            return cand
    return None


@pytest.mark.skipif(_real_dir() is None, reason="research parquet data not available")
def test_real_data_parity_and_headline():
    p = data.load_parquet(_real_dir())
    s = signals.compute_all(p)
    mine = engine.portfolio_returns(engine.sleeve_returns(s, lag=1))
    ref = ws.backtest(data=(p.close, p.high, p.low))
    assert (mine - ref).abs().max() < 1e-12
    oos = mine[mine.index >= "2016-01-01"].dropna()
    cagr = (1 + oos).prod() ** (252 / len(oos)) - 1
    assert abs(cagr - 0.2744) < 5e-4  # VERDICT headline OOS CAGR 27.4%


def test_b_reference_matches_research_month_weights(sig):
    """The live B target on a month's last bar equals the research month-end weights."""
    w = signals.b_month_weights(sig.mom)
    idx = sig.index
    checked = 0
    for label, row in w.iterrows():
        bars = idx[(idx.year == label.year) & (idx.month == label.month)]
        if not len(bars) or row.sum() == 0:
            continue
        last = bars[-1]
        assert signals.is_month_end(last)
        live = set(signals.b_rank_at(sig, last).index[: signals.B_TOP_N])
        assert live == set(row[row > 0].index)
        checked += 1
    assert checked > 50
