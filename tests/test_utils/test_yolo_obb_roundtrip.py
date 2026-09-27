"""OBB has to survive a round trip through YOLO, not just reach the menu.

The menus gained a YOLO OBB entry; this pins what the two converters actually
do with a rotation box: the coordinates that come back must land on the same
pixels, the class index must map through ``classes.txt``, and the shapes the
mode cannot express must be counted rather than dropped in silence.
"""

import json
import os
import tempfile
import unittest

from PIL import Image

from anylabeling.views.labeling.label_converter import LabelConverter

IMAGE_WIDTH = 200
IMAGE_HEIGHT = 100

# One rotation box, 10px in from every edge so the normalisation is exact.
IN_BOUNDS = [[10, 20], [180, 20], [180, 80], [10, 80]]
OUT_OF_BOUNDS = [[-5, 20], [180, 20], [180, 80], [10, 80]]


class TestYoloObbRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.classes_file = os.path.join(self.tmp.name, "classes.txt")
        with open(self.classes_file, "w", encoding="utf-8") as handle:
            handle.write("plane\nship\n")
        self.image_file = os.path.join(self.tmp.name, "image.png")
        Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), "white").save(
            self.image_file
        )
        self.label_json = os.path.join(self.tmp.name, "label.json")
        with open(self.label_json, "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "imagePath": "image.png",
                    "imageWidth": IMAGE_WIDTH,
                    "imageHeight": IMAGE_HEIGHT,
                    "shapes": [
                        {
                            "label": "ship",
                            "shape_type": "rotation",
                            "points": IN_BOUNDS,
                        },
                        {
                            "label": "plane",
                            "shape_type": "rotation",
                            "points": OUT_OF_BOUNDS,
                        },
                        {
                            # hbb is a different export mode: obb must count
                            # this as skipped instead of writing a wrong line.
                            "label": "ship",
                            "shape_type": "rectangle",
                            "points": [[0, 0], [10, 0], [10, 10], [0, 10]],
                        },
                    ],
                },
                handle,
            )

    def tearDown(self):
        self.tmp.cleanup()

    def test_export_writes_one_line_and_counts_the_rest(self):
        txt_file = os.path.join(self.tmp.name, "label.txt")
        stats = {}

        LabelConverter(classes_file=self.classes_file).custom_to_yolo(
            self.label_json, txt_file, "obb", stats=stats
        )

        with open(txt_file, "r", encoding="utf-8") as handle:
            lines = [line for line in handle.read().splitlines() if line]
        self.assertEqual(len(lines), 1, lines)
        fields = lines[0].split(" ")
        self.assertEqual(len(fields), 9, fields)
        # "ship" is the second line of classes.txt -> index 1.
        self.assertEqual(fields[0], "1")
        self.assertEqual(stats["exported"], 1)
        self.assertEqual(
            stats["skipped"],
            {
                "rotation reaching outside the image": 1,
                "rectangle is not part of a obb export": 1,
            },
        )

    def test_the_coordinates_come_back_on_the_same_pixels(self):
        txt_file = os.path.join(self.tmp.name, "label.txt")
        LabelConverter(classes_file=self.classes_file).custom_to_yolo(
            self.label_json, txt_file, "obb"
        )
        back_file = os.path.join(self.tmp.name, "back.json")

        LabelConverter(classes_file=self.classes_file).yolo_obb_to_custom(
            input_file=txt_file,
            output_file=back_file,
            image_file=self.image_file,
        )

        with open(back_file, "r", encoding="utf-8") as handle:
            shapes = json.load(handle)["shapes"]
        self.assertEqual(len(shapes), 1)
        shape = shapes[0]
        self.assertEqual(shape["label"], "ship")
        self.assertEqual(shape["shape_type"], "rotation")
        for expected, actual in zip(IN_BOUNDS, shape["points"]):
            self.assertAlmostEqual(expected[0], actual[0], places=3)
            self.assertAlmostEqual(expected[1], actual[1], places=3)

    def test_a_full_circle_stays_within_a_pixel(self):
        # Write, read back, write again: the second file must match the first
        # byte for byte, or a re-export would drift the boxes.
        first_txt = os.path.join(self.tmp.name, "first.txt")
        converter = LabelConverter(classes_file=self.classes_file)
        converter.custom_to_yolo(self.label_json, first_txt, "obb")

        back_file = os.path.join(self.tmp.name, "back.json")
        converter.yolo_obb_to_custom(first_txt, back_file, self.image_file)

        second_txt = os.path.join(self.tmp.name, "second.txt")
        converter.custom_to_yolo(back_file, second_txt, "obb")
        with open(first_txt, "r", encoding="utf-8") as handle:
            first = handle.read()
        with open(second_txt, "r", encoding="utf-8") as handle:
            second = handle.read()

        self.assertEqual(first, second)
