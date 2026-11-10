"""Market data: download, calendar alignment, validation.

The research restricted every panel to SPY trading days (VERDICT Amendment 1) so
crypto weekends cannot corrupt equity rolling windows. This module does the same.
"""
from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

import pandas as pd

from .config import ALL_TICKERS, SIGNAL_TICKERS

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


def _dead_tickers(close: pd.DataFrame, tickers: list[str]) -> list[str]:
    """Tickers whose whole column is missing or empty: what a failed per-ticker download looks like."""
    return [t for t in tickers if t not in close.columns or close[t].dropna().empty]


def _by_ticker(raw: pd.DataFrame, name: str, tickers: list[str]) -> pd.DataFrame:
    f = _field(raw, name)
    if len(tickers) == 1 and list(f.columns) != tickers:  # flat single-ticker frame: the column is called "Close"
        f = f.set_axis(tickers, axis=1)
    return f


def _splice(old: pd.DataFrame, new: pd.DataFrame, ok: list[str]) -> pd.DataFrame:
    """Replace the empty columns `ok` in `old` with the re-fetched ones, keeping the original column order."""
    order = list(old.columns) + [t for t in ok if t not in old.columns]
    merged = pd.concat([old.drop(columns=[t for t in ok if t in old.columns]), new[ok]], axis=1)
    return merged[order]


def _refetch_dead(yf, dead: list[str], start: str, retries: int,
                  close: pd.DataFrame, high: pd.DataFrame, low: pd.DataFrame):
    """Re-download only the tickers that came back empty, on one thread, and splice them in.

    yfinance does not raise when one ticker of a threaded batch fails. The usual cause is the shared tz-cache
    SQLite file ("OperationalError('database is locked')"): it prints "1 Failed download" and returns an empty
    column, which validate() then rejects, so a single unlucky ticker used to kill the whole run (frontier5
    2026-11-02 and the first pre-close run on 2026-11-09). A ticker that stays empty after the retries is left
    empty, so validate() still reports it and the bot still refuses to emit signals from bad data."""
    for attempt in range(1, retries + 1):
        print(f"[data] {len(dead)} ticker(s) came back empty ({', '.join(dead)}); re-fetching one thread (attempt {attempt}/{retries})")
        try:
            raw = yf.download(dead, start=start, auto_adjust=True, progress=False, threads=False)
            if raw is not None and not raw.empty:
                c, h, l = (_by_ticker(raw, n, dead) for n in ("Close", "High", "Low"))
                ok = [t for t in dead if t in c.columns and not c[t].dropna().empty]
                if ok:
                    close, high, low = (_splice(old, new, ok) for old, new in ((close, c), (high, h), (low, l)))
                    dead = [t for t in dead if t not in ok]
                    print(f"[data] recovered {', '.join(ok)}")
        except Exception as exc:  # same failure family as the batch; try again
            print(f"[data] re-fetch failed: {exc}")
        if not dead:
            break
        if attempt < retries:
            time.sleep(2 * attempt)
    return close, high, low


def download(start: str = "2012-01-01", retries: int = 3, tickers: list[str] | None = None) -> Panel:
    import yfinance as yf  # imported lazily so tests and offline use do not need it

    tickers = tickers or ALL_TICKERS
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            raw = yf.download(tickers, start=start, auto_adjust=True, progress=False, threads=True)
            if raw is None or raw.empty:
                raise DataError("yfinance returned no data")
            close, high, low = _field(raw, "Close"), _field(raw, "High"), _field(raw, "Low")
            dead = _dead_tickers(close, tickers)
            if dead:
                close, high, low = _refetch_dead(yf, dead, start, retries, close, high, low)
            return to_spy_calendar(close, high, low)
        except Exception as exc:  # network, rate limit, schema change
            last_err = exc
            time.sleep(5 * attempt)
    raise DataError(f"download failed after {retries} attempts: {last_err}")


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
