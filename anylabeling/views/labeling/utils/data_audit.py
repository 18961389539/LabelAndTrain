"""Dataset consistency audit.

One-click scan of the currently opened folder for:
- unlabeled images (no label json)
- empty label files (json exists but shapes == [])
- corrupted label files (unreadable / malformed json)
- orphan label files (json without a matching image)
- images worth reviewing, ranked by model uncertainty
- class / scale balancing advice

Results are shown in a dialog; double-clicking an image row jumps to it.
"""

import json
import os
import os.path as osp

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QLabel,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from anylabeling.views.labeling.logger import logger
from anylabeling.views.labeling.widgets import Popup
from anylabeling.views.labeling.utils.active_learning import (
    image_uncertainty,
    load_thresholds,
    needs_review,
)
from anylabeling.views.labeling.utils.data_intel import (
    analyze_distribution,
    suggest_balancing,
)
from anylabeling.views.labeling.utils.qt import new_icon_path
from anylabeling.views.labeling.utils.quality import (
    IMBALANCE_MIN_MAJORITY,
    IMBALANCE_RATIO,
    inspect_shape_quality,
    json_txt_mismatch,
)

CATEGORY_ORDER = (
    "unlabeled",
    "review",
    "empty",
    "corrupted",
    "orphan",
    "tiny",
    "edge",
    "balance",
    "imbalance",
    "json_txt",
)

CATEGORY_TITLES = {
    "unlabeled": "无标注的图片",
    "review": "优先复核（按不确定性排序）",
    "empty": "空标注文件（shapes 为空）",
    "corrupted": "损坏的标注文件",
    "orphan": "孤立的标注文件（对应图片不存在）",
    "tiny": "含极小框的图片",
    "edge": "含贴边框的图片",
    "balance": "配平建议",
    "imbalance": "类别数量失衡",
    "json_txt": "JSON 与 YOLO txt 不一致",
}

# How many "most uncertain" images the audit surfaces.
REVIEW_LIMIT = 50


def audit_dataset(image_list, image_dir):
    """Scan ``image_dir`` and categorize consistency issues.

    Args:
        image_list: Image paths currently opened in the file panel.
        image_dir: Folder that holds the label json files.

    Returns:
        dict with keys in ``CATEGORY_ORDER``. ``imbalance`` holds
        human-readable class-count lines; other keys are file paths.
    """
    results = {key: [] for key in CATEGORY_ORDER}
    if not image_dir or not osp.isdir(image_dir):
        return results

    images = [p for p in (image_list or []) if osp.exists(p)]
    if not images:
        return results

    image_basenames = {
        osp.splitext(osp.basename(p))[0] for p in images
    }
    class_counts = {}
    thresholds = load_thresholds(image_dir)
    review_scores = []
    distribution_entries = []

    for image_path in images:
        base = osp.splitext(osp.basename(image_path))[0]
        label_file = osp.join(image_dir, base + ".json")
        if not osp.exists(label_file):
            results["unlabeled"].append(image_path)
            distribution_entries.append((image_path, None))
            continue
        try:
            with open(label_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict) or "shapes" not in data:
                results["corrupted"].append(image_path)
                distribution_entries.append((image_path, None))
                continue
            distribution_entries.append((image_path, data))
            if not data["shapes"]:
                results["empty"].append(image_path)
            else:
                shapes = data.get("shapes") or []
                stats = inspect_shape_quality(
                    shapes,
                    int(data.get("imageWidth") or 0),
                    int(data.get("imageHeight") or 0),
                )
                if stats["tiny"]:
                    results["tiny"].append(image_path)
                if stats["edge"]:
                    results["edge"].append(image_path)
                for label, count in stats["labels"].items():
                    class_counts[label] = class_counts.get(label, 0) + count
                if needs_review(shapes, thresholds=thresholds):
                    review_scores.append(
                        (image_path, image_uncertainty(shapes, thresholds=thresholds))
                    )
            if json_txt_mismatch(label_file, data):
                results["json_txt"].append(image_path)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            logger.warning(f"Audit: failed to read {label_file}: {e}")
            results["corrupted"].append(image_path)

    review_scores.sort(key=lambda item: (-item[1], item[0]))
    results["review"] = [path for path, _ in review_scores[:REVIEW_LIMIT]]

    if distribution_entries:
        advice = suggest_balancing(analyze_distribution(distribution_entries))
        # A single "nothing to fix" line is not worth a category.
        if not (len(advice) == 1 and "未见明显问题" in advice[0]):
            results["balance"] = advice

    if class_counts:
        majority = max(class_counts.values())
        if majority >= IMBALANCE_MIN_MAJORITY:
            for label, count in sorted(class_counts.items()):
                if count <= 0:
                    continue
                if majority / max(count, 1) >= IMBALANCE_RATIO:
                    results["imbalance"].append(
                        f"{label}：{count}（最多类 {majority}）"
                    )

    for name in sorted(os.listdir(image_dir)):
        if not name.endswith(".json"):
            continue
        base = osp.splitext(name)[0]
        if base not in image_basenames:
            results["orphan"].append(osp.join(image_dir, name))

    return results


def run_data_audit(parent):
    """Scan the folder currently opened in the main window.

    ``parent`` is the LabelWidget instance; ``parent.image_list`` /
    ``parent.filename`` provide the scope, and double-clicking a result
    row calls ``parent.load_file`` to jump to that image.
    """
    if not getattr(parent, "filename", None):
        popup = Popup(
            parent.tr("请先打开一个图片文件夹再进行数据体检。"),
            parent,
            icon=new_icon_path("warning", "svg"),
        )
        popup.show_popup(parent, popup_height=65, position="center")
        return

    image_dir = parent.output_dir or osp.dirname(parent.filename)
    results = audit_dataset(parent.image_list, image_dir)
    total_issues = sum(len(v) for v in results.values())

    dialog = QDialog(parent)
    dialog.setWindowTitle(parent.tr("数据体检"))
    dialog.setMinimumSize(560, 480)
    layout = QVBoxLayout(dialog)

    if total_issues == 0:
        summary = parent.tr("体检通过：未发现问题。")
        label = QLabel(summary)
        label.setStyleSheet("padding: 24px; font-size: 14px;")
        layout.addWidget(label)
    else:
        summary = parent.tr("发现 %1 个问题：").replace(
            "%1", str(total_issues)
        )
        label = QLabel(summary)
        label.setStyleSheet("padding: 6px 2px; font-weight: 600;")
        layout.addWidget(label)

        tree = QTreeWidget()
        tree.setHeaderLabels(["类别", "文件"])
        tree.setColumnWidth(0, 240)
        tree.setRootIsDecorated(True)
        for key in CATEGORY_ORDER:
            items = results[key]
            if not items:
                continue
            root = QTreeWidgetItem(
                [f"{CATEGORY_TITLES[key]}（{len(items)}）", ""]
            )
            for path in items:
                if key in ("imbalance", "balance"):
                    child = QTreeWidgetItem([path, ""])
                    image_path = ""
                else:
                    child = QTreeWidgetItem(
                        [osp.basename(path), path]
                    )
                    image_path = path if key != "orphan" else ""
                child.setData(0, Qt.ItemDataRole.UserRole, image_path)
                root.addChild(child)
            tree.addTopLevelItem(root)
            root.setExpanded(True)

        def on_double_click(item, _column):
            image_path = item.data(0, Qt.ItemDataRole.UserRole)
            if image_path and osp.exists(image_path):
                dialog.accept()
                parent.load_file(image_path)

        tree.itemDoubleClicked.connect(on_double_click)
        layout.addWidget(tree)

    hint = QLabel(parent.tr("双击条目可跳转到对应图片。"))
    hint.setStyleSheet("color: #86868b; padding: 4px 2px;")
    layout.addWidget(hint)

    dialog.exec()
