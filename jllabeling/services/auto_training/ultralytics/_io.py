import json
import os
import tempfile
import yaml
from typing import Dict, Any

from .config import get_settings_config_path


def ensure_config_dir():
    """
    Ensure the configuration directory exists, create it if it doesn't.
    """
    config_dir = os.path.dirname(get_settings_config_path())
    if not os.path.exists(config_dir):
        os.makedirs(config_dir)


def save_config(config: Dict[str, Any]) -> bool:
    """
    Save configuration dictionary to JSON file.

    Args:
        config: Dictionary containing configuration data

    Returns:
        bool: True if save successful, False otherwise
    """
    file_path = get_settings_config_path()
    directory = os.path.dirname(os.path.abspath(file_path)) or "."
    temporary_file = None
    try:
        ensure_config_dir()
        fd, temporary_file = tempfile.mkstemp(
            prefix=".xal_settings_", suffix=".tmp", dir=directory
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_file, file_path)
        temporary_file = None
        return True
    except Exception:
        return False
    finally:
        if temporary_file and os.path.exists(temporary_file):
            try:
                os.remove(temporary_file)
            except OSError:
                pass


def save_json_atomic(
    data: Dict[str, Any],
    file_path: str,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> None:
    """Write JSON beside the target and replace it in one step."""
    directory = os.path.dirname(os.path.abspath(file_path)) or "."
    temporary_file = None
    try:
        os.makedirs(directory, exist_ok=True)
        fd, temporary_file = tempfile.mkstemp(
            prefix=".xal_json_", suffix=".tmp", dir=directory
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_file, file_path)
        temporary_file = None
    finally:
        if temporary_file and os.path.exists(temporary_file):
            try:
                os.remove(temporary_file)
            except OSError:
                pass


def save_yaml_config(config: Dict[str, Any], file_path: str) -> bool:
    """
    Save configuration dictionary to YAML file.

    Args:
        config: Dictionary containing configuration data
        file_path: Path to save the YAML file

    Returns:
        bool: True if save successful, False otherwise
    """
    directory = os.path.dirname(os.path.abspath(file_path)) or "."
    temporary_file = None
    try:
        os.makedirs(directory, exist_ok=True)
        fd, temporary_file = tempfile.mkstemp(
            prefix=".xal_yaml_", suffix=".tmp", dir=directory
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_file, file_path)
        temporary_file = None
        return True
    except Exception:
        return False
    finally:
        if temporary_file and os.path.exists(temporary_file):
            try:
                os.remove(temporary_file)
            except OSError:
                pass


def load_config() -> Dict[str, Any]:
    """
    Load configuration from default JSON config file.

    Returns:
        Dict: Configuration dictionary if successful, empty dict otherwise
    """
    try:
        settings_config_path = get_settings_config_path()
        if os.path.exists(settings_config_path):
            with open(settings_config_path, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def load_config_from_file(file_path: str) -> Dict[str, Any]:
    """
    Load configuration from specified JSON file.

    Args:
        file_path: Path to the JSON config file

    Returns:
        Dict: Configuration dictionary if successful, None otherwise
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_yaml_config(file_path: str) -> Dict[str, Any]:
    """
    Load configuration from YAML file.

    Args:
        file_path: Path to the YAML config file

    Returns:
        Dict: Configuration dictionary if successful, None otherwise
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception:
        return None
