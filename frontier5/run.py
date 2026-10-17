"""Entry point: python -m frontier5.run [--mode close|preclose] [--dry-run] ..."""
from __future__ import annotations

import argparse
import os
import sys
import traceback
from datetime import datetime, timezone

import pandas as pd

from . import data, events as ev, monitor, notify, state as st
from .config import Settings
from .signals import compute_all

PRECLOSE_OPEN = (9, 35)    # ET: before this there is no usable in-progress bar
PRECLOSE_USABLE_UNTIL = (15, 58)  # ET: same cutoff as the other bots; a later start cannot trade the close


def _now_et() -> datetime:
    return datetime.now(data.ET)


def preclose_window(now: datetime) -> tuple[str, str] | None:
    """None if a provisional run is useful right now, else (severity, reason): 'quiet' or 'late'."""
    if now.weekday() >= 5:
        return "quiet", "weekend"
    hm = (now.hour, now.minute)
    if hm < PRECLOSE_OPEN:
        return "quiet", f"market not open yet ({now:%H:%M} ET)"
    if hm >= PRECLOSE_USABLE_UNTIL:
        return "late", f"started {now:%H:%M} ET, after the {PRECLOSE_USABLE_UNTIL[0]}:{PRECLOSE_USABLE_UNTIL[1]:02d} ET cutoff"
    return None


NOTE_CLOSE = ("Final-close signals. Place any trades at the **next trading day's close** "
              "(the verdict's delayed-fill case: OOS CAGR 25.0%, Sharpe 1.51).")
NOTE_PRECLOSE = ("**PROVISIONAL** (session still open). Place trades in the last minutes before today's close "
                 "(the verdict's base case: OOS CAGR 27.4%, Sharpe 1.65). A final-close check will follow.")


def _parse(argv):
    ap = argparse.ArgumentParser(description="FRONTIER-5 signal bot")
    ap.add_argument("--mode", choices=["close", "preclose"], default="close")
    ap.add_argument("--source", default="yfinance", help="'yfinance' or a folder holding close/high/low .parquet")
    ap.add_argument("--state", default=st.DEFAULT_PATH)
    ap.add_argument("--start", default="2012-01-01", help="first date to download")
    ap.add_argument("--as-of", help="YYYY-MM-DD: evaluate as of an earlier bar (testing/backfill)")
    ap.add_argument("--force", action="store_true", help="process a bar that was already processed")
    ap.add_argument("--status", action="store_true", help="also send the full status message")
    ap.add_argument("--scheduled-for-et", default="", help="HH:MM ET the scheduler targeted (logged only)")
    ap.add_argument("--trigger", default="", help="who started the run, e.g. cf-scheduler or manual (logged only)")
    ap.add_argument("--no-window-check", action="store_true", help="preclose: ignore the 9:35-15:58 ET window (testing)")
    ap.add_argument("--dry-run", action="store_true", help="print only; do not post to Discord or write state")
    return ap.parse_args(argv)


def run(args) -> int:
    cfg = Settings.from_env()
    webhook = None if args.dry_run else cfg.webhook
    try:
        local = args.source != "yfinance"
        live_preclose = args.mode == "preclose" and not local and not args.as_of and not args.no_window_check
        now_et = _now_et()
        if args.scheduled_for_et or args.trigger:
            print(f"run context: trigger={args.trigger or '-'} scheduled_for_et={args.scheduled_for_et or '-'} now_et={now_et:%Y-%m-%d %H:%M}")
        if live_preclose:
            gate = preclose_window(now_et)
            if gate:
                kind, why = gate
                print(f"pre-close run skipped: {why}")
                if kind == "late":
                    notify.post(webhook, "FRONTIER-5 · pre-close run missed its window",
                                f"The provisional run {why}, so there is no time to trade today's close from it. "
                                "The final-close run will still post today's signals; trade them at the next close.", "info")
                return 0
        panel = data.load_parquet(args.source) if local else data.download(start=args.start)
        if args.as_of:
            cut = panel.close.index <= pd.Timestamp(args.as_of)
            panel = data.Panel(panel.close[cut], panel.high[cut], panel.low[cut])
        elif args.mode == "close" and not local:
            panel = data.drop_partial_last_bar(panel, now_et)
        data.validate(panel, now=now_et, max_age_days=10**6 if (local or args.as_of) else 6)
        if live_preclose and panel.close.index[-1].date() != now_et.date():
            print(f"pre-close run skipped: no session bar for {now_et.date()} (market holiday?). Latest bar {panel.close.index[-1].date()}.")
            return 0

        sig = compute_all(panel)
        snap = ev.snapshot(sig)
        bar = snap["bar"]
        prev = st.load(args.state)

        confirms_preclose = bool(prev) and args.mode == "close" and prev.get("provisional_bar") == bar
        if prev and prev.get("last_bar") == bar and not args.force and not confirms_preclose:
            print(f"bar {bar} already processed; nothing to do.")
            return 0

        kill_alerts, mon_status, mon_state = monitor.evaluate(sig, (prev or {}).get("monitor"))
        events, new = ev.process(snap, prev, cfg, args.mode, force_status=args.status, mon_status=mon_status)
        new["monitor"] = mon_state

        now = datetime.now(timezone.utc)
        changes = [e for e in events if e["kind"] == "change"]
        others = [e for e in events if e["kind"] != "change"] + [dict(a, sleeve="!") for a in kill_alerts]
        if not changes and not others:
            last = new.get("last_post_utc")
            stale = (last is None) or ((now - datetime.fromisoformat(last)).days >= cfg.heartbeat_days)
            if stale:
                others.append({"kind": "info", "title": "FRONTIER-5 · heartbeat",
                               "text": f"Bot healthy. Latest bar {bar}. No signal changes. "
                                       f"A {snap['A']['exposure']:.0%} · B {', '.join(snap['B']['top'])} · "
                                       f"C {len(snap['C']['on'])}/8 on · D {'on' if snap['D']['on'] else 'off'} · "
                                       f"E {'on' if snap['E']['on'] else 'off'}"})

        footer = f"signals as of close {bar} · mode {args.mode}"
        sent_ok = True
        posted_any = False
        note = NOTE_PRECLOSE if args.mode == "preclose" else NOTE_CLOSE
        if changes:
            body = "\n\n".join(f"**{e['title']}**\n{e['text']}" for e in changes) + f"\n\n{note}"
            sent_ok &= notify.post(webhook, f"FRONTIER-5 · signal change · {bar}", body, "change", footer) or webhook is None
            posted_any = True
        for e in others:
            text = e["text"] + (f"\n\n{note}" if e["kind"] == "status" else "")
            sent_ok &= notify.post(webhook, e["title"], text, e["kind"], footer) or webhook is None
            posted_any = True

        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a") as fh:
                fh.write(f"## FRONTIER-5 · {bar} ({args.mode})\n\n{ev.status_text(snap, cfg, mon_status)}\n")

        if args.dry_run:
            print("dry run: state not written")
            return 0
        if webhook and not sent_ok:
            print("Discord delivery failed; state NOT advanced so the next run retries.", file=sys.stderr)
            return 1
        if posted_any:
            new["last_post_utc"] = now.isoformat(timespec="seconds")
        st.save(new, args.state)
        print(f"processed bar {bar} ({args.mode}): {len(changes)} change(s), {len(others)} other message(s)")
        return 0
    except Exception as exc:
        tb = "".join(traceback.format_exception_only(type(exc), exc)).strip()
        notify.post(webhook, "FRONTIER-5 · bot error", f"```\n{tb[:1500]}\n```\nNo signals were sent. Check the Actions log.", "error")
        traceback.print_exc()
        return 2


def main(argv=None) -> None:
    sys.exit(run(_parse(argv)))


if __name__ == "__main__":
    main()
