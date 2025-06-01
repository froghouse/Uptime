#!/usr/bin/env python3
"""
Enhanced URL Uptime Monitor
Improved version with SQLite, proper logging, alerting, and async scheduling
"""

import requests
import sqlite3
import asyncio
import logging
import json
import os
from datetime import datetime, timedelta, time as dt_time
from typing import Optional, Dict, List, Any
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
from dataclasses import dataclass
from pathlib import Path
import importlib.util

# Check for YAML availability
YAML_AVAILABLE = importlib.util.find_spec("yaml") is not None
if not YAML_AVAILABLE:
    print("Warning: PyYAML not found. Please install with: pip install PyYAML")
    print("Falling back to JSON configuration support only.")

# Check for email functionality availability
EMAIL_AVAILABLE = all(
    [
        importlib.util.find_spec("smtplib"),
        importlib.util.find_spec("email.mime.text"),
        importlib.util.find_spec("email.mime.multipart"),
    ]
)

if not EMAIL_AVAILABLE:
    print("Warning: Email functionality not available")
    print("Email alerts will be disabled. Install email dependencies if needed.")


# Configuration dataclass
@dataclass
class MonitorConfig:
    url: str
    check_interval: int = 300  # 5 minutes
    timeout: int = 10
    db_path: str = "uptime_monitor.db"
    days_to_keep: int = 30

    # Email alerting config
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    alert_recipients: List[str] = None

    # Slack alerting config
    slack_webhook_url: Optional[str] = None

    # Alert thresholds
    alert_on_failure: bool = True
    alert_on_recovery: bool = True
    consecutive_failures_threshold: int = 3


class DatabaseManager:
    """Handles all database operations"""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the SQLite database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS uptime_checks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp DATETIME NOT NULL,
                    url TEXT NOT NULL,
                    is_up BOOLEAN NOT NULL,
                    response_time REAL,
                    status_code INTEGER,
                    error_message TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp_url 
                ON uptime_checks(timestamp, url)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_url_timestamp 
                ON uptime_checks(url, timestamp DESC)
            """)

    def save_check_result(
        self,
        url: str,
        is_up: bool,
        response_time: Optional[float] = None,
        status_code: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        """Save a single uptime check result"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO uptime_checks 
                (timestamp, url, is_up, response_time, status_code, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (datetime.now(), url, is_up, response_time, status_code, error_message),
            )

    def get_checks_for_date(
        self, url: str, target_date: datetime.date
    ) -> List[Dict[str, Any]]:
        """Get all checks for a specific date"""
        start_datetime = datetime.combine(target_date, dt_time.min)
        end_datetime = datetime.combine(target_date, dt_time.max)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM uptime_checks 
                WHERE url = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp
            """,
                (url, start_datetime, end_datetime),
            )

            return [dict(row) for row in cursor.fetchall()]

    def get_recent_checks(self, url: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get the most recent checks for a URL"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT * FROM uptime_checks 
                WHERE url = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """,
                (url, limit),
            )

            return [dict(row) for row in cursor.fetchall()]

    def cleanup_old_data(self, days_to_keep: int):
        """Remove data older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                DELETE FROM uptime_checks WHERE timestamp < ?
            """,
                (cutoff_date,),
            )

            deleted_rows = cursor.rowcount
            logging.info(f"Cleaned up {deleted_rows} old records")


class AlertManager:
    """Handles email and Slack notifications"""

    def __init__(self, config: MonitorConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def send_alert(
        self,
        url: str,
        is_failure: bool,
        consecutive_failures: int = 0,
        error_message: str = None,
    ):
        """Send alert via configured channels"""
        if is_failure and not self.config.alert_on_failure:
            return
        if not is_failure and not self.config.alert_on_recovery:
            return

        # Only alert on failures if we've hit the threshold
        if (
            is_failure
            and consecutive_failures < self.config.consecutive_failures_threshold
        ):
            return

        subject, message = self._create_alert_message(
            url, is_failure, consecutive_failures, error_message
        )

        # Send email alert
        if self.config.smtp_server and self.config.alert_recipients:
            await self._send_email_alert(subject, message)

        # Send Slack alert
        if self.config.slack_webhook_url:
            await self._send_slack_alert(message, is_failure)

    def _create_alert_message(
        self, url: str, is_failure: bool, consecutive_failures: int, error_message: str
    ) -> tuple:
        """Create alert message content"""
        if is_failure:
            subject = f"🚨 SITE DOWN: {url}"
            message = f"""
            ALERT: Website is DOWN
            
            URL: {url}
            Status: DOWN
            Consecutive Failures: {consecutive_failures}
            Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            """
            if error_message:
                message += f"Error: {error_message}\n"
        else:
            subject = f"✅ SITE RECOVERED: {url}"
            message = f"""
            RECOVERY: Website is back UP
            
            URL: {url}
            Status: UP
            Timestamp: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
            
            The site has recovered from previous failures.
            """

        return subject, message

    async def _send_email_alert(self, subject: str, message: str):
        """Send email alert"""
        if not EMAIL_AVAILABLE:
            self.logger.warning(
                "Email functionality not available - skipping email alert"
            )
            return

        if not all(
            [
                self.config.smtp_server,
                self.config.smtp_username,
                self.config.smtp_password,
                self.config.alert_recipients,
            ]
        ):
            self.logger.warning("Email configuration incomplete - skipping email alert")
            return

        try:
            # Import email modules only when needed
            from email.mime.text import MimeText
            from email.mime.multipart import MimeMultipart

            msg = MimeMultipart()
            msg["From"] = self.config.smtp_username
            msg["To"] = ", ".join(self.config.alert_recipients)
            msg["Subject"] = subject

            msg.attach(MimeText(message, "plain"))

            # Use asyncio to avoid blocking
            await asyncio.get_event_loop().run_in_executor(
                None, self._send_email_sync, msg
            )

            self.logger.info(f"Email alert sent: {subject}")

        except Exception as e:
            self.logger.error(f"Failed to send email alert: {e}")

    def _send_email_sync(self, msg):
        """Synchronous email sending (run in executor)"""
        if not EMAIL_AVAILABLE:
            return

        try:
            import smtplib

            with smtplib.SMTP(self.config.smtp_server, self.config.smtp_port) as server:
                server.starttls()
                server.login(self.config.smtp_username, self.config.smtp_password)
                server.send_message(msg)
        except Exception as e:
            self.logger.error(f"Error in email sync send: {e}")

    async def _send_slack_alert(self, message: str, is_failure: bool):
        """Send Slack webhook alert"""
        try:
            color = "danger" if is_failure else "good"
            icon = "🚨" if is_failure else "✅"

            payload = {
                "attachments": [
                    {
                        "color": color,
                        "title": f"{icon} Uptime Monitor Alert",
                        "text": message,
                        "ts": int(datetime.now().timestamp()),
                    }
                ]
            }

            # Use aiohttp or requests in executor
            await asyncio.get_event_loop().run_in_executor(
                None, self._send_slack_sync, payload
            )

            self.logger.info("Slack alert sent")

        except Exception as e:
            self.logger.error(f"Failed to send Slack alert: {e}")

    def _send_slack_sync(self, payload):
        """Synchronous Slack webhook sending"""
        import requests

        requests.post(self.config.slack_webhook_url, json=payload, timeout=10)


class UptimeMonitor:
    """Main uptime monitoring class with async scheduling"""

    def __init__(self, config: MonitorConfig):
        self.config = config
        self.db = DatabaseManager(config.db_path)
        self.alert_manager = AlertManager(config)
        self.logger = self._setup_logging()
        self.consecutive_failures = 0
        self.last_status = None
        self.running = False

    def _setup_logging(self) -> logging.Logger:
        """Setup proper logging configuration"""
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)

        # File handler
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "uptime_monitor.log")
        file_handler.setLevel(logging.DEBUG)

        # Formatter
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        # Add handlers if not already added
        if not logger.handlers:
            logger.addHandler(console_handler)
            logger.addHandler(file_handler)

        return logger

    async def ping_url(self) -> Dict[str, Any]:
        """Ping the URL and record the result"""
        timestamp = datetime.now()

        try:
            # Run requests in executor to avoid blocking
            response = await asyncio.get_event_loop().run_in_executor(
                None, lambda: requests.get(self.config.url, timeout=self.config.timeout)
            )

            is_up = response.status_code == 200
            response_time = response.elapsed.total_seconds()
            status_code = response.status_code
            error_message = None

        except requests.exceptions.RequestException as e:
            is_up = False
            response_time = None
            status_code = None
            error_message = str(e)
            self.logger.warning(f"Error pinging {self.config.url}: {e}")

        # Save to database
        self.db.save_check_result(
            self.config.url, is_up, response_time, status_code, error_message
        )

        # Handle alerting logic
        await self._handle_status_change(is_up, error_message)

        # Log result
        status = "UP" if is_up else "DOWN"
        time_str = f" ({response_time:.3f}s)" if response_time else ""
        self.logger.info(f"{self.config.url} - {status}{time_str}")

        return {
            "timestamp": timestamp,
            "is_up": is_up,
            "response_time": response_time,
            "status_code": status_code,
            "error_message": error_message,
        }

    async def _handle_status_change(self, is_up: bool, error_message: str = None):
        """Handle status changes and alerting"""
        if is_up:
            if self.consecutive_failures > 0:
                # Recovery alert
                await self.alert_manager.send_alert(self.config.url, is_failure=False)
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

            # Failure alert
            await self.alert_manager.send_alert(
                self.config.url,
                is_failure=True,
                consecutive_failures=self.consecutive_failures,
                error_message=error_message,
            )

        self.last_status = is_up

    async def generate_daily_report(self, target_date: datetime.date = None):
        """Generate uptime visualization for a specific day"""
        if target_date is None:
            target_date = datetime.now().date()

        day_data = self.db.get_checks_for_date(self.config.url, target_date)

        if not day_data:
            self.logger.warning(f"No data available for {target_date}")
            return

        # Calculate uptime statistics
        total_pings = len(day_data)
        successful_pings = sum(1 for entry in day_data if entry["is_up"])
        uptime_percentage = (
            (successful_pings / total_pings) * 100 if total_pings > 0 else 0
        )

        # Prepare data for visualization
        timestamps = [datetime.fromisoformat(entry["timestamp"]) for entry in day_data]
        statuses = [entry["is_up"] for entry in day_data]
        response_times = [
            entry["response_time"] if entry["response_time"] else 0
            for entry in day_data
        ]

        # Create the visualization
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(15, 10))
        fig.suptitle(
            f"Uptime Report for {self.config.url}\n{target_date}",
            fontsize=16,
            fontweight="bold",
        )

        # Top plot: Uptime status timeline
        ax1.set_title(f"Uptime Status (Overall: {uptime_percentage:.1f}%)", fontsize=14)

        # Create colored bars for uptime status
        for i, (timestamp, is_up) in enumerate(zip(timestamps, statuses)):
            color = "green" if is_up else "red"
            alpha = 0.8 if is_up else 0.9
            ax1.barh(
                0,
                1,
                left=i,
                height=0.5,
                color=color,
                alpha=alpha,
                edgecolor="white",
                linewidth=0.5,
            )

        ax1.set_xlim(0, len(timestamps))
        ax1.set_ylim(-0.5, 0.5)
        ax1.set_ylabel("Status")
        ax1.set_yticks([0])
        ax1.set_yticklabels(["UP/DOWN"])
        ax1.grid(True, alpha=0.3)

        # Set x-axis labels for time
        if len(timestamps) > 0:
            time_labels = []
            time_positions = []
            for i in range(0, len(timestamps), max(1, len(timestamps) // 12)):
                time_labels.append(timestamps[i].strftime("%H:%M"))
                time_positions.append(i)
            ax1.set_xticks(time_positions)
            ax1.set_xticklabels(time_labels, rotation=45)

        # Bottom plot: Response times
        ax2.set_title("Response Times", fontsize=14)

        # Only plot response times for successful pings
        success_times = [timestamps[i] for i, status in enumerate(statuses) if status]
        success_response_times = [
            response_times[i] for i, status in enumerate(statuses) if status
        ]

        if success_response_times:
            ax2.plot(
                success_times,
                success_response_times,
                "b-o",
                markersize=3,
                linewidth=1,
                alpha=0.7,
            )
            ax2.set_ylabel("Response Time (seconds)")
            ax2.grid(True, alpha=0.3)

            # Format x-axis
            ax2.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
            ax2.xaxis.set_major_locator(mdates.HourLocator(interval=2))
            plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45)
        else:
            ax2.text(
                0.5,
                0.5,
                "No successful pings recorded",
                transform=ax2.transAxes,
                ha="center",
                va="center",
                fontsize=12,
            )

        ax2.set_xlabel("Time")

        # Add statistics text box
        stats_text = f"""Statistics for {target_date}:
Total Pings: {total_pings}
Successful: {successful_pings}
Failed: {total_pings - successful_pings}
Uptime: {uptime_percentage:.1f}%"""

        if success_response_times:
            avg_response = np.mean(success_response_times)
            max_response = np.max(success_response_times)
            stats_text += f"""
Avg Response: {avg_response:.3f}s
Max Response: {max_response:.3f}s"""

        plt.figtext(
            0.02,
            0.02,
            stats_text,
            fontsize=10,
            bbox=dict(boxstyle="round,pad=0.5", facecolor="lightgray", alpha=0.8),
        )

        # Save the plot
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        filename = reports_dir / f"uptime_report_{target_date.strftime('%Y-%m-%d')}.png"
        plt.tight_layout()
        plt.savefig(filename, dpi=300, bbox_inches="tight")
        plt.close()  # Close to free memory

        self.logger.info(f"Daily report saved as: {filename}")
        self.logger.info(
            f"Uptime: {uptime_percentage:.1f}% ({successful_pings}/{total_pings} successful pings)"
        )

    async def scheduled_tasks(self):
        """Run scheduled maintenance tasks"""
        try:
            while self.running:
                now = datetime.now()

                # Daily report at midnight
                if now.hour == 0 and now.minute <= 5:
                    yesterday = now.date() - timedelta(days=1)
                    await self.generate_daily_report(yesterday)
                    self.logger.info("Generated daily report for yesterday")

                # Weekly cleanup on Sunday at 2 AM
                if now.weekday() == 6 and now.hour == 2 and now.minute <= 5:
                    self.db.cleanup_old_data(self.config.days_to_keep)
                    self.logger.info("Performed weekly data cleanup")

                # Check every 5 minutes
                await asyncio.sleep(300)
        except asyncio.CancelledError:
            self.logger.info("Scheduled tasks cancelled")
            raise

    async def monitoring_loop(self):
        """Main monitoring loop"""
        self.logger.info(f"Starting uptime monitor for: {self.config.url}")

        try:
            while self.running:
                try:
                    await self.ping_url()
                    await asyncio.sleep(self.config.check_interval)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    self.logger.error(f"Error in monitoring loop: {e}")
                    await asyncio.sleep(60)  # Wait 1 minute before retrying
        except asyncio.CancelledError:
            self.logger.info("Monitoring loop cancelled")
            raise

    async def run_monitor(self):
        """Start the monitoring system with concurrent tasks"""
        self.running = True

        # Create tasks
        monitoring_task = asyncio.create_task(self.monitoring_loop())
        scheduled_task = asyncio.create_task(self.scheduled_tasks())

        try:
            # Run monitoring and scheduled tasks concurrently
            await asyncio.gather(monitoring_task, scheduled_task)
        except KeyboardInterrupt:
            self.logger.info("Keyboard interrupt received")
        except asyncio.CancelledError:
            self.logger.info("Tasks cancelled")
        finally:
            self.running = False

            # Cancel tasks gracefully
            monitoring_task.cancel()
            scheduled_task.cancel()

            # Wait for tasks to finish cancelling
            try:
                await asyncio.gather(
                    monitoring_task, scheduled_task, return_exceptions=True
                )
            except Exception:
                pass  # Ignore exceptions during cleanup

            self.logger.info("Generating final report...")
            try:
                await self.generate_daily_report()
            except Exception as e:
                self.logger.error(f"Error generating final report: {e}")


def load_config_from_file(config_path: str = "monitor_config.yaml") -> MonitorConfig:
    """Load configuration from YAML or JSON file"""

    # Determine file format from extension
    path_obj = Path(config_path)
    is_yaml = path_obj.suffix.lower() in [".yaml", ".yml"]
    is_json = path_obj.suffix.lower() == ".json"

    # Auto-detect format if no extension or unknown extension
    if not (is_yaml or is_json):
        # Try YAML first if available, then JSON
        if YAML_AVAILABLE:
            config_path = str(path_obj.with_suffix(".yaml"))
            is_yaml = True
        else:
            config_path = str(path_obj.with_suffix(".json"))
            is_json = True

    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                if is_yaml and YAML_AVAILABLE:
                    import yaml

                    config_data = yaml.safe_load(f)
                else:
                    config_data = json.load(f)
            return MonitorConfig(**config_data)
        except Exception as e:
            print(f"Error loading config file {config_path}: {e}")
            print("Creating new default configuration...")

    # Create default config file
    default_config = {
        "url": "https://httpbin.org/status/200",
        "check_interval": 300,
        "timeout": 10,
        "db_path": "uptime_monitor.db",
        "days_to_keep": 30,
        "smtp_server": None,
        "smtp_port": 587,
        "smtp_username": None,
        "smtp_password": None,
        "alert_recipients": [],
        "slack_webhook_url": None,
        "alert_on_failure": True,
        "alert_on_recovery": True,
        "consecutive_failures_threshold": 3,
    }

    # Save config in preferred format
    try:
        with open(config_path, "w") as f:
            if is_yaml and YAML_AVAILABLE:
                import yaml

                yaml.dump(default_config, f, default_flow_style=False, indent=2)
                print(f"Created default YAML config file: {config_path}")
            else:
                json.dump(default_config, f, indent=2)
                print(f"Created default JSON config file: {config_path}")

        print("Please edit the configuration and run again.")

    except Exception as e:
        print(f"Error creating config file: {e}")

    return MonitorConfig(**default_config)


async def main():
    """Main entry point with command-line argument handling"""
    import argparse
    from datetime import datetime, timedelta

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
    # Install required packages:
    # pip install requests matplotlib numpy PyYAML

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting...")
    except Exception as e:
        print(f"Fatal error: {e}")
