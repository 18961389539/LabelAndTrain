"""Size-budget ratchet for the two remaining god objects.

The flake8 baseline and the coverage floor are ratchets: the current
state is frozen and only movement in the good direction is allowed.
``label_widget.py`` and ``widgets/canvas.py`` get the same treatment,
because split batches 1-7 showed the failure mode plainly: extraction
pulled methods out while edits elsewhere grew the file back (label_widget
went 7977 -> 8378 across the beta.3 batches despite two dedicated split
rounds).

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
BUDGETS = {
    "anylabeling/views/labeling/label_widget.py": 6774,
    "anylabeling/views/labeling/widgets/canvas.py": 3930,
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
