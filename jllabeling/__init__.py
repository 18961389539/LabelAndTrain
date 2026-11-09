"""JLLabelingAndTrain package.

The GUI-facing exports are imported lazily so headless consumers -- the core
package, CLI helpers and tests -- can import ``jllabeling`` without pulling
PyQt6 into the process.
"""

from .app_info import __appdescription__, __appname__, __version__

__all__ = (
    "__version__",
    "__appname__",
    "__appdescription__",
    "checks",
    "convert",
    "list_supported_tasks",
    "SUPPORTED_TASKS",
)

_LAZY_EXPORTS = {
    "checks": ("jllabeling.views.common.checks", "run_checks"),
    "convert": ("jllabeling.views.common.converter", "run_conversion"),
    "list_supported_tasks": (
        "jllabeling.views.common.converter",
        "list_supported_tasks",
    ),
    "SUPPORTED_TASKS": (
        "jllabeling.views.common.converter",
        "SUPPORTED_TASKS",
    ),
}


def __getattr__(name):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module_name, attribute = target
    value = getattr(import_module(module_name), attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(__all__))
