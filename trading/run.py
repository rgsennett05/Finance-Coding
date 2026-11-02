"""Runs the whole fund once: analyze → decide → check risk → trade → log.

    python -m trading.run --dry-run   # preview everything, place no orders
    python -m trading.run             # place PAPER orders (asks you to confirm)
    python -m trading.run --yes       # place PAPER orders without asking (for schedules)
"""
from __future__ import annotations

import argparse
import sys

from agents import market_analyst, portfolio_manager, risk_manager
from config.settings import load_settings
from data.broker import LiveKeyError, trading_client
from trading import journal, orders
from trading.portfolio import from_alpaca


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--dry-run", action="store_true", help="preview only; place no orders")
    args.add_argument("--yes", action="store_true", help="don't ask for confirmation before placing paper orders")
    opts = args.parse_args(argv)

    try:
        client = trading_client()
    except LiveKeyError as err:
        print(f"\n⛔ {err}\n")
        return 2

    settings = load_settings()
    clock = client.get_clock()
    portfolio = from_alpaca()
    mode = "DRY RUN" if opts.dry_run else "PAPER TRADING"
    print(f"\n🏙️  Trading City — {mode}")
    print(f"   Market is {'OPEN' if clock.is_open else 'CLOSED'} (next open {clock.next_open:%a %b %d %H:%M} ET)")
    print(f"   Portfolio ${portfolio.portfolio_value:,.2f} · cash ${portfolio.cash:,.2f} · "
          f"{len(portfolio.positions)} positions\n")

    print("📈 Market Analyst")
    signals = market_analyst.run(settings.tickers)
    for s in sorted(signals, key=lambda s: -s.score):
        print(f"   {s.ticker:<6} {s.label:<8} score {s.score:+.2f}")

    print("\n🧠 Portfolio Manager")
    decisions = portfolio_manager.decide(signals, portfolio, settings)
    for d in decisions:
        print(f"   {d.ticker:<6} {d.reason}")

    print("\n🛡️  Risk Manager")
    reviewed = risk_manager.review(portfolio_manager.proposals(decisions), portfolio, settings.risk)
    for r in reviewed:
        print("   " + r.summary().replace("\n", "\n   "))
    if not reviewed:
        print("   Nothing to review.")

    dry_run = opts.dry_run
    approved = [r for r in reviewed if r.approved]
    if approved and not dry_run and not opts.yes:
        answer = input(f"\nPlace {len(approved)} PAPER order(s) now? Type 'yes' to confirm: ").strip().lower()
        if answer != "yes":
            print("Not confirmed — treating this run as a dry run.")
            dry_run = True

    print("\n📨 Orders")
    results = orders.place(reviewed, client=client, dry_run=dry_run)
    for o in results:
        print(f"   {o.status.upper():<10} {o.side.upper()} {o.qty} {o.ticker} — {o.detail}")
    if not results:
        print("   No orders.")

    path = journal.write({
        "mode": "dry-run" if dry_run else "paper",
        "market_open": clock.is_open,
        "settings": settings,
        "portfolio_before": portfolio,
        "signals": signals,
        "decisions": decisions,
        "risk_review": [{**r.__dict__, "value": r.value} for r in reviewed],
        "orders": results,
    })
    print(f"\n📝 Logged to {path.relative_to(path.parent.parent)}")
    return 1 if any(o.status == "failed" for o in results) else 0


if __name__ == "__main__":
    sys.exit(main())
