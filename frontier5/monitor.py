"""Kill-switches from VERDICT section 8, computed on the bot's own sleeve return series.

Rules taken from the verdict:
  * BTC invalidation: sleeve D rolling 3-yr Sharpe < 0 AND more than 8 round trips in the last year.
  * Sleeve retirement: a sleeve's 3-yr Sharpe < 0 AND its deflated Sharpe probability < 50%
    (deflated against the verdict's hurdle Sharpe of 0.86 at N=215 trials).
Added by this bot (NOT in the verdict, labeled as such in alerts):
  * Model-portfolio drawdown levels vs the trailing 3-yr peak. These watch the *model* portfolio,
    not your brokerage account; compare the two to catch execution drift.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

from .config import (
    BTC_MAX_ROUND_TRIPS_PER_YEAR, DD_ALERT_LEVELS, HURDLE_SHARPE, ROLLING_WINDOW, SLEEVES,
)
from .engine import portfolio_returns, sleeve_returns
from .signals import Signals


def _ncdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def rolling_sharpe(r: pd.Series, window: int = ROLLING_WINDOW) -> float:
    sub = r.dropna().iloc[-window:]
    sd = sub.std()
    if len(sub) < window // 2 or not sd or np.isnan(sd):
        return float("nan")
    return float(sub.mean() / sd * math.sqrt(252))


def psr(r: pd.Series, sr0_annual: float = HURDLE_SHARPE, window: int = ROLLING_WINDOW) -> float:
    """Probabilistic Sharpe ratio vs a hurdle (Bailey & Lopez de Prado), skew/kurtosis adjusted."""
    sub = r.dropna().iloc[-window:]
    n = len(sub)
    sd = sub.std()
    if n < window // 2 or not sd:
        return float("nan")
    sr = sub.mean() / sd
    sr0 = sr0_annual / math.sqrt(252)
    skew, kurt = float(sub.skew()), float(sub.kurt()) + 3.0
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if denom <= 0:
        return float("nan")
    return _ncdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(denom))


def btc_round_trips(sig: Signals, window: int = 252) -> int:
    d = sig.d_on.dropna().iloc[-window:]
    return int((d.diff() == 1).sum())


def drawdown_vs_trailing_peak(port: pd.Series, window: int = ROLLING_WINDOW) -> float:
    eq = (1 + port.fillna(0)).cumprod().iloc[-window:]
    return float(eq.iloc[-1] / eq.max() - 1)


def dd_level(dd: float) -> int:
    return sum(dd <= lvl for lvl in DD_ALERT_LEVELS)


def evaluate(sig: Signals, prev: dict | None) -> tuple[list[dict], dict, dict]:
    """Return (alerts, status, new_monitor_state). Alerts fire only on a transition into the bad state."""
    prev = prev or {}
    sl = sleeve_returns(sig, lag=1)
    port = portfolio_returns(sl)

    status: dict = {"sleeves": {}}
    for s in SLEEVES:
        status["sleeves"][s] = {"sharpe3y": rolling_sharpe(sl[s]), "psr": psr(sl[s])}
    status["btc_round_trips_1y"] = btc_round_trips(sig)
    status["dd"] = drawdown_vs_trailing_peak(port)
    status["port_ret_1y"] = float((1 + port.iloc[-252:].fillna(0)).prod() - 1)
    status["port_sharpe3y"] = rolling_sharpe(port)

    alerts: list[dict] = []
    new = {"retired": dict(prev.get("retired", {})), "btc_invalid": bool(prev.get("btc_invalid", False)),
           "dd_level": int(prev.get("dd_level", 0))}

    d = status["sleeves"]["D"]
    btc_bad = (not np.isnan(d["sharpe3y"])) and d["sharpe3y"] < 0 and status["btc_round_trips_1y"] > BTC_MAX_ROUND_TRIPS_PER_YEAR
    if btc_bad and not new["btc_invalid"]:
        alerts.append({"kind": "kill", "title": "KILL-SWITCH · Bitcoin sleeve invalidated",
                       "text": (f"Sleeve D rolling 3-yr Sharpe is {d['sharpe3y']:.2f} (< 0) with "
                                f"{status['btc_round_trips_1y']} round trips in the last year (> {BTC_MAX_ROUND_TRIPS_PER_YEAR}). "
                                "VERDICT section 8 invalidation trigger: the 2016-21 BTC premium is not repeating. "
                                "Expect the portfolio to degrade toward its ~12.5% no-BTC core. Review the 20% allocation.")})
    new["btc_invalid"] = bool(btc_bad)

    for s in SLEEVES:
        st = status["sleeves"][s]
        bad = (not np.isnan(st["sharpe3y"])) and st["sharpe3y"] < 0 and (not np.isnan(st["psr"])) and st["psr"] < 0.5
        if bad and not new["retired"].get(s, False):
            alerts.append({"kind": "kill", "title": f"KILL-SWITCH · retire sleeve {s}",
                           "text": (f"Sleeve {s} 3-yr Sharpe {st['sharpe3y']:.2f} (< 0) and deflated-Sharpe probability "
                                    f"{st['psr']:.0%} (< 50%). VERDICT section 8: retire the sleeve and redistribute its weight to A and C.")})
        new["retired"][s] = bool(bad)

    lvl = dd_level(status["dd"])
    if lvl > new["dd_level"]:
        alerts.append({"kind": "kill", "title": f"DRAWDOWN · model portfolio {status['dd']:.1%} from trailing 3-yr peak",
                       "text": (f"Crossed the {DD_ALERT_LEVELS[lvl - 1]:.0%} level (levels are this bot's addition, not the verdict's; "
                                "worst historical drawdown was -23.3%). This tracks the MODEL portfolio: compare it with your actual "
                                "account to catch execution drift. The verdict's 0.2% ruin estimate assumes you keep following the rules.")})
    new["dd_level"] = lvl
    return alerts, status, new
