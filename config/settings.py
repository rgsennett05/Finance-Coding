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
    trim_buffer_pct: float = 0.01   # trim only above max_position_pct + this buffer
    cooldown_days: int = 7          # no re-buy this many calendar days after a stop-out


@dataclass(frozen=True)
class Settings:
    tickers: list[str]
    benchmark: str
    risk: RiskLimits
    routine_model: str
    portfolio_manager_model: str
    portfolio_manager_mode: str = "rules"
    market_weight: float = 0.6
    fundamentals_weight: float = 0.4
    buy_above: float = 0.33
    sell_below: float = -0.33


def load_settings(path: Path = SETTINGS_PATH) -> Settings:
    raw = tomllib.loads(path.read_text())
    risk = RiskLimits(**raw["risk"])

    for name in ("max_position_pct", "min_cash_pct", "stop_loss_pct"):
        value = getattr(risk, name)
        if not 0 < value < 1:
            raise ValueError(f"risk.{name} must be between 0 and 1 (it's a fraction: 0.10 = 10%), got {value}")
    if not 0 <= risk.trim_buffer_pct < 1:
        raise ValueError(f"risk.trim_buffer_pct must be between 0 and 1, got {risk.trim_buffer_pct}")
    if risk.cooldown_days < 0:
        raise ValueError("risk.cooldown_days can't be negative")
    if risk.max_open_positions < 1:
        raise ValueError("risk.max_open_positions must be at least 1")

    tickers = [t.strip().upper() for t in raw["watchlist"]["tickers"]]
    if not tickers:
        raise ValueError("watchlist.tickers is empty")

    pm = raw.get("portfolio_manager", {})
    pm_mode = pm.get("mode", "rules")
    mw, fw = float(pm.get("market_weight", 0.6)), float(pm.get("fundamentals_weight", 0.4))
    if mw < 0 or fw < 0 or mw + fw <= 0:
        raise ValueError("portfolio_manager weights must be zero or positive and not both zero")
    buy_above, sell_below = float(pm.get("buy_above", 0.33)), float(pm.get("sell_below", -0.33))
    if not -1 <= sell_below < buy_above <= 1:
        raise ValueError("portfolio_manager: need -1 <= sell_below < buy_above <= 1")
    if pm_mode not in ("rules", "ai"):
        raise ValueError(f'portfolio_manager.mode must be "rules" or "ai", got "{pm_mode}"')

    return Settings(
        tickers=tickers,
        benchmark=raw["watchlist"]["benchmark"].upper(),
        risk=risk,
        routine_model=raw["models"]["routine"],
        portfolio_manager_model=raw["models"]["portfolio_manager"],
        portfolio_manager_mode=pm_mode,
        market_weight=mw,
        fundamentals_weight=fw,
        buy_above=buy_above,
        sell_below=sell_below,
    )
