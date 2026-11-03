"""Fundamentals Analyst — is each company a healthy, reasonably priced business?

Reads the company's own annual reports (10-K) as published by the SEC, and the
live share price, then scores four areas from −1 (weak) to +1 (strong):

  Valuation      P/E ratio and free-cash-flow yield     (cheaper = better)
  Growth         revenue growth vs. the year before
  Profitability  operating margin and return on equity
  Health         debt compared with shareholders' equity (less = better)

Plain code does all the math. Banks are scored without margin, cash-flow and
debt measures (they don't apply to banks); funds such as VOO have no company
filings and are skipped. It's advisory for now: the Portfolio Manager sees the
result but doesn't act on it yet.

Adapted from our own Ticker City prototype (branch archive/ticker-city-v1).

Run it on the watchlist:
    python -m agents.fundamentals_analyst
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np

STALE_DAYS = 550   # an annual report older than ~18 months is too old to judge on

CONCEPTS = {
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenuesNetOfInterestExpense", "SalesRevenueNet"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps": ["EarningsPerShareDiluted", "EarningsPerShareBasic"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsToAcquireProductiveAssets"],
    "equity": ["StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "long_term_debt": ["LongTermDebtNoncurrent", "LongTermDebt"],
    "current_debt": ["LongTermDebtCurrent", "DebtCurrent"],
}
INSTANT = {"equity", "long_term_debt", "current_debt"}


@dataclass
class Fundamentals:
    ticker: str
    available: bool
    reason: str = ""
    company: str = ""
    fiscal_year_end: str | None = None
    is_bank: bool = False
    price: float | None = None
    pe: float | None = None
    fcf_yield: float | None = None
    revenue_growth: float | None = None
    operating_margin: float | None = None
    roe: float | None = None
    debt_to_equity: float | None = None
    scores: dict = field(default_factory=dict)   # area -> −1..+1
    score: float | None = None
    label: str = "n/a"                           # strong | average | weak | n/a
    explanation: str = ""
    explained_by: str = "rules (no AI key set)"


# ------------------------------------------------------------------------------
# Reading the SEC's company facts
# ------------------------------------------------------------------------------

def annual(facts: dict, concepts: list[str], instant: bool = False, unit: str = "USD") -> list[tuple[str, float]]:
    """[(fiscal-year end date, value)] from 10-K filings, oldest first. Companies rename their tags
    over the years, so every listed tag is read and merged per year (earlier tags in the list win)."""
    by_end: dict[str, tuple[int, str, float]] = {}
    for rank, concept in enumerate(concepts):
        ns = "dei" if concept.startswith("Entity") else "us-gaap"
        rows = facts.get("facts", {}).get(ns, {}).get(concept, {}).get("units", {})
        rows = rows.get(unit) or rows.get("USD/shares") or []
        for r in rows:
            if r.get("form") != "10-K" or "end" not in r:
                continue
            if not instant:
                if "start" not in r:
                    continue
                days = (date.fromisoformat(r["end"]) - date.fromisoformat(r["start"])).days
                if not 350 <= days <= 380:
                    continue
            prev = by_end.get(r["end"])
            if prev is None or rank < prev[0] or (rank == prev[0] and r.get("filed", "") > prev[1]):
                by_end[r["end"]] = (rank, r.get("filed", ""), float(r["val"]))
    return sorted((end, v[2]) for end, v in by_end.items())


def extract(facts: dict) -> dict:
    """The latest fiscal year's numbers (and the year before, for growth)."""
    out: dict = {"company": facts.get("entityName", "")}
    for key, concepts in CONCEPTS.items():
        unit = "USD/shares" if key == "eps" else "USD"
        series = annual(facts, concepts, instant=key in INSTANT, unit=unit)
        out[key] = series[-1][1] if series else None
        out[key + "_end"] = series[-1][0] if series else None
        if key == "revenue":
            out["revenue_prior"] = series[-2][1] if len(series) > 1 else None
    out["fiscal_year_end"] = out.get("revenue_end") or out.get("net_income_end")
    out["is_bank"] = "Deposits" in facts.get("facts", {}).get("us-gaap", {})
    shares = None
    for ns, concept in [("dei", "EntityCommonStockSharesOutstanding"), ("us-gaap", "CommonStockSharesOutstanding"),
                        ("us-gaap", "WeightedAverageNumberOfDilutedSharesOutstanding")]:
        rows = facts.get("facts", {}).get(ns, {}).get(concept, {}).get("units", {}).get("shares", [])
        if rows:
            shares = float(sorted(rows, key=lambda r: (r["end"], r.get("filed", "")))[-1]["val"])
            break
    out["shares"] = shares
    return out


# ------------------------------------------------------------------------------
# Scoring (plain code)
# ------------------------------------------------------------------------------

def band(x: float | None, bad: float, good: float) -> float | None:
    """Map x linearly so that `bad` → −1 and `good` → +1 (clipped). Works whichever way round."""
    if x is None or not np.isfinite(x):
        return None
    return float(np.clip(-1 + 2 * (x - bad) / (good - bad), -1, 1))


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return float(np.mean(xs)) if xs else None


def analyze(ticker: str, facts: dict, price: float | None, today: date | None = None) -> Fundamentals:
    today = today or date.today()
    d = extract(facts)
    f = Fundamentals(ticker, True, company=d["company"], fiscal_year_end=d["fiscal_year_end"], is_bank=d["is_bank"], price=price)
    if not d["fiscal_year_end"]:
        return Fundamentals(ticker, False, "No annual report (10-K) figures found in the SEC data.", company=d["company"])
    if (today - date.fromisoformat(d["fiscal_year_end"])).days > STALE_DAYS:
        return Fundamentals(ticker, False, f"The latest annual figures are from {d['fiscal_year_end']}, too old to judge on.",
                            company=d["company"])

    rev, ni, eq = d["revenue"], d["net_income"], d["equity"]
    if price and d["eps"] and d["eps"] > 0:
        f.pe = price / d["eps"]
    if d["revenue_prior"] and rev:
        f.revenue_growth = rev / d["revenue_prior"] - 1
    if ni is not None and eq and eq > 0:
        f.roe = ni / eq
    if not f.is_bank:
        if d["operating_income"] is not None and rev:
            f.operating_margin = d["operating_income"] / rev
        if d["operating_cash_flow"] is not None and d["capex"] is not None and price and d["shares"]:
            f.fcf_yield = (d["operating_cash_flow"] - d["capex"]) / (price * d["shares"])
        debt = (d["long_term_debt"] or 0) + (d["current_debt"] or 0)
        if eq and eq > 0:
            f.debt_to_equity = debt / eq

    earnings_yield = 1 / f.pe if f.pe else None
    f.scores = {
        "valuation": _mean([band(earnings_yield, 0.02, 0.07), band(f.fcf_yield, 0.01, 0.06)]),
        "growth": band(f.revenue_growth, -0.05, 0.15),
        "profitability": _mean([band(f.operating_margin, 0.05, 0.30), band(f.roe, 0.05, 0.25)]),
        "health": band(f.debt_to_equity, 2.0, 0.3),
    }
    f.score = _mean(list(f.scores.values()))
    if f.score is not None:
        f.score = round(f.score, 3)
        f.label = "strong" if f.score > 0.33 else "weak" if f.score < -0.33 else "average"
    f.explanation = explain(f)
    return f


def explain(f: Fundamentals) -> str:
    pct = lambda x: f"{x * 100:+.0f}%" if x is not None else "n/a"
    bits = []
    if f.pe:
        bits.append(f"P/E {f.pe:.0f} ({'expensive' if f.pe > 30 else 'cheap' if f.pe < 15 else 'fairly priced'})")
    if f.fcf_yield is not None:
        bits.append(f"free-cash-flow yield {f.fcf_yield * 100:.1f}%")
    if f.revenue_growth is not None:
        bits.append(f"revenue {pct(f.revenue_growth)} last fiscal year")
    if f.operating_margin is not None:
        bits.append(f"operating margin {f.operating_margin * 100:.0f}%")
    if f.roe is not None:
        bits.append(f"return on equity {f.roe * 100:.0f}%")
    if f.debt_to_equity is not None:
        bits.append(f"debt {f.debt_to_equity:.1f}× equity")
    note = " Bank: margin, cash-flow and debt measures don't apply, so it's judged on price, growth and return on equity." if f.is_bank else ""
    fy = f" (fiscal year ending {f.fiscal_year_end})" if f.fiscal_year_end else ""
    text = ", ".join(bits)
    return f"{text[:1].upper() + text[1:]}{fy}.{note} Fundamentals: {f.label}."


# ------------------------------------------------------------------------------
# Agent entry point
# ------------------------------------------------------------------------------

def run(tickers: list[str], prices: dict[str, float], skip: set[str] = frozenset()) -> list[Fundamentals]:
    from data.sec import cik_for, company_facts

    out = []
    for t in tickers:
        if t in skip:
            out.append(Fundamentals(t, False, "A fund that tracks an index, not a company, so there are no company fundamentals."))
            continue
        try:
            cik = cik_for(t)
            if cik is None:
                out.append(Fundamentals(t, False, "Not found in the SEC's company list."))
                continue
            out.append(analyze(t, company_facts(cik), prices.get(t)))
        except Exception as err:  # one company's data problem must not stop the others
            out.append(Fundamentals(t, False, f"Couldn't read SEC data: {type(err).__name__}: {err}"))
    return out


if __name__ == "__main__":
    from dotenv import load_dotenv

    from config.settings import load_settings
    from data.market_data import live_quotes

    load_dotenv()
    s = load_settings()
    quotes = live_quotes(s.tickers)
    results = run(s.tickers, {t: q["price"] for t, q in quotes.items()}, skip={s.benchmark})
    print(f"\n{'Stock':<6}{'P/E':>6}{'FCF yld':>9}{'Rev gr':>8}{'Op mgn':>8}{'ROE':>6}{'D/E':>6}{'Score':>7}  Label")
    num = lambda x, f: "—" if x is None else f.format(x)
    for r in results:
        if not r.available:
            print(f"{r.ticker:<6}  — {r.reason}")
            continue
        print(f"{r.ticker:<6}{num(r.pe, '{:.0f}'):>6}{num(r.fcf_yield and r.fcf_yield * 100, '{:.1f}%'):>9}"
              f"{num(r.revenue_growth and r.revenue_growth * 100, '{:+.0f}%'):>8}{num(r.operating_margin and r.operating_margin * 100, '{:.0f}%'):>8}"
              f"{num(r.roe and r.roe * 100, '{:.0f}%'):>6}{num(r.debt_to_equity, '{:.1f}'):>6}{num(r.score, '{:+.2f}'):>7}  {r.label}")
    print()
    for r in results:
        print(f"{r.ticker} — {r.explanation if r.available else r.reason}\n")
