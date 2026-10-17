"""Snapshot of today's signals, change detection against saved state, and message text.

Everything here is pure (no network, no clock) so tests and the history replay can drive it.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd

from .config import (
    B_TOP_N, BTC, C_BASKET, D_SMA, E_IBS_MAX, SLEEVE_NAMES, VOL_TARGET, WEIGHTS, Settings,
)
from .portfolio import a_split, build_targets, render_targets, sleeve_label
from .signals import Signals, b_rank_at, b_reference_bar, is_month_end

MARGINAL = 0.015  # BTC within 1.5% of its SMA is flagged as a marginal call


# ---------------------------------------------------------------------------------------- snapshot
def snapshot(sig: Signals, bar: pd.Timestamp | None = None) -> dict:
    idx = sig.index
    bar = idx[-1] if bar is None else bar
    close = sig.panel.close

    ref = b_reference_bar(sig, bar)
    rank = b_rank_at(sig, ref)
    top = list(rank.index[:B_TOP_N])
    preview = list(b_rank_at(sig, bar).index[:B_TOP_N])  # ranking if the month ended today

    btc_hist = sig.btc.loc[:bar]
    sma = float(sig.btc_sma.loc[btc_hist.index[-1]]) if len(btc_hist) else float("nan")
    price = float(btc_hist.iloc[-1]) if len(btc_hist) else float("nan")
    d_on = bool(sig.d_on.loc[btc_hist.index[-1]] == 1.0) if len(btc_hist) and not np.isnan(sma) else False

    ibs = sig.ibs.reindex(idx).loc[bar]
    prices = {t: float(v) for t, v in close.loc[bar].items() if not np.isnan(v)}
    prices[BTC] = price

    return {
        "bar": bar.strftime("%Y-%m-%d"),
        "A": {"exposure": float(sig.a.loc[bar]), "vol": float(sig.vol.loc[bar])},
        "B": {"top": top, "ranking": [(t, float(v)) for t, v in rank.items()],
              "ref_bar": ref.strftime("%Y-%m-%d"), "month_end": bool(is_month_end(bar)),
              "preview": preview},
        "C": {"on": [t for t in C_BASKET if sig.c_on.loc[bar, t] == 1.0],
              "ret": {t: float(sig.c_ret.loc[bar, t]) for t in C_BASKET}},
        "D": {"on": d_on, "price": price, "sma": sma,
              "margin": (price / sma - 1) if sma and not np.isnan(sma) else float("nan")},
        "E": {"ibs": float(ibs) if not np.isnan(ibs) else float("nan"), "on": bool(ibs < E_IBS_MAX)},
        "prices": prices,
    }


# --------------------------------------------------------------------------------------- formatting
def _usd(x: float) -> str:
    return f"${x:,.0f}"


def _sleeve_cash(cfg: Settings, s: str) -> str:
    return f" (~{_usd(WEIGHTS[s] * cfg.account_usd)})" if cfg.account_usd else ""


def text_a(snap: dict, cfg: Settings, old: float | None) -> str:
    e, vol = snap["A"]["exposure"], snap["A"]["vol"]
    sp = a_split(e)
    head = f"target SPY exposure **{e:.0%}**" + (f" (was {old:.0%}, {'raise' if e > old else 'cut'})" if old is not None else "")
    usd = ""
    if cfg.account_usd:
        cap = WEIGHTS["A"] * cfg.account_usd
        usd = f" = SPY {_usd(cap * sp['SPY'])}, SSO {_usd(cap * sp['SSO'])}, cash {_usd(cap * sp['CASH'])}"
    return (f"{head}. 21d vol {vol:.1%} vs {VOL_TARGET:.0%} target.\n"
            f"Sleeve split: SPY {sp['SPY']:.0%} · SSO {sp['SSO']:.0%} · cash {sp['CASH']:.0%}{usd}")


def text_b(snap: dict, cfg: Settings, old: list[str] | None) -> str:
    top = snap["B"]["top"]
    each = WEIGHTS["B"] / B_TOP_N
    per = f" ({_usd(each * cfg.account_usd)} each)" if cfg.account_usd else ""
    rk = ", ".join(f"{t} {m:+.0%}" for t, m in snap["B"]["ranking"][:7])
    if old is None:
        body = f"hold **{', '.join(top)}** at {each:.0%} of the portfolio each{per}"
    else:
        buys = [t for t in top if t not in old]
        sells = [t for t in old if t not in top]
        keep = [t for t in top if t in old]
        body = (f"monthly rotation: BUY **{', '.join(buys) or '-'}** · SELL **{', '.join(sells) or '-'}** · "
                f"keep {', '.join(keep) or '-'}; each holding {each:.0%}{per}")
    pv = ""
    if snap["B"]["ref_bar"] != snap["bar"] and set(snap["B"]["preview"]) != set(top):
        pv = f"\nIf the month ended today the top 5 would be {', '.join(snap['B']['preview'])} (informational; B only rotates at month-end)."
    return f"{body}\nRanking as of {snap['B']['ref_bar']} (12-1 month return): {rk}{pv}"


def text_c(snap: dict, cfg: Settings, old: list[str] | None) -> str:
    on, rets = snap["C"]["on"], snap["C"]["ret"]
    each = WEIGHTS["C"] / len(C_BASKET)
    per = f" ({_usd(each * cfg.account_usd)} each)" if cfg.account_usd else ""
    lines = []
    if old is not None:
        for t in [t for t in C_BASKET if t in on and t not in old]:
            lines.append(f"{t} → **ON** (126d {rets[t]:+.1%}): buy {each:.1%}{per}")
        for t in [t for t in C_BASKET if t in old and t not in on]:
            lines.append(f"{t} → **OFF** (126d {rets[t]:+.1%}): sell to cash")
    state = f"ON ({len(on)}/{len(C_BASKET)}): {', '.join(on) or 'none'}. Each ON asset is {each:.1%} of the portfolio, the rest of the sleeve stays cash."
    return ("\n".join(lines) + "\n" if lines else "") + state


def text_d(snap: dict, cfg: Settings, was_on: bool | None) -> str:
    d = snap["D"]
    rel = "ABOVE" if d["on"] else "BELOW"
    act = ("hold/buy " + f"{WEIGHTS['D']:.0%} in BTC{_sleeve_cash(cfg, 'D')}") if d["on"] else "hold this sleeve in cash/T-bills"
    flip = "" if was_on is None else (" — **BUY**" if d["on"] else " — **SELL**")
    marg = ""
    if abs(d["margin"]) < MARGINAL:
        marg = " Marginal call: the latest BTC bar is still forming, so re-check at the next run."
    return (f"BTC ${d['price']:,.0f} is {rel} its {D_SMA}-day average ${d['sma']:,.0f} ({d['margin']:+.1%}){flip}. {act}.{marg}")


def text_e(snap: dict, cfg: Settings, was_on: bool | None) -> str:
    e = snap["E"]
    if e["on"]:
        act = f"**BUY** {WEIGHTS['E']:.0%} QQQ{_sleeve_cash(cfg, 'E')} at the close and hold into tomorrow" if not was_on else "keep holding QQQ into tomorrow"
    else:
        act = "**EXIT** to cash (sell QQQ at the close)" if was_on else "stay in cash"
    return f"QQQ IBS {e['ibs']:.2f} ({'<' if e['on'] else '≥'} {E_IBS_MAX:.2f}) → {act}."


def status_text(snap: dict, cfg: Settings, mon_status: dict | None) -> str:
    out = []
    if cfg.account_usd:
        out.append(f"Account size used for sizing: {_usd(cfg.account_usd)}. Live sleeves: {''.join(sorted(cfg.live()))}"
                   + (f". Shadow (signals only, not in the table): {''.join(sorted(cfg.shadow & cfg.enabled))}" if cfg.shadow & cfg.enabled else "."))
    else:
        out.append("FRONTIER5_ACCOUNT_USD is not set, so sizes are shown as % of portfolio only. "
                   f"Live sleeves: {''.join(sorted(cfg.live()))}"
                   + (f". Shadow: {''.join(sorted(cfg.shadow & cfg.enabled))}." if cfg.shadow & cfg.enabled else "."))
    for s in sorted(cfg.enabled):
        body = {"A": text_a(snap, cfg, None), "B": text_b(snap, cfg, None), "C": text_c(snap, cfg, None),
                "D": text_d(snap, cfg, None), "E": text_e(snap, cfg, None)}[s]
        out.append(f"**{sleeve_label(s, cfg)} ({WEIGHTS[s]:.0%})** — {body}")
    out.append("**Target portfolio**\n```\n" + render_targets(build_targets(snap, cfg, snap["prices"]), cfg) + "\n```")
    out.append("**Monthly rebalance:** return each sleeve to " + " / ".join(f"{s} {WEIGHTS[s]:.0%}" for s in WEIGHTS)
               + ". Sleeve capital drifts between rebalances (BTC especially); the research shows monthly rebalancing "
                 "matches the verdict (27.9% vs 27.4% OOS CAGR).")
    if mon_status:
        rows = []
        for s in sorted(cfg.enabled):
            m = mon_status["sleeves"][s]
            sh = "n/a" if np.isnan(m["sharpe3y"]) else f"{m['sharpe3y']:+.2f}"
            p = "n/a" if np.isnan(m["psr"]) else f"{m['psr']:.0%}"
            rows.append(f"{s}: 3y Sharpe {sh}, P(edge>hurdle) {p}")
        out.append("**Health (model portfolio):** " + "; ".join(rows)
                   + f". Drawdown vs 3y peak {mon_status['dd']:.1%}; 1y return {mon_status['port_ret_1y']:+.1%}; "
                     f"BTC round trips (1y) {mon_status['btc_round_trips_1y']}.")
    return "\n\n".join(out)


# -------------------------------------------------------------------------------------- change detection
def process(snap: dict, prev: dict | None, cfg: Settings, mode: str, force_status: bool = False,
            mon_status: dict | None = None) -> tuple[list[dict], dict]:
    """Compare today's snapshot with saved state. Returns (events, new_state).

    mode 'close'   : final-close run (the normal case).
    mode 'preclose': provisional run while the session is open; a later close run confirms it.
    """
    new = copy.deepcopy(prev) if prev else {}
    first = prev is None
    bar = snap["bar"]
    correction = bool(prev) and mode == "close" and prev.get("provisional_bar") == bar
    events: list[dict] = []

    def add(sleeve: str, text: str, kind: str = "change") -> None:
        title = sleeve_label(sleeve, cfg)
        if correction:
            title = "CORRECTION vs pre-close alert · " + title
        events.append({"kind": kind, "sleeve": sleeve, "title": title, "text": text})

    # Sleeve A -------------------------------------------------------------------------------
    if "A" in cfg.enabled:
        held = (new.get("A") or {}).get("held")
        e = snap["A"]["exposure"]
        if held is None:
            new["A"] = {"held": e}
        elif abs(e - held) >= cfg.a_band - 1e-12:
            add("A", text_a(snap, cfg, held))
            new["A"] = {"held": e}

    # Sleeve B -------------------------------------------------------------------------------
    if "B" in cfg.enabled:
        old = (new.get("B") or {}).get("holdings")
        top = snap["B"]["top"]
        if old is None:
            new["B"] = {"holdings": top}
        elif set(top) != set(old):
            add("B", text_b(snap, cfg, old))
            new["B"] = {"holdings": top}

    # Sleeve C -------------------------------------------------------------------------------
    if "C" in cfg.enabled:
        old = (new.get("C") or {}).get("on")
        on = snap["C"]["on"]
        if old is None:
            new["C"] = {"on": on}
        elif set(on) != set(old):
            add("C", text_c(snap, cfg, old))
            new["C"] = {"on": on}

    # Sleeve D -------------------------------------------------------------------------------
    if "D" in cfg.enabled:
        was = (new.get("D") or {}).get("on")
        if was is None:
            new["D"] = {"on": snap["D"]["on"]}
        elif bool(was) != snap["D"]["on"]:
            add("D", text_d(snap, cfg, bool(was)))
            new["D"] = {"on": snap["D"]["on"]}

    # Sleeve E -------------------------------------------------------------------------------
    if "E" in cfg.enabled:
        was = (new.get("E") or {}).get("on")
        if was is None:
            new["E"] = {"on": snap["E"]["on"]}
        elif bool(was) != snap["E"]["on"]:
            add("E", text_e(snap, cfg, bool(was)))
            new["E"] = {"on": snap["E"]["on"]}

    # Monthly status / rebalance reminder, initial targets --------------------------------------
    month = bar[:7]
    if first or force_status or new.get("status_month") != month:
        events.append({"kind": "status", "sleeve": "*",
                       "title": ("FRONTIER-5 · initial targets" if first else
                                 f"FRONTIER-5 · monthly status & rebalance ({month})"),
                       "text": status_text(snap, cfg, mon_status)})
        new["status_month"] = month

    if correction and not [e for e in events if e["kind"] == "change"]:
        events.append({"kind": "info", "sleeve": "*", "title": "Pre-close signals confirmed",
                       "text": f"The final close of {bar} agrees with the pre-close alert. No changes."})

    new["last_bar"] = bar
    new["provisional_bar"] = bar if mode == "preclose" else None
    return events, new
