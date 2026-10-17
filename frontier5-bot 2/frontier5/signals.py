"""Vectorized signal construction (unshifted: the value at row t is known at close t).

The formulas mirror research/winner_strategy.py line for line; tests/test_parity.py
proves the bot's returns equal the research backtest to machine precision.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import (
    B_LOOKBACK, B_SKIP, B_TOP_N, B_UNIVERSE, BTC, C_BASKET, C_LOOKBACK, D_SMA, E_IBS_MAX,
    E_TICKER, MAX_EXPOSURE, VOL_TARGET, VOL_WINDOW,
)
from .data import Panel


def _ret(df, n: int):
    """n-bar simple return, no implicit forward-fill (identical to pct_change(n) in pandas 3)."""
    return df / df.shift(n) - 1


@dataclass
class Signals:
    panel: Panel
    rspy: pd.Series        # SPY daily return
    vol: pd.Series         # 21d realized SPY vol, annualized
    a: pd.Series           # sleeve A target exposure, 0..2
    mom: pd.DataFrame      # sleeve B: 252d return ending 21 bars ago
    b_rets: pd.DataFrame   # B universe daily returns
    c_ret: pd.DataFrame    # sleeve C: 126d return
    c_on: pd.DataFrame     # sleeve C: 1.0 where 126d return > 0
    c_rets: pd.DataFrame   # C basket daily returns
    btc: pd.Series         # BTC closes on SPY days (NaNs dropped)
    btc_sma: pd.Series
    d_on: pd.Series        # sleeve D: 1.0 where BTC > SMA100
    ibs: pd.Series
    e_on: pd.Series        # sleeve E: 1.0 where IBS < 0.30
    e_rets: pd.Series

    @property
    def index(self) -> pd.DatetimeIndex:
        return self.panel.close.index


def compute_all(panel: Panel) -> Signals:
    close, high, low = panel
    spy = close["SPY"].dropna()
    rspy = spy.pct_change()
    vol = rspy.rolling(VOL_WINDOW).std() * np.sqrt(252)
    a = (VOL_TARGET / vol).clip(0, MAX_EXPOSURE)

    mom = _ret(close[B_UNIVERSE], B_LOOKBACK).shift(B_SKIP)
    b_rets = _ret(close[B_UNIVERSE], 1)

    c_ret = _ret(close[C_BASKET], C_LOOKBACK)
    c_on = (c_ret > 0).astype(float)
    c_rets = _ret(close[C_BASKET], 1)

    btc = close[BTC].dropna()
    btc_sma = btc.rolling(D_SMA).mean()
    d_on = (btc > btc_sma).astype(float)

    q = close[E_TICKER].dropna()
    lo = low[E_TICKER].reindex(q.index)
    hi = high[E_TICKER].reindex(q.index)
    ibs = (q - lo) / ((hi - lo) + 1e-12)
    e_on = (ibs < E_IBS_MAX).astype(float)
    e_rets = close[E_TICKER].pct_change()

    return Signals(panel, rspy, vol, a, mom, b_rets, c_ret, c_on, c_rets, btc, btc_sma, d_on, ibs, e_on, e_rets)


def apply_band(series: pd.Series, band: float) -> pd.Series:
    """Hold the previous value until the target has moved by at least `band` (path-dependent).

    Used for sleeve A so alerts fire on meaningful exposure changes instead of every day.
    """
    if band <= 0:
        return series
    out = np.empty(len(series))
    held = np.nan
    for i, v in enumerate(series.to_numpy(dtype=float)):
        if np.isnan(v):
            out[i] = np.nan
            continue
        if np.isnan(held) or abs(v - held) >= band:
            held = v
        out[i] = held
    return pd.Series(out, index=series.index)


# ---- Sleeve B helpers -----------------------------------------------------------------------

def b_month_weights(mom: pd.DataFrame) -> pd.DataFrame:
    """Research definition: weights per calendar-month label from the month's last momentum row."""
    mm = mom.resample("ME").last()
    w = pd.DataFrame(0.0, index=mm.index, columns=mom.columns)
    for d, row in mm.iterrows():
        r = row.dropna().sort_values(ascending=False)
        if len(r) >= B_TOP_N:
            w.loc[d, r.index[:B_TOP_N]] = 1.0 / B_TOP_N
    return w


def b_rank_at(sig: Signals, bar: pd.Timestamp) -> pd.Series:
    """Momentum ranking (descending) as of `bar`."""
    return sig.mom.loc[bar].dropna().sort_values(ascending=False)


def is_month_end(bar: pd.Timestamp) -> bool:
    """True when `bar` is the last weekday of its month (so also the last trading day)."""
    nxt = bar + pd.offsets.BDay(1)
    return nxt.month != bar.month


def b_reference_bar(sig: Signals, bar: pd.Timestamp) -> pd.Timestamp:
    """Bar whose ranking defines the sleeve B target on `bar`.

    On the last trading day of a month the rotation is already decided (the 21-bar skip means
    the ranking uses no price from the final month), so it is announced that day. Otherwise
    the target is the ranking at the last bar of the previous month.
    """
    if is_month_end(bar):
        return bar
    month_start = bar.replace(day=1)
    prior = sig.index[sig.index < month_start]
    return prior[-1] if len(prior) else bar
