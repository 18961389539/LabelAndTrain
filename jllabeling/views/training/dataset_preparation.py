"""Determinate dataset preparation with a cooperative cancel.

The dialog owns the widgets; this mixin owns the preparation lifecycle so the
cancel/progress rules live in one place and ``ultralytics_dialog`` keeps its
size budget.
"""

import os
import shutil
import threading

from PyQt6 import QtWidgets

from jllabeling.services.auto_training.ultralytics.general import (
    DatasetPreparationCancelled,
    create_yolo_dataset,
)
from jllabeling.views.labeling.logger import logger


class DatasetPreparationMixin:
    def handle_preparation_close(self, event):
        """Delay a close until the background build has unwound.

        Returns True when the close was handled here (the event is ignored);
        False means no build is running and the normal close path applies.
        """
        thread = self._dataset_thread
        if thread is None or not thread.is_alive():
            return False
        if not self._dataset_cancel_event.is_set():
            reply = QtWidgets.QMessageBox.question(
                self,
                self.tr("Dataset Preparation in Progress"),
                self.tr(
                    "数据集仍在准备中。取消准备并关闭窗口吗？"
                    "已复制的临时文件会被清理。"
                ),
                QtWidgets.QMessageBox.StandardButton.Yes
                | QtWidgets.QMessageBox.StandardButton.No,
                QtWidgets.QMessageBox.StandardButton.No,
            )
            if reply != QtWidgets.QMessageBox.StandardButton.Yes:
                event.ignore()
                return True
            self.cancel_dataset_preparation(close_after=True)
        else:
            # A cancel is already in flight: let it reach the worker and
            # close from _on_dataset_preparation_finished, so the thread
            # never outlives the dialog.
            self._close_after_prepare = True
        event.ignore()
        return True

    def start_dataset_preparation(self, config):
        """Build the dataset off the UI thread with visible progress."""
        self._dataset_pending_config = config
        self._dataset_cancel_event.clear()
        self._close_after_prepare = False
        total_images = max(1, len(self.image_list))
        self._dataset_progress = ("scanning", 0, total_images)
        self.start_training_button.setEnabled(False)
        self.start_training_button.setText(self.tr("Preparing dataset..."))
        # Name the phase in the status area too: the button is on the config
        # tab, and "Ready to train" would otherwise sit there for the whole
        # build (the training_started event takes over from here).
        self.training_status = "preparing"
        self.update_training_status_display()
        self.progress_bar.setRange(0, total_images)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat(f"0/{total_images}")
        if hasattr(self, "metrics_label"):
            self.metrics_label.setText(self.tr("Preparing dataset..."))
        self._set_preparation_controls(True)
        self.dataset_progress_timer.start(200)
        self.refresh_wizard_state()
        self.append_training_log(
            self.tr("Preparing dataset in the background...")
        )
        self._dataset_thread = threading.Thread(
            target=self._prepare_dataset_worker,
            args=(config,),
            daemon=True,
        )
        self._dataset_thread.start()

    def _prepare_dataset_worker(self, config):
        """Run create_yolo_dataset off the UI thread (pure file IO)."""
        temp_dir = None
        error_msg = ""
        cancelled = False
        report = {}
        try:
            # Runs on a worker thread: no widget calls here. The seed reaches
            # the log through the training command line on the UI thread.
            seed, seed_source = self._project_split_seed()
            temp_dir = create_yolo_dataset(
                self.image_list,
                self.selected_task_type,
                config["basic"]["dataset_ratio"],
                config["basic"]["data"],
                self.output_dir,
                config["basic"].get("pose_config"),
                config["checkpoint"].get("skip_empty_files", False),
                config["checkpoint"].get("only_checked_files", False),
                seed=seed,
                seed_source=seed_source,
                report=report,
                progress_callback=self._record_dataset_progress,
                cancel_check=self._dataset_cancel_event.is_set,
            )
            if self._dataset_cancel_event.is_set():
                # Cancel arrived after the last file: do not hand a
                # just-built dataset to a user who asked to stop.
                cancelled = True
                shutil.rmtree(temp_dir, ignore_errors=True)
                temp_dir = None
        except DatasetPreparationCancelled:
            cancelled = True
            logger.info("Dataset preparation cancelled by user")
        except Exception as e:  # noqa: BLE001
            logger.error(f"Dataset preparation failed: {e}")
            error_msg = str(e)
        # Read by the UI thread once the queued signal lands; the assignment
        # happens before the emit so the dict is always there.
        self._dataset_report = report
        # PyQt signals are thread-safe; delivery is queued to the UI thread.
        self.dataset_preparation_finished.emit(
            temp_dir or "", error_msg, cancelled
        )

    def _set_preparation_controls(self, active):
        button = getattr(self, "cancel_preparation_button", None)
        if button is None:
            return
        button.setEnabled(True)
        button.setText(self.tr("取消准备"))
        button.setVisible(active)

    def cancel_dataset_preparation(self, close_after=False):
        """Ask the worker to stop; the dialog closes once it has unwound."""
        if close_after:
            self._close_after_prepare = True
        thread = self._dataset_thread
        if thread is None or not thread.is_alive():
            return
        if self._dataset_cancel_event.is_set():
            return
        self._dataset_cancel_event.set()
        self.append_training_log(self.tr("正在取消数据集准备…"))
        button = getattr(self, "cancel_preparation_button", None)
        if button is not None:
            button.setEnabled(False)
            button.setText(self.tr("正在取消…"))
        if hasattr(self, "status_label"):
            self.status_label.setText(self.tr("正在取消数据集准备…"))
        if hasattr(self, "progress_bar"):
            self.progress_bar.setFormat(self.tr("正在取消…"))

    def _record_dataset_progress(self, stage, processed, total):
        """Worker-thread writer; the UI timer reads this tuple."""
        self._dataset_progress = (str(stage), int(processed), int(total))

    def _update_dataset_progress(self):
        if self.training_status != "preparing":
            self.dataset_progress_timer.stop()
            return
        if self._dataset_cancel_event.is_set():
            return
        stage, processed, total = self._dataset_progress
        if total > 0:
            processed = min(processed, total)
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(processed)
            self.progress_bar.setFormat(f"{processed}/{total}")
        if stage == "scanning":
            text = (
                self.tr("正在检查标注：%1/%2")
                .replace("%1", str(processed))
                .replace("%2", str(total))
            )
        elif stage == "copying":
            text = (
                self.tr("正在写入数据集：%1/%2")
                .replace("%1", str(processed))
                .replace("%2", str(total))
            )
        else:
            text = self.tr("Preparing dataset...")
        if hasattr(self, "status_label"):
            self.status_label.setText(text)
        if hasattr(self, "metrics_label"):
            self.metrics_label.setText(text)

    def _leave_preparing_status(self):
        """Drop the dataset-build phase when the build did not lead to a run."""
        self.dataset_progress_timer.stop()
        self.training_status = "idle"
        self.update_training_status_display()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0/0")
        self._set_preparation_controls(False)
        if hasattr(self, "metrics_label"):
            self.metrics_label.setText("")
        self.refresh_wizard_state()

    def _on_dataset_preparation_finished(
        self, temp_dir, error_msg, cancelled=False
    ):
        """Continue the training flow once the background dataset is ready."""
        self.dataset_progress_timer.stop()
        self._dataset_thread = None
        close_after = self._close_after_prepare
        self._close_after_prepare = False
        self.start_training_button.setEnabled(True)
        self.start_training_button.setText(self.tr("Start Training"))

        if cancelled or self._dataset_cancel_event.is_set():
            self._leave_preparing_status()
            self.append_training_log(self.tr("数据集准备已取消。"))
            if hasattr(self, "metrics_label"):
                self.metrics_label.setText(self.tr("数据集准备已取消。"))
            if close_after:
                self.close()
            return

        if close_after:
            # The build won the race against the cancel request. The user
            # still asked to close, so do not start the run they cancelled.
            self._leave_preparing_status()
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)
            self.append_training_log(self.tr("数据集准备已取消。"))
            self.close()
            return

        if error_msg:
            self._leave_preparing_status()
            self.append_training_log(f"Failed to prepare dataset: {error_msg}")
            QtWidgets.QMessageBox.critical(
                self,
                self.tr("Dataset Error"),
                self.tr("Failed to prepare dataset:\n%s") % error_msg,
            )
            return
        if not temp_dir:
            self._leave_preparing_status()
            self.append_training_log(
                self.tr("Dataset preparation returned no output directory.")
            )
            return

        logger.info(f"Successfully created YOLO dataset at {temp_dir}")
        self.append_training_log(f"Created dataset: {temp_dir}")

        # A build that had to leave label files out says so here, before the
        # run starts: those images are absent from the dataset, not trained as
        # empty ones, and the difference is invisible in the metrics.
        report = getattr(self, "_dataset_report", None) or {}
        self._report_dataset_skips(report)
        if not self._confirm_dataset_skips(report):
            self._leave_preparing_status()
            self.append_training_log(
                self.tr(
                    "Training cancelled: fix the listed label files first."
                )
            )
            return

        config = self._dataset_pending_config
        try:
            if self.selected_task_type == "Classify":
                data_path = temp_dir
            else:
                data_path = os.path.join(temp_dir, "data.yaml")
            train_args = self.get_training_args(config, data_path=data_path)
            self._start_training_after_args(train_args)
        except Exception as e:
            error_msg = f"Failed to start training: {str(e)}"
            self.append_training_log(f"ERROR: {error_msg}")
            QtWidgets.QMessageBox.critical(
                self, self.tr("Training Error"), error_msg
            )
