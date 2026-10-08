"""Switching folders must not leave the previous classes in the panel.

``LabelingWidget._yolo_class_names`` builds the YOLO id map from the labels
dock, so a stale list silently remaps every exported label.  A folder without
a ``classes.txt`` used to leave the panel exactly as the previous folder had
left it — and the project-record fallback could not correct it, because it
only fires when the panel is empty.  The panel now falls back to
``config.labels`` instead, which is what the original behaviour intended.
"""

from types import SimpleNamespace

from anylabeling.views.labeling import project_settings
from anylabeling.views.labeling.label_widget import LabelingWidget


class _Panel:
    def __init__(self, names=()):
        self.names = list(names)

    def count(self):
        return len(self.names)

    def item(self, row):
        if row >= len(self.names):
            return None
        label = self.names[row]
        return SimpleNamespace(data=lambda _role, label=label: label)

    def clear(self):
        self.names = []


class _LabelList:
    def __init__(self):
        self.cleared = False

    def clear(self):
        self.cleared = True


class _Dialog:
    def __init__(self):
        self.label_list = _LabelList()


def _widget(names=("cat", "dog"), configured=()):
    panel = _Panel(names)
    dialog = _Dialog()
    widget = SimpleNamespace(
        output_dir=None,
        unique_label_list=panel,
        label_dialog=dialog,
        _config={"labels": list(configured)},
    )
    widget._panel_label_names = lambda: list(panel.names)
    widget.load_labels = lambda labels, clear_existing=False: setattr(
        panel, "names", list(labels)
    )
    widget._reset_label_dialog_labels = lambda labels: None
    return widget, panel, dialog


class TestRestoreConfiguredClasses:
    def test_falls_back_to_the_configured_labels(self):
        widget, panel, _dialog = _widget(configured=("bird",))

        assert project_settings.restore_configured_classes(widget) is True
        assert panel.names == ["bird"]

    def test_clears_when_nothing_is_configured(self):
        widget, panel, dialog = _widget()

        assert project_settings.restore_configured_classes(widget) is True
        assert panel.names == []
        assert dialog.label_list.cleared is True

    def test_a_panel_that_already_matches_is_left_alone(self):
        widget, _panel, _dialog = _widget(configured=("cat", "dog"))

        assert project_settings.restore_configured_classes(widget) is False

    def test_a_widget_without_a_panel_is_tolerated(self):
        assert (
            project_settings.restore_configured_classes(SimpleNamespace())
            is False
        )


class TestFolderSwitch:
    def test_a_folder_without_classes_txt_falls_back_to_the_config(
        self, tmp_path
    ):
        widget, panel, _dialog = _widget(configured=("bird",))

        loaded = LabelingWidget._load_classes_from_folder(
            widget, str(tmp_path)
        )

        assert loaded == []
        assert panel.names == ["bird"]

    def test_a_folder_with_classes_txt_still_wins(self, tmp_path):
        (tmp_path / "classes.txt").write_text(
            "cat\ndog\nbird\n", encoding="utf-8"
        )
        widget, panel, _dialog = _widget(configured=("ignored",))

        loaded = LabelingWidget._load_classes_from_folder(
            widget, str(tmp_path)
        )

        assert loaded == ["cat", "dog", "bird"]
        assert panel.names == ["cat", "dog", "bird"]
