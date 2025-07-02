# 🔍 Uptime Monitor

A comprehensive Python-based uptime monitoring tool that continuously monitors website availability with intelligent alerting, detailed reporting, and beautiful visualizations.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code Style](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

## ✨ Features

### 🚀 Core Monitoring
- **Continuous Monitoring**: Non-blocking async monitoring with configurable intervals
- **Smart Alerting**: Consecutive failure thresholds to prevent alert spam
- **Multiple Protocols**: HTTP/HTTPS support with custom timeout handling
- **Response Time Tracking**: Detailed performance metrics and statistics

### 📊 Reporting & Visualization
- **Daily Reports**: Automated PNG report generation with matplotlib
- **Uptime Statistics**: Percentage calculations and success/failure ratios
- **Response Time Charts**: Visual timeline of website performance
- **Historical Data**: SQLite storage with configurable retention periods

### 🔔 Multi-Channel Alerting
- **Email Notifications**: SMTP support with Gmail integration
- **Slack Integration**: Webhook-based notifications with rich formatting
- **Recovery Alerts**: Automatic notifications when services recover
- **Customizable Thresholds**: Configure when and how alerts are sent

### 🔧 Advanced Features
- **Async Architecture**: Non-blocking operations for optimal performance
- **Graceful Shutdown**: Proper cleanup with final report generation
- **Flexible Configuration**: YAML/JSON support with validation
- **Comprehensive Logging**: Centralized logging with file and console output
- **Data Management**: Automatic cleanup of old monitoring data

## 📸 Sample Output

### Console Monitoring
```
2025-07-02 10:30:15,123 - uptime_monitor - INFO - Starting uptime monitor for: https://example.com
2025-07-02 10:30:16,456 - uptime_monitor - INFO - https://example.com - UP (0.234s)
2025-07-02 10:35:16,789 - uptime_monitor - INFO - https://example.com - UP (0.187s)
```

### Generated Reports
The tool automatically generates daily uptime reports with:
- Uptime timeline visualization (green/red status bars)
- Response time trends and statistics
- Summary statistics (uptime percentage, avg response time)
- Professional formatting suitable for sharing

## 🚀 Quick Start

### Prerequisites
- Python 3.11 or higher
- pip package manager

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd uptime
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure monitoring**
   ```bash
   cp monitor_config.yaml.example monitor_config.yaml
   # Edit monitor_config.yaml with your settings
   ```

### Basic Usage

**Start continuous monitoring:**
```bash
python main.py
```

**Generate reports:**
```bash
python main.py --report                    # Yesterday's report
python main.py --report --date 2025-01-15 # Specific date
python main.py --report --days 7          # Last 7 days
python main.py --report --today           # Today's report
```

**Custom configuration:**
```bash
python main.py --config custom_config.yaml
```

## ⚙️ Configuration

### Configuration File (monitor_config.yaml)

```yaml
# Target URL to monitor
url: "https://your-website.com"

# Monitoring settings
check_interval: 300        # Check every 5 minutes (seconds)
timeout: 10               # Request timeout (seconds)
days_to_keep: 30          # Data retention period

# Alert settings
alert_on_failure: true
alert_on_recovery: true
consecutive_failures_threshold: 3  # Alert after N consecutive failures

# Email configuration (Gmail example)
smtp_server: "smtp.gmail.com"
smtp_port: 587
smtp_username: "your-email@gmail.com"
smtp_password: "your-app-password"
alert_recipients:
  - "admin@yourcompany.com"
  - "devops@yourcompany.com"

# Slack integration (optional)
slack_webhook_url: "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK"

# Database
db_path: "uptime_monitor.db"
```

### Environment Variables

You can also configure via environment variables:
```bash
export UPTIME_URL="https://your-site.com"
export UPTIME_CHECK_INTERVAL=300
export UPTIME_SMTP_USERNAME="your-email@gmail.com"
export UPTIME_SMTP_PASSWORD="your-password"
```

## 📊 Data Storage

### Database Schema
The tool uses SQLite with the following schema:

```sql
CREATE TABLE uptime_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    url TEXT NOT NULL,
    is_up BOOLEAN NOT NULL,
    response_time REAL,
    status_code INTEGER,
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### Generated Files
```
uptime/
├── uptime_monitor.db           # SQLite database
├── logs/
│   └── uptime_monitor.log     # Application logs
└── reports/
    ├── uptime_report_2025-01-15.png
    └── uptime_report_2025-01-16.png
```

## 🔧 Development

### Code Structure
```
uptime/
├── main.py                     # CLI entry point
├── uptime_monitor.py          # Core monitoring logic
├── database_manager.py        # Data persistence
├── alert_manager.py           # Notification system
├── monitor_config.py          # Configuration management
├── logging_config.py          # Centralized logging
├── monitor_config.yaml        # Configuration file
├── test_database_manager.py   # Unit tests
├── test_logging_config.py     # Unit tests
└── CLAUDE.md                  # Development guidance
```

### Running Tests
```bash
# Run all tests
python -m unittest discover -s . -p "test_*.py" -v

# Run specific test modules
python -m unittest test_database_manager.py -v
python -m unittest test_logging_config.py -v
```

### Code Quality
```bash
# Format code
ruff format .

# Lint code
ruff check .
```

## 📋 Command Line Options

```bash
usage: main.py [-h] [--report] [--date DATE] [--days DAYS] [--config CONFIG] [--today]

Enhanced URL Uptime Monitor

optional arguments:
  -h, --help            show this help message and exit
  --report, -r          Generate uptime report instead of running monitor
  --date DATE, -d DATE  Specific date for report generation (YYYY-MM-DD format)
  --days DAYS           Generate reports for the last N days
  --config CONFIG, -c CONFIG
                        Path to configuration file (default: monitor_config.yaml)
  --today               Generate report for today

Examples:
  python main.py                          # Run continuous monitoring
  python main.py --report                 # Generate report for yesterday
  python main.py --report --date 2025-05-30  # Generate report for specific date
  python main.py --report --days 7        # Generate reports for last 7 days
  python main.py --config custom.json     # Use custom config file
```

## 🚨 Alerting Examples

### Email Alert (Failure)
```
Subject: 🚨 SITE DOWN: https://example.com

ALERT: Website is DOWN

URL: https://example.com
Status: DOWN
Consecutive Failures: 3
Timestamp: 2025-01-15 14:30:00
Error: Connection timeout
```

### Email Alert (Recovery)
```
Subject: ✅ SITE RECOVERED: https://example.com

RECOVERY: Website is back UP

URL: https://example.com
Status: UP
Timestamp: 2025-01-15 14:35:00

The site has recovered from previous failures.
```

### Slack Alert
Rich formatted messages with color coding:
- 🚨 Red for failures
- ✅ Green for recoveries
- Timestamp and error details included

## 🔒 Security Considerations

### Email Configuration
- Use app-specific passwords for Gmail
- Store sensitive credentials in environment variables
- Consider using OAuth2 for production deployments

### Network Security
- Monitor internal services through VPN when possible
- Use HTTPS for webhook URLs
- Validate SSL certificates in production

## 📈 Performance

### Resource Usage
- **Memory**: ~10-20MB typical usage
- **CPU**: Minimal impact with async operations
- **Storage**: ~1MB per month of monitoring data
- **Network**: One HTTP request per check interval

### Scalability
- Single URL monitoring optimized for reliability
- For multiple URLs, run separate instances
- Database supports millions of check records
- Automatic data cleanup prevents unbounded growth

## 🛠️ Troubleshooting

### Common Issues

**Import Errors**
```bash
# Missing dependencies
pip install -r requirements.txt

# Virtual environment not activated
source venv/bin/activate
```

**Configuration Issues**
```bash
# Test configuration loading
python -c "from monitor_config import load_config_from_file; print(load_config_from_file())"

# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('monitor_config.yaml'))"
```

**Email Issues**
```bash
# Test SMTP connection
python -c "import smtplib; smtplib.SMTP('smtp.gmail.com', 587).ehlo()"

# Check app password (Gmail)
# Go to Google Account settings > Security > App passwords
```

### Logging
Check `logs/uptime_monitor.log` for detailed error information:
```bash
tail -f logs/uptime_monitor.log
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for new functionality
5. Run tests (`python -m unittest discover`)
6. Run linting (`ruff check .` and `ruff format .`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

### Development Guidelines
- Follow existing code style and patterns
- Add unit tests for new features
- Update documentation for user-facing changes
- Use conventional commit messages
- Ensure backwards compatibility

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **matplotlib** for beautiful report generation
- **requests** for reliable HTTP client functionality
- **PyYAML** for flexible configuration management
- **asyncio** for efficient async operations

## 📬 Support

- **Documentation**: See [CLAUDE.md](CLAUDE.md) for development guidance
- **Issues**: Report bugs and request features via GitHub Issues
- **Discussions**: Use GitHub Discussions for questions and community support

---

**Made with ❤️ for reliable website monitoring**