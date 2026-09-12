#!/usr/bin/env python3
"""
Batch Orchestration CLI

Utility for manually triggering and monitoring batch jobs.

Usage:
    python scripts/batch_cli.py run                    # Run batch now
    python scripts/batch_cli.py run --tickers AAPL TSLA # Run for specific tickers
    python scripts/batch_cli.py status                  # Check last run status
    python scripts/batch_cli.py test                    # Test run with single ticker
"""

import asyncio
import argparse
import sys
import logging
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.services.orchestration.batch_scheduler import (
    run_scheduled_batch,
    BatchOrchestrator,
    SchedulerConfig,
)


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def cmd_run(args):
    """Run a batch job now."""
    tickers = args.tickers if args.tickers else None

    print("\n" + "="*60)
    print("🚀 MANUAL BATCH EXECUTION")
    print("="*60)

    if tickers:
        print(f"Tickers: {', '.join(tickers)}")
    else:
        print(f"Tickers: {', '.join(SchedulerConfig.DEFAULT_TICKERS)}")

    print()

    results = await run_scheduled_batch(tickers)

    if results.get("status") == "success":
        print("\n✅ Batch completed successfully!")
        print(f"   Processed: {results['tickers_succeeded']}/{results['tickers_processed']}")
        print(f"   Duration: {results['duration_seconds']:.2f}s")
    else:
        print(f"\n❌ Batch failed: {results.get('error')}")
        return 1

    return 0


async def cmd_test(args):
    """Run a test batch with a single ticker."""
    test_ticker = args.ticker or "AAPL"

    print("\n" + "="*60)
    print(f"🧪 TEST RUN: {test_ticker}")
    print("="*60 + "\n")

    orchestrator = BatchOrchestrator([test_ticker])
    results = await orchestrator.run_full_pipeline()

    if results.get("status") == "success":
        print("\n✅ Test completed successfully!")

        # Print detailed results
        stages = results.get("stages", {})
        for stage_name, stage_data in stages.items():
            if isinstance(stage_data, dict) and "summary" in stage_data:
                summary = stage_data["summary"]
                print(f"\n{stage_name.upper()}:")
                for key, value in summary.items():
                    print(f"  {key}: {value}")

        return 0
    else:
        print(f"\n❌ Test failed: {results.get('error')}")
        return 1


async def cmd_status(args):
    """Check the status of the last batch run."""
    from app.db.session import async_session
    from app.db.models import HybridSignal
    from sqlalchemy import select, func

    print("\n" + "="*60)
    print("📊 BATCH STATUS")
    print("="*60 + "\n")

    async with async_session() as session:
        # Get latest signals
        result = await session.execute(
            select(
                func.max(HybridSignal.updated_at).label("last_update"),
                func.count(HybridSignal.id).label("total_signals"),
            )
        )
        stats = result.first()

        if stats and stats.last_update:
            print(f"Last Update: {stats.last_update.strftime('%Y-%m-%d %H:%M:%S')}")
            print(f"Total Signals: {stats.total_signals}")

            # Time since last update
            now = datetime.utcnow()
            time_diff = now - stats.last_update
            hours = time_diff.total_seconds() / 3600

            print(f"Time Since Last Update: {hours:.1f} hours")

            # Get signal distribution
            result = await session.execute(
                select(
                    HybridSignal.signal,
                    func.count(HybridSignal.id).label("count"),
                )
                .group_by(HybridSignal.signal)
            )

            print("\nSignal Distribution:")
            for row in result:
                print(f"  {row.signal}: {row.count}")

        else:
            print("No batch runs found in database.")

    print()
    return 0


async def cmd_schedule(args):
    """Show the batch schedule."""
    print("\n" + "="*60)
    print("📅 BATCH SCHEDULE")
    print("="*60 + "\n")

    for schedule in SchedulerConfig.SCHEDULE_TIMES:
        print(f"  {schedule['hour']:02d}:{schedule['minute']:02d} - {schedule['name']}")

    print()
    print(f"Default Tickers: {', '.join(SchedulerConfig.DEFAULT_TICKERS)}")
    print()

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Quantimental Batch Orchestration CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Run command
    run_parser = subparsers.add_parser("run", help="Run a batch job now")
    run_parser.add_argument(
        "--tickers",
        nargs="+",
        help="Specific tickers to analyze (default: watchlist)"
    )

    # Test command
    test_parser = subparsers.add_parser("test", help="Run a test with single ticker")
    test_parser.add_argument(
        "--ticker",
        default="AAPL",
        help="Ticker to test (default: AAPL)"
    )

    # Status command
    subparsers.add_parser("status", help="Check last batch run status")

    # Schedule command
    subparsers.add_parser("schedule", help="Show batch schedule")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Setup logging
    setup_logging(args.verbose)

    # Execute command
    commands = {
        "run": cmd_run,
        "test": cmd_test,
        "status": cmd_status,
        "schedule": cmd_schedule,
    }

    exit_code = asyncio.run(commands[args.command](args))
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
