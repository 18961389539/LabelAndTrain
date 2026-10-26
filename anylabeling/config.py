import functools
import os
import os.path as osp
import shutil
import copy
import tempfile
from datetime import datetime

import yaml
import importlib.resources as pkg_resources

from anylabeling import configs as anylabeling_configs
from anylabeling.views.labeling.logger import logger

current_config_file = None
_work_directory = None
#: Details of the last unreadable config file, for the startup dialog.
_config_load_warning = None
_LEGACY_KEY_MAP = {
    "epsilon": "canvas.epsilon",
    "show_cross_line": "canvas.crosshair.show",
}
_LEGACY_DROP_KEYS = {"ui"}


def set_work_directory(directory: str) -> None:
    """
    Sets the working directory for JLLabelingAndTrain.

    Args:
        directory (str): The path to the working directory.
    """
    global _work_directory
    _work_directory = osp.abspath(osp.expanduser(directory))


def get_work_directory() -> str:
    """
    Gets the working directory for JLLabelingAndTrain.

    Returns:
        str: The absolute path to the working directory.
    """
    if _work_directory is None:
        return osp.expanduser("~")
    return _work_directory


def update_dict(target_dict, new_dict, validate_item=None):
    for key, value in new_dict.items():
        if validate_item:
            validate_item(key, value)
        if key not in target_dict:
            logger.warning(f"Skipping unexpected key in config: {key}")
            continue
        if isinstance(target_dict[key], dict) and isinstance(value, dict):
            update_dict(target_dict[key], value, validate_item=validate_item)
        else:
            target_dict[key] = value


def _set_nested_value(target_dict, key_path, value):
    parts = key_path.split(".")
    current = target_dict
    for part in parts[:-1]:
        node = current.get(part)
        if not isinstance(node, dict):
            node = {}
            current[part] = node
        current = node
    current[parts[-1]] = value


def _has_nested_key(target_dict, key_path):
    current = target_dict
    for part in key_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def _get_nested_value(target_dict, key_path):
    current = target_dict
    for part in key_path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


# Shipped-default changes, keyed by the template config_version they
# belong to. Each entry is (dotted key, old default, new default) and is
# only applied when the user's rc still carries the old default -- a
# value the user deliberately changed is never overwritten. Bump
# config_version in jllabeling_config.yaml when adding a rule.
_MIGRATIONS = {
    1: [
        ("canvas.num_backups", 10, 100),
    ],
    # v2: digit shortcuts ship enabled. ``null`` used to be the shipped
    # default, which silently left the 0-9 keys dead -- an annotator got no
    # hint that auto-assign (or Alt+D) even existed. Only an rc still
    # carrying that untouched default is flipped; a deliberately configured
    # map is never overwritten, and once the rc is stamped version 2 a
    # hand-edited ``null`` (the "off" switch) survives future loads.
    2: [
        ("digit_shortcuts", None, {}),
    ],
}


def _apply_config_migrations(user_config):
    """Bring an rc dict up to the template's config_version in place."""
    target = _load_template_config().get("config_version", 1)
    current = user_config.get("config_version", 0)
    for version in sorted(_MIGRATIONS):
        if version <= current or version > target:
            continue
        for key_path, old_value, new_value in _MIGRATIONS[version]:
            if (
                _has_nested_key(user_config, key_path)
                and _get_nested_value(user_config, key_path) == old_value
            ):
                _set_nested_value(user_config, key_path, new_value)
    user_config["config_version"] = target
    return user_config


def _normalize_shortcut_value(value):
    if value in (None, ""):
        return None
    if isinstance(value, (list, tuple)):
        values = [item for item in value if item not in (None, "")]
        if not values:
            return None
        value = values[0]
    text = str(value).strip()
    return text or None


def _normalize_multi_shortcut_value(value):
    if value in (None, ""):
        return []
    if isinstance(value, (list, tuple)):
        raw_values = [item for item in value if item not in (None, "")]
    else:
        raw_values = [value]
    normalized = []
    for item in raw_values:
        text = str(item).strip()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def normalize_user_config(config):
    if not isinstance(config, dict):
        return config
    normalized = copy.deepcopy(config)
    for key, target_path in _LEGACY_KEY_MAP.items():
        if key in normalized:
            value = normalized.pop(key)
            if not _has_nested_key(normalized, target_path):
                _set_nested_value(normalized, target_path, value)
    for key in _LEGACY_DROP_KEYS:
        normalized.pop(key, None)
    shortcuts = normalized.get("shortcuts")
    if isinstance(shortcuts, dict):
        for key, value in list(shortcuts.items()):
            if key == "zoom_in":
                shortcuts[key] = _normalize_multi_shortcut_value(value)
            else:
                shortcuts[key] = _normalize_shortcut_value(value)
    return normalized


def _backup_unreadable_config(path):
    """Move the broken file aside so its contents are not lost."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{path}.invalid-{stamp}"
    if osp.exists(backup):
        backup = f"{path}.invalid-{stamp}-{os.getpid()}"
    try:
        os.replace(path, backup)
        return backup
    except OSError:
        pass
    try:
        shutil.copyfile(path, backup)
        return backup
    except OSError:
        return None


def _record_config_load_warning(path, error):
    global _config_load_warning, current_config_file
    backup = _backup_unreadable_config(path)
    _config_load_warning = {
        "path": osp.abspath(path),
        "error": str(error),
        "backup": backup,
    }
    if current_config_file and osp.abspath(current_config_file) == osp.abspath(
        path
    ):
        # The file is gone (or unusable); do not try to load it again on
        # the next get_config() call, and let save_config() fall back to
        # the default rc file.
        current_config_file = None
    summary = (
        str(error).splitlines()[0] if str(error) else type(error).__name__
    )
    logger.error(
        f"Ignoring unreadable config {path}: {summary}. "
        f"Starting from defaults; original kept at {backup or 'nowhere'}."
    )


def take_config_load_warning():
    """Return and clear the details of the last unreadable config."""
    global _config_load_warning
    warning = _config_load_warning
    _config_load_warning = None
    return warning


def _load_user_config(config_file_or_yaml):
    """Parse user config from inline YAML or a file path; never raise on
    a corrupt *file*.

    A config file that cannot be parsed used to abort startup with an
    unhandled traceback (an empty file crashed on ``None.get``, a typo
    raised ``ParserError``). The annotations are safe, but the app could
    not open at all until the file was fixed by hand. Falling back to the
    template keeps the app usable; the broken file is moved aside so the
    user can still inspect or repair it.
    """
    if not config_file_or_yaml:
        return {}

    try:
        parsed = yaml.safe_load(config_file_or_yaml)
    except yaml.YAMLError:
        parsed = None
    if isinstance(parsed, dict):
        return parsed

    path = str(config_file_or_yaml)
    try:
        with open(path, encoding="utf-8-sig") as f:
            content = f.read()
    except FileNotFoundError:
        # An explicitly requested config that does not exist is a real
        # error; the startup crash dialog explains it.
        raise
    except (OSError, UnicodeDecodeError) as exc:
        _record_config_load_warning(path, exc)
        return {}

    if not content.strip():
        return {}
    try:
        loaded = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        _record_config_load_warning(path, exc)
        return {}
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        _record_config_load_warning(
            path,
            ValueError(f"expected a mapping, got {type(loaded).__name__}"),
        )
        return {}
    return loaded


def _write_yaml_atomic(file_path, data):
    """Write YAML beside the target, then replace it in one step.

    A crash or full disk mid-dump used to leave a truncated rc, which
    then crashed the next startup. Raises ``OSError`` when the write
    fails; the old file is untouched in that case.
    """
    directory = osp.dirname(file_path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, temporary_file = tempfile.mkstemp(
        prefix=".xanylabelingrc_", suffix=".tmp", dir=directory
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, allow_unicode=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary_file, file_path)
        temporary_file = None
    finally:
        if temporary_file and osp.exists(temporary_file):
            try:
                os.remove(temporary_file)
            except OSError:
                pass


def _is_shipped_template(path):
    """True when ``path`` is the bundled defaults file, not a user config."""
    try:
        template = pkg_resources.files(anylabeling_configs) / (
            "jllabeling_config.yaml"
        )
        return osp.normcase(osp.realpath(str(template))) == osp.normcase(
            osp.realpath(path)
        )
    except Exception:  # noqa
        return False


def save_config(config):
    # Write back to the file the session loaded from (a --config path) so
    # reads and writes stay symmetric; inline YAML strings and the default
    # startup path (None) fall through to the work-directory rc file.
    if current_config_file and osp.isfile(current_config_file):
        if _is_shipped_template(current_config_file):
            # The template is the shipped default, not a user config.
            # Writing it back turned a settings change into a permanent
            # edit of the install (and, in tests, poisoned every later
            # run); the work-directory rc is the right destination.
            logger.error(
                "Refusing to overwrite the bundled default config; "
                "saving to the work-directory rc instead."
            )
            user_config_file = osp.join(
                get_work_directory(), ".xanylabelingrc"
            )
        else:
            user_config_file = current_config_file
    else:
        user_config_file = osp.join(get_work_directory(), ".xanylabelingrc")
    try:
        _write_yaml_atomic(user_config_file, config)
        return True
    except Exception:  # noqa
        logger.exception(f"Failed to save config: {user_config_file}")
        return False


@functools.lru_cache(maxsize=1)
def _load_template_config():
    """Parse the bundled template yaml once per process.

    get_config() is called from ~34 places, every one of which used to
    re-read and re-parse the static template. Callers get a deep copy,
    so the cached dict is never mutated.
    """
    config_file = "jllabeling_config.yaml"
    with pkg_resources.open_text(anylabeling_configs, config_file) as f:
        return yaml.safe_load(f)


def get_default_config():
    work_dir = get_work_directory()
    old_cfg_file = osp.join(work_dir, ".anylabelingrc")
    new_cfg_file = osp.join(work_dir, ".xanylabelingrc")
    if osp.exists(old_cfg_file) and not osp.exists(new_cfg_file):
        try:
            shutil.copyfile(old_cfg_file, new_cfg_file)
        except Exception as e:  # noqa
            logger.warning(
                f"Failed to migrate legacy config: {old_cfg_file}: {e}"
            )

    config = copy.deepcopy(_load_template_config())

    if not osp.exists(new_cfg_file):
        # Write the work-directory rc only. save_config() honours
        # --config, which may point at a user-authored file: seeding the
        # defaults through it used to overwrite that file on a machine
        # whose work directory had no rc yet.
        try:
            _write_yaml_atomic(new_cfg_file, config)
        except Exception:  # noqa
            logger.exception(
                f"Failed to create the default config: {new_cfg_file}"
            )

    return config


def validate_config_item(key, value):
    if (
        key == "font_family"
        and value is not None
        and (not isinstance(value, str) or not value.strip())
    ):
        raise ValueError(
            f"Unexpected value for config key 'font_family': {value}"
        )
    if key == "validate_label" and value not in [None, "exact"]:
        raise ValueError(
            f"Unexpected value for config key 'validate_label': {value}"
        )
    if key == "qt_image_allocation_limit" and value is not None:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(
                "Unexpected value for config key "
                f"'qt_image_allocation_limit': {value}"
            )
    if key == "shape_color" and value not in [None, "auto", "manual"]:
        raise ValueError(
            f"Unexpected value for config key 'shape_color': {value}"
        )
    if key == "labels" and value is not None and len(value) != len(set(value)):
        raise ValueError(
            f"Duplicates are detected for config key 'labels': {value}"
        )


def get_config(
    config_file_or_yaml=None, config_from_args=None, show_msg=False
):
    # 1. Load default configuration
    config = get_default_config()

    # 2. Load configuration from file or YAML string
    if not config_file_or_yaml:
        config_file_or_yaml = current_config_file

    config_from_yaml = normalize_user_config(
        _load_user_config(config_file_or_yaml)
    )
    _apply_config_migrations(config_from_yaml)
    update_dict(config, config_from_yaml, validate_item=validate_config_item)
    if show_msg:
        logger.info(
            f"🔧️ Initializing config from local file: {config_file_or_yaml}"
        )

    # 3. Update configuration with command line arguments
    if config_from_args:
        config_from_args = normalize_user_config(config_from_args)
        update_dict(
            config, config_from_args, validate_item=validate_config_item
        )
        if show_msg:
            logger.info(
                f"🔄 Updated config from CLI arguments: {config_from_args}"
            )

    return config
