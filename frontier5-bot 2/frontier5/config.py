"""Single source of truth for FRONTIER-5 parameters.

Every number below is copied from research/VERDICT.md. Do not tune them here:
the research was pre-registered and a changed parameter is a different strategy.
Runtime knobs (account size, shadow sleeves, alert band) come from environment
variables and only change how alerts are presented, never what the signals are.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

SLEEVES = ("A", "B", "C", "D", "E")
WEIGHTS = {"A": 0.30, "B": 0.25, "C": 0.20, "D": 0.20, "E": 0.05}
SLEEVE_NAMES = {
    "A": "Vol-targeted SPY",
    "B": "ETF momentum",
    "C": "Diversified trend",
    "D": "Bitcoin trend",
    "E": "QQQ mean reversion",
}

# Sleeve A: exposure = clip(VOL_TARGET / 21d realized SPY vol, 0, MAX_EXPOSURE)
VOL_TARGET = 0.20
VOL_WINDOW = 21
MAX_EXPOSURE = 2.0
LEVERAGED_ETF = "SSO"  # 2x SPY, used for the part of exposure above 100%

# Sleeve B: monthly, rank by 252d return skipping the last 21d, hold top 5 equally
B_UNIVERSE = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "DBC", "VNQ", "XLE"]
B_LOOKBACK = 252
B_SKIP = 21
B_TOP_N = 5

# Sleeve C: hold 1/8 of the sleeve in each asset whose 126d return is > 0, else cash
C_BASKET = ["SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"]
C_LOOKBACK = 126

# Sleeve D: hold BTC iff close > 100-day SMA (weekday-sampled closes), never levered
BTC = "BTC-USD"
D_SMA = 100

# Sleeve E: hold QQQ into tomorrow iff today's IBS < 0.30
E_TICKER = "QQQ"
E_IBS_MAX = 0.30

# Costs per unit of turnover (VERDICT section 1)
COST_ETF = 0.0005
COST_BTC = 0.0015

SIGNAL_TICKERS = sorted(set(["SPY"] + B_UNIVERSE + C_BASKET + [BTC]))
PRICE_ONLY_TICKERS = [LEVERAGED_ETF]  # downloaded for sizing, never used in a signal
ALL_TICKERS = SIGNAL_TICKERS + PRICE_ONLY_TICKERS

# VERDICT section 8: invalidation / retirement rules
HURDLE_SHARPE = 0.86  # deflated-Sharpe hurdle at N=215 trials
ROLLING_WINDOW = 756  # ~3 years of trading days
BTC_MAX_ROUND_TRIPS_PER_YEAR = 8
# NOT in the verdict: proposed model-portfolio drawdown alert levels (worst historical was -23.3%)
DD_ALERT_LEVELS = (-0.15, -0.20, -0.25)


def _truthy(v: str | None, default: bool) -> bool:
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "y", "on")


def _letters(v: str | None, default: str) -> frozenset[str]:
    """Sleeve letters from an env var. Blank (GitHub Actions passes unset vars as "") means the default;
    NONE means an explicit empty set."""
    if v is None or v.strip() == "":
        v = default
    if v.strip().upper() in ("NONE", "-"):
        return frozenset()
    return frozenset(c for c in v.upper() if c in SLEEVES)


@dataclass(frozen=True)
class Settings:
    account_usd: float | None = None  # never guessed: unset means percentages only
    enabled: frozenset = frozenset(SLEEVES)
    shadow: frozenset = frozenset({"B"})  # shadow sleeves alert but are left out of the dollar table
    a_band: float = 0.15  # sleeve A alerts only when target exposure moves this much (research/studies.py)
    fractional: bool = True  # False -> whole-share rounding in the dollar table
    heartbeat_days: int = 7
    webhook: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ
        acct = (e.get("FRONTIER5_ACCOUNT_USD") or "").strip().replace(",", "").replace("$", "")
        band = (e.get("FRONTIER5_A_BAND") or "").strip()
        hb = (e.get("FRONTIER5_HEARTBEAT_DAYS") or "").strip()
        return cls(
            account_usd=float(acct) if acct else None,
            enabled=_letters(e.get("FRONTIER5_ENABLED"), "ABCDE"),
            shadow=_letters(e.get("FRONTIER5_SHADOW"), "B"),
            a_band=float(band) if band else 0.15,
            fractional=_truthy(e.get("FRONTIER5_FRACTIONAL"), True),
            heartbeat_days=int(hb) if hb else 7,
            webhook=(e.get("DISCORD_WEBHOOK_URL") or "").strip() or None,
        )

    def live(self) -> frozenset:
        return self.enabled - self.shadow
