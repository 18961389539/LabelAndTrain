"""Acceptance harness: walk the machine checklist on a real display.

``scripts/smoke_widget_paths.py`` runs offscreen and asserts the wiring.
This one forces the *real* platform plugin, shows a real ``MainWindow``,
and photographs what ``reviews/project_work_machine_check_2026-10-10.md``
describes -- so the things that checklist is about (menu layout, dialog
wording, title bar, spacing) can be looked at rather than described.

Running it that way is worth the trouble: it caught a 2555-character
string of ``.ts`` markup rendering as the 文件 panel's title, which 1166
passing tests and 13 offscreen smoke steps had no way to notice.

A real window appears on screen for the few seconds this takes. Nothing
leaves the scratch directory: QSettings is redirected into it and the
work directory is set to it, so the machine's real configuration and its
recent-project list are untouched. Shots go to
``reviews/acceptance_shots/`` (git-ignored -- they date fast).

    python -u scripts/accept_project_work.py

Exit code 0 when every step passed, 1 otherwise.
"""

import json
import os
import shutil
import sys
import tempfile
import traceback
from types import SimpleNamespace

# A step that opens a modal blocks forever with nothing on screen to say
# so, and a hung run looks exactly like a slow one. Set ACCEPT_DUMP_STACK
# to have the stack printed and the process ended if a step stalls.
if os.environ.get("ACCEPT_DUMP_STACK"):
    import faulthandler

    faulthandler.enable()
    faulthandler.dump_traceback_later(45, exit=True)

# The real platform plugin -- the whole point is to look at the app on a
# display. An inherited value would quietly turn this into a second copy
# of the offscreen smoke run.
os.environ.pop("QT_QPA_PLATFORM", None)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

from PyQt6 import QtCore, QtGui, QtWidgets  # noqa: E402

TEMPLATE_CONFIG = os.path.join(
    REPO, "anylabeling", "configs", "jllabeling_config.yaml"
)
SHOT_DIR = os.path.join(REPO, "reviews", "acceptance_shots")
RESULTS = []


def step(name):
    def deco(fn):
        def run(ctx):
            try:
                fn(ctx)
                RESULTS.append((name, "OK", ""))
                print(f"[OK]   {name}", flush=True)
            except Exception as exc:  # noqa: BLE001
                RESULTS.append((name, "FAIL", repr(exc)))
                print(f"[FAIL] {name}: {exc!r}", flush=True)
                traceback.print_exc()

        return run

    return deco


def pump(app, ms=120):
    """Let the real event loop breathe; popups need a frame to paint."""
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(ms, loop.quit)
    loop.exec()
    app.processEvents()


def shoot(widget, app, name):
    """Photograph a widget, and say out loud what the OS title bar holds.

    A window manager draws the title bar outside the widget, so ``grab``
    cannot capture it -- the text would otherwise go unverified.
    """
    os.makedirs(SHOT_DIR, exist_ok=True)
    pump(app, 60)
    pix = widget.grab()
    pix.save(os.path.join(SHOT_DIR, name))
    print(f"       shot {name}  {pix.width()}x{pix.height()}", flush=True)
    if isinstance(widget, QtWidgets.QMainWindow):
        print(f"       标题栏：{widget.windowTitle()}", flush=True)


def shoot_menu(menu, app, anchor, name):
    """A QMenu only paints once it is shown: pop it, shoot it, close it."""
    os.makedirs(SHOT_DIR, exist_ok=True)
    menu.popup(anchor.mapToGlobal(QtCore.QPoint(40, 60)))
    pump(app, 220)
    pix = menu.grab()
    menu.close()
    pump(app, 60)
    pix.save(os.path.join(SHOT_DIR, name))
    print(f"       shot {name}  {pix.width()}x{pix.height()}", flush=True)


def install_auto_dismiss(app, notes):
    """Answer modal message boxes instead of waiting for a human.

    Production code blocks on ``exec()``. A step that reaches one would
    hang the run with nothing on screen to say why -- which is exactly
    what happened the first time this harness ran: opening a freshly
    created project raised 「还没有类别」 and the run sat there. The swap
    photographs the dialog, records what it said, and returns at once;
    ``clickedButton()`` is then ``None``, the same branch as 「稍后再说」.
    """
    original = QtWidgets.QMessageBox.exec
    seen_titles = set()

    def auto_exec(self):
        title = self.windowTitle()
        text = self.text()
        notes.append((title, text))
        first = (text.splitlines() or [""])[0]
        print(f"       弹窗：{title} / {first[:50]}", flush=True)
        # One shot per distinct dialog: 「还没有类别」 comes up on every
        # folder opened, and eleven copies of it say nothing.
        if title not in seen_titles:
            seen_titles.add(title)
            os.makedirs(SHOT_DIR, exist_ok=True)
            self.show()
            pump(app, 180)
            self.grab().save(
                os.path.join(SHOT_DIR, f"modal_{len(seen_titles):02d}.png")
            )
            self.close()
            pump(app, 60)
        return 0

    QtWidgets.QMessageBox.exec = auto_exec

    def restore():
        QtWidgets.QMessageBox.exec = original

    return restore


def make_images(tmp, count=3):
    """Real PNGs on disk, the first one with a label file already."""
    paths = []
    for i in range(count):
        img = QtGui.QImage(200, 120, QtGui.QImage.Format.Format_RGB32)
        img.fill(QtGui.QColor(30 + i * 40, 60, 90))
        path = os.path.join(tmp, f"img_{i}.png")
        img.save(path)
        paths.append(path)
    label = QtCore.QJsonDocument(
        {
            "version": "2.4.0",
            "flags": {},
            "shapes": [
                {
                    "label": "box",
                    "points": [[10, 10], [80, 60]],
                    "group_id": None,
                    "shape_type": "rectangle",
                    "flags": {},
                }
            ],
            "imagePath": "img_0.png",
            "imageData": None,
            "imageHeight": 120,
            "imageWidth": 200,
        }
    )
    with open(os.path.join(tmp, "img_0.json"), "w", encoding="utf-8") as fh:
        fh.write(
            label.toJson(QtCore.QJsonDocument.JsonFormat.Indented)
            .data()
            .decode()
        )
    return paths


def build_context(app):
    """A real MainWindow plus a scratch dataset for each step to use."""
    from anylabeling import config as app_config
    from anylabeling.views.labeling import (
        project_model,
        project_registry,
        project_settings,
    )
    from anylabeling.views.labeling.utils import project_view
    from anylabeling.views.labeling.widgets.project_dialog import (
        ProjectPropertiesDialog,
    )
    from anylabeling.views.mainwindow import MainWindow

    tmp = tempfile.mkdtemp(prefix="accept_project_work_")
    app_config.set_work_directory(tmp)
    config_copy = os.path.join(tmp, "accept_config.yaml")
    shutil.copy(TEMPLATE_CONFIG, config_copy)
    app_config.current_config_file = config_copy

    win = MainWindow(app, config=None)
    win.resize(1180, 780)
    win.move(80, 60)
    win.show()
    pump(app, 400)

    fresh = os.path.join(tmp, "fresh_project")
    os.makedirs(fresh)
    fresh_images = make_images(fresh)
    screws = os.path.join(tmp, "screws")
    os.makedirs(screws)
    screw_images = make_images(screws)
    plain = os.path.join(tmp, "plain")
    os.makedirs(plain)
    make_images(plain)

    return SimpleNamespace(
        app=app,
        tmp=tmp,
        win=win,
        widget=win.labeling_widget.view,
        fresh=fresh,
        fresh_images=fresh_images,
        screws=screws,
        screw_images=screw_images,
        plain=plain,
        project_model=project_model,
        project_registry=project_registry,
        project_settings=project_settings,
        project_view=project_view,
        ProjectPropertiesDialog=ProjectPropertiesDialog,
    )


@step("1. 文件菜单：第一项是「项目」子菜单，且分三段")
def s1_project_menu(ctx):
    widget, win, app = ctx.widget, ctx.win, ctx.app
    file_menu = widget.menus.file
    tops = file_menu.actions()
    assert tops, "File menu has no entries"
    first = tops[0]
    assert (
        first.menu() is not None
    ), f"the first File entry is {first.text()!r}, not a submenu"
    assert first.text().replace("&", "") == "项目", first.text()

    proj = first.menu()
    rows = []
    for act in proj.actions():
        if act.isSeparator():
            rows.append(("---", "", ""))
            continue
        rows.append(
            (
                act.text().replace("&", ""),
                act.shortcut().toString(),
                ">submenu" if act.menu() else "",
            )
        )
    print("       项目菜单：", flush=True)
    for text, key, kind in rows:
        print(f"         {text}   {key} {kind}".rstrip(), flush=True)

    texts = [row[0] for row in rows]
    for expected in (
        "新建项目…",
        "项目属性…",
        "关闭项目",
        "打开项目设置文件夹",
    ):
        assert expected in texts, (expected, texts)
    assert texts.count("---") == 2, texts
    assert any(row[2] for row in rows), "最近项目 submenu is missing"

    shoot(win, app, "01_window.png")
    shoot_menu(proj, app, win, "01_project_menu.png")


@step("2. 新建项目：属性对话框 + 保存后自动打开")
def s2_new_project(ctx):
    win, app, widget = ctx.win, ctx.app, ctx.widget
    fresh = ctx.fresh
    dialog = ctx.ProjectPropertiesDialog(
        win,
        name=ctx.project_model.default_name(fresh),
        root=fresh,
        title="新建项目",
    )
    dialog.show()
    pump(app, 220)
    shoot(dialog, app, "02a_new_project_dialog.png")

    labels = [lb.text() for lb in dialog.findChildren(QtWidgets.QLabel)]
    assert any(fresh in text for text in labels), labels
    radios = dialog.task_group.buttons()
    assert len(radios) == 4, [r.text() for r in radios]
    assert dialog.name_edit.text() == ctx.project_model.default_name(fresh)

    dialog.name_edit.setText("螺丝划痕")
    for button in radios:
        button.setChecked(button.property("task_kind") == "Segment")
    pump(app, 140)
    shoot(dialog, app, "02b_new_project_filled.png")

    values = dialog.values()
    assert values == {"name": "螺丝划痕", "task": "Segment"}, values
    dialog.accept()
    pump(app, 80)

    assert ctx.project_model.create(
        fresh, name=values["name"], task=values["task"]
    ), "create() refused a folder with no record"
    widget.import_image_folder(fresh)
    pump(app, 350)

    record = os.path.join(fresh, ".jllabel", "project.json")
    assert os.path.isfile(record), os.listdir(fresh)
    assert "螺丝划痕" in win.windowTitle(), win.windowTitle()
    shoot(win, app, "02c_opened_title.png")


@step("3. 已是项目的文件夹：拒绝覆盖")
def s3_no_overwrite(ctx):
    fresh, model = ctx.fresh, ctx.project_model
    assert model.has_record(fresh)
    before = model.describe(fresh)
    written = model.create(fresh, name="别的名字", task="Detect")
    assert written is False, "create() overwrote an existing record"
    after = model.describe(fresh)
    assert after["name"] == before["name"], (before, after)
    assert after["task"] == before["task"], (before, after)
    assert after["name"] == "螺丝划痕"


@step("4. 标题栏：没有清单的文件夹回退目录名")
def s4_title_plain_folder(ctx):
    ctx.widget.import_image_folder(ctx.plain)
    pump(ctx.app, 350)
    title = ctx.win.windowTitle()
    assert "[plain]" in title, title
    assert "[1/3]" in title, title
    shoot(ctx.win, ctx.app, "04_title_plain_folder.png")


@step("5. 关闭项目 + 续点：回到第 3 张")
def s5_close_and_resume(ctx):
    widget, win, app = ctx.widget, ctx.win, ctx.app
    widget.import_image_folder(ctx.fresh)
    pump(app, 350)
    widget.load_file(ctx.fresh_images[2])
    pump(app, 180)
    assert widget.filename == ctx.fresh_images[2]

    assert ctx.project_view.close_project(widget) is True
    pump(app, 220)
    assert widget.file_list_widget.count() == 0
    assert widget.filename is None
    assert "螺丝划痕" not in win.windowTitle(), win.windowTitle()
    shoot(win, app, "05a_after_close.png")

    widget.load_recent_dir(ctx.fresh)
    pump(app, 350)
    assert widget.filename == ctx.fresh_images[2], widget.filename
    shoot(win, app, "05b_resumed_on_third.png")


@step("6. 两个项目互切：各自回到自己的位置")
def s6_switch_between_projects(ctx):
    widget, win, app = ctx.widget, ctx.win, ctx.app
    assert ctx.project_model.create(ctx.screws, name="螺钉", task="Detect")
    widget.import_image_folder(ctx.fresh)
    pump(app, 300)
    widget.load_file(ctx.fresh_images[2])
    pump(app, 160)

    widget.import_image_folder(ctx.screws)
    pump(app, 300)
    widget.load_file(ctx.screw_images[1])
    pump(app, 160)

    widget.load_recent_dir(ctx.fresh)
    pump(app, 320)
    assert widget.filename == ctx.fresh_images[2], widget.filename
    shoot(win, app, "06a_back_to_first.png")

    widget.load_recent_dir(ctx.screws)
    pump(app, 320)
    assert widget.filename == ctx.screw_images[1], widget.filename
    shoot(win, app, "06b_back_to_second.png")


@step("7. 训练窗口预选项目任务，并写回项目")
def s7_task_reaches_trainer(ctx):
    widget, app = ctx.widget, ctx.app
    from anylabeling.views.training import ultralytics_dialog as dialog_mod
    from anylabeling.views.training.ultralytics_dialog import (
        UltralyticsDialog,
    )

    widget.import_image_folder(ctx.fresh)
    pump(app, 300)
    assert ctx.project_model.describe(ctx.fresh)["task"] == "Segment"

    stubs = {
        "get_trainer_root_dir": lambda: os.path.join(ctx.tmp, "trainer"),
        "load_config": lambda: {},
        "get_config": lambda: {"training": {}},
        "DEVICE_OPTIONS": ["cpu"],
    }
    originals = {name: getattr(dialog_mod, name) for name in stubs}
    for name, value in stubs.items():
        setattr(dialog_mod, name, value)
    dialog = None
    try:
        dialog = UltralyticsDialog(widget)
        dialog.show()
        pump(app, 500)
        shoot(dialog, app, "07a_training_data_page.png")
        assert (
            dialog.selected_task_type == "Segment"
        ), dialog.selected_task_type

        dialog.on_task_type_selected("Detect")
        dialog._save_project_train_prefs({"basic": {}})
        assert ctx.project_model.describe(ctx.fresh)["task"] == "Detect"
    finally:
        for name, original in originals.items():
            setattr(dialog_mod, name, original)
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
        pump(app, 120)


@step("8. 属性对话框改名：标题变、文件夹名不变")
def s8_rename_keeps_folder(ctx):
    win, app, widget = ctx.win, ctx.app, ctx.widget
    fresh = ctx.fresh
    widget.import_image_folder(fresh)
    pump(app, 300)
    described = ctx.project_model.describe(fresh)
    dialog = ctx.ProjectPropertiesDialog(
        win,
        name=described["name"],
        task=described["task"],
        root=fresh,
        title="项目属性",
    )
    dialog.show()
    pump(app, 220)
    shoot(dialog, app, "08a_project_properties.png")

    assert dialog.name_edit.text() == "螺丝划痕"
    dialog.name_edit.setText("划痕检测")
    values = dialog.values()
    dialog.accept()
    assert ctx.project_model.rename(fresh, values["name"])
    widget.update_progress_title()
    pump(app, 160)

    assert "划痕检测" in win.windowTitle(), win.windowTitle()
    assert os.path.isdir(fresh), "the folder itself moved or vanished"
    assert os.path.basename(os.path.normpath(fresh)) == "fresh_project"
    with open(
        os.path.join(fresh, ".jllabel", "project.json"), encoding="utf-8"
    ) as fh:
        on_disk = json.load(fh)
    assert on_disk["name"] == "划痕检测", on_disk
    shoot(win, app, "08b_renamed_title.png")


@step("9. 写失败被看见，且同一目录只报一次")
def s9_write_failure_is_visible(ctx):
    win, app, widget = ctx.win, ctx.app, ctx.widget
    settings = ctx.project_settings
    readonly = os.path.join(ctx.tmp, "readonly_project")
    os.makedirs(readonly)
    make_images(readonly)
    # A *file* named .jllabel: the write cannot succeed, and unlike chmod
    # on Windows it needs no privilege to arrange.
    with open(os.path.join(readonly, ".jllabel"), "w", encoding="utf-8") as fh:
        fh.write("not a directory\n")
    assert settings.update_values(readonly, labels=["a"]) is False

    seen = []
    original_show = settings._show_write_warning
    original_panel = widget._panel_label_names
    settings._show_write_warning = lambda w, d: seen.append(d)
    settings._WRITE_WARNED.clear()
    widget._panel_label_names = lambda: ["a"]
    try:
        widget.import_image_folder(readonly)
        pump(app, 300)
        settings.save_current_labels(widget, readonly)
        settings.save_current_labels(widget, readonly)
    finally:
        settings._show_write_warning = original_show
        widget._panel_label_names = original_panel
        settings._WRITE_WARNED.clear()

    assert len(seen) == 1, f"expected one warning, got {len(seen)}"
    shoot(win, app, "09a_readonly_open.png")

    # The real dialog, shown but not exec'd, for the wording.
    box = QtWidgets.QMessageBox(win)
    box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
    box.setWindowTitle("项目设置无法保存")
    box.setText(
        "无法把项目设置写入下面的目录（只读盘或没有写入权限）：\n"
        f"{readonly}\n\n"
        "本次会话中这个项目的标签列表与标注输出目录不会被记住。"
    )
    box.show()
    pump(app, 200)
    shoot(box, app, "09b_write_warning.png")
    box.close()
    pump(app, 80)


STEPS = (
    s1_project_menu,
    s2_new_project,
    s3_no_overwrite,
    s4_title_plain_folder,
    s5_close_and_resume,
    s6_switch_between_projects,
    s7_task_reaches_trainer,
    s8_rename_keeps_folder,
    s9_write_failure_is_visible,
)


def main():
    # Redirect everything that persists into the scratch dir *before* any
    # QSettings is built: the machine's real ini file must not learn about
    # this run any more than its recent-project list should.
    scratch = tempfile.mkdtemp(prefix="accept_qsettings_")
    QtCore.QSettings.setDefaultFormat(QtCore.QSettings.Format.IniFormat)
    QtCore.QSettings.setPath(
        QtCore.QSettings.Format.IniFormat,
        QtCore.QSettings.Scope.UserScope,
        scratch,
    )
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    # Startup does this before the window exists, and without it every
    # string whose source is English renders English -- which is most of
    # the File menu, and the one reused action inside the project menu.
    from anylabeling.resources import resources  # noqa: F401

    translator = QtCore.QTranslator()
    assert translator.load(
        ":/languages/translations/zh_CN.qm"
    ), "zh_CN catalog missing from the compiled resources"
    app.installTranslator(translator)

    modal_notes = []
    restore_auto_dismiss = install_auto_dismiss(app, modal_notes)
    ctx = build_context(app)

    for run_step in STEPS:
        run_step(ctx)

    print("\n--- 本次运行弹出的对话框（真实产品行为，脚本自动应答）---")
    if not modal_notes:
        print("    （无）")
    for title, text in modal_notes:
        print(f"    {title}：{(text.splitlines() or [''])[0]}")

    print("\n--- 最近项目（本次运行自己的注册表）---")
    for entry in ctx.project_registry.recent_projects():
        print(f"    {entry['root']}")

    ctx.win.close()
    pump(app, 200)
    restore_auto_dismiss()

    failed = [name for name, status, _ in RESULTS if status != "OK"]
    print(f"\n=== {len(RESULTS) - len(failed)}/{len(RESULTS)} 通过 ===")
    for name in failed:
        print(f"    FAILED: {name}")
    print(f"截图目录：{SHOT_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
