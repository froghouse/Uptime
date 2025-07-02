import unittest
import asyncio
import tempfile
import os
import shutil
from datetime import datetime, date
from unittest.mock import Mock, AsyncMock, patch, call
from pathlib import Path

from uptime_monitor import UptimeMonitor
from monitor_config import MonitorConfig
from database_manager import DatabaseManager
from alert_manager import AlertManager


class TestUptimeMonitor(unittest.TestCase):
    """Unit tests for UptimeMonitor class - sync tests only"""

    def setUp(self):
        """Set up test environment for each test"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_uptime.db")

        # Create test configuration
        self.test_config = MonitorConfig(
            url="https://example.com",
            check_interval=60,
            timeout=5,
            db_path=self.test_db_path,
            days_to_keep=7,
            alert_on_failure=True,
            alert_on_recovery=True,
            consecutive_failures_threshold=2,
        )

        # Create monitor instance
        self.monitor = UptimeMonitor(self.test_config)

    def tearDown(self):
        """Clean up test environment after each test"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    def test_init_creates_proper_instances(self):
        """Test that UptimeMonitor initialization creates proper component instances"""
        self.assertEqual(self.monitor.config, self.test_config)
        self.assertIsInstance(self.monitor.db, DatabaseManager)
        self.assertIsInstance(self.monitor.alert_manager, AlertManager)
        self.assertEqual(self.monitor.consecutive_failures, 0)
        self.assertIsNone(self.monitor.last_status)
        self.assertFalse(self.monitor.running)
        self.assertIsNotNone(self.monitor.logger)

    def test_init_with_different_config(self):
        """Test initialization with different configuration parameters"""
        custom_config = MonitorConfig(
            url="https://custom.com",
            check_interval=120,
            timeout=10,
            consecutive_failures_threshold=5,
        )

        custom_monitor = UptimeMonitor(custom_config)

        self.assertEqual(custom_monitor.config.url, "https://custom.com")
        self.assertEqual(custom_monitor.config.check_interval, 120)
        self.assertEqual(custom_monitor.config.timeout, 10)
        self.assertEqual(custom_monitor.config.consecutive_failures_threshold, 5)

    def test_monitor_attributes_after_init(self):
        """Test that monitor has correct attributes after initialization"""
        # Test config reference
        self.assertIs(self.monitor.config, self.test_config)

        # Test component initialization
        self.assertIsInstance(self.monitor.db, DatabaseManager)
        self.assertEqual(self.monitor.db.db_path, self.test_db_path)

        self.assertIsInstance(self.monitor.alert_manager, AlertManager)
        self.assertIs(self.monitor.alert_manager.config, self.test_config)

        # Test initial state
        self.assertEqual(self.monitor.consecutive_failures, 0)
        self.assertIsNone(self.monitor.last_status)
        self.assertFalse(self.monitor.running)

        # Test logger
        self.assertIsNotNone(self.monitor.logger)
        self.assertEqual(self.monitor.logger.name, "uptime_monitor")


class TestUptimeMonitorAsync(unittest.IsolatedAsyncioTestCase):
    """Unit tests for UptimeMonitor class - async tests"""

    async def asyncSetUp(self):
        """Set up test environment for each async test"""
        # Create temporary directory for test files
        self.temp_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.temp_dir, "test_uptime.db")

        # Create test configuration
        self.test_config = MonitorConfig(
            url="https://example.com",
            check_interval=60,
            timeout=5,
            db_path=self.test_db_path,
            days_to_keep=7,
            alert_on_failure=True,
            alert_on_recovery=True,
            consecutive_failures_threshold=2,
        )

        # Create monitor instance
        self.monitor = UptimeMonitor(self.test_config)

    async def asyncTearDown(self):
        """Clean up test environment after each async test"""
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)

    @patch("requests.get")
    @patch.object(DatabaseManager, "save_check_result")
    async def test_ping_url_success(self, mock_save, mock_get):
        """Test successful URL ping"""
        # Mock successful response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.elapsed.total_seconds.return_value = 0.5
        mock_get.return_value = mock_response

        # Mock alert manager
        self.monitor.alert_manager.send_alert = AsyncMock()

        result = await self.monitor.ping_url()

        # Verify response structure
        self.assertIsInstance(result, dict)
        self.assertIn("timestamp", result)
        self.assertIn("is_up", result)
        self.assertIn("response_time", result)
        self.assertIn("status_code", result)
        self.assertIn("error_message", result)

        # Verify response values
        self.assertTrue(result["is_up"])
        self.assertEqual(result["response_time"], 0.5)
        self.assertEqual(result["status_code"], 200)
        self.assertIsNone(result["error_message"])

        # Verify database save was called
        mock_save.assert_called_once_with(self.test_config.url, True, 0.5, 200, None)

        # Verify requests.get was called correctly
        mock_get.assert_called_once_with(
            self.test_config.url, timeout=self.test_config.timeout
        )

    @patch("requests.get")
    @patch.object(DatabaseManager, "save_check_result")
    async def test_ping_url_failure_connection_error(self, mock_save, mock_get):
        """Test URL ping with connection error"""
        import requests

        # Mock connection error
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection failed")

        # Mock alert manager
        self.monitor.alert_manager.send_alert = AsyncMock()

        result = await self.monitor.ping_url()

        # Verify failure response
        self.assertFalse(result["is_up"])
        self.assertIsNone(result["response_time"])
        self.assertIsNone(result["status_code"])
        self.assertEqual(result["error_message"], "Connection failed")

        # Verify database save was called with failure data
        mock_save.assert_called_once_with(
            self.test_config.url, False, None, None, "Connection failed"
        )

    @patch("requests.get")
    @patch.object(DatabaseManager, "save_check_result")
    async def test_ping_url_failure_timeout(self, mock_save, mock_get):
        """Test URL ping with timeout error"""
        import requests

        # Mock timeout error
        mock_get.side_effect = requests.exceptions.Timeout("Request timed out")

        # Mock alert manager
        self.monitor.alert_manager.send_alert = AsyncMock()

        result = await self.monitor.ping_url()

        # Verify failure response
        self.assertFalse(result["is_up"])
        self.assertIsNone(result["response_time"])
        self.assertIsNone(result["status_code"])
        self.assertEqual(result["error_message"], "Request timed out")

    @patch("requests.get")
    @patch.object(DatabaseManager, "save_check_result")
    async def test_ping_url_non_200_status(self, mock_save, mock_get):
        """Test URL ping with non-200 status code"""
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.elapsed.total_seconds.return_value = 0.3
        mock_get.return_value = mock_response

        # Mock alert manager
        self.monitor.alert_manager.send_alert = AsyncMock()

        result = await self.monitor.ping_url()

        # Verify failure response (only 200 is considered success)
        self.assertFalse(result["is_up"])
        self.assertEqual(result["response_time"], 0.3)
        self.assertEqual(result["status_code"], 404)
        self.assertIsNone(result["error_message"])

        # Verify database save was called
        mock_save.assert_called_once_with(self.test_config.url, False, 0.3, 404, None)

    async def test_handle_status_change_first_failure(self):
        """Test handling first failure"""
        self.monitor.alert_manager.send_alert = AsyncMock()

        await self.monitor._handle_status_change(False, "Test error")

        # Verify consecutive failures incremented
        self.assertEqual(self.monitor.consecutive_failures, 1)
        self.assertFalse(self.monitor.last_status)

        # Alert should be sent
        self.monitor.alert_manager.send_alert.assert_called_once_with(
            self.test_config.url,
            is_failure=True,
            consecutive_failures=1,
            error_message="Test error",
        )

    async def test_handle_status_change_multiple_failures(self):
        """Test handling multiple consecutive failures"""
        self.monitor.alert_manager.send_alert = AsyncMock()

        # Simulate multiple failures
        await self.monitor._handle_status_change(False, "Error 1")
        await self.monitor._handle_status_change(False, "Error 2")
        await self.monitor._handle_status_change(False, "Error 3")

        # Verify consecutive failures count
        self.assertEqual(self.monitor.consecutive_failures, 3)

        # Verify all alerts were sent
        self.assertEqual(self.monitor.alert_manager.send_alert.call_count, 3)

    async def test_handle_status_change_recovery(self):
        """Test handling recovery from failures"""
        self.monitor.alert_manager.send_alert = AsyncMock()

        # Set up previous failures
        self.monitor.consecutive_failures = 3

        # Recovery
        await self.monitor._handle_status_change(True)

        # Verify consecutive failures reset
        self.assertEqual(self.monitor.consecutive_failures, 0)
        self.assertTrue(self.monitor.last_status)

        # Recovery alert should be sent
        self.monitor.alert_manager.send_alert.assert_called_once_with(
            self.test_config.url, is_failure=False
        )

    async def test_handle_status_change_recovery_from_zero_failures(self):
        """Test handling success when there were no previous failures"""
        self.monitor.alert_manager.send_alert = AsyncMock()

        # Success with no previous failures
        await self.monitor._handle_status_change(True)

        # Verify state
        self.assertEqual(self.monitor.consecutive_failures, 0)
        self.assertTrue(self.monitor.last_status)

        # No alert should be sent (no recovery to report)
        self.monitor.alert_manager.send_alert.assert_not_called()

    @patch.object(DatabaseManager, "get_checks_for_date")
    @patch("matplotlib.pyplot.savefig")
    @patch("matplotlib.pyplot.close")
    @patch("matplotlib.pyplot.tight_layout")
    async def test_generate_daily_report_with_data(
        self, mock_tight_layout, mock_close, mock_savefig, mock_get_checks
    ):
        """Test generating daily report with available data"""
        # Mock data from database
        test_data = [
            {
                "timestamp": "2025-01-01T10:00:00",
                "is_up": True,
                "response_time": 0.5,
                "status_code": 200,
            },
            {
                "timestamp": "2025-01-01T10:05:00",
                "is_up": False,
                "response_time": None,
                "status_code": None,
            },
            {
                "timestamp": "2025-01-01T10:10:00",
                "is_up": True,
                "response_time": 0.3,
                "status_code": 200,
            },
        ]
        mock_get_checks.return_value = test_data

        # Create reports directory
        reports_dir = Path(self.temp_dir) / "reports"
        reports_dir.mkdir(exist_ok=True)

        with patch("uptime_monitor.Path") as mock_path:
            mock_path.return_value = reports_dir

            test_date = date(2025, 1, 1)
            await self.monitor.generate_daily_report(test_date)

        # Verify database query was called
        mock_get_checks.assert_called_once_with(self.test_config.url, test_date)

        # Verify matplotlib functions were called
        mock_tight_layout.assert_called_once()
        mock_close.assert_called_once()

    @patch.object(DatabaseManager, "get_checks_for_date")
    async def test_generate_daily_report_no_data(self, mock_get_checks):
        """Test generating daily report with no available data"""
        # Mock empty data from database
        mock_get_checks.return_value = []

        test_date = date(2025, 1, 1)
        await self.monitor.generate_daily_report(test_date)

        # Verify database query was called
        mock_get_checks.assert_called_once_with(self.test_config.url, test_date)

        # Function should return early with no data warning

    @patch.object(DatabaseManager, "get_checks_for_date")
    async def test_generate_daily_report_default_date(self, mock_get_checks):
        """Test generating daily report with default date (today)"""
        mock_get_checks.return_value = []

        await self.monitor.generate_daily_report()

        # Should use today's date
        today = datetime.now().date()
        mock_get_checks.assert_called_once_with(self.test_config.url, today)

    @patch("asyncio.sleep")
    async def test_monitoring_loop_success(self, mock_sleep):
        """Test successful monitoring loop iteration"""
        self.monitor.running = True
        self.monitor.ping_url = AsyncMock()

        # Make sleep cancel after first ping
        mock_sleep.side_effect = [asyncio.CancelledError()]

        with self.assertRaises(asyncio.CancelledError):
            await self.monitor.monitoring_loop()

        # Verify ping was called
        self.monitor.ping_url.assert_called_once()
        mock_sleep.assert_called_once_with(self.test_config.check_interval)

    @patch("asyncio.sleep")
    async def test_monitoring_loop_ping_error_recovery(self, mock_sleep):
        """Test monitoring loop recovery from ping errors"""
        self.monitor.running = True

        # Create a counter to track calls
        ping_call_count = 0

        async def mock_ping():
            nonlocal ping_call_count
            ping_call_count += 1
            if ping_call_count == 1:
                raise Exception("Network error")
            elif ping_call_count == 2:
                return {"is_up": True}  # Success
            else:
                raise asyncio.CancelledError()

        self.monitor.ping_url = mock_ping

        # Sleep calls: check_interval, 60s recovery, check_interval, then cancel
        mock_sleep.side_effect = [
            None,  # After first failed ping
            None,  # Recovery sleep (60s)
            None,  # After successful ping
            asyncio.CancelledError(),  # Cancel loop
        ]

        with self.assertRaises(asyncio.CancelledError):
            await self.monitor.monitoring_loop()

        # Verify ping was called multiple times
        self.assertEqual(ping_call_count, 3)

        # Verify sleep calls: first with check_interval, then 60s recovery
        # Check that we have at least the expected calls (might have more due to cancellation timing)
        actual_calls = mock_sleep.call_args_list
        self.assertGreaterEqual(len(actual_calls), 2)  # At least 2 calls
        # Check specific call patterns
        self.assertEqual(actual_calls[0], call(self.test_config.check_interval))
        self.assertEqual(actual_calls[1], call(60))

    @patch("asyncio.sleep")
    async def test_monitoring_loop_cancellation(self, mock_sleep):
        """Test monitoring loop proper cancellation handling"""
        self.monitor.running = True
        self.monitor.ping_url = AsyncMock(side_effect=asyncio.CancelledError())

        # Should raise CancelledError and not suppress it
        with self.assertRaises(asyncio.CancelledError):
            await self.monitor.monitoring_loop()

    async def test_run_monitor_successful_execution(self):
        """Test successful monitor execution - simplified version"""
        # Mock the loop methods to avoid complex task mocking
        self.monitor.monitoring_loop = AsyncMock()
        self.monitor.scheduled_tasks = AsyncMock()
        self.monitor.generate_daily_report = AsyncMock()

        # Run the monitor
        await self.monitor.run_monitor()

        # Verify running was set to False at the end
        self.assertFalse(self.monitor.running)

        # Verify final report generation
        self.monitor.generate_daily_report.assert_called_once()

    async def test_run_monitor_task_cleanup(self):
        """Test monitor task cleanup and final report"""
        # Mock the loop methods to return normally
        self.monitor.monitoring_loop = AsyncMock()
        self.monitor.scheduled_tasks = AsyncMock()
        self.monitor.generate_daily_report = AsyncMock()

        # Run the monitor
        await self.monitor.run_monitor()

        # Verify running was set to False at the end
        self.assertFalse(self.monitor.running)

        # Verify final report generation
        self.monitor.generate_daily_report.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)