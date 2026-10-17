"""Tiny JSON state store committed back to the repo by the workflow."""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_PATH = os.environ.get("FRONTIER5_STATE", "state/state.json")


def load(path: str | Path = DEFAULT_PATH) -> dict | None:
    p = Path(path)
    if not p.exists():
        return None
    text = p.read_text().strip()
    return json.loads(text) if text else None


def save(state: dict, path: str | Path = DEFAULT_PATH) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
    tmp.replace(p)
