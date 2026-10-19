"""``--skip-empty-files`` must leave no empty output behind.

The flag is a promise about the output directory, not only about the
"Converted N files" count: the GUI export removes the empty ``.txt`` and the
training split drops the pair. The CLI counted the file as skipped while
leaving the zero-object output in place, so a later training run picked it up.
"""

import json
import os
import tempfile
import unittest

import cv2
import numpy as np

from anylabeling.views.common.converter import run_conversion


class TestCliSkipEmptyFiles(unittest.TestCase):
    def setUp(self):
        self.holder = tempfile.TemporaryDirectory()
        self.dir = self.holder.name
        self.images = os.path.join(self.dir, "images")
        self.labels = os.path.join(self.dir, "labels")
        self.output = os.path.join(self.dir, "out")
        for path in (self.images, self.labels, self.output):
            os.makedirs(path)
        cv2.imwrite(
            os.path.join(self.images, "img.png"),
            np.zeros((30, 20, 3), dtype=np.uint8),
        )
        self.classes = os.path.join(self.dir, "classes.txt")
        with open(self.classes, "w", encoding="utf-8") as handle:
            handle.write("cat\n")
        self.write_label("rectangle", "zebra")

    def tearDown(self):
        self.holder.cleanup()

    def write_label(self, shape_type, label):
        with open(
            os.path.join(self.labels, "img.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "version": "2.4.0",
                    "flags": {},
                    "shapes": [
                        {
                            "label": label,
                            "points": [[2, 3], [12, 3], [12, 20], [2, 20]],
                            "group_id": None,
                            "shape_type": shape_type,
                            "flags": {},
                        }
                    ],
                    "imagePath": "img.png",
                    "imageData": None,
                    "imageHeight": 30,
                    "imageWidth": 20,
                },
                handle,
            )

    def _convert(self, task, mode, skip):
        run_conversion(
            task,
            images=self.images,
            labels=self.labels,
            output=self.output,
            classes_file=self.classes,
            mode=mode,
            skip_empty_files=skip,
        )

    def test_yolo_skip_empty_removes_the_empty_txt(self):
        # The rectangle's class is not in classes.txt, so nothing is written.
        self._convert("xlabel2yolo", "detect", True)

        self.assertFalse(os.path.exists(os.path.join(self.output, "img.txt")))

    def test_yolo_without_skip_keeps_the_empty_txt(self):
        self._convert("xlabel2yolo", "detect", False)

        path = os.path.join(self.output, "img.txt")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "")

    def test_voc_skip_empty_removes_the_empty_xml(self):
        # A polygon cannot be expressed in a rectangle export.
        self.write_label("polygon", "cat")

        self._convert("xlabel2voc", "detect", True)

        self.assertFalse(os.path.exists(os.path.join(self.output, "img.xml")))

    def test_voc_without_skip_keeps_the_objectless_xml(self):
        self.write_label("polygon", "cat")

        self._convert("xlabel2voc", "detect", False)

        path = os.path.join(self.output, "img.xml")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("<annotation>", text)
        self.assertNotIn("<object>", text)


if __name__ == "__main__":
    unittest.main()
