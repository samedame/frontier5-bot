"""Design studies behind the bot's defaults. Run: python research/studies.py [parquet_dir] > research/STUDIES.md

1. Sleeve A alert band: how many alerts per year, and does banding cost anything?
2. Sleeve rebalancing: the research backtest holds sleeve weights constant every day;
   this measures what a monthly (or quarterly / never) rebalance actually produces.
3. Alert frequency: replay the bot's change detection over history (2016+, the OOS window).
4. Timing: base case (fill at the signal close) vs delayed case (fill at the next close).
"""
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from frontier5 import data, engine, events as ev, signals  # noqa: E402
from frontier5.config import Settings  # noqa: E402

warnings.filterwarnings("ignore")


def stats(s: pd.Series) -> str:
    s = s.dropna()
    yrs = len(s) / 252
    c = (1 + s).cumprod()
    return f"{(c.iloc[-1] ** (1 / yrs) - 1):.2%} | {s.mean() / s.std() * np.sqrt(252):.2f} | {(c / c.cummax() - 1).min():.2%}"


def main(src: str) -> None:
    panel = data.load_parquet(src) if src != "yfinance" else data.download(start="1993-01-01")
    sig = signals.compute_all(panel)
    oos = lambda s: s[s.index >= "2016-01-01"]  # noqa: E731

    print("# FRONTIER-5 bot design studies\n")
    print(f"Data through {panel.close.index[-1].date()}; OOS = 2016-01-01 onward (the verdict's holdout).\n")

    print("## 1. Timing: where the verdict's 'execute next close' label sits\n")
    print("| Fill assumption | OOS CAGR | Sharpe | MaxDD |\n|---|---|---|---|")
    for lag, lab in ((1, "lag 1 (verdict base case): trade AT the close that produced the signal"),
                     (2, "lag 2 (verdict '+1-bar delay'): trade at the NEXT close")):
        print(f"| {lab} | {stats(oos(engine.portfolio_returns(engine.sleeve_returns(sig, lag=lag))))} |")

    print("\n## 2. Sleeve A alert band\n")
    print("| Band | OOS CAGR (lag 1) | Sharpe | MaxDD | A target changes / yr |\n|---|---|---|---|---|")
    for band in (0.0, 0.05, 0.10, 0.15, 0.20, 0.25):
        p = oos(engine.portfolio_returns(engine.sleeve_returns(sig, lag=1, a_band=band)))
        held = signals.apply_band(sig.a, band) if band else sig.a
        n = int((held.diff().abs() > 0).loc["2016":].sum())
        print(f"| {band:.2f} | {stats(p)} | {n / ((len(p)) / 252):.0f} |")

    print("\n## 3. Rebalancing the five sleeves\n")
    sl = engine.sleeve_returns(sig, lag=1)
    print("| Policy | OOS CAGR | Sharpe | MaxDD |\n|---|---|---|---|")
    for lab, s in (("Daily to target weights (research backtest, zero cost)", engine.portfolio_returns(sl)),
                   ("Monthly rebalance (5 bp / 15 bp BTC on traded amount)", engine.simulate_rebalanced(sl, freq="M")),
                   ("Quarterly rebalance", engine.simulate_rebalanced(sl, freq="Q")),
                   ("Yearly rebalance (BTC drifts far above 20% in between)", engine.simulate_rebalanced(sl, freq="Y"))):
        print(f"| {lab} | {stats(oos(s))} |")
    print("\nYearly is the longest period the helper supports; with BTC drifting far above its 20% target the drawdown rises.")

    print("\n## 4. Alert frequency (bot logic replayed bar by bar, 2016+)\n")
    cfg = Settings(account_usd=None, shadow=frozenset(), a_band=0.15)
    idx = [d for d in sig.index if d >= pd.Timestamp("2016-01-01")]
    state, counts = None, {s: 0 for s in "ABCDE"}
    for d in idx:
        snap = ev.snapshot(sig, d)
        events, state = ev.process(snap, state, cfg, "close")
        for e in events:
            if e["kind"] == "change":
                counts[e["sleeve"]] += 1
    yrs = len(idx) / 252
    print("| Sleeve | Alerts / yr | Meaning |\n|---|---|---|")
    meaning = {"A": "exposure moved >= 15 points", "B": "monthly rotation changed the top-5 set",
               "C": "an asset's 126d trend flipped", "D": "BTC crossed its 100d average", "E": "IBS entry or exit"}
    for s in "ABCDE":
        print(f"| {s} | {counts[s] / yrs:.1f} | {meaning[s]} |")
    print(f"| all | {sum(counts.values()) / yrs:.1f} | plus one status message per month |")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "yfinance")
