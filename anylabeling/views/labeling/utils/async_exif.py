import os
import os.path as osp
import shutil
import stat
import tempfile
import time
from typing import List

import PIL.Image
import PIL.ImageOps
from PyQt6 import QtCore, QtWidgets
from PyQt6.QtCore import QCoreApplication, QObject, Qt, pyqtSignal

from ...labeling.logger import logger
from ._io import safe_replace
from .qt import EXIF_BACKUP_DIR_NAME as BACKUP_DIR_NAME

#: Longest failure list put into the details pane; every failure is logged.
MAX_DETAILED_FAILURES = 20


class ExifScannerWorker(QObject):
    exif_files_found = pyqtSignal(list)
    scan_finished = pyqtSignal()

    def __init__(self, image_files: List[str], parent=None):
        super().__init__(parent)
        self.image_files = image_files
        self._should_stop = False

    def stop(self):
        self._should_stop = True

    def scan_files(self):
        exif_files = []
        for filename in self.image_files:
            if self._should_stop:
                break
            try:
                with PIL.Image.open(filename) as img:
                    exif = img.getexif()
                    orientation = exif.get(0x0112, 1)
                    if orientation not in (1, None):
                        exif_files.append(filename)
            except Exception as e:
                logger.debug("Skipping %s: %s", filename, e)

        if not self._should_stop and exif_files:
            self.exif_files_found.emit(exif_files)

        self.scan_finished.emit()


class AsyncExifScanner(QObject):
    exif_detected = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.worker = None
        self.thread = None

    def start_scan(self, image_files: List[str]):
        if self.thread and self.thread.isRunning():
            self.stop_scan()

        self.thread = QtCore.QThread(self)
        self.worker = ExifScannerWorker(image_files)
        self.worker.moveToThread(self.thread)

        self.thread.started.connect(self.worker.scan_files)
        self.worker.exif_files_found.connect(self.exif_detected)
        self.worker.scan_finished.connect(self._cleanup_thread)

        self.thread.start()

    def _cleanup_thread(self):
        if self.worker:
            try:
                self.worker.scan_finished.disconnect(self._cleanup_thread)
            except (RuntimeError, TypeError):
                pass
        if self.thread:
            try:
                if self.thread.isRunning():
                    self.thread.quit()
                    if not self.thread.wait(3000):
                        self.thread.terminate()
                        self.thread.wait()
                self.thread.deleteLater()
                self.thread = None
            except RuntimeError:
                self.thread = None
        if self.worker:
            try:
                self.worker.deleteLater()
            except RuntimeError:
                pass
            self.worker = None

    def stop_scan(self):
        if self.worker:
            self.worker.stop()
        self._cleanup_thread()


class ExifProcessingDialog:
    @staticmethod
    def show_detection_dialog(parent, exif_count: int) -> bool:
        reply = QtWidgets.QMessageBox.question(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "EXIF Orientation Detected"
            ),
            QCoreApplication.translate(
                "LabelingWidget",
                "Detected %s images with EXIF orientation data. "
                "Direct annotation without correction may cause training anomalies.\n\n"
                "We will process these images in background and create backups in "
                "'x-anylabeling-exif-backup' folder under current directory. "
                "This may take some time.\n\n"
                "Continue processing or ignore?",
            )
            % exif_count,
            QtWidgets.QMessageBox.StandardButton.Ok
            | QtWidgets.QMessageBox.StandardButton.Cancel,
            QtWidgets.QMessageBox.StandardButton.Ok,
        )
        return reply == QtWidgets.QMessageBox.StandardButton.Ok

    @staticmethod
    def process_exif_files_with_progress(parent, exif_files: List[str]):
        progress = QtWidgets.QProgressDialog(
            QCoreApplication.translate(
                "LabelingWidget", "Processing EXIF orientation..."
            ),
            QCoreApplication.translate("LabelingWidget", "Cancel"),
            0,
            len(exif_files),
            parent,
        )
        progress.setWindowModality(Qt.WindowModality.WindowModal)
        progress.setAutoClose(True)

        template = QCoreApplication.translate(
            "LabelingWidget", "Processing: %s"
        )

        def on_file(index, filename):
            progress.setLabelText(template % osp.basename(filename))
            progress.setValue(index)
            QtWidgets.QApplication.processEvents()

        result = ExifProcessingDialog._process_files(
            exif_files, cancel=progress.wasCanceled, on_file=on_file
        )
        progress.setValue(len(exif_files))
        ExifProcessingDialog._report_result(parent, result)

    @staticmethod
    def _process_files(exif_files, cancel=None, on_file=None):
        """Rotate oriented images, keeping one backup per source file.

        Returns what actually happened (``processed`` / ``skipped`` /
        ``failed``, whether the run was cancelled, and the backup folder).
        One failure never stops the batch; the caller reports the real
        counts instead of claiming every image succeeded.
        """
        result = {
            "processed": [],
            "skipped": [],
            "failed": [],
            "cancelled": False,
            "backup_dir": None,
            "total": len(exif_files or []),
        }
        if not exif_files:
            return result
        root = ExifProcessingDialog._common_root(exif_files)
        backup_dir = ExifProcessingDialog._new_backup_dir(root)
        for index, filename in enumerate(exif_files):
            if cancel is not None and cancel():
                result["cancelled"] = True
                break
            if on_file is not None:
                on_file(index, filename)
            try:
                status = ExifProcessingDialog._process_single_file(
                    filename, root, backup_dir
                )
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    f"Error processing EXIF orientation for {filename}: {exc}"
                )
                result["failed"].append((filename, str(exc)))
                continue
            result[status].append(filename)
            if status == "processed" and result["backup_dir"] is None:
                result["backup_dir"] = backup_dir
        return result

    @staticmethod
    def _common_root(exif_files):
        directories = [osp.dirname(osp.abspath(name)) for name in exif_files]
        try:
            return osp.commonpath(directories)
        except ValueError:
            return directories[0]

    @staticmethod
    def _new_backup_dir(root):
        """A fresh folder per run, so a second pass cannot clobber a backup."""
        stamp = time.strftime("%Y%m%d_%H%M%S")
        base = osp.join(root, BACKUP_DIR_NAME, stamp)
        candidate = base
        suffix = 1
        while osp.exists(candidate):
            candidate = f"{base}_{suffix}"
            suffix += 1
        return candidate

    @staticmethod
    def _backup_target(filename, root, backup_dir):
        """Mirror the source's relative path so equal basenames cannot meet."""
        try:
            relative = osp.relpath(osp.abspath(filename), root)
        except ValueError:
            relative = osp.basename(filename)
        if relative.startswith(".."):
            relative = osp.basename(filename)
        target = osp.join(backup_dir, relative)
        if osp.exists(target):
            stem, extension = osp.splitext(target)
            target = f"{stem}_{os.getpid()}{extension}"
        return target

    @staticmethod
    def _process_single_file(filename, root, backup_dir):
        with PIL.Image.open(filename) as img:
            orientation = img.getexif().get(0x0112, 1)
            if orientation in (1, None):
                return "skipped"
            image_format = img.format
            if not image_format:
                raise ValueError("unknown image format")
            corrected = PIL.ImageOps.exif_transpose(img)
            corrected.load()
            source = {
                "format": image_format,
                "exif": corrected.getexif(),
                "icc": img.info.get("icc_profile"),
                "qtables": getattr(img, "quantization", None),
            }

        # The image is fully decoded and the file handle is closed before
        # the original is replaced: Windows refuses to replace an open file.
        backup_target = ExifProcessingDialog._backup_target(
            filename, root, backup_dir
        )
        os.makedirs(osp.dirname(backup_target), exist_ok=True)
        shutil.copy2(filename, backup_target)
        ExifProcessingDialog._replace_image_atomically(
            corrected, filename, source
        )
        return "processed"

    @staticmethod
    def _replace_image_atomically(image, target, source):
        """Write beside the image and swap it in; a failed encode is harmless."""
        image_format = source["format"]
        directory = osp.dirname(osp.abspath(target))
        fd, temporary_file = tempfile.mkstemp(
            prefix=".xal_exif_", suffix=".tmp", dir=directory
        )
        try:
            with os.fdopen(fd, "wb") as handle:
                options = {}
                if image_format in ("JPEG", "PNG", "WEBP"):
                    if source["exif"]:
                        options["exif"] = source["exif"]
                    if source["icc"]:
                        options["icc_profile"] = source["icc"]
                if image_format == "JPEG" and source["qtables"]:
                    options["qtables"] = dict(source["qtables"])
                image.save(handle, format=image_format, **options)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(temporary_file, stat.S_IMODE(os.stat(target).st_mode))
            except OSError:
                pass
            safe_replace(temporary_file, target)
            temporary_file = None
        finally:
            if temporary_file and osp.exists(temporary_file):
                try:
                    os.remove(temporary_file)
                except OSError:
                    pass

    @staticmethod
    def _report_result(parent, result):
        processed = len(result["processed"])
        skipped = len(result["skipped"])
        failed = result["failed"]
        attempted = processed + skipped + len(failed)

        if failed:
            details = []
            if result["backup_dir"]:
                details.append(result["backup_dir"])
            for filename, error in failed[:MAX_DETAILED_FAILURES]:
                details.append(f"{filename}: {error}")
            box = QtWidgets.QMessageBox(parent)
            box.setIcon(QtWidgets.QMessageBox.Icon.Warning)
            box.setWindowTitle(
                QCoreApplication.translate(
                    "LabelingWidget",
                    "Error occurred while processing images!",
                )
            )
            box.setText(
                QCoreApplication.translate(
                    "LabelingWidget",
                    "Processing finished: %d succeeded, %d failed "
                    "(of %d total).",
                )
                % (processed, len(failed), attempted)
            )
            if details:
                box.setDetailedText("\n".join(details))
            box.exec()
            return box

        if result["cancelled"] or processed == 0:
            # Cancelling is the user's decision, not a failure, and a run
            # that changed nothing has nothing to announce.
            logger.info(
                "EXIF processing stopped: %d processed, %d skipped, "
                "%d failed" % (processed, skipped, len(failed))
            )
            return

        template = QCoreApplication.translate(
            "LabelingWidget",
            "Successfully processed %s images.\n\n"
            "Original images backed up to:\n"
            "%s",
        )
        QtWidgets.QMessageBox.information(
            parent,
            QCoreApplication.translate(
                "LabelingWidget", "EXIF Processing Complete"
            ),
            template % (processed, result["backup_dir"]),
        )
