import os

# Temporary fix for: bus error
# Source: https://stackoverflow.com/questions/73072612/
# why-does-np-linalg-solve-raise-bus-error-when-running-on-its-own-thread-mac-m1
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["NUMEXPR_NUM_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

# torch bundles its own libiomp5md.dll; without this, loading torch into the
# GUI process (PySide6 already loaded) crashes with duplicate-OpenMP errors.
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# Suppress ICC profile warnings
os.environ["QT_LOGGING_RULES"] = "*.debug=false;qt.gui.icc=false"

import argparse
import codecs
import logging
import multiprocessing
import os
import sys
import tempfile
import traceback
from datetime import datetime
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

import yaml
from PyQt6 import QtCore, QtGui, QtWidgets

from anylabeling.app_info import (
    __appname__,
    __version__,
    __url__,
    CLI_HELP_MSG,
)
from anylabeling.config import (
    get_config,
    set_work_directory,
    get_work_directory,
)
from anylabeling import config as anylabeling_config


def is_wsl_environment():
    if os.environ.get("WSL_DISTRO_NAME") or os.environ.get("WSL_INTEROP"):
        return True

    try:
        with open("/proc/version", "r", encoding="utf-8") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def get_default_qt_platform():
    if os.environ.get("QT_QPA_PLATFORM"):
        return None

    if is_wsl_environment() and os.environ.get("WAYLAND_DISPLAY"):
        return "xcb"

    return None


def main():
    """Entry point with a top-level safety net.

    Startup failures (broken config YAML, unwritable work directory,
    missing Qt plugin, ...) used to terminate the app with only a stderr
    traceback — invisible when the app is launched from the Windows exe.
    Any uncaught exception is now written to a crash log and surfaced as a
    readable message box when a GUI session is available.
    """
    multiprocessing.freeze_support()
    try:
        _main()
    except SystemExit:
        raise
    except KeyboardInterrupt:
        raise
    except Exception:  # noqa: BLE001
        _handle_fatal_startup_error()


def _handle_fatal_startup_error():
    """Last-resort handler: crash log + readable user-facing message."""
    exc_text = traceback.format_exc()
    log_path = ""
    try:
        work_dir = get_work_directory()
        log_dir = os.path.join(work_dir, "xanylabeling_logs")
        os.makedirs(log_dir, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = os.path.join(log_dir, f"crash_{stamp}.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(
                "JLLabelingAndTrain startup crash\n"
                f"time: {datetime.now().isoformat()}\n"
                f"python: {sys.version}\n"
                f"cwd: {os.getcwd()}\n"
                "------------------------------------------\n"
            )
            f.write(exc_text)
    except Exception as e:  # noqa: BLE001
        try:
            log_path = os.path.join(tempfile.gettempdir(), "jll_crash.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(exc_text)
        except Exception:  # noqa: BLE001
            log_path = ""

    # Make sure a QApplication exists so the message box can render.
    try:
        app = QtWidgets.QApplication.instance()
        if app is None:
            app = QtWidgets.QApplication(sys.argv)
        title = QtWidgets.QMessageBox.Icon.Critical
        box = QtWidgets.QMessageBox()
        box.setIcon(title)
        box.setWindowTitle("JLLabelingAndTrain - 启动失败")
        detail = (
            "程序启动时发生未处理的错误。\n\n"
            "常见原因：\n"
            "· 配置文件 .xanylabelingrc 损坏或格式错误\n"
            "· 工作目录不可写或已被删除\n"
            "· Qt/图形环境异常\n\n"
        )
        if log_path:
            detail += f"详细错误已写入：\n{log_path}"
        box.setText(detail)
        box.setDetailedText(exc_text)
        box.exec()
    except Exception:  # noqa: BLE001
        # No GUI available (headless / plugin broken): fall back to stderr.
        print(
            "JLLabelingAndTrain failed to start.\n"
            f"Crash log: {log_path or 'unavailable'}\n{exc_text}",
            file=sys.__stderr__,
        )
    sys.exit(1)


def _main():
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(
        dest="command", help="available commands"
    )
    subparsers.add_parser("help", help="show help message")
    subparsers.add_parser(
        "checks", help="display system and package information"
    )
    subparsers.add_parser("version", help="show version information")
    subparsers.add_parser("config", help="show config file path")
    train_worker_parser = subparsers.add_parser(
        "train-worker", help=argparse.SUPPRESS
    )
    train_worker_parser.add_argument(
        "--payload", required=True, help=argparse.SUPPRESS
    )

    convert_parser = subparsers.add_parser(
        "convert", help="run conversion tasks"
    )
    convert_parser.add_argument(
        "--task",
        type=str,
        help="conversion task name (e.g., yolo2xlabel, xlabel2yolo)",
    )
    convert_parser.add_argument(
        "--images", type=str, help="image directory path"
    )
    convert_parser.add_argument(
        "--labels", type=str, help="label directory path"
    )
    convert_parser.add_argument(
        "--output", type=str, help="output directory path"
    )
    convert_parser.add_argument(
        "--classes", type=str, help="classes file path"
    )
    convert_parser.add_argument(
        "--pose-cfg", type=str, help="pose configuration file path"
    )
    convert_parser.add_argument("--mode", type=str, help="conversion mode")
    convert_parser.add_argument(
        "--mapping", type=str, help="mapping table file path"
    )
    convert_parser.add_argument(
        "--skip-empty-files",
        action="store_true",
        help="skip creating empty output files, only support `xlabel2yolo` and `xlabel2voc` tasks",
    )

    parser.add_argument(
        "--reset-config", action="store_true", help="reset qt config"
    )
    parser.add_argument(
        "--logger-level",
        default="info",
        choices=["debug", "info", "warning", "fatal", "error"],
        help="logger level",
    )
    parser.add_argument(
        "--qt-platform",
        help=(
            "Force Qt platform plugin (e.g., 'xcb', 'wayland'). "
            "If not specified, Qt will auto-detect the platform."
        ),
        default=None,
    )
    parser.add_argument(
        "--qt-image-allocation-limit",
        type=int,
        help=(
            "Override Qt image allocation limit in MB. "
            "Qt default is 256 MB. Use 0 to disable the limit."
        ),
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--filename",
        nargs="?",
        help=(
            "image or label filename; "
            "If a directory path is passed in, the folder will be loaded automatically"
        ),
    )
    parser.add_argument(
        "--output",
        "-O",
        "-o",
        help=(
            "output file or directory (if it ends with .json it is "
            "recognized as file, else as directory)"
        ),
    )
    parser.add_argument(
        "--config",
        dest="config",
        help="config file or yaml-format string",
        default=None,
    )
    # config for the gui
    parser.add_argument(
        "--nodata",
        dest="store_data",
        action="store_false",
        help="stop storing image data to JSON file",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--autosave",
        dest="auto_save",
        action="store_true",
        help="auto save",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--nosortlabels",
        dest="sort_labels",
        action="store_false",
        help="stop sorting labels",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--flags",
        help="comma separated list of flags OR file containing flags",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--labelflags",
        dest="label_flags",
        help=r"yaml string of label specific flags OR file containing json "
        r"string of label specific flags (ex. {person-\d+: [male, tall], "
        r"dog-\d+: [black, brown, white], .*: [occluded]})",  # NOQA
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--labels",
        help="comma separated list of labels OR file containing labels",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--validatelabel",
        dest="validate_label",
        choices=["exact"],
        help="label validation types",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--keep-prev",
        action="store_true",
        help="keep annotation of previous frame",
        default=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--work-dir",
        type=str,
        help="working directory for configuration and data files",
        default=os.path.expanduser("~"),
    )
    args = parser.parse_args()

    set_work_directory(args.work_dir)

    special = {
        "help": lambda args: print(CLI_HELP_MSG),
        "checks": lambda args: __import__(
            "anylabeling.views.common.checks", fromlist=["run_checks"]
        ).run_checks(),
        "version": lambda args: print(__version__),
        "config": lambda args: print(
            os.path.join(get_work_directory(), ".xanylabelingrc")
        ),
        "convert": lambda args: __import__(
            "anylabeling.views.common.converter",
            fromlist=["handle_convert_command"],
        ).handle_convert_command(args),
        "train-worker": lambda args: __import__(
            "anylabeling.services.auto_training.ultralytics.trainer",
            fromlist=["run_training_worker_command"],
        ).run_training_worker_command(args),
    }

    if args.command and args.command in special:
        special[args.command](args)
        return

    from anylabeling.views.mainwindow import MainWindow
    from anylabeling.views.labeling.logger import logger
    from anylabeling.views.labeling.utils import new_icon, gradient_text
    from anylabeling.views.labeling.utils.theme import (
        init_theme,
        get_app_stylesheet,
        get_dark_palette,
    )
    from anylabeling.views.labeling.utils.qt import apply_application_font

    # NOTE: Do not remove this import, it is required for loading translations
    from anylabeling.resources import resources  # noqa: F401

    if hasattr(args, "flags"):
        if os.path.isfile(args.flags):
            with codecs.open(args.flags, "r", encoding="utf-8") as f:
                args.flags = [line.strip() for line in f if line.strip()]
        else:
            args.flags = [line for line in args.flags.split(",") if line]

    if hasattr(args, "labels"):
        if os.path.isfile(args.labels):
            with codecs.open(args.labels, "r", encoding="utf-8") as f:
                args.labels = [line.strip() for line in f if line.strip()]
        else:
            args.labels = [line for line in args.labels.split(",") if line]

    if hasattr(args, "label_flags"):
        if os.path.isfile(args.label_flags):
            with codecs.open(args.label_flags, "r", encoding="utf-8") as f:
                args.label_flags = yaml.safe_load(f)
        else:
            args.label_flags = yaml.safe_load(args.label_flags)

    config_from_args = args.__dict__
    config_from_args.pop("command", None)
    config_from_args.pop("work_dir")
    reset_config = config_from_args.pop("reset_config")
    filename = config_from_args.pop("filename")
    output = config_from_args.pop("output")
    config_file_or_yaml = config_from_args.pop("config")
    if config_file_or_yaml is None:
        config_file_or_yaml = os.path.join(
            get_work_directory(), ".xanylabelingrc"
        )
    logger_level = config_from_args.pop("logger_level")
    qt_platform = config_from_args.pop("qt_platform", None)

    # --- Crash diagnostics (file logs + faulthandler) ---------------------
    try:
        import faulthandler

        log_dir = os.path.join(get_work_directory(), "xanylabeling_logs")
        os.makedirs(log_dir, exist_ok=True)
        _fh = logging.FileHandler(
            os.path.join(log_dir, "app.log"),
            encoding="utf-8",
            mode="a",
        )
        _fh.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)s | %(name)s:%(lineno)d - "
                "%(message)s"
            )
        )
        logger.addHandler(_fh)
        faulthandler.enable(
            file=open(
                os.path.join(log_dir, "faulthandler.log"),
                "w",
                encoding="utf-8",
            )
        )
        logger.info(f"📝 Crash diagnostics enabled: {log_dir}")
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Could not enable crash diagnostics: {e}")

    logger.setLevel(getattr(logging, logger_level.upper()))
    logger.info(
        f"🚀 {gradient_text(f'{__appname__} v{__version__} launched!')}"
    )
    logger.info(f"⭐ If you like it, give us a star: {__url__}")
    if qt_platform:
        os.environ["QT_QPA_PLATFORM"] = qt_platform
        logger.info(f"🖥️ Using Qt platform: {qt_platform}")
    else:
        default_qt_platform = get_default_qt_platform()
        if default_qt_platform:
            os.environ["QT_QPA_PLATFORM"] = default_qt_platform
            logger.info(
                "🖥️ Detected WSL/Wayland; using Qt platform: "
                f"{default_qt_platform}"
            )

    anylabeling_config.current_config_file = config_file_or_yaml
    config = get_config(config_file_or_yaml, config_from_args, show_msg=True)

    if not config["labels"] and config["validate_label"]:
        logger.error(
            "--labels must be specified with --validatelabel or "
            "validate_label: exact in the config file "
            "(ex. ~/.xanylabelingrc)."
        )
        sys.exit(1)

    output_file = None
    output_dir = None
    if output is not None:
        if output.endswith(".json"):
            output_file = output
        else:
            output_dir = output

    translator = QtCore.QTranslator()
    loaded_language = translator.load(":/languages/translations/zh_CN.qm")
    QtCore.QCoreApplication.setAttribute(
        QtCore.Qt.ApplicationAttribute.AA_ShareOpenGLContexts
    )
    qt_image_allocation_limit = config.get("qt_image_allocation_limit")
    if qt_image_allocation_limit is not None:
        QtGui.QImageReader.setAllocationLimit(qt_image_allocation_limit)
        if qt_image_allocation_limit == 0:
            logger.info("🖼️ Disabled Qt image allocation limit")
        else:
            logger.info(
                "🖼️ Set Qt image allocation limit to "
                f"{qt_image_allocation_limit} MB"
            )

    app = QtWidgets.QApplication(sys.argv)
    apply_application_font(config.get("font_family"))
    init_theme(config.get("theme", "light"))
    _dark_palette = get_dark_palette()
    if _dark_palette is not None:
        app.setStyle("Fusion")
        app.setPalette(_dark_palette)
    app.setStyleSheet(get_app_stylesheet())
    app.processEvents()

    app.setApplicationName(__appname__)
    app.setApplicationVersion(__version__)
    app.setWindowIcon(new_icon("icon"))
    if loaded_language:
        app.installTranslator(translator)
    else:
        logger.warning(
            "Failed to load translation for zh_CN. Using default language."
        )
    if reset_config:
        settings = QtCore.QSettings("anylabeling", "anylabeling")
        logger.info(f"Resetting Qt config: {settings.fileName()}")
        settings.clear()
        settings.sync()
        return

    win = MainWindow(
        app,
        config=config,
        filename=filename,
        output_file=output_file,
        output_dir=output_dir,
    )

    win.showMaximized()
    win.raise_()

    # Resume last folder after the window is visible. First-run has no
    # last directory, so the empty-canvas CTA stays unobstructed.
    def _offer_session_resume():
        try:
            widget = win.labeling_widget.view
            directory = widget.session_resume_path()
            if not directory:
                return
            from PyQt6.QtWidgets import QMessageBox

            box = QMessageBox(win)
            box.setWindowTitle(widget.tr("继续上次标注"))
            box.setIcon(QMessageBox.Icon.Question)
            box.setText(
                widget.tr("检测到上次打开的文件夹：\n%s\n\n是否继续上次标注？")
                % directory
            )
            continue_btn = box.addButton(
                widget.tr("继续上次"), QMessageBox.ButtonRole.YesRole
            )
            open_btn = box.addButton(
                widget.tr("打开别的文件夹"),
                QMessageBox.ButtonRole.ActionRole,
            )
            box.addButton(
                widget.tr("取消"), QMessageBox.ButtonRole.RejectRole
            )
            box.setDefaultButton(continue_btn)
            box.exec()
            clicked = box.clickedButton()
            if clicked == continue_btn:
                widget.continue_last_session()
            elif clicked == open_btn:
                widget.open_folder_dialog()
        except Exception as e:  # noqa
            logger.warning(f"Session resume prompt skipped: {e}")

    QtCore.QTimer.singleShot(500, _offer_session_resume)
    sys.exit(app.exec())


# this main block is required to generate executable by pyinstaller
if __name__ == "__main__":
    main()
