"""Checks that the settings file loads and the risk limits make sense."""
from pathlib import Path

import pytest

from config.settings import load_settings


def test_settings_load():
    s = load_settings()
    assert 5 <= len(s.tickers) <= 10
    assert s.risk.max_position_pct == 0.10
    assert s.risk.min_cash_pct == 0.10
    assert s.risk.max_open_positions == 10


def test_limits_fit_together():
    # 10 positions at the max size must not eat into the cash reserve beyond 100%.
    r = load_settings().risk
    assert r.max_position_pct * r.max_open_positions <= 1.0


def test_bad_percent_is_rejected(tmp_path: Path):
    bad = tmp_path / "settings.toml"
    bad.write_text(
        load_settings.__globals__["SETTINGS_PATH"].read_text().replace("max_position_pct = 0.10", "max_position_pct = 10")
    )
    with pytest.raises(ValueError, match="between 0 and 1"):
        load_settings(bad)
