"""The press list: what every key actually does on the live widget.

Ground truth comes from the QActions, not from the yaml -- the same three
layers that agree in tests can still disagree with what a keypress does, and
the one thing that only a real press can reveal (an IME or another app eating
the combo) needs a human who knows which key was *supposed* to fire.

Run it and hand the output to whoever sits at the machine:

    QT_QPA_PLATFORM=offscreen python -u scripts/shortcut_press_list.py \
        [--baseline <git-ref>]

``--baseline`` marks the keys that differ from that ref's template, so the
press list can put the new ones first -- those are the ones worth pressing.

Exit code is 0 when the widget's QActions agree with the template; a non-zero
exit means the press list would be describing keys that do not exist.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from PyQt6 import QtGui, QtWidgets  # noqa: E402

TEMPLATE = os.path.join(
    REPO, "anylabeling", "configs", "jllabeling_config.yaml"
)


def read_template():
    import yaml

    with open(TEMPLATE, encoding="utf-8") as handle:
        return yaml.safe_load(handle)["shortcuts"]


def read_baseline_shortcuts(ref):
    """The shortcuts table as it was at ``ref``, for the new-today marks."""
    # git's ref:path syntax wants forward slashes, os.path.relpath does not.
    rel = os.path.relpath(TEMPLATE, REPO).replace(os.sep, "/")
    out = subprocess.run(
        ["git", "show", f"{ref}:{rel}"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )
    import yaml

    return yaml.safe_load(out.stdout)["shortcuts"]


def build_widget():
    """The real widget, offscreen, on a copy of the template it may write."""
    from anylabeling import config as app_config
    from anylabeling.views.labeling.label_widget import LabelingWidget

    tmp = tempfile.mkdtemp(prefix="shortcut_press_list_")
    config_copy = os.path.join(tmp, "config.yaml")
    shutil.copy(TEMPLATE, config_copy)
    app_config.current_config_file = config_copy
    LabelingWidget.menu = lambda self, title: QtWidgets.QMenu(title)
    parent = QtWidgets.QFrame()
    widget = LabelingWidget(parent)
    widget.parent = type("P", (), {"parent": QtWidgets.QMainWindow()})()
    return widget, tmp


def collect(widget):
    """Everything a keypress can reach, from the QActions themselves.

    The applier's live map is the ground truth: it holds one QAction per
    template key, including the nine "hidden" ones whose actions are created
    on demand instead of sitting on ``widget.actions``. Returns ``(mapped,
    extra)`` -- ``mapped`` keyed by bare config name, ``extra`` holding any
    other action that carries a shortcut (the registered digit keys).
    """
    # The applier keys its map "shortcuts.X"; the template table and the F1
    # sheet use the bare name. Key everything here by the bare name.
    shortcut_map = widget._settings_runtime_applier._shortcut_action_map
    mapped, extra = {}, []
    seen = set()
    for config_key, action in sorted(shortcut_map.items()):
        shortcuts = [s.toString() for s in action.shortcuts()]
        mapped[config_key.split(".", 1)[1]] = (config_key, action, shortcuts)
        seen.add(id(action))

    # ``widget.actions`` is the Struct of named actions, which shadows
    # QWidget.actions(); the unbound method still reaches the addAction list.
    for action in QtWidgets.QWidget.actions(widget):
        if id(action) in seen:
            continue
        shortcuts = [s.toString() for s in action.shortcuts()]
        if shortcuts:
            extra.append((action.text() or action.iconText(), shortcuts))
    return mapped, extra


def qseq(value):
    """A template value, normalised the way Qt would read it."""
    if value in (None, "", [], [None]):
        return []
    entries = value if isinstance(value, list) else [value]
    return [
        QtGui.QKeySequence(str(entry)).toString() for entry in entries if entry
    ]


def section_new_keys(lines, mapped, template, baseline, f1_names):
    """The keys worth pressing: whatever differs from the baseline."""
    new_keys = [k for k in mapped if baseline.get(k) != template.get(k)]
    lines.append(f"## 一、今天新增/变更的键位（{len(new_keys)} 条，重点逐按）")
    lines.append("")
    lines.append("| # | 按键 | 动作 | 按后预期 | 未开图状态 |")
    lines.append("|---|---|---|---|---|")
    for index, name in enumerate(new_keys, 1):
        _key, action, shortcuts = mapped[name]
        enabled = "灰的（开图后才有）" if not action.isEnabled() else "可用"
        keys = (
            " / ".join(shortcuts) if shortcuts else "（无默认键，去设置页绑）"
        )
        label = f1_names.get(name) or action.text()
        lines.append(
            f"| {index} | `{keys}` | {label} | 触发与菜单同名的那一项 | {enabled} |"
        )
    lines.append("")


def section_f1_sheet(lines, mapped, template, unbound_names):
    """Every F1 row, checked against the live QAction while it is printed."""
    from anylabeling.views.labeling.utils.shortcuts_help import SHORTCUT_GROUPS

    mismatches = []
    for group_title, entries in SHORTCUT_GROUPS:
        rows = []
        for name, description in entries:
            if name in unbound_names:
                continue
            _key, action, shortcuts = mapped.get(name, ("", None, []))
            if action is None:
                mismatches.append(f"{name}: 不在 runtime 映射里")
                continue
            if sorted(qseq(template.get(name))) != sorted(shortcuts):
                mismatches.append(
                    f"{name}: 模板 {qseq(template.get(name))} != QAction {shortcuts}"
                )
            state = "灰的（开图后才有）" if not action.isEnabled() else "可用"
            keys = " / ".join(shortcuts) if shortcuts else "（无默认键）"
            rows.append(f"| `{keys}` | {description} | {state} |")
        if rows:
            lines.append(f"### {group_title}")
            lines.append("")
            lines.append("| 按键 | 动作 | 未开图状态 |")
            lines.append("|---|---|---|")
            lines.extend(rows)
            lines.append("")
    return mismatches


def section_digits(lines, widget):
    """What 1-9/0 do right now, and how to exercise the cold-start path."""
    lines.append("## 三、数字键 1-9 / 0（画第一个框的路径）")
    lines.append("")
    digit_table = getattr(widget, "drawing_digit_shortcuts", None) or {}
    if not digit_table:
        lines.append(
            "当前工程没有已分配的数字键（未开项目或项目未声明标签）。"
        )
        lines.append("")
        lines.append(
            "**真机按法**：打开一个声明过标签的图片文件夹，标签会按声明"
        )
        lines.append(
            "顺序自动占 1-9 然后 0；之后**不选中任何东西**直接按数字，应以"
        )
        lines.append(
            "对应标签进入绘制状态。这是冷启动修复（`5e55493`）要验的那一步。"
        )
    else:
        lines.append("| 数字 | 标签 | 模式 |")
        lines.append("|---|---|---|")
        for digit, data in sorted(digit_table.items()):
            lines.append(
                f"| {digit} | {data.get('label')} | {data.get('mode')} |"
            )
    lines.append("")


def section_unbound(lines, mapped):
    """The declared-keyless actions, re-checked against their QActions."""
    from anylabeling.views.labeling.utils.shortcuts_help import UNBOUND_ACTIONS

    mismatches = []
    lines.append("## 四、有意无默认键的动作（按了没反应是预期）")
    lines.append("")
    lines.append("| 动作 | 怎么到它 |")
    lines.append("|---|---|")
    for name, description in UNBOUND_ACTIONS:
        _key, action, shortcuts = mapped.get(name, ("", None, []))
        if action is not None and shortcuts:
            mismatches.append(
                f"{name}: 声明无默认键但 QAction 带着 {shortcuts}"
            )
        lines.append(f"| {description} | 菜单（或在设置页给它绑键） |")
    lines.append("")
    return mismatches


def section_notes(lines):
    """How to tell "the key was eaten" from "the feature is broken"."""
    lines.append("## 五、怎么判断一个键被截胡了")
    lines.append("")
    lines.append(
        "1. 按下后**菜单里同名那一项没有触发**，也没有任何弹出/画布变化；"
    )
    lines.append("2. 换到菜单里手动点同一项，功能本身是好的；")
    lines.append("3. 两条同时成立 ≈ 按键被输入法或别的程序吃掉了——去")
    lines.append(
        "   **设置 → 快捷键** 把这个键改成别的组合（改完立即生效，不用重启）。"
    )
    lines.append("")
    lines.append(
        "已知要留意的组合：`Ctrl+Alt+1/2/3`（部分输入法的数字候选/自定义短语）、"
    )
    lines.append("`Ctrl+Alt+D`（个别显卡/截图工具的热键）、裸字母 `Q`/`X`/`Y`")
    lines.append(
        "（只在画布有焦点时生效，在文本框里按会正常输入字符——这是既有行为）。"
    )
    lines.append("")


def section_extra(lines, extra):
    """Actions wired in code rather than through the template."""
    if not extra:
        return
    lines.append("## 六、带键但不走模板的动作（代码里直接注册的）")
    lines.append("")
    lines.append("| 按键 | 动作 |")
    lines.append("|---|---|")
    for label, shortcuts in extra:
        lines.append(f"| {' / '.join(shortcuts)} | {label} |")
    lines.append("")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--baseline",
        help="git ref to diff the template against; those keys are the new ones",
    )
    args = parser.parse_args()

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    widget, tmp = build_widget()
    app.processEvents()
    template = widget._config["shortcuts"]
    mapped, extra = collect(widget)
    baseline = (
        read_baseline_shortcuts(args.baseline) if args.baseline else template
    )

    from anylabeling.views.labeling.utils.shortcuts_help import UNBOUND_ACTIONS

    f1_names = {
        name: description
        for _title, entries in _shortcut_groups()
        for name, description in entries
    }
    lines = []
    lines.append("# 键位逐按清单")
    lines.append("")
    lines.append(
        f"生成于 {date.today().isoformat()}，数据来自 offscreen 真 widget 上的"
        " `QAction.shortcuts()`，不是抄配置。"
    )
    if args.baseline:
        lines.append(f"基线：`{args.baseline}`（与它不同的键集中在第一节）。")
    lines.append("")
    lines.append(
        "按法：在**画布有焦点**的状态下按键（不是在文本框里）。一节按完打一个勾；"
    )
    lines.append(
        "「按了没反应」先看该行的 *未开图状态* 列——灰的就需要先开一个项目，再按一次。"
    )
    lines.append("")

    section_new_keys(lines, mapped, template, baseline, f1_names)
    mismatches = section_f1_sheet(
        lines, mapped, template, {k for k, _d in UNBOUND_ACTIONS}
    )
    section_digits(lines, widget)
    mismatches += section_unbound(lines, mapped)
    section_notes(lines)
    section_extra(lines, extra)

    if mismatches:
        print("MISMATCHES:", file=sys.stderr)
        for item in mismatches:
            print(f"  {item}", file=sys.stderr)
        return 1

    print("\n".join(lines))
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


def _shortcut_groups():
    from anylabeling.views.labeling.utils.shortcuts_help import SHORTCUT_GROUPS

    return SHORTCUT_GROUPS


if __name__ == "__main__":
    sys.exit(main())
