"""Risk Manager — enforces the fund's risk limits. Plain code, no AI.

Given the portfolio and a list of proposed trades, it decides for each one:
approve, shrink, or block — and says why in plain English. Every approved buy
gets a stop-loss price. No prompt or model can change these rules; the only
way to change a limit is config/settings.toml.

Rules (from config/settings.toml):
  - No single position over max_position_pct of the portfolio
  - Keep at least min_cash_pct of the portfolio in cash
  - At most max_open_positions positions
  - Stop-loss on every buy, stop_loss_pct below the entry price
  - Whole shares only (Alpaca only attaches stop-losses to whole-share orders)
  - No shorting (can't sell what we don't own) and no borrowed money
  - Buys still waiting to fill count against cash and position limits, and a
    stock with a buy already waiting can't get a second one
  - Cool-down: no re-buying a stock within cooldown_days of a stop-loss selling it
  - Trimming: a position that grows past max_position_pct + trim_buffer_pct is
    sold back down to max_position_pct

Preview on your paper account (places no orders):
    python -m agents.risk_manager
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from config.settings import RiskLimits, load_settings
from trading.portfolio import PortfolioState


@dataclass(frozen=True)
class TradeProposal:
    ticker: str
    side: str                        # "buy" or "sell"
    price: float                     # latest price per share
    target_value: float | None = None  # buy: how many dollars to put in (None = as much as allowed)
    qty: int | None = None           # sell: how many shares (None = all)
    reason: str = ""                 # why the proposer wants it (shown on the dashboard)


@dataclass
class RiskDecision:
    ticker: str
    side: str
    approved: bool
    qty: int = 0
    price: float = 0.0
    stop_price: float | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def value(self) -> float:
        return round(self.qty * self.price, 2)

    def summary(self) -> str:
        head = (
            f"✅ {self.side.upper()} {self.qty} {self.ticker} @ ${self.price:,.2f} (${self.value:,.2f})"
            + (f", stop-loss ${self.stop_price:,.2f}" if self.stop_price else "")
            if self.approved
            else f"⛔ {self.side.upper()} {self.ticker} blocked"
        )
        return head + "".join(f"\n     – {n}" for n in self.notes)


def stop_price(entry: float, limits: RiskLimits) -> float:
    return round(entry * (1 - limits.stop_loss_pct), 2)


def trim_proposals(portfolio: PortfolioState, limits: RiskLimits) -> list[TradeProposal]:
    """Positions that grew past the limit (plus buffer): sell them back down to the limit."""
    total = portfolio.portfolio_value
    out = []
    if total <= 0:
        return out
    cap = limits.max_position_pct * total
    for t, pos in portfolio.positions.items():
        if pos.qty <= 0 or pos.price <= 0:
            continue
        weight = pos.market_value / total
        if weight <= limits.max_position_pct + limits.trim_buffer_pct:
            continue
        qty = min(pos.qty, math.ceil((pos.market_value - cap) / pos.price))
        out.append(TradeProposal(
            t, "sell", pos.price, qty=qty,
            reason=(f"TRIM: {t} grew to {weight:.1%} of the portfolio, above the "
                    f"{limits.max_position_pct:.0%} limit (+{limits.trim_buffer_pct:.0%} buffer); "
                    f"selling {qty} shares to bring it back to {limits.max_position_pct:.0%}."),
        ))
    return out


def review(
    proposals: list[TradeProposal],
    portfolio: PortfolioState,
    limits: RiskLimits,
    today: date | None = None,
) -> list[RiskDecision]:
    """Check every proposal against the limits. Sells go first so their cash can fund buys."""
    today = today or date.today()
    total = portfolio.portfolio_value
    # Money already promised to buys that haven't filled yet is not available.
    cash = portfolio.cash - portfolio.pending_cost
    holdings = {t: p.market_value for t, p in portfolio.positions.items()}
    for t, cost in portfolio.pending_buys.items():
        holdings[t] = holdings.get(t, 0.0) + cost
    shares = {t: p.qty for t, p in portfolio.positions.items()}
    decisions: list[RiskDecision] = []
    seen: set[str] = set()

    def block(p: TradeProposal, why: str) -> None:
        decisions.append(RiskDecision(p.ticker, p.side, False, price=p.price, notes=[why]))

    ordered = sorted(proposals, key=lambda p: p.side != "sell")  # sells first, order kept within each side
    for p in ordered:
        key = (p.ticker, p.side)
        if p.side not in ("buy", "sell"):
            block(p, f"Unknown side '{p.side}'.")
            continue
        if key in seen:
            block(p, "Duplicate proposal for the same stock and side in this run.")
            continue
        seen.add(key)
        if not (p.price > 0 and math.isfinite(p.price)):
            block(p, "No valid price, so the order can't be sized.")
            continue
        if total <= 0:
            block(p, "Portfolio value is zero or unknown.")
            continue

        if p.side == "sell":
            held = shares.get(p.ticker, 0)
            if held <= 0:
                block(p, "We don't own this stock, and short selling isn't allowed.")
                continue
            qty = held if p.qty is None else min(p.qty, held)
            if qty <= 0:
                block(p, "Sell quantity must be at least 1 share.")
                continue
            d = RiskDecision(p.ticker, "sell", True, qty, p.price)
            if p.reason.startswith("TRIM"):
                d.notes.append(p.reason)
            if p.qty is not None and p.qty > held:
                d.notes.append(f"Asked to sell {p.qty} shares but we only own {held}; selling {held}.")
            cash += qty * p.price
            shares[p.ticker] = held - qty
            holdings[p.ticker] = max(0.0, holdings.get(p.ticker, 0.0) - qty * p.price)
            if shares[p.ticker] == 0:
                holdings.pop(p.ticker, None)
            decisions.append(d)
            continue

        # ---- buys ----
        notes: list[str] = []
        if p.ticker in portfolio.pending_buys:
            block(p, "A buy order for this stock is already waiting to fill; no second order.")
            continue
        stopped = portfolio.recently_stopped.get(p.ticker)
        if stopped is not None and (today - stopped).days < limits.cooldown_days:
            free = stopped.toordinal() + limits.cooldown_days
            block(p, f"Cool-down: a stop-loss sold it on {stopped:%b %d}; no re-buying until "
                     f"{date.fromordinal(free):%b %d} ({limits.cooldown_days}-day rule).")
            continue
        current = holdings.get(p.ticker, 0.0)
        open_positions = sum(1 for v in holdings.values() if v > 0)
        if current == 0 and open_positions >= limits.max_open_positions:
            block(p, f"Already at the limit of {limits.max_open_positions} open positions.")
            continue

        room_position = limits.max_position_pct * total - current
        room_cash = cash - limits.min_cash_pct * total
        wanted = p.target_value if p.target_value is not None else room_position
        if cash < 0:
            block(p, "Cash is negative (borrowed money). No buys until that's fixed.")
            continue
        if room_position <= 0:
            block(p, f"Position is already at the {limits.max_position_pct:.0%} limit.")
            continue
        if room_cash <= 0:
            block(p, f"Buying would drop cash below the {limits.min_cash_pct:.0%} reserve.")
            continue

        allowed = min(wanted, room_position, room_cash)
        if p.target_value is not None and allowed < wanted:
            which = (
                f"the {limits.max_position_pct:.0%} position limit" if room_position <= room_cash
                else f"the {limits.min_cash_pct:.0%} cash reserve"
            )
            notes.append(f"Wanted ${wanted:,.2f}; cut to ${allowed:,.2f} to respect {which}.")
        qty = math.floor(allowed / p.price)
        if qty < 1:
            block(p, f"One share costs ${p.price:,.2f}, more than the ${allowed:,.2f} the limits allow.")
            continue

        d = RiskDecision(p.ticker, "buy", True, qty, p.price, stop_price(p.price, limits), notes)
        d.notes.append(f"Stop-loss set {limits.stop_loss_pct:.0%} below entry.")
        cash -= d.value
        holdings[p.ticker] = current + d.value
        shares[p.ticker] = shares.get(p.ticker, 0) + qty
        decisions.append(d)

    return decisions


if __name__ == "__main__":
    # Dry run: pretend we want to buy every bullish stock at the maximum size.
    from agents import market_analyst
    from trading.portfolio import from_alpaca

    settings = load_settings()
    portfolio = from_alpaca()
    signals = market_analyst.run()
    proposals = [
        TradeProposal(s.ticker, "buy", s.price, reason=f"Market Analyst: {s.label} (score {s.score:.2f})")
        for s in sorted(signals, key=lambda s: -s.score) if s.label == "bullish"
    ]
    print(f"\nPortfolio ${portfolio.portfolio_value:,.2f}, cash ${portfolio.cash:,.2f}, "
          f"{len(portfolio.positions)} open positions")
    print("DRY RUN — no orders are placed.\n")
    for d in review(proposals, portfolio, settings.risk):
        print(d.summary())
