"""The headless core must stay importable without PyQt6, and must not reach
back into the UI layer.

The first rule is checked in a fresh interpreter: the test process itself has
already imported Qt through the GUI tests, so ``sys.modules`` there says
nothing about what a CLI or a plain import would load.

The second rule is checked statically, on every module under
``jllabeling/core``.  Importing alone cannot see it -- a core module that
imports ``jllabeling.views`` still imports fine as long as PyQt is installed,
which on a developer machine it always is.  The arrow is meant to point one
way: UI code imports the core, never the other way round.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE_ROOT = REPO_ROOT / "jllabeling" / "core"

#: The GUI, and the toolkit it is built on.  A core module importing any of
#: these is no longer headless, whatever the import happens to pull in.
UI_PACKAGES = ("PyQt6", "PySide6", "jllabeling.views")


def _core_files():
    return sorted(CORE_ROOT.rglob("*.py"))


def _relative(path):
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def _module_name(path):
    parts = list(path.relative_to(REPO_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _package_of(path):
    """The package a relative import is resolved against."""
    module = _module_name(path)
    return module if path.name == "__init__.py" else module.rsplit(".", 1)[0]


def _resolve(path, node):
    """Absolute module name behind an ``ImportFrom`` node."""
    if not node.level:
        return node.module or ""
    parts = _package_of(path).split(".")
    steps = node.level - 1
    if steps > len(parts) - 1:
        # Walks past the top-level package, so the import cannot run at all.
        return ""
    for _ in range(steps):
        parts.pop()
    if node.module:
        parts.extend(node.module.split("."))
    return ".".join(parts)


def _join(prefix, name):
    return f"{prefix}.{name}" if prefix else name


def _imports(path):
    """Yield ``(imported module, line)`` for every import in ``path``.

    Covers ``import a.b``, ``from a import b`` and relative forms, including
    imports written inside a function.  Aliases are yielded both as written
    and as child modules, because ``from jllabeling import views`` imports
    ``jllabeling.views`` without ever naming it.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno
        elif isinstance(node, ast.ImportFrom):
            resolved = _resolve(path, node)
            if resolved:
                yield resolved, node.lineno
            for alias in node.names:
                yield _join(resolved, alias.name), node.lineno


def _is_ui(module):
    return any(
        module == pkg or module.startswith(pkg + ".") for pkg in UI_PACKAGES
    )


def _dynamic_imports(path):
    """Yield ``(module string, line)`` for literal ``import_module`` calls."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        func = node.func
        callee = getattr(func, "attr", None) or getattr(func, "id", "")
        if callee not in {"import_module", "__import__"}:
            continue
        argument = node.args[0]
        if isinstance(argument, ast.Constant) and isinstance(
            argument.value, str
        ):
            yield argument.value, node.lineno


def _run(code):
    completed = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("path", _core_files(), ids=_relative)
def test_core_module_does_not_import_the_ui_layer(path):
    offenders = [
        f"{_relative(path)}:{line} imports {module}"
        for module, line in _imports(path)
        if _is_ui(module)
    ]
    assert (
        offenders == []
    ), "the core must stay below the UI layer:\n" + "\n".join(offenders)


@pytest.mark.parametrize("path", _core_files(), ids=_relative)
def test_core_module_does_not_dynamic_import_the_ui_layer(path):
    offenders = [
        f"{_relative(path)}:{line} import_module({module!r})"
        for module, line in _dynamic_imports(path)
        if _is_ui(module)
    ]
    assert offenders == [], (
        "a dynamic import sidesteps the static scan, so these are checked "
        "by name:\n" + "\n".join(offenders)
    )


def test_every_core_module_imports_without_pyqt():
    names = [_module_name(path) for path in _core_files()]
    assert names, f"no modules found under {CORE_ROOT}"
    _run(
        "import importlib, sys\n"
        f"for name in {names!r}:\n"
        "    importlib.import_module(name)\n"
        "bad = [name for name in sys.modules if name.startswith('PyQt6')]\n"
        "assert not bad, bad\n"
    )


def test_top_level_package_stays_lazy():
    _run(
        "import sys; "
        "import jllabeling; "
        "bad=[name for name in sys.modules "
        "if name.startswith('PyQt6')]; "
        "assert not bad, bad"
    )
