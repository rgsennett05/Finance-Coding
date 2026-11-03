"""Portfolio Manager — decides what the fund wants to do this run.

Rules mode (free, no AI) blends both analysts into one score (weights in settings.toml):
  - BUY  stocks we don't own whose blended score is above buy_above, highest first
  - SELL stocks we own whose blended score falls below sell_below
  - HOLD everything else
A stock with no fundamentals (a fund, a missing report) uses the market score alone.
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


def blend(signal: MarketSignals, fund, settings: Settings) -> tuple[float, str]:
    """One score from -1 to +1 combining both analysts, plus a plain-English breakdown."""
    mw, fw = settings.market_weight, settings.fundamentals_weight
    has_fund = fund is not None and _get(fund, "available") and _get(fund, "score") is not None
    if not has_fund or fw == 0:
        why = "no fundamentals available" if not has_fund else "fundamentals weight is 0"
        return signal.score, f"blended score {signal.score:+.2f} (market {signal.score:+.2f} only; {why})"
    f = _get(fund, "score")
    score = (mw * signal.score + fw * f) / (mw + fw)
    return score, (f"blended score {score:+.2f} = market {signal.score:+.2f} × {mw / (mw + fw):.0%} "
                   f"+ fundamentals {f:+.2f} × {fw / (mw + fw):.0%}")


def _get(obj, key):
    return obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)


def decide_rules(signals: list[MarketSignals], portfolio: PortfolioState, settings: Settings,
                 fundamentals: list | None = None) -> list[PMDecision]:
    decisions: list[PMDecision] = []
    by_ticker = {s.ticker: s for s in signals}
    funds = {_get(f, "ticker"): f for f in (fundamentals or [])}
    scored = [(s, *blend(s, funds.get(s.ticker), settings)) for s in signals]

    for s, score, why in sorted(scored, key=lambda x: -x[1]):
        held = portfolio.positions.get(s.ticker)
        owned = held is not None and held.qty > 0

        if s.ticker in portfolio.pending_buys and not owned:
            decisions.append(PMDecision(s.ticker, "hold", f"WAIT: {why}; a buy order is already waiting to fill."))
        elif s.ticker == settings.benchmark:
            decisions.append(PMDecision(s.ticker, "hold", f"{s.ticker} is the benchmark we measure against; it is never traded."))
        elif score > settings.buy_above and not owned:
            reason = f"BUY: {why}, above the {settings.buy_above:+.2f} buy level, and we don't own it yet."
            decisions.append(PMDecision(s.ticker, "buy", reason, TradeProposal(s.ticker, "buy", s.price, reason=reason)))
        elif score < settings.sell_below and owned:
            reason = f"SELL: {why}, below the {settings.sell_below:+.2f} sell level, so we exit the {held.qty}-share position."
            decisions.append(PMDecision(s.ticker, "sell", reason, TradeProposal(s.ticker, "sell", s.price, reason=reason)))
        elif owned:
            decisions.append(PMDecision(s.ticker, "hold", f"HOLD: {why}; we own it and it's above the sell level."))
        else:
            decisions.append(PMDecision(s.ticker, "hold", f"HOLD (stay out): {why}; not high enough to buy."))

    # Positions we own that the Analyst didn't look at this run: keep, but flag them.
    for ticker, pos in portfolio.positions.items():
        if ticker not in by_ticker and pos.qty > 0:
            decisions.append(PMDecision(ticker, "hold", "HOLD: we own it but it isn't on the watchlist, so there's no signal. Review it by hand."))
    return decisions


def decide(signals: list[MarketSignals], portfolio: PortfolioState, settings: Settings,
           fundamentals: list | None = None) -> list[PMDecision]:
    if settings.portfolio_manager_mode == "ai":
        raise NotImplementedError(
            'AI mode isn\'t built yet. Set portfolio_manager.mode = "rules" in config/settings.toml.'
        )
    return decide_rules(signals, portfolio, settings, fundamentals)


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
