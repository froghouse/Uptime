import unittest
from unittest.mock import Mock, AsyncMock, patch
import smtplib

from alert_manager import AlertManager
from monitor_config import MonitorConfig


class TestAlertManager(unittest.TestCase):
    """Unit tests for AlertManager class - sync tests only"""

    def setUp(self):
        """Set up test environment for each test"""
        # Create test configuration with email settings
        self.test_config_email = MonitorConfig(
            url="https://example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            smtp_username="test@example.com",
            smtp_password="testpass",
            alert_recipients=["admin@example.com", "dev@example.com"],
            alert_on_failure=True,
            alert_on_recovery=True,
            consecutive_failures_threshold=2,
        )

        # Create test configuration with Slack settings
        self.test_config_slack = MonitorConfig(
            url="https://example.com",
            slack_webhook_url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            alert_on_failure=True,
            alert_on_recovery=True,
            consecutive_failures_threshold=2,
        )

        # Create test configuration with both email and Slack
        self.test_config_both = MonitorConfig(
            url="https://example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            smtp_username="test@example.com",
            smtp_password="testpass",
            alert_recipients=["admin@example.com"],
            slack_webhook_url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            alert_on_failure=True,
            alert_on_recovery=True,
            consecutive_failures_threshold=2,
        )

        # Create test configuration with minimal settings
        self.test_config_minimal = MonitorConfig(
            url="https://example.com",
            alert_on_failure=False,
            alert_on_recovery=False,
            consecutive_failures_threshold=5,
        )

        # Create AlertManager instances
        self.alert_manager_email = AlertManager(self.test_config_email)
        self.alert_manager_slack = AlertManager(self.test_config_slack)
        self.alert_manager_both = AlertManager(self.test_config_both)
        self.alert_manager_minimal = AlertManager(self.test_config_minimal)

    def test_init_creates_proper_instances(self):
        """Test that AlertManager initialization creates proper instances"""
        self.assertEqual(self.alert_manager_email.config, self.test_config_email)
        self.assertIsNotNone(self.alert_manager_email.logger)
        self.assertEqual(self.alert_manager_email.logger.name, "alert_manager")

    def test_init_with_different_configs(self):
        """Test initialization with different configuration types"""
        # Test email config
        self.assertEqual(self.alert_manager_email.config.smtp_server, "smtp.example.com")
        self.assertEqual(len(self.alert_manager_email.config.alert_recipients), 2)

        # Test Slack config
        self.assertIn("slack.com", self.alert_manager_slack.config.slack_webhook_url)

        # Test minimal config
        self.assertFalse(self.alert_manager_minimal.config.alert_on_failure)
        self.assertFalse(self.alert_manager_minimal.config.alert_on_recovery)

    def test_create_alert_message_failure(self):
        """Test creating alert message for failure"""
        url = "https://test.com"
        consecutive_failures = 3
        error_message = "Connection timeout"

        with patch("alert_manager.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2025-07-02 10:00:00"

            subject, message = self.alert_manager_email._create_alert_message(
                url, True, consecutive_failures, error_message
            )

        # Verify subject
        self.assertEqual(subject, "🚨 SITE DOWN: https://test.com")

        # Verify message content
        self.assertIn("ALERT: Website is DOWN", message)
        self.assertIn("https://test.com", message)
        self.assertIn("Status: DOWN", message)
        self.assertIn("Consecutive Failures: 3", message)
        self.assertIn("2025-07-02 10:00:00", message)
        self.assertIn("Error: Connection timeout", message)

    def test_create_alert_message_failure_no_error(self):
        """Test creating alert message for failure without error message"""
        url = "https://test.com"
        consecutive_failures = 1

        with patch("alert_manager.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2025-07-02 10:00:00"

            subject, message = self.alert_manager_email._create_alert_message(
                url, True, consecutive_failures, None
            )

        # Verify subject
        self.assertEqual(subject, "🚨 SITE DOWN: https://test.com")

        # Verify message content (should not contain error line)
        self.assertIn("ALERT: Website is DOWN", message)
        self.assertNotIn("Error:", message)

    def test_create_alert_message_recovery(self):
        """Test creating alert message for recovery"""
        url = "https://test.com"

        with patch("alert_manager.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2025-07-02 10:00:00"

            subject, message = self.alert_manager_email._create_alert_message(
                url, False, 0, None
            )

        # Verify subject
        self.assertEqual(subject, "✅ SITE RECOVERED: https://test.com")

        # Verify message content
        self.assertIn("RECOVERY: Website is back UP", message)
        self.assertIn("https://test.com", message)
        self.assertIn("Status: UP", message)
        self.assertIn("2025-07-02 10:00:00", message)
        self.assertIn("The site has recovered from previous failures", message)


class TestAlertManagerAsync(unittest.IsolatedAsyncioTestCase):
    """Unit tests for AlertManager class - async tests"""

    async def asyncSetUp(self):
        """Set up test environment for each async test"""
        # Create test configurations
        self.test_config_email = MonitorConfig(
            url="https://example.com",
            smtp_server="smtp.example.com",
            smtp_port=587,
            smtp_username="test@example.com",
            smtp_password="testpass",
            alert_recipients=["admin@example.com", "dev@example.com"],
            alert_on_failure=True,
            alert_on_recovery=True,
            consecutive_failures_threshold=2,
        )

        self.test_config_slack = MonitorConfig(
            url="https://example.com",
            slack_webhook_url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            alert_on_failure=True,
            alert_on_recovery=True,
            consecutive_failures_threshold=2,
        )

        self.test_config_disabled = MonitorConfig(
            url="https://example.com",
            alert_on_failure=False,
            alert_on_recovery=False,
            consecutive_failures_threshold=3,
        )

        # Create AlertManager instances
        self.alert_manager_email = AlertManager(self.test_config_email)
        self.alert_manager_slack = AlertManager(self.test_config_slack)
        self.alert_manager_disabled = AlertManager(self.test_config_disabled)

    async def test_send_alert_failure_below_threshold(self):
        """Test that failure alerts are not sent below threshold"""
        # Mock the alert sending methods
        self.alert_manager_email._send_email_alert = AsyncMock()
        self.alert_manager_email._send_slack_alert = AsyncMock()

        # Send alert with consecutive failures below threshold
        await self.alert_manager_email.send_alert(
            "https://test.com", is_failure=True, consecutive_failures=1
        )

        # No alerts should be sent
        self.alert_manager_email._send_email_alert.assert_not_called()
        self.alert_manager_email._send_slack_alert.assert_not_called()

    async def test_send_alert_failure_at_threshold(self):
        """Test that failure alerts are sent at threshold"""
        # Mock the alert sending methods
        self.alert_manager_email._send_email_alert = AsyncMock()

        # Send alert with consecutive failures at threshold
        await self.alert_manager_email.send_alert(
            "https://test.com", is_failure=True, consecutive_failures=2, error_message="Timeout"
        )

        # Email alert should be sent
        self.alert_manager_email._send_email_alert.assert_called_once()
        call_args = self.alert_manager_email._send_email_alert.call_args[0]
        self.assertIn("SITE DOWN", call_args[0])  # subject
        self.assertIn("ALERT: Website is DOWN", call_args[1])  # message

    async def test_send_alert_recovery(self):
        """Test recovery alert sending"""
        # Mock the alert sending methods
        self.alert_manager_email._send_email_alert = AsyncMock()

        # Send recovery alert
        await self.alert_manager_email.send_alert(
            "https://test.com", is_failure=False
        )

        # Email alert should be sent
        self.alert_manager_email._send_email_alert.assert_called_once()
        call_args = self.alert_manager_email._send_email_alert.call_args[0]
        self.assertIn("SITE RECOVERED", call_args[0])  # subject
        self.assertIn("RECOVERY: Website is back UP", call_args[1])  # message

    async def test_send_alert_disabled_failure(self):
        """Test that disabled failure alerts are not sent"""
        # Mock the alert sending methods
        self.alert_manager_disabled._send_email_alert = AsyncMock()

        # Send failure alert with disabled config
        await self.alert_manager_disabled.send_alert(
            "https://test.com", is_failure=True, consecutive_failures=5
        )

        # No alerts should be sent
        self.alert_manager_disabled._send_email_alert.assert_not_called()

    async def test_send_alert_disabled_recovery(self):
        """Test that disabled recovery alerts are not sent"""
        # Mock the alert sending methods
        self.alert_manager_disabled._send_email_alert = AsyncMock()

        # Send recovery alert with disabled config
        await self.alert_manager_disabled.send_alert(
            "https://test.com", is_failure=False
        )

        # No alerts should be sent
        self.alert_manager_disabled._send_email_alert.assert_not_called()

    async def test_send_alert_both_channels(self):
        """Test sending alerts to both email and Slack"""
        # Create config with both channels
        config_both = MonitorConfig(
            url="https://example.com",
            smtp_server="smtp.example.com",
            smtp_username="test@example.com",
            smtp_password="testpass",
            alert_recipients=["admin@example.com"],
            slack_webhook_url="https://hooks.slack.com/services/TEST/WEBHOOK/URL",
            consecutive_failures_threshold=1,
        )
        alert_manager = AlertManager(config_both)

        # Mock both alert methods
        alert_manager._send_email_alert = AsyncMock()
        alert_manager._send_slack_alert = AsyncMock()

        # Send failure alert
        await alert_manager.send_alert(
            "https://test.com", is_failure=True, consecutive_failures=1
        )

        # Both alerts should be sent
        alert_manager._send_email_alert.assert_called_once()
        alert_manager._send_slack_alert.assert_called_once()

    @patch("alert_manager.EMAIL_AVAILABLE", True)
    async def test_send_email_alert_success(self):
        """Test successful email alert sending"""
        # Mock the email sending sync method
        with patch.object(self.alert_manager_email, "_send_email_sync"):
            # Test email sending
            await self.alert_manager_email._send_email_alert(
                "Test Subject", "Test Message"
            )

        # Test passes if no exception is raised and sync method is accessible

    @patch("alert_manager.EMAIL_AVAILABLE", False)
    async def test_send_email_alert_not_available(self):
        """Test email alert when email functionality is not available"""
        # Should complete without error and log warning
        await self.alert_manager_email._send_email_alert(
            "Test Subject", "Test Message"
        )
        # Test passes if no exception is raised

    async def test_send_email_alert_incomplete_config(self):
        """Test email alert with incomplete configuration"""
        # Create config with missing email settings
        incomplete_config = MonitorConfig(
            url="https://example.com",
            smtp_server="smtp.example.com",
            # Missing smtp_username, smtp_password, alert_recipients
        )
        alert_manager = AlertManager(incomplete_config)

        # Should complete without error and log warning
        await alert_manager._send_email_alert("Test Subject", "Test Message")
        # Test passes if no exception is raised

    @patch("alert_manager.EMAIL_AVAILABLE", True)
    @patch("asyncio.get_event_loop")
    async def test_send_email_alert_exception(self, mock_get_loop):
        """Test email alert handling exceptions"""
        # Mock the event loop to raise exception
        mock_loop = AsyncMock()
        mock_get_loop.return_value = mock_loop
        mock_loop.run_in_executor.side_effect = Exception("SMTP error")

        # Should handle exception gracefully
        await self.alert_manager_email._send_email_alert(
            "Test Subject", "Test Message"
        )
        # Test passes if no exception is raised

    def test_send_email_sync_success(self):
        """Test synchronous email sending"""
        # Create mock message
        mock_msg = Mock()

        # Mock SMTP server
        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_server = Mock()
            mock_smtp_class.return_value.__enter__.return_value = mock_server

            # Test email sending
            self.alert_manager_email._send_email_sync(mock_msg)

            # Verify SMTP operations
            mock_smtp_class.assert_called_once_with("smtp.example.com", 587)
            mock_server.starttls.assert_called_once()
            mock_server.login.assert_called_once_with("test@example.com", "testpass")
            mock_server.send_message.assert_called_once_with(mock_msg)

    @patch("alert_manager.EMAIL_AVAILABLE", False)
    def test_send_email_sync_not_available(self):
        """Test sync email sending when not available"""
        mock_msg = Mock()
        # Should return early without error
        self.alert_manager_email._send_email_sync(mock_msg)

    def test_send_email_sync_exception(self):
        """Test sync email sending with SMTP exception"""
        mock_msg = Mock()

        # Mock SMTP to raise exception
        with patch("smtplib.SMTP") as mock_smtp_class:
            mock_smtp_class.side_effect = smtplib.SMTPException("SMTP error")

            # Should handle exception gracefully
            self.alert_manager_email._send_email_sync(mock_msg)
            # Test passes if no exception is raised

    @patch("asyncio.get_event_loop")
    async def test_send_slack_alert_failure(self, mock_get_loop):
        """Test Slack alert for failure"""
        # Mock the event loop and executor
        mock_loop = AsyncMock()
        mock_get_loop.return_value = mock_loop
        mock_loop.run_in_executor = AsyncMock()

        # Test Slack alert sending
        await self.alert_manager_slack._send_slack_alert(
            "Test failure message", is_failure=True
        )

        # Verify executor was called
        mock_loop.run_in_executor.assert_called_once()
        call_args = mock_loop.run_in_executor.call_args
        self.assertIsNone(call_args[0][0])  # executor should be None
        self.assertEqual(call_args[0][1], self.alert_manager_slack._send_slack_sync)

        # Verify payload structure
        payload = call_args[0][2]  # payload argument
        self.assertIn("attachments", payload)
        attachment = payload["attachments"][0]
        self.assertEqual(attachment["color"], "danger")
        self.assertIn("🚨", attachment["title"])
        self.assertEqual(attachment["text"], "Test failure message")

    @patch("asyncio.get_event_loop")
    async def test_send_slack_alert_recovery(self, mock_get_loop):
        """Test Slack alert for recovery"""
        # Mock the event loop and executor
        mock_loop = AsyncMock()
        mock_get_loop.return_value = mock_loop
        mock_loop.run_in_executor = AsyncMock()

        # Test Slack alert sending
        await self.alert_manager_slack._send_slack_alert(
            "Test recovery message", is_failure=False
        )

        # Verify executor was called
        mock_loop.run_in_executor.assert_called_once()
        call_args = mock_loop.run_in_executor.call_args

        # Verify payload structure
        payload = call_args[0][2]  # payload argument
        attachment = payload["attachments"][0]
        self.assertEqual(attachment["color"], "good")
        self.assertIn("✅", attachment["title"])
        self.assertEqual(attachment["text"], "Test recovery message")

    @patch("asyncio.get_event_loop")
    async def test_send_slack_alert_exception(self, mock_get_loop):
        """Test Slack alert handling exceptions"""
        # Mock the event loop to raise exception
        mock_loop = AsyncMock()
        mock_get_loop.return_value = mock_loop
        mock_loop.run_in_executor.side_effect = Exception("Network error")

        # Should handle exception gracefully
        await self.alert_manager_slack._send_slack_alert(
            "Test message", is_failure=True
        )
        # Test passes if no exception is raised

    def test_send_slack_sync_success(self):
        """Test synchronous Slack webhook sending"""
        payload = {"test": "data"}

        # Mock requests.post
        with patch("requests.post") as mock_post:
            mock_post.return_value.status_code = 200

            # Test Slack sending
            self.alert_manager_slack._send_slack_sync(payload)

            # Verify request was made
            mock_post.assert_called_once_with(
                "https://hooks.slack.com/services/TEST/WEBHOOK/URL",
                json=payload,
                timeout=10
            )

    def test_send_slack_sync_exception(self):
        """Test sync Slack sending with network exception"""
        payload = {"test": "data"}

        # Mock requests.post to raise exception
        with patch("requests.post") as mock_post:
            mock_post.side_effect = Exception("Network error")

            # Should handle exception gracefully (raised by the method)
            with self.assertRaises(Exception):
                self.alert_manager_slack._send_slack_sync(payload)

    async def test_message_creation_with_mocked_datetime(self):
        """Test message creation with controlled datetime"""
        url = "https://test.example.com"

        # Mock datetime to return predictable timestamp
        with patch("alert_manager.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "2025-07-02 15:30:45"
            mock_datetime.now.return_value.timestamp.return_value = 1719934245

            # Test failure message
            subject, message = self.alert_manager_email._create_alert_message(
                url, True, 3, "DNS resolution failed"
            )

            self.assertEqual(subject, f"🚨 SITE DOWN: {url}")
            self.assertIn("Consecutive Failures: 3", message)
            self.assertIn("Error: DNS resolution failed", message)
            self.assertIn("2025-07-02 15:30:45", message)

            # Test recovery message
            subject, message = self.alert_manager_email._create_alert_message(
                url, False, 0, None
            )

            self.assertEqual(subject, f"✅ SITE RECOVERED: {url}")
            self.assertIn("Website is back UP", message)
            self.assertIn("2025-07-02 15:30:45", message)

    async def test_integration_alert_flow(self):
        """Test integration of alert flow from send_alert to message creation"""
        # Mock both email and Slack sending methods
        self.alert_manager_email._send_email_alert = AsyncMock()
        
        # Test failure alert
        await self.alert_manager_email.send_alert(
            "https://integration.test", 
            is_failure=True, 
            consecutive_failures=2,
            error_message="Integration test error"
        )

        # Verify email alert was called
        self.alert_manager_email._send_email_alert.assert_called_once()
        call_args = self.alert_manager_email._send_email_alert.call_args[0]
        
        # Verify subject and message content
        subject, message = call_args[0], call_args[1]
        self.assertIn("SITE DOWN", subject)
        self.assertIn("https://integration.test", subject)
        self.assertIn("ALERT: Website is DOWN", message)
        self.assertIn("Integration test error", message)


if __name__ == "__main__":
    unittest.main(verbosity=2)