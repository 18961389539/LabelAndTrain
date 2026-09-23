"""The review queue must stay complete; only the audit dialog truncates.

``audit_dataset`` used to cut the ranked queue at 50 entries, and the smart
review jump inherited that list, so a folder with hundreds of uncertain images
reported "1/50" and then "end of queue" while the rest were never visited.
"""

import json
import os
import os.path as osp
import tempfile
import unittest

try:
    from anylabeling.views.labeling.utils.data_audit import (
        DISPLAY_LIMIT,
        audit_dataset,
        format_category_title,
    )
    from anylabeling.views.labeling.utils.smart_tools import run_review_jump

    _AUDIT_AVAILABLE = True
except Exception:
    _AUDIT_AVAILABLE = False

UNCERTAIN = 0.30  # below the auto-accept band, above the review floor
WORST = 0.10  # at or under the review floor: uncertainty 1.0
CONFIDENT = 0.90


def _write_folder(tmp, scores):
    """Create images in one folder and their label jsons in another.

    Returns ``(image_paths, label_dir)`` the way the app has them after
    「Change Output Dir」.
    """
    image_dir = os.path.join(tmp, "images")
    label_dir = os.path.join(tmp, "labels")
    os.makedirs(image_dir, exist_ok=True)
    os.makedirs(label_dir, exist_ok=True)
    paths = []
    for index, score in enumerate(scores):
        image_path = os.path.join(image_dir, f"img_{index:04d}.jpg")
        open(image_path, "wb").close()
        shape = {
            "label": "cat",
            "score": score,
            "points": [[10, 10], [60, 10], [60, 60], [10, 60]],
            "group_id": None,
            "flags": {},
            "shape_type": "rectangle",
        }
        with open(
            osp.join(label_dir, f"img_{index:04d}.json"),
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                {
                    "imageWidth": 100,
                    "imageHeight": 100,
                    "shapes": [shape],
                },
                handle,
            )
        paths.append(image_path)
    return paths, label_dir


class _Parent:
    """Stand-in for the widget: only the parts the jump touches."""

    def __init__(self, image_list, label_dir):
        self.image_list = image_list
        self.output_dir = label_dir
        self.filename = None
        self.opened = []
        self.statuses = []

    def tr(self, text):
        return text

    def load_file(self, path):
        self.opened.append(path)

    def status(self, text):
        self.statuses.append(text)


@unittest.skipUnless(
    _AUDIT_AVAILABLE, "PyQt6 is required for the audit and smart tools"
)
class TestReviewQueueIsNotTruncated(unittest.TestCase):
    def test_queue_holds_every_uncertain_image(self):
        scores = [WORST] + [UNCERTAIN] * 130 + [CONFIDENT] * 3
        with tempfile.TemporaryDirectory() as tmp:
            paths, label_dir = _write_folder(tmp, scores)
            results = audit_dataset(paths, label_dir)

            self.assertEqual(len(results["review"]), 131)
            self.assertGreater(len(results["review"]), DISPLAY_LIMIT)
            # Confident images are not queued at all, so the count above is a
            # measured queue and not "everything in the folder".
            self.assertNotIn(paths[131], results["review"])
            # Worst first: the queue is ranked, not merely long.
            self.assertEqual(results["review"][0], paths[0])

    def test_category_title_shows_the_total_when_capped(self):
        self.assertEqual(
            format_category_title("review", 131, 100),
            "优先复核（按不确定性排序）（共 131，显示前 100）",
        )
        self.assertEqual(
            format_category_title("empty", 4, 4),
            "空标注文件（shapes 为空）（4）",
        )

    def test_jump_reports_the_full_queue_and_opens_the_worst(self):
        scores = [WORST] + [UNCERTAIN] * 130
        with tempfile.TemporaryDirectory() as tmp:
            paths, label_dir = _write_folder(tmp, scores)
            parent = _Parent(paths, label_dir)
            run_review_jump(parent)

            self.assertEqual(parent.opened, [paths[0]])
            self.assertEqual(len(parent.statuses), 1)
            self.assertIn("1/131", parent.statuses[0])
            self.assertNotIn("末尾", parent.statuses[0])


if __name__ == "__main__":
    unittest.main()
