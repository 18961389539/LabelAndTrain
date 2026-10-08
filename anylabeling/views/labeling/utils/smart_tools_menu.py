"""The 智能工具 menu, grouped instead of twelve flat entries.

The tools grew into one flat list -- the overview audit plus items
numbered 1..11 -- which is a list nobody reads to the end. The numbers
are what the docs and the F1 sheet refer to, so they stay; the entries
are now spread over three submenus, and this module is the one place
that knows the grouping.
"""

from PyQt6.QtCore import QCoreApplication

from .qt import add_actions

#: Submenu title and the action names it owns, in display order.
SMART_TOOL_GROUPS = (
    (
        "检查与诊断",
        (
            "data_audit",
            "smart_calibrate",
            "smart_analysis",
            "smart_missing_scan",
            "smart_stale_audit",
        ),
    ),
    (
        "复核与建议",
        (
            "smart_iteration",
            "smart_review",
            "smart_propagate",
            "smart_advice",
        ),
    ),
    (
        "批量与恢复",
        (
            "smart_archive",
            "smart_template",
            "smart_restore_backup",
        ),
    ),
)


def populate_smart_tools_menu(menu, actions):
    """Fill ``menu`` with the three submenus and their tools.

    ``actions`` is the widget's actions namespace. A name it does not
    carry is skipped rather than crashing the menu build, which is what
    keeps light test stubs usable.
    """
    for title, names in SMART_TOOL_GROUPS:
        submenu = menu.addMenu(
            QCoreApplication.translate("LabelingWidget", title)
        )
        add_actions(
            submenu,
            tuple(
                found
                for found in (getattr(actions, name, None) for name in names)
                if found is not None
            ),
        )
    return menu
