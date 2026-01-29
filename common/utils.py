"""Common utility functions."""

from __future__ import annotations

import os
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Union, Optional

import yaml


def generate_id(prefix: str = "") -> str:
    """Generate a unique identifier."""
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    if prefix:
        return f"{prefix}_{timestamp}_{short_uuid}"
    return f"{timestamp}_{short_uuid}"


def generate_execution_id() -> str:
    """Generate an execution ID."""
    return generate_id("exec")


def parse_size(size_str: str) -> int:
    """Parse a size string (e.g., '10G', '512M', '4k') to bytes."""
    size_str = size_str.strip().upper()
    
    units = {
        'B': 1,
        'K': 1024,
        'KB': 1024,
        'M': 1024 ** 2,
        'MB': 1024 ** 2,
        'G': 1024 ** 3,
        'GB': 1024 ** 3,
        'T': 1024 ** 4,
        'TB': 1024 ** 4,
    }
    
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([A-Z]*)$', size_str)
    if not match:
        raise ValueError(f"Invalid size format: {size_str}")
    
    value = float(match.group(1))
    unit = match.group(2) or 'B'
    
    if unit not in units:
        raise ValueError(f"Unknown unit: {unit}")
    
    return int(value * units[unit])


def format_size(bytes_val: int, precision: int = 2) -> str:
    """Format bytes to human-readable string."""
    if bytes_val < 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    unit_index = 0
    size = float(bytes_val)
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    if unit_index == 0:
        return f"{int(size)} {units[unit_index]}"
    return f"{size:.{precision}f} {units[unit_index]}"


def parse_bandwidth(bw_str: str) -> float:
    """Parse bandwidth string (e.g., '10Gbps', '1000Mbps') to bits per second."""
    bw_str = bw_str.strip().upper()
    
    units = {
        'BPS': 1,
        'KBPS': 1000,
        'MBPS': 1000 ** 2,
        'GBPS': 1000 ** 3,
        'TBPS': 1000 ** 4,
    }
    
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([A-Z]*)$', bw_str)
    if not match:
        raise ValueError(f"Invalid bandwidth format: {bw_str}")
    
    value = float(match.group(1))
    unit = match.group(2) or 'BPS'
    
    if unit not in units:
        raise ValueError(f"Unknown unit: {unit}")
    
    return value * units[unit]


def format_bandwidth(bps: float, precision: int = 2) -> str:
    """Format bits per second to human-readable string."""
    units = ['bps', 'Kbps', 'Mbps', 'Gbps', 'Tbps']
    unit_index = 0
    size = float(bps)
    
    while size >= 1000 and unit_index < len(units) - 1:
        size /= 1000
        unit_index += 1
    
    return f"{size:.{precision}f} {units[unit_index]}"


def format_duration(seconds: int) -> str:
    """Format seconds to human-readable duration."""
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        minutes = seconds // 60
        secs = seconds % 60
        return f"{minutes}m {secs}s"
    else:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60
        return f"{hours}h {minutes}m {secs}s"


def load_yaml(path: str | Path) -> dict:
    """Load a YAML file."""
    with open(path, 'r') as f:
        return yaml.safe_load(f) or {}


def save_yaml(path: str | Path, data: dict) -> None:
    """Save data to a YAML file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w') as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def deep_merge(base: dict, override: dict) -> dict:
    """Deep merge two dictionaries."""
    result = base.copy()
    
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    
    return result


def get_env(key: str, default: Any = None, required: bool = False) -> Any:
    """Get environment variable with optional default and required check."""
    value = os.environ.get(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable not set: {key}")
    return value


def ensure_dir(path: str | Path) -> Path:
    """Ensure a directory exists, creating it if necessary."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_filename(name: str) -> str:
    """Sanitize a string to be used as a filename."""
    # Replace spaces with underscores
    name = name.replace(' ', '_')
    # Remove any characters that aren't alphanumeric, underscore, hyphen, or dot
    name = re.sub(r'[^\w\-.]', '', name)
    # Limit length
    return name[:255]


class Timer:
    """Simple context manager for timing code blocks."""
    
    def __init__(self):
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None
    
    def __enter__(self):
        self.start_time = datetime.utcnow()
        return self
    
    def __exit__(self, *args):
        self.end_time = datetime.utcnow()
    
    @property
    def elapsed_seconds(self) -> float:
        if self.start_time is None:
            return 0
        end = self.end_time or datetime.utcnow()
        return (end - self.start_time).total_seconds()
    
    @property
    def elapsed_ms(self) -> float:
        return self.elapsed_seconds * 1000
