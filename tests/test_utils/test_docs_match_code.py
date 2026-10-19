"""The counts the documentation states about this build, checked against code.

The docs keep drifting from the product: `model_zoo.md` said "this build is
YOLO-only" while the two models it actually ships are SAM2, and the quick-start
page advertised seven advanced features of which this build has two. Both were
catchable by arithmetic -- the repository knows how many model types it can
load and how many built-in configs it ships, and the pages quote those numbers.

So the numbers are no longer allowed to be prose.
"""

import io
import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]

_WORDS = {
    1: "one",
    2: "two",
    3: "three",
    4: "four",
    5: "five",
    6: "six",
    7: "seven",
    8: "eight",
    9: "nine",
    10: "ten",
}


def _loadable_type_count():
    from anylabeling.services.auto_labeling import _CUSTOM_MODELS

    return len(_CUSTOM_MODELS)


def _builtin_config_count():
    path = REPO / "anylabeling" / "configs" / "models.yaml"
    return len(yaml.safe_load(io.open(path, encoding="utf-8").read()))


def _text(relative):
    return io.open(REPO / relative, encoding="utf-8", errors="replace").read()


def _states(text, number, pattern):
    """True when the page writes `number` in the form `pattern` describes."""
    digits = pattern.format(n=str(number))
    if re.search(digits, text):
        return True
    spelled = pattern.format(n=_WORDS.get(number, ""))
    return bool(re.search(spelled, text))


def test_the_code_side_of_the_comparison_is_sane():
    """A zero from the code side would let any claim pass."""
    assert _loadable_type_count() >= 5
    assert _builtin_config_count() >= 1


def test_readme_states_the_real_number_of_loadable_model_types():
    types = _loadable_type_count()
    configs = _builtin_config_count()
    for relative, type_pattern, config_pattern in (
        (
            "README.md",
            r"\*\*{n} loadable model types\*\*",
            r"\*\*{n}\*\* built-in config",
        ),
        (
            "README_zh-CN.md",
            r"{n} 种可加载模型类型",
            r"内置配置文件只有 \*\*{n} 个\*\*",
        ),
    ):
        text = _text(relative)
        assert _states(text, types, type_pattern), (
            f"{relative} no longer says {types} loadable model types -- either "
            f"the build changed or the page drifted."
        )
        assert _states(text, configs, config_pattern), (
            f"{relative} no longer matches configs/models.yaml ({configs} "
            f"entries)."
        )


def test_the_archived_zoo_pages_quote_the_same_numbers():
    types = _loadable_type_count()
    configs = _builtin_config_count()
    for relative, type_pattern, config_pattern in (
        (
            "docs/en/model_zoo.md",
            r"{n} model types",
            r"{n}\*\*?\s*built-in config",
        ),
        ("docs/zh_cn/model_zoo.md", r"{n} 种模型类型", r"{n} 个"),
    ):
        text = _text(relative)
        assert _states(
            text, types, type_pattern
        ), f"{relative}: the banner should quote {types} loadable model types."
        assert _states(
            text, configs, config_pattern
        ), f"{relative}: the banner should quote {configs} built-in configs."


def test_the_model_selection_pages_do_not_call_this_build_yolo_only():
    """ "YOLO-only" is the fork's shorthand, and on the pages whose whole job is
    "which models can I load" it is wrong in the one direction that matters:
    the two configs this build ships are SAM2, so the sentence talked a reader
    out of the feature they actually have. Kept as shorthand elsewhere
    (FORK_POLICY, the archived task-panel banners), asserted away here."""
    surfaces = [
        "README.md",
        "README_zh-CN.md",
        "docs/en/model_zoo.md",
        "docs/zh_cn/model_zoo.md",
        "docs/en/get_started.md",
        "docs/zh_cn/get_started.md",
    ]
    offenders = [
        relative
        for relative in surfaces
        if re.search(r"YOLO[- ]only", _text(relative), re.I)
    ]
    assert offenders == [], f"stale 'YOLO-only' claim in {offenders}"
