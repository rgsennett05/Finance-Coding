"""Checks the four rules added on 2026-11-03: stop-losses at the real purchase price,
trimming oversized positions, the re-buy cool-down, and counting waiting buys."""
from datetime import date
from types import SimpleNamespace as NS

from agents.market_analyst import MarketSignals
from agents.portfolio_manager import decide
from agents.risk_manager import TradeProposal, review, trim_proposals
from config.settings import RiskLimits, load_settings
from trading.portfolio import PortfolioState, Position
from trading.stops import plan

LIMITS = RiskLimits(max_position_pct=0.10, min_cash_pct=0.10, max_open_positions=10, stop_loss_pct=0.08,
                    trim_buffer_pct=0.01, cooldown_days=7)


# ---------- 1. Stop-losses follow the price we actually paid ----------

def pos(t="AAA", qty=10, entry=100.0, price=101.0):
    return NS(symbol=t, qty=str(qty), avg_entry_price=str(entry), current_price=str(price))


def order(t="AAA", side="sell", type_="stop", qty=10, stop=None, filled=0, oid="o1"):
    return NS(id=oid, symbol=t, side=side, type=type_, qty=str(qty), filled_qty=str(filled), stop_price=stop)


def actions(positions, orders):
    return [(a.ticker, a.action, a.qty, a.stop_price) for a, _, _ in plan(positions, orders, LIMITS)]


def test_stop_moves_to_8_percent_under_the_fill_price():
    # Order expected $100 (stop $92), but it filled at $103 -> stop should be $94.76.
    assert actions([pos(entry=103.0, price=104.0)], [order(stop=92.0)]) == [("AAA", "replace", 10, 94.76)]


def test_correct_stop_is_left_alone():
    assert actions([pos()], [order(stop=92.0)])[0][1] == "ok"


def test_missing_stop_is_created():
    assert actions([pos()], []) == [("AAA", "create", 10, 92.0)]


def test_stop_only_covers_shares_not_already_being_sold():
    a = actions([pos(qty=10)], [order(stop=92.0), order(type_="market", qty=4, oid="o2")])
    assert a == [("AAA", "replace", 6, 92.0)]


def test_price_already_below_stop_level_sells():
    assert actions([pos(entry=100.0, price=91.0)], [])[0][1] == "exit"


def test_buy_still_filling_is_skipped():
    assert actions([pos()], [order(side="buy", type_="market")])[0][1] == "skip"


def test_extra_stops_are_cleaned_up():
    a, stops, _ = plan([pos()], [order(stop=92.0), order(stop=92.0, oid="o2")], LIMITS)[0]
    assert a.action == "replace" and "extra" in a.detail and len(stops) == 2


# ---------- 2. Trim positions that grow too big ----------

def test_position_above_11_percent_is_trimmed_back_to_10():
    p = PortfolioState(100_000, 50_000, {"BIG": Position("BIG", 100, 12_000, 90.0)})   # 12%, $120/share
    [t] = trim_proposals(p, LIMITS)
    assert t.side == "sell" and t.qty == 17          # ceil(2,000 / 120)
    assert (12_000 - t.qty * 120) / 100_000 <= 0.10


def test_small_drift_inside_buffer_is_left_alone():
    p = PortfolioState(100_000, 50_000, {"OK": Position("OK", 100, 10_800, 90.0)})     # 10.8%
    assert trim_proposals(p, LIMITS) == []


def test_trim_passes_risk_review_with_its_reason():
    p = PortfolioState(100_000, 50_000, {"BIG": Position("BIG", 100, 12_000, 90.0)})
    [d] = review(trim_proposals(p, LIMITS), p, LIMITS)
    assert d.approved and d.qty == 17 and d.notes[0].startswith("TRIM")


# ---------- 3. Cool-down after a stop-loss ----------

def test_no_rebuy_within_cooldown():
    p = PortfolioState(100_000, 100_000, recently_stopped={"XOM": date(2026, 11, 3)})
    [d] = review([TradeProposal("XOM", "buy", 100.0)], p, LIMITS, today=date(2026, 11, 6))
    assert not d.approved and "Cool-down" in d.notes[0] and "Nov 10" in d.notes[0]


def test_rebuy_allowed_after_cooldown():
    p = PortfolioState(100_000, 100_000, recently_stopped={"XOM": date(2026, 11, 3)})
    [d] = review([TradeProposal("XOM", "buy", 100.0)], p, LIMITS, today=date(2026, 11, 10))
    assert d.approved


# ---------- 4. Waiting buys count against cash and limits ----------

def test_waiting_buys_reduce_cash_but_dont_block_other_buys():
    # $100k cash, $85k already promised to waiting buys -> only $5k left above the 10% reserve.
    p = PortfolioState(100_000, 100_000, pending_buys={"W1": 45_000, "W2": 40_000})
    [d] = review([TradeProposal("NEW", "buy", 100.0)], p, LIMITS)
    assert d.approved and d.value <= 5_000


def test_no_second_buy_for_a_waiting_stock():
    p = PortfolioState(100_000, 100_000, pending_buys={"AAA": 9_000})
    [d] = review([TradeProposal("AAA", "buy", 100.0)], p, LIMITS)
    assert not d.approved and "already waiting" in d.notes[0]


def test_waiting_buys_count_toward_position_limit():
    p = PortfolioState(100_000, 100_000, pending_buys={f"W{i}": 1_000 for i in range(10)})
    [d] = review([TradeProposal("NEW", "buy", 100.0)], p, LIMITS)
    assert not d.approved and "10 open positions" in d.notes[0]


def test_portfolio_manager_waits_instead_of_rebuying():
    s = MarketSignals("AAA", 100.0, None, None, None, None, None, None, None, None, 1, 1, 0, 0.9, "bullish")
    [d] = decide([s], PortfolioState(100_000, 100_000, pending_buys={"AAA": 9_000}), load_settings())
    assert d.action == "hold" and "waiting" in d.reason


def test_settings_have_the_new_limits():
    r = load_settings().risk
    assert r.trim_buffer_pct == 0.01 and r.cooldown_days == 7
