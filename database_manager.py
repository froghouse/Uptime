from typing import Optional, List, Dict, Any
import sqlite3
import logging
from datetime import datetime, timedelta, time as dt_time

from logging_config import get_logger


class DatabaseManager:
    """Handles all database operations"""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.logger = get_logger(__name__)
        self.init_database()

    def init_database(self) -> None:
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
    ) -> None:
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

    def cleanup_old_data(self, days_to_keep: int) -> None:
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
            self.logger.info(f"Cleaned up {deleted_rows} old records")
