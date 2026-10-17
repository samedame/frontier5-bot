"""Market data: download, calendar alignment, validation.

The research restricted every panel to SPY trading days (VERDICT Amendment 1) so
crypto weekends cannot corrupt equity rolling windows. This module does the same.
"""
from __future__ import annotations

import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

import pandas as pd

from .config import ALL_TICKERS, BTC, SIGNAL_TICKERS

ET = ZoneInfo("America/New_York")


class DataError(RuntimeError):
    """Raised when data is missing or stale; the bot refuses to emit signals from bad data."""


class Panel(NamedTuple):
    close: pd.DataFrame
    high: pd.DataFrame
    low: pd.DataFrame


def _field(raw: pd.DataFrame, name: str) -> pd.DataFrame:
    if isinstance(raw.columns, pd.MultiIndex):
        if name in raw.columns.get_level_values(0):
            return raw[name]
        return raw.xs(name, axis=1, level=1)
    return raw[[name]]


def to_spy_calendar(close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame) -> Panel:
    if "SPY" not in close.columns:
        raise DataError("SPY missing from data; cannot build the trading calendar")
    bdays = close["SPY"].dropna().index
    return Panel(close.reindex(bdays), high.reindex(bdays), low.reindex(bdays))


def _frames(raw: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    return _field(raw, "Close"), _field(raw, "High"), _field(raw, "Low")


def _incomplete(close: pd.DataFrame, tickers: list[str]) -> list[str]:
    """Tickers a download silently dropped: absent, empty, or no bar on SPY's latest day (BTC trades
    every day, so only the other tickers are held to the last-bar rule)."""
    if "SPY" not in close.columns or close["SPY"].dropna().empty:
        return list(tickers)
    spy_last = close["SPY"].dropna().index[-1]
    bad = []
    for t in tickers:
        if t not in close.columns or close[t].dropna().empty:
            bad.append(t)
        elif t != BTC and pd.isna(close[t].get(spy_last, float("nan"))):
            bad.append(t)
    return bad


def _put(frame: pd.DataFrame, series: pd.Series, ticker: str) -> pd.DataFrame:
    frame = frame.reindex(frame.index.union(series.index))
    frame[ticker] = series
    return frame


def download(start: str = "2012-01-01", retries: int = 3, tickers: list[str] | None = None) -> Panel:
    """Download adjusted daily bars.

    yfinance keeps a SQLite cache that can raise 'database is locked' when several tickers download in
    parallel (seen on GitHub Actions: XLE came back empty). So: fresh private cache directory, no threads,
    and any ticker that still comes back empty is re-fetched on its own before validation sees it.
    """
    import yfinance as yf  # imported lazily so tests and offline use do not need it

    try:
        yf.set_tz_cache_location(tempfile.mkdtemp(prefix="yf-cache-"))
    except Exception:
        pass  # older/newer yfinance without this hook: the retries below still apply

    tickers = tickers or ALL_TICKERS
    frames = None
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            raw = yf.download(tickers, start=start, auto_adjust=True, progress=False, threads=False)
            if raw is None or raw.empty:
                raise DataError("yfinance returned no data")
            frames = list(_frames(raw))
            break
        except Exception as exc:  # network, rate limit, schema change
            last_err = exc
            time.sleep(5 * attempt)
    if frames is None:
        raise DataError(f"download failed after {retries} attempts: {last_err}")

    for attempt in range(1, retries + 1):
        bad = _incomplete(frames[0], tickers)
        if not bad:
            break
        print(f"re-fetching incomplete tickers (attempt {attempt}): {bad}")
        for t in bad:
            try:
                raw = yf.download([t], start=start, auto_adjust=True, progress=False, threads=False)
                if raw is None or raw.empty:
                    continue
                one = _frames(raw)
                if t in one[0].columns:
                    frames = [_put(f, o[t], t) for f, o in zip(frames, one)]
            except Exception as exc:
                print(f"  {t}: {exc}")
        time.sleep(3 * attempt)
    return to_spy_calendar(*frames)


def load_parquet(directory: str | Path) -> Panel:
    d = Path(directory)
    close, high, low = (pd.read_parquet(d / f"{n}.parquet") for n in ("close", "high", "low"))
    return to_spy_calendar(close, high, low)


def drop_partial_last_bar(panel: Panel, now: datetime | None = None) -> Panel:
    """Close mode: if today's session has not finished, discard today's in-progress bar."""
    now = now or datetime.now(ET)
    last = panel.close.index[-1]
    if last.date() == now.date() and (now.hour, now.minute) < (16, 10):
        return Panel(panel.close.iloc[:-1], panel.high.iloc[:-1], panel.low.iloc[:-1])
    return panel


def validate(panel: Panel, now: datetime | None = None, max_age_days: int = 6) -> None:
    now = now or datetime.now(ET)
    close = panel.close
    missing = [t for t in SIGNAL_TICKERS if t not in close.columns]
    if missing:
        raise DataError(f"tickers missing from download: {missing}")
    last = close.index[-1]
    age = (pd.Timestamp(now.date()) - pd.Timestamp(last.date())).days
    if age > max_age_days:
        raise DataError(f"latest bar is {last.date()} ({age} days old); data feed looks stale")
    if len(close) < 400:
        raise DataError(f"only {len(close)} bars; need >= 400 for the 252+21 day momentum window")
    stale = [t for t in SIGNAL_TICKERS if t != "BTC-USD" and pd.isna(close[t].iloc[-1])]
    if stale:
        raise DataError(f"no close on {last.date()} for {stale}")
    if close["BTC-USD"].dropna().empty:
        raise DataError("no BTC-USD data")
