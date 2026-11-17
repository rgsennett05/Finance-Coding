"""Runs the whole fund once: analyze → decide → trim → check risk → trade → fix stop-losses → log.

    python -m trading.run --dry-run   # preview everything, place no orders
    python -m trading.run             # place PAPER orders (asks you to confirm)
    python -m trading.run --yes       # place PAPER orders without asking (for schedules)
    python -m trading.run --yes --once-a-day   # what the daily schedule runs (see below)

--once-a-day: the schedule starts several times a day because GitHub often starts scheduled jobs
hours late. Only the first attempt while the market is open trades; later ones stop straight away.
If every attempt was late and the market has closed, one run still happens so stops get checked.
"""
from __future__ import annotations

import argparse
import sys

from agents import fundamentals_analyst, market_analyst, portfolio_manager, risk_manager
from config.settings import load_settings
from data.broker import LiveKeyError, trading_client
from trading import alerts, journal, orders, stops
from trading.portfolio import from_alpaca


def already_ran_today(clock) -> bool:
    """True if today's run is done: a run while the market was open, or (market closed) any run."""
    from zoneinfo import ZoneInfo
    today = clock.timestamp.astimezone(ZoneInfo("America/New_York")).date()
    runs = journal.paper_runs_on(today)
    if any(r.get("market_open") for r in runs):
        print(f"✅ Today's run ({today}) already happened while the market was open. Nothing to do.")
        return True
    if runs and not clock.is_open:
        print(f"✅ Today's run ({today}) already happened. The market is closed, so nothing to do.")
        return True
    return False


def main(argv: list[str] | None = None) -> int:
    args = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    args.add_argument("--dry-run", action="store_true", help="preview only; place no orders")
    args.add_argument("--yes", action="store_true", help="don't ask for confirmation before placing paper orders")
    args.add_argument("--once-a-day", action="store_true",
                      help="skip if today's run already happened (used by the several-times-a-day schedule)")
    opts = args.parse_args(argv)

    try:
        client = trading_client()
    except LiveKeyError as err:
        print(f"\n⛔ {err}\n")
        return 2

    settings = load_settings()
    clock = client.get_clock()
    if opts.once_a_day and not opts.dry_run and already_ran_today(clock):
        return 0
    portfolio = from_alpaca(client, settings.risk.cooldown_days)
    mode = "DRY RUN" if opts.dry_run else "PAPER TRADING"
    print(f"\n🏙️  Trading City — {mode}")
    print(f"   Market is {'OPEN' if clock.is_open else 'CLOSED'} (next open {clock.next_open:%a %b %d %H:%M} ET)")
    print(f"   Portfolio ${portfolio.portfolio_value:,.2f} · cash ${portfolio.cash:,.2f} · "
          f"{len(portfolio.positions)} positions\n")

    print("📈 Market Analyst")
    signals = market_analyst.run(settings.tickers)
    for s in sorted(signals, key=lambda s: -s.score):
        print(f"   {s.ticker:<6} {s.label:<8} score {s.score:+.2f}")

    print("\n🏦 Fundamentals Analyst")
    try:
        fundamentals = fundamentals_analyst.run(settings.tickers, {s.ticker: s.price for s in signals}, skip={settings.benchmark})
    except Exception as err:   # advisory agent: a data problem must never stop trading
        fundamentals = []
        print(f"   Skipped: {type(err).__name__}: {err}")
    for f in fundamentals:
        print(f"   {f.ticker:<6} " + (f"{f.label:<8} score {f.score:+.2f}" if f.available and f.score is not None else f"— {f.reason}"))

    print("\n🧠 Portfolio Manager")
    decisions = portfolio_manager.decide(signals, portfolio, settings, fundamentals)
    for d in decisions:
        print(f"   {d.ticker:<6} {d.reason}")

    proposals = portfolio_manager.proposals(decisions)
    selling = {p.ticker for p in proposals if p.side == "sell"}
    trims = [t for t in risk_manager.trim_proposals(portfolio, settings.risk) if t.ticker not in selling]
    for t in trims:
        print(f"   {t.ticker:<6} {t.reason}")

    print("\n🛡️  Risk Manager")
    reviewed = risk_manager.review(proposals + trims, portfolio, settings.risk)
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

    print("\n🧯 Stop-loss check")
    stop_actions = stops.maintain(client, settings.risk, dry_run=dry_run)
    for a in stop_actions:
        print(f"   {a.status.upper():<8} {a.ticker:<6} {a.detail}")
    if not stop_actions:
        print("   No positions to protect yet.")

    found = alerts.find(results, stop_actions, client=client, dry_run=dry_run)
    alerts.report(found)

    path = journal.write({
        "mode": "dry-run" if dry_run else "paper",
        "market_open": clock.is_open,
        "settings": settings,
        "portfolio_before": portfolio,
        "signals": signals,
        "fundamentals": fundamentals,
        "decisions": decisions,
        "risk_review": [{**r.__dict__, "value": r.value} for r in reviewed],
        "orders": results,
        "trims": trims,
        "stop_maintenance": stop_actions,
        "alerts": found,
    })
    print(f"\n📝 Logged to {path.relative_to(path.parent.parent)}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
