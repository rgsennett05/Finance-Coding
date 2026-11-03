"""Checks the Fundamentals Analyst on made-up SEC filings (no internet needed)."""
from datetime import date

from agents.fundamentals_analyst import analyze, annual, band, run


def fy(year, val, start=None):
    return {"form": "10-K", "start": start or f"{year - 1}-10-01", "end": f"{year}-09-30", "val": val, "filed": f"{year}-11-01"}


def inst(year, val):
    return {"form": "10-K", "end": f"{year}-09-30", "val": val, "filed": f"{year}-11-01"}


def facts(usgaap, shares=1_000, dei=None):
    return {"entityName": "Test Co", "facts": {
        "us-gaap": {k: {"units": {"USD/shares" if k.startswith("EarningsPerShare") else "USD": v}} for k, v in usgaap.items()},
        "dei": dei or {"EntityCommonStockSharesOutstanding": {"units": {"shares": [{"end": "2026-10-15", "val": shares, "filed": "2026-11-01"}]}}},
    }}


HEALTHY = facts({
    "Revenues": [fy(2025, 1_000), fy(2026, 1_200)],                     # +20% growth
    "OperatingIncomeLoss": [fy(2026, 360)],                               # 30% margin
    "NetIncomeLoss": [fy(2026, 300)],
    "EarningsPerShareDiluted": [fy(2026, 0.30)],
    "NetCashProvidedByUsedInOperatingActivities": [fy(2026, 400)],
    "PaymentsToAcquirePropertyPlantAndEquipment": [fy(2026, 100)],         # FCF 300
    "StockholdersEquity": [inst(2026, 1_200)],                            # ROE 25%
    "LongTermDebtNoncurrent": [inst(2026, 240)],                          # D/E 0.2
})


def test_a_healthy_cheap_grower_scores_strong():
    f = analyze("GOOD", HEALTHY, price=4.0, today=date(2026, 11, 3))       # P/E 13.3, FCF yield 7.5%
    assert f.available and f.label == "strong"
    assert round(f.pe, 1) == 13.3 and round(f.fcf_yield, 3) == 0.075
    assert round(f.revenue_growth, 2) == 0.20 and round(f.operating_margin, 2) == 0.30
    assert round(f.roe, 2) == 0.25 and round(f.debt_to_equity, 2) == 0.20
    assert "P/E 13" in f.explanation


def test_the_same_business_at_a_sky_high_price_scores_lower():
    cheap = analyze("A", HEALTHY, price=4.0, today=date(2026, 11, 3))
    pricey = analyze("A", HEALTHY, price=40.0, today=date(2026, 11, 3))     # P/E 133
    assert pricey.scores["valuation"] < cheap.scores["valuation"] and pricey.score < cheap.score


def test_renamed_tags_are_merged_per_year():
    f = facts({"Revenues": [fy(2024, 900)], "RevenueFromContractWithCustomerExcludingAssessedTax": [fy(2025, 950)]})
    assert annual(f, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]) == [("2024-09-30", 900.0), ("2025-09-30", 950.0)]


def test_quarterly_figures_are_ignored():
    f = facts({"Revenues": [fy(2026, 1_200), {"form": "10-Q", "start": "2026-07-01", "end": "2026-09-30", "val": 300, "filed": "2026-10-30"},
                            {"form": "10-K", "start": "2026-07-01", "end": "2026-09-30", "val": 300, "filed": "2026-11-01"}]})
    assert annual(f, ["Revenues"]) == [("2026-09-30", 1200.0)]


def test_banks_skip_margin_cash_flow_and_debt():
    bank = facts({**{k: v["units"]["USD"] for k, v in HEALTHY["facts"]["us-gaap"].items() if k != "EarningsPerShareDiluted"},
                  "EarningsPerShareDiluted": [fy(2026, 0.30)], "Deposits": [inst(2026, 5_000)]})
    f = analyze("BANK", bank, price=4.0, today=date(2026, 11, 3))
    assert f.is_bank and f.operating_margin is None and f.fcf_yield is None and f.debt_to_equity is None
    assert f.scores["health"] is None and f.score is not None and "Bank" in f.explanation


def test_old_or_missing_reports_are_not_judged():
    assert not analyze("OLD", HEALTHY, price=4.0, today=date(2028, 6, 1)).available
    assert "No annual report" in analyze("NEW", facts({}), price=4.0).reason


def test_negative_equity_does_not_produce_a_nonsense_ratio():
    f = facts({**{k: v["units"]["USD"] for k, v in HEALTHY["facts"]["us-gaap"].items() if k != "EarningsPerShareDiluted"},
               "EarningsPerShareDiluted": [fy(2026, 0.30)], "StockholdersEquity": [inst(2026, -50)]})
    r = analyze("BUYBACK", f, price=4.0, today=date(2026, 11, 3))
    assert r.roe is None and r.debt_to_equity is None


def test_band_maps_both_directions():
    assert band(0.07, 0.02, 0.07) == 1 and band(0.02, 0.02, 0.07) == -1 and band(0.3, 2.0, 0.3) == 1
    assert band(None, 0, 1) is None


def test_funds_and_unknown_tickers_are_explained(monkeypatch):
    monkeypatch.setattr("data.sec.cik_for", lambda t: None)
    out = run(["VOO", "ZZZZ"], {}, skip={"VOO"})
    assert "fund" in out[0].reason and "Not found" in out[1].reason
