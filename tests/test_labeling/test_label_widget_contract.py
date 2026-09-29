"""The widget contract is locked from both sides.

``label_widget_contract.CONTRACT_MEMBERS`` is the set of widget members
the extracted modules touch.  These tests keep that set equal to
reality: a module reaching for a new member without declaring it fails,
a contract entry whose member vanished from the widget fails, and every
declared member must actually exist on ``LabelingWidget`` (found either
as a method, a class attribute, or an ``__init__`` assignment -- by AST,
so nothing needs instantiating).
"""

import ast
import os
import unittest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

LABEL_WIDGET = os.path.join(
    REPO_ROOT, "anylabeling", "views", "labeling", "label_widget.py"
)
CONTRACT = os.path.join(
    REPO_ROOT, "anylabeling", "views", "labeling", "label_widget_contract.py"
)

#: The modules the split batches extracted -- every widget-first function
#: in them takes the whole widget as its first parameter.
EXTRACTED_MODULES = [
    os.path.join(REPO_ROOT, "anylabeling", "views", "labeling", "utils", name)
    for name in (
        "file_lifecycle.py",
        "file_navigation.py",
        "file_list_ops.py",
        "label_editing.py",
        "panel_visibility.py",
    )
]


def _widget_reference_face():
    """Every ``widget.X`` the extracted modules touch, as a set."""
    face = set()
    for path in EXTRACTED_MODULES:
        tree = ast.parse(open(path, encoding="utf-8").read())
        for fn in tree.body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            args = fn.args.args
            if not args or args[0].arg != "widget":
                continue
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Attribute)
                    and isinstance(node.value, ast.Name)
                    and node.value.id == "widget"
                ):
                    face.add(node.attr)
    return face


def _widget_class_members():  # noqa: C901 -- collects every binding form
    """Every member that exists on LabelingWidget: method definitions,
    class-level names, ``self.X = ...`` assignments anywhere in the
    class body, ``widget.X = ...`` assignments in the module-level
    assembly helpers (``_build_actions`` / ``_build_layout`` set up half
    the UI since split batch 4), and ``widget.X = ...`` in the extracted
    modules themselves (some own their scratch state, e.g.
    ``widget._syncing_file_item``)."""
    members = set()
    tree = ast.parse(open(LABEL_WIDGET, encoding="utf-8").read())

    def collect_assigns(node, receiver=None):
        for child in ast.walk(node):
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Attribute) and isinstance(
                        target.value, ast.Name
                    ):
                        if receiver is None or target.value.id == receiver:
                            members.add(target.attr)
            elif isinstance(child, ast.AnnAssign):
                target = child.target
                if isinstance(target, ast.Attribute) and isinstance(
                    target.value, ast.Name
                ):
                    if receiver is None or target.value.id == receiver:
                        members.add(target.attr)

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "LabelingWidget":
            for child in ast.walk(node):
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    members.add(child.name)
                elif isinstance(child, ast.Name) and isinstance(
                    child.ctx, ast.Store
                ):
                    members.add(child.id)
            collect_assigns(node)
        elif isinstance(node, ast.FunctionDef):
            # module-level assembly helpers: they only count as widget
            # members if they assign to their first parameter
            args = node.args.args
            if not args:
                continue
            collect_assigns(node, receiver=args[0].arg)

    # extracted modules may own scratch state on the widget
    # (file_list_ops sets widget._file_sort_mode / ._syncing_file_item)
    for path in EXTRACTED_MODULES:
        ext_tree = ast.parse(open(path, encoding="utf-8").read())
        for node in ext_tree.body:
            if isinstance(node, ast.FunctionDef):
                args = node.args.args
                if args and args[0].arg == "widget":
                    collect_assigns(node, receiver="widget")
    return members


def _member_exists_on_widget(name):
    """AST-visible members are already proven; names that survive to this
    check are inherited (e.g. QWidget.fontMetrics), so fall back to a
    runtime getattr on the class."""
    if name in _widget_class_members():
        return True
    from anylabeling.views.labeling.label_widget import LabelingWidget

    return hasattr(LabelingWidget, name)


def _contract_members():
    namespace = {}
    exec(open(CONTRACT, encoding="utf-8").read(), namespace)
    return set(namespace["CONTRACT_MEMBERS"])


class TestLabelWidgetContract(unittest.TestCase):
    def test_reference_face_is_exactly_the_contract(self):
        face = _widget_reference_face()
        contract = _contract_members()
        self.assertEqual(
            face - contract,
            set(),
            "a module touches a widget member that is not in the "
            "contract -- declare it in label_widget_contract.py, and "
            "ask yourself whether it belongs in the slice being "
            "extracted next",
        )
        self.assertEqual(
            contract - face,
            set(),
            "the contract declares members no module touches anymore "
            "-- remove them from label_widget_contract.py",
        )

    def test_every_contract_member_exists_on_the_widget(self):
        missing = sorted(
            name
            for name in _contract_members()
            if not _member_exists_on_widget(name)
        )
        self.assertEqual(
            missing,
            [],
            "contract members that no longer exist on LabelingWidget",
        )


if __name__ == "__main__":
    unittest.main()
