"""Backtest engine built on the bot's own signals.

`sleeve_returns` reproduces research/winner_strategy.py exactly (see tests/test_parity.py).
The live bot uses it for kill-switch statistics and the research tools use it for studies.

Timing convention, verified empirically in this repo:
  lag=1 (the verdict's base case): position on day t = signal at close t-1, earning the
         close(t-1) -> close(t) return. That is a fill AT the close that produced the signal
         (market-on-close using a near-final price). The verdict labels this "execute close t+1".
  lag=2 (the verdict's "+1-bar delay" stress): the signal is computed at close t, you trade at
         the NEXT close. This is what an after-close alert realizes: OOS CAGR 24.96%, Sharpe 1.51.
"""
from __future__ import annotations

import pandas as pd

from .config import COST_BTC, COST_ETF, WEIGHTS, C_BASKET
from .signals import Signals, apply_band, b_month_weights


def sleeve_returns(sig: Signals, lag: int = 1, cost_mult: float = 1.0, a_band: float = 0.0) -> pd.DataFrame:
    idx = sig.index

    scale = apply_band(sig.a, a_band)
    pos_a = scale.shift(lag)
    ret_a = pos_a * sig.rspy - pos_a.diff().abs().fillna(0) * COST_ETF * cost_mult

    w = b_month_weights(sig.mom)
    wd = w.resample("D").ffill().reindex(idx).ffill().fillna(0).shift(lag)
    ret_b = (wd * sig.b_rets).sum(axis=1) - wd.diff().abs().sum(axis=1).fillna(0) * COST_ETF * cost_mult

    wc = (sig.c_on / len(C_BASKET)).shift(lag).fillna(0)
    ret_c = (wc * sig.c_rets).sum(axis=1) - wc.diff().abs().sum(axis=1).fillna(0) * COST_ETF * cost_mult

    pos_d = sig.d_on.shift(lag).reindex(idx).ffill().fillna(0)
    btc_ret = sig.btc.pct_change().reindex(idx)
    ret_d = pos_d * btc_ret - pos_d.diff().abs().fillna(0) * COST_BTC * cost_mult

    pos_e = sig.e_on.reindex(idx).fillna(0).shift(lag)
    ret_e = pos_e * sig.e_rets - pos_e.diff().abs().fillna(0) * COST_ETF * cost_mult

    out = pd.DataFrame({"A": ret_a, "B": ret_b, "C": ret_c, "D": ret_d, "E": ret_e}).reindex(idx)
    return out


def portfolio_returns(sleeves: pd.DataFrame, weights: dict | None = None) -> pd.Series:
    weights = weights or WEIGHTS
    total = 0.0
    for k, w in weights.items():
        total = total + w * sleeves[k].fillna(0)
    return total


def simulate_rebalanced(sleeves: pd.DataFrame, weights: dict | None = None, freq: str = "M",
                        cost: float = COST_ETF, cost_d: float = COST_BTC) -> pd.Series:
    """Sleeve capital drifts between rebalances; at each period end sleeves return to target weights.

    The research backtest implicitly rebalances daily at zero cost; this is what a monthly
    reminder actually produces. Rebalancing trades are charged at the sleeve's cost rate.
    freq is a pandas period alias: "M" monthly, "Q" quarterly.
    """
    weights = weights or WEIGHTS
    keys = list(weights)
    r = sleeves[keys].fillna(0)
    tgt = pd.Series(weights, dtype=float)
    per = pd.Series(r.index.to_period(freq), index=r.index)
    last = (per != per.shift(-1)).to_numpy()
    cap = tgt.copy()
    nav = []
    for row, is_last in zip(r.to_numpy(), last):
        cap = cap * (1 + row)
        if is_last:
            total = cap.sum()
            desired = tgt * total
            trade = (desired - cap).abs()
            fee = trade.drop("D", errors="ignore").sum() * cost + trade.get("D", 0.0) * cost_d
            cap = desired - tgt * fee
        nav.append(cap.sum())
    nav = pd.Series(nav, index=r.index)
    return nav.pct_change().fillna(nav.iloc[0] - 1.0)
