"""Unit tests for common utility functions."""

import os
import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from common.utils import (
    generate_id,
    generate_execution_id,
    parse_size,
    format_size,
    parse_bandwidth,
    format_bandwidth,
    format_duration,
    load_yaml,
    save_yaml,
    deep_merge,
    get_env,
    ensure_dir,
    sanitize_filename,
    Timer,
)


class TestGenerateID:
    """Tests for ID generation functions."""
    
    def test_generate_id_no_prefix(self):
        """Test generating ID without prefix."""
        id1 = generate_id()
        id2 = generate_id()
        
        assert id1 != id2
        assert len(id1) > 0
        assert "_" in id1
    
    def test_generate_id_with_prefix(self):
        """Test generating ID with prefix."""
        id1 = generate_id("test")
        
        assert id1.startswith("test_")
        assert len(id1) > len("test_")
    
    def test_generate_execution_id(self):
        """Test generating execution ID."""
        exec_id = generate_execution_id()
        
        assert exec_id.startswith("exec_")
        assert len(exec_id) > len("exec_")


class TestParseSize:
    """Tests for size parsing functions."""
    
    def test_parse_size_bytes(self):
        """Test parsing bytes."""
        assert parse_size("1024") == 1024
        assert parse_size("1024B") == 1024
    
    def test_parse_size_kb(self):
        """Test parsing kilobytes."""
        assert parse_size("1K") == 1024
        assert parse_size("1KB") == 1024
        assert parse_size("2K") == 2048
    
    def test_parse_size_mb(self):
        """Test parsing megabytes."""
        assert parse_size("1M") == 1024 ** 2
        assert parse_size("1MB") == 1024 ** 2
        assert parse_size("2M") == 2 * (1024 ** 2)
    
    def test_parse_size_gb(self):
        """Test parsing gigabytes."""
        assert parse_size("1G") == 1024 ** 3
        assert parse_size("1GB") == 1024 ** 3
        assert parse_size("2G") == 2 * (1024 ** 3)
    
    def test_parse_size_tb(self):
        """Test parsing terabytes."""
        assert parse_size("1T") == 1024 ** 4
        assert parse_size("1TB") == 1024 ** 4
    
    def test_parse_size_decimal(self):
        """Test parsing decimal sizes."""
        assert parse_size("1.5G") == int(1.5 * (1024 ** 3))
        assert parse_size("0.5M") == int(0.5 * (1024 ** 2))
    
    def test_parse_size_invalid(self):
        """Test parsing invalid size strings."""
        with pytest.raises(ValueError):
            parse_size("invalid")
        
        with pytest.raises(ValueError):
            parse_size("10X")  # Unknown unit
    
    def test_format_size(self):
        """Test formatting bytes to human-readable."""
        assert format_size(0) == "0 B"
        assert format_size(1024) == "1.00 KB"
        assert format_size(1024 ** 2) == "1.00 MB"
        assert format_size(1024 ** 3) == "1.00 GB"
        assert format_size(1536) == "1.50 KB"
    
    def test_format_size_negative(self):
        """Test formatting negative sizes."""
        assert format_size(-100) == "0 B"


class TestParseBandwidth:
    """Tests for bandwidth parsing functions."""
    
    def test_parse_bandwidth_bps(self):
        """Test parsing bits per second."""
        assert parse_bandwidth("1000") == 1000
        assert parse_bandwidth("1000BPS") == 1000
    
    def test_parse_bandwidth_kbps(self):
        """Test parsing kilobits per second."""
        assert parse_bandwidth("1KBPS") == 1000
        assert parse_bandwidth("2KBPS") == 2000
    
    def test_parse_bandwidth_mbps(self):
        """Test parsing megabits per second."""
        assert parse_bandwidth("1MBPS") == 1000 ** 2
        assert parse_bandwidth("10MBPS") == 10 * (1000 ** 2)
    
    def test_parse_bandwidth_gbps(self):
        """Test parsing gigabits per second."""
        assert parse_bandwidth("1GBPS") == 1000 ** 3
        assert parse_bandwidth("10GBPS") == 10 * (1000 ** 3)
    
    def test_parse_bandwidth_decimal(self):
        """Test parsing decimal bandwidth."""
        assert parse_bandwidth("1.5GBPS") == 1.5 * (1000 ** 3)
    
    def test_parse_bandwidth_invalid(self):
        """Test parsing invalid bandwidth strings."""
        with pytest.raises(ValueError):
            parse_bandwidth("invalid")
        
        with pytest.raises(ValueError):
            parse_bandwidth("10X")  # Unknown unit
    
    def test_format_bandwidth(self):
        """Test formatting bandwidth to human-readable."""
        assert format_bandwidth(1000) == "1.00 Kbps"
        assert format_bandwidth(1000 ** 2) == "1.00 Mbps"
        assert format_bandwidth(1000 ** 3) == "1.00 Gbps"
        assert format_bandwidth(1500) == "1.50 Kbps"


class TestFormatDuration:
    """Tests for duration formatting."""
    
    def test_format_duration_seconds(self):
        """Test formatting seconds."""
        assert format_duration(0) == "0s"
        assert format_duration(30) == "30s"
        assert format_duration(59) == "59s"
    
    def test_format_duration_minutes(self):
        """Test formatting minutes."""
        assert format_duration(60) == "1m 0s"
        assert format_duration(90) == "1m 30s"
        assert format_duration(3599) == "59m 59s"
    
    def test_format_duration_hours(self):
        """Test formatting hours."""
        assert format_duration(3600) == "1h 0m 0s"
        assert format_duration(3661) == "1h 1m 1s"
        assert format_duration(7323) == "2h 2m 3s"


class TestYAML:
    """Tests for YAML file operations."""
    
    def test_save_and_load_yaml(self, temp_dir):
        """Test saving and loading YAML files."""
        test_data = {
            "key1": "value1",
            "key2": 123,
            "key3": [1, 2, 3],
            "key4": {"nested": "value"},
        }
        
        yaml_path = temp_dir / "test.yaml"
        save_yaml(yaml_path, test_data)
        
        assert yaml_path.exists()
        
        loaded_data = load_yaml(yaml_path)
        assert loaded_data == test_data
    
    def test_load_yaml_nonexistent(self, temp_dir):
        """Test loading non-existent YAML file."""
        yaml_path = temp_dir / "nonexistent.yaml"
        
        with pytest.raises(FileNotFoundError):
            load_yaml(yaml_path)
    
    def test_load_yaml_empty(self, temp_dir):
        """Test loading empty YAML file."""
        yaml_path = temp_dir / "empty.yaml"
        yaml_path.write_text("")
        
        data = load_yaml(yaml_path)
        assert data == {}


class TestDeepMerge:
    """Tests for deep merge function."""
    
    def test_deep_merge_simple(self):
        """Test simple deep merge."""
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        
        result = deep_merge(base, override)
        
        assert result == {"a": 1, "b": 3, "c": 4}
        assert base == {"a": 1, "b": 2}  # Original unchanged
    
    def test_deep_merge_nested(self):
        """Test nested deep merge."""
        base = {"a": {"x": 1, "y": 2}, "b": 3}
        override = {"a": {"y": 20, "z": 30}, "c": 4}
        
        result = deep_merge(base, override)
        
        assert result == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3, "c": 4}
    
    def test_deep_merge_override_list(self):
        """Test that lists are replaced, not merged."""
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}
        
        result = deep_merge(base, override)
        
        assert result == {"items": [4, 5]}


class TestGetEnv:
    """Tests for environment variable functions."""
    
    def test_get_env_existing(self, monkeypatch):
        """Test getting existing environment variable."""
        monkeypatch.setenv("TEST_VAR", "test_value")
        
        assert get_env("TEST_VAR") == "test_value"
    
    def test_get_env_missing_with_default(self):
        """Test getting missing env var with default."""
        assert get_env("NONEXISTENT_VAR", default="default_value") == "default_value"
    
    def test_get_env_missing_required(self):
        """Test getting missing required env var."""
        with pytest.raises(ValueError):
            get_env("NONEXISTENT_REQUIRED", required=True)


class TestEnsureDir:
    """Tests for directory creation."""
    
    def test_ensure_dir_creates(self, temp_dir):
        """Test creating directory."""
        new_dir = temp_dir / "new" / "nested" / "dir"
        
        result = ensure_dir(new_dir)
        
        assert new_dir.exists()
        assert new_dir.is_dir()
        assert result == new_dir
    
    def test_ensure_dir_existing(self, temp_dir):
        """Test ensuring existing directory."""
        existing_dir = temp_dir / "existing"
        existing_dir.mkdir()
        
        result = ensure_dir(existing_dir)
        
        assert existing_dir.exists()
        assert result == existing_dir


class TestSanitizeFilename:
    """Tests for filename sanitization."""
    
    def test_sanitize_filename_simple(self):
        """Test sanitizing simple filename."""
        assert sanitize_filename("test") == "test"
        assert sanitize_filename("test_file") == "test_file"
    
    def test_sanitize_filename_spaces(self):
        """Test sanitizing filename with spaces."""
        assert sanitize_filename("test file") == "test_file"
        assert sanitize_filename("my test file") == "my_test_file"
    
    def test_sanitize_filename_special_chars(self):
        """Test sanitizing filename with special characters."""
        assert sanitize_filename("test@file#name") == "testfilename"
        assert sanitize_filename("test/file\\name") == "testfilename"
    
    def test_sanitize_filename_length(self):
        """Test filename length limit."""
        long_name = "a" * 300
        result = sanitize_filename(long_name)
        
        assert len(result) == 255


class TestTimer:
    """Tests for Timer context manager."""
    
    def test_timer_context(self):
        """Test timer as context manager."""
        with Timer() as timer:
            pass
        
        assert timer.start_time is not None
        assert timer.end_time is not None
        assert timer.elapsed_seconds >= 0
        assert timer.elapsed_ms >= 0
    
    def test_timer_elapsed_before_exit(self):
        """Test timer elapsed time before exit."""
        timer = Timer()
        with timer:
            elapsed = timer.elapsed_seconds
        
        assert elapsed >= 0
        assert timer.elapsed_seconds >= elapsed
