"""Turn sleeve signals into a target portfolio (percent, dollars, share counts)."""
from __future__ import annotations

import math

from .config import (
    B_TOP_N, BTC, C_BASKET, E_TICKER, LEVERAGED_ETF, SLEEVE_NAMES, WEIGHTS, Settings,
)


def a_split(exposure: float) -> dict[str, float]:
    """Split sleeve-A capital between SPY, SSO (2x SPY) and cash for a target SPY exposure.

    exposure <= 1: SPY = e, rest cash.   exposure > 1: SPY = 2 - e, SSO = e - 1 (SPY + 2*SSO = e).
    """
    e = min(max(exposure, 0.0), 2.0)
    if e <= 1.0:
        return {"SPY": e, LEVERAGED_ETF: 0.0, "CASH": 1.0 - e}
    return {"SPY": 2.0 - e, LEVERAGED_ETF: e - 1.0, "CASH": 0.0}


def sleeve_positions(snap: dict) -> dict[str, dict[str, float]]:
    """Per sleeve: {ticker: fraction of the TOTAL portfolio}. Cash is implied (the remainder)."""
    out: dict[str, dict[str, float]] = {}
    split = a_split(snap["A"]["exposure"])
    out["A"] = {t: WEIGHTS["A"] * f for t, f in split.items() if t != "CASH" and f > 0}
    out["B"] = {t: WEIGHTS["B"] / B_TOP_N for t in snap["B"]["top"]}
    out["C"] = {t: WEIGHTS["C"] / len(C_BASKET) for t in snap["C"]["on"]}
    out["D"] = {BTC: WEIGHTS["D"]} if snap["D"]["on"] else {}
    out["E"] = {E_TICKER: WEIGHTS["E"]} if snap["E"]["on"] else {}
    return out


def build_targets(snap: dict, cfg: Settings, prices: dict[str, float]) -> dict:
    """Net target by instrument for the sleeves that are live (enabled and not shadow)."""
    per = sleeve_positions(snap)
    net: dict[str, dict] = {}
    for s in sorted(cfg.live()):
        for t, f in per[s].items():
            row = net.setdefault(t, {"frac": 0.0, "by": {}})
            row["frac"] += f
            row["by"][s] = row["by"].get(s, 0.0) + f
    invested = sum(r["frac"] for r in net.values())
    for t, row in net.items():
        if cfg.account_usd is not None:
            usd = row["frac"] * cfg.account_usd
            row["usd"] = usd
            px = prices.get(t)
            if px and px > 0:
                if t == BTC or cfg.fractional:
                    row["qty"] = round(usd / px, 6 if t == BTC else 4)
                else:
                    row["qty"] = math.floor(usd / px)
                    row["usd_filled"] = row["qty"] * px
    return {"rows": net, "cash_frac": 1.0 - invested, "invested_frac": invested}


def render_targets(targets: dict, cfg: Settings) -> str:
    rows = sorted(targets["rows"].items(), key=lambda kv: -kv[1]["frac"])
    have_usd = cfg.account_usd is not None
    head = f"{'ASSET':<8}{'% PORT':>7}" + (f"{'USD':>10}{'QTY':>11}" if have_usd else "") + "  SLEEVES"
    lines = [head]
    for t, r in rows:
        sl = "+".join(f"{s}{v * 100:.1f}" for s, v in sorted(r["by"].items()))
        line = f"{t.replace('-USD', ''):<8}{r['frac'] * 100:>6.1f}%"
        if have_usd:
            qty = r.get("qty")
            qtxt = "" if qty is None else (f"{qty:.6f}".rstrip("0").rstrip(".") if t == BTC else (f"{qty:.4f}".rstrip("0").rstrip(".") if cfg.fractional else str(qty)))
            line += f"{r['usd']:>10,.0f}{qtxt:>11}"
        lines.append(line + "  " + sl)
    cash = targets["cash_frac"]
    cash_line = f"{'CASH':<8}{cash * 100:>6.1f}%"
    if have_usd:
        cash_line += f"{cash * cfg.account_usd:>10,.0f}"
    lines.append(cash_line + "  (T-bills / sweep)")
    return "\n".join(lines)


def sleeve_label(s: str, cfg: Settings) -> str:
    tag = " [SHADOW]" if s in cfg.shadow else ""
    return f"{s} · {SLEEVE_NAMES[s]}{tag}"
