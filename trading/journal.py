"""Writes one JSON file per run to logs/, recording every step and why.

The dashboard (Stage 2) and the Auditor (Stage 3) read these files.
logs/ stays on your computer; it is not uploaded to GitHub.
"""
from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def _plain(obj):
    if is_dataclass(obj):
        return {k: _plain(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if isinstance(obj, float) and obj != obj:  # NaN
        return None
    return obj


def write(record: dict, log_dir: Path = LOG_DIR, now: datetime | None = None) -> Path:
    now = now or datetime.now(timezone.utc)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"run_{now:%Y-%m-%d_%H%M%S}.json"
    path.write_text(json.dumps(_plain({"run_at": now.isoformat(), **record}), indent=2, default=str))
    return path
