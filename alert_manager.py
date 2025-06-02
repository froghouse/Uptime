from __future__ import annotations
import asyncio
import importlib.util
import logging
from datetime import datetime

from monitor_config import MonitorConfig

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


class AlertManager:
    """Handles email and Slack notifications"""

    def __init__(self, config: MonitorConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(__name__)

    async def send_alert(
        self,
        url: str,
        is_failure: bool,
        consecutive_failures: int = 0,
        error_message: str = None,
    ) -> None:
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
    ) -> tuple[str, str]:
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

    async def _send_email_alert(self, subject: str, message: str) -> None:
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

    def _send_email_sync(self, msg) -> None:
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

    async def _send_slack_alert(self, message: str, is_failure: bool) -> None:
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

    def _send_slack_sync(self, payload) -> None:
        """Synchronous Slack webhook sending"""
        import requests

        requests.post(self.config.slack_webhook_url, json=payload, timeout=10)
