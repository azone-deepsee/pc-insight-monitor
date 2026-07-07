from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "qr_log": {
        "enabled": False,
        "directory": "",
        "pattern": "*.csv",
    }
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with CONFIG_PATH.open(encoding="utf-8-sig") as fp:
            data = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    if "qr_log" in data and isinstance(data["qr_log"], dict):
        merged["qr_log"] = {**DEFAULT_CONFIG["qr_log"], **data["qr_log"]}
    return merged
