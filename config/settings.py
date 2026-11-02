"""Loads config/settings.toml into a typed, validated object."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

SETTINGS_PATH = Path(__file__).with_name("settings.toml")


@dataclass(frozen=True)
class RiskLimits:
    max_position_pct: float
    min_cash_pct: float
    max_open_positions: int
    stop_loss_pct: float


@dataclass(frozen=True)
class Settings:
    tickers: list[str]
    benchmark: str
    risk: RiskLimits
    routine_model: str
    portfolio_manager_model: str
    portfolio_manager_mode: str = "rules"


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    raw = tomllib.loads(path.read_text())
    risk = RiskLimits(**raw["risk"])

    for name in ("max_position_pct", "min_cash_pct", "stop_loss_pct"):
        value = getattr(risk, name)
        if not 0 < value < 1:
            raise ValueError(f"risk.{name} must be between 0 and 1 (it's a fraction: 0.10 = 10%), got {value}")
    if risk.max_open_positions < 1:
        raise ValueError("risk.max_open_positions must be at least 1")

    tickers = [t.strip().upper() for t in raw["watchlist"]["tickers"]]
    if not tickers:
        raise ValueError("watchlist.tickers is empty")

    pm_mode = raw.get("portfolio_manager", {}).get("mode", "rules")
    if pm_mode not in ("rules", "ai"):
        raise ValueError(f'portfolio_manager.mode must be "rules" or "ai", got "{pm_mode}"')

    return Settings(
        tickers=tickers,
        benchmark=raw["watchlist"]["benchmark"].upper(),
        risk=risk,
        routine_model=raw["models"]["routine"],
        portfolio_manager_model=raw["models"]["portfolio_manager"],
        portfolio_manager_mode=pm_mode,
    )
