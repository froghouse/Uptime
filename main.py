#!/usr/bin/env python3
"""
Enhanced URL Uptime Monitor
This script monitors the uptime of specified URLs, generates daily reports,
and supports command-line arguments for flexible operation.
It can run in continuous monitoring mode or generate reports for specific dates.
It uses asyncio for non-blocking operations and supports both YAML and JSON configuration files.
"""

import asyncio
import argparse
from datetime import datetime, timedelta

from monitor_config import load_config_from_file
from uptime_monitor import UptimeMonitor


async def main() -> None:
    """Main entry point with command-line argument handling"""

    parser = argparse.ArgumentParser(
        description="Enhanced URL Uptime Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # Run continuous monitoring
  %(prog)s --report                 # Generate report for yesterday
  %(prog)s --report --date 2025-05-30  # Generate report for specific date
  %(prog)s --report --days 7        # Generate reports for last 7 days
  %(prog)s --config custom.json     # Use custom config file
        """,
    )

    parser.add_argument(
        "--report",
        "-r",
        action="store_true",
        help="Generate uptime report instead of running monitor",
    )

    parser.add_argument(
        "--date",
        "-d",
        type=str,
        help="Specific date for report generation (YYYY-MM-DD format). Defaults to yesterday.",
    )

    parser.add_argument("--days", type=int, help="Generate reports for the last N days")

    parser.add_argument(
        "--config",
        "-c",
        type=str,
        default="monitor_config.yaml",
        help="Path to configuration file (default: monitor_config.yaml)",
    )

    parser.add_argument(
        "--today",
        action="store_true",
        help="Generate report for today (use with --report)",
    )

    args = parser.parse_args()

    # Load configuration
    config = load_config_from_file(args.config)

    # Create monitor instance
    monitor = UptimeMonitor(config)

    if args.report:
        # Report generation mode
        if args.days:
            # Generate reports for multiple days
            print(f"Generating reports for the last {args.days} days...")
            for i in range(args.days):
                target_date = datetime.now().date() - timedelta(
                    days=i + (0 if args.today else 1)
                )
                print(f"Generating report for {target_date}...")
                await monitor.generate_daily_report(target_date)

        elif args.date:
            # Generate report for specific date
            try:
                target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
                print(f"Generating report for {target_date}...")
                await monitor.generate_daily_report(target_date)
            except ValueError:
                print("Error: Invalid date format. Use YYYY-MM-DD (e.g., 2025-05-30)")
                return

        elif args.today:
            # Generate report for today
            target_date = datetime.now().date()
            print(f"Generating report for today ({target_date})...")
            await monitor.generate_daily_report(target_date)

        else:
            # Default: generate report for yesterday
            yesterday = datetime.now().date() - timedelta(days=1)
            print(f"Generating report for yesterday ({yesterday})...")
            await monitor.generate_daily_report(yesterday)

    else:
        # Monitoring mode (default)
        print("Starting continuous uptime monitoring...")
        print("Use Ctrl+C to stop, or run with --help to see report options")
        try:
            await monitor.run_monitor()
        except KeyboardInterrupt:
            print("\nShutdown requested by user")
        except Exception as e:
            print(f"Unexpected error: {e}")
            monitor.logger.error(f"Unexpected error in main: {e}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
