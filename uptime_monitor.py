from datetime import datetime, timedelta
import asyncio
import logging
from pathlib import Path
import requests
from typing import Dict, Any
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np

from monitor_config import MonitorConfig
from database_manager import DatabaseManager
from alert_manager import AlertManager


class UptimeMonitor:
    """Main uptime monitoring class with async scheduling"""

    def __init__(self, config: MonitorConfig) -> None:
        """Initialize the monitor with configuration and setup"""
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

    async def _handle_status_change(
        self, is_up: bool, error_message: str = None
    ) -> None:
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

    async def generate_daily_report(self, target_date: datetime.date = None) -> None:
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

    async def scheduled_tasks(self) -> None:
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

    async def monitoring_loop(self) -> None:
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

    async def run_monitor(self) -> None:
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
