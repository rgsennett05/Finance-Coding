"""SEC EDGAR client: official company financials (XBRL "company facts"), free.

The SEC requires every client to identify itself with a contact email and to
stay under 10 requests a second. Set SEC_USER_AGENT in .env (and as a GitHub
secret for the daily run) to a name and an email of your choice, for example
"TradingCity Jane Doe jane@example.com".
"""
from __future__ import annotations

import os
import time

import requests

_last = 0.0
_tickers: dict[str, int] | None = None


def _get(url: str) -> dict:
    global _last
    wait = 0.15 - (time.time() - _last)
    if wait > 0:
        time.sleep(wait)
    _last = time.time()
    ua = os.getenv("SEC_USER_AGENT", "").strip()
    if "@" not in ua:
        raise RuntimeError("SEC_USER_AGENT is missing. The SEC requires a contact email: set SEC_USER_AGENT "
                           "in .env (and as a GitHub secret) to something like 'TradingCity Your Name you@example.com'.")
    r = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=30)
    r.raise_for_status()
    return r.json()


def cik_for(ticker: str) -> int | None:
    """The SEC's company number (CIK) for a stock ticker."""
    global _tickers
    if _tickers is None:
        data = _get("https://www.sec.gov/files/company_tickers.json")
        _tickers = {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}
    return _tickers.get(ticker.upper())


def company_facts(cik: int) -> dict:
    """Every number the company has reported in its filings, as published by the SEC."""
    return _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
