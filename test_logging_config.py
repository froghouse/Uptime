import unittest
import tempfile
import os
import logging
import shutil
from pathlib import Path
from io import StringIO
from unittest.mock import patch

from logging_config import setup_logging, get_logger


class TestLoggingConfig(unittest.TestCase):
    """Unit tests for logging_config module"""
    
    def setUp(self):
        """Setup test environment"""
        # Create temporary directory for test logs
        self.temp_dir = tempfile.mkdtemp()
        self.test_log_dir = os.path.join(self.temp_dir, "test_logs")
        
        # Clear any existing handlers to avoid conflicts
        root_logger = logging.getLogger()
        root_logger.handlers.clear()
        root_logger.setLevel(logging.NOTSET)
        
    def tearDown(self):
        """Clean up test environment"""
        # Properly close all handlers before clearing
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            handler.close()
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.NOTSET)
        
        # Remove temporary directory
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_setup_logging_default_parameters(self):
        """Test setup_logging with default parameters"""
        # Use a real temporary directory instead of mocking
        setup_logging(log_dir=self.test_log_dir)
        
        # Check root logger configuration
        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.INFO)
        self.assertEqual(len(root_logger.handlers), 2)  # Console + File
    
    def test_setup_logging_custom_log_level(self):
        """Test setup_logging with custom log level"""
        setup_logging(log_level="DEBUG", log_dir=self.test_log_dir)
        
        root_logger = logging.getLogger()
        self.assertEqual(root_logger.level, logging.DEBUG)
    
    def test_setup_logging_custom_log_dir(self):
        """Test setup_logging with custom log directory"""
        setup_logging(log_dir=self.test_log_dir)
        
        # Check that the directory was created
        self.assertTrue(os.path.exists(self.test_log_dir))
        
        # Check that log file path is correct
        log_file_path = os.path.join(self.test_log_dir, "uptime_monitor.log")
        
        # Test actual logging to verify file handler works
        test_logger = get_logger("test")
        test_logger.info("Test message")
        
        # Check that log file was created and has content
        self.assertTrue(os.path.exists(log_file_path))
        with open(log_file_path, 'r') as f:
            content = f.read()
            self.assertIn("Test message", content)
    
    def test_setup_logging_invalid_log_level(self):
        """Test setup_logging with invalid log level"""
        with self.assertRaises(AttributeError):
            setup_logging(log_level="INVALID_LEVEL")
    
    def test_setup_logging_creates_handlers(self):
        """Test that setup_logging creates proper handlers"""
        setup_logging(log_dir=self.test_log_dir)
        
        root_logger = logging.getLogger()
        
        # Should have exactly 2 handlers: console and file
        self.assertEqual(len(root_logger.handlers), 2)
        
        # Check handler types
        handler_types = [type(handler).__name__ for handler in root_logger.handlers]
        self.assertIn("StreamHandler", handler_types)
        self.assertIn("FileHandler", handler_types)
        
        # Check handler levels
        for handler in root_logger.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
                self.assertEqual(handler.level, logging.INFO)
            elif isinstance(handler, logging.FileHandler):
                self.assertEqual(handler.level, logging.DEBUG)
    
    def test_setup_logging_handler_formatters(self):
        """Test that handlers have proper formatters"""
        setup_logging(log_dir=self.test_log_dir)
        
        root_logger = logging.getLogger()
        
        for handler in root_logger.handlers:
            self.assertIsNotNone(handler.formatter)
            # Check formatter format string
            format_string = handler.formatter._fmt
            self.assertIn("%(asctime)s", format_string)
            self.assertIn("%(name)s", format_string)
            self.assertIn("%(levelname)s", format_string)
            self.assertIn("%(message)s", format_string)
    
    def test_setup_logging_clears_existing_handlers(self):
        """Test that setup_logging clears existing handlers"""
        root_logger = logging.getLogger()
        
        # Add a dummy handler
        dummy_handler = logging.StreamHandler()
        root_logger.addHandler(dummy_handler)
        self.assertEqual(len(root_logger.handlers), 1)
        
        # Setup logging should clear existing handlers
        setup_logging(log_dir=self.test_log_dir)
        
        # Should have new handlers, not the dummy one
        self.assertEqual(len(root_logger.handlers), 2)
        self.assertNotIn(dummy_handler, root_logger.handlers)
    
    def test_setup_logging_third_party_loggers(self):
        """Test that third-party loggers are configured with WARNING level"""
        setup_logging(log_dir=self.test_log_dir)
        
        # Check specific third-party loggers
        urllib3_logger = logging.getLogger("urllib3")
        requests_logger = logging.getLogger("requests")
        matplotlib_logger = logging.getLogger("matplotlib")
        
        self.assertEqual(urllib3_logger.level, logging.WARNING)
        self.assertEqual(requests_logger.level, logging.WARNING)
        self.assertEqual(matplotlib_logger.level, logging.WARNING)
    
    def test_get_logger_returns_logger_instance(self):
        """Test that get_logger returns proper Logger instance"""
        logger = get_logger("test_module")
        
        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.name, "test_module")
    
    def test_get_logger_different_names(self):
        """Test that get_logger returns different loggers for different names"""
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        
        self.assertNotEqual(logger1, logger2)
        self.assertEqual(logger1.name, "module1")
        self.assertEqual(logger2.name, "module2")
    
    def test_get_logger_same_name_returns_same_instance(self):
        """Test that get_logger returns same instance for same name"""
        logger1 = get_logger("same_module")
        logger2 = get_logger("same_module")
        
        self.assertIs(logger1, logger2)
    
    def test_logging_integration_console_output(self):
        """Test actual logging output to console"""
        # Capture console output
        with patch('sys.stdout', new_callable=StringIO) as mock_stdout:
            setup_logging(log_dir=self.test_log_dir)
            
            logger = get_logger("test_console")
            logger.info("Test console message")
            
            # Note: StreamHandler writes to stderr by default, not stdout
            # So we need to check stderr instead
        
        with patch('sys.stderr', new_callable=StringIO) as mock_stderr:
            setup_logging(log_dir=self.test_log_dir)
            
            logger = get_logger("test_console")
            logger.info("Test console message")
            
            output = mock_stderr.getvalue()
            self.assertIn("Test console message", output)
            self.assertIn("test_console", output)
            self.assertIn("INFO", output)
    
    def test_logging_integration_file_output(self):
        """Test actual logging output to file"""
        setup_logging(log_dir=self.test_log_dir)
        
        logger = get_logger("test_file")
        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")
        
        # Ensure all handlers are flushed
        for handler in logging.getLogger().handlers:
            handler.flush()
        
        log_file_path = os.path.join(self.test_log_dir, "uptime_monitor.log")
        self.assertTrue(os.path.exists(log_file_path))
        
        with open(log_file_path, 'r') as f:
            content = f.read()
            
            # File handler is set to DEBUG level, but root logger level controls what gets through
            # Since we set up with default INFO level, DEBUG messages won't appear
            self.assertIn("Info message", content)
            self.assertIn("Warning message", content)
            self.assertIn("Error message", content)
            self.assertIn("test_file", content)
    
    def test_logging_levels_filtering(self):
        """Test that log levels are properly filtered"""
        setup_logging(log_level="WARNING", log_dir=self.test_log_dir)
        
        logger = get_logger("test_levels")
        
        # Capture file output
        logger.debug("Debug message - should not appear")
        logger.info("Info message - should not appear")
        logger.warning("Warning message - should appear")
        logger.error("Error message - should appear")
        
        log_file_path = os.path.join(self.test_log_dir, "uptime_monitor.log")
        
        with open(log_file_path, 'r') as f:
            content = f.read()
            
            # Only WARNING and above should appear in file
            # Note: File handler is always DEBUG, but root logger level controls what gets through
            self.assertNotIn("Debug message", content)
            self.assertNotIn("Info message", content)
            self.assertIn("Warning message", content)
            self.assertIn("Error message", content)
    
    def test_multiple_setup_calls(self):
        """Test that multiple calls to setup_logging don't create duplicate handlers"""
        setup_logging(log_dir=self.test_log_dir)
        initial_handler_count = len(logging.getLogger().handlers)
        
        # Call setup_logging again
        setup_logging(log_dir=self.test_log_dir)
        
        # Should still have the same number of handlers
        self.assertEqual(len(logging.getLogger().handlers), initial_handler_count)
        self.assertEqual(len(logging.getLogger().handlers), 2)  # Console + File
    
    def test_log_directory_creation(self):
        """Test that log directory is created if it doesn't exist"""
        non_existent_dir = os.path.join(self.temp_dir, "new_logs")
        self.assertFalse(os.path.exists(non_existent_dir))
        
        setup_logging(log_dir=non_existent_dir)
        
        self.assertTrue(os.path.exists(non_existent_dir))
        
        # Test that logging works in the new directory
        logger = get_logger("test_creation")
        logger.info("Test message")
        
        log_file = os.path.join(non_existent_dir, "uptime_monitor.log")
        self.assertTrue(os.path.exists(log_file))
    
    def test_concurrent_logger_access(self):
        """Test that concurrent access to loggers works correctly"""
        setup_logging(log_dir=self.test_log_dir)
        
        # Create multiple loggers simultaneously
        loggers = []
        for i in range(10):
            logger = get_logger(f"concurrent_test_{i}")
            loggers.append(logger)
            logger.info(f"Message from logger {i}")
        
        # All loggers should be different instances
        for i, logger in enumerate(loggers):
            self.assertEqual(logger.name, f"concurrent_test_{i}")
        
        # Check that all messages were logged
        log_file_path = os.path.join(self.test_log_dir, "uptime_monitor.log")
        with open(log_file_path, 'r') as f:
            content = f.read()
            
            for i in range(10):
                self.assertIn(f"Message from logger {i}", content)


if __name__ == '__main__':
    unittest.main()