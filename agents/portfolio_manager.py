"""Portfolio Manager — decides what the fund wants to do this run.

Rules mode (free, no AI):
  - BUY  stocks rated bullish that we don't own yet, strongest score first
  - SELL stocks we own that the Market Analyst now rates bearish
  - HOLD everything else
The benchmark (VOO) is only for comparison and is never traded.

The Portfolio Manager only *proposes*. Every proposal goes to the Risk
Manager, which sizes it, attaches a stop-loss, or blocks it.

Preview on your paper account (places no orders):
    python -m agents.portfolio_manager
"""
from __future__ import annotations

from dataclasses import dataclass

from agents.market_analyst import MarketSignals
from agents.risk_manager import TradeProposal
from config.settings import Settings
from trading.portfolio import PortfolioState


@dataclass
class PMDecision:
    ticker: str
    action: str          # buy | sell | hold
    reason: str
    proposal: TradeProposal | None = None


def decide_rules(signals: list[MarketSignals], portfolio: PortfolioState, settings: Settings) -> list[PMDecision]:
    decisions: list[PMDecision] = []
    by_ticker = {s.ticker: s for s in signals}

    for s in sorted(signals, key=lambda x: -x.score):
        held = portfolio.positions.get(s.ticker)
        owned = held is not None and held.qty > 0
        signal_txt = f"Market Analyst rates it {s.label} (score {s.score:+.2f})"

        if s.ticker in portfolio.pending_buys and not owned:
            decisions.append(PMDecision(s.ticker, "hold", f"WAIT: {signal_txt}; a buy order is already waiting to fill."))
        elif s.ticker == settings.benchmark:
            decisions.append(PMDecision(s.ticker, "hold", f"{s.ticker} is the benchmark we measure against; it is never traded."))
        elif s.label == "bullish" and not owned:
            reason = f"BUY: {signal_txt}, and we don't own it yet."
            decisions.append(PMDecision(s.ticker, "buy", reason, TradeProposal(s.ticker, "buy", s.price, reason=reason)))
        elif s.label == "bearish" and owned:
            reason = f"SELL: {signal_txt}, so we exit the {held.qty}-share position."
            decisions.append(PMDecision(s.ticker, "sell", reason, TradeProposal(s.ticker, "sell", s.price, reason=reason)))
        elif owned:
            decisions.append(PMDecision(s.ticker, "hold", f"HOLD: {signal_txt}; we own it and it hasn't turned bearish."))
        else:
            decisions.append(PMDecision(s.ticker, "hold", f"HOLD (stay out): {signal_txt}; not strong enough to buy."))

    # Positions we own that the Analyst didn't look at this run: keep, but flag them.
    for ticker, pos in portfolio.positions.items():
        if ticker not in by_ticker and pos.qty > 0:
            decisions.append(PMDecision(ticker, "hold", "HOLD: we own it but it isn't on the watchlist, so there's no signal. Review it by hand."))
    return decisions


def decide(signals: list[MarketSignals], portfolio: PortfolioState, settings: Settings) -> list[PMDecision]:
    if settings.portfolio_manager_mode == "ai":
        raise NotImplementedError(
            'AI mode isn\'t built yet. Set portfolio_manager.mode = "rules" in config/settings.toml.'
        )
    return decide_rules(signals, portfolio, settings)


def proposals(decisions: list[PMDecision]) -> list[TradeProposal]:
    return [d.proposal for d in decisions if d.proposal is not None]


if __name__ == "__main__":
    from agents import market_analyst, risk_manager
    from config.settings import load_settings
    from trading.portfolio import from_alpaca

    settings = load_settings()
    portfolio = from_alpaca()
    signals = market_analyst.run()
    decisions = decide(signals, portfolio, settings)

    print(f"\nPortfolio Manager ({settings.portfolio_manager_mode} mode)")
    for d in decisions:
        print(f"  {d.ticker:<6} {d.reason}")
    print("\nRisk Manager review — DRY RUN, no orders are placed:")
    for r in risk_manager.review(proposals(decisions), portfolio, settings.risk):
        print("  " + r.summary().replace("\n", "\n  "))
