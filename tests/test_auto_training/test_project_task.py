"""任务类型在项目与训练窗口之间双向流动。

正向：项目声明了 Segment，训练窗口打开时就预选 Segment —— 选错任务
类型的代价是"跑完一整轮才发现数据集转换成空"。
反向：训练时选定的类型写回项目，所以在这里改过主意，下次打开还记得。

只对有项目清单的目录生效：只是被打开过的文件夹保持"什么都没选"，
因为在这里替用户猜一个任务类型，猜错的代价太高。
"""

import json
import os
import tempfile
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QWidget

from anylabeling.views.labeling import project_model
from anylabeling.views.training import ultralytics_dialog as dialog_module
from anylabeling.views.training.ultralytics_dialog import UltralyticsDialog


def _labeled_images(folder, count=20):
    """``count`` images with one rectangle each — clears the Data gate."""
    images = []
    for index in range(count):
        image = os.path.join(folder, f"img{index}.jpg")
        open(image, "wb").close()
        with open(
            os.path.join(folder, f"img{index}.json"), "w", encoding="utf-8"
        ) as handle:
            json.dump(
                {
                    "shapes": [
                        {
                            "label": "cat",
                            "shape_type": "rectangle",
                            "points": [[1, 1], [5, 5]],
                        }
                    ],
                    "flags": {},
                },
                handle,
            )
        images.append(image)
    return images


class TestProjectTaskRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "trainer")
        self._patchers = {
            "get_trainer_root_dir": dialog_module.get_trainer_root_dir,
            "load_config": dialog_module.load_config,
            "get_config": dialog_module.get_config,
            "DEVICE_OPTIONS": dialog_module.DEVICE_OPTIONS,
        }
        dialog_module.get_trainer_root_dir = lambda: self.root
        dialog_module.load_config = lambda: {}
        dialog_module.get_config = lambda: {"training": {}}
        dialog_module.DEVICE_OPTIONS = ["cpu"]

        self.dataset_dir = os.path.join(self.tmp.name, "dataset")
        os.makedirs(self.dataset_dir)
        self.image_list = _labeled_images(self.dataset_dir)
        # 造一份项目清单，然后在构造对话框之前改它的 task。
        project_model.create(self.dataset_dir, name="螺丝划痕", task="Detect")
        self.dialogs = []

    def tearDown(self):
        for name, original in self._patchers.items():
            setattr(dialog_module, name, original)
        for dialog in self.dialogs:
            dialog.deleteLater()
        self.tmp.cleanup()

    def _set_project_task(self, task):
        record = project_model.load_record(self.dataset_dir)
        record["task"] = task
        project_model.save_record(self.dataset_dir, record)

    def _build_dialog(self):
        parent = QWidget()
        parent.image_list = self.image_list
        parent.output_dir = self.dataset_dir
        parent.supported_shape = ["rectangle", "polygon", "point"]
        # Held on the test: a QObject parent that goes out of scope takes
        # the dialog (and every widget in it) down with it.
        self.parent = parent
        dialog = UltralyticsDialog(parent)
        self.dialogs.append(dialog)
        return dialog

    # -- 项目 → 窗口 -------------------------------------------------------

    def test_a_declared_task_is_preselected(self):
        self._set_project_task("Segment")

        dialog = self._build_dialog()

        self.assertEqual(dialog.selected_task_type, "Segment")

    def test_detect_is_preselected_too(self):
        dialog = self._build_dialog()
        self.assertEqual(dialog.selected_task_type, "Detect")

    def test_a_plain_folder_still_selects_nothing(self):
        """没有清单的目录保持改造前的行为 —— 不替用户猜任务类型。"""
        plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(plain)
        self.image_list = _labeled_images(plain, count=20)

        dialog = self._build_dialog()

        self.assertIsNone(dialog.selected_task_type)

    def test_a_corrupt_record_falls_back_to_the_default_task(self):
        """清单损坏时 describe 给默认值，预选不会炸。"""
        path = os.path.join(self.dataset_dir, ".jllabel", "project.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("{ not json")

        dialog = self._build_dialog()

        self.assertEqual(dialog.selected_task_type, "Detect")

    # -- 窗口 → 项目 -------------------------------------------------------

    def test_the_committed_task_is_written_back(self):
        dialog = self._build_dialog()
        self.assertEqual(dialog.selected_task_type, "Detect")

        # 用户在训练窗口里改了主意。
        dialog.on_task_type_selected("Segment")
        dialog._save_project_train_prefs({"basic": {}, "train": {}})

        self.assertEqual(
            project_model.describe(self.dataset_dir)["task"], "Segment"
        )

    def test_a_plain_folder_gets_a_record_carrying_the_task(self):
        plain = os.path.join(self.tmp.name, "plain")
        os.makedirs(plain)
        self.image_list = _labeled_images(plain, count=20)

        dialog = self._build_dialog()
        dialog.on_task_type_selected("Pose")
        dialog._save_project_train_prefs({"basic": {}})

        described = project_model.describe(plain)
        self.assertTrue(described["has_record"])
        self.assertEqual(described["task"], "Pose")

    def test_nothing_is_written_without_a_committed_task(self):
        """没选任务类型就不碰 task 字段（老行为不变）。"""
        dialog = self._build_dialog()
        dialog.on_task_type_selected("Detect")  # toggle 掉：又变成未选
        self.assertIsNone(dialog.selected_task_type)

        dialog._save_project_train_prefs({"basic": {}})

        self.assertEqual(
            project_model.load_record(self.dataset_dir)["task"], "Detect"
        )


if __name__ == "__main__":
    unittest.main()
