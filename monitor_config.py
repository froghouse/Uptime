from dataclasses import dataclass
from typing import Optional, List
from pathlib import Path
import json
import os
import importlib.util

# Check for JSON availability
JSON_AVAILABLE = importlib.util.find_spec("json") is not None
if not JSON_AVAILABLE:
    print(
        "Warning: JSON module not found. Please ensure Python's standard library is intact."
    )
    print("Falling back to YAML configuration support only.")


# Check for YAML availability
YAML_AVAILABLE = importlib.util.find_spec("yaml") is not None
if not YAML_AVAILABLE:
    print("Warning: PyYAML not found. Please install with: pip install PyYAML")
    print("Falling back to JSON configuration support only.")


# Configuration dataclass
@dataclass
class MonitorConfig:
    url: str
    check_interval: int = 300  # 5 minutes
    timeout: int = 10
    db_path: str = "uptime_monitor.db"
    days_to_keep: int = 30

    # Email alerting config
    smtp_server: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    alert_recipients: List[str] = None

    # Slack alerting config
    slack_webhook_url: Optional[str] = None

    # Alert thresholds
    alert_on_failure: bool = True
    alert_on_recovery: bool = True
    consecutive_failures_threshold: int = 3


def load_config_from_file(config_path: str = "monitor_config.yaml") -> MonitorConfig:
    """Load configuration from YAML or JSON file"""

    # Determine file format from extension
    path_obj = Path(config_path)
    is_yaml = path_obj.suffix.lower() in [".yaml", ".yml"]
    is_json = path_obj.suffix.lower() == ".json"

    # Auto-detect format if no extension or unknown extension
    if not (is_yaml or is_json):
        # Try YAML first if available, then JSON
        if YAML_AVAILABLE:
            config_path = str(path_obj.with_suffix(".yaml"))
            is_yaml = True
        else:
            config_path = str(path_obj.with_suffix(".json"))
            is_json = True

    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                if is_yaml and YAML_AVAILABLE:
                    import yaml

                    config_data = yaml.safe_load(f)
                else:
                    config_data = json.load(f)
            return MonitorConfig(**config_data)
        except Exception as e:
            print(f"Error loading config file {config_path}: {e}")
            print("Creating new default configuration...")

    # Create default config file
    default_config = {
        "url": "https://httpbin.org/status/200",
        "check_interval": 300,
        "timeout": 10,
        "db_path": "uptime_monitor.db",
        "days_to_keep": 30,
        "smtp_server": None,
        "smtp_port": 587,
        "smtp_username": None,
        "smtp_password": None,
        "alert_recipients": [],
        "slack_webhook_url": None,
        "alert_on_failure": True,
        "alert_on_recovery": True,
        "consecutive_failures_threshold": 3,
    }

    # Save config in preferred format
    try:
        with open(config_path, "w") as f:
            if is_yaml and YAML_AVAILABLE:
                import yaml

                yaml.dump(default_config, f, default_flow_style=False, indent=2)
                print(f"Created default YAML config file: {config_path}")
            else:
                json.dump(default_config, f, indent=2)
                print(f"Created default JSON config file: {config_path}")

        print("Please edit the configuration and run again.")

    except Exception as e:
        print(f"Error creating config file: {e}")

    return MonitorConfig(**default_config)
