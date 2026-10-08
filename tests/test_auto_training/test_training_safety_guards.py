"""The guards that keep a training run from quietly losing data.

Three findings, one file, because they share a root: the training side had no
account of what it could not use, and no rule about which directories it may
delete.

* A label file that exists but cannot be parsed used to be filed as a
  *background* image — an empty sample — so a fully annotated frame trained
  the model on "there is nothing here". The export path already refuses this
  (``utils/export_check.is_blocking``); the dataset build now leaves the image
  out and says so.
* One bad label file used to take the whole build down with it (a ``KeyError``
  on a missing ``imageWidth``, on a label some converter had produced). A
  single file is dropped now, with the reason recorded.
* ``Project`` and ``Name`` are plain text boxes that get joined into the
  directory the overwrite confirmation deletes recursively, and
  ``os.path.join`` discards the project when the name is absolute. The name is
  one directory component now, and the delete refuses anything that is not
  inside the project or does not look like a run.
"""

import json
import os

import cv2
import numpy as np
import pytest
import yaml

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from anylabeling.services.auto_training.ultralytics import (  # noqa: E402
    general,
    validators,
)
from anylabeling.services.auto_training.ultralytics.general import (  # noqa: E402
    create_yolo_dataset,
    partition_images,
)
from anylabeling.services.auto_training.ultralytics.validators import (  # noqa: E402
    is_inside_directory,
    is_single_path_component,
    validate_basic_config,
    validate_classes,
)
from anylabeling.views.training import run_history  # noqa: E402
from anylabeling.views.training import (
    ultralytics_dialog as dialog_module,
)  # noqa: E402
from anylabeling.views.training.ultralytics_dialog import (  # noqa: E402
    UltralyticsDialog,
    dataset_skips,
    is_blocking_dataset_skip,
    is_fresh_export,
    looks_like_training_run,
)

CLASSES = ["cat", "dog"]


def _write_image(path):
    canvas = np.zeros((30, 20, 3), dtype=np.uint8)
    canvas[5, 5] = (255, 255, 255)
    cv2.imwrite(str(path), canvas)
    return str(path)


def _label(shapes, **extra):
    payload = {
        "version": "1",
        "flags": {},
        "checked": True,
        "shapes": shapes,
        "imagePath": "x.jpg",
        "imageData": None,
        "imageHeight": 30,
        "imageWidth": 20,
    }
    payload.update(extra)
    return payload


def _rectangle(label="cat"):
    return {
        "label": label,
        "points": [[2, 3], [12, 20]],
        "group_id": None,
        "description": "",
        "shape_type": "rectangle",
        "flags": {},
        "attributes": {},
        "kie_linking": [],
    }


@pytest.fixture
def dataset_root(tmp_path, monkeypatch):
    root = tmp_path / "trainer_datasets"
    root.mkdir()
    monkeypatch.setattr(general, "get_dataset_path", lambda: str(root))
    return root


def _data_file(tmp_path):
    path = tmp_path / "classes.yaml"
    path.write_text(
        yaml.safe_dump({"names": {0: "cat", 1: "dog"}, "nc": 2}),
        encoding="utf-8",
    )
    return str(path)


def _tree(tmp_path):
    """A folder with one good image and one whose label JSON is truncated."""
    good = _write_image(tmp_path / "good.jpg")
    broken = _write_image(tmp_path / "broken.jpg")
    (tmp_path / "good.json").write_text(
        json.dumps(_label([_rectangle()])), encoding="utf-8"
    )
    (tmp_path / "broken.json").write_text(
        '{"shapes": [{"label": "cat", "shape', encoding="utf-8"
    )
    return good, broken


class TestPartitionImages:
    def test_a_label_file_that_cannot_be_read_is_not_a_negative_sample(
        self, tmp_path
    ):
        good, broken = _tree(tmp_path)

        groups = partition_images([good, broken], "Detect", str(tmp_path))

        assert [pair[0] for pair in groups["valid"]] == [good]
        assert groups["background"] == []
        assert groups["unreadable_labels"] == [
            os.path.join(str(tmp_path), "broken.json")
        ]

    def test_an_image_without_any_label_file_is_still_a_negative_sample(
        self, tmp_path
    ):
        good, _ = _tree(tmp_path)
        unlabeled = _write_image(tmp_path / "unlabeled.jpg")

        groups = partition_images([good, unlabeled], "Detect", str(tmp_path))

        # No label file at all is a deliberate negative sample and stays one;
        # only a file that exists and cannot be read is a different thing.
        assert groups["background"] == [unlabeled]
        assert groups["unreadable_labels"] == []

    def test_a_json_that_is_not_an_object_counts_as_unreadable(self, tmp_path):
        path = _write_image(tmp_path / "odd.jpg")
        (tmp_path / "odd.json").write_text("[1, 2, 3]", encoding="utf-8")

        groups = partition_images([path], "Detect", str(tmp_path))

        assert len(groups["unreadable_labels"]) == 1
        assert groups["background"] == []

    def test_unchecked_files_and_missing_labels_are_counted_separately(
        self, tmp_path
    ):
        images = []
        for name, checked in (("a", True), ("b", False)):
            images.append(_write_image(tmp_path / f"{name}.jpg"))
            (tmp_path / f"{name}.json").write_text(
                json.dumps(_label([_rectangle()], checked=checked)),
                encoding="utf-8",
            )
        no_label = _write_image(tmp_path / "c.jpg")

        groups = partition_images(
            images + [no_label],
            "Detect",
            str(tmp_path),
            only_checked_files=True,
        )

        assert len(groups["valid"]) == 1
        # Both are out of the dataset, but for different reasons and only one
        # of them is worth telling the annotator about.
        assert len(groups["unchecked_files"]) == 2
        assert groups["unreadable_labels"] == []
        assert groups["background"] == []


class TestDatasetBuildReportsWhatItCouldNotUse:
    def test_unreadable_label_is_left_out_and_reported(
        self, dataset_root, tmp_path
    ):
        good, broken = _tree(tmp_path)
        report = {}

        out = create_yolo_dataset(
            [good, broken],
            "Detect",
            1.0,
            _data_file(tmp_path),
            str(tmp_path),
            None,
            False,
            False,
            seed=1,
            report=report,
        )

        trained = sorted(os.listdir(os.path.join(out, "images", "train")))
        assert trained == ["good.jpg"]
        assert report["unreadable_labels_count"] == 1
        assert report["background"] == 0

        manifest = json.loads(
            open(os.path.join(out, "manifest.json"), encoding="utf-8").read()
        )
        assert manifest["skipped"]["unreadable_labels_count"] == 1
        assert manifest["counts"]["background"] == 0
        info = open(
            os.path.join(out, "dataset_info.txt"), encoding="utf-8"
        ).read()
        assert "Unreadable label files: 1" in info
        assert "broken.json" in info

    def test_one_bad_label_file_does_not_take_the_build_down(
        self, dataset_root, tmp_path
    ):
        good = _write_image(tmp_path / "good.jpg")
        odd = _write_image(tmp_path / "odd.jpg")
        (tmp_path / "good.json").write_text(
            json.dumps(_label([_rectangle()])), encoding="utf-8"
        )
        # Valid JSON, missing imageWidth: this used to raise a KeyError out of
        # the converter and kill the whole batch.
        no_size = _label([_rectangle()])
        del no_size["imageWidth"]
        del no_size["imageHeight"]
        (tmp_path / "odd.json").write_text(
            json.dumps(no_size), encoding="utf-8"
        )
        report = {}

        out = create_yolo_dataset(
            [good, odd],
            "Detect",
            1.0,
            _data_file(tmp_path),
            str(tmp_path),
            None,
            False,
            False,
            seed=1,
            report=report,
        )

        assert sorted(os.listdir(os.path.join(out, "images", "train"))) == [
            "good.jpg"
        ]
        assert len(report["conversion_errors"]) == 1
        assert "KeyError" in report["conversion_errors"][0]["error"]
        # The half-built pair is gone, so nothing trains the image as empty.
        assert not os.path.exists(
            os.path.join(out, "labels", "train", "odd.txt")
        )

    def test_shapes_the_task_cannot_express_are_counted(
        self, dataset_root, tmp_path
    ):
        image = _write_image(tmp_path / "img.jpg")
        polygon = dict(_rectangle(), shape_type="polygon")
        (tmp_path / "img.json").write_text(
            json.dumps(_label([_rectangle(), polygon])), encoding="utf-8"
        )
        report = {}

        out = create_yolo_dataset(
            [image],
            "Detect",
            1.0,
            _data_file(tmp_path),
            str(tmp_path),
            None,
            False,
            False,
            seed=1,
            report=report,
        )

        assert report["dropped_shapes"]
        assert sum(report["dropped_shapes"].values()) == 1
        # The rectangle that mode *can* express still made it in.
        assert os.path.isfile(os.path.join(out, "labels", "train", "img.txt"))
        # Counted, not blocking: a known limitation of the mode, reported the
        # same way the export path reports it.
        assert [
            entry
            for entry in dataset_skips(report)
            if is_blocking_dataset_skip(entry[0])
        ] == []


class TestNameIsOneDirectory:
    @pytest.mark.parametrize(
        "name",
        ["..", ".", "a/b", "a\\b", "C:/", "D:/labels", "/etc", "", "   "],
    )
    def test_path_shaped_names_are_rejected(self, name, tmp_path):
        config = {
            "basic": {
                "project": str(tmp_path),
                "name": name,
                "model": "yolov8n.pt",
                "data": _data_file(tmp_path),
            }
        }

        is_valid, message = validate_basic_config(config, "Detect")

        assert is_valid is False
        assert "single folder name" in message or "required" in message

    @pytest.mark.parametrize("name", ["exp", "run_2", "exp.v2", "实验一"])
    def test_a_plain_folder_name_passes(self, name, tmp_path):
        config = {
            "basic": {
                "project": str(tmp_path),
                "name": name,
                "model": "yolov8n.pt",
                "data": _data_file(tmp_path),
            }
        }

        assert validate_basic_config(config, "Detect") == (True, "")

    def test_the_component_check_matches_its_docstring(self):
        assert is_single_path_component("exp")
        assert is_single_path_component("exp.v2")
        assert not is_single_path_component("..")
        assert not is_single_path_component(".")
        assert not is_single_path_component("a/b")
        assert not is_single_path_component("C:/runs")
        assert not is_single_path_component("")


class TestIsInsideDirectory:
    def test_inside_and_outside(self, tmp_path):
        project = tmp_path / "runs"
        project.mkdir()
        (project / "exp").mkdir()
        outside = tmp_path / "labels"
        outside.mkdir()

        assert is_inside_directory(str(project / "exp"), str(project))
        assert not is_inside_directory(str(outside), str(project))

    def test_the_directory_itself_and_a_sibling_prefix_do_not_count(
        self, tmp_path
    ):
        project = tmp_path / "runs"
        project.mkdir()
        sibling = tmp_path / "runs_extra"
        sibling.mkdir()

        # Deleting the project root is not "overwriting a run", and
        # "runs_extra" only shares a prefix.
        assert not is_inside_directory(str(project), str(project))
        assert not is_inside_directory(str(sibling), str(project))


class _RecordingDialogs:
    """Stand-in for QMessageBox: records the kind, answers as told."""

    class StandardButton:
        # Ints, not labels: the caller combines them with "|".
        Yes = 1
        No = 2

    class Icon:
        Warning = "warning"
        Critical = "critical"
        Question = "question"

    def __init__(self, answer=StandardButton.No):
        self.calls = []
        self.answer = answer

    def warning(self, *args, **kwargs):
        self.calls.append("warning")
        return None

    def question(self, *args, **kwargs):
        self.calls.append("question")
        return self.answer


def _overwrite_stub():
    """A stub that can still run the real helpers the guards call.

    ``_confirm_overwrite`` delegates its wording and its listing to two other
    methods, so an unbound call needs them bound onto the stand-in.
    """
    from types import SimpleNamespace

    logged = []
    stub = SimpleNamespace(
        tr=lambda text, *a, **k: text,
        append_training_log=logged.append,
    )
    stub._refuse_overwrite = (
        lambda *a, **k: UltralyticsDialog._refuse_overwrite(stub, *a, **k)
    )
    stub._describe_dir_contents = (
        lambda *a, **k: UltralyticsDialog._describe_dir_contents(stub, *a, **k)
    )
    return stub, logged


class TestOverwriteGuard:
    def test_a_directory_outside_the_project_is_refused(
        self, tmp_path, monkeypatch
    ):
        project = tmp_path / "runs"
        project.mkdir()
        outside = tmp_path / "my_annotations"
        outside.mkdir()
        (outside / "img0.json").write_text("{}", encoding="utf-8")

        dialogs = _RecordingDialogs()
        monkeypatch.setattr(dialog_module, "QMessageBox", dialogs)
        removed = []
        monkeypatch.setattr(
            dialog_module,
            "shutil",
            type("S", (), {"rmtree": staticmethod(removed.append)}),
        )
        stub, logged = _overwrite_stub()

        result = UltralyticsDialog._confirm_overwrite(
            stub, str(outside), str(project)
        )

        assert result is False
        assert removed == []
        # Refused with an explanation, and never by asking a question whose
        # "yes" would delete it.
        assert dialogs.calls == ["warning"]
        assert (outside / "img0.json").exists()
        assert any("Refused to overwrite" in entry for entry in logged)

    def test_a_directory_without_run_markers_is_refused(
        self, tmp_path, monkeypatch
    ):
        project = tmp_path / "runs"
        (project / "labels").mkdir(parents=True)
        for index in range(3):
            (project / "labels" / f"{index}.json").write_text(
                "{}", encoding="utf-8"
            )

        dialogs = _RecordingDialogs()
        monkeypatch.setattr(dialog_module, "QMessageBox", dialogs)
        removed = []
        monkeypatch.setattr(
            dialog_module,
            "shutil",
            type("S", (), {"rmtree": staticmethod(removed.append)}),
        )
        stub, _ = _overwrite_stub()

        result = UltralyticsDialog._confirm_overwrite(
            stub, str(project / "labels"), str(project)
        )

        assert result is False
        assert removed == []
        assert dialogs.calls == ["warning"]
        assert (project / "labels" / "0.json").exists()

    def test_a_real_run_directory_still_reaches_the_question(
        self, tmp_path, monkeypatch
    ):
        project = tmp_path / "runs"
        run = project / "exp"
        (run / "weights").mkdir(parents=True)
        (run / "weights" / "best.pt").write_text("w", encoding="utf-8")

        dialogs = _RecordingDialogs(answer=_RecordingDialogs.StandardButton.No)
        monkeypatch.setattr(dialog_module, "QMessageBox", dialogs)
        removed = []
        monkeypatch.setattr(
            dialog_module,
            "shutil",
            type("S", (), {"rmtree": staticmethod(removed.append)}),
        )
        stub, _ = _overwrite_stub()

        result = UltralyticsDialog._confirm_overwrite(
            stub, str(run), str(project)
        )

        # The guards are additive: a real run still gets the usual prompt, and
        # answering No still deletes nothing.
        assert dialogs.calls == ["question"]
        assert result is False
        assert removed == []

    def test_yes_removes_the_run_directory(self, tmp_path, monkeypatch):
        project = tmp_path / "runs"
        run = project / "exp"
        (run / "weights").mkdir(parents=True)
        (run / "weights" / "best.pt").write_text("w", encoding="utf-8")

        dialogs = _RecordingDialogs(
            answer=_RecordingDialogs.StandardButton.Yes
        )
        monkeypatch.setattr(dialog_module, "QMessageBox", dialogs)
        removed = []
        monkeypatch.setattr(
            dialog_module,
            "shutil",
            type("S", (), {"rmtree": staticmethod(removed.append)}),
        )
        stub, _ = _overwrite_stub()

        result = UltralyticsDialog._confirm_overwrite(
            stub, str(run), str(project)
        )

        assert result is True
        assert removed == [str(run)]

    @pytest.mark.parametrize("marker", ["weights", "args.yaml", "results.csv"])
    def test_each_run_marker_is_enough(self, tmp_path, marker):
        run = tmp_path / "exp"
        run.mkdir()
        if marker == "weights":
            (run / marker).mkdir()
        else:
            (run / marker).write_text("x", encoding="utf-8")

        assert looks_like_training_run(str(run))

    def test_a_plain_directory_is_not_a_run(self, tmp_path):
        plain = tmp_path / "labels"
        plain.mkdir()
        (plain / "a.json").write_text("{}", encoding="utf-8")

        assert not looks_like_training_run(str(plain))
        assert not looks_like_training_run("")


class TestDatasetSkips:
    def test_nothing_to_report_means_nothing_to_report(self):
        assert dataset_skips({}) == []
        assert dataset_skips(None) == []

    def test_unreadable_files_block_and_dropped_shapes_do_not(self):
        report = {
            "unreadable_labels": ["a.json"],
            "conversion_errors": [{"label": "b.json", "error": "KeyError: x"}],
            "dropped_shapes": {"polygon is not part of a hbb export": 3},
        }

        skips = {
            kind: (count, details)
            for kind, count, details in dataset_skips(report)
        }

        assert skips["unreadable"][0] == 1
        assert skips["failed"][0] == 1
        assert skips["failed"][1] == ["b.json"]
        assert skips["dropped_shapes"][0] == 3
        assert is_blocking_dataset_skip("unreadable")
        assert is_blocking_dataset_skip("failed")
        assert not is_blocking_dataset_skip("dropped_shapes")


class _StubButton:
    __slots__ = ("text", "role")

    def __init__(self, text, role):
        self.text = text
        self.role = role


class _StubMessageBox:
    """Answers by role, and records what it was asked.

    ``exec()`` presses the RejectRole button (the one that does not train);
    the static entry points answer whatever the class attribute says, so a
    test can flip one decision without rebuilding the object.
    """

    ButtonRole = type(
        "ButtonRole",
        (),
        {
            "AcceptRole": "accept",
            "RejectRole": "reject",
            "DestructiveRole": "destructive",
        },
    )
    Icon = type("Icon", (), {"Warning": "warning", "Critical": "critical"})
    StandardButton = type("StandardButton", (), {"Yes": 1, "No": 2})

    answer = StandardButton.No
    last_question = None

    def __init__(self, parent=None):
        self.text = ""
        self.buttons = []
        self._clicked = None

    @classmethod
    def question(cls, parent, title, text, *args, **kwargs):  # noqa: N802
        cls.last_question = text
        return cls.answer

    @classmethod
    def warning(cls, *args, **kwargs):  # noqa: N802
        cls.last_question = args[-1] if args else ""
        return None

    def setIcon(self, icon):  # noqa: N802
        self.icon = icon

    def setWindowTitle(self, title):  # noqa: N802
        self.title = title

    def setText(self, text):  # noqa: N802
        self.text = text

    def addButton(self, text, role=None):  # noqa: N802
        button = _StubButton(
            text if isinstance(text, str) else str(text), role
        )
        self.buttons.append(button)
        return button

    def setDefaultButton(self, button):  # noqa: N802
        self.default_button = button

    def exec(self):
        self._clicked = next(
            (b for b in self.buttons if b.role == self.ButtonRole.RejectRole),
            None,
        )

    def clickedButton(self):  # noqa: N802
        return self._clicked


_APP = None


def _ensure_app():
    """One QApplication for the whole session, held so it cannot be collected.

    A QApplication that goes out of scope while widgets built from it are
    still alive takes the interpreter down with it (no traceback, no exit
    code a test can assert on), so the reference lives at module level - the
    same reason the sibling config-form tests keep theirs on the class.
    """
    global _APP
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or QApplication([])
    return _APP


def _build_dialog(tmp_path, monkeypatch):
    """A real ``UltralyticsDialog`` with both tabs built and no real dialogs.

    Returns ``(parent, dialog)``. The parent must be held by the caller: a
    QObject parent that goes out of scope takes the dialog with it.
    """
    from PyQt6.QtWidgets import QWidget

    import anylabeling.resources.resources  # noqa: F401
    from anylabeling.views.training.ultralytics_dialog import UltralyticsDialog

    _ensure_app()
    # The dialog reads its config through module-level names; the autouse
    # conftest fixture leaves ``current_config_file`` at None, so these have
    # to be stubbed before the constructor runs (same three the sibling
    # config-form test patches).
    monkeypatch.setattr(dialog_module, "get_config", lambda: {"training": {}})
    monkeypatch.setattr(dialog_module, "load_config", lambda: {})
    monkeypatch.setattr(
        dialog_module,
        "get_trainer_root_dir",
        lambda: str(tmp_path / "trainer"),
    )

    parent = QWidget()
    parent.image_list = []
    parent.output_dir = str(tmp_path)
    parent.supported_shape = ["rectangle"]
    dialog = UltralyticsDialog(parent)
    # Both tabs are built on demand; the train tab owns the buttons the
    # handlers below touch.
    dialog.ensure_config_tab_initialized()
    dialog.ensure_train_tab_initialized()
    dialog.selected_task_type = "Detect"
    # ``QMessageBox`` is imported by name into the dialog module *and* reached
    # as ``QtWidgets.QMessageBox``; both names have to point at the stub.
    _StubMessageBox.last_question = None
    _StubMessageBox.answer = _StubMessageBox.StandardButton.No
    monkeypatch.setattr(dialog_module, "QMessageBox", _StubMessageBox)
    monkeypatch.setattr(
        dialog_module.QtWidgets, "QMessageBox", _StubMessageBox
    )
    return parent, dialog


class TestTheGuardRunsBeforeTrainingStarts:
    """The wiring, not just the helper: a guard nobody calls protects nothing."""

    @pytest.fixture
    def dialog_and_records(self, tmp_path, monkeypatch):
        parent, dialog = _build_dialog(tmp_path, monkeypatch)
        started = []
        monkeypatch.setattr(
            dialog, "get_training_args", lambda *a, **k: {"data": "x"}
        )
        monkeypatch.setattr(
            dialog,
            "_start_training_after_args",
            lambda args: started.append(args),
        )
        return parent, dialog, started, tmp_path

    def test_a_clean_dataset_starts_the_run(self, dialog_and_records):
        _parent, dialog, started, tmp_path = dialog_and_records
        dataset = tmp_path / "ds"
        dataset.mkdir()
        dialog._dataset_report = {}
        dialog._dataset_pending_config = {"basic": {}, "checkpoint": {}}

        dialog._on_dataset_preparation_finished(str(dataset), "")

        assert started, "a dataset with nothing to report must still train"

    def test_an_unreadable_label_stops_the_run_until_it_is_acknowledged(
        self, dialog_and_records
    ):
        _parent, dialog, started, tmp_path = dialog_and_records
        dataset = tmp_path / "ds"
        dataset.mkdir()
        dialog._dataset_report = {
            "unreadable_labels": [str(tmp_path / "broken.json")],
            "unreadable_labels_count": 1,
        }
        dialog._dataset_pending_config = {"basic": {}, "checkpoint": {}}

        dialog._on_dataset_preparation_finished(str(dataset), "")

        # The stub presses the rejection button, so nothing trains and the
        # status does not stay stuck on "preparing".
        assert started == []
        assert dialog.training_status == "idle"


class TestClassesFilterIsChecked:
    """``classes`` out of range used to reach ultralytics, which trains on nothing."""

    @pytest.mark.parametrize("value", [[0, 1], "0, 1", [1], None, ""])
    def test_values_the_dataset_supports_pass(self, value):
        assert validate_classes(value, ["cat", "dog"]) == (True, "")

    @pytest.mark.parametrize("value", [[2], "2", [5], [0, 9]])
    def test_indexes_past_the_last_class_are_refused(self, value):
        is_valid, message = validate_classes(value, ["cat", "dog"])

        assert is_valid is False
        assert "out of range" in message

    def test_unknown_names_are_not_an_error(self):
        # Nothing to check against is not the same as a bad value: the data
        # config may be empty while the labels carry the classes.
        assert validate_classes([7], []) == (True, "")

    def test_a_filter_without_a_dataset_is_left_alone(self):
        assert validate_classes("", ["cat"]) == (True, "")

    def test_the_stub_still_catches_a_bad_index_in_the_dialog(
        self, tmp_path, monkeypatch
    ):
        _parent, dialog = _build_dialog(tmp_path, monkeypatch)
        data_file = tmp_path / "classes.yaml"
        data_file.write_text(
            yaml.safe_dump({"names": {0: "cat", 1: "dog"}}), encoding="utf-8"
        )
        config = {
            "basic": {
                "project": str(tmp_path / "runs"),
                "name": "exp",
                "data": str(data_file),
            },
            "train": {"classes": [5]},
        }
        monkeypatch.setattr(dialog, "get_current_config", lambda: config)

        dialog.start_training_from_train_tab()

        # Refused at the door: no dataset build was kicked off, so the status
        # never moved to "preparing" and no run was committed.
        assert dialog.training_status == "idle"
        assert dialog._dataset_pending_config is None
        assert "out of range" in (_StubMessageBox.last_question or "")


class TestStaleOnnxExport:
    """用于自动标注 must not hand back the model from before the last resume."""

    def test_a_fresh_artifact_is_reused(self, tmp_path):
        weights = tmp_path / "best.pt"
        onnx = tmp_path / "best.onnx"
        weights.write_text("w", encoding="utf-8")
        onnx.write_text("o", encoding="utf-8")
        os.utime(weights, (1000, 1000))
        os.utime(onnx, (2000, 2000))

        assert is_fresh_export(str(onnx), str(weights))

    def test_an_artifact_older_than_the_weights_is_stale(self, tmp_path):
        weights = tmp_path / "best.pt"
        onnx = tmp_path / "best.onnx"
        weights.write_text("w", encoding="utf-8")
        onnx.write_text("o", encoding="utf-8")
        os.utime(onnx, (1000, 1000))
        os.utime(weights, (2000, 2000))

        assert not is_fresh_export(str(onnx), str(weights))

    def test_a_missing_artifact_is_not_fresh(self, tmp_path):
        weights = tmp_path / "best.pt"
        weights.write_text("w", encoding="utf-8")

        assert not is_fresh_export(str(tmp_path / "best.onnx"), str(weights))
        assert not is_fresh_export("", str(weights))


class TestRunMetadataOnStop:
    """A stopped run is a run: it gets a record and a status in the table."""

    def test_a_stopped_run_writes_its_record(self, tmp_path, monkeypatch):
        _parent, dialog = _build_dialog(tmp_path, monkeypatch)
        run_dir = tmp_path / "runs" / "detect" / "exp"
        run_dir.mkdir(parents=True)
        dialog.current_project_path = str(run_dir)
        dialog._last_dataset_manifest = {}
        dialog._last_train_args = {"data": "x", "epochs": 10}

        written = dialog.write_run_metadata(status="stopped")

        assert written
        meta = json.loads(open(written, encoding="utf-8").read())
        assert meta["status"] == "stopped"
        assert meta["train_args"]["epochs"] == 10

    def test_the_history_reports_the_status(self, tmp_path, monkeypatch):
        _parent, dialog = _build_dialog(tmp_path, monkeypatch)
        runs_root = tmp_path / "runs"
        run_dir = runs_root / "detect" / "exp"
        run_dir.mkdir(parents=True)
        dialog.current_project_path = str(run_dir)
        dialog._last_dataset_manifest = {}
        dialog._last_train_args = {}
        dialog.write_run_metadata(status="stopped")

        rows = run_history.collect_run_history(str(runs_root))["rows"]

        assert [row["status"] for row in rows] == ["stopped"]
        header = run_history.format_history_rows([])[0]
        assert "状态" in header
        assert run_history.format_history_rows(rows)[1][
            header.index("状态")
        ] == ("stopped")


class TestExportDependencyConsent:
    """pip must not run because an export was clicked."""

    def test_nothing_missing_means_no_prompt(self, tmp_path, monkeypatch):
        _parent, dialog = _build_dialog(tmp_path, monkeypatch)
        monkeypatch.setattr(
            dialog_module, "get_export_validator", lambda _: (lambda: [])
        )

        assert dialog._confirm_export_dependencies("onnx") is True
        assert _StubMessageBox.last_question is None

    def test_declining_cancels_instead_of_installing(
        self, tmp_path, monkeypatch
    ):
        _parent, dialog = _build_dialog(tmp_path, monkeypatch)
        monkeypatch.setattr(
            dialog_module,
            "get_export_validator",
            lambda _: (lambda: ["onnx>=1.15.0"]),
        )
        _StubMessageBox.answer = _StubMessageBox.StandardButton.No

        assert dialog._confirm_export_dependencies("onnx") is False
        # The prompt carries the command that actually works, including in a
        # packaged build that cannot pip-install into itself.
        assert "pip install onnx>=1.15.0" in _StubMessageBox.last_question

    def test_accepting_allows_the_install(self, tmp_path, monkeypatch):
        _parent, dialog = _build_dialog(tmp_path, monkeypatch)
        monkeypatch.setattr(
            dialog_module,
            "get_export_validator",
            lambda _: (lambda: ["onnx>=1.15.0"]),
        )
        _StubMessageBox.answer = _StubMessageBox.StandardButton.Yes

        assert dialog._confirm_export_dependencies("onnx") is True


class TestInstallIsNotAttemptedInAPackagedBuild:
    def test_a_frozen_build_reports_instead_of_running_pip(self, monkeypatch):
        monkeypatch.setattr(validators.sys, "frozen", True, raising=False)
        calls = []
        monkeypatch.setattr(
            validators.subprocess,
            "Popen",
            lambda *a, **k: calls.append(a),
        )

        success, _stdout, stderr = validators.install_packages_with_timeout(
            ["onnx"]
        )

        assert success is False
        assert calls == [], "a frozen build cannot install into itself"
        assert "packaged build" in stderr

    def test_the_default_timeout_fits_a_download(self):
        assert validators.DEFAULT_INSTALL_TIMEOUT >= 120
