import copy
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import numpy as np
import pandas as pd
import pytest

from frontier5 import events as ev, monitor, notify, portfolio, run, signals, state
from frontier5.config import Settings


CFG = Settings(account_usd=10_000.0, shadow=frozenset(), a_band=0.15)


def snap_of(sig, bar=None):
    return ev.snapshot(sig, bar)


def base_snap(sig):
    return copy.deepcopy(snap_of(sig))


# ----------------------------------------------------------------------------------- pure helpers
def test_a_split():
    assert portfolio.a_split(1.96) == pytest.approx({"SPY": 0.04, "SSO": 0.96, "CASH": 0.0})
    assert portfolio.a_split(1.0) == pytest.approx({"SPY": 1.0, "SSO": 0.0, "CASH": 0.0})
    assert portfolio.a_split(0.4) == pytest.approx({"SPY": 0.4, "SSO": 0.0, "CASH": 0.6})
    for e in np.linspace(0, 2, 21):  # SPY + 2*SSO always equals the target exposure
        s = portfolio.a_split(e)
        assert s["SPY"] + 2 * s["SSO"] == pytest.approx(e)


@pytest.mark.parametrize("d,expected", [("2026-10-30", True), ("2026-10-29", False), ("2026-12-31", True),
                                         ("2026-05-28", False), ("2026-05-29", True), ("2026-11-02", False)])
def test_month_end(d, expected):
    assert signals.is_month_end(pd.Timestamp(d)) is expected


def test_apply_band_holds_until_move():
    s = pd.Series([1.0, 1.05, 1.1, 1.2, 1.14, 1.0, 0.8])
    assert signals.apply_band(s, 0.15).tolist() == [1.0, 1.0, 1.0, 1.2, 1.2, 1.0, 0.8]
    assert signals.apply_band(s, 0.0).tolist() == s.tolist()


# ------------------------------------------------------------------------------------- change events
def test_initial_run_emits_status_only(sig):
    events, new = ev.process(base_snap(sig), None, CFG, "close")
    assert [e["kind"] for e in events] == ["status"]
    assert set(new) >= {"A", "B", "C", "D", "E", "last_bar", "status_month"}


def test_no_change_no_events(sig):
    s = base_snap(sig)
    _, st = ev.process(s, None, CFG, "close")
    events, _ = ev.process(s, st, CFG, "close")
    assert events == []


def test_a_band_threshold(sig):
    s = base_snap(sig)
    _, st = ev.process(s, None, CFG, "close")
    s2 = copy.deepcopy(s)
    s2["A"]["exposure"] = st["A"]["held"] + 0.10
    events, st2 = ev.process(s2, st, CFG, "close")
    assert events == [] and st2["A"]["held"] == st["A"]["held"]
    s2["A"]["exposure"] = st["A"]["held"] + 0.16
    events, st3 = ev.process(s2, st, CFG, "close")
    assert len(events) == 1 and events[0]["sleeve"] == "A" and st3["A"]["held"] == pytest.approx(s2["A"]["exposure"])


def test_c_d_e_b_flips(sig):
    s = base_snap(sig)
    _, st = ev.process(s, None, CFG, "close")
    s2 = copy.deepcopy(s)
    flip_c = s2["C"]["on"][0] if s2["C"]["on"] else None
    s2["C"]["on"] = [t for t in s2["C"]["on"] if t != flip_c] if flip_c else ["SPY"]
    s2["D"]["on"] = not s2["D"]["on"]
    s2["E"]["on"] = not s2["E"]["on"]
    s2["B"]["top"] = s2["B"]["top"][:4] + [t for t in ["TLT", "VNQ", "XLE", "GLD"] if t not in s2["B"]["top"]][:1]
    events, st2 = ev.process(s2, st, CFG, "close")
    sleeves = sorted(e["sleeve"] for e in events if e["kind"] == "change")
    assert sleeves == ["B", "C", "D", "E"]
    assert st2["D"]["on"] == s2["D"]["on"] and st2["E"]["on"] == s2["E"]["on"]
    text = {e["sleeve"]: e["text"] for e in events}
    assert "BUY" in text["B"] and "SELL" in text["B"]
    assert ("**BUY**" in text["D"]) == s2["D"]["on"]


def test_monthly_status_fires_once_per_month(sig):
    s = base_snap(sig)
    _, st = ev.process(s, None, CFG, "close")
    s2 = copy.deepcopy(s)
    y, m = int(s["bar"][:4]), int(s["bar"][5:7])
    s2["bar"] = f"{y + (m == 12)}-{(m % 12) + 1:02d}-03"
    events, st2 = ev.process(s2, st, CFG, "close")
    assert [e["kind"] for e in events] == ["status"]
    events, _ = ev.process(s2, st2, CFG, "close")
    assert events == []


def test_shadow_sleeve_labeled_and_excluded_from_table(sig):
    cfg = Settings(account_usd=10_000.0, shadow=frozenset({"B"}))
    s = base_snap(sig)
    t = portfolio.build_targets(s, cfg, s["prices"])
    assert all("B" not in r["by"] for r in t["rows"].values())
    assert t["cash_frac"] >= 0.25 - 1e-9
    assert "[SHADOW]" in portfolio.sleeve_label("B", cfg)


def test_preclose_then_close_confirmation_and_correction(sig):
    s = base_snap(sig)
    _, st0 = ev.process(s, None, CFG, "close")
    _, st_pre = ev.process(s, st0, CFG, "preclose")
    assert st_pre["provisional_bar"] == s["bar"]
    events, st_close = ev.process(s, st_pre, CFG, "close")
    assert [e["kind"] for e in events] == ["info"] and st_close["provisional_bar"] is None
    # final close disagrees with the pre-close alert -> labelled correction
    s_pre = copy.deepcopy(s)
    s_pre["E"]["on"] = not s["E"]["on"]
    _, st_pre = ev.process(s_pre, st0, CFG, "preclose")
    events, _ = ev.process(s, st_pre, CFG, "close")
    ch = [e for e in events if e["kind"] == "change"]
    assert len(ch) == 1 and ch[0]["title"].startswith("CORRECTION")


def test_c_sleeve_sizing_is_one_eighth_per_asset(sig):
    """Regression for daily_callout.py, which sized each ON asset at 20%/len(on)."""
    s = base_snap(sig)
    s["C"]["on"] = ["SPY", "EFA", "DBC"]
    per = portfolio.sleeve_positions(s)["C"]
    assert all(v == pytest.approx(0.20 / 8) for v in per.values()) and sum(per.values()) == pytest.approx(0.075)


def test_whole_share_rounding(sig):
    cfg = Settings(account_usd=10_000.0, shadow=frozenset(), fractional=False)
    s = base_snap(sig)
    t = portfolio.build_targets(s, cfg, s["prices"])
    for tk, r in t["rows"].items():
        if tk != "BTC-USD":
            assert float(r["qty"]).is_integer() and r["qty"] * s["prices"][tk] <= r["usd"] + 1e-9


# --------------------------------------------------------------------------------------- monitoring
def test_psr_directions():
    rng = np.random.default_rng(1)
    good = pd.Series(rng.normal(0.002, 0.008, 900))
    bad = pd.Series(rng.normal(-0.0005, 0.008, 900))
    assert monitor.psr(good) > 0.9 and monitor.psr(bad) < 0.05
    assert monitor.rolling_sharpe(good) > 0 > monitor.rolling_sharpe(bad)


def test_kill_switches_fire_once(sig, monkeypatch):
    monkeypatch.setattr(monitor, "rolling_sharpe", lambda r, window=756: -0.4)
    monkeypatch.setattr(monitor, "psr", lambda r, sr0_annual=0.86, window=756: 0.05)
    monkeypatch.setattr(monitor, "btc_round_trips", lambda s, window=252: 11)
    monkeypatch.setattr(monitor, "drawdown_vs_trailing_peak", lambda p, window=756: -0.22)
    alerts, _, mon = monitor.evaluate(sig, None)
    titles = " | ".join(a["title"] for a in alerts)
    assert "Bitcoin sleeve invalidated" in titles and titles.count("retire sleeve") == 5 and "DRAWDOWN" in titles
    again, _, _ = monitor.evaluate(sig, mon)
    assert again == []
    monkeypatch.setattr(monitor, "drawdown_vs_trailing_peak", lambda p, window=756: -0.26)
    deeper, _, _ = monitor.evaluate(sig, mon)
    assert [a["title"].split(" ·")[0] for a in deeper] == ["DRAWDOWN"]


# ------------------------------------------------------------------------------------ end to end
def test_notify_payload_and_429_retry():
    got = []

    class H(BaseHTTPRequestHandler):
        hits = 0

        def do_POST(self):
            H.hits += 1
            body = self.rfile.read(int(self.headers["Content-Length"]))
            if H.hits == 1:
                self.send_response(429)
                self.end_headers()
                self.wfile.write(b'{"retry_after": 0.01}')
                return
            got.append((json.loads(body), self.headers.get("User-Agent")))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    ok = notify.post(f"http://127.0.0.1:{srv.server_port}/hook", "T", "x" * 9000, "change", "foot")
    srv.shutdown()
    assert ok and len(got) == 3  # 9000 chars -> 3 chunks; first request was retried after the 429
    assert got[0][0]["embeds"][0]["title"] == "T" and got[1][0]["embeds"][0]["title"].endswith("(cont.)")
    assert got[0][1].startswith("frontier5-bot")


def test_run_is_idempotent_and_writes_state(tmp_path, monkeypatch, capsys):
    import frontier5.data as d
    p = pytest.importorskip("conftest").make_panel()
    for n, df in zip(("close", "high", "low"), p):
        df.to_parquet(tmp_path / f"{n}.parquet")
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    sp = tmp_path / "state.json"
    args = run._parse(["--source", str(tmp_path), "--state", str(sp)])
    assert run.run(args) == 0 and sp.exists()
    st1 = state.load(sp)
    capsys.readouterr()
    assert run.run(args) == 0
    assert "already processed" in capsys.readouterr().out
    assert state.load(sp) == st1
    # dry-run never writes
    sp2 = tmp_path / "s2.json"
    assert run.run(run._parse(["--source", str(tmp_path), "--state", str(sp2), "--dry-run"])) == 0
    assert not sp2.exists()


def test_drop_partial_last_bar():
    from datetime import datetime
    from frontier5 import data as d
    from conftest import make_panel
    p = make_panel(end="2026-10-16")
    et = d.ET
    during = datetime(2026, 10, 16, 15, 0, tzinfo=et)
    after = datetime(2026, 10, 16, 16, 30, tzinfo=et)
    assert len(d.drop_partial_last_bar(p, during).close) == len(p.close) - 1
    assert len(d.drop_partial_last_bar(p, after).close) == len(p.close)
    assert len(d.drop_partial_last_bar(p, datetime(2026, 10, 17, 9, 0, tzinfo=et)).close) == len(p.close)


def test_validate_flags_stale_and_missing(panel):
    from datetime import datetime
    from frontier5 import data as d
    with pytest.raises(d.DataError):
        d.validate(panel, now=datetime(2030, 1, 1, tzinfo=d.ET))  # years stale
    broken = d.Panel(panel.close.drop(columns=["GLD"]), panel.high, panel.low)
    with pytest.raises(d.DataError):
        d.validate(broken, now=datetime(2022, 12, 31, tzinfo=d.ET))


def test_settings_from_blank_actions_env(monkeypatch):
    """GitHub Actions passes unset repository variables as empty strings."""
    for k in ("FRONTIER5_ACCOUNT_USD", "FRONTIER5_SHADOW", "FRONTIER5_ENABLED", "FRONTIER5_A_BAND",
              "FRONTIER5_FRACTIONAL", "DISCORD_WEBHOOK_URL", "FRONTIER5_HEARTBEAT_DAYS"):
        monkeypatch.setenv(k, "")
    c = Settings.from_env()
    assert c.account_usd is None and c.enabled == frozenset("ABCDE") and c.shadow == frozenset("B")
    assert c.a_band == 0.15 and c.fractional is True and c.webhook is None and c.live() == frozenset("ACDE")
    monkeypatch.setenv("FRONTIER5_SHADOW", "none")
    monkeypatch.setenv("FRONTIER5_ENABLED", "abcd")
    monkeypatch.setenv("FRONTIER5_ACCOUNT_USD", "$12,500")
    monkeypatch.setenv("FRONTIER5_FRACTIONAL", "false")
    c = Settings.from_env()
    assert c.shadow == frozenset() and c.enabled == frozenset("ABCD") and c.account_usd == 12500.0 and c.fractional is False


# ------------------------------------------------------------------------------- pre-close guards
def _et(y, m, d, hh, mm):
    from datetime import datetime
    from frontier5 import data as d_
    return datetime(y, m, d, hh, mm, tzinfo=d_.ET)


def test_preclose_window():
    assert run.preclose_window(_et(2026, 10, 16, 15, 45)) is None
    assert run.preclose_window(_et(2026, 10, 16, 15, 57)) is None
    assert run.preclose_window(_et(2026, 10, 16, 15, 58))[0] == "late"
    assert run.preclose_window(_et(2026, 10, 16, 16, 40))[0] == "late"
    assert run.preclose_window(_et(2026, 10, 16, 9, 0))[0] == "quiet"
    assert run.preclose_window(_et(2026, 10, 17, 15, 45))[0] == "quiet"  # Saturday


@pytest.fixture
def live_env(tmp_path, monkeypatch):
    """Fake yfinance: panel whose last bar is Friday 2026-10-16; controllable clock; no webhook."""
    from conftest import make_panel
    from frontier5 import data as d_
    panel = make_panel(end="2026-10-16")
    monkeypatch.setattr(d_, "download", lambda start="2012-01-01", **k: panel)
    monkeypatch.delenv("DISCORD_WEBHOOK_URL", raising=False)
    clock = {"now": _et(2026, 10, 16, 15, 45)}
    monkeypatch.setattr(run, "_now_et", lambda: clock["now"])
    return tmp_path / "state.json", clock


def test_preclose_run_then_close_confirms(live_env, capsys):
    sp, clock = live_env
    assert run.run(run._parse(["--mode", "preclose", "--state", str(sp)])) == 0
    st1 = state.load(sp)
    assert st1["last_bar"] == "2026-10-16" and st1["provisional_bar"] == "2026-10-16"
    clock["now"] = _et(2026, 10, 16, 17, 30)
    capsys.readouterr()
    assert run.run(run._parse(["--mode", "close", "--state", str(sp)])) == 0
    out = capsys.readouterr().out
    assert "Pre-close signals confirmed" in out
    assert state.load(sp)["provisional_bar"] is None
    capsys.readouterr()
    assert run.run(run._parse(["--mode", "close", "--state", str(sp)])) == 0
    assert "already processed" in capsys.readouterr().out


def test_preclose_late_posts_notice_and_keeps_state_clean(live_env, capsys):
    sp, clock = live_env
    clock["now"] = _et(2026, 10, 16, 16, 12)
    assert run.run(run._parse(["--mode", "preclose", "--state", str(sp)])) == 0
    out = capsys.readouterr().out
    assert "missed its window" in out and not sp.exists()


def test_preclose_skips_holiday_and_weekend_quietly(live_env, capsys):
    sp, clock = live_env
    clock["now"] = _et(2026, 10, 19, 15, 45)  # Monday, but the feed's latest bar is still Friday (a holiday)
    assert run.run(run._parse(["--mode", "preclose", "--state", str(sp)])) == 0
    assert "no session bar" in capsys.readouterr().out and not sp.exists()
    clock["now"] = _et(2026, 10, 17, 15, 45)  # Saturday
    assert run.run(run._parse(["--mode", "preclose", "--state", str(sp)])) == 0
    assert "weekend" in capsys.readouterr().out and not sp.exists()
