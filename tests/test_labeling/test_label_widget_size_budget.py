"""Size-budget ratchet for the remaining god objects.

The flake8 baseline and the coverage floor are ratchets: the current
state is frozen and only movement in the good direction is allowed.
``label_widget.py``, ``widgets/canvas.py`` and the training dialog get
the same treatment, because split batches 1-7 showed the failure mode
plainly: extraction pulled methods out while edits elsewhere grew the
file back (label_widget went 7977 -> 8378 across the beta.3 batches
despite two dedicated split rounds).

Rule, identical to the coverage ratchet: when a split batch shrinks a
file, lower its budget; never raise it. The failure message names the
file and the number to beat, so the fix is obvious from CI alone.
"""

import os
import unittest

REPO_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)

#: Frozen 2026-09-28, after split batch 12 (label editing cluster).
#: label_widget.py: ~6380 lines of class + ~2000 lines of module-level
#: assembly functions (_build_actions/_build_layout, batch 4).
#: canvas.py already has brush/cuboid/rotation split into their own
#: modules; the rest is the core drawing surface.
#:
#: label_widget.py raised 6777 -> 6813 on 2026-09-29 for the keyboard
#: coverage batch: +18 shortcuts is +8 net lines in _build_actions, +10
#: widget.actions members and +18 widget.addAction calls. That is a
#: feature, not drift -- the ratchet exists to stop split batches from
#: being refilled by unrelated edits. The registration tail of
#: _build_actions is the next extraction candidate; wherever the next
#: split batch lands, freeze the lower number and never raise this one
#: again for anything but a documented feature.
BUDGETS = {
    # Raised 6805 -> 6817 on 2026-09-29: the "unreviewed" file filter and
    # its navigation predicate (filelist/items.file_item_is_unchecked)
    # landed in the widget -- one combo entry plus tooltip, one filter
    # branch, one delegate and a wider docstring. A documented feature,
    # which is the only reason this number may move up; the next split
    # batch should take _apply_file_filter / _refresh_file_progress out
    # to file_list_ops and freeze the lower number again.
    #
    # Lowered 6817 -> 6808 on 2026-10-10: the project UI batch (a 项目
    # submenu, the project name in the title bar, one merged recent list)
    # moved the recent-dir menu and the project actions into
    # utils/project_view.py -- the two retired methods were 22 lines, the
    # delegations, the project-name prefix and the menu call add 13, so
    # the widget delegates its way to a smaller file instead of growing.
    #
    # Lowered 6808 -> 6781 the same day, one batch later: session resume
    # (which project, and which image inside it) moved to project_view too,
    # so session_resume_path and continue_last_session left the widget and
    # nothing took their place -- callers reach project_view directly.
    #
    # Raised 6781 -> 6785 on 2026-10-10, documented feature: the label
    # panel opened on the project record as its single source (project
    # settings own the resolution now), and the record/classes.txt
    # mismatch says so in the status bar -- the four lines are that
    # warning, the one thing the single-source change adds to the widget.
    #
    # Raised 6785 -> 6787 on 2026-10-14, documented feature: the 设备
    # submenu under 工具. Two lines only -- the import and the one call
    # that hands the widget to utils/device_menu.py, which builds every
    # action itself. The menu is where the device list can be dynamic
    # (a QActionGroup asks device_manager at fill time); the settings
    # schema's static `options` cannot express a machine-dependent list.
    #
    # Raised 6787 -> 6789 on 2026-10-15, documented feature: the persistent
    # rework banner. Two lines only -- one build call in _build_layout and
    # one refresh call in update_labeling_instruction; the banner itself and
    # its show/hide rule live in utils/file_lifecycle.py, so the widget gains
    # wiring, not logic. It keeps a rejected image's reason on screen instead
    # of relying on the eight-second status-bar line.
    #
    # Raised 6789 -> 6797 on 2026-10-15, documented feature: the 负样本 filter.
    # The file list has shown a dedicated negative-sample badge all along, but
    # the filter dropdown could not isolate those rows -- one combo entry with
    # its tooltip and one branch in _apply_file_filter are the whole change.
    #
    # Lowered 6797 -> 6768 on 2026-10-17: the 还没有类别 hint left for
    # utils/missing_classes_hint.py. Its dialog, its once-per-project table and
    # the per-project mute were 38 lines inside the widget; what stays is a
    # five-line delegation, because `load_dir` reaches the hint through the
    # widget contract. The freed 29 lines are the first headroom this file has
    # had in a week -- the next extraction candidate is still the
    # _build_actions registration tail.
    #
    # Raised 6768 -> 6772 the same day, documented feature: two dock
    # checkboxes' tooltips moved from `widget.tr(...)` to
    # QCoreApplication.translate, which the extractor can actually see (the
    # old form never reached zh_CN.ts). The longer call is what the four extra
    # lines are; utils/export.py and filelist/controller.py gave up 27 of the
    # same invisible call sites in the same batch, outside this budget.
    #
    # Lowered 6772 -> 6697 on 2026-10-23: union_selection moved to
    # utils/shape_union.py, where refusing an unrepresentable selection is
    # testable without a widget. The widget keeps a four-line delegation,
    # so this is a net removal.
    # Lowered 6697 -> 6663 on 2026-10-26: _refresh_file_progress moved
    # to file_list_ops (the low-confidence count now reads a background
    # role), and the widget keeps a one-line delegation.
    "anylabeling/views/labeling/label_widget.py": 6663,
    # Lowered 3772 -> 3760 on 2026-09-29: the undo/redo stacks moved out to
    # widgets/shape_history.py (which is also what made them survive a file
    # switch) and the canvas reaches them through the attribute names it has
    # always exposed, so the move is a net removal.
    # Lowered 3760 -> 3414 on 2026-10-17: the overlay band left for
    # widgets/canvas_overlays.py -- _paint_texts / _paint_labels /
    # _paint_cross_coordinates / _paint_attributes, 358 lines that only read
    # the canvas and draw. Canvas keeps the four `_paint_*` methods as one-line
    # delegations, so `_paint_content` and its callers are untouched, and the
    # render digest of a fixed scene was byte-identical across the move
    # (tests/test_canvas/test_canvas_overlays.py now pins what each overlay
    # draws, and that the module needs nothing but the read surface). This is
    # the headroom the next canvas feature needed.
    # Lowered 3414 -> 3380 on 2026-10-19: the background-hiding band was
    # unreachable and went -- `hide_background_shapes` had no caller, so
    # `_hide_backround` was permanently False, the 14 `set_hiding()` calls were
    # no-ops, and both paint guards (`selected or not _hide_backround`) reduced
    # to a visibility test. Both guards reduced by inspection -- the flag had
    # exactly one writer and it had no caller -- so no pixel can differ; the
    # canvas ink tests are here in case that reasoning is ever wrong.
    #
    # Raised 3380 -> 3381 on 2026-10-23, correctness fix: the scratch
    # canvas behind 另存可视化图 now copies shape_opacity. It defaulted to
    # 1.0, so the saved picture ignored the adjustment panel's opacity --
    # one line, and the canvas ink test pins the result.
    #
    # Lowered 3381 -> 2704 on 2026-10-27: the render flags/colors/loading/
    # compare state moved to CanvasRenderState and the 16 paint methods to
    # CanvasRenderMixin (widgets/canvas_render.py, 755 lines). Canvas
    # inherits the mixin and keeps the historical attribute names through
    # descriptors, so actions, settings and paint callers are unchanged.
    "anylabeling/views/labeling/widgets/canvas.py": 2704,
    # Lowered 4406 -> 4002 -> 3335 on 2026-10-26: first the
    # export/autolabel cluster moved to views/training/export_autolabel.py
    # (nine delegating stubs, is_fresh_export included), then
    # init_train_settings moved to views/training/train_settings_form.py as
    # eleven section builders behind one stub.
    "anylabeling/views/training/ultralytics_dialog.py": 3335,
}


class TestGodObjectSizeBudget(unittest.TestCase):
    def test_files_do_not_grow_past_their_budget(self):
        for rel, budget in BUDGETS.items():
            with self.subTest(file=rel):
                path = os.path.join(REPO_ROOT, rel)
                with open(path, encoding="utf-8") as handle:
                    lines = sum(1 for _ in handle)
                self.assertLessEqual(
                    lines,
                    budget,
                    f"{rel} grew to {lines} lines (budget {budget}). "
                    f"Split something out -- scripts/extract_method.py "
                    f"exists for exactly this -- then lower the budget "
                    f"to {lines} in "
                    f"tests/test_labeling/test_label_widget_size_budget.py.",
                )

    def test_every_budgeted_file_exists(self):
        # A renamed/moved file would silently free its budget; fail
        # instead, and point the budget at the new path.
        for rel in BUDGETS:
            with self.subTest(file=rel):
                self.assertTrue(
                    os.path.exists(os.path.join(REPO_ROOT, rel)),
                    f"{rel} moved or was renamed -- repoint BUDGETS",
                )


if __name__ == "__main__":
    unittest.main()
