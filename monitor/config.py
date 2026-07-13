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
    },
    "monitoring": {
        "poll_interval_sec": 3,
        "ping_target": "8.8.8.8",
        "ping_interval_sec": 5,
        "gpu_interval_sec": 10,
        "enable_system_metrics": True,
        "enable_network_metrics": True,
        "enable_gpu": False,
        "suppress_initial_device_events": True,
        "use_local_cache": True,
        "metrics_max_points": 300,
    },
}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with CONFIG_PATH.open(encoding="utf-8-sig") as fp:
            data = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_CONFIG))

    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    for key, value in data.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged
