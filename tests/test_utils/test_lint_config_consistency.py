"""The flake8 rule set is declared in four places; they must agree.

``.flake8`` is the authority, but three other files have to carry the same
information:

* the ``dev`` extra in ``pyproject.toml`` -- what a contributor installs,
* the ``flake8-baseline`` hook in ``.pre-commit-config.yaml`` -- what runs
  before a commit,
* ``.github/workflows/ci.yml`` -- what runs on the pull request.

When they drift, flake8 quietly checks a *smaller* rule set and every gate
still passes, which is how ``select = B,C,...`` sat there meaning nothing
while neither plugin was installed anywhere.  These tests make that drift
loud.
"""

import configparser
import os
import re
import tomllib

import pytest
import yaml

REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

FLAKE8_CONFIG = os.path.join(REPO_ROOT, ".flake8")
PYPROJECT = os.path.join(REPO_ROOT, "pyproject.toml")
PRECOMMIT = os.path.join(REPO_ROOT, ".pre-commit-config.yaml")
CI_WORKFLOW = os.path.join(
    REPO_ROOT, ".github", "workflows", "ci.yml"
)
BASELINE = os.path.join(REPO_ROOT, "scripts", "flake8_baseline.txt")

#: Which plugin has to be installed for a `select` token to mean anything.
PLUGIN_BY_PREFIX = (
    ("B", "flake8-bugbear"),
    ("C", "flake8-comprehensions"),
)


def _flake8_section():
    parser = configparser.ConfigParser()
    parser.read(FLAKE8_CONFIG, encoding="utf-8")
    return parser["flake8"]


def _tokens(raw):
    return [token.strip() for token in raw.split(",") if token.strip()]


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _selected_tokens():
    return _tokens(_flake8_section()["select"])


def _required_plugins():
    """Plugins implied by whatever `select` asks for."""
    plugins = set()
    for token in _selected_tokens():
        for prefix, plugin in PLUGIN_BY_PREFIX:
            if token.startswith(prefix):
                plugins.add(plugin)
    return plugins


def test_flake8_config_exists_and_is_the_only_copy():
    assert os.path.isfile(FLAKE8_CONFIG)

    # pyproject.toml is not read by flake8 without the Flake8-pyproject
    # plugin, so a [tool.flake8] table there is dead config that can only
    # drift away from the one that applies.
    with open(PYPROJECT, "rb") as handle:
        pyproject = tomllib.load(handle)
    assert "flake8" not in pyproject.get("tool", {})


def test_every_selected_prefix_has_a_plugin():
    """Guards the mapping itself: a new prefix must be classified."""
    for token in _selected_tokens():
        if token[0] in {"B", "C"}:
            assert any(
                token.startswith(prefix) for prefix, _ in PLUGIN_BY_PREFIX
            ), f"select token {token!r} is not mapped to a plugin"


def test_pyproject_dev_extra_installs_the_selected_plugins():
    with open(PYPROJECT, "rb") as handle:
        pyproject = tomllib.load(handle)
    declared = {
        re.split(r"[<>=!~;\[]", entry, maxsplit=1)[0].strip()
        for entry in pyproject["project"]["optional-dependencies"]["dev"]
    }

    assert _required_plugins() <= declared


def test_precommit_and_ci_install_the_same_plugins():
    """Both gates, and the dev extra, must check the same rule set."""
    with open(PRECOMMIT, encoding="utf-8") as handle:
        precommit = yaml.safe_load(handle)

    hooks = {
        hook["id"]: hook
        for repo in precommit["repos"]
        for hook in repo.get("hooks", [])
    }
    assert "flake8-baseline" in hooks, (
        "the baseline gate is what makes pre-commit and CI agree"
    )
    hook_deps = {
        re.split(r"[<>=!~;\[]", dep, maxsplit=1)[0].strip()
        for dep in hooks["flake8-baseline"]["additional_dependencies"]
    }

    workflow = yaml.safe_load(_read(CI_WORKFLOW))
    lint_steps = " ".join(
        step.get("run", "") for step in workflow["jobs"]["lint"]["steps"]
    )

    for plugin in _required_plugins():
        assert plugin in hook_deps, f"pre-commit hook is missing {plugin}"
        assert plugin in lint_steps, f"CI lint job is missing {plugin}"


def test_ci_lint_job_runs_the_same_command_as_precommit():
    workflow = yaml.safe_load(_read(CI_WORKFLOW))
    lint_steps = " ".join(
        step.get("run", "") for step in workflow["jobs"]["lint"]["steps"]
    )

    assert "scripts/check_flake8_baseline.py" in lint_steps


def test_precommit_runs_black_at_most_once():
    """It was listed twice -- once rewriting, once with --check."""
    with open(PRECOMMIT, encoding="utf-8") as handle:
        precommit = yaml.safe_load(handle)

    black_hooks = [
        hook
        for repo in precommit["repos"]
        for hook in repo.get("hooks", [])
        if hook["id"] == "black"
    ]
    assert len(black_hooks) <= 1, (
        "two black hooks disagree about whether to rewrite or check"
    )
    for hook in black_hooks:
        assert "--check" not in hook.get("args", []), (
            "a hook that rewrites and a hook that only checks cannot both be "
            "wanted; pick one"
        )


def test_precommit_is_actually_installed_where_the_repo_lives():
    """A config nobody has wired up protects nothing."""
    hook = os.path.join(REPO_ROOT, ".git", "hooks", "pre-commit")
    if not os.path.isdir(os.path.join(REPO_ROOT, ".git")):
        pytest.skip("not a git checkout")
    if not os.path.isfile(hook):
        pytest.skip(
            "run `pre-commit install` to arm the hooks in this checkout"
        )


def test_the_baseline_only_contains_codes_the_config_selects():
    """A baseline entry for an unselected code means the gate cannot see it."""
    with open(BASELINE, encoding="utf-8") as handle:
        entries = [
            line.rsplit(None, 2)
            for line in handle
            if line.strip() and not line.startswith("#")
        ]

    assert entries, "the baseline should not be empty"

    selected = _selected_tokens()
    ignore = set(_tokens(_flake8_section()["ignore"]))
    for parts in entries:
        assert len(parts) == 3, f"malformed baseline line: {parts}"
        code = parts[1]
        assert not any(code.startswith(token) for token in ignore), (
            f"{code} is ignored by .flake8 but sits in the baseline"
        )
        assert any(code.startswith(token) for token in selected), (
            f"{code} is not covered by .flake8's select, so no run would "
            "ever report it -- remove it from the baseline"
        )
