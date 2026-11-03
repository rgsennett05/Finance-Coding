"""Download the permanent run history from GitHub into logs/.

The daily GitHub run saves every run log on the `fund-history` branch. Run this
on your computer to copy any logs you don't have yet, so the dashboard shows
every past day:

    python -m trading.history
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = ROOT / "logs"
BRANCH = "fund-history"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def pull() -> int:
    """Copy run logs from the fund-history branch that aren't in logs/ yet. Returns how many were added."""
    try:
        git("fetch", "--quiet", "origin", BRANCH)
    except subprocess.CalledProcessError as err:
        if "couldn't find remote ref" in (err.stderr or ""):
            print("No saved history yet — it appears after the first daily GitHub run.")
            return 0
        raise
    LOG_DIR.mkdir(exist_ok=True)
    added = 0
    for name in git("ls-tree", "--name-only", "FETCH_HEAD").split():
        if not (name.startswith("run_") and name.endswith(".json")) or "/" in name:
            continue
        target = LOG_DIR / name
        if target.exists():
            continue
        target.write_text(git("show", f"FETCH_HEAD:{name}"))
        added += 1
    return added


if __name__ == "__main__":
    n = pull()
    total = len(list(LOG_DIR.glob("run_*.json")))
    print(f"Added {n} run log(s) from GitHub. logs/ now has {total} run(s).")
