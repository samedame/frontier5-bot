"""Discord webhook delivery (stdlib only)."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request

COLORS = {"change": 0xE67E22, "status": 0x2ECC71, "kill": 0xE74C3C, "info": 0x3498DB, "error": 0x992D22}
UA = "frontier5-bot/1.0 (+personal signal bot)"


def _chunks(text: str, limit: int = 3800) -> list[str]:
    """Split on line boundaries; hard-split any single line longer than the limit (Discord caps embeds at 4096)."""
    if len(text) <= limit:
        return [text]
    lines: list[str] = []
    for para in text.split("\n"):
        while len(para) > limit:
            lines.append(para[:limit])
            para = para[limit:]
        lines.append(para)
    out, cur = [], ""
    for line in lines:
        if len(cur) + len(line) + 1 > limit and cur:
            out.append(cur)
            cur = ""
        cur += line + "\n"
    if cur:
        out.append(cur)
    return out


def post(webhook: str | None, title: str, text: str, kind: str = "info", footer: str = "") -> bool:
    """Returns True if delivered. With no webhook it prints instead (dry run) and returns False."""
    if not webhook:
        print(f"\n--- [{kind}] {title} ---\n{text}\n")
        return False
    ok = True
    for i, chunk in enumerate(_chunks(text)):
        embed = {"title": title if i == 0 else f"{title} (cont.)", "description": chunk,
                 "color": COLORS.get(kind, COLORS["info"])}
        if footer and i == 0:
            embed["footer"] = {"text": footer}
        body = json.dumps({"username": "FRONTIER-5", "embeds": [embed]}).encode()
        for attempt in range(4):
            req = urllib.request.Request(webhook, data=body, method="POST",
                                         headers={"Content-Type": "application/json", "User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=20):
                    break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    try:
                        wait = float(json.loads(e.read().decode()).get("retry_after", 2))
                    except Exception:
                        wait = 2.0
                    time.sleep(min(wait, 15))
                    continue
                print(f"discord HTTP {e.code}: {e.reason}")
                ok = False
                break
            except Exception as e:
                print(f"discord error: {e}")
                time.sleep(2 * (attempt + 1))
        else:
            ok = False
    return ok
