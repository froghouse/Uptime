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
    """Unit tests for UptimeMonitor class"""

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
    async def test_scheduled_tasks_daily_report(self, mock_sleep):
        """Test scheduled tasks daily report generation"""
        self.monitor.running = True

        # Mock generate_daily_report and database cleanup
        self.monitor.generate_daily_report = AsyncMock()
        self.monitor.db.cleanup_old_data = Mock()

        # Mock datetime to simulate midnight
        with patch("uptime_monitor.datetime") as mock_datetime:
            mock_now = Mock()
            mock_now.hour = 0
            mock_now.minute = 3
            mock_now.date.return_value = date(2025, 1, 2)
            mock_now.weekday.return_value = 1  # Tuesday
            mock_datetime.now.return_value = mock_now

            # Make sleep cancel the task after first iteration
            mock_sleep.side_effect = [asyncio.CancelledError()]

            with self.assertRaises(asyncio.CancelledError):
                await self.monitor.scheduled_tasks()

        # Verify daily report was generated for yesterday
        yesterday = date(2025, 1, 1)  # mock_now.date() - 1 day
        self.monitor.generate_daily_report.assert_called_once_with(yesterday)

    @patch("asyncio.sleep")
    async def test_scheduled_tasks_weekly_cleanup(self, mock_sleep):
        """Test scheduled tasks weekly cleanup"""
        self.monitor.running = True

        # Mock generate_daily_report and database cleanup
        self.monitor.generate_daily_report = AsyncMock()
        self.monitor.db.cleanup_old_data = Mock()

        # Mock datetime to simulate Sunday at 2 AM
        with patch("uptime_monitor.datetime") as mock_datetime:
            mock_now = Mock()
            mock_now.hour = 2
            mock_now.minute = 3
            mock_now.weekday.return_value = 6  # Sunday
            mock_datetime.now.return_value = mock_now

            # Make sleep cancel the task after first iteration
            mock_sleep.side_effect = [asyncio.CancelledError()]

            with self.assertRaises(asyncio.CancelledError):
                await self.monitor.scheduled_tasks()

        # Verify cleanup was called
        self.monitor.db.cleanup_old_data.assert_called_once_with(
            self.test_config.days_to_keep
        )

    @patch("asyncio.sleep")
    async def test_scheduled_tasks_cancellation(self, mock_sleep):
        """Test scheduled tasks proper cancellation handling"""
        self.monitor.running = True

        # Mock sleep to raise CancelledError
        mock_sleep.side_effect = asyncio.CancelledError()

        # Should raise CancelledError and not suppress it
        with self.assertRaises(asyncio.CancelledError):
            await self.monitor.scheduled_tasks()

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

        # First ping fails, second succeeds, then cancel
        self.monitor.ping_url = AsyncMock(
            side_effect=[
                Exception("Network error"),
                None,  # Success
                asyncio.CancelledError(),
            ]
        )

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
        self.assertEqual(self.monitor.ping_url.call_count, 3)

        # Verify sleep calls: first with check_interval, then 60s recovery, then check_interval
        expected_calls = [
            call(self.test_config.check_interval),
            call(60),  # Recovery sleep
            call(self.test_config.check_interval),
        ]
        mock_sleep.assert_has_calls(expected_calls)

    @patch("asyncio.sleep")
    async def test_monitoring_loop_cancellation(self, mock_sleep):
        """Test monitoring loop proper cancellation handling"""
        self.monitor.running = True
        self.monitor.ping_url = AsyncMock(side_effect=asyncio.CancelledError())

        # Should raise CancelledError and not suppress it
        with self.assertRaises(asyncio.CancelledError):
            await self.monitor.monitoring_loop()

    @patch("asyncio.create_task")
    @patch("asyncio.gather")
    async def test_run_monitor_successful_execution(
        self, mock_gather, mock_create_task
    ):
        """Test successful monitor execution"""
        # Mock tasks
        mock_monitoring_task = AsyncMock()
        mock_scheduled_task = AsyncMock()
        mock_create_task.side_effect = [mock_monitoring_task, mock_scheduled_task]

        # Mock gather to complete successfully
        mock_gather.return_value = None

        # Mock generate_daily_report
        self.monitor.generate_daily_report = AsyncMock()

        await self.monitor.run_monitor()

        # Verify running was set to True initially
        self.assertFalse(self.monitor.running)  # Should be reset in finally

        # Verify tasks were created
        self.assertEqual(mock_create_task.call_count, 2)

        # Verify gather was called with both tasks
        mock_gather.assert_called()

        # Verify final report generation
        self.monitor.generate_daily_report.assert_called_once()

    @patch("asyncio.create_task")
    @patch("asyncio.gather")
    async def test_run_monitor_keyboard_interrupt(self, mock_gather, mock_create_task):
        """Test monitor handling keyboard interrupt"""
        # Mock tasks
        mock_monitoring_task = AsyncMock()
        mock_scheduled_task = AsyncMock()
        mock_create_task.side_effect = [mock_monitoring_task, mock_scheduled_task]

        # Mock gather to raise KeyboardInterrupt
        mock_gather.side_effect = KeyboardInterrupt()

        # Mock generate_daily_report
        self.monitor.generate_daily_report = AsyncMock()

        await self.monitor.run_monitor()

        # Verify tasks were cancelled
        mock_monitoring_task.cancel.assert_called_once()
        mock_scheduled_task.cancel.assert_called_once()

        # Verify final report generation
        self.monitor.generate_daily_report.assert_called_once()

    @patch("asyncio.create_task")
    @patch("asyncio.gather")
    async def test_run_monitor_task_cancellation(self, mock_gather, mock_create_task):
        """Test monitor handling task cancellation"""
        # Mock tasks
        mock_monitoring_task = AsyncMock()
        mock_scheduled_task = AsyncMock()
        mock_create_task.side_effect = [mock_monitoring_task, mock_scheduled_task]

        # Mock gather to raise CancelledError
        mock_gather.side_effect = [
            asyncio.CancelledError(),
            None,
        ]  # First gather cancelled, second succeeds during cleanup

        # Mock generate_daily_report
        self.monitor.generate_daily_report = AsyncMock()

        await self.monitor.run_monitor()

        # Verify tasks were cancelled
        mock_monitoring_task.cancel.assert_called_once()
        mock_scheduled_task.cancel.assert_called_once()

        # Verify final report generation
        self.monitor.generate_daily_report.assert_called_once()

    @patch("asyncio.create_task")
    @patch("asyncio.gather")
    async def test_run_monitor_final_report_error(self, mock_gather, mock_create_task):
        """Test monitor handling error in final report generation"""
        # Mock tasks
        mock_monitoring_task = AsyncMock()
        mock_scheduled_task = AsyncMock()
        mock_create_task.side_effect = [mock_monitoring_task, mock_scheduled_task]

        # Mock gather to complete successfully
        mock_gather.return_value = None

        # Mock generate_daily_report to raise exception
        self.monitor.generate_daily_report = AsyncMock(
            side_effect=Exception("Report error")
        )

        # Should not raise exception, but handle it gracefully
        await self.monitor.run_monitor()

        # Verify final report generation was attempted
        self.monitor.generate_daily_report.assert_called_once()

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


# Test runner for async tests
def run_async_test(coro):
    """Helper function to run async tests"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Patch async test methods to run properly
def patch_async_methods(cls):
    """Patch async test methods to run synchronously"""
    for attr_name in dir(cls):
        if attr_name.startswith("test_"):
            method = getattr(cls, attr_name)
            if asyncio.iscoroutinefunction(method):

                def make_sync_wrapper(async_method):
                    def sync_wrapper(self):
                        return run_async_test(async_method(self))

                    return sync_wrapper

                setattr(cls, attr_name, make_sync_wrapper(method))
    return cls


# Apply the patch to the main test class
TestUptimeMonitor = patch_async_methods(TestUptimeMonitor)


if __name__ == "__main__":
    # Run with proper async handling
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2))
