"""Shortcut settings use the same Chinese names as the F1 sheet."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from jllabeling.views.labeling.settings.schema import _shortcut_label


def test_plain_shortcut_keys_are_chinese():
    assert _shortcut_label("auto_run") == "对所有图片自动标注"
    assert _shortcut_label("auto_label") == "自动标注"


def test_auto_labeling_keys_are_chinese():
    assert _shortcut_label("auto_labeling_add_point") == "自动标注：加提示点"
    assert (
        _shortcut_label("auto_labeling_finish_object")
        == "自动标注：完成当前对象"
    )


def test_unknown_keys_keep_the_readable_fallback():
    assert _shortcut_label("some_new_action") == "Some New Action"
