"""Connects to Alpaca — paper trading only.

Two safety checks run before any connection is made:
  1. The API key must look like a paper key (paper keys start with "PK").
  2. The trading client is always created with paper=True, which points it at
     Alpaca's paper endpoint (https://paper-api.alpaca.markets).
If either check fails, nothing connects and the program stops with a warning.

Run this file to check your connection:
    python -m data.broker
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

PAPER_KEY_PREFIX = "PK"


class LiveKeyError(RuntimeError):
    """Raised when keys look like live (real-money) keys. We never trade live."""


@dataclass(frozen=True)
class AlpacaKeys:
    api_key: str
    secret_key: str


def load_keys() -> AlpacaKeys:
    """Read Alpaca keys from .env and refuse anything that isn't a paper key."""
    load_dotenv()
    api_key = os.getenv("ALPACA_API_KEY", "").strip()
    secret_key = os.getenv("ALPACA_SECRET_KEY", "").strip()
    if not api_key or not secret_key:
        raise RuntimeError(
            "ALPACA_API_KEY and ALPACA_SECRET_KEY are missing. On your computer: copy .env.example to .env "
            "and fill them in. On GitHub: add them under Settings → Secrets and variables → Actions."
        )
    check_paper_key(api_key)
    return AlpacaKeys(api_key, secret_key)


def check_paper_key(api_key: str) -> None:
    if not api_key.startswith(PAPER_KEY_PREFIX):
        raise LiveKeyError(
            "STOP: this Alpaca key does not start with 'PK', so it may be a LIVE (real-money) key. "
            "This project only paper trades. Generate keys from the Paper Trading account instead."
        )


def trading_client():
    """Alpaca client for orders and account info, locked to paper trading."""
    from alpaca.trading.client import TradingClient

    keys = load_keys()
    return TradingClient(keys.api_key, keys.secret_key, paper=True)


def data_client():
    """Alpaca client for historical prices and quotes."""
    from alpaca.data.historical import StockHistoricalDataClient

    keys = load_keys()
    return StockHistoricalDataClient(keys.api_key, keys.secret_key)


def account_summary() -> dict:
    acct = trading_client().get_account()
    return {
        "status": str(acct.status),
        "portfolio_value": float(acct.portfolio_value),
        "cash": float(acct.cash),
        "buying_power": float(acct.buying_power),
        "currency": acct.currency,
    }


if __name__ == "__main__":
    try:
        s = account_summary()
    except LiveKeyError as err:
        raise SystemExit(f"\n⛔ {err}\n")
    print("✅ Connected to Alpaca PAPER account")
    print(f"   Status:          {s['status']}")
    print(f"   Portfolio value: ${s['portfolio_value']:,.2f}")
    print(f"   Cash:            ${s['cash']:,.2f}")
    print(f"   Buying power:    ${s['buying_power']:,.2f}")
