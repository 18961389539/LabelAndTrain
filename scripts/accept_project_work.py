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
import re
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


_CJK = re.compile(r"[\u4e00-\u9fff]")
_LATIN_WORDS = re.compile(r"[A-Za-z]{2,}")


def untranslated_copy(widget, include_menus=False, ignore=()):
    """Copy this widget actually shows that has Latin words and no Chinese.

    A ``.ui`` default string is invisible to both guards the code has:
    ``lupdate`` scans .py, so it never enters ``zh_CN.ts``, and the
    English-copy ratchet parses Python sources. Only a rendered widget -- on
    a real window, with the compiled catalog installed -- shows what the user
    actually reads.

    ``ignore`` names the strings a step put in there itself: a folder's own
    name can legitimately reach a placeholder (the properties dialog hints
    「fresh_project」 because that is the default it would apply), and that is
    data, not untranslated copy.
    """
    found = []
    for child in widget.findChildren(QtWidgets.QWidget):
        if not child.isVisible():
            continue
        # What is typed into a field is data (a folder name, a search term);
        # its placeholder is copy -- unless it names this very dataset.
        readers = (
            []
            if isinstance(child, QtWidgets.QLineEdit)
            else ([("text", child.text)] if hasattr(child, "text") else [])
        )
        readers += (
            [("placeholder", child.placeholderText)]
            if hasattr(child, "placeholderText")
            else []
        )
        for kind, read in readers:
            text = (read() or "").strip()
            if not text or _CJK.search(text) or not _LATIN_WORDS.search(text):
                continue
            if any(token and token in text for token in ignore):
                continue
            name = child.objectName() or type(child).__name__
            found.append(f"{name}/{kind}: {text}")
    if include_menus:
        for menu in widget.findChildren(QtWidgets.QMenu):
            for action in menu.actions():
                text = (action.text() or "").strip()
                if not text or _CJK.search(text):
                    continue
                if _LATIN_WORDS.search(text):
                    found.append(f"menu {menu.objectName()}: {text}")
    return found


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
        # One shot per distinct dialog: the same dialog photographed eleven
        # times says nothing new. (It used to *appear* eleven times, on
        # every folder open -- step 14 guards against that coming back.)
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
    from anylabeling.views.labeling.utils import missing_classes_hint
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
        missing_classes_hint=missing_classes_hint,
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
    # 字段级断言：values() 可能随新功能（如模板）多带键，整字典相等会过时
    assert values["name"] == "螺丝划痕", values
    assert values["task"] == "Segment", values
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


@step("10. 项目管理器：标注进度列占位后回填")
def s10_switcher_progress_column(ctx):
    from anylabeling.views.labeling.widgets.project_switcher import (
        ProjectSwitcherDialog,
    )

    win = ctx.win
    dialog = ProjectSwitcherDialog(win)
    dialog.show()
    pump(ctx.app, 250)
    assert dialog.list.columnCount() == 6
    assert dialog.list.headerItem().text(3) == "标注进度"
    # 后台计数在真窗口上也要落下来：每个格子要么是计数中，要么已回填。
    for _ in range(40):
        if all(
            dialog.list.topLevelItem(i).text(3) != "计数中…"
            for i in range(dialog.list.topLevelItemCount())
        ):
            break
        pump(ctx.app, 200)
    shoot(dialog, ctx.app, "10a_switcher_progress.png")
    for i in range(dialog.list.topLevelItemCount()):
        text = dialog.list.topLevelItem(i).text(3)
        assert text != "计数中…", f"row {i} still counting after 8s: {text}"
    dialog.close()
    pump(ctx.app, 80)


@step("11. 项目内搜索：对话框打开、条件与空态文案")
def s11_project_search_dialog(ctx):
    from anylabeling.views.labeling.widgets.project_search_dialog import (
        ProjectSearchDialog,
    )

    dialog = ProjectSearchDialog(ctx.win)
    dialog.show()
    pump(ctx.app, 250)
    assert dialog.state_combo.count() == 5  # 全部 + 四个状态
    for _ in range(40):
        if "搜索中" not in dialog.count_label.text():
            break
        pump(ctx.app, 200)
    text = dialog.count_label.text()
    assert text and "搜索中" not in text, text
    shoot(dialog, ctx.app, "11a_project_search.png")
    dialog.close()
    pump(ctx.app, 80)


@step("12. 工具 → 设备：子菜单列出可用设备与重新检测")
def s12_device_submenu(ctx):
    widget = ctx.widget
    tool_menu = widget.menus.tool
    submenus = [a for a in tool_menu.actions() if a.menu() is not None]
    device_actions = [a for a in submenus if a.text() == "设备"]
    assert device_actions, [a.text() for a in tool_menu.actions()]
    menu = device_actions[0].menu()
    entries = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert "CPU" in entries, entries
    assert "重新检测设备" in entries, entries
    # 这台机器上 onnxruntime 没有 CUDA provider：只有 CPU 一个可选项
    checkable = [a.text() for a in menu.actions() if a.isCheckable()]
    assert checkable and checkable[0] == "CPU", checkable
    shoot_menu(menu, ctx.app, tool_menu, "12a_device_submenu.png")


@step("13. 项目菜单：打开项目文件夹 排在设置文件夹之前")
def s13_open_project_folder_entry(ctx):
    menu = ctx.widget.menus.project
    labels = [a.text() for a in menu.actions()]
    assert "打开项目文件夹" in labels, labels
    assert "打开项目设置文件夹" in labels, labels
    # 数据目录在前：十次里有九次想看的是数据本身
    assert labels.index("打开项目文件夹") < labels.index("打开项目设置文件夹")


@step("14. 还没有类别：每个项目只问一次，「不再提示」写进项目记录")
def s14_missing_classes_hint_once(ctx):
    """The eleven dialogs of the 2026-10-10 run must not come back.

    ``_ask`` is recorded rather than shown, and into a folder none of the
    earlier steps opened: by this point the real widget has already been
    asked about the folders the run touched, so its answer for those is
    silence -- correct, but it would prove nothing about the rule.
    """
    hint = ctx.missing_classes_hint
    settings = ctx.project_settings
    asked = []

    def probe():
        return SimpleNamespace(
            unique_label_list=SimpleNamespace(count=lambda: 0),
            isVisible=lambda: True,
        )

    untouched = os.path.join(ctx.tmp, "hint_project")
    os.makedirs(untouched, exist_ok=True)
    make_images(untouched, count=2)

    original = hint._ask
    hint._ask = lambda widget, root: asked.append(os.path.abspath(root))
    try:
        for _ in range(3):
            hint.maybe_prompt(probe(), untouched)
        assert asked == [os.path.abspath(untouched)], asked

        # 不再提示 is a recorded choice: a widget with no memory of the
        # session still leaves the project alone.
        muted = os.path.join(ctx.tmp, "muted_project")
        os.makedirs(muted, exist_ok=True)
        make_images(muted, count=1)
        hint.maybe_prompt(probe(), muted)
        assert len(asked) == 2, asked
        assert settings.update_values(muted, **{settings.HINT_KEY: hint.MUTED})
        hint.maybe_prompt(probe(), muted)
        assert len(asked) == 2, asked

        # 项目切换器 → 重置本项目设置 is the way back, and it is a *durable*
        # re-arm: inside this process the project has already been asked once,
        # so what reset promises is that the next session asks again.
        assert settings.reset_ui_settings(muted) is True
        hint.asked_roots().discard(os.path.normcase(os.path.abspath(muted)))
        hint.maybe_prompt(probe(), muted)
        assert len(asked) == 3, asked

        # The production path does reach the hint: the earlier steps opened
        # real folders, and each one is now in the asked table.
        assert hint.asked_roots(), "load_dir never reached the hint"
        assert (
            os.path.normcase(os.path.abspath(ctx.plain)) in hint.asked_roots()
        )
    finally:
        hint._ask = original


@step("15. 每个绑定的快捷键都真的挂在窗口上（不只是配置里有这个键）")
def s15_shortcut_keys_are_installed(ctx):
    """`shortcuts` in the yaml is a different claim from "this key does something".

    Qt fires a WindowShortcut QAction only while the action is installed on a
    widget inside the active window -- which is what the
    `# XXX: need to add some actions here to activate the shortcut` note in
    label_widget.py was worried about. Enabled-ness is deliberately not
    asserted here: copy / paste / union are selection-dependent by design, and
    a step that demanded they be live would only teach the next person to
    delete the check.
    """
    widget, win = ctx.widget, ctx.win
    bound = {
        name: key
        for name, key in widget._config.get("shortcuts", {}).items()
        if isinstance(key, str) and key.strip()
    }
    # A config that silently lost its keys would otherwise pass by having
    # nothing to check.
    assert len(bound) > 60, len(bound)

    installed = set()
    for holder in [win] + win.findChildren(QtWidgets.QWidget):
        installed.update(QtWidgets.QWidget.actions(holder))
    actions = win.findChildren(QtGui.QAction)

    for name, key in sorted(bound.items()):
        wanted = QtGui.QKeySequence(key)
        carriers = [
            act for act in actions if any(s == wanted for s in act.shortcuts())
        ]
        assert carriers, f"{name} ({key}) is bound but no action carries it"
        live = [
            act
            for act in carriers
            if act in installed
            or act.shortcutContext()
            == QtCore.Qt.ShortcutContext.ApplicationShortcut
        ]
        assert live, f"{name} ({key}) has an action that is never installed"


@step("16. 类别筛选：入口、勾选列表与项目记忆在真实窗口里成立")
def s16_class_filter_entry(ctx):
    """The dialog and the setter existed; nothing on screen could reach them.

    Real window, real compiled catalog. This is also the only machine check
    that the shipped ``zh_CN.qm`` carries the inherited dialog's Chinese --
    its sources are English (``Filter Classes`` / ``Select All``), and 14
    offscreen steps assert the wiring without ever resolving a string.
    """
    from anylabeling.services.auto_labeling.__base__.yolo import YOLO
    from anylabeling.views.labeling import project_settings
    from anylabeling.views.labeling.widgets.auto_labeling.auto_labeling import (
        _dataset_dir_for,
    )
    from anylabeling.views.labeling.widgets.classes_filter_dialog import (
        ClassesFilterDialog,
    )

    panel = ctx.widget.auto_labeling_widget
    classes = ["划痕", "凹坑", "气泡"]

    class _StubYolo:
        """The real setter, so the indices checked here are production's."""

        set_auto_labeling_filter_classes = (
            YOLO.set_auto_labeling_filter_classes
        )

        def unload(self):
            pass

    model = _StubYolo()
    model.classes = classes
    model.filter_classes = "unset"
    panel.model_manager.loaded_model_config = {
        "model": model,
        "type": "yolov8",
        "display_name": "桩模型",
        "classes": classes,
    }

    project_dir = os.path.join(ctx.tmp, "class_filter_project")
    os.makedirs(project_dir, exist_ok=True)
    ctx.widget._project_dataset_dir = project_dir
    assert _dataset_dir_for(panel) == project_dir

    # Open the panel the way the user does (the same call the shortcut makes):
    # "not hidden" is a local flag, and a control inside a panel nobody
    # opened would still pass that check.
    if not panel.isVisible():
        ctx.widget.toggle_auto_labeling_widget()
    pump(ctx.app, 200)
    assert panel.isVisible(), "智能标注面板没有打开"

    panel.apply_project_class_filter()
    assert not panel.button_class_filter.isHidden(), "支持筛选却没有入口"
    assert "类别筛选" in panel.button_class_filter.text()
    assert panel._more_panel.isHidden()
    # Nothing is filtered yet, so the visible row must not claim otherwise.
    assert "类别筛选" not in panel._more_button.toolTip()

    panel._more_button.click()
    pump(ctx.app, 150)
    assert panel.button_class_filter.isVisible()
    assert panel.button_class_filter.width() > 0
    shoot(panel, ctx.app, "16a_more_panel_filter.png")

    # Nothing on the rendered panel may be untranslated English. A `.ui`
    # default string is invisible to both guards the code has: `lupdate`
    # scans .py only, so it never enters the catalog, and the English-copy
    # ratchet parses Python sources. Only a real window can see it -- which
    # is how "Ready!" sat in the panel's status slot unnoticed.
    english = untranslated_copy(panel)
    assert not english, english

    panel.set_class_filter(["凹坑"])
    assert model.filter_classes == [1], model.filter_classes
    assert "1/3" in panel.button_class_filter.text()
    assert project_settings.class_filter(project_dir) == ["凹坑"]
    # The panel is open here, so the filter names itself on its own button.
    assert "类别筛选" not in panel._more_button.toolTip()

    # 收起之后，筛选状态改由看得见的那个按钮承担
    panel._more_button.click()
    pump(ctx.app, 120)
    assert not panel.button_class_filter.isVisible()
    assert "类别筛选" in panel._more_button.toolTip()
    shoot(panel, ctx.app, "16b_more_button_marked.png")

    dialog = ClassesFilterDialog(classes, ["凹坑"], ctx.win)
    dialog.show()
    pump(ctx.app, 220)
    assert dialog.windowTitle() == "筛选类别", dialog.windowTitle()
    rows = [dialog._list.item(i).text() for i in range(dialog._list.count())]
    assert rows == classes, rows
    assert dialog._toggle_btn.text() == "全选", dialog._toggle_btn.text()
    assert "搜索类别" in dialog._search_bar.placeholderText()
    dialog_english = untranslated_copy(dialog)
    assert not dialog_english, dialog_english
    shoot(dialog, ctx.app, "16c_class_filter_dialog.png")
    dialog.close()

    # 换模型时状态与标记都不能留下上一个人的痕迹
    panel.hide_labeling_widgets()
    assert panel._class_filter is None
    assert "类别筛选" not in panel._more_button.toolTip()
    panel.model_manager.loaded_model_config = None


@step("17. 本 fork 自己的界面无未翻译英文；继承部分只报告不挡门")
def s17_no_untranslated_english(ctx):
    """The rule the panel now keeps, on the surfaces this fork wrote.

    The fork's own dialogs are held to it. The inherited main window is
    *measured* and printed instead: an English-source sweep across upstream
    widgets was ruled out of scope for this fork, so the number is what a
    future batch starts from -- and it cannot be claimed to be unknown.
    """
    from anylabeling.views.labeling.widgets.project_switcher import (
        ProjectSwitcherDialog,
    )
    from anylabeling.views.labeling.widgets.overview_dialog import (
        OverviewDialog,
    )
    from anylabeling.views.labeling.widgets.shape_converter_dialog import (
        ShapeConverterDialog,
    )

    # What this run put on screen itself: folder names, image names, the app
    # name. Those reach labels and placeholders as data, not as copy.
    data = (ctx.tmp, "img_", "JLLabelingAndTrain") + tuple(
        os.path.basename(p)
        for p in (ctx.fresh, ctx.screws, ctx.plain)
        if os.path.basename(p)
    )
    offenders = []

    switcher = ProjectSwitcherDialog(ctx.win)
    switcher.show()
    pump(ctx.app, 250)
    offenders += untranslated_copy(switcher, ignore=data)
    switcher.close()

    described = ctx.project_model.describe(ctx.fresh)
    properties = ctx.ProjectPropertiesDialog(
        ctx.win,
        name=described["name"],
        task=described["task"],
        root=ctx.fresh,
        title="项目属性",
    )
    properties.show()
    pump(ctx.app, 220)
    offenders += untranslated_copy(properties, ignore=data)
    properties.close()
    pump(ctx.app, 80)

    # The two dialogs that read the open project: 形状转换器 (a bulk rewrite
    # tool, so its copy is worth money) and 统计总览. The latter runs its own
    # modal loop from ``__init__``, so the scan has to step over that call --
    # a step that blocks on a dialog is the one failure mode this harness
    # cannot afford (it looks exactly like a slow run).
    ctx.widget.import_image_folder(ctx.fresh)
    pump(ctx.app, 300)
    OverviewDialog.exec = lambda _self: 0
    try:
        for kind in (ShapeConverterDialog, OverviewDialog):
            dialog = kind(ctx.widget)
            dialog.show()
            pump(ctx.app, 250)
            offenders += untranslated_copy(dialog, ignore=data)
            dialog.close()
            pump(ctx.app, 80)
    finally:
        del OverviewDialog.exec

    assert not offenders, offenders

    inherited = untranslated_copy(ctx.win, include_menus=True, ignore=data)
    # ASCII marker first: a redirected log is gbk, where the Chinese half of
    # this line is what a later reader cannot grep for.
    print(
        f"       [inherited-english] {len(inherited)} 处（上游继承，仅报告）",
        flush=True,
    )
    for line in inherited[:40]:
        print(f"         - {line}", flush=True)


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
    s10_switcher_progress_column,
    s11_project_search_dialog,
    s12_device_submenu,
    s13_open_project_folder_entry,
    s14_missing_classes_hint_once,
    s15_shortcut_keys_are_installed,
    s16_class_filter_entry,
    s17_no_untranslated_english,
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
