"""The export has to say what it is about to drop, before it starts.

Two failures in this path cannot be undone by the summary popup that follows
them: a shape whose label is not in the exported class list disappears file by
file, and an unreadable label file raises out of the run and leaves a
half-written directory. Both are visible before the first byte is written.

The last class here holds the two implementations together: ``export_check``
and ``data_audit`` both decide what "unlabeled", "empty" and "corrupted" mean,
and they must not drift apart.
"""

import json
import os
import os.path as osp
import pathlib
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
EXPORT_SOURCE = REPO_ROOT / "anylabeling/views/labeling/utils/export.py"

from anylabeling.views.labeling.utils import export_check  # noqa: E402
from anylabeling.views.labeling.utils.data_audit import (  # noqa: E402
    audit_dataset,
)
from anylabeling.views.labeling.utils.export_check import (  # noqa: E402
    build_manifest,
    check_export_readiness,
    format_readiness,
    is_blocking,
    scan_source,
    write_manifest,
)


class _Tree(unittest.TestCase):
    """A folder of images and label files that does not need real pixels."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        self.images = []

    def image(self, name):
        path = osp.join(self.root, name)
        # audit_dataset skips images that do not exist, so the cross-check
        # needs a real file on disk.
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("")
        self.images.append(path)
        return path

    def label(self, name, shapes):
        path = osp.join(self.root, name)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(
                {"imageWidth": 100, "imageHeight": 100, "shapes": shapes},
                handle,
            )
        return path

    @staticmethod
    def label_for(image_file):
        return osp.splitext(image_file)[0] + ".json"


def shape(label):
    return {
        "label": label,
        "shape_type": "rectangle",
        "points": [[0, 0], [1, 1]],
    }


class TestScanSource(_Tree):
    def test_counts_every_label_across_the_files(self):
        self.image("a.png")
        self.image("b.png")
        self.label("a.json", [shape("scratch"), shape("dent")])
        self.label("b.json", [shape("scratch")])

        scan = scan_source(self.images, self.label_for)

        self.assertEqual(scan["label_counts"], {"scratch": 2, "dent": 1})
        self.assertEqual(scan["images"], 2)
        self.assertEqual((scan["unlabeled"], scan["empty"]), (0, 0))
        self.assertEqual(scan["corrupted"], [])

    def test_a_missing_label_file_is_not_an_error(self):
        self.image("a.png")

        scan = scan_source(self.images, self.label_for)

        self.assertEqual(scan["unlabeled"], 1)
        self.assertEqual(scan["corrupted"], [])

    def test_an_empty_label_file_is_counted_but_not_flagged(self):
        self.image("a.png")
        self.label("a.json", [])

        scan = scan_source(self.images, self.label_for)

        self.assertEqual(scan["empty"], 1)
        self.assertEqual(scan["label_counts"], {})
        self.assertEqual(scan["corrupted"], [])

    def test_unreadable_json_lands_in_corrupted_and_stops_nothing(self):
        self.image("a.png")
        self.image("b.png")
        self.label("a.json", [shape("scratch")])
        with open(
            osp.join(self.root, "b.json"), "w", encoding="utf-8"
        ) as handle:
            handle.write("{not json")

        scan = scan_source(self.images, self.label_for)

        self.assertEqual(
            [osp.basename(p) for p in scan["corrupted"]], ["b.json"]
        )
        self.assertEqual(scan["label_counts"], {"scratch": 1})

    def test_a_json_without_a_shape_list_is_corrupted_not_empty(self):
        # The converter indexes data["shapes"], so this file raises; calling
        # it "empty" would tell the annotator the opposite of what happens.
        self.image("a.png")
        self.label("a.json", None)
        with open(
            osp.join(self.root, "a.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump({"imageWidth": 10, "imageHeight": 10}, handle)

        scan = scan_source(self.images, self.label_for)

        self.assertEqual(scan["corrupted"], [osp.join(self.root, "a.json")])
        self.assertEqual(scan["empty"], 0)

    def test_a_cleared_label_still_counts(self):
        self.image("a.png")
        self.label("a.json", [shape("")])

        scan = scan_source(self.images, self.label_for)

        self.assertEqual(scan["label_counts"], {"": 1})


class TestReadiness(_Tree):
    def test_labels_outside_the_class_list_are_named_with_their_counts(self):
        self.image("a.png")
        self.label("a.json", [shape("scratch"), shape("dent"), shape("dent")])

        readiness = check_export_readiness(
            self.images, self.label_for, ["scratch"]
        )

        self.assertEqual(readiness["unknown_labels"], {"dent": 2})
        self.assertEqual(readiness["unknown_shapes"], 2)

    def test_a_matching_class_list_is_clean(self):
        self.image("a.png")
        self.label("a.json", [shape("scratch")])

        readiness = check_export_readiness(
            self.images, self.label_for, ["scratch", "dent"]
        )

        self.assertEqual(readiness["unknown_shapes"], 0)
        self.assertEqual(format_readiness(readiness), [])

    def test_only_dropped_shapes_and_unreadable_files_block(self):
        self.image("a.png")
        self.label("a.json", [shape("scratch")])
        clean = check_export_readiness(
            self.images, self.label_for, ["scratch"]
        )
        self.assertFalse(is_blocking(clean))

        unknown = check_export_readiness(self.images, self.label_for, ["dent"])
        self.assertTrue(is_blocking(unknown))

    def test_empty_and_unlabeled_alone_do_not_block(self):
        # Negative samples export as background on purpose; stopping there
        # would train the annotator to click through the dialog.
        self.image("a.png")
        self.image("b.png")
        self.label("a.json", [])

        readiness = check_export_readiness(self.images, self.label_for, ["x"])

        self.assertEqual(readiness["empty"], 1)
        self.assertEqual(readiness["unlabeled"], 1)
        self.assertFalse(is_blocking(readiness))
        self.assertEqual(format_readiness(readiness), [])

    def test_the_body_lists_ranked_labels_and_file_names(self):
        self.image("a.png")
        self.image("b.png")
        self.label("a.json", [shape("dent")] * 3 + [shape("crack")])
        self.label("b.json", None)
        with open(
            osp.join(self.root, "b.json"), "w", encoding="utf-8"
        ) as handle:
            handle.write("{not json")

        readiness = check_export_readiness(self.images, self.label_for, [])
        lines = format_readiness(readiness)

        # headline, dent, crack, unreadable headline, the file itself.
        self.assertEqual(len(lines), 5)
        self.assertIn("4 个标注", lines[0])
        self.assertIn("dent：3", lines[1])
        self.assertIn("crack：1", lines[2])
        self.assertIn("b.json", lines[4])
        # The dead shape's own path is what the manifest carries.
        self.assertEqual(
            readiness["corrupted"], [osp.join(self.root, "b.json")]
        )


class TestManifest(_Tree):
    def _manifest(self, readiness, **overrides):
        payload = {
            "mode": "hbb",
            "version": "1.2.3",
            "image_dir": "/data/images",
            "label_dir": "/data/labels",
            "classes": ["scratch", "dent"],
            "classes_source": "当前标签列表",
            "filters": {"only_confirmed": True, "skip_empty_labels": False},
            "result": {"images_exported": 2, "shapes_exported": 5},
            "readiness": readiness,
            "generated_at": "2026-09-29T14:00:00",
        }
        payload.update(overrides)
        return build_manifest(**payload)

    def test_records_the_class_list_that_gives_the_ids_their_meaning(self):
        self.image("a.png")
        self.label("a.json", [shape("scratch")])
        readiness = check_export_readiness(
            self.images, self.label_for, ["scratch", "dent"]
        )

        manifest = self._manifest(readiness)

        self.assertEqual(manifest["classes"]["names"], ["scratch", "dent"])
        self.assertEqual(manifest["classes"]["source"], "当前标签列表")
        self.assertEqual(manifest["mode"], "hbb")
        self.assertEqual(manifest["version"], "1.2.3")

    def test_records_the_filters_and_the_source_data_state(self):
        self.image("a.png")
        self.image("b.png")
        self.label("a.json", [shape("scratch")])
        readiness = check_export_readiness(
            self.images, self.label_for, ["scratch"]
        )

        manifest = self._manifest(readiness)

        self.assertTrue(manifest["filters"]["only_confirmed"])
        self.assertEqual(manifest["source"]["images"], 2)
        self.assertEqual(manifest["source_data"]["no_label_file"], 1)
        self.assertEqual(manifest["result"]["shapes_exported"], 5)

    def test_it_is_written_as_readable_json(self):
        self.image("a.png")
        self.label("a.json", [shape("scratch")])
        readiness = check_export_readiness(
            self.images, self.label_for, ["scratch"]
        )

        target = write_manifest(self.root, self._manifest(readiness))

        self.assertEqual(osp.basename(target), export_check.MANIFEST_NAME)
        with open(target, "r", encoding="utf-8") as handle:
            written = json.load(handle)
        self.assertEqual(written["classes"]["names"], ["scratch", "dent"])

    def test_a_manifest_that_cannot_be_written_does_not_fail_the_export(self):
        # The export has already succeeded here; losing the record must not
        # turn that into an error the annotator sees.
        readiness = check_export_readiness([], self.label_for, [])

        self.assertIsNone(
            write_manifest(
                osp.join(self.root, "no-such-dir"), self._manifest(readiness)
            )
        )


class TestAgreesWithDataAudit(_Tree):
    """Two implementations, one verdict.

    ``export_check`` reads the label files in one pass for the export's own
    reasons instead of reusing ``audit_dataset`` (which scans again and scores
    uncertainty). The trade is only safe while the three shared answers stay
    identical, so they are compared on one fixture rather than assumed.
    """

    def test_unlabeled_empty_and_corrupted_match_the_audit(self):
        self.image("clean.png")
        self.image("empty.png")
        self.image("broken.png")
        self.image("noshapes.png")
        self.image("nothing.png")
        self.label("clean.json", [shape("scratch")])
        self.label("empty.json", [])
        with open(
            osp.join(self.root, "broken.json"), "w", encoding="utf-8"
        ) as h:
            h.write("{oops")
        with open(
            osp.join(self.root, "noshapes.json"), "w", encoding="utf-8"
        ) as h:
            h.write('{"imageWidth": 1, "imageHeight": 1}')

        scan = scan_source(self.images, self.label_for)
        audit = audit_dataset(self.images, self.root)

        def stems(paths):
            # The audit reports the image path (its rows jump to the image);
            # this reports the label file, which is the file that is broken.
            # Same verdict, different handle -- compare by stem.
            return sorted(osp.splitext(osp.basename(p))[0] for p in paths)

        self.assertEqual(scan["unlabeled"], len(audit["unlabeled"]))
        self.assertEqual(stems(audit["empty"]), ["empty"])
        self.assertEqual(stems(audit["corrupted"]), ["broken", "noshapes"])
        self.assertEqual(stems(scan["corrupted"]), ["broken", "noshapes"])
        self.assertEqual(scan["empty"], 1)


class TestExportWiring(unittest.TestCase):
    """Where the check sits, not just that it exists.

    Both properties here are about position in the export flow, which no unit
    test of the pure functions can see:

    - it must read the *filtered* list through the same label mapping the run
      uses, or it would report on images this export will not touch;
    - it must run *before* the output directory is resolved, so answering
      "Cancel" leaves nothing behind on disk.
    """

    @classmethod
    def setUpClass(cls):
        cls.source = EXPORT_SOURCE.read_text(encoding="utf-8")

    def test_it_checks_the_files_the_run_will_actually_read(self):
        self.assertIn(
            "check_export_readiness(image_list, get_label_file, classes)",
            self.source,
        )

    def test_it_runs_before_the_output_directory_is_touched(self):
        check_at = self.source.index("check_export_readiness(")
        directory_at = self.source.index("resolve_existing_output_dir(")

        self.assertLess(check_at, directory_at)

    def test_the_manifest_is_written_and_named_in_the_summary(self):
        self.assertIn("write_manifest(", self.source)
        self.assertIn("manifest_target=manifest_target", self.source)
        self.assertIn("MANIFEST_NAME", self.source)


if __name__ == "__main__":
    unittest.main()
