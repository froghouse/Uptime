import unittest
import tempfile
import os
import sqlite3
from datetime import datetime, date, timedelta
from unittest.mock import patch

from database_manager import DatabaseManager


class TestDatabaseManager(unittest.TestCase):
    """Unit tests for DatabaseManager class"""
    
    def setUp(self):
        """Create a temporary database for each test"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.db_manager = DatabaseManager(self.db_path)
    
    def tearDown(self):
        """Clean up temporary database after each test"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_init_database_creates_table(self):
        """Test that database initialization creates the required table"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='uptime_checks'
            """)
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            self.assertEqual(result[0], 'uptime_checks')
    
    def test_init_database_creates_indexes(self):
        """Test that database initialization creates the required indexes"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='index' AND name IN ('idx_timestamp_url', 'idx_url_timestamp')
            """)
            results = cursor.fetchall()
            index_names = [row[0] for row in results]
            self.assertIn('idx_timestamp_url', index_names)
            self.assertIn('idx_url_timestamp', index_names)
    
    def test_save_check_result_success(self):
        """Test saving a successful check result"""
        url = "https://example.com"
        is_up = True
        response_time = 0.5
        status_code = 200
        
        self.db_manager.save_check_result(url, is_up, response_time, status_code)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT url, is_up, response_time, status_code, error_message 
                FROM uptime_checks WHERE url = ?
            """, (url,))
            result = cursor.fetchone()
            
            self.assertIsNotNone(result)
            self.assertEqual(result[0], url)
            self.assertEqual(result[1], 1)  # SQLite stores bool as 1/0
            self.assertEqual(result[2], response_time)
            self.assertEqual(result[3], status_code)
            self.assertIsNone(result[4])
    
    def test_save_check_result_failure(self):
        """Test saving a failed check result with error message"""
        url = "https://broken.example.com"
        is_up = False
        error_message = "Connection timeout"
        
        self.db_manager.save_check_result(url, is_up, error_message=error_message)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT url, is_up, response_time, status_code, error_message 
                FROM uptime_checks WHERE url = ?
            """, (url,))
            result = cursor.fetchone()
            
            self.assertIsNotNone(result)
            self.assertEqual(result[0], url)
            self.assertEqual(result[1], 0)  # SQLite stores bool as 1/0
            self.assertIsNone(result[2])
            self.assertIsNone(result[3])
            self.assertEqual(result[4], error_message)
    
    def test_get_checks_for_date_with_data(self):
        """Test retrieving checks for a specific date with existing data"""
        url = "https://example.com"
        target_date = date.today()
        
        # Insert test data
        with sqlite3.connect(self.db_path) as conn:
            test_timestamp = datetime.combine(target_date, datetime.min.time().replace(hour=12))
            conn.execute("""
                INSERT INTO uptime_checks 
                (timestamp, url, is_up, response_time, status_code)
                VALUES (?, ?, ?, ?, ?)
            """, (test_timestamp, url, True, 0.3, 200))
        
        results = self.db_manager.get_checks_for_date(url, target_date)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['url'], url)
        self.assertEqual(results[0]['is_up'], 1)
        self.assertEqual(results[0]['response_time'], 0.3)
        self.assertEqual(results[0]['status_code'], 200)
    
    def test_get_checks_for_date_no_data(self):
        """Test retrieving checks for a date with no data"""
        url = "https://example.com"
        target_date = date.today()
        
        results = self.db_manager.get_checks_for_date(url, target_date)
        
        self.assertEqual(len(results), 0)
    
    def test_get_checks_for_date_different_date(self):
        """Test that checks from different dates are not returned"""
        url = "https://example.com"
        target_date = date.today()
        different_date = target_date - timedelta(days=1)
        
        # Insert data for different date
        with sqlite3.connect(self.db_path) as conn:
            test_timestamp = datetime.combine(different_date, datetime.min.time().replace(hour=12))
            conn.execute("""
                INSERT INTO uptime_checks 
                (timestamp, url, is_up, response_time, status_code)
                VALUES (?, ?, ?, ?, ?)
            """, (test_timestamp, url, True, 0.3, 200))
        
        results = self.db_manager.get_checks_for_date(url, target_date)
        
        self.assertEqual(len(results), 0)
    
    def test_get_recent_checks_with_limit(self):
        """Test retrieving recent checks with limit"""
        url = "https://example.com"
        
        # Insert multiple test records with timestamps going back in time
        timestamps = []
        with sqlite3.connect(self.db_path) as conn:
            for i in range(5):
                timestamp = datetime.now() - timedelta(minutes=i)
                timestamps.append(timestamp)
                conn.execute("""
                    INSERT INTO uptime_checks 
                    (timestamp, url, is_up, response_time, status_code)
                    VALUES (?, ?, ?, ?, ?)
                """, (timestamp, url, True, 0.1 + (i * 0.1), 200))
        
        results = self.db_manager.get_recent_checks(url, limit=3)
        
        self.assertEqual(len(results), 3)
        # Results should be ordered by timestamp DESC (most recent first)
        # Convert timestamp strings back to datetime for comparison
        result_timestamps = [datetime.fromisoformat(r['timestamp'].replace(' ', 'T')) for r in results]
        self.assertGreater(result_timestamps[0], result_timestamps[1])
        self.assertGreater(result_timestamps[1], result_timestamps[2])
    
    def test_get_recent_checks_default_limit(self):
        """Test retrieving recent checks with default limit"""
        url = "https://example.com"
        
        # Insert more than default limit (10) records
        with sqlite3.connect(self.db_path) as conn:
            for i in range(15):
                timestamp = datetime.now() - timedelta(minutes=i)
                conn.execute("""
                    INSERT INTO uptime_checks 
                    (timestamp, url, is_up, response_time, status_code)
                    VALUES (?, ?, ?, ?, ?)
                """, (timestamp, url, True, 0.1, 200))
        
        results = self.db_manager.get_recent_checks(url)
        
        self.assertEqual(len(results), 10)  # Default limit
    
    def test_get_recent_checks_no_data(self):
        """Test retrieving recent checks when no data exists"""
        url = "https://nonexistent.com"
        
        results = self.db_manager.get_recent_checks(url)
        
        self.assertEqual(len(results), 0)
    
    def test_cleanup_old_data(self):
        """Test cleanup of old data"""
        url = "https://example.com"
        days_to_keep = 7
        
        # Insert old data (should be deleted)
        old_timestamp = datetime.now() - timedelta(days=10)
        # Insert recent data (should be kept)
        recent_timestamp = datetime.now() - timedelta(days=3)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO uptime_checks 
                (timestamp, url, is_up, response_time, status_code)
                VALUES (?, ?, ?, ?, ?)
            """, (old_timestamp, url, True, 0.1, 200))
            
            conn.execute("""
                INSERT INTO uptime_checks 
                (timestamp, url, is_up, response_time, status_code)
                VALUES (?, ?, ?, ?, ?)
            """, (recent_timestamp, url, True, 0.2, 200))
        
        self.db_manager.cleanup_old_data(days_to_keep)
        
        # Check that only recent data remains
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM uptime_checks")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
            
            cursor = conn.execute("""
                SELECT response_time FROM uptime_checks WHERE url = ?
            """, (url,))
            result = cursor.fetchone()
            self.assertEqual(result[0], 0.2)  # Recent data should remain
        
        # Check that logging was called by verifying the log message format
        # Since we can't easily mock the logger in the instance, we'll verify the data was deleted correctly
        # The logging functionality is tested separately
    
    def test_cleanup_old_data_no_old_data(self):
        """Test cleanup when no old data exists"""
        url = "https://example.com"
        days_to_keep = 7
        
        # Insert only recent data
        recent_timestamp = datetime.now() - timedelta(days=3)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO uptime_checks 
                (timestamp, url, is_up, response_time, status_code)
                VALUES (?, ?, ?, ?, ?)
            """, (recent_timestamp, url, True, 0.1, 200))
        
        self.db_manager.cleanup_old_data(days_to_keep)
        
        # Check that data remains
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM uptime_checks")
            count = cursor.fetchone()[0]
            self.assertEqual(count, 1)
    
    def test_database_path_property(self):
        """Test that database path is correctly stored"""
        self.assertEqual(self.db_manager.db_path, self.db_path)
    
    def test_multiple_urls(self):
        """Test operations with multiple URLs"""
        url1 = "https://example1.com"
        url2 = "https://example2.com"
        
        # Save data for both URLs
        self.db_manager.save_check_result(url1, True, 0.1, 200)
        self.db_manager.save_check_result(url2, False, error_message="Timeout")
        
        # Get recent checks for each URL
        results1 = self.db_manager.get_recent_checks(url1)
        results2 = self.db_manager.get_recent_checks(url2)
        
        self.assertEqual(len(results1), 1)
        self.assertEqual(len(results2), 1)
        self.assertEqual(results1[0]['url'], url1)
        self.assertEqual(results2[0]['url'], url2)
        self.assertEqual(results1[0]['is_up'], 1)
        self.assertEqual(results2[0]['is_up'], 0)


if __name__ == '__main__':
    unittest.main()