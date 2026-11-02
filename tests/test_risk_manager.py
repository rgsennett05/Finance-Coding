"""Checks every risk rule with made-up portfolios (no internet needed)."""
from agents.risk_manager import TradeProposal, review
from config.settings import RiskLimits
from trading.portfolio import PortfolioState, Position

LIMITS = RiskLimits(max_position_pct=0.10, min_cash_pct=0.10, max_open_positions=10, stop_loss_pct=0.08)


def fresh(cash=100_000.0):
    return PortfolioState(portfolio_value=cash, cash=cash)


def buy(ticker="AAA", price=100.0, target=None):
    return TradeProposal(ticker, "buy", price, target_value=target)


def test_buy_is_capped_at_10_percent_with_whole_shares_and_a_stop():
    [d] = review([buy(price=333.0)], fresh(), LIMITS)
    assert d.approved
    assert d.qty == 30                     # 30 x $333 = $9,990 <= $10,000
    assert d.value <= 10_000
    assert d.stop_price == round(333 * 0.92, 2)


def test_oversized_request_is_shrunk_and_explained():
    [d] = review([buy(target=50_000)], fresh(), LIMITS)
    assert d.approved and d.value <= 10_000
    assert any("10% position limit" in n for n in d.notes)


def test_cash_reserve_is_kept():
    # $15k cash out of $100k: only $5k can be spent before hitting the 10% reserve.
    p = PortfolioState(100_000, 15_000)
    [d] = review([buy(price=100)], p, LIMITS)
    assert d.value <= 5_000
    p2 = PortfolioState(100_000, 9_000)
    [d2] = review([buy()], p2, LIMITS)
    assert not d2.approved and "cash" in d2.notes[0]


def test_several_buys_never_break_the_reserve_together():
    ds = review([buy(f"T{i}") for i in range(12)], fresh(), LIMITS)
    spent = sum(d.value for d in ds if d.approved)
    assert spent <= 90_000
    assert sum(d.approved for d in ds) <= 10


def test_max_open_positions():
    held = {f"H{i}": Position(f"H{i}", 1, 5_000) for i in range(10)}
    p = PortfolioState(100_000, 50_000, held)
    [d] = review([buy("NEW")], p, LIMITS)
    assert not d.approved and "10 open positions" in d.notes[0]
    # adding to an existing position is still allowed
    [d2] = review([buy("H1")], p, LIMITS)
    assert d2.approved and d2.value <= 5_000


def test_share_too_expensive_is_blocked():
    [d] = review([buy(price=12_000)], fresh(), LIMITS)
    assert not d.approved and "One share costs" in d.notes[0]


def test_no_short_selling_and_sells_are_capped():
    p = PortfolioState(100_000, 90_000, {"AAA": Position("AAA", 5, 500)})
    [d] = review([TradeProposal("BBB", "sell", 100)], p, LIMITS)
    assert not d.approved and "short" in d.notes[0]
    [d2] = review([TradeProposal("AAA", "sell", 100, qty=50)], p, LIMITS)
    assert d2.approved and d2.qty == 5


def test_sells_free_up_cash_for_buys():
    p = PortfolioState(100_000, 10_000, {"OLD": Position("OLD", 100, 90_000)})
    ds = review([buy("NEW"), TradeProposal("OLD", "sell", 900.0, qty=20)], p, LIMITS)
    assert ds[0].side == "sell" and ds[0].approved
    assert ds[1].approved and ds[1].value > 0


def test_bad_inputs_are_blocked():
    ds = review([buy(price=0), TradeProposal("X", "hold", 10), buy("A"), buy("A")], fresh(), LIMITS)
    assert [d.approved for d in ds] == [False, False, True, False]


def test_borrowed_money_blocks_buys():
    [d] = review([buy()], PortfolioState(100_000, -5_000), LIMITS)
    assert not d.approved
