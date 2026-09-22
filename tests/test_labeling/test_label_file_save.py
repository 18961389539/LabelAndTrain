import base64
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from PIL import Image

from anylabeling.views.labeling import label_file


class TestLabelFileSave(unittest.TestCase):
    def test_image_dimensions_are_read_without_pixel_conversion(self):
        image_buffer = io.BytesIO()
        Image.new("RGB", (2, 3), "white").save(image_buffer, format="PNG")

        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "annotation.json")
            label = label_file.LabelFile()
            with mock.patch.object(
                label_file.utils,
                "img_data_to_arr",
                side_effect=AssertionError("unexpected pixel conversion"),
            ):
                label.save(
                    filename=filename,
                    shapes=[],
                    image_path="image.png",
                    image_height=1,
                    image_width=1,
                    image_data=image_buffer.getvalue(),
                )

            with open(filename, "r", encoding="utf-8") as label_stream:
                data = json.load(label_stream)
            self.assertEqual(data["imageHeight"], 3)
            self.assertEqual(data["imageWidth"], 2)
            self.assertEqual(
                base64.b64decode(data["imageData"]), image_buffer.getvalue()
            )

    def test_failed_save_preserves_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = os.path.join(directory, "annotation.json")
            original_data = '{"original": true}\n'
            with open(filename, "w", encoding="utf-8") as f:
                f.write(original_data)

            def fail_after_partial_write(data, f, **kwargs):
                f.write('{"partial":')
                raise OSError("simulated write failure")

            label = label_file.LabelFile()
            with mock.patch.object(
                label_file.json,
                "dump",
                side_effect=fail_after_partial_write,
            ):
                with self.assertRaises(label_file.LabelFileError):
                    label.save(
                        filename=filename,
                        shapes=[],
                        image_path="image.jpg",
                        image_height=1,
                        image_width=1,
                    )

            with open(filename, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), original_data)
            self.assertEqual(os.listdir(directory), ["annotation.json"])
            self.assertIsNone(label.filename)


if __name__ == "__main__":
    unittest.main()


class TestReviewStatePersistence(unittest.TestCase):
    """`review_state` is authoritative; `checked` mirrors it for old readers."""

    def _label_path(self, directory, name="a.json"):
        return os.path.join(directory, name)

    def _write_image(self, directory, name="a.png"):
        """`LabelFile.load` validates dimensions, so the image must exist."""
        path = os.path.join(directory, name)
        if not os.path.exists(path):
            Image.new("RGB", (2, 3), "white").save(path)
        return name

    def _save_with(self, filename, other_data):
        directory = os.path.dirname(filename)
        image_name = self._write_image(directory)
        label_file.LabelFile().save(
            filename=filename,
            shapes=[],
            image_path=image_name,
            image_height=3,
            image_width=2,
            image_data=None,
            other_data=other_data,
        )

    def _read(self, filename):
        with open(filename, "r", encoding="utf-8") as stream:
            return json.load(stream)

    def test_rejected_writes_state_and_clears_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = self._label_path(directory)
            self._save_with(
                filename,
                {
                    "checked": True,
                    "review_state": "rejected",
                    "reviewed_at": "2026-09-21T20:00:00",
                },
            )
            data = self._read(filename)
            self.assertEqual(data["review_state"], "rejected")
            self.assertIs(data["checked"], False)
            self.assertEqual(data["reviewed_at"], "2026-09-21T20:00:00")

    def test_confirmed_state_forces_checked_true(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = self._label_path(directory)
            self._save_with(
                filename, {"checked": False, "review_state": "confirmed"}
            )
            self.assertIs(self._read(filename)["checked"], True)

    def test_legacy_file_derives_state_from_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write_image(directory, "legacy.png")
            filename = self._label_path(directory, "legacy.json")
            with open(filename, "w", encoding="utf-8") as stream:
                json.dump(
                    {
                        "version": "0.0.0",
                        "flags": {},
                        "checked": True,
                        "shapes": [],
                        "imagePath": "legacy.png",
                        "imageData": None,
                        "imageHeight": 1,
                        "imageWidth": 1,
                    },
                    stream,
                )
            label = label_file.LabelFile()
            label.image_dir = directory
            label.load(filename)
            self.assertEqual(label.other_data["review_state"], "confirmed")
            self.assertIs(label.other_data["checked"], True)

    def test_state_survives_a_save_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            filename = self._label_path(directory)
            self._save_with(
                filename,
                {
                    "review_state": "rejected",
                    "reviewed_at": "2026-09-21T20:00:00",
                    "custom_note": "keep me",
                },
            )
            label = label_file.LabelFile()
            label.image_dir = directory
            label.load(filename)
            self.assertEqual(label.other_data["review_state"], "rejected")
            self.assertEqual(label.other_data["custom_note"], "keep me")

    def test_scanner_agrees_with_full_parse(self):
        from anylabeling.views.labeling.utils.async_label_check import (
            _label_file_review_state,
        )

        for state in ("unchecked", "confirmed", "rejected"):
            with self.subTest(state=state):
                with tempfile.TemporaryDirectory() as directory:
                    filename = self._label_path(directory)
                    self._save_with(filename, {"review_state": state})
                    label = label_file.LabelFile()
                    label.image_dir = directory
                    label.load(filename)
                    self.assertEqual(
                        _label_file_review_state(filename),
                        label.other_data["review_state"],
                    )
