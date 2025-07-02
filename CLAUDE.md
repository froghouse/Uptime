# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python-based URL uptime monitoring tool that continuously monitors website availability with alerting and reporting capabilities. The application uses async/await patterns for non-blocking operations and stores data in SQLite.

## Architecture

The codebase follows a modular design with clear separation of concerns:

- **main.py**: CLI entry point with argument parsing and asyncio task orchestration
- **uptime_monitor.py**: Core monitoring engine with async HTTP requests and status tracking
- **database_manager.py**: SQLite database operations with proper connection management
- **alert_manager.py**: Email and Slack notification system with failure threshold logic
- **monitor_config.py**: YAML/JSON configuration management with dataclass validation
- **logging_config.py**: Centralized logging configuration for all application components

## Development Commands

### Setup and Dependencies
```bash
# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Code formatting and linting
ruff check .
ruff format .
```

### Running the Application

**Continuous monitoring mode:**
```bash
python main.py
```

**Report generation:**
```bash
python main.py --report                    # Yesterday's report
python main.py --report --date 2025-06-01 # Specific date report
python main.py --report --days 7          # Last 7 days
python main.py --report --today           # Today's report
```

**Custom configuration:**
```bash
python main.py --config custom_config.yaml
```

## Configuration

The system uses `monitor_config.yaml` for configuration. Key settings include:
- URL to monitor
- Check interval (seconds)
- Alert thresholds and recipients
- Database retention period
- SMTP settings for email alerts

## Database Schema

SQLite database (`uptime_monitor.db`) with `uptime_checks` table:
- `timestamp` (TEXT): ISO format timestamp
- `url` (TEXT): Monitored URL
- `status` (TEXT): 'UP' or 'DOWN'
- `response_time` (REAL): Response time in seconds
- `status_code` (INTEGER): HTTP status code
- `error_message` (TEXT): Error details if any

## Key Patterns

**Async Operations**: All monitoring and database operations use async/await for non-blocking execution.

**Configuration Management**: Supports both YAML and JSON with graceful fallbacks and type validation.

**Centralized Logging**: Application-wide logging configuration in `logging_config.py` with consistent formatting across all components.

**Error Handling**: Comprehensive exception handling with structured logging to `logs/uptime_monitor.log`.

**Graceful Shutdown**: Handles SIGINT/SIGTERM with proper cleanup and final report generation.

## Generated Artifacts

- **Database**: `uptime_monitor.db` (SQLite)
- **Logs**: `logs/uptime_monitor.log`
- **Reports**: `reports/uptime_report_YYYY-MM-DD.png` (matplotlib charts)

## Dependencies

Core libraries: `asyncio`, `requests`, `matplotlib`, `numpy`, `PyYAML`, `aiofiles`, `sqlite3`

Formatting: `ruff` for code linting and formatting