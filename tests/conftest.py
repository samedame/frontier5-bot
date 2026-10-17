import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "research"))

from frontier5.config import ALL_TICKERS  # noqa: E402
from frontier5.data import Panel  # noqa: E402


def make_panel(seed: int = 0, start: str = "2016-01-01", end: str = "2022-12-30") -> Panel:
    """Random-walk panel on SPY trading days, with NaN gaps in BTC to exercise calendar handling."""
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, end)
    close, high, low = {}, {}, {}
    for i, t in enumerate(ALL_TICKERS):
        vol = 0.012 if t != "BTC-USD" else 0.035
        drift = 0.0003 + 0.00005 * (i % 4)
        r = rng.normal(drift, vol, len(idx))
        px = 100 * np.exp(np.cumsum(r))
        spread = np.abs(rng.normal(0.004, 0.002, len(idx))) * px
        close[t] = px
        high[t] = px + rng.uniform(0, 1, len(idx)) * spread
        low[t] = px - rng.uniform(0, 1, len(idx)) * spread
    c, h, l = (pd.DataFrame(d, index=idx) for d in (close, high, low))
    gaps = rng.choice(len(idx), size=12, replace=False)
    c.iloc[gaps, c.columns.get_loc("BTC-USD")] = np.nan
    return Panel(c, h, l)


@pytest.fixture(scope="session")
def panel():
    return make_panel()


@pytest.fixture(scope="session")
def sig(panel):
    from frontier5.signals import compute_all
    return compute_all(panel)
