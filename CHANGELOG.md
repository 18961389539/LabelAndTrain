# JLLabelingAndTrain Changelog

Fork entries are listed first; everything below the upstream marker is
X-AnyLabeling's own history, kept for provenance.

## `v1.0.0-beta.7` (Oct 26, 2026)

### 🐛 Bug Fixes

- **Closing the window during batch auto-labeling no longer destroys the widget under a running QThread.** The batch worker is a `QThread` with no QObject parent, and `closeEvent` neither set `cancel_processing` nor waited: after the window disappeared the thread still held the widget and the model, kept writing labels, and could tear down a running QThread at process exit. `utils/exit_cleanup.batch_allows_close()` now runs before the save prompt: it requests the batch stop and, while the thread is still running, `closeEvent` shows「正在停止批量标注，请处理完当前图片再关闭窗口。」and ignores the close; a stopped or already-deleted thread lets the close proceed. Once the close is really going ahead (the save prompt answered), `cancel_model_work()` calls the model manager's `cancel_download()` / `cancel_prediction()` so a running download or inference also stops; it deliberately runs after the prompt, so cancelling the close does not cancel model work. Nine tests pin the idle/running/stopped/deleted-thread cases, the warning/ordering in `closeEvent`, and the model-cancel side effects. The warning string joined the catalog via the normal `pylupdate6`/`lrelease` flow. The audit also records the paths that were already safe (training stop, EXIF/label-check stop, smart-tool cancel) and the remaining boundary — `model.export()` still has no cancellation hook, so an export finishes in its daemon thread. Full write-up: `reviews/exit_interrupt_paths_2026-10-26.md`. Suite 1672 passed / 1 skipped / 61 subtests, smoke 17/17, acceptance 17/17, black 206 files, flake8 214 findings with no regression.

- **F1 did nothing: the shortcut was bound to two actions, and Qt treats that as ambiguous.** The Tool menu's 快捷键速查 action carried F1 from the config, while `SettingsRuntimeApplier` also created a hidden QAction for the same feature and bound F1 to it; a window shortcut that matches two actions fires neither. D/A, Ctrl+G, Ctrl+0 and F9 all worked, so the key event itself was fine — the key was simply claimed twice. The runtime applier now maps `shortcuts.show_shortcuts_help` to the visible action and no longer builds a hidden duplicate, and `widget.actions` exposes that action as `shortcuts_help` (the first version of the fix referenced a member the namespace did not have; the packaged build caught it at startup with `AttributeError`, which no unit test saw because none constructs the real widget). Two structural tests now hold both ends: no shortcut key may be bound by both a menu action and a hidden action, and every `self._widget.actions.X` the applier reaches for must exist in the namespace built at startup. Verified on the packaged build: F1 opens 快捷键速查 with 69 rows; F9 opens the navigator as a function-key control. The walkthrough, evidence and the UIA-close caveat are in `reviews/packaged_action_walkthrough_2026-10-26.md`. Suite 1663 passed / 1 skipped / 59 subtests, smoke 17/17, acceptance 17/17.

- **A refused training start no longer leaves the window on "preparing", and the CPU path is now walked end to end.** The background dataset build sets the dialog to `preparing`; when the training manager then refused to start — reproduced for real by starting a second run the instant the first one's completion event arrived, while `TrainingManager.is_training` was still winding down — the error was logged and shown, but the phase, the progress format and the status line stayed on "Preparing dataset..." with the dataset built and nothing running. `_start_training_after_args` now calls `_leave_preparing_status()` before reporting a refused start, so the window says idle and the re-enabled Start button is the honest retry; `tests/test_auto_training/test_training_safety_guards.py` drives `_on_dataset_preparation_finished` with a refusing manager and asserts the idle status, the enabled button and the logged reason. The end-to-end check behind it ran the real dialog offscreen on 4 synthetic images with one rectangle each: dataset build (manifest requested 4 / valid 4 / train 3 / val 1 / background 0, classes `["defect"]`, a project-pinned seed), then a real `yolov8n.pt` 1-epoch CPU run (imgsz 64, batch 1, workers 0) through the worker subprocess, which exited 0; `run_meta.json` matched the build manifest's seed, counts and SHA-1, recorded the weights SHA-1 and `epochs: 1` metrics, and the run appeared once in the history table with its CSV export (BOM + header + row). A second 10-epoch run was stopped after epoch 1 (`last.pt` present, worker terminated), writing `status: "stopped"` metadata and offering Resume, so the history listed one completed and one stopped run. The cleanup offer, reached with the keep/byte thresholds lowered for the tiny build, deleted the oldest of three real builds and kept the current one plus the newest old build, leaving the completed run's `run_meta.json` still naming its now-pruned dataset. 56/56 checks; suite 1661 passed / 1 skipped, smoke 17/17, acceptance 17/17.

- **Converter imports now write labels atomically.** `LabelConverter.save_json` was a plain `open(..., "w")`; every `*_to_custom` import (COCO/VOC/YOLO, GUI and CLI) snapshotted the pre-import file and then truncated it before writing, so a disk error left a damaged label even though a backup existed. It now writes beside the target and replaces it through the shared `safe_replace`, leaving the previous file intact when the write fails. Tests: a failed write keeps the old bytes with no temp residue; a successful one replaces it. Suite 1660 passed / 1 skipped, smoke 17/17, acceptance 17/17.

- **Training provenance files are written atomically.** `manifest.json` (the exact annotations a dataset was built from) and `run_meta.json` (the run's weights and metrics) were written in place; a crash mid-write left a truncated provenance record with no second copy. Both go through `save_json_atomic` (temp + fsync + replace); a failed manifest write still aborts the build and removes its half-written dataset, and a failed `run_meta` write is logged and returns `None` as before. Tests: JSON atomic success/failure, and a forced manifest failure leaving no files under the dataset root. Suite 1658 passed / 1 skipped, smoke 17/17, acceptance 17/17.

- **陈旧框清理 now says how many boxes it skipped.** Locked, changed-since-the-report and unavailable boxes are skipped by design, but the count lived only in the log while the toast reported the deletions -- a selection where half the boxes were skipped read like a complete delete. The summary appends the skip count (and an all-skipped selection says why nothing was deleted); the log line stays. Tests: deleted+skipped, all-skipped, and nothing-to-do wording. Suite 1655 passed / 1 skipped, smoke 17/17, acceptance 17/17.

- **Smart-tool jumps now respect unsaved edits.** Double-clicking a result row, 跳到首个结果 and 跳到下一张待复核 called `load_file` directly, skipping the `may_continue()` prompt every navigation path runs; with auto-save off -- or after a failed write -- that silently discarded the edits on screen. All three go through `load_result_image`, which asks first and leaves the dialog and current image intact when the user cancels. Tests: a cancelled prompt blocks the load and the dialog close; a clean (or stub) parent still loads. Suite 1652 passed / 1 skipped, smoke 17/17, acceptance 17/17.

- **A delayed relabel update no longer lands in the previous project.** `watch_relabel_result` schedules a 1.5 s poll after the batch; if the user switched or deleted the project before it fired, it counted the *new* project's images and appended those numbers to the *old* directory's iteration history, corrupting the round record. `_record_relabel_result` now verifies that the directory still exists and is still the open project's label dir before counting, and the poll stops entirely when either check fails. Tests: switched and deleted projects write nothing; the same project still records the gain. Suite 1648 passed / 1 skipped, smoke 17/17, acceptance 17/17.

- **漏标扫描/模板预标注 now write labels atomically and count only successful writes.** Both batch writers used `open(..., "w") + json.dump` after snapshotting, so a failed write truncated the label (recoverable from the snapshot, but still damaged); 漏标扫描 also counted every appended box before the write, so its toast could claim boxes that never landed. Both go through `save_json` (temp + fsync + replace); 漏标扫描 returns `(written, failed)` and reports failed files with a warning instead of a success toast. Tests: failed-write cases for both writers keep the label unchanged and return `(0, 1)`, alongside the existing success/snapshot assertions. Suite 1645 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **一键去重归档 now saves first and reports every file it could not move.** The action ran `finalize_moves` and discarded its skipped list, so a locked label or an I/O error left an image archived without its annotation while the toast still said "已归档 N 项"; a pending auto-save could also land next to a file that had just been moved. It now calls `may_continue()` before touching the filesystem (flushing or prompting for unsaved edits) and shows a warning naming up to ten skipped paths with the moved/skipped counts; the success toast appears only when nothing was skipped. Tests: all-moved versus partial reporting. Suite 1643 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **裁剪导出 no longer overwrites one image's crops with another's.** Crop files are named `<stem>_<n>-<shape>.jpg`; a recursive folder with `a/photo.png` and `b/photo.png` produced identical names, so the second image's crops silently replaced the first's. Colliding stems now get a short path digest (`photo_ab12cd34_1-rectangle.jpg`), while unique stems keep their names; the suffix travels with the batch worker arguments. Tests: only colliding stems receive a suffix, and two same-stem images produce two distinct, non-empty crops. Suite 1639 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **图像标志文件导入 now survives the reload and restarts.** The action applied the new flag list to the widget and then immediately reloaded the current image -- but nothing had saved that list, so the old flags came back from disk; the name list also never reached `_config["flags"]`, so every launch required importing it again. It now strips and de-duplicates the text (UTF-8 BOM tolerated), rejects an empty file, persists the schema through the atomic config save, marks the image dirty so the normal save path lands the checked state, and no longer reloads over its own work. Messages are Chinese. Tests: the import sanitizes/persists/marks dirty and never reloads; an empty file touches nothing. Suite 1637 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **形状属性与标签标志导入 now persist and validate.** Both actions updated only in-memory fields: `canvas.attributes` and `label_flags` in the config -- the source on the next launch -- kept the old schema, so the import vanished after a restart; a flags YAML with the wrong shape failed with a generic English popup after already touching the panel. The flags file is now validated as a label-to-list-of-names mapping (`null` becomes `[]`), both schemas are written through the atomic config save, and the success/failure messages are Chinese. Tests: flags normalization and rejection, both persistence helpers (including a broken `canvas` node), and the attribute-panel tests now assert persistence without touching the real config. Suite 1635 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **上传类别文件 now actually persists, and blank/duplicate lines no longer become classes.** The action read raw lines (a blank line became an empty class, duplicates stayed), updated only the two in-memory widgets, reported "Successfully loaded N labels!" in English, and left `config.labels` and the project record untouched -- the imported list vanished at restart while training and export kept using the old classes. It now reads UTF-8 with BOM tolerance, strips and de-duplicates preserving order, writes `config.labels` (through the atomic config save), updates the open project's record, re-assigns digit shortcuts, and reports the count in Chinese. Tests: the sanitizer plus the config/UI/digit/project wiring inside and outside a project. Suite 1627 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **Run-history CSV export and the training dialog's settings JSON are written atomically now.** The CSV export opened the chosen path for writing first, so a disk error left a truncated table where a previous export used to be; the settings JSON had the same in-place write. Both go through temp + fsync + replace now. The CSV keeps its UTF-8 BOM and spreadsheet row endings (`newline=""`), and a failed write leaves the previous file untouched with no temp behind. Tests: exported rows/BOM and failed-export retention in `tests/test_auto_training/test_run_history_export.py`, plus settings success and failed-save retention in `test_training_settings_io.py`. Suite 1622 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **`--output` imports now refuse duplicate image stems instead of letting them share one label file.** In output-directory mode labels are keyed by the image basename, so a recursive folder with `train/photo.png` and `val/photo.png` (or `photo.png` and `photo.jpg`) mapped both to `photo.json`: saving one silently replaced the other's annotations. The folder is scanned once up front and, when `output_dir` is set, duplicate stems abort the import with the names listed before any project state is reset; that same scan then feeds the file list, so the check adds no second walk. Project mode (labels beside each image) is unchanged. Tests: nested same stem, same folder with different extensions, unique stems, and an import that refuses while leaving the open project untouched. Suite 1618 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **Overview statistics export no longer uses the chosen folder as scratch space.** It wrote `label_infos.csv`, `shape_infos.csv` and `classes.txt` into the directory the user picked, zipped them, and then deleted those three paths. Choosing the dataset folder -- a natural choice -- overwrote and then removed the real `classes.txt`. The scratch files now live in a temp dir, the archive goes to a free `export_data[_N].zip` name (an earlier export is never clobbered), and it is written through a `.part` file so a failure leaves neither a truncated zip nor stray CSVs. Tests: an existing `classes.txt` and zip survive byte-for-byte while the new archive carries the three entries, and an archive failure leaves the directory empty. Suite 1614 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **A failed training dataset build now removes its half-written folder.** Builds created `trainer_datasets/<task>/<name>/` up front and filled it image by image; any later failure (unwritable `data.yaml`, a corrupt label, a full disk) reached the dialog as an error but left the partial folder behind -- it looks like a real dataset to the cleanup tools and occupies disk until the user finds it. `create_yolo_dataset` is now a thin wrapper over the existing builder: the directory is recorded as soon as it exists and removed on any exception, even when the caller passed no report; the caller's report still carries the skip counts gathered before the failure. Test: forcing the YAML write to fail leaves no files under the dataset root. Suite 1612 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **COCO 导入 tolerates a few bad annotations, and cancelling it is cooperative now.** `coco_to_custom` parsed every annotation with no guard: an unknown category or image id, a two-value bbox or a malformed keypoint list aborted the whole file, and the upload thread reported a generic failure while the labels already written stayed behind. Annotations are now converted one at a time through `_coco_annotation_shapes()`; skipped annotations and failed writes are counted in a returned report, and the dialog shows the translated batch warning with the counts and offending image ids/paths in its details pane instead of a success toast. Cancel now calls `QThread.requestInterruption`, polled between annotations and image writes -- no more `terminate()` in the middle of a write; a cancelled run writes nothing and shows no success message. The thread's signal is renamed `upload_finished` so it no longer collides with QThread's own zero-argument `finished`. Tests: a short bbox among good ones, unknown category, unknown image id, cancel-before-write, a write failure, and pose content. Suite 1612 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **VOC 导入 gets the same per-file tolerance as YOLO.** The loop also ran inside a single `try` on the UI thread: one malformed XML (or one missing `<size>`) aborted the rest of the folder, and a cancelled run still showed the success toast. `import_voc_labels()` now converts each XML independently and counts imported/failed/attempted; failures use the shared translated batch count with the offending paths in the details pane, and cancel is silent. Tests: one bad XML leaves the good file imported and fails only its own pair, images without an XML are skipped rather than failed, and cancellation stops with accurate counts. Suite 1606 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **YOLO 导入 no longer abandons the folder on one bad file, and no longer reports success after a cancel.** The loop behind 导入 YOLO ran inside a single `try`: one malformed line, one missing image or one unreadable existing JSON aborted the entire folder, surfaced a generic English popup, and left the files already converted in place with no account of them; cancelling still ended with "Upload completed successfully!". The loop is now a testable `import_yolo_labels()` that catches each pair independently and counts imported/failed/attempted; failures are reported through the batch tools' translated count string with the offending paths in the details pane, and a cancelled run shows nothing instead of a success toast. The preserve-existing merge also goes through `save_label_json()`, so the file it replaces is snapshotted like every other importer -- which removed the last exemption in the label-writer invariant. Tests: a malformed line and a missing image each leave the good file imported and fail only their own pair, preserve-existing merges, and cancellation stops with accurate counts. Suite 1603 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **A failed save can no longer let the user leave the image, and cancelling a close no longer tears down the session.** The Save/Discard/Cancel prompt returned True after Save unconditionally; `save_file` returned nothing, so a full disk or read-only folder closed the window or switched images right after the error dialog, discarding the dirty state the user had just asked to keep. `save_labels` caught only `LabelFileError`, so a plain `OSError` from `makedirs`, the sidecar write or a locked file escaped as an exception instead of returning False. Saves now report their result end-to-end: output-mode saves do not close on failure, the prompt keeps the user on the image when the write failed, and every `OSError` is shown through the existing error dialog. Separately, `closeEvent` fell through to persisting settings and stopping the EXIF/label scanners after the user chose Cancel; it now returns immediately. The save helpers moved to `file_lifecycle` with thin widget delegates (the size budget stays under its cap), and the widget contract lists the seven newly touched members. Tests: the save-fail/leave matrix, cancelled-close leaves the session untouched, a failed output save does not close, and a real widget whose `LabelFile.save` raises `OSError` returns False. Suite 1599 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **The exported class list and dataset YAML are written atomically, and a failed training YAML now stops the build.** Exports wrote `classes.txt` and `data.yaml` in place, and the training dataset builder both wrote `data.yaml` in place and ignored `save_yaml_config`'s failure. A crash or full disk could therefore leave a truncated class list -- silently reordering or dropping classes for whatever reads it next -- or let the build "succeed" without a usable dataset descriptor, failing only later inside ultralytics with an error that points at the trainer instead of the write. Both writers now go through temp-file + fsync + replace (`save_text` for the export artifacts, the training `_io` for its YAML), and `create_yolo_dataset` raises a clear "Could not write the dataset YAML" when the write returns False, so the existing dataset-preparation error path reports it. Tests: `save_text` success/failure, training YAML success/failure, and a build forced to fail on the YAML write. Suite 1591 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **A failed project import or label restore no longer leaves damaged state behind.** Two paths write over user data without a second chance. `import_bundle` extracted straight into the target folder, so a corrupt entry or a disk error halfway through left a half-project that looked real and blocked a retry ("target already exists"); the archive is intact, so any failure now removes the folder it was creating, the same way cancellation already did. `restore_label_backup` copied each snapshot over the live label with `shutil.copy2`, which opens the destination for writing first: a disk-full or interrupted copy truncated a label that was previously valid (the pre-restore snapshot made it recoverable, but the restore reported one skipped file and left a damaged one). A shared `copy_file_atomic` writes beside the target, fsyncs and replaces, so a failed copy leaves the old label byte-identical, and the restore counts it as skipped. Tests: a stored-entry CRC failure aborts an import with no folder left; a restore copy interrupted after seven bytes leaves the label unchanged with no `.xal_copy_` residue. Suite 1586 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **An interrupted model download now resumes instead of starting over.** Every retry used to begin at byte 0, so a 30-second timeout at 90% of a 300 MB model threw away the whole transfer and the two retries could still end with nothing. A retry now sends `Range: bytes=<part size>-`, appends a 206 response after checking that its `Content-Range` starts exactly where the part ends, and takes the total from that header so the completeness check still rejects a short body; a server that ignores the range (200) or answers 416 is restarted from zero. Resume is scoped to the retries of one call on purpose: a `.part` left by an earlier process cannot be proven to belong to the same URL (the registry can change it), so the first attempt discards it. A body longer than the announced length is rejected as a size mismatch as well. Tests: six-of-ten bytes resumed to `secure7890` with exactly one range request, range-ignored restart, 416 restart, stale part not resumed, over-long body rejected -- all in `tests/test_models/test_model_download.py`. Suite 1584 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **The batch run's progress label is Chinese now.** 运行全部 built its label by hand in three places (`f"Progress: {done}/{total}"`), and the English-UI gate could not see any of them: `setLabelText` was not in its setter list, and the scanner only read plain string constants, so an f-string was invisible even when the setter was. All batch surfaces now share `_batch_progress_text()` with the Chinese source "进度：%1/%2", including the dialog's initial label and the progress bar's valueChanged path. The gate scans `setLabelText` and the constant parts of f-strings (markup fragments filtered), which finds only the three already-allowlisted technical values and would catch a regression here. Tests: the helper's output in `tests/test_auto_labeling/test_batch_skip.py` plus the extended gate. Suite 1579 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **A failed label snapshot no longer leaves a half-restorable run behind.** `backup_label_files` copies every file that is about to change into a timestamped `.label_backups/` run; when the copy failed partway, it returned `None` (so callers correctly aborted the change) but the already-filled run directory stayed on disk, and 从备份恢复标注 offered it like any other snapshot -- picking it would put back only the files copied before the failure while appearing to be a complete undo point. The run this call created is now removed on failure (a run that already existed is never touched), with a cleanup failure logged rather than hidden. Test: a two-file snapshot whose second copy fails leaves no run in the picker. Suite 1578 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **A truncated model download is no longer installed as if it succeeded.** `download_with_retry` streamed the body, renamed `.part` into place and announced "Download completed" without comparing the bytes received with the server's Content-Length: a connection that closed cleanly at 90% produced a non-empty, plausible-looking weight file that only failed later inside the loader, pointing at the model rather than the download. The body is now verified before the rename -- an empty body or one shorter than the announced size raises a network error, so the existing retry loop runs and the partial file is removed; nothing reaches the model path. Tests: six-of-ten bytes and zero bytes in `tests/test_models/test_model_download.py`, both asserting no destination and no `.part` residue. Suite 1577 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **A malformed custom-model registration no longer takes the auto-labeling panel down.** `custom_models` lives in the user-editable rc and was iterated without a shape check, while every registered YAML was parsed and indexed without checking it was a mapping: `custom_models: null`, a mapping, a list of strings, or an emptied/hand-edited model YAML each raised inside `ModelManager.__init__` before the panel could build. The list is now sanitized (mappings with a string `config_file`) and each entry is parsed and validated by one helper: a non-mapping YAML, invalid `name`, unsupported `type`, or non-string `display_name` is logged and skipped, but deliberately kept in the rc so a temporarily unreadable file is not forgotten -- the next save repairs structurally invalid entries. `load_custom_model` and `remove_custom_model` share the same sanitizer, and the "model type ... is not supported" log line is now actually interpolated. Tests: 9 registry cases in `tests/test_auto_labeling/test_custom_model_registry.py` -- four malformed `custom_models` shapes, an empty/list model YAML, unsupported type, bad display name, a valid registration, and the invalid-config status message. Suite 1575 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **EXIF 方向修正 now backs up every original and reports what it actually did.** The batch rewrote images in place with `Image.save`, which put every backup under one flat `x-anylabeling-exif-backup` folder keyed by basename -- two `photo.jpg` from different subfolders collided and the first backup was overwritten; it also re-encoded JPEGs at Pillow's default quality, dropped all EXIF (date/GPS/camera) and ICC data, truncated the original if the encoder failed mid-save, and ended a cancelled or partially failed run with "Successfully processed N images" where N was the requested count, not the processed one. Each run now writes to `x-anylabeling-exif-backup/<timestamp>/` while mirroring the source's relative path (a second pass cannot clobber the first), encodes beside the target and atomically replaces it after fsync (a failed encode leaves the original untouched), keeps the source JPEG's quantisation tables and its EXIF/ICC payload, and reports processed/skipped/failed counts; a cancelled run no longer announces success, and failures name their paths in the details pane. Because that folder now lives inside the dataset, `scan_all_images` prunes it -- otherwise reopening the project would list every backup as a second, unlabelled image. The strings are the batch tools' existing "Processing finished: %d succeeded, %d failed" pair, so no catalog churn. Tests: 9 cases in `tests/test_utils/test_exif_processing.py` -- nested same-name backups, quantisation/EXIF preservation, a second run, cancel accounting, a corrupt file mid-batch, the scanner exclusion, and the dialog's wording. Suite 1566 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **A corrupt config file no longer blocks startup, and a config save can no longer produce one.** `.xanylabelingrc` was parsed with no guard: an empty file crashed on `None.get`, a hand-edit typo raised `ParserError`, and a top-level list raised `AttributeError` -- all before the window existed, so the app could not open until the file was fixed by hand. The file is now moved aside with an `.invalid-<timestamp>` suffix, the app starts from the template, and a startup dialog names both the original and the backup instead of silently forgetting every setting. Two write-side defects shared the blame and are fixed with it: `save_config` wrote in place, so a crash or full disk mid-dump left the truncated file that bricked the next launch (it now writes beside the target, fsyncs, and replaces); and `get_default_config` seeded defaults through `save_config`, which honours `--config`, so a fresh work directory plus `--config my.yaml` overwrote the user's custom file with the template. The bundled template is also never a write target now -- several tests pointed `current_config_file` at it and were silently editing the shipped defaults, which is how one suite run could poison every later run. Tests: 10 recovery/atomicity cases plus 2 dialog-copy cases in `tests/test_config/test_broken_config_recovery.py` and `tests/test_widgets/test_config_recovery_warning.py`, and the full suite now finishes with the template byte-identical. Suite 1557 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **合并选中标注 no longer deletes the shapes it cannot merge.** The polygon path built one mask, kept only the largest exterior contour, then removed every selected shape -- so two disjoint polygons became one and the other vanished, with no prompt and no hint that the selection had been partial. A point or rotation selected alongside two rectangles was worse: it fed the mask as a one-point polygon and was then deleted with the originals, while the action was still enabled. The operation now lives in `utils/shape_union.py` and refuses what one shape cannot represent: the selection must be all rectangles or all polygons, polygons must form exactly one region with no hole, and the refusal names the reason in the status bar while leaving every shape untouched. The commit is one history step too: removing the rows used to rebuild `canvas.shapes` once per row, so the first Ctrl+Z resurrected one original, the next emptied the image, and only a third brought the selection back; the merged result now lands with a single push, and one undo restores both originals (asserted in smoke step 13). Differing classes ask first and name the class and attributes that survive (the last selected shape's), instead of letting selection order decide silently. The enabled state now requires an all-mergeable, same-kind, unlocked selection of at least two shapes, and leaving draw mode re-derives it from the selection instead of enabling it blindly, so the menu no longer offers a merge that would have to discard something. `render_visualization` also copies `shape_opacity` to its scratch canvas -- the saved picture used to paint annotations at full strength while the screen faded them. Tests: 15 operation/enable cases, plus smoke step 13 on a real widget (disjoint stays two, connected becomes one covering both), and a pixel test for the opacity copy. Suite 1557 passed / 1 skipped, smoke 15/15, acceptance 17/17.

### 🔗 CI / Tooling

- **The release checksum file covered only macOS.** Each matrix build wrote its own `release/SHA256SUMS.txt`; `actions/download-artifact` with `merge-multiple: true` kept the last platform's copy, so beta.7 shipped a 359-byte checksum file listing three macOS files while the Windows and Linux binaries sat beside it unhashed. The build jobs now only collect artifacts, and the publish job hashes the merged set once (excluding the macOS zip's own `.sha256`), so one `SHA256SUMS.txt` covers every released binary. The beta.7 release itself still carries the incomplete file; the fix applies to the next tag. No unit test can see a workflow merge collision — this entry is the evidence.

### 🛠 Improvements

- **The five former rc-only canvas knobs now have an end-to-end settings-page guard.** The three attribute colors and the two brush undo limits already had `SettingField`s and a runtime applier, but the only coverage was schema membership plus direct applier calls — a regression that stopped rendering Canvas, dropped a binding, or left the editor unwired would still pass. `tests/test_settings/test_canvas_knobs_page.py` now renders the real Canvas page: it asserts all five keys are bound and visible by label, that each is findable through the page's search, and that editing one brush step limit and one RGBA attribute color reaches both the controller and the runtime callback. Their labels/descriptions were bare Chinese variables passed to `self.tr`, which `pylupdate6` cannot see; they are wrapped in `QT_TRANSLATE_NOOP` with explicit `SettingsDialog` markers now, and the 10 catalog entries were filled. The old packaged `dist` exe predates the fields (they landed on 2026-10-17), so a rebuild is required for the packaged UI to show them. Suite 1685 passed / 1 skipped / 61 subtests, smoke 17/17, acceptance 17/17, black 206 files, flake8 214 findings with no regression.

- **Opening a several-thousand-image folder no longer freezes the window, and paging no longer measures the whole list.** Measured on 3000 labelled 96×128 images: the first cold import took **7–12s**, of which `_refresh_file_panel` was 6.8–12.3s, because the progress summary counted "待复核" by opening and parsing every label JSON on the UI thread (the async checker had only moved the review-header half). The count now reads a cached row role: `_refresh_file_progress` moved to `file_list_ops.refresh_file_progress`, and a second pass in the existing background checker computes low confidence from the shapes, applies it in batches, and fills the count afterwards — the slot shows `待复核 …` until then. Low-confidence parsing reads the file, closes it, then parses, so a delete or temp-folder cleanup cannot collide with an open JSON. The sync import dropped to **0.16s** (40×); the low-confidence pass still takes 8–11s on a cold cache but does not block the UI, and 0.89s warm. Separately, `setUniformItemSizes(True)` stopped Qt from measuring all 3000 rows on every `scrollToItem`: paging went from **32.8ms mean / 32.7ms p50** to **4.8ms mean / 4.6ms p50 / 5.3ms p95**, including while the background scan runs (p50 5.05ms). Eight new low-confidence/worker/placeholder tests, a uniform-size guard, four contract members (139 → 143), and the label-widget budget lowered 6697 → 6663. Full write-up with the baseline and profile: `reviews/large_folder_performance_2026-10-26.md`. Suite 1681 passed / 1 skipped / 61 subtests, smoke 17/17, acceptance 17/17, black 206 files, flake8 214 findings with no regression.

- **The smart-tools God module is gone, and the training dialog gave up its run-maintenance half.** `utils/smart_tools.py` carried 1920 lines and more than a dozen responsibilities; it is replaced by eight modules that follow the menu's own grouping: `smart_common.py` (shared label/path helpers), `smart_analysis.py` (threshold calibration and dataset intelligence), `smart_missing.py` (the scan thread and writer), `smart_stale.py` (audit, cleanup report, deletion), `smart_review.py` (iteration dashboard, review jump, relabel watch, training advice), `smart_archive.py`, `smart_backup.py`, `smart_prelabel.py`; the shared result dialog gained the background task thread and progress dialog in `smart_ui.py`. The old module is deleted rather than left as a re-export façade, and the widget, training dialog and tests import the feature modules directly; the largest new module is 470 lines. `UltralyticsDialog` drops 4559 → 4406 as `write_run_metadata` and `_offer_dataset_cleanup` move to `views/training/run_maintenance.py` behind two delegating stubs — the JSON fields, SHA-1s, stop/completed status and cleanup policy are unchanged, and the moved cleanup strings use `QCoreApplication.translate("LabelingWidget", ...)` so the catalog still sees them. The training dialog joins the size-budget ratchet at 4406; `label_widget.py` ends at 6663 and `canvas.py` stays at 3381. The catalog was regenerated with the repo's `pylupdate6`/`lrelease`/`rcc` flow, its moved and unfinished entries were filled, and the flake8 baseline was re-frozen at 214 findings because the old `smart_tools.py` keys no longer exist. Full write-up: `reviews/structural_split_final_2026-10-26.md`. Suite 1663 passed / 1 skipped / 61 subtests, smoke 17/17, acceptance 17/17, black 205 files.

- **The smart-tools result dialog moved to `smart_ui.py`.** Every action built the same tree, CSV export and jump/open buttons inside the 2120-line action module. The dialog, `_notify`, `label_dir_for` and the row-role constants now live in `utils/smart_ui.py` (306 lines); `smart_tools` imports the pieces its actions use and drops from 2120 to 1838 lines. A structural test blocks `smart_ui` from importing `smart_tools`, and the tests read the dialog and row roles from their new home. Suite 1641 passed / 1 skipped, smoke 15/15, acceptance 17/17.

- **The label-backup engine moved out of the smart-tools God module.** Backup retention, snapshot listing, restore planning/apply and the session marker were defined in `smart_tools.py`, so `session_snapshot` -- on the editor's every-write path -- imported the entire smart-tools UI module just to reach them. The engine now lives in `utils/label_backup.py` (177 lines): `smart_tools` imports the five entry points it still uses and drops from 2263 to 2120 lines, `session_snapshot` depends on the new module, and a structural test fails if the editor reaches into smart_tools again. Tests patch retention and copy failures at the new owner. Suite 1624 passed / 1 skipped, smoke 15/15, acceptance 17/17.

### 🔗 CI / Tooling

- **The packaged CPU build is now walked action by action, and the walkthrough caught an F1 that no unit test could.** PowerShell's `System.Windows.Automation` plus synthetic mouse/keyboard drove the real one-file `win-cpu` build -- no new Python dependency, which is what the 2026-10-17 review had left as a manual step. 83/83 checks: folder load and title, File-menu paging, the 显示标签 toggle, 统计总览 (defect ×2), Ctrl+0 settings and its search box, the theme confirmation writing `theme: dark` then restoring `auto`, YOLO HBB export through the native classes-file picker and the export-options dialog (`p0.txt`/`p1.txt` with normalized boxes, an empty negative-sample `p2.txt`, `classes.txt`, `data.yaml` and a manifest recording 3 images / 2 shapes / 1 missing label file), the empty run-history state, the CPU pack's honest 缺少 ultralytics message, the project manager listing the open folder, 项目属性 creating the record then reopening with the overview, renaming `alpha` → `alpha-final` in the title and `.jllabel/project.json`, F1 opening the 69-row shortcut sheet, 关闭项目 clearing the title, and a native `WM_CLOSE` leaving a 0-byte `faulthandler.log` and no exit error. It also reproduced the first fix's missing `actions.shortcuts_help` as a packaged startup crash, which is now held by a structural test. Two limits are recorded rather than hidden: the CPU pack cannot train (by design; the train spec is the onedir build), and a UIA-attached close leaves a COM exception in `faulthandler.log` while a native `WM_CLOSE` with no UIA client exits with a 0-byte log and no errors. Full write-up: `reviews/packaged_action_walkthrough_2026-10-26.md`. Suite 1663 passed / 1 skipped / 59 subtests, smoke 17/17, acceptance 17/17.

- **The smoke harness also walks the image-flag import's tail.** Step 15 drives the real `upload_image_flags_file` with only the file picker and toast stubbed, then asserts the flag dock lists the sanitized names, the config copy carries `flags`, and the widget is dirty -- i.e. the imported list reached the normal save path instead of being reloaded away. Smoke is 17 checks; the CI comment and the harness docstring follow. Suite 1645 passed / 1 skipped, acceptance 17/17.

- **The smoke harness now proves an imported class list survives.** Step 14 calls the real `apply_uploaded_labels` on the opened project, then reads the on-disk config copy and the project record and asserts both carry the new list -- the unit tests stub that save path, this walks it. Smoke is 16 checks now, and the CI comment and the harness docstring follow. Suite 1645 passed / 1 skipped, acceptance 17/17.

## `v1.0.0-beta.6` (Oct 19, 2026)

### ✨ New Features

- **OBB 越界策略 is an export option now: clamp the box to the image instead of dropping it.** `custom_to_yolo` accepted `obb_boundary_policy` from the start, but no caller passed it and no setting existed, so every export -- GUI, CLI and training split -- was locked to the `"skip"` default: a rotation with any vertex outside the frame vanished and the annotator only saw a count. The YOLO export dialog now shows 「越界旋转框裁剪到图像内」 in OBB mode, pre-checks it from the project's last-export record (`obb_boundary`, added to `project_model.EXPORT_PARAM_KEYS`), passes the choice to the converter, and records the effective policy in both the export manifest's `filters` and the remembered parameters -- so a directory of `.txt` files stays explainable months later. Two rules keep the new mode honest: clamping is per vertex, because YOLO OBB takes exactly four points and a real polygon clip would change that count; and a box whose vertices all land outside one edge collapses to zero area, so it is still skipped, with its own reason (`rotation collapsed after clamping`) translated in the recap. Any value other than `"clamp"` keeps behaving like skip, so a typo cannot silently export coordinates outside `[0, 1]`. Tests: exact-bytes converter cases for clamp, collapse and typo, plus `tests/test_utils/test_export_obb_option.py`, which walks the dialog path -- the box exists only for OBB, a remembered clamp comes back checked, and accepting the dialog writes the clamped line. Suite 1525 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **自动标注的「类别筛选」is a feature now, not two orphans.** `widgets/classes_filter_dialog.py` (134 lines) had never been constructed by any code, and `YOLO.set_auto_labeling_filter_classes()` had never been called by any interface -- the dialog and the setter shipped on either side of a gap nothing crossed. The panel's 「更多」 row now carries a **类别筛选** button that lists the loaded model's classes (with the dialog's own search box and 全选/取消全选) and hands the selection through `ModelManager` into the model's index filter, so a run emits boxes for the checked classes only. Wiring it up is where the failure modes were, and all three are now rules with tests behind them:
  - **A name this model does not have is dropped, never passed through.** An empty index list is not "nothing selected" to the post-processing mask -- `classes=[]` masks *every* class and the model returns nothing at all. So a remembered filter from another model, or a class renamed since, would have read as "the model broke"; it now reads as "no filter", the same way selecting every class and selecting none both mean unfiltered. `_YoloLikeModel` in the new tests copies `YOLO`'s six-line semantics verbatim rather than being a friendly stand-in, which is what makes the case testable at all.
  - **The filter belongs to the project.** The selection is written to the project record (`class_filter`, part of `UI_KEYS`, so 重置本项目设置 forgets it and the switcher's question now says so) and re-applied both when a model finishes loading and when a project opens. The re-apply is only half of it: a project that remembers *nothing* has to **clear** the filter, because selecting 只标 person in project A and then opening project B used to keep filtering B's model by A's classes with nothing on screen to explain the missing boxes.
  - **A filter you cannot see is still a filter.** The button reads `类别筛选 3/12` and names the classes in its tooltip, applying says so in the status bar (类别筛选已启用：仅标注 …), and because the button lives behind a collapsed 「更多」, an active filter moves that mark onto the 更多 button itself -- the state stays visible on the row the user can actually see. Selecting a different model clears it (the same path that hides the toolbar's per-model widgets drops the state and the mark), so no mark outlives the model it describes.
  Only models that understand the switch offer it: the button needs `set_auto_labeling_filter_classes` on the loaded model *and* a non-empty class list, so a classification model cannot be talked into promising a filter it does not perform, and the dialog refuses to open for one. 47 tests: the index math, the stale-memory and no-intersection cases, order following the model, project round trips through a real project file (including junk in the record reading as "no filter"), the 更多 mark in both directions, the model-switch reset, the dialog seam -- a cancelled dialog applies nothing -- the layout box of the
control once its panel is open, and the inherited dialog itself: pre-checked rows, `[]` meaning everything, search hiding rows without losing their checks, and 取消全选 touching only what is visible. 7 new strings went into `zh_CN.ts`; the dialog's inherited English sources were already cataloged (筛选类别 / 搜索类别… / 全选 / 取消全选 / 确认), so the panel opens in Chinese. `docs/zh_cn/fork_features.md` states the three rules where the rest of the per-project memory is described.

- **23 English strings stopped showing up in the Chinese UI, and a ratchet now keeps them out.** Hover the auto-labeling panel and the help was English (选择模型的提示、加前景点、清除所有提示… eleven tooltips), the range rows in the label manager and the shape manager still read `From:` / `To:` -- the same defect fixed today in 统计总览, in three other places -- the 本地 chip, the custom-model delete icon, and the training confirmation dialog (`Start Training` / `Ready to Start Training` / `The following command will be executed:`) all said it in English to a user whose entire interface is Chinese. They are Chinese source text behind `self.tr(...)` now, which also means they are in `zh_CN.ts` (1580 -> 1603 compiled entries, none left untranslated). `tests/test_utils/test_english_ui.py` is the part that keeps this from regrowing: it parses every source file and fails on an ASCII literal handed to `setText` / `setToolTip` / `setWindowTitle` / `setPlaceholderText` / `addItem` or a widget constructor, with a three-entry allowlist for the things that are not copy at all (a zoom `100`, the Ultralytics run name `exp`, a threshold `0.8`) -- and it fails the *other* way too, if an allowlisted literal disappears, so the list can only shrink. The catalog entries were filled with the repo's own `scripts/_fill_translations.py`, which is the tool for that job; hand-editing the `.ts` instead is how one run this week produced a greedy regex that ate `<source>` lines. Writing the gate also uncovered a repo bug of its own: `.gitignore` carried the broad pattern `*_ui.py` (meant for the one pyuic-generated file in the tree), which silently refused to let a test named `*_ui.py` be committed -- `git add` errored and the file simply stayed invisible. The rule now names `anylabeling/views/labeling/widgets/auto_labeling/auto_labeling_ui.py` instead.

- **The loop is now walked end to end by a gate, in one step.** `scripts/smoke_widget_paths.py` went from 11 steps to 14 checks: the new step takes a clean image with no label file, feeds it a real `AutoLabelingResult` through `new_shapes_from_auto_labeling`, and follows that box all the way out -- provenance stamped (`source: model`, `model: …`, plus the weight digest), written by the same debounced auto-save the 400 ms timer uses, marked 已确认 on its file-list row, then exported by the real YOLO path so the row lands in `img_1.txt` and the manifest counts it. Only inference is faked. Nothing in the repo used to connect these stages: unit tests covered the model panel's plumbing, step 7 exported shapes a human had drawn, and the fork's pitch is "the model labels the next batch" -- a break in any hand-off between those stages was catchable only by hand. This gate runs on every push (the CI smoke job), so it is not a local script someone has to remember. Two facts the draft surfaced on the way: `save_file()` on an image that never had a label file falls through to a 「选择文件」 dialog -- the loop's own path is the auto-save flush -- and a file-list row's `UserRole` is its checked flag, not its path, so the row is reached through `widget.fn_to_index`. Offscreen the 还没有类别 hint defers rather than showing, so the step tolerates its absence and fails on any *other* modal: a surprise dialog is named instead of hanging the run, which is how the first version behaved.

- **The export recap explains skipped shapes in Chinese.** The recap already itemized what an export dropped -- 「跳过 N 个无法转换的标注」 with one line each -- but the reason itself was the converter's internal code printed raw: 「4 × polygon is not part of a hbb export」, 「1 × label not in classes: dog」 inside an otherwise Chinese dialog, and the fork feature page advertised exactly that. `_skip_reason_text` now renders each of the six reasons the converter can emit (label not in classes / polygon with < 3 points / rotation with N points / rotation reaching outside the image / X cannot be a pose keypoint / X is not part of a Y export) as a Chinese sentence that keeps the internal code in it -- 形状类型 polygon 不属于 hbb 导出 -- because that code is what the user has to look up in `export_manifest.json`. The manifest keys stay English on purpose: a key that changed wording with the UI language could not be diffed between two exports. An unmapped reason passes through rather than disappearing behind the table. The guard reads the reason templates out of `label_converter.py` and fails if any of them renders as English, so adding a reason without teaching the dialog about it is a test failure now, not a silent regression. 5 new tests; the existing summary test asserts the new wording and that no raw code phrase survives.

- **29 user-visible strings that the translation catalog had never seen are in it now, and a test keeps them from disappearing again.** The fork writes Chinese source text, so an unreachable string looks fine on screen -- which is why this went unnoticed: `pylupdate6` can only attribute a `tr()` call when it can see the receiver, so `self.tr("...")` inside a class is cataloged while `widget.tr("...")` handed to a module-level util function is **dropped silently**. That is what export.py had been doing for 21 strings (the whole YOLO recap: 导出完成：%d/%d 张图… / 跳过 %d 个无法转换的标注： / 已写入 … / 复制输出路径), the file list's review-rejection presets another 6 (漏标 / 类别错误 / 框不准 / 多标/误标 / 打回并下一张 …), and two dock tooltips the rest. They now call `QCoreApplication.translate("LabelingWidget", ...)`, which the extractor does read, and the compiled catalog went from 1554 to 1574 entries with nothing left untranslated. `test_no_tr_call_is_invisible_to_the_extractor` parses every source file with `ast` and fails on any `tr()` call whose receiver is not `self`/`cls` -- the check that would have caught the 772-location drift found in the catalog on 2026-10-10, and the reason a future batch cannot repeat it. The English strings that surfaced this way got proper Chinese (Select the class list → 选择类别列表) instead of the source echoing back. `label_widget.py` grows 4 lines purely because the qualified call is longer (6768 → 6772, documented); no logic moved.

- **The 还没有类别 hint is advice now, not a modal on every folder open.** The 2026-10-10 machine check counted **eleven** of these dialogs inside nine steps: `load_dir` ended with the prompt unconditionally, so 关闭项目后重开 and every 切换项目 raised another one — and the check's own step 5 turned into "first answer a dialog, then get back to the third image". A project is asked **once per session**, and the dialog gained a fourth button, 不再提示, which records the choice in the project settings so a restart stays quiet; 项目切换器 → 重置本项目设置 is the way back (the hint key joins `project_settings.UI_KEYS`, and the reset dialog's question now says it clears 提示开关 too). The hint moved out of the widget into `utils/missing_classes_hint.py`, which is also where its dedup table and the per-project mute live; `label_widget` keeps the contract method as a one-line delegation and gives 29 lines back to its size budget (6797 → 6768, the first headroom the file has had in a week). Its strings go through `QCoreApplication.translate`, not `widget.tr()` — the extractor cannot place a `tr()` call whose receiver it cannot see, and the strings would leave the catalog silently. 15 tests cover the rules (classes present, one prompt per project, silence across rebuilt widget objects and across two spellings of one folder, the mute round-tripping through the project file, a failed mute write being reported, the four buttons, the vanished-folder and not-yet-visible cases), and acceptance step 14 guards the rule on a real window — where it caught the first version of the fix counting per widget object rather than per process. Two leftovers found while rebuilding the catalog: the 概览 range row shipped **English** labels and a button in a Chinese UI (`From:`, `To:`, and a `tr("Go")` whose catalog entry was empty), which now read 起始：/结束：/跳转. The fork feature page also catches up with last batch's 返工 banner and 负样本 filter, which shipped undocumented.

- **The project overview now answers two more questions, and 项目菜单 can open the data folder.** First: the properties dialog's 概览 showed progress and training but not the two things that decide whether a project is safe to hand to training -- **which labels it uses** and **where its last export went**. Both now render there (`标签 3 个：划痕、凹坑、气泡`, long lists stop at six; `上次导出：G:/out（yolo，2026-10-14 09:20:11）`), fed by two new `project_dashboard` collectors that read the record and degrade to silence rather than blocking the dialog. The snapshot gained an `at` timestamp so the line can say *when* -- a path without a date cannot answer "is this export stale?". Second: **打开项目文件夹**, paired with the existing 打开项目设置文件夹 and placed before it, because nine times out of ten the user wants the data (images, labels, export output), not the .jllabel directory. 11 tests, plus acceptance step 13 on real windows. Separately found along the way -- and left for its own batch -- 77 call sites wrap strings in a per-module `_tr()` helper, which `lupdate` cannot see through: none of those strings are in the translation catalogue. Invisible in the Chinese UI (the source *is* Chinese), wrong for any future English one.

- **工具 → 设备: the device is now a menu, and the menu can say card names.** The previous batch made `GPU:1` expressible but left it reachable only by hand-editing the rc or exporting an environment variable. A 设备 submenu under 工具 lists what this machine offers as a radio group — `CPU`, `GPU · RTX 4090`, `GPU:1 · RTX 3060` — and selection writes the choice back to the config (下次加载模型时生效; a loaded model is not hot-swapped). An out-of-range pick reports the fallback in the status bar instead of leaving a tick that lies. 重新检测设备 re-probes in place, which is the whole point of `refresh_devices`: install onnxruntime-gpu and the card appears without a restart. The menu lives in `utils/device_menu.py` and the widget contributes two lines (import + call, size budget 6785 → 6787, documented) — the settings schema was the wrong home because its `options` are a static tuple validated with `value in options`, which cannot express a machine-dependent list. Building the menu never imports torch on a CPU-only machine. 7 tests drive a real `QMenu`: the entries per machine shape, the current device being the ticked one, selection persisting, the impossible-index report, refresh showing a card that appeared, and a widget without a tool menu being left alone.

- **The device manager can name a card, and says why a GPU goes unused.** Two gaps, both hit by real machines. First, multi-card hosts could only ask for "GPU", which always meant card 0 — the device string now takes an index (`GPU:1`, `CUDA:2`, `gpu:1` all normalize to one spelling), an index past the end falls back to card 0 with a warning instead of an error, and `OnnxBaseModel` passes `device_id` to `CUDAExecutionProvider` so the chosen card is the card used. Second, and worse, a machine with an NVIDIA card but a CPU-only onnxruntime **silently ran on CPU**: the only symptom is "auto labeling feels slow", which is not something a user can act on. The model-load-failed dialog now says it out loud — 「本机有 NVIDIA GPU（RTX 4090），但当前 onnxruntime 未启用 CUDA…安装 onnxruntime-gpu 后可用 GPU 加速」 — via `DeviceManager.gpu_advice()`, which stays silent on machines where there is nothing to fix. Startup logs one line (`🧮 Auto-labeling device: …`) so "why is this slow" has a first place to look, `describe_devices()` gives a readable summary for diagnosis, and `refresh_devices()` re-probes without a restart (probing is cached, and the startup path deliberately never imports torch for it — card counting happens only when an index is asked for). 34 tests: spec normalization, per-card selection, out-of-range fallback, source precedence, description and advice wording, and cache/refresh behaviour. A device *picker* in the UI is not part of this batch — the settings schema's static `options` cannot express a machine-dependent list, so that needs its own design pass.

- **The recycle-bin channel refuses volumes that have no recycle bin.** `FOF_ALLOWUNDO` means "use the bin **when there is one**" — on a network share or a RAM disk the same `SHFileOperationW` call deletes **permanently**, which is exactly what this channel promises never to do. `GetDriveTypeW` now gates the operation: only fixed and removable drives (the ones with bins) go through; a network, RAM-disk, optical or unrecognizable volume reads as a refusal — False, nothing deleted, the dialog says to handle it manually. 2 more tests: the refused drive types and the volume-root extraction.

- **The second export needs no re-typing: the parameters travel with the project.** Every YOLO export made the user rebuild the same dialog — the save path defaulted to a guessed `../labels`, the three checkboxes started from False, even though the project record already knew where this project's exports belong. Now a successful export leaves a whitelisted parameter snapshot (`last_export`: save path, save-with-images, skip-empty, only-confirmed, classes.txt, manifest, mode) in the project record, and the next dialog pre-fills every field from it — path falls back to the project's `output_dir`, then the old guess, and a vanished save path is not pre-filled (a directory that no longer exists must not look like a choice). Not a project? The dialog opens exactly as before. This is "自动导出" kept honest: the second export is one confirmation away, but nothing ever writes to disk without the user pressing OK — counts and class lists stay in the export manifest, the record only answers "how did I export this project last time". 5 tests: whitelist-only keys, the empty snapshot for a folder without a record, the refusal to remember one, overwrite-on-new-export, and a damaged snapshot reading as empty.

- **A full recent-projects list now evicts by a stated order, and says who left.** When the registry hit its 20-entry cap the cut was `projects[:20]` — silent, and blind to what was being cut: entries whose folder no longer exists (the switcher never shows them) occupied real slots, while a moved hard drive's entries sat one opening away from being dropped. The policy now reads: when the list overflows, vanished folders make way first — only then, if slots are still short, does the oldest entry go, and the entry being recorded is never evicted. Under the limit nothing is pruned, because a missing folder may be a drive that comes back. Eviction is not silent: `on_evicted` hands the caller the roots that left, and both recording paths put one status-bar line — 最近项目已满，已移出列表（数据与设置不受影响）：… — because a row disappearing without a word reads exactly like lost data. The datasets themselves are never touched; only the convenience list shrinks. 8 tests pin the order, the never-evict-the-current rule, the vanished-first rule, keeping vanished entries while under the limit, the callback contract, and a failing callback never blocking the record.

- **项目内搜索 answers "which images still need work" without walking the file list by hand.** A per-project progress column says how much is left; it cannot say where. The 项目 menu gains 项目内搜索…: a state (未标注 / 未复检 / 已确认 / 待复检), an optional label-name substring (case-insensitive), and the results land in one list — filename, state, labels — double-click to jump there through the same navigation gate the arrow keys use (drawing in progress and unsaved changes are respected, and the jump closes the dialog because the search did its job). Matching lives in `utils/project_search.py` as a pure disk-read function using the same head-read the file list uses, so the three surfaces can never disagree about what 已确认 means; a damaged label file is data (未标注), not an error. The dialog searches the session's own file list in a `QThreadPool` worker — one generation number per search, a stale generation's late results are dropped, and an empty session says 当前没有打开的图片 instead of pretending to search. 13 tests: the four states, substring stacking with state, the damaged-file rule, order preservation, criteria from the session, result rows and the count line, stale-generation drops, no-match wording, the jump and its refusal when unsaved work is pending.

- **The project manager now answers "how far along is each project" at a glance.** The switcher's five columns said when a project was last opened and how often it trained, but the number that actually decides which project to open next — how much of it is labeled — lived in the properties dialog of each folder, one dialog per project. The manager gains a 标注进度 column: `12/40`, annotated over images, counted by `project_dashboard.collect_progress` from disk, the same scan the file list uses so the two can never disagree about what counts as labeled. Counting happens in `QThreadPool` workers so the dialog opens instantly on twenty datasets of any size — each row shows 计数中… until its count lands, a count that cannot be made leaves the placeholder (a missing column beats a broken dialog), and a result for a row that has since gone is dropped, not an error. The confirmed/rework split rides along in the tooltip. 6 tests: the `format_progress` shaping (dashes for an image-less project), the column's existence and placeholder, a result landing in its own row with the tooltip split, an unknown root being dropped, and an empty registry staying quiet.

- **删除项目数据 exists, and it goes to the recycle bin or it does not happen.** The switcher could forget a project from the list, but the folder itself — images, labels, the work of days — had no path out, and the one way out a script reaches for (`shutil.rmtree`) does not use the recycle bin. The switcher gains 删除项目数据…: two confirmations (the first names the project and spells out that 只想忘掉的话请用「从列表移除」, the second shows the full path again; both default to cancel), then the folder goes through `utils/recycle_bin.py` — `SHFileOperationW` with `FOF_ALLOWUNDO`, zero dependencies, recoverable. A failing or declined channel means **nothing was deleted** and the dialog says so with the path for manual handling; the module never falls back to an irreversible delete on a platform without a bin. Deleting the currently open project closes it first through the usual unsaved-work question, and the registry entry goes only after the recycle succeeded. 10 tests: the channel's contract (absolute path in, False-means-refused, a missing path never reaches the operation), the volume-type gate, and the flow's gates — a declined confirm touches nothing, a successful delete forgets the entry, a failed recycle keeps it, and the open project closes before the folder goes.

- **The project record is the one place labels live.** Two sources used to answer "what can I label": a folder's `classes.txt` (authoritative on every open) and the project record (only a fallback for an empty panel) — so a label added through the label manager survived the leaving flush into the record and was then silently overwritten by the stale file on the next open. The panel now opens on the record when it carries labels; `classes.txt` is the seed a folder ships and is read only while the record has none (the panel it seeds lands in the record with the leaving flush, so the two can disagree for one session at most — a dataset stays read-only on open). When the record wins but a disagreeing `classes.txt` sits beside it, the status bar says so: a hand-edited file that "did nothing" must not be a silent nothing. The resolution itself lives in `project_settings.resolve_open_labels`, and `_load_classes_from_folder` delegates — the widget keeps the panel surgery and loses the precedence decision. Nothing changes for a folder without a record: `classes.txt` opens exactly as before. 6 new tests pin the precedence, the conflict notice (and its absence when the two agree), the read-only open, and the seed-then-flush handoff.

- **A project packs into one zip and comes back out of it.** "The record travels with the data" makes migration almost free — but free is not the same as one click. The 项目 menu gains 导出项目包… (the whole dataset folder — images, labels, `.jllabel` — into a zip, arcnames under the folder's own name, stored uncompressed because deflate cannot shrink jpegs and the minutes it would burn on a many-GB folder are real) and 从项目包导入… (peek inside without unpacking, show the project's name and task, unpack under a chosen parent and open it). Both run with a progress dialog and a cancel that cleans up: a cancelled export removes the half-written zip, because a残缺 archive that calls itself a project bundle is worse than none. The import is paranoid on three fronts: anything that is not a single-folder bundle is refused before a dialog is even confirmed; every entry is checked **before the first byte is written**, so "整体拒绝" is literal (a `plates/../x` entry ends the import, it does not skip past it); and entries are placed by their path *relative to* the bundle's top folder — the first cut joined the top twice and unpacked into `plates/plates/`, which no count-based assertion could see and only reading a file back could. A bundle whose folder never had a record still imports (it is a folder, after all); its 概览 simply has nothing to show. 13 tests in `tests/test_utils/test_project_bundle.py`: the packing shape, progress/cancel cleanup, self-exclusion of the archive's own target, the peek's three refusals (flat, multi-top, damaged), the round trip into a real `describe()`-able project, the existing-target refusal, and the slip guard.

- **新建项目 can start from what a previous project already knew.** The wizard's second project of the same kind used to begin from a blank page: re-type the class list, re-pick the task, re-tune the hyperparameters. The wizard now offers a 设置模板 combo listing the projects that really carry a record (registry order, the target itself excluded, merely-opened folders never qualify); picking one preselects its task kind on the spot, and on save `project_model.apply_template` copies exactly two things onto the fresh record — the label list and the trainer's whitelisted `train_prefs`. Everything path-bound stays behind on purpose: no `output_dir` (the new folder must not inherit another folder's paths), no `last_file`, no `split_seed` (the resume point and the split comparability are per-project by design), no name. A failed template copy is a logged warning and a project with defaults — the project exists either way, so nothing stands in front of it. The task written to the record stays the radio buttons' choice: the template only suggests it. 11 tests in `tests/test_utils/test_project_template.py` pin what the template carries, what it deliberately leaves, the refuse-missing-record guard, the combo's task preselection and the candidate list's boundaries — plus one bite from a real trap: a `QApplication([])` kept in a temporary is garbage collected, and the next widget creation dies a native death (exit 127), so the Qt tests now hold the app.

- **项目属性 now answers "where is this project" before asking what to call it.** The annotation progress lived in the file panel's row data and the training rounds in the experiment history — "where is this project" was never answerable in one place. An existing project's properties dialog opens with a read-only 项目概览 block: 已标 X/Y · 已确认 Z · 需返工 W, then 训练 N 轮 with the best mAP50 and the run that holds it, plus the most recent round and when it finished (or 尚未训练). Nothing new is stored: `views/labeling/project_dashboard.py` recounts both halves from disk on open — progress through the same head-scan the file list uses (so the two cannot disagree about what 已确认 means), training through `run_history.project_run_rows`, the single-anchor form of the project list's closest-ancestor attribution, added to `run_history.py` so the rows and the list's numbers cannot drift. A missing runs directory or an unreadable label file reads as "none"/"unreviewed", never an error — the overview must not become a reason the properties dialog fails to open. A folder without a record (the not-a-project-yet path) shows nothing, as before. 10 tests in `tests/test_utils/test_project_dashboard.py`: the counting, the output-dir override, prefix-boundary attribution, the never-trained shape, and the rendered lines.

- **"Which project is open" has one owner now.** The training dialog, the auto-labeling panel and the project UI each carried a private copy of the same parent-walk (`parent → _project_dataset_dir → guess from the image list`), agreeing only by discipline. `views/labeling/project_context.py` is a read-only snapshot module — `current_dataset_dir` / `current_task` / `current_name` — and the dialog and panel helpers now delegate to it, so the answers agree by construction. It is deliberately not a state holder (a second writable copy is how the two recent-project lists once drifted), it accepts both parent shapes (real widgets expose `parent()`, test stand-ins a plain attribute), and a vanished folder still reads as "nothing open". `tests/test_labeling/test_project_context.py` (8 tests) pins the walk, both parent shapes and the vanished-folder rule.

- **A project remembers the auto-labeling model it was worked with.** The model choice lived only in memory (`_last_model_selection`), so switching to another project and coming back meant finding the model again — the gap L3 closed for the image position and L4 for the task kind. Selecting a model now records `{provider, model}` in the project's own record, and only those two facts: the config path is the panel registry's business, and storing it would leave a dead reference the first time a weights file moves. Opening a project puts the panel back on that model through the same path a click takes — the button text, the hidden labeling widgets and `_last_model_selection` all follow — so a restored model cannot leave the panel claiming nothing is selected while something is loaded. It declines quietly in the two cases that do not deserve a dialog: the model is already the selected one (the away-and-back case), or the registry no longer knows it (deleted, or dropped from the list while this project was closed). Restoring cannot cause a download, because the memory is of a model already run here. `last_model` joins the keys 「重置本项目设置」 clears, so a project can still be put back to defaults without disturbing its split seed. 17 tests: `tests/test_auto_labeling/test_project_model_memory.py` drives the real panel in both directions (recording on selection, restoring on open, the already-selected skip, a model that is gone, no project context), and `tests/test_utils/test_project_settings.py` covers the record, the failed-write warning, the model-key reset, and a panel that raises — a memory must never be the reason a project fails to open.

- **The whole right sidebar leaves the screen in one click.** Labels, Objects, Files and the thumbnail box are one unit now: a 14-px strip at the sidebar's edge carries a caret that hides all of it — and brings all of it back — so the canvas can take the full window width without hiding three panels by hand. The strip deliberately does not hide with the panel, because a collapse with nothing left to click is not reversible, and the caret plus its tooltip name the action they offer (收起 / 展开). The state is remembered in the config (`sidebar.collapsed`) and replayed at startup without rewriting it. Assembly and logic live in `utils/panel_visibility.py`, the module that already owns these toggles — which is also why the widget's size ratchet stayed at 6817: `_build_layout` gained one call instead of forty lines. `tests/test_labeling/test_sidebar_collapse.py` pins the container contract (thumbnail, flag dock, labels, objects, files and the search row must all be inside the widget that gets hidden, or "collapse" would quietly stop covering the sidebar), both click directions, the tooltip/icon swap, and the write-on-change/replay-without-rewrite pair; `CONTRACT_MEMBERS` grew 125 → 128.
- **An export writes down how it was made.** A directory of YOLO `.txt` files is not self-describing: the class list decides what every `0 1 2` in them means, and the filters decide which images never made it in — neither is recoverable from the output. The export directory now gets an `export_manifest.json` (a checkbox in the export options, on by default) recording the class list *and where it came from*, the mode, the filters that were on (仅已确认 / 跳过空标注 / 复制图片 / 是否写了 classes.txt), the counts the run reported (images, shapes, copies, unconfirmed skips, missing label files, skipped shapes by reason) and what the pre-export check found in the source data. Nothing reads it and deleting it changes nothing — it exists so "how was this batch exported" is answerable months later.
- **The last twenty-two keyless actions are rebindable, and the F1 sheet stops staying silent about them.** The audit's finding was never "no key" — most of these are one-off menu items (a file dialog, a batch export, a training launcher) that need none on day one — it was "no key *and* no way to bind one": the keys were absent from the template, so the settings dialog had no row and F1 had nothing to show. All 22 exist in the template now with a `null` default (118 shortcut keys: 96 ship with a key, 22 deliberately empty), and `runtime_applier` binds them through one generic loop that resolves each by name and feeds the apply pass that was already there — it handles `None` by clearing, so nothing had to change for the unbound state. F1 gained a trailing 未绑定动作（可在设置页绑键）section naming each one while it has no key; it empties itself as keys are chosen, so the sheet can neither claim a key that does not exist nor hide a feature that does. Three guards keep the new axis honest: the declared actions must exist in the template, must resolve to a real action on the live widget, and the ghost-key check counts them as consumed only while the applier loop is present.
- Side effect worth naming: `label_widget.py` came out **eight lines shorter** — three `widget.actions` members in, ten digit registrations collapsed into a loop out — so the size ratchet tightened to 6805 rather than being raised again.
- **The interface finally calls a dataset a 项目, and the two "recent" lists became one.** The app has treated "the folder you opened" as the unit of work for a while — `.jllabel/project.json` beside the data, a registry of recent datasets, a switcher dialog — but nothing on screen said so: the File menu offered `Open Dir` next to a separate 打开最近文件夹, the title bar named only the image, and a project could not be closed. Four changes, all presentation: the File menu gains a 项目 submenu (切换项目… / 打开最近项目 / 打开项目设置文件夹 / 关闭项目), the title bar leads with the project name (`… - [myproj] - a.png* [3/120]`, unchanged when no folder is open), the empty canvas says 打开或新建项目, and 关闭项目 clears the file list and returns there after the usual unsaved-work confirmation. The recent list is read from `projects.json` now, and the older QSettings key is migrated into it on first read — so 打开最近项目 and the switcher dialog can no longer disagree about what was opened last, which they did whenever the two lists drifted. Identity stays the folder path (no uuid, no alias table), so no existing dataset moves and no file format changes. The logic lives in `views/labeling/utils/project_view.py` and `LabelingWidget` only delegates — retiring `_recent_dir_list` / `_update_recent_dirs_menu` against the delegations and the menu call made the owner come out **nine lines shorter** (6817 → 6808), so the size ratchet tightened rather than being raised. 14 tests in `tests/test_utils/test_project_view.py` pin the migration (including "already recorded, only the key is dropped" and an unreadable settings object), and the existing widget-wiring test now asserts the opened folder lands in the registry.
- **A dataset can name itself and say what it is for.** The interface learned the word 项目 last batch; this one gives a project something to *be* — a display name, a task kind and a creation date — by taking `project.json` from schema 1 to 2. The name is a label and nothing else: identity is still the folder path, with no uuid and no alias table, so renaming a project never moves a byte on disk (a test asserts the directory keeps its name). `文件 → 项目` gains 新建项目… (pick a folder, name it, choose Detect / Segment / Pose / Classify) and 项目属性… (rename, change the task, and — for a folder that was only ever opened — create its record), the switcher grew a 任务 column and now shows the recorded name instead of the folder name, and the title bar shows it too. Records written before schema 2 are completed **in memory** when read and pick up the new fields on the next save, so opening a folder still writes nothing; `tests/test_utils/test_project_model.py` pins that with a byte-for-byte comparison of the file before and after a read, plus "an existing name survives the migration", "an unknown task falls back to the default", "`create()` refuses to overwrite a record already there" and "the split seed still round-trips". The task list is a deliberate copy of the training side's `TASK_TYPES` rather than an import — annotating must not pull in the training package — and a test keeps the two sets equal. Not one line was added to `label_widget.py` for any of this: the new actions call `project_view` directly, so the ratchet held at 6808.
- **A project setting that cannot be saved now says so, once.** `project.json` lives inside the dataset, so on a read-only or network folder every save failed silently: the label panel accepted the new list, and after a restart it was gone — the quiet-loss failure this fork has been closing everywhere else. `save_current_labels` and `record_output_dir_change` check their write now; a failure raises one dialog per dataset per session (naming the directory and what was not kept) while the log records every occurrence, so a run of folder switches cannot stack boxes the annotator can do nothing about. Three tests in `tests/test_utils/test_project_settings.py`: a failed write warns exactly once across repeated attempts, a panel save routes through it, and a successful write stays silent.
- **A project remembers where you were, not just which folder was open.** Until now there was one global "last image": switching to another project overwrote it, so coming back meant hunting for the frame you had been working in. Each project now records its own position — `last_file` in `project.json` — at the moments you leave it (switching away, closing the project, quitting) and reopens there. The path is stored relative to the dataset folder, so a copied or moved project keeps working; an image that has since been deleted falls through to the first image instead of turning into a phantom row; and the record itself is deliberately left alone, because the drive may come back. The switcher's tooltip names the remembered image and the creation date. Startup follows the same rule — the project's own position first, with the old global `filename` kept as a fallback for sessions that predate this — and the three-way preference is pinned by tests. `tests/test_utils/test_project_resume.py` (18 tests) covers relative vs absolute storage, "unchanged position, no write", the deleted-image fall-through, the startup order, and that a stale path cannot survive into a freshly scanned image list. Moving `session_resume_path` / `continue_last_session` out of the widget into `project_view` left `label_widget.py` **27 lines shorter** (6808 → 6781), so the size ratchet tightened again rather than being raised.
- **The task a project declares now reaches the trainer, and what the trainer runs comes back.** Projects have carried a task kind since the record gained one, but nothing consumed it: opening a project that says 实例分割 still meant picking Segment by hand in the training window every time — and picking wrong there is only discovered after a full run, as a dataset that converted into an empty one. The Data tab preselected nothing before; it now preselects the project's kind, and committing a run writes the chosen kind back to the record, so the project ends up agreeing with what was actually trained. It is deliberately limited to folders that carry a record: one that was merely opened keeps the old "nothing selected yet" start, because guessing a task there is guessing at the user's expense. `tests/test_auto_training/test_project_task.py` (7 tests) drives the real dialog in both directions, including a corrupt record falling back to the default and a plain folder still selecting nothing.
- **What this batch turned out to be, having gone and looked.** It was planned as "resource isolation", and the audit found two of its three items already built — and better than the plan claimed. The training statistics already join runs to projects through `run_meta.dataset.label_dir` with a closest-ancestor match, not the path-prefix guess the roadmap assumed; and the per-project surfaces are all in place: the label list, the output-directory override, the pinned split seed, the per-folder calibrated thresholds, and the whole whitelisted training tuning (`train_prefs`, rewritten on every committed run). The third item, a general per-project override for `get_config()`, is deliberately **not** built: what remains in the global rc is exactly the set that *should* be global (theme, font, shortcuts, window layout, device), and a general override layer would give every one of those a second possible source for nothing the user can see. The genuine gap was the second half of the task kind, above.

### 🐛 Bug Fixes

- **COCO pose annotations took `ignore` from whichever shape happened to be last, and the COCO output now has content tests.** The three export modes had only "the aggregate file exists" behind them. New tests pin the facts consumers rely on: rectangle category ids in class-list order and pixel bboxes; polygon category ids (with `_background_` at 0) plus instance grouping by `(label, group_id)` and raw segmentation vertices; pose boxes, keypoints and `num_keypoints`. Writing the pose case exposed the leak: `ignore` read the `difficult` flag left over from the last shape in the file instead of the group's own box, so one hard box could mark every pose annotation in the image, and a hard box followed by a normal keypoint lost its flag. The group now carries its own flag. The polygon bbox convention (pycocotools' inclusive `max - min + 1`, as floats) is pinned too. Suite 1529 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **`--skip-empty-files` now cleans the output, and VOC no longer writes geometry-less objects.** Two halves of one promise. The CLI counted an all-skipped file as skipped but left the zero-object `.txt`/`.xml` in the output directory, where a later training run or a colleague picks it up; it now removes the file, exactly as the GUI export already does. Writing the test exposed the second half: `custom_to_voc` appended the `<object>` element before checking whether the shape could be expressed, so a polygon in a rectangle export (or a 2-point polygon) produced an object with a name and no `<bndbox>`/`<polygon>` -- an annotation every VOC consumer must either reject or silently drop, and this fork's own importer skips it with a warning. Objects are now created only by the branches that can fill them. Four tests in `tests/test_utils/test_cli_convert_skip_empty.py` pin both flags on both formats: skip removes the file, no-skip keeps the empty `.txt` / the objectless `<annotation>`. Suite 1520 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **跳过空标注 now holds in the training split too.** An image can pass `partition_images` (it has a shape type this task can express) and still end up with zero exported shapes -- a class missing from `data.yaml`, or the out-of-bounds rotation the default OBB policy drops. The converter reports the file as empty, and the dataset builder used to leave an empty `.txt` beside the copied image, so with 「Skip Empty Files」 checked the image still entered training as a background sample -- the exact opposite of its tooltip, "Leave images with no shapes out of training". The split writers now return only the pairs they actually wrote; an all-skipped image is dropped from `images/` **and** `labels/`, and the build says so (a `dataset_info.txt` line plus `skipped.empty_after_conversion` in the manifest). The counts and the manifest's `files` list are built from the filtered pairs, so they describe the dataset that exists rather than the one that was requested. Two tests pin both directions: checked leaves no image, no `.txt`, `counts.train == 0` and records the path; unchecked keeps the empty file as the intended background sample. Suite 1516 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **批量改 group id wrote every frame's shapes backwards, and the classes hint could fire on a destroyed view.** Two defects that content-level tests catch and call-level tests cannot. `GroupIDModifyDialog.modify_group_id` rebuilt `data["shapes"]` by walking `reversed(src_shapes)` (and removing items from the very list it was walking), so the file it saved held the shapes in the opposite order from the one they were drawn in -- for every frame in the range, on every run, even when nothing was deleted. The label list, the YOLO export and 类别统计 all read that order. It now filters forward and appends in place, which fixes the order and drops the mutation-during-iteration in the same breath. The second one is a crash that nobody could see: `_schedule` hands an 800 ms `QTimer.singleShot` a lambda holding the labeling widget, so 关闭项目 or a project switch that destroys that view leaves the retry alive; it then read `widget.unique_label_list.count()` on a deleted C++ object and raised `RuntimeError: wrapped C/C++ object of type UniqueLabelQListWidget has been deleted` **inside the Qt event loop**, where no dialog shows it and the surviving traceback names only the timer. `maybe_prompt` now drops a retry whose view is gone (`_is_gone`, through `PyQt6.sip.isdeleted`; the plain test doubles this package is fed stay live, because a fake is not a Qt object). How it surfaced is worth keeping: the suite was green for weeks, and the exception only appeared as a call error in an unrelated splitter test once the new range-editor dialogs let the event loop turn -- "tests pass" and "nothing raised in the event loop" are different claims. These are the four new tests: the group editor's snapshot still holds `cat, dog` after a group is dropped, append leaves `cat` recoverable, removal leaves `cat, dog`, and the group editor's order assertion; `delete_images_in_range` is covered too -- its test reads the removed image's `dog` box back out of `.label_backups/<run>/` while its neighbour stays untouched, and the fixture now nests images under `images/` because the method's sibling `_delete_` folder must land inside the test's own holder rather than the shared temp root. Suite 1508 passed / 1 skipped, smoke 14/14, acceptance 17/17, black 195 files, flake8 baseline clean.

- **The training panel told users in English that training had died, and a new ratchet keeps the whole catalog honest about it.** `UltralyticsDialog` renders a training-subprocess failure as 「%s — the training subprocess terminated unexpectedly. Please check the training log above for details.」 -- an English source whose `zh_CN.ts` entry was *identical to itself*, so the translator returned English and the message a user reads at the worst possible moment was the one string the Chinese UI did not have. It slipped through both existing guards: the English-copy ratchet looks at ASCII literals handed to widget setters (this one arrives through a log-append path), and `test_catalog_is_fully_translated` only asks whether a translation is *empty* -- a filled-but-unchanged entry looks finished. The source is Chinese now (「%s —— 训练子进程意外结束，请查看上方训练日志。」, per the fork's convention), and `tests/test_utils/test_translations.py` gained the two checks that were missing: every Latin-only source must be answered with non-empty, non-`unfinished` Chinese (measured: 1035 such sources, 0 silent), and the set of sources that legitimately translate to themselves is pinned to 14 named entries (`AMG`, `AI`, `YOLO HBB/Seg/OBB/Pose`, `loss %1`, `mAP50 %1`, coordinate and count formats) -- the ratchet fails both when a new English-on-screen string appears and when an allowlisted one disappears. Found by writing the guard, not by a user report: the guard failed on its first run, which is the point. Suite 1481 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **Three label deletions now snapshot too, and the invariant covers `os.remove`.** The scan that checks the writers asked the wrong verb: a function can destroy a label file by *deleting* it as easily as by overwriting it. Extending it to `os.remove(label_file)` found three sites, one of which contradicted the app's own promise -- `delete_image_file` moves the image into `_delete_` and tells the user 「可从该目录找回」, then removed the annotation permanently; `ShapeModifyDialog.delete_images_in_range` did the same while moving images to a chosen folder, and `remove_selected_shapes_in_range` deleted the whole JSON whenever the removed shapes happened to be every shape in the file (the partial case snapshotted, the total case did not -- so the more you deleted, the less recoverable it was). All three now copy the file into `.label_backups/<run>/` first, which is what 智能工具 → 从备份恢复标注 reads, so a deletion becomes a move with an undo instead of an end. The invariant's coverage list names all three so a future `os.remove` cannot slip past. Step 6 of `scripts/smoke_widget_paths.py` now asserts this end to end: it writes a label for the image it deletes and checks the pre-delete content is found again under `.label_backups/<run>/img_2.json`. Getting there produced its own finding -- the first version of that fixture hung the run for 45s until a `faulthandler` dump showed `load_file` taking its **error dialog** path, because the JSON had no `version` key (`label_file.load` warns "of unknown version" and `error_message` opens a modal, which is right for a user and fatal offscreen). The fixture is complete now; the smoke still cannot answer modals, which is why an unexpected dialog is named rather than hung on. Suite 1502 passed / 1 skipped, smoke 14/14, acceptance 17/17, flake8 baseline clean.

- **Two more range editors snapshot, and an AST invariant now covers the whole class.** The scan that built the invariant (`tests/test_utils/test_label_writer_invariant.py`: any function containing `json.dump(` plus a label-path name plus `open(..., "w")` must *call* `snapshot_before_label_write`) turned up four writers the five previous batches had still missed. Two are real user actions over a range of frames: `LabelModifyDialog.modify_group_id` (批量改 group id, which also *deletes* group assignments) and `ShapeModifyDialog.remove_selected_shapes_in_range` (removes the selected shapes from every frame in a range -- destruction across N files, no undo), plus its sibling `add_selected_shapes_to_range` and the `upload_yolo_annotation` merge that is exempt with a reason. The editors' own `modify_label` had been fixed two batches ago; its neighbours had not. Two failures of my own tooling are recorded here because they are the reason the checks are shaped as they are: the first version of the invariant asked whether the helper's *name* appeared in the function body, and a mutation test (delete one call, expect a failure) passed -- the **import statement** matched, so the check was vacuous; it now walks the AST for a real `Call`. And the first version of the editor patch put the local import inside the two methods' **docstrings** (the file's docstrings open with a bare `"""` line, which the insertion code took for the closing one), leaving `F821 undefined name` that no test caught -- 1502 tests, 14 smoke steps and 17 acceptance steps all passed on the broken tree, because none of them drives those two dialogs; the flake8 baseline gate is what stopped it. Both are now covered: the invariant proves the call exists, and the gate proves the name resolves. Suite 1502 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **The other three bulk label writers snapshot too: 漏标扫描, 智能模板预标注 and 类别改名.** Same rule, same helper, three more doors. `_write_missing` appends accepted predictions to each label file, `_write_prelabels` writes propagated template shapes, and `rename_label_across_folder` rewrites **every** JSON that mentions a class when a name changes in the label manager -- the last of these is the one a user can get catastrophically wrong (rename `scratch` to `scratches` across 800 files), and none of them could be undone. They now take the same `snapshot_before_label_write()` copy the editor uses, into the same `.label_backups/<run>/` that 从备份恢复标注 reads. `utils/upload.py`'s merge-after-import was left alone on purpose: the converter already snapshotted that file's pre-import state in the same run, and a second copy of import output is noise. What the tests earned on the way: the first version of this patch raised `NameError` at runtime, because the helper had been imported *inside another function* in the same module -- nothing but a real call would ever have shown that, and three of the four new tests are exactly that call. Suite 1499 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **`运行全部` no longer rewrites a folder's annotations with nothing to restore.** The batch auto-label path (`save_auto_labeling_result`) writes each image's label JSON itself, and with 「保留已有标注」 off the model's shapes **replace** whatever a person drew -- across every image in the run, in one action. The single-image save has snapshotted into `.label_backups/` for a while (`file_lifecycle`), and the empty-prediction guard already stops a no-result run from clearing ground truth, but a *wrong* prediction set replaced hundreds of files with no undo and no trace. Both batch writers now call `snapshot_before_label_write()` before the write -- the same helper, the same runs directory, so 智能工具 → 从备份恢复标注 finds them -- which is a no-op for a file that does not exist yet and copies each file once per session, meaning a whole batch lands in **one** run directory: the undo point is the batch, not each image. `save_classification_predictions` is covered by the same rule (it rewrites the file to add `predictions`). What did not change: the shapes themselves, the YOLO sidecar, the negative-sample marker, and 「保留已有标注」's meaning. 5 first-of-their-kind tests on this path (`tests/test_utils/test_batch_snapshots.py`): replace-mode leaves the pre-run `凹坑` box and `checked: true` in the snapshot, append-mode snapshots too, a first-ever write creates no backup, two images of one run share one backup directory, and a classifier's suggestion lands in `predictions` without touching `shapes`. Suite 1496 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **Importing over an annotated folder no longer erases what was there.** All five `*_to_custom` conversions (`yolo_to_custom`, `yolo_obb_to_custom`, `yolo_pose_to_custom`, `voc_to_custom`, `coco_to_custom`) wrote each per-image label file through `LabelConverter.save_json` -- a bare `open(path, "w")` -- and those files land **in the image folder**, which is where a project's real annotations live. So 导入 → 目标检测/分割/OBB/Pose/VOC/COCO over a folder someone had already annotated truncated every colliding label JSON with nothing to restore, and `jllabelingandtrain convert` did the same to whatever `--output-dir` pointed at. The GUI's bulk editors and the shape converter had already been given this protection; the import path was the last one writing labels without it. They now go through `save_label_json()`, which takes the same `snapshot_before_label_write()` copy the editor uses -- into the same `.label_backups/<run>/` that 智能工具 → 从备份恢复标注 reads -- and then writes; a snapshot that cannot be taken logs and lets the import proceed, because losing the backup is bad and refusing the user's import is worse. `custom_to_coco` deliberately keeps the plain writer: an aggregate export the user chose a path for is an artifact, not annotation state, and snapshotting it would bury the label snapshots in noise. 4 tests: re-importing over a hand-annotated file leaves the previous version recoverable (the old `凹坑` box and its `checked: true` found again under `.label_backups/`), a failing copy still lets the import land, the plain writer creates no backup, and an AST case fails if any `*_to_custom` grows a `save_json` call again -- the same shape as the "new branch forgot the safety" bug this was. Suite 1491 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **The stale-box cleanup no longer has a "delete with no undo" mode.** `apply_stale_deletions(refs, model, label_dir=None)` backed up batch-wide through `backup_label_files()` **only when the caller passed a label dir** -- and with no dir it fell straight through to `save_json(data, label_file)`, rewriting every selected label file with nothing to restore. The one UI caller (智能工具 → 旧轮模型框盘点) does pass `label_dir`, so this was not a live data-loss bug today; it was a default argument that silently meant "skip the safety", and the function's own older tests called it that way and asserted the deletion succeeded -- i.e. the suite was blessing the unprotected mode. Now the fallback snapshots each pending file through `snapshot_before_label_write()`, the helper the editor and the shape converter already use, which derives the folder from the file itself, and **refuses the whole batch when a snapshot cannot be taken** (the same rule the batch path already followed: a failed backup means nothing is deleted). Two tests replace the blessing: without a `label_dir` the run still leaves a snapshot holding the pre-deletion `["cat","dog"]`, and with `shutil.copy2` failing it reports `backup_failed`, deletes nothing, and leaves the file untouched. Found by an AST sweep for `except` blocks that neither log nor raise (143 in `views/labeling`, nearly all deliberate best-effort UI) followed by the more useful question -- which write paths can reach disk without a snapshot? Two candidates surfaced; `project_bundle.py`'s swallowing is documented and correct (a damaged record reads as "no record", a bad zip is refused before any dialog), so this is the only one that needed changing. Suite 1487 passed / 1 skipped, smoke 14/14, black and the flake8 baseline clean.

- **The numbers the docs quote about this build are now arithmetic, not prose -- and the first one checked was wrong.** `docs/{zh_cn,en}/model_zoo.md` opened with 「本构建为 YOLO-only / This build is YOLO-only」, on the one page whose job is answering "which models can I load" -- and the two models this build actually ships are **SAM2**, so the banner talked readers out of the feature they had while pointing at ~90 they do not. Both banners now state the real shape (8 loadable types: the YOLO family plus SAM2; 2 built-in configs; everything else registered as custom), and `tests/test_utils/test_docs_match_code.py` reads those numbers from the code -- `len(_CUSTOM_MODELS)` and the entry count of `configs/models.yaml` -- instead of trusting a sentence: the READMEs and both zoo pages must quote them (digits or the spelled-out word), a case asserts the code side is non-degenerate so a `0` cannot make every claim pass, and a case forbids "YOLO-only" on the model-selection surfaces while leaving the shorthand alone where it is not misleading (`FORK_POLICY.md`, the archived task-panel banners). Verified by editing README's `8` to `9` -- `README.md no longer says 8 loadable model types` -- then restoring it. Related cleanup in the same family: the same pages' 235+235 relative links were re-pointed upstream in the previous batch, so a link on those pages now resolves somewhere real in every case.

- **478 documentation links pointed at files this build deleted, and a new gate keeps them from coming back.** `docs/{zh_cn,en}/model_zoo.md` each carried 235 relative links into `anylabeling/configs/auto_labeling/*.yaml` and `services/auto_labeling/*.py` -- the ~90-model upstream zoo whose config files this fork never shipped or removed, so every one of them resolved to nothing in the repository. `custom_model.md` had 4 more. The pages are about upstream and stay (both keep their 归档/上游 banner, now asserted), so the links were re-pointed where they belong: `https://github.com/CVHub520/X-AnyLabeling/blob/main/...`, which is a real target for a reader who wants those models. The one claim that could not be re-pointed away was `custom_model.md`'s "an adapter may use PyTorch / OpenVINO / TensorRT, see the SAM 2 video tracking example" -- this build has `dnn` and `trt` for YOLO and **no** video tracking, so the sentence now says both, instead of describing upstream's capability set as if it were ours. `tests/test_utils/test_docs_links.py` is the guard: every relative link in `docs/**/*.md` and both READMEs must resolve, one parametrized case per file (25 files), with a case that fails if the file list ever goes empty and one that requires the archived pages to keep saying they are upstream. Verified by breaking a link on purpose -- `docs\zh_cn\faq.md: 1 broken relative link(s)` -- then restoring it.

- **The quick-start page advertised seven advanced features and this build has two of them.** `docs/zh_cn/get_started.md` (and its English twin) opened with upstream's 「高级功能说明」 list -- remote inference service, SAM2/SAM3 video tracking, UPN candidate boxes, interactive detection with **text prompts**, YOLOE / SAM 3 / LocateAnything, Ultralytics training, Rex-Omni. Checked one by one against what this build can actually load: `configs/models.yaml` registers exactly two models (both `segment_anything_2`), `_CUSTOM_MODELS` has eight types and none of them is a grounding, video, UPN or vision-language model, and `grep` for `yoloe` / `sam3` / `locateanything` / `rex_omni` / `upn` / `vqa` across `anylabeling/` returns nothing. So the list promised a text-prompt path in the paragraph where this fork's own README says the build is trimmed -- and the text-prompt code was in fact unreachable *and* broken (see the pruning entries above). The list is now what this build ships, item by item with links that resolve inside this repository (`custom_model.md` / `user_guide.md` / `cli.md` / `fork_features.md`, all verified present), plus an explicit 「上游有、本分支没有」 paragraph naming the four feature families to go upstream for. `README.md`'s 分支范围 section already told the truth; the inconsistency was only in the page a new user reads first.

- **The auto-labeling panel's status slot said `Ready!` in English, and nothing could notice.** `auto_labeling.ui` gives `model_status_label` the design-time text `Ready!`, which is what the panel shows until a model reports a status -- in a Chinese-only interface. It is invisible to both guards the repo has: `pylupdate6` scans .py files, so no .ui string ever enters `zh_CN.ts` (the catalog holds zero entries for "Ready!"), and `tests/test_utils/test_english_ui.py` parses Python sources, so a .ui default is outside its reach. The only thing that could see it was a screenshot, which is how it surfaced while 类别筛选 was being verified on a real window. The default now reads 未选择模型 -- true, where `Ready!` was a claim about a model that had not been loaded -- and acceptance step 16 walks the panel's visible widgets so the class of defect cannot come back silently. The inherited `auto_labeling_ui.py` (the pyuic output, git-ignored and unused: the panel loads the .ui through `uic.loadUi`) still carries the old string and is not what renders.

- **The shape converter can no longer rewrite a folder's annotations with no way back.** Its loop replaced every label file in place -- under a confirm dialog whose own text says 「当前标注将被修改」 -- while the save path (`file_lifecycle`) and the bulk label editor (`label_dialog`) both snapshot first into the same `.label_backups/` run that 智能工具 → 从备份恢复标注 reads. One snapshot call in the loop makes a conversion the user did not mean recoverable instead of final. The legacy `utils/shape.shape_conversion()` had the same hole *and* no caller at all (only a `utils/__init__` re-export; the live route is 工具 → 形状转换器 → `ShapeConverterDialog`), so it was deleted rather than patched twice: two implementations of one destructive loop is how they drift apart, and its removal also cleared two stale F405 lint entries (baseline 224 → 222). `tests/test_labeling/test_shape_converter_dialog.py` covers the dialog, which had never been executed by any test: 9 tests over target options tracking `CONVERSION_TARGETS`, the progress denominator's fallback chain (label files → image list → one open file → nothing) and its no-divide-by-zero path, `3/12 (25%)` formatting with the value clamped to the bar, cancel meaning *stop* rather than *quit* mid-run, the cancel button staying enabled while source/target/confirm go dark, an unmapped pair and an empty folder touching nothing, the real conversion (two rectangles → 4-point rotations, the open image repainted once, the pre-conversion bytes found again under `.label_backups/*/a.json`), and declining the confirm writing nothing and leaving no snapshot.

- **`convert --task coco2xlabel --mode segment` no longer throws away every RLE-encoded object.** The branch that reads COCO segmentations said `# TODO: Handle RLE format segmentation` followed by `continue` -- and RLE is how the *standard* COCO distribution files store masks (COCO's own `annotations.json` uses polygon lists, which is why the repo's sample imported fine and hid the bug). Any such object disappeared from the import with no output at all: the run reported success and produced label files with missing shapes. `_rle_run_counts()` decodes both encodings (the compressed string is 5-bit LEB128 with the sign folded into the low bit; the uncompressed `counts` list is the same runs), `_rle_to_mask()` rebuilds the column-major mask and refuses anything whose runs do not add up to `h*w`, and `_rle_to_polygons()` traces outlines through the `cv2` the app already depends on, keeping each outline ≥3 points. An encoding that cannot be read is now *named in the log* -- image id, and that the object was not imported -- because "silently fewer shapes" is the failure mode this whole fork keeps eliminating. 6 tests: run-count round trip in both forms, decoded mask equals the source, five malformed inputs returning `None` instead of raising, the end-to-end import through `coco_to_custom` asserting the polygon lands where the rectangle was (±1.5 px, since contours trace pixel edges), a mixed file where the unreadable annotation is reported and the readable one still imports, and polygon-list input still working.

- **A photo whose embedded ICC profile is broken now says so, instead of just showing the wrong colors.** `file_lifecycle.py` carried the note `# TODO(jack): icc profile issue warning` over the two Qt messages `fromIccProfile: failed minimal tag size sanity` and `invalid tag offset alignment` -- and `app.py` sets `QT_LOGGING_RULES` with `qt.gui.icc=false`, so even those were muted: the annotator got a picture whose colors are mis-rendered and no trace anywhere of why. Colors are a labeling input (a rust-colored defect on a card that displays gray is a shape the annotator may never draw), so `icc_profile_issue()` now reads the profile that is actually embedded -- JPEG APP2 `ICC_PROFILE` chunks reassembled in sequence order, PNG `iCCP` inflated -- and checks the header length, the `acsp` signature at offset 36, the declared size against the bytes present, and each tag table entry's offset and size. `note_icc_profile()` reports it: a status line naming the defect once per file per session, and a log entry every time. Detection is advisory only -- nothing about decoding changes, and a profile this walker cannot read (HEIC, a truncated JPEG, an `iCCP` whose zlib stream is broken in a way PIL would have shrugged at) reads as *no issue* rather than as a warning, because a false alarm about colors is its own kind of wrong. 16 tests build profiles byte by byte: the valid one, the four distinct breakages Qt complains about, multi-chunk JPEGs including out-of-order chunks and a missing chunk, PNG with and without `iCCP`, garbage input never raising, and the reporting rules (clean file silent, one line per file per session, a different file gets its own line, two spellings of one path do not). Catalog 1603 -> 1604 entries; suite 1390 passed, 1 skipped; smoke 14/14.

- **A class filter on a model that spells its classes as a map used to switch the model off.** `YOLO.set_auto_labeling_filter_classes` built its index list with `enumerate(self.classes)`, which is right for the name lists most models carry and wrong for the `{id: name}` map the YOLOv8+SAM2 combo keeps (its own `predict_shapes` reads `self.classes[int(class_id)]`, and it re-assigns that raw config value *after* `super().__init__()` normalized one copy away). Enumerating a map yields ids, so no selected name ever matched and the result was an empty index list -- and the mask built from `classes=[]` in NMS suppresses *every* class. The symptom was "auto labeling suddenly finds nothing", with the panel looking perfectly configured, because it had flattened the same map to names for display. The setter takes the names out of whichever shape `classes` is in now, exactly as the panel does, so the two agree by construction. 5 tests call the production function itself (name lists subset / all / none, map matched on names, map with everything selected) plus one that drives the whole path through the panel with a map-shaped model delegating to the real setter. Only the map cases fail before the fix -- and they fail as `[] != [1]`, which is the whole shape of the bug. This became reachable the moment the filter got an entry, and was invisible while the setter had no caller.
- **The reusable 切换项目 entry was missing its ellipsis.** The project menu reuses the File menu's `open_project` action rather than building a second one — so the shortcut, the settings-page binding and the F1 row all keep pointing at the same object — but that action's source string is English (`Switch Project`) and the catalog's Chinese has no ellipsis, while both of its neighbours in the same menu carry one (they open a dialog, which is what the ellipsis is for). The menu sets the text when it adopts the action, so both places agree; the F1 sheet still lists it without the ellipsis, where it names a key rather than an action. Found by the machine check, which prints the menu's actual labels.
- **A project record was written into the opened folder's *parent*.** `import_image_folder` derived the dataset folder with `dataset_dir_for(filename=dirpath)`, and that helper takes an *image* path (it returns the file's `dirname`) — handing it a folder returned one level up. Two quiet consequences. Every dataset in one directory shared a single `.jllabel/project.json`, so opening `/data/plates` and then `/data/screws` gave the second the first's label list, output directory and — since the resume batch — its remembered image; and the record landed *beside* the datasets rather than inside them, so "the project travels with the data" held only for a whole tree. Both call sites pass the folder itself now. Found by the smoke script's new project steps, not by the unit tests: those exercise `dataset_dir_for` with the arguments it documents, which is exactly what the call site got wrong.
- **The training window read its project from "where the first image is".** `_dataset_dir_for` derived the dataset folder from `image_list[0]`, and `scan_all_images` recurses — so opening a folder that contains annotated sub-folders had the tuning read from (and written to) whichever sub-folder sorted first. The widget's own project context wins now that the dialog has a real widget for a parent, and the image list is only the fallback.
- **The canvas hint bar showed raw markup, and kept describing the previous state.** Two display bugs in the same bar under the menu. `_format_instruction_shortcut` wrapped every key in `<b>` for per-key emphasis, then `keycap_html` — whose contract is plain keys, and which escapes its input — wrapped that in an accent span; the escape turned the markup into `&lt;b&gt;`, so the rich-text label faithfully rendered the literal text `<b>Ctrl</b>+<b>U</b> 打开文件夹…` and none of the bar's styling survived (an unbound shortcut also read `<b>-</b>` instead of `-`). Styling now has one owner: the helper returns plain shortcut text and `keycap_html` escapes and styles it. The bar was also rendered once at construction and refreshed only by unrelated triggers (a canvas scroll-range change, a mode switch, the auto-labeling panel toggling) — never when a file was loaded — so it kept the boot-time "尚未打开图片" line while `t1.png [2/2]` was open, and only corrected itself on the next zoom or pan. `load_file` now refreshes it once the file is in place, and `reset_state` refreshes it when the state is cleared, so the bar tracks "no image / open image / drawing / brush / auto-labeling" as intended. `tests/test_labeling/test_instruction_bar.py` pins both: no literal markup in any state's text, keycaps present, the state-specific hints appearing, and the two refresh calls staying wired — the widget-contract test caught the new `file_lifecycle` → widget member, and the contract was declared (124 → 125) rather than the call being dropped.
- **A resumed run's length was reported one epoch too long.** Ultralytics writes the interrupted epoch's row a *second* time when a run picks up from its checkpoint, so a finished 50-epoch run left 51 rows in `results.csv` — and `parse_training_metrics` returned the row count as the epoch count. That number goes into `run_meta.json` and is the epochs value the experiment history shows, which is precisely the field two rounds are compared on: the interrupted-and-resumed round looked one epoch longer than it was. `estimate_remaining_seconds` had already been written around this quirk (its docstring says a resumed run can repeat a row, and it reads the epoch column); the sibling parser in the same file had not. It reads the `epoch` column now, falling back to the row count when that column is absent or unparseable. **Found by running a real training on this machine** (24 synthetic images, CPU, stopped at epoch 6, resumed to 50: 51 rows, epoch column ending at 50) — no unit test caught it, because every fixture wrote clean, gap-free CSVs. Two regression tests pin both branches, and the round trip that found it — dataset build, worker protocol, stop, resume into the same directory, no `exp-2`, optimizer stripped on completion — is written up with numbers in `reviews/measurements_2026-09-30.md`.
- **A label file that cannot be read is no longer trained as an empty image.** The dataset build filed every failure into one bucket: an image with no label file (a deliberate negative sample) and an image whose label file exists but cannot be parsed both became "background", so a fully annotated frame taught the model that there is nothing in it — and nothing anywhere said so. The two are separate groups now: unreadable files are *left out of the dataset* and counted, and the run does not start until the person training has seen the list (`Dataset Incomplete`, default button is the one that does not train). The export path has treated an unreadable label file as a blocking loss since the pre-export check landed; the training path consumed the same data with the opposite judgement. What the build could not use is written to three places so the answer survives the dialog: the `manifest.json` gains a `skipped` block, `dataset_info.txt` gains the counts and every offending path, and `create_yolo_dataset(..., report=...)` hands the same numbers to the caller. Unchecked-file skips are counted too — `only_checked_files` used to drop images with no record at all, so the flag's effect on a run was unmeasurable. `General.partition_images` is the extraction this needed (the split used to live inline in a 42-complexity function; it is 37 with the same behaviour plus the report, and the grouping is now testable without building a dataset).
- **One bad label file no longer takes the whole dataset build down.** A label that is valid JSON but lacks `imageWidth` (exactly what some converters emit) raised a `KeyError` out of `custom_to_yolo`, up through `create_yolo_dataset`, and out as `Failed to prepare dataset: 'imageWidth'` — one file, no dataset, no training, and no hint that the other 3000 images were fine. The per-file conversion is guarded now: the offending image is dropped with its reason recorded, and the build continues. The half-written pair is deleted with it, because an empty or truncated `.txt` left in `labels/train` reads as "this image has no objects" to ultralytics — the same wrong answer the reclassification above exists to prevent.
- **The overwrite confirmation deleted whatever `Project` and `Name` added up to.** Two free-text boxes are joined into the directory a "Retrain (overwrite)" then removes with `shutil.rmtree`, and `os.path.join` *discards* the first part when the second is absolute: with `Name` set to `D:/labels`, the dialog announced it was deleting the run directory and deleted the annotation folder instead. Verified in an isolated sandbox: `Name = ".."` listed a directory that looked harmless (`['detect']`) and then removed every sibling run's weights along with `runs/` itself. Three guards, each of which alone would have stopped it: `Name` is one directory component now (validated in `validate_basic_config`, and the field carries a `QRegularExpressionValidator` so a pasted path cannot even be typed), the target has to resolve *inside* the `Project` folder (`is_inside_directory`), and it has to look like a run this tool wrote (`looks_like_training_run`: `weights/`, `args.yaml` or `results.csv`). A directory that fails either of the last two cancels with an explanation instead of offering a click that cannot be undone — the rule `utils/output_dir.py` already follows for the images being annotated. 18 new tests in `tests/test_auto_training/test_training_safety_guards.py`, three of which drive the real dialog to prove the guard is wired in front of the run rather than sitting unused next to it.
- **The `classes` filter is checked before the run, not after the mAP.** `validate_classes` was written to catch exactly the mistake this field invites — every index past the last class means ultralytics trains on nothing, and the resulting mAP describes the filter rather than the data — and it had **no caller**. It is wired into `start_training_from_train_tab`, where both entry points land (the Config tab commits first and calls it; the Train tab calls it directly), so an out-of-range filter is refused with the valid range before any dataset is built. The names come from the data config, falling back to what the label panel already knows: reading every label file here would put a folder scan in front of the Start button. The function accepts the parsed list too, not only the raw string, since that is the form the dialog holds by the time a run is committed.
- **A stopped run appears in the history, labelled as stopped.** `run_meta.json` was written only when a run *completed*, so an interrupted run — which has a `results.csv`, a resumable `last.pt` and arguments worth keeping — was counted as "unrecorded" and could not be compared with the finished run it is usually compared against. The record carries `status` now (`completed` / `stopped`, blank for records written before the field existed), the experiment table gained a 状态 column, and the fixed-column-count guard moved with it (`COLUMNS` 15 → 16, checked against the row formatter so a new field cannot silently lose its column).
- **用于自动标注 no longer hands back the model from before the last resume.** The button reuses `weights/best.onnx` when the file exists, without comparing dates: resume a run, train a few more epochs, click it, and the ONNX that gets loaded was exported from the *earlier* `best.pt` — a finished-looking run paired with a model that is not the one on screen. The export is regenerated whenever it is older than the weights it came from, with a line in the log saying why (`is_fresh_export`).
- **Exporting no longer runs pip because a dialog was clicked.** The export worker installed missing packages into the user's environment on its own, unprompted, with a 30s timeout that no real wheel download fits in — so the "automatic" path could only fail slowly, after making the person wait. Installing is opt-in now: the dialog (which owns the UI, and is the only place a modal box can be shown) lists the packages, offers to install them, and cancels the export on No with the exact `pip install` command. Consent is threaded through as `allow_install`, defaulting to off, so a caller that does not ask cannot mutate the environment. The install timeout is 300s, and a PyInstaller build — where `sys.executable` is the app itself, so `-m pip` would relaunch it — reports what to install instead of trying.
- **The dataset cleanup prompt names the directories.** It said "5 old directories, 412 MB" and nothing else; it lists them now (capped, with a "... and N more" tail) before asking to delete them.
- **A stopped run can be continued again, and the `Resume` checkbox is reachable at last.** Resuming was impossible from the UI: the only way out of the existing-directory branch either deleted the directory (`shutil.rmtree`, taking `weights/last.pt` with it) or returned, so the `Resume` option in **Checkpoint and Validation** could never survive the trip. The branch is one dialog now with three ways out — *Resume Training* (offered only when `last.pt` really is resumable: it carries epoch and optimizer state and the run still has epochs left; a completed run is stripped and correctly not offered), *Use Existing Model* (the old "export the existing model" path) and *Retrain (overwrite)*, which keeps the destructive confirmation that spells out what would be lost. A resumed run launches with `model=last.pt, resume=True` and the freshly rebuilt dataset yaml: ultralytics restores project/epochs/hyperparameters from the checkpoint, keeps the device override, and writes back into the same run directory — verified end to end by interrupting a real run and resuming it (same `exp/`, `results.csv` continues, no `exp-2`). Since a stop is where this is reached from, the Train tab grows a `Resume Training` button that appears only while a `weights/last.pt` exists (the click validates it).
- **The export asks before it drops shapes, instead of reporting it afterwards.** A run that drops shapes still says so in the end — but by then the files are written, and two of the ways it drops them cannot be walked back by reading a popup: a shape whose label is outside the exported class list disappears file after file without an error, and an unreadable label file raises out of the run and leaves a half-written directory. Both are visible before the first byte is written, so `utils/export_check.py` reads the label files the run is about to read (one pass, in the same order, through the same mapping) and the export interrupts with the specific entries listed before it resolves the output directory — placing it there is deliberate: answering Cancel must not leave a directory behind. The default button is Cancel. Nothing else blocks: an image with no label file and an empty label file are legitimate negative samples and only get counted, since a dialog that fires on those would train the annotator to click through it. Three tests pin the wiring, not just the functions: the check must run on the *filtered* list, must run before the output directory is touched, and the manifest must be written and named in the summary.
- **The tenth digit key works, and the keys answer before the first box is drawn.** `auto_assign_digit_shortcuts` scanned `range(1, 10)`, so slot `0` — a real key (`digit_shortcut_0`) that `user_guide` documents as part of "0-9" — stayed dead unless mapped by hand; it is the tenth slot now. And assignment only ran once a *shape* existed, so a brand new project answered nothing when the very first box was drawn with the digit keys, which is exactly the step those keys exist to remove: opening a folder now hands the project's declared labels their slots in order (`assign_label_digits`, called from `import_image_folder` after the project restores its own labels). Labels already mapped keep their key, a full set of slots is left alone, `digit_shortcuts: null` still disables the whole feature, and past ten labels the label dialog's completer remains the keyboard path. Sixteen tests, plus a smoke assertion on a real widget that opens a folder declaring two labels. The contract test earned its keep on the way: `file_lifecycle` now reaches `widget.digit_shortcut_controller`, which had to be declared in `CONTRACT_MEMBERS` (123 → 124) before the suite would go green.
- **Undo now survives leaving the image.** `canvas.reset_state()` emptied both stacks on every file switch, with a comment stating it as if it were a design — so a wrong edit noticed after moving on had no Ctrl+Z and no way back. The stacks live in a per-image store now (`widgets/shape_history.py`): `load_file` points the canvas at the image being opened and banks the previous image's stack instead of dropping it, for up to `MAX_BUCKETS` (20) images, least-recently-used. The old attribute names (`shapes_backups` / `shapes_redo_backups`) stay reachable through properties, because the label editor, the rotation mixin and the widget's undo/redo reload path all read, mutate *and* assign them. Two details carry the behaviour: the banked top is dropped on restore, since `load_shapes()` is about to push that same on-disk state back — otherwise the first Ctrl+Z would restore what is already on screen and read as "undo is broken"; and the canvas got **smaller**, 3772 → 3760, because the plumbing moved out rather than in.
- **The menu entry is re-read after a load.** The smoke script caught this, the unit tests could not: the history came back correctly while `Ctrl+Z` stayed greyed out, which is a restored feature nobody can reach. `load_file` now refreshes both actions from the canvas (behind a `getattr`, since light test stubs carry no `actions`), and smoke step 2b asserts the stack *and* the enabled state across a switch away and back.
- **The editor keeps a snapshot of every label file it overwrites, so an edit stops being final the moment you leave the image.** The canvas undo stack does not survive a file switch — `canvas.py` says so outright — and the auto-save overwrites the only remaining copy on disk 400ms after an edit. "I broke this ten images ago" therefore had no answer at all: neither Ctrl+Z nor any file remembered the earlier state. `utils/session_snapshot.py` copies a label file into a run the batch tools' backup namespace already owns, once per (session, label file), immediately before the first write of that session — the granularity that answers "an hour ago" without writing hundreds of copies per image. It lands in the existing 从备份恢复标注 picker marked 自动快照: recovery needed no new UI, and it shows up even though the annotator never asked for a snapshot, which is the point. Run naming and retention are unchanged (`BACKUP_KEEP_RUNS`), the marker file is a `.txt` so it cannot inflate the picker's label count, and the disk cost is bounded by the label files rather than the images: only the current image reaches this path (auto-save, Ctrl+S, review toggle) — the bulk review writer only repaints list rows. Eleven tests pin the parts that carry the value: a later edit never replaces the baseline, runs are per label directory, a first save has nothing to keep, a failed copy is logged but never blocks the save, and — asserted against the real `save_labels` — the snapshot is taken **before** the write.
- **The crop export no longer deletes a directory one click after you name it.** Four call sites each carried their own copy of the "output directory already exists" dialog, and the copies disagreed: the YOLO export had been hardened to Merge / Clear / Cancel while VOC, COCO and `utils/crop.py` kept the older shape — Overwrite / Cancel, straight into `shutil.rmtree(save_path)`, with no path in the dialog, no listing of what would go, and a merge option only for VOC's misleading "Yes". The crop one is reachable from the Tool menu, and `shutil.rmtree` does not use the recycle bin, so that click was irreversible. Reading any single file could not have shown this; only comparing the four could. They are one implementation now, `utils/output_dir.py`: `export.py` loses 85 lines and `crop.py` 16.
- **A target that holds (or is) the folder being annotated can never be cleared.** The dialog does not offer Clear at all in that case, and even a caller that insists gets Cancel — deleting the images is the one mistake no second confirmation fixes. This is the rule the four copies could not state, because none of them knew what was being annotated.
- Merge is the default button everywhere, and Clear always asks a second time with the absolute path spelled out. `tests/test_utils/test_output_dir.py` (14 tests) drives the two-step flow through a stand-in QMessageBox, and carries the ratchet: if any module under `utils/` deletes `save_path` on its own again, or a caller wires the shared dialog without declaring what must survive, the suite fails.
- **Classification never worked, and said only "Error in model prediction".** `YOLOv8Cls` inherits `Model`, not `YoloBaseModel`, so it never got the `qt_img_to_rgb_cv_img` step every other adapter performs: `predict_shapes` handed the caller's `QImage` straight to `cv2.cvtColor`, which raised on every run. The class list, the top-k and the confidence floor were all correct — the entry point simply never survived its first line. `preprocess` also converted BGR→RGB a *second* time, which would have swapped red and blue had the call ever got that far; the conversion happens once now, in `predict_shapes`, mirroring `__base__/yolo.py:377`. `tests/test_auto_labeling/test_classifier_loopback.py` feeds the QImage a real caller hands over (its fixtures used to pass a BGR array, which is exactly how the mismatch stayed invisible) and `tests/test_auto_labeling/test_service_regressions.py` pins the channel order.
- **One model that refused to unload locked the model switcher for the rest of the session.** `GenericWorker.run` emitted `finished` only after a clean return, and callers clear their "an operation is running" flag from that signal — so a payload that raised left `is_model_download_running()` true forever: no model could be loaded again, and nothing said why. `run` is `try/finally` now (the failure is logged), and `model_manager._load_model` no longer lets a failing `unload()` take the next model down with it. Smaller bug in the same area: `YOLOv8SegmentAnything2.unload` called `self.pre_inference_thread.quit` without parentheses, so the preload thread was never asked to stop and `self.model` — the SAM2 encoder/decoder sessions, which live there and not on `net` — was never released. All three are pinned in `tests/test_auto_labeling/test_service_regressions.py`.
- **The Chinese interface fell back to English in every export, upload and crop dialog — 181 times.** `pylupdate6` derives a context from the receiver of `tr()`, and these strings sit in *module-level* functions (`def export_yolo_annotation(self, mode)`, called as `utils.export_yolo_annotation(widget, …)`): no class to belong to, so each string was dropped from the catalogue before anyone could translate it. `utils/output_dir.py` had already been fixed this way; the other 181 calls had not. They are explicit `QCoreApplication.translate("LabelingWidget", …)` now. The same bug had a second form in `widgets/canvas_rotation.py`, where a `self.tr` inside `CanvasRotationMixin` is looked up at runtime as the derived class (`Canvas`) and can never match the `CanvasRotationMixin` entry the extractor produces. Counted with an AST walk (module-level function → `self.tr`), never by grep: 62 in `export.py`, 52 in `upload.py`, 35 in `visualization.py`, 15 in `crop.py`, 9 in `batch.py`, 8 in `shape.py`. Fixing this exposed a third defect: `scripts/generate_languages.py` could not run at all at the current size — 175 sources joined into one `shell=True` command exceed cmd.exe's 8191-character limit (a bare "命令行太长", exit 1) — so the argument list is passed directly now. The catalogue went 1288 → 1430 entries, 0 unfinished.
- **Switching to a folder without `classes.txt` exported the previous folder's class ids.** `_load_classes_from_folder` returned early when the new folder shipped no `classes.txt`, leaving the panel exactly as the previous folder had left it — and `_yolo_class_names` reads that panel to build the YOLO id map, so a stale list silently remapped every exported label. The project-record fallback meant to catch this only fires on an *empty* panel, so it never could. Such folders fall back to `config.labels` now (`project_settings.restore_configured_classes`), which is what the original comment intended; `tests/test_labeling/test_folder_classes.py` and `tests/test_labeling/test_class_panel_across_folders.py` pin the fallback and the clear.
- **The lint gate switched itself off if you deleted the baseline.** `check_flake8_baseline.py` returned an empty `Counter` for a missing file and then exited 0, so removing `scripts/flake8_baseline.txt` turned the pre-commit hook and the CI lint job into no-ops. A missing baseline is a failure now; recreating it stays an explicit `--update`.
- **The training progress bar counted one epoch too many after a resume.** `update_training_progress` counted rows in `results.csv` — the quirk `parse_training_metrics` had already been changed to avoid, since a resumed run repeats the interrupted epoch's row — so the bar read `51/50` while the metrics label beside it and `run_meta.json` both said 50. It calls the same parser now.
- **Window geometry had two owners.** `app.py` saved `window/geometry` + `window/maximized`; `MainWindow` saved `window/size`, `window/position` and `window/state` — the same `QSettings`, both replayed at startup and both written on close, so whichever ran last won. The split is by responsibility now: `app.py` owns the window's geometry, `MainWindow` owns the dock layout (`window/state`); and the WSL branch, which existed on one side only and therefore left the "no stable geometry to restore" rule half-applied, drops the other side's keys as well.
- **"will free X MB" counted the source images on Linux/macOS.** `general.directory_size` followed symlinks via `os.path.getsize`, while the dataset is built from `os.symlink` entries on those platforms: the number in the dataset-cleanup prompt was the size of the files the links point at, and deleting a link frees nothing. Symlinks count as zero now.

### 🛠 Improvements

- **The `text_prompt` / `existing_shapes` plumbing is gone too (170 lines) -- and it turns out those branches could never have worked.** `1fa4c45a` left the optional keywords in place on purpose; this finishes the band. What the check found while doing it is worth stating: every `predict_shapes` this build can load is declared `(self, image, filename=None)` (`model.py`, `segment_anything_2.py`, `yolov8_sam2.py`, `yolov8_cls.py`, `__base__/yolo.py`), so `model_config["model"].predict_shapes(image, filename, text_prompt=...)` would have raised `TypeError` and landed in the surrounding `except` as 「Error in model prediction: predict_shapes() got an unexpected keyword argument」. The skip-detection path was therefore not only unreachable (empty gate list, hidden button) but **broken underneath** -- a second reason it could never have been a working feature, and a warning about inheriting a plumbing layer whose contract the leaf implementations no longer honor. Out: `TextInputDialog` (112 lines), the batch thread's `text_prompt` parameter and its branch, `self.text_prompt` and its reset entry, `_BATCH_PROCESSING_TEXT_PROMPT_MODELS`, and both keyword paths through `ModelManager.predict_shapes` / `predict_shapes_threading` (the worker now always gets `(image, filename)`). 3 catalog entries followed the dialog out (1588 → 1585). Suite 1452 passed / 1 skipped, smoke 14/14, acceptance 17/17, black clean at 195 files.

- **"Hide other shapes when one is selected" is deleted, not left pretending.** `Canvas.hide_background_shapes()` had no caller in production or in a test -- and it was the only writer of `hide_backround`. So `_hide_backround` stayed False for the life of the canvas, the 14 `set_hiding()` calls scattered through the selection, vertex-drag, rotation-handle and finish-shape paths did nothing, and both paint guards (`shape.selected or not self._hide_backround`) were a visibility test wearing a costume. Reduced by inspection rather than by hope: one flag, one writer, no caller. `canvas.py` gives 34 lines back to its size budget (3414 → 3380, with the reasoning in the note), `canvas_rotation.py` and `mode_controller.py` lose one call each, and the two guards now read `if not self.is_visible(shape)` / `if self.is_visible(shape)`. The canvas ink tests stay as the tripwire in case the reduction is ever wrong. Suite 1452 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **Seven auto-labeling controls that no model in this build could ever show are gone (284 lines, plus 11 catalog entries).** The orphan sweep kept going where the first commit stopped, and this cluster was not dead code but **dead affordance**: `button_skip_detection` (跳过检测), `edit_text` + `button_send` (the text-prompt / visual-language row), `add_pos_rect` / `add_neg_rect` / `button_run_rect` (SAM rectangle prompts) and `input_box_thres` (a caption whose spinbox does not exist anywhere in the tree). The visibility mechanism is `update_visible_widgets()`, which shows exactly the names in a loaded model's `Meta.widgets` -- and the union across every model this build can load (`button_run`, the two threshold pairs, the SAM2 point/rect/clear/finish/AMG set, output mode) contains none of them, while `hide_labeling_widgets()` hides all seven at construction. So each was hidden forever, with its handler, its entry in the enable-during-inference list and its `update_button_colors()` styling running for a widget nobody could reach. The two gate lists were empty too -- `_SKIP_DET_MODELS = []` and `_BATCH_PROCESSING_TEXT_PROMPT_MODELS = []` -- which is what made the *behavior* as well as the button unreachable: `run_prediction()`'s skip branch, `batch.py`'s `existing_shapes` load and the batch `TextInputDialog` branch could not fire for any model. Removed with them: `_extract_shapes_for_recognition()`, `run_vl_prediction()`, the two rect-mode handlers (the only entry points to `REMOVE`+`RECTANGLE`), `load_existing_shapes()`, the `skip_detection` parameter of `BatchProcessingThread`, `_SKIP_DET_MODELS`, the seven `.ui` items, and the "Skip Det" mention in the More-panel docstring that described a folded tool which could not fold or unfold. Kept: the `text_prompt=` / `existing_shapes=` plumbing inside `ModelManager`, because pruning an optional keyword through the worker and every model signature is its own change and nothing calls it now. What the deletion had to be careful about: `batch.py` read `button_skip_detection.isChecked()` on **every** batch run, so removing the widget without that file raises `AttributeError` in the middle of 运行全部 -- the band had to go in one piece. The two tests that named the widgets (`test_layout`'s hidden-control list, `test_batch_skip`'s constructor kwargs) failed exactly where expected and were trimmed; 11 catalog entries went obsolete (1599 → 1588). Suite 1452 passed / 1 skipped, smoke 14/14, acceptance 17/17 -- where step 16's panel scan is the check that the surviving toolbar still lays out.

- **545 lines nothing could ever call are gone, and the catalog lost 6 messages with them.** An orphan sweep (the same shape as the class-filter finding: a complete implementation on one side of a gap nothing crossed) turned up seven dead pieces, each verified by identifier grep *and* by the dynamic paths this repo actually uses -- `getattr(self, name)` string tables, `Meta.widgets` lists, `.ui` promotion, settings dispatch through `_build_*_editor`. Out: `TimeoutContext` (65 lines, imported by `model_manager` and never used), `Args` (an empty namespace class, zero references), `ModelManager.update_model_config` (18 lines -- and its tail called `save_config()` after reading the config without changing anything, so it was dead *and* wrong had it ever run), `AutoLabelingWidget.on_open` / `on_close` (no-op stubs), `ShortcutEditor` + `MultiKeySequenceEditor` (184 lines in `settings/editors.py`; the dialog imports four editors and builds shortcut rows with `ShortcutLineEditor(allow_multiple=...)`), `TrainingConfirmDialog` (82 lines plus its re-export -- the live training path builds `cmd_parts` and logs the command itself, never opening a dialog), and the `description_dock` block in the config template (a dock this build never creates -- only `flag`/`label`/`shape`/`file` docks exist -- carried in the schema's exclusion list, which is precisely how a ghost leaf hides). The catalog guard earned its keep: `test_every_context_is_a_live_class` failed the moment the classes went away, naming the three dead translation contexts, and `lupdate --no-obsolete` dropped them (1605 -> 1599 entries). One correction worth stating plainly: the batch that took 23 English strings out of the Chinese UI included three from `TrainingConfirmDialog` (开始训练 / 准备开始训练 / 即将执行的命令) -- right work on a dialog that turns out to be unreachable, which is why the sweep was worth running. What the same sweep found is *not* in this commit because it needs a decision rather than a cleanup: seven auto-labeling controls no model in this build can ever show (`button_skip_detection`, `edit_text`, `button_send`, `add_pos_rect`, `add_neg_rect`, `button_run_rect`, `input_box_thres`) -- none of them appears in any `Meta.widgets`, and `_SKIP_DET_MODELS` / `_BATCH_PROCESSING_TEXT_PROMPT_MODELS` are empty lists, so the branches that read them cannot fire either.

- **Three inherited markers that described nothing were deleted, each with its reason recorded.** `widgets/label_dialog.py` carried `# TODO(unknown): Calculate optimal position so as not to go out of screen area` while the `move_mode == "auto"` branch 1800 lines below already reads `QApplication.screenAt(cursor)`, clamps the right and bottom edges and moves the dialog -- the work was done and the note was a lie about the code. `shape.py`'s `[opt] Store paths instead of creating new ones at each paint` is a real idea with no measurement behind it, and an unowned `TODO(unknown)` is how such a note lives forever; if path caching is ever worth doing, `tests/test_canvas/test_canvas_overlays.py` is the guard that would make it safe, which is the place to start rather than the comment. `label_widget.py`'s `# XXX: Could be completely declarative.` floated above the `QSettings` restore whose next two lines already explain why it runs before any folder import. What is left in the app is only markers with a live decision attached: the OBB rotation clamp in `canvas.py`, waiting on the product call.

- **The canvas has 346 lines of headroom again.** `widgets/canvas.py` sat at exactly its frozen 3760-line budget, which meant the next canvas feature had to start by moving something out; this does the moving. The overlay band -- `_paint_texts`, `_paint_labels`, `_paint_cross_coordinates`, `_paint_attributes`, 358 lines -- now lives in `widgets/canvas_overlays.py` as `paint_*` functions that read the canvas and draw, the way `canvas_geometry` and `shape_history` already do. `Canvas` keeps the four `_paint_*` methods as one-line delegations, so `_paint_content` and every caller are untouched. The move was proven, not asserted: a fixed scene (label + score + description + attributes, one invisible shape, one `AUTOLABEL_*` marker) rendered through the production `render_visualization` produced a byte-identical SHA-256 before and after. `tests/test_canvas/test_canvas_overlays.py` is what keeps it honest from here -- 7 tests that count *where ink lands* rather than hashing bytes, so a deliberate restyle can still pass while an overlay that silently stopped drawing cannot; the last one paints through a bare namespace holding only the documented read surface, so the day the module needs to *write* canvas state, the test says so. Three `B007` lint findings arrived with the move (the baseline is per-file, so borrowed code counts as new debt) and were fixed by dropping the unused `enumerate` indices rather than re-freezing the baseline. Budget lowered 3760 → 3414 with the note. Suite 1374 passed, 1 skipped; smoke 14/14.

- **Projects come first now: the manager opens at startup by default.** `startup_show_project_manager` shipped as `false`, so the one page that answers "which project am I working on" was reachable only from a menu — and the common launch restored the last session without ever showing it. The factory default is now `true`: every launch starts on the manager, with the last project preselected and the progress column filled, which is one click away from either resuming or switching. The "直接续上上次现场" fast path is not gone — it is what happens when the switch is unticked (the manager's own checkbox, or the rc key), and the pure decision function is unchanged. The existing rc of an installation keeps its own value; the switch is the user's, the default is ours.

- **The machine checklist runs itself now, and photographs what it sees.** The four project batches had only unit tests behind them — 1166 of them, plus 13 offscreen smoke steps — and none of that can see a menu's shape or a dialog's wording. `scripts/accept_project_work.py` opens a **real** `MainWindow` on the real platform plugin, walks the nine items of `reviews/project_work_machine_check_2026-10-10.md` end to end, and writes a screenshot per step to `reviews/acceptance_shots/` (git-ignored: they date the moment a dialog is restyled). Three things make it work where the smoke script could not. It loads the zh_CN catalog the way startup does — without it every string whose source is English renders English, and the one action the project menu reuses showed `Switch Project` in an otherwise Chinese menu. It prints `windowTitle()` at each step, because a window manager draws the title bar *outside* the widget and `grab()` cannot capture it. And it answers modal dialogs instead of waiting for a human: the first run sat for 90 seconds on 「还没有类别」, which is production behaviour that no user-facing test had ever driven. Nothing leaves the scratch directory — QSettings is redirected into it and the work directory is set to it. 9/9 through, and it earned its keep immediately: opening the window at all revealed that the right sidebar's 文件 panel had been rendering 2555 characters of `.ts` markup as its title since 2026-10-08, which 1166 tests and 13 offscreen steps had no way to notice (written up in `reviews/translation_catalog_corruption_2026-10-10.md`).

- **CI is green again, which it had not been for a while — and a red gate announces nothing.** Three platform assumptions in the suite failed on every run for as far back as the history goes, so the `Unit tests (windows-latest)`, `Smoke tests (ubuntu-latest)` and `Smoke tests (macos-latest)` jobs were permanently red. That is worse than it sounds: a gate that is always red cannot report a regression, and the integration smoke added to CI in the same batch would have been swallowed by it. Two tests were asserting Windows behaviour everywhere. `test_path_shaped_names_are_rejected` parametrised `a\b`, and a backslash is a separator *only* on Windows — on POSIX it is an ordinary character in a directory name, one that cannot escape its parent, so `is_single_path_component` accepting it is correct rather than a hole; the case is now its own `skipif(os.sep != "\\")` test with that reasoning written down. And `test_clear_asks_a_second_time_with_the_path` compared the confirmation dialog's path against `os.path.realpath(...)` — equal on this machine, different on a runner whose TEMP sits behind an 8.3 short name (`C:\Users\RUNNER~1\...`); both sides are resolved now, the way `test_provenance.py` already does it for the same reason.
- **The smoke script stopped leaking into the real recent-project list, and learned the project paths.** `<work directory>/.jllabel/projects.json` is where opening a folder records it, and the script set only `current_config_file` — so every run pushed its throwaway temp folders into the *user's* registry (a live one held nine of them, the oldest dated 2026-09-29; the leak predates the project batches). `set_work_directory(tmp)` fixes it. Four new steps then walk the project work end to end: registry entry + name + title bar, the resume round trip (left on this frame, came back to it), closing a project back to an empty canvas, and the task kind travelling both ways to the training window — 13/13. Adding them is what caught the two bugs above: every one of those unit tests passes, because they call the helpers with the arguments the helpers document; only the assembled path shows what the call sites actually pass.
- **An auto-labeling run says what it produced, including "nothing".** `new_shapes_from_auto_labeling` ended in silence either way: when a model detected nothing on an image that was already annotated, the guard that keeps the existing ground truth logged its decision and returned — the canvas did not change, no message appeared, and the only trace was a log line, so the run looked like a hang or a broken model. A run that did produce boxes never said how many. The status bar now carries 自动标注完成：N 个目标 / 本图未检测到目标 / 本图未检测到目标，已保留原有标注 (the last one matching the guard's actual behaviour, so the message and the code tell the same story). `tests/test_labeling/test_auto_labeling_feedback.py` (three tests) drives the real method — including the real apply path for a hit — and pins all three messages.
- **An audit round found four small things, and the fixes reached past the four.** (1) The Labels and Objects section checkboxes are textless styled squares and carried no tooltip at all — a blue box the user has to guess at; they now name what they toggle. (2) The export recap — 导出完成：x/y 张图, skips included — was a three-second toast whose only pointer to the output was the path printed in its text: nothing to click, nothing to copy, and gone before it could be read. The completion toast (YOLO, VOC and COCO, one helper now) carries 打开输出目录 (through the same WSL-aware `platform_open.open_path` the training window uses) and 复制输出路径 (confirmed on the status bar), and a toast with actions waits 15 s instead of vanishing in 3. (3) 标签搜索 had a clear button and 文件搜索 did not, and Qt's built-in ✕ carries no tooltip of its own — both boxes have one now, with a hint. (4) The 智能工具 menu was twelve flat entries (the audit plus items 1..11); it is three submenus now — 检查与诊断 / 复核与建议 / 批量与恢复 — built in `utils/smart_tools_menu.py`, with the numbers kept because the docs and the F1 sheet refer to them. A new ratchet in `test_tooltips.py` walks every text-less button of the built window and fails on one without a tooltip: the audit that found (1) and (3) is now the test that keeps them fixed.
- **Five smaller sidebar and window paper cuts, all in the "you would have to know" family.** (1) The settings gear sat in the same row as the file-search box, where it read as "settings for this list"; it lives in a new sidebar footer now, beside a 收起 text button — which is also the answer to (2): the collapse control used to exist only as a caret on the 14 px strip, so that strip had to stay on screen while the sidebar was open, charging the canvas 14 px for a control nobody used. The strip joins the layout only while collapsed; expanded, the canvas measures 1006 px where it used to get 992. (3) The column had four section headers in three styles — Labels/Objects with the centered title plus checkbox, Files with no header at all, and Flags still wearing Qt's native title bar; Files gained the matching title row and Flags' native bar was swapped for the same header widget. (4) The file list's right-click menu has a 勾选 submenu now — 全部勾选 / 全部取消勾选 / 反选 — applying only to the rows the filter is showing, and a right-click below the rows no longer does nothing; the checkbox is the row's "has labels" marker, item data only with nothing written to disk, so no confirmation step is needed. (5) The window always started maximized — the geometry save was a commented-out line — so a window sized for a second monitor came back filling the primary one; geometry and the maximized flag are saved on quit and replayed on start, and a first run still opens maximized. Tests: four more in `test_sidebar_splitters.py` (strip visibility, footer ownership, both headers), `test_file_list_bulk_check.py` (six, including hidden and uncheckable rows being left alone) and `test_window_placement.py` (three, snapshotting and restoring the machine's real QSettings values so the suite leaves no trace). Widget contract 130 → 132 (`flag_dock`, `settings_button`), and the widget itself shrank to 6805.
- **A dataset folder can be dropped on the window now.** `dragEnterEvent` matched only image extensions, so the most natural gesture — dragging the folder being annotated onto the window — was refused outright (and `dropEvent` filtered folders out a second time), while the first line of the empty-canvas guidance is 打开文件夹. Folders are accepted now and open through the same `import_image_folder` path the Ctrl+U dialog uses — one folder per drop, the first one wins, and the unsaved-work confirmation still runs first; images keep the old drag-in behaviour unchanged. Both handlers moved to `file_lifecycle` (`handle_drag_enter` / `handle_drop`), which took the widget down to 6806. `tests/test_labeling/test_drop_targets.py` (7 tests) pins accept/refuse per drop shape, the folder-wins rule and the dirty-image gate. The empty-canvas steps were a three-step guide that stopped at drawing; a fourth line now names what the loop pays off with (一键训练 → 用于自动标注), pinned by `tests/test_widgets/test_empty_canvas_state.py`.
- **The right sidebar is draggable now, and the states it hides are remembered.** A design pass over the panel produced three fixes. (1) It was a fixed-width column: the canvas could not be widened past it, and the labels / objects / files sections divided whatever height was left by size hint. Two `QSplitter` handles are in charge now — canvas | sidebar for width, and one between the three sections — 6 px wide, highlighted on hover, with the sizes remembered in the config (`sidebar.width` / `sidebar.lists`, one write per drag through a 600 ms debounce) and replayed at startup; the no-memory fallback is capped so the canvas does not pay for the wrapper's wider size hint on a first run. A collapse pins the strip to the edge with the width handle disabled, and the expand comes back to the width that was there. (2) Section visibility had three mechanisms with three memories: the Labels/Objects checkboxes wrote nothing, the settings page's per-dock 显示 switch only applied at startup, and the whole-sidebar collapse remembered. The checkboxes and the settings row now read and write the same `<dock>.show` key, the runtime applier applies 显示 immediately (and points the checkbox at the new state without bouncing the write back), so one state has one memory. (3) The collapse was mouse-only: `toggle_sidebar` joins the shortcut system as a hidden action with a default key (Ctrl+Shift+B), listed in F1 and rebindable in the settings page. The widget's size ratchet stayed at 6817 — the assembly lives in `utils/panel_visibility.py`, which now owns the whole right column. `tests/test_labeling/test_sidebar_splitters.py` (9 tests) pins the handles, the debounced save, the replay, the collapse round trip and the shared visibility key; the template gained `sidebar.width` / `sidebar.lists`, and the shortcut-count anchor moved 118 → 119.
- **The README pair and the training guide were rewritten around what the build actually is.** The root `README.md` / `README_zh-CN.md` had drifted apart — the Chinese page carried a dated update log and contribution/sponsor sections the English one lacked, and both left a reader to guess at the first five minutes. They are mirrors now, with a quick-start walk through the loop (open folder → auto-label → review → train → 用于自动标注 → repeat), features grouped by area (annotation, auto-labeling, review & quality, provenance, smart tools, project management, reproducibility, recovery), the on-disk layout of the work directory, a compact dated "what's new", and the packaging targets incl. `win-cpu-train`. Facts were checked against the tree rather than carried over: the shortcut keys come from `jllabeling_config.yaml` (which is how `Ctrl+I` opens a single image while `Ctrl+U` opens a folder), the model lists from the config directory, the build targets from `scripts/build_executable.sh`. The training guide — patched repeatedly while the panel was being reworked — is a complete document again, and it exists in Chinese too (`examples/training/ultralytics/README_zh-CN.md`), so the loop's docs finally match the interface's language; the two Chinese links in `docs/zh_cn/` point at that version. All 80 relative links in the four documents were resolved before committing.
- **The training window reads as one language, and the run survives the window.** Three leftovers from before the interface was translated, all in the same "it works but you have to know" category. The Config tab was half Chinese and half bare English field names — the group titles came from `tr()`, while the 59 labels inside them (`Project:`, `Epochs:`, `LR0:`, `Close Mosaic:`, `Skip Empty Files`…) were plain string literals that no translator ever saw; they all go through `tr()` now with Chinese in the catalog, and a test builds the dialog with the shipped catalog installed and asserts every visible label comes out Chinese, so the next unwrapped label fails the suite instead of shipping. The log was written to disk only from `closeEvent`, which means a crash, a force-quit or a cleared log view took the only copy — it is written whenever a run reaches a terminal state (error logs are persisted *before* the modal box, which is where a user can still close the app), identical content is not written twice, a second-granularity name collision keeps both snapshots, and the log view itself is capped at 10k lines so a chatty worker cannot grow it without bound. And the six thumbnails were the whole story for the run's images: clicking one now opens an in-dialog pager over everything the run wrote (every train batch, both val batches, results / PR / F1 curves, the confusion matrix) with arrow-key and button paging that wraps, plus **Open in System Viewer** for zooming. The WSL2-aware "open this in the desktop" logic existed twice (image and directory) and the pager needed a third copy, so it is one `platform_open.open_path()` now — which also retired the last baselined `B907` finding, and the flake8 baseline was re-frozen to lock that in.
- **The training form explains itself, and offers three preset paces.** The advanced half of the Config tab was a wall of bare jargon — `LR0`, `LRF`, `DFL`, `Kobj`, `Close Mosaic` — with no note anywhere saying what a value does or when to move it, which is the whole difficulty of the panel: the defaults are fine, so nothing teaches you what changing them means. All 36 advanced fields (strategy, learning rate, warmup, augmentation, regularization, loss weights, checkpoints) now carry a tooltip that says what the parameter is *and* which way to push it, and five more on the Basic row do the same (`-1` on Batch picks the batch size automatically on GPU and falls back to 16 on CPU; Workers is forced to 0 there). A `Presets` row on top answers the other question — how hard should this run try — with `Quick check` (30 epochs at 416), `Standard` (the shipped defaults) and `High quality` (300 epochs, cosine LR) setting epochs, image size, patience, close-mosaic and cosine LR in one click, replacing those fields (that is what a tier button is for) and logging what it applied. Five tests drive the real dialog: every listed field must have a tooltip, a tier must apply every value it names, `Standard` must equal the shipped defaults, and an unknown tier must change nothing.
- **A running job says how much time is left, and a failed one offers the fix.** Three gaps in the same area: the status label read "Ready to train" for the whole dataset build (the phase lived only in the log), nothing estimated the remaining time, and an error dialog explained the cause but could not act on it — pressing retry after an out-of-memory reproduced the out-of-memory. The build now has its own `Preparing dataset` status (its own colour and wizard hint; the start button was already on the other tab) that `training_started` replaces; the metrics line gains "About 12 min left", computed from the deltas of ultralytics' *cumulative* `time` column so the slow warm-up epochs do not dominate and a resumed run — whose clock restarts while the epoch counter continues — does not divide by the wrong number (eight tests cover the arithmetic, including the repeated row a resume can leave behind); and the failure dialog adds a one-click remedy for the three causes we can name, applied to the form and logged before retrying: `Halve Batch & Retry` (halves the value that is actually in the field), `Set Workers to 0 & Retry` (access-violation / heap-corruption exit codes) and `Switch to CPU & Retry` (no usable CUDA device). The remedy is the default button when offered, because plain retry is the one action known to reproduce the failure; `Retry Training` and `Back to Config` stay as they were, and the error branch moved into its own method so the event dispatcher stays a readable switch.
- **The training form adapts to CPU instead of pretending it is a GPU.** The device dropdown was the only CPU-aware control: AMP stayed ticked (ultralytics ignores it on CPU — `batch=-1` silently falls back to 16 there too, and both are now in the field tooltips), and the GPU-oriented defaults (100 epochs at 640, batch 16) made a first CPU pass run for hours before it could say anything about the data. Choosing CPU now switches AMP off and disables it, remembering the choice so returning to a GPU device restores it rather than silently changing the setting; untouched epochs/batch/imgsz are filled from a CPU preset (50 / 8 / 416) and a note under Device says what was replaced and that the values remain editable. Nothing is overwritten: a field the user (or a saved per-dataset prefs file) already changed is left alone. The adaptation runs once after the config load rather than mid-load, because `device` and `amp` load in separate passes and the later pass would have re-enabled what the earlier one just switched off. Epochs/Batch/Image Size/Workers/Multi Scale gained tooltips while at it.
- **The training form starts filled in, and starting is one click.** `Model` and `Data` both used to open empty and had to be pointed at a file produced elsewhere: a `.pt` — with validation rejecting a bare `yolov8n.pt` even though `resolve_training_model_path` downloads exactly that — and a `data.yaml` whose only real content for det/seg/pose is the class list, which the tool can read from the labels it is already looking at. `Model` gains a task-aware preset dropdown (`yolov8`/`yolo11`, with the `-seg`/`-pose`/`-cls` variants) and defaults to the smallest family member; a preset left over from another task is swapped rather than trained, and a bare asset name now passes validation and is downloaded on first use. `Data` is generated per folder as a names-only yaml under the trainer root (folder name + path hash + task, so two folders never share one), refreshed on every visit to the Config tab and by the `From Labels` button, and a yaml the user picked is never overwritten; classification may leave `Data` empty now, which the validator had blocked despite the docs describing the flag-based flow. The download itself moved out of the UI thread into the training worker, where its progress lands in the log instead of freezing the dialog, and the Config tab's primary button is `Start Training` — it used to turn the page and wait for a second click on the Train tab even though the click that reached it had already validated and committed the run.
- **Eighteen more actions answer to the keyboard, and the keyless ones are a declared list now.** The audit behind this was mechanical: walk every `action(...)` call in `label_widget.py`, classify its third argument, and ask what the annotator actually reaches for mid-batch. It found 120 actions, 78 of them bound -- and, worse, that the unbound ones were not merely missing a key but missing from the yaml shortcut table entirely, so the settings dialog could not offer a rebind either. The threshold at the time was 12 per batch; 18 were fixed here: the other eight smart tools (`smart_calibrate` Ctrl+Alt+C, `smart_analysis` Ctrl+Alt+N, `smart_missing_scan` Ctrl+Alt+M, `smart_iteration` Ctrl+Alt+I, `smart_archive` Ctrl+Alt+H, `smart_advice` Ctrl+Alt+V, `smart_template` Ctrl+Alt+T, `smart_restore_backup` Ctrl+Alt+B), brightness/contrast (Ctrl+Alt+D), the three keep-previous toggles (Ctrl+Alt+1/2/3), the overlay toggles show-groups/scores/degrees (Ctrl+Alt+G/O/E), fill-drawing (Ctrl+Alt+Q), shape-converter (Ctrl+Alt+Y) and toggle-all-shapes (Ctrl+Alt+X). The template goes 78 -> 96 keys, and yaml / runtime map / F1 sheet agree at 96/96/96 with no ghost key, no key that needs a restart to rebind and no key hidden from the F1 sheet.
- **`save_to` was the one row the F1 sheet listed but never rendered.** Its config value was `null`, and `build_shortcut_rows` skips empty entries, so 另存到指定文件夹 was advertised in the source, editable nowhere and reachable by no key. It is Ctrl+Shift+E now, and the count of "listed but invisible" keys is zero.
- **The guards that keep this from rotting.** Three new ones, because all previous checks compared the three layers to each other and three layers can agree while being wrong together: `test_shortcut_bindings.py` walks the AST of `label_widget.py` and asserts every wired key exists in the template, that every keyless action is declared in `NO_SHORTCUT_BY_DESIGN` (22 entries, bidirectional -- an entry must leave the list as soon as it gains a key), that no template key is a ghost, and that the settings dialog describes no shortcut that no longer exists. `test_widget_wiring.py` gained the end-to-end pair: every `"shortcuts.X": self._widget.actions.Y` mapping in the runtime applier is checked against the live QAction's actual sequence (87 of 87 match), and every template key must be either mapped or listed in `HIDDEN_SHORTCUT_KEYS` (the nine the applier builds on demand). The first of these immediately earned its keep by finding `open_video` -- a shortcut description left behind for a feature this YOLO-only fork does not have.
- **The settings schema can no longer lose a field in silence.** `EXCLUDED_KEYS` was a declaration no code read: the template carries 224 leaves, the dialog exposes 165, and the remaining 32 — `device`, `file_search`, the dock and panel geometry keys, the canvas brush limits — sat outside both sets, changeable only by editing the rc file by hand. The runtime applier even carried branches for three of them, which could never fire because the controller emits only keys that exist as fields. The keys are enumerated as deliberately excluded with the reason beside each group, `runtime_applier` lost the branch that resolved to nothing (`training.ultralytics.project_readonly`), and `test_schema.py` gained `test_template_leaves_are_accounted_for`: every template leaf must be either a field or explicitly excluded, so the next one cannot go missing quietly.
- **The canvas repaints asynchronously on the hot paths.** 21 `self.repaint()` calls sat in mouse and keyboard handlers (20 in `canvas.py`, one in `canvas_rotation.py`); `repaint()` forces a synchronous full repaint on every move event, while `update()` coalesces them into the next event-loop turn — the Qt-recommended form, and the difference between one repaint per mouse-move and one per frame. Nothing else changed, but this is a responsiveness change: offscreen `repaint()` costs 0 ms by construction, so it wants the zoom/drag pass on real hardware rather than a test run.
- **Smaller cleanups in the same sweep.** The toast body used `QFont.Weight.Thin` (100) where "normal" was meant — the only `setWeight` call in the tree. `views/common/converter.py` lost an assigned-and-unused `output_files`, and its `__main__` block called `run_conversion()` with no arguments, which can only raise `TypeError`; the real CLI is `app.py --convert`, so it now says so. `filelist/quality.py` logged nothing when a label file failed to parse — the row was stamped "fine" while `data_audit` and `export_check` call the same file corrupted — it warns now. The export side and the training dialog disagreed about how a parked GPU is spelled (`""` vs `"-1"`), so the exporter's cleanup branch was dead code; both spellings are cleared. `scripts/compile_languages.py` and `scripts/generate_languages.py` printed an error and returned success when no Qt resource compiler was found, which would have published a stale `resources.py` as a successful build; both raise. And `generate_languages.py`'s `.ui` scan now honours the same `SKIP_DIRS` the Python scan does, instead of writing generated `_ui.py` files into `.venv` and `build`.
- **The YOLO/pose writers no longer leave half a label file behind.** `custom_to_yolo` built its output line by line with a bare `open(output_file, "w")`: a shape it could not handle raised part way through and left a truncated `.txt`, which ultralytics then reads as "this image has fewer objects" — a silently wrong sample rather than a visible error. It writes through a temp file and `os.replace`s it in, the way `label_file.save` always has. `tests/test_utils/test_atomic_label_write.py` pins the three states: a clean exit promotes the file, a raising body leaves nothing at all behind, and an existing file is left untouched.
- **The device picker's three paths agree now.** `DeviceManager._load_from_config` read `.xanylabelingrc` directly, bypassing `get_config` — so a `--config` file was ignored and what the settings dialog showed could disagree with what the model actually loaded — and `set_device` skipped the GPU-availability gate the environment and config paths apply, so asking for a GPU that was not there failed later inside whichever library first touched the device instead of falling back to CPU.
- **Three training-side gaps, all in the "it works until it does not" family.** `ExportManager.stop_export` cleared `is_exporting` *before* waiting, which let a second export start on top of a running one, and it reported `export_stopped` even when the join had timed out — `model.export()` is a single blocking call with no cancellation hook, so it now says so in the log and leaves the flag to the worker's own `finally`; the thread is a daemon, so closing the window no longer keeps the process alive for it. The trainer only swept the process tree when `terminate()` timed out, so a worker that exited quickly orphaned ultralytics' dataloader children; the sweep is unconditional. And the run history's "open this directory" hand-rolled a `file://` URL — a third copy of the WSL-aware logic — and goes through `platform_open.open_path` like the rest of the training window.
- **The OpenCV DNN engine refuses the configurations it cannot run.** `DnnBaseModel` implements `get_dnn_inference` only: pose models also ask for ONNX metadata, and every other task falls through to `get_ort_inference`, which it does not have. Pointing `engine: dnn` at those models used to fail with an `AttributeError` from inside the first prediction; the unsupported pairing is rejected at construction now, with a message that names the model type.
- **`test_window_placement` stopped writing to this machine's registry.** It drove `QSettings("anylabeling", "anylabeling")` — a registry key on Windows — and snapshotted and restored the real values around every case, so a failure midway left a trace behind. It runs against a file-backed settings object in a temp directory now, and a fourth test asserts the real key comes out untouched.
- **Dead code and duplicate paths.** `ai/config.py` carried `get_models_config_path` / `get_providers_config_path`, neither of which anything called — the one in use is `searchable_model_dropdown._get_models_config_path`, and it points at a different directory (the star import sitting above it is what hid the difference). `LRUCache` gained `clear()` and `__len__`, which the SAM2 unload needed to drop caches belonging to the sessions it was releasing. The flake8 baseline was re-frozen at 227 findings, down from 235.

### 🔗 CI / Tooling

- **The first tag CI caught four platform differences the Windows suite could not, all fixed here.** (1) Two doc links spelled `assets/annotations` while the directory is `assets/Annotations`; Windows resolves case-insensitively, Linux does not, and the link guard now walks every component case-exactly so the Windows runner catches this class too. (2) The hint-dedup and ICC-warning tests asserted that an uppercased path folds into one project, which only holds where `normcase` folds case -- the assertion is now conditional on that, and the hint's project key uses `realpath` so `/var` vs `/private/var` spellings also collapse on macOS. (3) The canvas label test compared whole-render ink, which on the Linux runner came out identical for both renders whatever the label path did; it now paints `paint_labels` directly and asserts the label rect starts at the box's top-left, independent of prior canvas state. (4) The hint tests now keep a module-level `QApplication` reference -- without one the file exited 127 when run alone, a crash the full suite had masked. Suite 1529 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **The YOLO writer's output is now asserted byte for byte.** The converter tests counted skipped shapes and checked that an all-out-of-bounds OBB produced an empty file; none of them read a populated export back. Six new tests in `tests/test_utils/test_label_converter.py` compare whole lines: the class index follows the classes-list order (`ship, plane` puts `1` on plane), hbb is `xc yc w h` with six decimals, a two-point diagonal rectangle expands to the same four-corner box, a skipped unknown label leaves no partial line, seg writes normalised vertex pairs, OBB keeps the four vertices in order, and pose emits the declared keypoint order with absent joints padded `0 0 0`. These pin the file ultralytics actually trains on, so a format change fails in CI instead of in a training run. Writing them also exposed a wiring fact: `custom_to_yolo`'s `obb_boundary_policy` is passed by no caller (`export.py`, the training split, `views/common/converter.py`) and has no config key, so only its `"skip"` default is reachable -- the pending clamp-vs-skip decision is therefore "implement and wire clamp" or "delete the parameter", not a choice between two live behaviours. Suite 1514 passed / 1 skipped, smoke 14/14, acceptance 17/17.

- **Acceptance step 17 holds the fork's own dialogs to the same copy rule, and measures the inherited ones instead of guessing.** The panel scan from step 16 became `untranslated_copy()`: every visible child's `text()` / `placeholderText()` with two or more Latin letters and no CJK is an offender, plus menu action texts. It is asserted on the surfaces this fork wrote -- 项目切换器 and 项目属性 -- and *reported* for the whole main window, because an English-source sweep across upstream widgets was ruled out of scope for this fork; now the size of that gap is a number rather than a worry. Measured on a real window: **10 entries, all technical names** (`YOLO HBB` / `YOLO Seg` / `YOLO OBB` / `YOLO Pose` in each of the 导入 and 导出 menus, `CPU`, `Ultralytics`) -- no untranslated prose anywhere the live window shows. Two distinctions the check had to learn the hard way: what is typed into a `QLineEdit` is data, not copy, and a placeholder can be data too (项目属性 hints the folder's own name because that is the default it would apply), so a step passes what it put on screen itself through `ignore`. The report line leads with an ASCII `[inherited-english]` marker because a redirected log is gbk, where the Chinese half of a line is exactly what cannot be grepped later. 17/17.

- **Acceptance step 16 walks 类别筛选 on a real window, and the panel is now checked for English no code guard can see.** The step opens the auto-labeling panel through the same `toggle_auto_labeling_widget()` the shortcut uses, expands 「更多」, and asserts the whole chain: the entry appears with a real layout box, `set_class_filter(["凹坑"])` produces index `[1]` on a stub carrying the **production** `YOLO.set_auto_labeling_filter_classes`, the choice lands in the project record, the mark moves onto 更多 when the panel collapses and disappears while it is open, and the dialog renders as 筛选类别 / 搜索类别… / 全选 / 确认 over the model's own class rows (`reviews/acceptance_shots/16a-16c`). Two things came out of running it rather than writing it. First, the step's own first version was wrong: it asserted the 更多 mark *before* any filter was active -- exactly the state that must stay unmarked -- so the harness caught an assumption, not just code. Second, the screenshot showed `● Ready!` in the panel's status slot, and no existing guard could have caught it: `.ui` default strings are outside the catalog (`lupdate` scans .py; "Ready!" has zero entries in `zh_CN.ts`) and outside the English-copy ratchet (it parses Python sources). The step now walks every **visible** child of the panel and fails on any `text()` / `placeholderText()` carrying two or more Latin letters without a single CJK one -- restoring the .ui string makes it report `['model_status_label: ● Ready!']`, and naming the widget is the point. Offscreen cannot stand in for this: `isHidden()` is a local flag, so a control inside a panel nobody opened passes a state-only assertion, and no `.qm` is installed there. Suite 1452 passed / 1 skipped, smoke 14/14, acceptance 16/16.

- **The coverage ratchet got tightened for the first time since it was written: floor 44 → 53.** `[tool.coverage.report] fail_under` has been a documented one-way rule since 2026-09-28 ("when coverage grows, raise this number; never lower it") and the CI test job runs with `--cov`, so the gate does work -- but nothing re-measures, so the number sat at 44 while the test batches of the last three weeks carried it to **53.72%** of 35602 statements. A stale floor is invisible: no commit fails because a gate is merely loose. Rounded down to 53 so ordinary float drift between runs cannot break CI. This closes the remaining half of `reviews/improvement_plan_2026-09-29.md`'s 「门禁 🟡 部分（覆盖率与键位覆盖棘轮未动）」 line -- the key-binding half is now covered by acceptance step 15 plus `tests/test_settings/test_shortcut_bindings.py`.

- **Acceptance step 15: every bound shortcut key is checked to actually be installed on the window.** `label_widget.py` carried `# XXX: need to add some actions here to activate the shortcut` next to the menu tuples handed to the action builder, and the existing shortcut gates (`tests/test_settings/test_shortcut_bindings.py`) only prove the *config* side -- action ↔ yaml ↔ description stay mutually consistent, which they can be while being wrong together with the F1 sheet. What was never checked is the Qt rule: a `WindowShortcut` QAction fires only while it is installed on a widget inside the active window, so "the yaml has Ctrl+B" is a different claim from "Ctrl+B does something". Measured on a real `MainWindow` with a folder open: **97 bound keys, 0 without a carrier, 0 whose action is never installed** -- the XXX's fear does not describe the current build, so the comment became a pointer to the guard instead of staying as an unfalsifiable worry. The step asserts the two structural facts and deliberately *not* enabled-ness (copy / paste / union are selection-dependent by design, and demanding they be live would only teach the next person to delete the check), plus a floor on how many keys are bound so a config that lost its shortcuts cannot pass by having nothing to verify. Two probe iterations were thrown away before this was trustworthy: the offscreen smoke widget stubs `LabelingWidget.menu`, which detaches every `QMenu` and made nearly everything look unreachable, and `QtGui.QKeySequence` canonicalises `Ctrl+Delete` to `Ctrl+Del`, so string comparison invented three "missing" keys. Acceptance 15/15, suite 1390 passed, 1 skipped, smoke 14/14.

- **The packaged CPU build was verified on a real machine for the first time, and it had quietly stopped being the lean build.** `reviews/training_review_2026-09-30.md` listed 打包版 as unverified; a `win-cpu` onefile was built from current source (into `dist-verify/`, never over `dist/`) and launched with `--work-dir` pointed at a scratch folder so a verification run could not write into the real recent-project registry or `.xanylabelingrc`. It behaves like the source tree: title `JLLabelingAndTrain v1.0.0-beta.6 - [pkgcheck_imgs] - p0.png [240x160] [1/3]` (folder-name fallback, file, size and the `[i/N]` counter all live in a packaged build), `Responding=True`, no `crash_*.log`, and `🧮 Auto-labeling device: CPU` in the app log. What the build revealed is size: **376 MB** where this target historically produced ~154 MB. Not a second Qt -- PySide6 appears 0 times in the build log -- but environment drift: the spec still said `excludes=[]`, and once torch / torchvision / ultralytics were installed into the same venv the *annotation-only* target swallowed them (`hook-torch.py` in the log), 2.4x bloat and a slower every-launch unpack. It also contradicted `docs/zh_cn/get_started.md`, which promises 普通 `win-cpu` 目标仍为仅标注、体积更小的版本, and the `-train` spec's own header (torch does not belong in a onefile). The CPU spec now excludes `torch`, `torchvision`, `torchaudio`, `ultralytics`, `ultralytics_platform`, `triton`: **154,417,283 bytes** and ~63 s to build, launched and verified the same way with identical results. The packaged app's limits are unchanged by this and now match the docs: annotation / review / smart tools / auto-labeling / export / run history work, the training panel reports it cannot import ultralytics (graceful, not a crash) and `win-cpu-train` is the target that trains. Not covered yet: the GPU path (no CUDA provider on this machine) and clicking through the packaged UI via UI Automation. Written up in `reviews/packaged_build_verification_2026-10-17.md`.

- The split batches got an integration smoke: `scripts/smoke_widget_paths.py` builds the real `LabelingWidget` offscreen against a real image folder and walks the seams unit tests cannot see -- folder import (the file_lifecycle rewires), a load_file round trip that has to restore zoom / scroll / brightness (ViewStateStore), the thumbnail panel show-reset cycle, review-state writes and the keep-alive quality-note stub, the canvas rectangle wheel edits, `delete_image_file` moving the image into the adjacent `_delete_` folder, and a YOLO export end to end. Nine steps, one report, exit code 0 only when all pass; modal confirmations are stubbed because they are a human step. The export step replaces only the two clicks a human supplies — it types the target directory and presses OK — while the dialog itself is built for real, so what runs is the production checkbox wiring; it then asserts the manifest's contents, the `classes.txt` / `data.yaml` / label file on disk, and that the summary popup names the record. Run it before a machine-verification pass or a release.
- `black --check` runs over the whole repository instead of only the changed files, which is what let three files in `widgets/auto_labeling/` stay unformatted while every commit passed. They are formatted now, and the repo is clean at 174 files.
- The size budget moves 6777 -> 6813 for `label_widget.py`. That is a feature, not drift -- +18 shortcuts is +8 net lines in `_build_actions`, plus 10 `widget.actions` members and 18 `widget.addAction` calls -- and the reason is written into the test so the raise is not mistaken for a precedent. The action-registration tail of `_build_actions` is the next extraction candidate; the next split batch should absorb the number.
- **Repaired a red `main`.** The previous batch opened the `v1.0.0-beta.6` changelog section without moving `app_info.__version__` off beta.5, and `read_changelog_section` requires the requested tag to be the newest section, so four release-notes tests failed on any checkout of that commit. The version matches the open section again.
- `test_shortcut_list_value_uses_first_entry` used "Ctrl+Alt+D" as its throwaway key; brightness/contrast took that combination over, so the fixture moved to an unbound one.

## `v1.0.0-beta.5` (Sep 29, 2026)

### 🛠 Improvements

- The first *domain* extraction, as opposed to a mechanical move: canvas rectangle geometry is now `widgets/rectangle_geometry.py` — plain functions taking the image bounds and the wheel-editing constants as arguments (`clip_rectangle_to_pixmap`, `scale_from_center`, `adjust_edge`), with the Canvas methods as thin delegating stubs. The math is testable without a widget, a pixmap, or an event loop: `tests/test_widgets/test_rectangle_geometry.py` (10 tests) pins clipping, atomic scale rejection, edge choice and clamping directly. `canvas.py` drops 4097 → 3974 and its budget follows.
- The hit test joined it: `Canvas._shape_hit_candidates` is now `canvas_geometry.hit_candidates(shapes, point, epsilon, is_visible, cuboid_vertex_lookup, cuboid_face_hit)` — the three interaction priority tiers (vertex, edge/new-point, body) and the stack-index tie-break are plain functions over the shapes, with the two canvas-owned cuboid lookups passed in as callbacks. `select_shape_point` itself stays on Canvas: it is the selection state machine, not geometry. Seven tests pin vertex-beats-body, stack-order tie-break, hidden/locked handling and the cuboid callback path. `rectangle_geometry.py` was renamed `canvas_geometry.py` to be the single home for this kind of math.
- The drag constraints joined it. `bounded_move_vertex` / `bounded_move_shapes` / `calculate_offsets` / `rotate_point` / `intersection_point` split into `canvas_geometry.move_vertex_bounded` (rotation adjoint corners, rectangle axis shifts, border intersection), `drag_shapes_bounded` (locked filtering, out-of-pixmap refusal, the offsets clamp), `selection_offsets`, `line_image_intersection`, `rotate_point` and `out_of_bounds` — the locked/cuboid dispatch and the `prev_point` bookkeeping stay on Canvas, which is state, not math. Canvas shrinks 3930 → 3772. Thirteen tests pin the clamp behaviour, including the upstream off-by-one (the clamp uses `pixmap.width()`, so a shape can end 1px over the border — the original XXX shaky comment, now pinned as-is instead of silently fixed).
- The god parameter got a contract. `label_widget_contract.py` declares `CONTRACT_MEMBERS` -- the exact set of 132 widget attributes and methods the five extracted modules touch, collected mechanically -- and `tests/test_labeling/test_label_widget_contract.py` locks it from both sides: a module reaching for a member that is not declared fails (the interface grows only on purpose), a declared member that no module touches fails (it cannot rot), and every declared member is proven to exist on `LabelingWidget` (methods, class names, `self.x =` and `widget.x =` assignments in the assembly helpers, module-owned scratch state, or inherited from Qt). The number is the honest size of the implicit interface the split batches created -- and the yardstick any future controller-class extraction will be measured against.
- Stage one of the roadmap ran: eight contract members left the widget. `_apply_checked_batch`, `_maybe_focus_low_confidence_shapes`, `_record_recent_dir` and `_maybe_show_smart_tools_guide` moved into `file_lifecycle` through the extraction script (byte-compared), and three existing stubs (`_set_file_item_annotated`, `_set_file_item_low_conf`, `_shapes_need_review`) were deleted in favour of direct cross-module calls. The contract follows at 128 — the honest outcome is smaller than the roadmap's guess, because most "unused" members turned out to be live canvas/list callbacks; the roadmap document records the corrected numbers and the reason. One real catch on the way: `_note_save_quality` is called by `attributes_controller` through `getattr(widget, ...)`, so deleting its stub would have silently dropped quality notes — the deletion was reverted, the stub stays with a comment naming the blind spot (a getattr string is invisible to both the AST scan and the contract test).
- Stage two opened with the thumbnail slice: `thumbnail_pixmap`, `thumbnail_image_label` and `thumbnail_container` were three loose members on the widget for one feature; they are `widgets/thumbnail_panel.py` now -- a `ThumbnailPanel` that owns the pixmap, the label and the show-hide policy, with `reset()` / `set_pixmap()` / `refresh()` as its surface. `file_list_ops.update_thumbnail_display` still decides *which* file gets a thumbnail (that needs the model config), but it only calls the panel now; `on_thumbnail_click` takes the panel instead of the whole widget. The contract drops to 125, and the three members that had no test at all are covered by six new `ThumbnailPanel` tests.
- Second stage-two slice: the view memory. `zoom_values`, `brightness_contrast_values` and `scroll_values` were three dicts on the widget, keyed by filename, written from three different files and read back in `load_file` -- the "where was I on this picture" state, in three places at once. They are `widgets/view_state.py` now: a `ViewStateStore` with `zoom` / `brightness_contrast` / `scroll`, an `is_empty()` that names the first-load-of-the-session check, and `remember_scroll` / `scroll_for` helpers. Eighteen call sites across `label_widget`, `file_lifecycle` and `file_navigation` follow. Contract 125 → 123; the memory itself -- which had no test at all -- gets five.
- The difficult checkbox reads the way the UI always looked. Its source string was the internal field name (`useDifficult`) while the catalog mapped it to 困难标志; the source is the Chinese string now and `zh_CN.ts` follows. With the source equal to the target text, `tr()` returns it unchanged -- the UI shows exactly what it showed before, and the `.qm` waits for the next `lrelease` run.
- The extraction roadmap is in the tree: `docs/zh_cn/controller_extraction_roadmap.md` records the contract analysis (73 of 132 members single-module-exclusive, 41 unused inside the class), the three stages, and -- after execution -- the corrected numbers, the reasons the remaining members are not sliceable, and the archived original plan. The machine checklist gained a section for this batch's paths.

## `v1.0.0-beta.4` (Sep 28, 2026)

### 🛠 Improvements

- The export honours the review state now, the way training always did. `only_checked_files` in the ultralytics general module has kept 需返工 images out of a training set for a while, while the YOLO export wrote them into the output directory anyway: an image marked for rework was good enough to leave out of training and good enough to hand to a customer. The export options gained 仅导出「已确认」的图片 (off by default, so nothing changes unless it is asked for), backed by `split_images_by_review()` and the file list's cheap head-scan reader; an unreadable state counts as unconfirmed rather than silently passing, and the recap names how many images the filter removed. An export that ends up with nothing says so instead of writing an empty directory. `tests/test_utils/test_export_summary.py::TestReviewStateFilter` covers confirmed / unchecked / rejected / missing file / legacy `checked` / filter off.
- The F1 cheat sheet admits that Ctrl+Z does two things. `undo_last_point` sat in `_HIDDEN_KEYS`, so the page a user consults when a key misbehaves was silent about the one case that surprises people: while a polygon is being drawn, Ctrl+Z drops the last vertex instead of undoing an edit. The two actions trade places through `mode_controller.toggle_drawing_sensitive`, and `SHORTCUT_DUPLICATE_WHITELIST` already recorded the intentional overlap; the row is advertised now, with the hidden-keys set empty and a test that keeps it that way.
- `switch_to_checked` is gone — the last of the ghost config keys. It arrived with the rebrand commit, was routed by `settings/runtime_applier.py` into `apply_behavior_flags()`, and that function has branches for four of the five keys it routes and none for this one; nothing else in the tree read it and the settings dialog never exposed it. What it presumably wanted — mark checked and move on — is `mark_checked_and_next` (Ctrl+Shift+J) plus `open_next_unchecked` (Ctrl+Shift+D). Dropping the key from the template also lets it self-clean out of existing rc files, which is the documented behaviour for template-deleted keys.
- OBB has an end-to-end guard, not just a menu entry: `tests/test_utils/test_yolo_obb_roundtrip.py` writes a rotation box out, reads it back and compares the pixels, checks the class index against `classes.txt`, counts the shapes the mode cannot express, and re-exports to prove both files are byte-identical — a re-export is exactly where drift would sneak in unnoticed. Measured on an offscreen widget, 12 frames of 5328×3040 load in a median 59 ms with the working set flat at 210 → 211 MB (one ARGB32 QImage is 64.8 MB, which is the whole first-frame step), so the load path does not leak. The numbers, and what the measurement cannot see — offscreen `repaint()` is a no-op, so drag feel stays a human check — are written down in `measurements_2026-09-27.md`.
- Digit shortcuts ship on now. The template's `digit_shortcuts: null` was the factory default, and null means "feature disabled" everywhere in `digit_controller` — so on a fresh install the 0-9 keys did nothing, with no hint that Alt+D or auto-assign even existed; "press a digit to slap the matching label on" is the cheapest efficiency win this tool has and it was off at the factory. The template now ships `{}` (auto-assign maps free digits 1-9 to labels as they are first seen) and a version-2 config migration flips only rcs still carrying the untouched null, so a deliberately configured map is never overwritten. null stays available as the off switch: once the rc is stamped version 2, a hand-edited null survives every later load. `tests/test_config_migrations.py` gained five cases pinning flip / respect-choice / off-switch behaviour.
- Auto-save is debounced. `set_dirty()` under `auto_save: true` used to run a full mkstemp + fsync + safe_replace cycle on every single edit — each wheel-step resize, each drag frame, no content check, nothing debounced but the feedback toast. On the mechanical and network drives industrial annotation actually runs on, that is a visible stutter per gesture, and it was the amplifier behind the keep_prev pollution path. Edits now arm a 400 ms single-shot timer and one write lands after the last change; the dirty flag stays set until the write actually happens, so every path out of the image flushes or asks first — `may_continue` (both silent switching and window close), `load_file`, `reset_state`, `set_clean`, and the explicit `_save_file`, which cancels the pending write so the file is not rewritten twice. The batch-export guard already keyed off `dirty`, which is now honest about pending changes. `tests/test_labeling/test_auto_save_debounce.py` (8 tests) pins schedule / flush / burst-collapse / supersede, and the two suites that read the disk right after an edit now flush explicitly first.
- Split batches 10-13 moved the navigation, file-list, and label-editing clusters the same way: `open_next/prev_image` and the unchecked-queue jumps to `utils/file_navigation.py`, thirteen list-item/tooltip/thumbnail/review-state operations to `utils/file_list_ops.py`, `edit_label`/`batch_edit_labels`/`loop_thru_labels`/`_apply_unique_label_rename`/`finish_auto_labeling_object`/`new_shape` to `utils/label_editing.py`, and `save_labels` to `file_lifecycle.py` — thirteen more methods, every one byte-compared instruction for instruction, `label_widget.py` down 7914 → 6832 across the four batches. Two more script bugs surfaced and were fixed at the gate: import merging compared statement text while black reshapes earlier copies into parenthesised blocks (double-inserting the roles import as 8× F811 — merging is by bound-name subset now), and nested `def` names were missing from the locals set, so every nested helper looked like an unresolved global. Cumulative for the day: 8380 → 6832 lines (−18.5%), the class's C901 count at zero, zero behaviour changes.

### 🔗 CI / Tooling

- Method extraction became a script. Split batches 5/7 proved the recipe by hand — free-variable analysis, `self` → `widget` rewrite, thin delegating stub, byte-compare — and every batch risked a slip doing it again. `scripts/extract_method.py` (`--dry-run` / `--apply`) mechanises the whole move: it refuses what it cannot move safely (`property`/`staticmethod`, `super()`, `global`, re-extracting a stub), reports the self-attributes / self-methods / external names the body needs, skips string literals during the rewrite, auto-copies the import lines the moved body needs, and byte-compares the moved function against the original — `co_code` must match instruction for instruction (LOAD_FAST addresses by slot index, so renaming the first parameter does not change the bytecode). `tr()` calls are flagged per method: runtime context survives (the call goes through the widget instance), pylupdate6 does not — the known i18n debt, now quantified per move. First batch through the script: `toggle_shapes_visibility`, `show_attributes_panel`, `hide_attributes_panel` → `utils/panel_visibility.py` with stubs left in the class.
- The two remaining god objects got a size budget. `tests/test_labeling/test_label_widget_size_budget.py` freezes `label_widget.py` at 8380 lines and `widgets/canvas.py` at 4097, the same ratchet pattern as the flake8 baseline and the coverage floor: a split batch that shrinks a file lowers its budget, nothing ever raises it. This exists because batches 1–7 showed the failure mode — extraction pulled methods out while edits elsewhere grew the file right back (7977 → 8378 across beta.3 despite two dedicated split rounds). The failure message names the file, the number to beat, and the script to use.
- Split batch 9: the file-lifecycle cluster left the god object. `load_file` (236 lines), `import_image_folder`, `delete_file`, and `delete_image_file` moved to `utils/file_lifecycle.py` through `scripts/extract_method.py`, each byte-compared instruction for instruction; the module-level helpers they need (`_report_inherited_shapes`, `move_file_to_delete_folder`) moved first, with re-imports keeping the test imports valid. `label_widget.py` drops 8380 → 7914 lines and the size budget moved down with it. The extraction run itself surfaced and fixed two script bugs the byte-compare guard caught before they could corrupt anything: string-literal ranges computed against the indented source drift once applied to the dedented body (they started eating real `self` references past the first docstring), and import statements pasted across package levels kept their relative-dot count, silently resolving to modules that do not exist. Imports are now copied as whole AST statements with the dot count adjusted for the depth difference.
- The extraction script grew `--translate-class`. A moved function's `widget.tr(...)` calls are rewritten to `QCoreApplication.translate("LabelingWidget", ...)` — equivalent at runtime (instance `tr()` resolves through the widget's own class), but pylupdate6 can only see explicit `translate()` calls, so moved strings stop silently dropping out of the .ts catalog. First batch through it: the 17 `tr()` calls that left with the file-lifecycle cluster are all explicit now. This is the i18n decision the reviews kept asking for, applied where it costs nothing: new moves no longer add to the translation debt.
- The export now writes a `data.yaml` next to `classes.txt`. `nc` and `names` come straight from the class list — the part that is easy to get subtly wrong (order, spelling), and the exact mistake that makes an export silently drop a whole class — while `path`/`train`/`val` are left as comments: the export cannot know the dataset layout, and a guessed path would point at directories that may not exist. Gated behind the same 写入 classes.txt checkbox and reported in the export recap. Pinned by three tests in `tests/test_utils/test_export_summary.py`.
- Coverage got a ratchet. The CI test job printed the coverage table and stopped there — a number nobody was accountable to, free to slide on every refactor. `[tool.coverage.report]` in pyproject.toml now carries `fail_under = 44`, measured 2026-09-28 at 44.72% of 32088 statements, and pytest-cov fails any `--cov` run below it; a bare local `pytest tests` stays the fast path. The old comment that argued a threshold nobody could pass is worse than a number somebody reads is replaced by the ratchet rule instead: when coverage grows, raise the number — never lower it.
- The six batches passed machine verification. `docs/zh_cn/split_verification_2026-09-28.md` is the 15-minute checklist that was run — every high-frequency path the extractions touched, ordered by risk, each item tagged with the batch and module to blame if it fails. Byte-compare proves instruction equivalence; this proved the feel.

## `v1.0.0-beta.3` (Sep 28, 2026)

### ✨ New Features

- YOLO OBB can come in and go out through the menus at last. The converter already spoke `obb` (`custom_to_yolo` had the branch, `views/common/converter.py` listed it for the CLI, `yolo_obb_to_custom` handled the way back) and both READMEs plus `user_guide.md` section 4.1 promised rotation-box import/export — but the Export and Upload menus offered only hbb/seg/pose, so drawing a rotation box with `O` was a dead end. Both menus now carry a fourth entry, the upload path dispatches to `yolo_obb_to_custom`, and `classes.txt` is shared with the other two box modes. Pinned by `test_yolo_obb_can_come_in_and_go_out_through_the_menus` and `test_every_yolo_export_action_is_wired_to_the_converter`. The five empty `None` slots that had been padding both menus are gone with it.
- An export now reports what it did. `LabelConverter.custom_to_yolo` gained an optional `stats` out-parameter (the return value stays the same bool, so the CLI is untouched) counting written shapes, shape types the mode cannot express, labels missing from the class list, rotation boxes left outside the image, and images with no label file at all; the completion popup reads 导出完成：N/M 张图，K 个标注 followed by one line per skipped reason (`4 × polygon is not part of a hbb export`, `1 × label not in classes: dog` — sorted by count, then name) and switches to a warning icon when anything was dropped. Skips also reach the log as a warning. This replaces a popup that said "Exporting annotations successfully!" whatever had happened, which is how a batch that silently dropped every polygon passed for a good run. `tests/test_utils/test_label_converter.py::TestLabelConverterYoloExportStats` (6 tests) and `tests/test_utils/test_export_summary.py` (6) pin the counters and the wording.
- The class list no longer has to be hunted for on every run. `resolve_classes_for_yolo` (shared by export and upload) offers the open project's own labels first — they are what the shapes on screen were drawn with, in that order — and keeps the `classes.txt` picker for when the target order differs; `LabelConverter(classes=[...])` was added so a list can be passed without round-tripping it through a temp file. The export dialog can also drop a `classes.txt` next to the labels (on by default), so the training side no longer needs a hand-assembled copy: `test_writes_one_class_per_line_in_order` covers the writer.
- Four smart tools got keyboard shortcuts, a new group in the F1 cheat sheet (质检与审核), and entries in the settings map so they can be rebound live like every other key: 数据体检 `Ctrl+Alt+A`, 智能复核 `Ctrl+Alt+R`, 标注传播 `Ctrl+Alt+P`, 旧轮模型框盘点 `Ctrl+Alt+S`. The quality/review tools were menu-only, which left the four actions an annotator runs on every batch needing a mouse; they are the first 智能工具 entries to join the actions struct, and the shortcut-count anchor in `tests/test_settings/test_schema.py` moved 74 → 78 with them. `test_the_quality_tools_are_reachable_from_the_keyboard` fails if one loses its key.

### 🛠 Improvements

- Clearing the output directory is no longer one click. The "directory already exists" prompt offered `Yes - merge` / `No - delete existing directory` / `Cancel`, and `No` ran `shutil.rmtree()` straight away — on a path the annotator typed, which the same export may just have copied the images into. It is now `Merge` (the default button, and what most runs want) / `Clear` / `Cancel`, and `Clear` asks a second time with a critical icon, the directory path spelled out, "Cancel" as the default, and a log line when it does happen. The unmounted VOC/COCO exporters keep the old copy for now; they are reachable only from code.
- `keep_prev` is documented as what it is. `docs/zh_cn/fork_features.md` gained a section explaining that inherited shapes stay unsaved, why the negative-sample case is the dangerous one, and that 标注传播 (now `Ctrl+Alt+P`) is the better tool when the intent is to carry boxes forward.
- The user guide admits the fork's scope. `docs/zh_cn/user_guide.md` section 4 opens upstream's eleven-format tour with a banner: the GUI provides YOLO hbb/seg/obb/pose, VOC and COCO are CLI-only, and the formats from 4.4 on are not shipped at all — the page previously read as instructions for menus this build does not have, and an annotator following it would find nothing. `docs/zh_cn/fork_features.md` gained an 导入导出（YOLO） section (the sections after it renumbered) covering the class-list prompt, the export recap and the overwrite policy.

### 🐛 Bug Fixes

- `keep_prev` no longer writes the previous image's shapes behind the annotator's back. With 保留上一张标注 on (`Ctrl+P`), `load_file` copies the previous shapes into an image that has none and then called `set_dirty()` — which, under the shipped `auto_save: true`, wrote them to disk at once: an image that honestly contains nothing (a negative sample) silently became a duplicate of its neighbour, with a toast that only said 已保存（自动）. `set_dirty()` now takes `from_inherited` and skips the auto-save for that proposal, `set_clean()` ends it, and the annotator is told in the status bar (已继承上一张的 N 个标注，尚未写入本图（按 Ctrl+S 保存，或直接编辑后自动保存）) and in the save-state tooltip. Any real edit clears the flag and auto-save resumes; leaving the image no longer passes through the silent-save branch of `may_continue` — it asks, with the inherited state named in the question. The delete actions had guarded against `keep_prev` for years (`delete_file` refuses while it is on); only the write path had not. `tests/test_labeling/test_keep_prev_proposal.py` pins all six behaviours, including that a normal image still saves silently when switching.

### 🔗 CI / Tooling

- The dependency locks went per platform: `requirements-lock-{win,linux,macos}.txt` replace the single universal file, because a universal resolution drags the Linux-only `PyQt6<6.10` cap onto every OS — and on Windows that 6.9.x binding makes `import onnxruntime` access-violate inside PyInstaller's isolated analysis subprocess, which is what took the first release run's win-cpu build down (linux and macos built fine and were let through). The release build jobs and the smoke matrix each install the lock for their OS. `PySide6` left the `dev` extra at the same time — the i18n tools live in their own venv, and with PySide6 installed next to PyQt6 the same onnxruntime import crashes reproducibly in a clean environment, PySide6 itself unimported. The device probe that `import anylabeling` ran at import time is lazy now as well: `checks.py` resolves `__preferred_device__` inside `run_checks()` instead of at import, so merely importing the package no longer loads onnxruntime.

## `v1.0.0-beta.2` (Sep 27, 2026)

### ✨ New Features

- The flake8 gate is real now: `scripts/check_flake8_baseline.py` freezes the fork's inherited findings as `<path> <code> <count>` triples in `scripts/flake8_baseline.txt` (line numbers deliberately excluded, so editing a file above a finding is not a regression, and paths are separator-normalised so a Windows-generated baseline gates a Linux runner). It fails only when a `(path, code)` pair is new or its count rises, reports what improved, and re-freezes with `--update`. 13 tests in `tests/test_utils/test_lint_baseline.py` pin both directions, including that a gate which never fires is not mistaken for protection.
- Dependencies have a lock file: `requirements-lock.txt` (335 lines) pins the whole cpu+dev+test set — resolved universally with `uv pip compile --universal`, so one file serves the three OSes the release builds on, with `macholib`/`pywin32-ctypes`/`colorama` carrying proper environment markers. The new `test` extra (`pytest`, `pytest-cov`) collects what CI used to install as loose words. Both the CI test job and the release build jobs now install the lock and add the project with `-e . --no-deps`, so a release binary is built from exactly the versions the test gate ran against — not from a fresh resolution that could pick up something newer overnight. The regeneration command lives as a comment above the `test` extra in `pyproject.toml`.
- The `SimpleNamespace` stub convention is written down at last: CONTRIBUTING.md gained a "Testing Conventions (This Fork)" section covering the real-method-on-fake-widget pattern, the sharp edge that any new `self.foo()` call breaks every stub traversing that path (the failure that turned 17 tests red when settings code touched `QCoreApplication`-adjacent attributes directly), the prevention rule — new helper logic goes in module-level `def f(widget, ...)` functions with thin class delegates, as `attributes_controller.py` and the canvas mixins already do — plus the rc-write protection and the stub-vs-real-fixture division of labour. The convention used to live only in one session's notes; now a contributor can hit it before the tests do.
- Startup goes through the project manager: the "继续上次标注？" prompt is replaced by a three-way decision (`project_registry.decide_startup_action`, pure and tested) — a recorded session is restored directly (folder plus last image, no questions asked), a registry with entries but no current session opens the project manager dialog instead, and a true first run keeps the empty-canvas CTA unobstructed. A new `startup_show_project_manager` rc key (default off) shows the manager on every launch; the switch lives as a checkbox inside the dialog itself. The switcher grew into the project manager: four columns (项目 / 上次打开 / 训练 / 最近训练) join `run_meta.json` records to each project by normalized path prefix — the recorded label dir anchor beats the image folder, sibling folders (`plates` vs `plates_extra`) never cross-credit, and runs without a dataset record are skipped rather than guessed (`run_history.project_training_stats`, `dataset_label_dir` now carried on every row). 5 new tests: `test_startup_action_matrix`, `test_startup_show_project_manager_defaults_off`, `test_project_training_stats_match_by_closest_anchor`, `test_project_training_stats_respect_prefix_boundaries`, `test_project_training_stats_without_runs_root_is_all_zero`.
- Hover text where the fork's data actually lives: an object row now shows class, shape, producing model plus its weight digest, confidence, vertex count and bounding box, attributes, description and what protects it; a file row shows the path, its label file, the review state with timestamp and, for the open image, the model/human/unknown split. The panel grip and collapse button, the zoom box, both filter comboboxes, the label search, the preview sliders and the auto-labeling panel buttons got real tooltips too.
- The status dot's one-line tooltip (`已检查` / `负样本…`) is folded into the row tooltip instead of fighting it for the same property — refreshing the icon can no longer erase the detail, and one builder owns the text.
- Multi-project support, layer by layer: the label panel's suggestion list and the annotation output dir now live in `.jllabel/project.json` too (anchored at the image folder — `classes.txt` still wins for classes), so folder B no longer inherits folder A's labels or output dir; a recorded dir that no longer exists is ignored, not cleared. The project switcher (`文件 → Switch Project`, Ctrl+Shift+O) lists every opened dataset with its label dir and last-opened time (registry at `<work_dir>/.jllabel/projects.json`, 20 entries, vanished folders skipped) and carries 打开项目设置文件夹 / 重置本项目设置 (keeps the pinned split seed) / 从列表移除. Training tuning mirrors per dataset through a whitelist (`train_prefs`: `basic.model`/`pose_config` plus the eight pure hyperparameter sections — never `project`/`name`/`data`/`device`/`workers`/`dataset_ratio`): the config tab restores the dataset's last-used values on open, and committing a run records them. A second instance is detected per work directory and logged — project settings are isolated, but the global rc and recent lists stay last-close-wins. `run_meta.json` records the open dataset's label dir, and the experiment-history table gains a 数据集 column so rounds from different datasets can be told apart. Guarded by 25 new tests in `tests/test_utils/test_project_settings.py`.
- Search box in the settings header. 119 settings sat behind four pages and three levels of navigation with no way to filter; the box now matches across every page at once, on key, title, English description *and* the Chinese translation of that description, so typing 撤销 lands on "Undo Backups". Results keep their real editors — a setting found by search can be changed in place, and the edit marks its *owning* page dirty — and each result group carries a breadcrumb plus 打开此页 to open the page it lives on. Shortcut entries also answer to the Chinese name the F1 cheat sheet gives them, so 撤销 finds `shortcuts.undo` too.

### 🛠 Improvements

- God Object diet, batch 8 -- this time `canvas.py` (4496 lines, 157 methods). The cuboid geometry and interaction cluster (26 methods, 395 lines) moved verbatim into `widgets/canvas_cuboid.py` as `CuboidCanvasMixin`, in the same style as `BrushCanvasMixin` / `CanvasRotationMixin`: the methods are byte-identical to what they were, because a mixin needs no dedent and no `self.` -> `widget.` transform, and the cluster turned out to be pure geometry -- its only references outside itself are `self._palette`-style instance attributes, with no `update()` or other Qt side effect anywhere. The eight `CUBOID_*` constants moved with it and `canvas.py` re-imports the names, so `tests/test_canvas/test_cuboid_interaction.py` and the mouse-event code that predates the split keep importing from `canvas`. `canvas.py` is 4098 lines now (was 4496); `calculate_offsets` / `get_adjoint_points` / `get_cross_point` stayed behind because the rotation path shares them.
- God Object diet, batch 7: the settings dialog's chrome (280 lines) moved out of `settings/dialog.py` into `settings/appearance.py` -- the palette, the two icon painters and four stylesheet builders. It was the only cluster in that 2434-line, 94-method class touching nothing but `_palette` and `_nav_icon_size`, so the cut was free: eight thin delegates stay behind and all 76 `self._rgb(...)` call sites keep reading the same. `dialog.py` is 2186 lines now. The move is verbatim after the mechanical `self.` to `widget.` transform (which also rewrote the 14 internal `_rgb` calls); the three CSS templates lost four columns of leading whitespace per continuation line with their code (1524 to 1368, 1814 to 1614, 692 to 608 characters). Checked against the pre-move methods loaded out of `HEAD`: identical line for line once leading whitespace is stripped, every declaration unchanged, and all eight navigation icons come out pixel-identical.
- The fork's own features finally have user documentation. They were described nowhere but this file, which is written for whoever maintains the code. `docs/zh_cn/fork_features.md` covers project management and per-project settings, the review-state workflow, the eleven smart tools in their recommended order, the training loop and its `run_meta.json` / `manifest.json` reproducibility, shape provenance, the settings dialog and the shortcut layer, and where each piece of data lands on disk. It is Chinese on purpose and the English README says why: Chinese is the source language for everything this fork owns and the interface ships only `zh_CN`. Linked from `user_guide.md` section 10 and the README doc index.
- `views/training/ultralytics_dialog.py` no longer star-imports. Five `from ... import *` lines pulled 39 names in from the widgets and auto-training packages and hid 157 findings behind `F405` ("*may* be undefined"); they are now explicit imports listing exactly the 36 names the file uses, resolved in the same order as before. Two of those names (`get_settings_config_path`, `TASK_SHAPE_MAPPINGS`) were claimed by two modules each and three (`get_theme`, `os`/`json`/`csv`/`re`) were shadowing an earlier import -- all verified to be the *same object*, so the rewrite is behaviour-preserving. The file's flake8 count went 157 to 1 (a pre-existing `C901`), and the repository total 331 to 175.
- flake8 had two configs and the authority was the wrong one: `pyproject.toml` carried a `[tool.flake8]` table that flake8 never reads (it needs the third-party Flake8-pyproject plugin), duplicating the `ignore` list that `.flake8` actually applies -- free to drift, and holding the only copy of the `exclude` list, which is why the generated `anylabeling/resources/resources.py` was being linted. The dead table is gone, `.flake8` gained that exclude, and `select = B,C` now means something because `flake8-bugbear` and `flake8-comprehensions` are installed by the `dev` extra everywhere (neither was installed anywhere before, so those rules silently did not run). `B950` is ignored next to the already-ignored `E501`, since it is the same check with 10% tolerance -- leaving it on would have policed 86 columns by the back door, which is 335 of the findings.
- Typo sweep over comments and docstrings: `paramters` to `parameters` in four ONNX exporters, `contorl` and `abreviated` in `__base__/clip.py`, `lables` in `label_widget.py`. `.codespell-ignore` records the four words codespell gets wrong here -- `dota`/`mot` are dataset names, `dfine` is a model name, and `pres` comes from splitting the `pResx`/`pResy` locals of `Canvas.rotate_point`; `degress` is parked there with the reason written down.
- Cross-platform test hardening for the new smoke matrix: the catalog-location check normalises pylupdate6's separator-native paths (a Windows-built `zh_CN.ts` pointed 44 files through backslashes that only resolve on Windows), the provenance path test compares `realpath` on both sides (macOS reports `/var/tmp` as `/private/var/...`, Windows CI builds tempdirs under 8.3 names like `RUNNER~1`), the font-selector test asserts an order-preserving subset instead of a snapshot (macOS enumerates fonts lazily), and the two AMG chunk-count tests skip on darwin where the stub's grid-hit boundary flips on libm rounding.
- The archived upstream pages now say so on the page. `docs/{en,zh_cn}/{chatbot,vqa,image_classifier,paddle_ocr,model_zoo}.md` are reachable from a search engine or from `user_guide.md` and read as instructions for panels this build does not ship; the README disclosed their status but the pages themselves did not, so each got a banner pointing at "Fork scope". `user_guide.md` section 10 stopped listing them as live features, and dropped a link to upstream's `video_classifier.md`, which is not in `docs/en/` or `docs/zh_cn/` either. `docs/site.yml` had declared that same missing page as a workflow -- a manifest entry no code path reads and no renderer complains about. `tests/test_utils/test_docs_manifest.py` now checks both: every manifest workflow resolves in every declared locale, and every relative `.md` link in the two guides exists.
- One command name: the `xanylabeling` console-script alias is removed, and the converter's usage text plus every documentation example follow `jllabelingandtrain`. The packaged default config is `jllabeling_config.yaml`, `x-anylabeling.desktop` became `jllabelingandtrain.desktop` (nothing referenced it), and the training payload's temp-file prefix and model-download User-Agent carry the fork's name. On-disk data locations — `~/.xanylabelingrc`, `xanylabeling_data/`, `xanylabeling_logs/`, the Qt settings domain — and the Python package name stay, because renaming those costs either your existing weights/runs/config or upstream mergeability.
- The 1744-line `_build_actions` built the actions, the menus, the tool list **and** the entire layout, so its name described a third of what it did. The layout half is now `_build_layout(widget)` (249 lines, called from `__init__` right after, in the same order), and the split was dependency-free: the laid-out half touches nothing but `widget` attributes, which is why it moved as a byte-identical block (the diff shows those 249 lines as context, not as rewrites). The menus stayed behind on purpose — they consume ~80 of the action handles created just above them, so carving them out would mean threading a namespace through both halves for no gain. `_build_actions` is now 1498 lines and its docstring says what it really does.
- God Object diet, batch 5: the attribute-panel cluster (498 lines) moved out of `label_widget.py` into `widgets/attributes_controller.py` — `update_attributes` (348, the width-wrapping radio/combo/lineedit editor grid with its four nested helpers), `save_attributes` (81, the standard label-file serialization) and `shape_selection_changed` (69, edit-action syncing) as widget-first module functions, byte-identical after the mechanical `self.` → `widget.` transform (verified against `HEAD` blocks, multiline-string token check included). `_measure_text_width` moved to `utils/qt.py` as `measure_text_width` (aliased back so moved bodies stay untouched). The widget keeps thin delegates, so menu wiring and the unbound-call test style hold; the one test patch target that named `label_widget.LabelFile` now names the new module. `label_widget.py` is 8727 → 8238 lines, and its flake8 baseline dropped from 6 to 4 entries (the `update_attributes` C901 and one `blocker` F841 moved out with the code). Full suite 703 passed.

### 🐛 Bug Fixes

- The translation catalog stopped silently losing strings. `pylupdate6` attributes a `tr()` call to a context only when the receiver is a class it can see, so the 416 `widget.tr(...)` / `parent.tr(...)` calls inside module-level helper functions were dropped wholesale: the next extraction lost 249 `LabelingWidget` entries, and since the dropped translations were still in the shipped `.qm`, nothing would have shown up until a rebuild. A probe against both extractors settled the fix -- `QCoreApplication.translate("LabelingWidget", ...)` is recognised by `pylupdate6` *and* `pyside6-lupdate`, inside and outside classes, with the right context. All 416 call sites were rewritten and reflowed with `black`, and the View-menu item is spelled `Show Degrees` now. The catalog grew 1013 -> 1133 entries with **zero** unfinished, and the whole chain (`.ts` -> `.qm` -> the blob embedded in `resources.py`) was rebuilt together. `scripts/generate_languages.py`'s shrink guard stayed quiet because the catalog grew instead of shrinking.
- The training-failure dialog could not be shown at all. `on_training_event` built its error box through `QtWidgets.QMessageBox` while the module only imported the widget classes themselves, so every failed run ended in `NameError: name 'QtWidgets' is not defined` instead of a readable "training failed" box with its Retry button. The name was never supplied by any of the five star imports either -- a star import downgrades a missing name from `F821` to `F405`, so it sat inside 157 "probably fine" warnings until the star imports were replaced, at which point the four real uses turned into `F821`. Fixed by importing `QtWidgets` the way `app.py` and `toaster.py` do, and covered by 5 tests in `tests/test_auto_training/test_training_error_dialog.py` that drive the branch with a recording message box.
- `scripts/generate_languages.py` will not silently eat the catalog any more. `pylupdate6` can only attribute a `tr()` call to a context when it can see one, so `widget.tr(...)` inside a module-level function is dropped without a word -- and this fork moved a lot of `LabelingWidget` methods into `widget`-first module functions, leaving 249 of its 421 entries looking obsolete on the next extraction. Running the script today reported "249 obsolete messages were discarded" and recompiled a catalog with 790 entries instead of 1013: 26 user-facing strings would have lost their Chinese, and one of them (`Show Degrees`, the View-menu item) would have fallen back to English because the extractor cannot place it at all. It also leaves the ~249 dropped messages' translations stranded: they are still in the shipped `.qm`, so the loss only shows up at the *next* rebuild. The script now compares the entry count before and after and refuses to go on when a run sheds more than 10%, naming the likely cause. Verified by running it: it raises instead of overwriting. The underlying extraction problem (and the `Show Degress` typo it protects) is left for a dedicated i18n pass -- fixing it properly means an explicit context for every `tr()` that moved out of a class, plus a rebuild of the blob embedded in `resources.py`.
- The shipped Chinese catalog was an inherited upstream artefact, not this fork's own. 69 of its `<location>` entries named files this YOLO-only fork deleted (772 locations total), and it still carried 725 strings for dialogs that do not exist here — `VideoClassifierDialog`, `PPOCRDialog`, `ChatbotDialog`, `VQA`/`Classifier`/`Export` and others. Meanwhile 336 strings actually present in the code were missing from it, so they could never be translated. Re-extracted from the current tree: 1013 entries over 39 live contexts, 0 dangling locations, 0 unfinished translations, and every context name is a class that still exists. `scripts/generate_languages.py` also walked `**/*.py` including `.venv`, which would have drowned the catalog in dependency strings; it now scans `anylabeling/` only, skips generated blobs and build dirs, and fails loudly when the extractor is missing instead of shelling out, ignoring the error and recompiling a stale `.ts`.
- Three model-manager messages could never be translated: `Loading model: {model_name}. Please wait...`, `Error in loading model: {error_message}` and `Error in model prediction: {error_message}` were passed to the translation call as *variables*, and the extractor only reads literals — it recorded one `(unknown)` placeholder instead of the three strings. The literals are now passed at the call site, so they are extracted, translated and reachable at runtime.
- `tests/test_utils/test_translations.py` now holds the catalog to its sources: no location may point at a missing file, every context must name a live class, nothing may be left unfinished, and all 722 English→Chinese entries must match what the compiled `.qm` in `resources.py` returns — a `.ts` edit without a rebuild fails the suite instead of being invisible at runtime.
- The floating tools panel showed one button out of 26. Its content is a `QScrollArea`, whose `sizeHint()` is the scroll area's own small default rather than the toolbar inside it, so `adjustSize()` sized the panel to ~76px and everything else went behind a scrollbar; `sync_to_parent()` only ever set a *maximum* height, which cannot make a widget taller. The panel now sizes its content from the largest height any source reports (scroll area, inner toolbar, minimums) and clamps to the viewport when the window is short — the scrollbar stays as the overflow path it was meant to be. Measured on a 1400×900 window: panel 50×76 → 50×711, all 26 tools visible. The existing panel tests fed it a fixed-size `QFrame`, which is why none of them caught it; `TestPanelWithScrollAreaContent` covers the real shape, including the short-parent clamp.
- Launching with `--filename <folder>` died at startup with `AttributeError: 'LabelingWidget' object has no attribute 'settings'`: the recent-folders feature records the opened folder through `self.settings`, but the folder import ran ten lines before `self.settings` was created. Opening a folder from inside the window still worked, so nothing but a folder launch hit it — and no test constructed the widget with a folder. `QSettings` is now restored first, and `TestWidgetLaunchedWithFolder` covers the path (reverting the order fails it with the original traceback).
- `checks` inside a built executable reported `None` for PyQt6, onnxruntime and OpenCV while the app was using them: the versions came from packaging metadata, which PyInstaller does not carry. They are read from the live modules now, and the PyQt6 line names the Qt runtime too.
- Both get-started pages told readers to `pip install --pre "x-anylabeling-cvhub"`, to clone `CVHub520/X-AnyLabeling`, or to download the GUI installer from upstream's Releases. All three get you **upstream's** program, which has none of this fork's loop features; the pages now state that this build is source-install only, publishes nothing, and its executable comes from building it yourself.
- `load_recent_dir` was defined twice in `LabelingWidget` (line 2380 and line 5526), so the second silently shadowed the first — and only the earlier one carried the empty-path guard. This is the same failure mode as the five shadowed file-list methods fixed earlier, which were found by eye; the whole tree was re-scanned with an AST pass over every class body in `anylabeling/` and `tests/`, which now reports **0** duplicate definitions (property/setter pairs excluded). The dead copy is gone, the survivor kept the docstring and the guard.
- Three methods had no caller anywhere in the tree, not even a test: `copy_to_clipboard`, `update_selected_options` and `has_labels` (99 lines, zero references across every file type in the checkout). They were orphaned by the review-flow rewrite and the attribute-panel rework; deleted rather than left as an untested surface. `dragEnterEvent`/`dropEvent` stay — Qt calls those.
- Two code paths computed the same label path with the same `output_dir` override written out twice (`get_label_file()` and `_label_path_for_image()`), so a change to the override rule could land in one and miss the other. `get_label_file()` delegates to `_label_path_for_image()` for that part now; only its `self.label_file` / `.json` handling sits above the delegation.

### 🔗 CI / Tooling

- First release cut by this fork's own pipeline: `v1.0.0-beta.2` is the first tag that runs the tag → verify → test → build → publish chain from `.github/workflows/release.yml`, with binaries for every OS the README claims.
- `pytest-cov` is wired up, so "how much is tested" has an answer: **44.3%** of 31891 statements across 158 files, with 35 files complete. The distribution is the interesting part -- `views/labeling` is 49.8%, `services/auto_labeling` 28.1%, `views/training` 21.3%, and `app.py` / `views/mainwindow.py` are at 0%. The single worst offender is the fork's own `views/training/ultralytics_dialog.py`: 1741 statements at **12.3%**, which is exactly where the `QtWidgets` NameError lived, so the two findings are the same finding. No threshold is set: coverage is printed in the test job and nothing more, because a gate nobody can pass is worse than a number somebody reads. `--cov` is deliberately not in `addopts`, so a local `pytest tests` stays the fast path, and the config lives in `[tool.coverage]` in `pyproject.toml`.
- A `lint` job in `.github/workflows/ci.yml` runs `scripts/check_flake8_baseline.py` on every push and pull request. The test job runs the suite on `windows-latest` / 3.12.
- The OS badge is checked now, not decorative: a `smoke` matrix in `ci.yml` runs the full suite on `ubuntu-latest` and `macos-latest` with Qt offscreen — Linux needs five system libraries (`libegl1`, `libgl1`, `libxkbcommon0`, `libdbus-1-3`, `libfontconfig1`) that the runner image does not ship whole, macOS needs nothing beyond the runner. Same locked dependency set as the test job, so a platform-specific regression in the locked tree cannot hide.
- pre-commit is wired up for the first time. The config existed but nothing ran it: `pre_commit` was not installed, `.git/hooks` held only the two ref-tracking hooks, and CI had no lint step. It is installed now, and the config was repaired while doing it -- `black` was listed twice (once rewriting, once with `--check`, which cannot both be wanted) and it is removed rather than fixed, because `black --check` rejects 44 of the 156 files it reads and wants trailing comments moved onto their own line inside parentheses, against this repo's documented style. Enabling it would reformat the tree as a side effect of the next unrelated commit or fail on whatever file a contributor touches; that is a decision to take deliberately, and the config says so in place. The flake8 plugins `select = B,C` asks for are installed by the `dev` extra so local, CI and the hook all check the same rule set -- `tests/test_utils/test_lint_config_consistency.py` asserts they agree and that `pyproject.toml` does not grow a `[tool.flake8]` table back.
- `end-of-file-fixer` fixed 11 files with no final newline and trimmed two with trailing blank lines. Note for whoever runs pre-commit on this checkout: the hook opens every file `rb+`, and on the G: volume used here it fails about one run in two with a `PermissionError` on a different file each time, even though all 157 `.py` files under `anylabeling/` open `rb+` 20 times out of 20 in a loop. It is the volume, not the config.
- Three scripts with a shebang were not marked executable (`build_and_publish_pypi.sh`, `build_executable.sh`, `generate_release_notes.py`); `git update-index --chmod=+x` fixes the mode. The hook then caught the same thing on `scripts/check_flake8_baseline.py` the moment it was first committed, which is the gate doing its job.
- Releases have a pipeline now: `.github/workflows/release.yml` turns a pushed `v*` tag into a GitHub Release. A cheap first job fails fast when the tag is not `v` + `anylabeling.app_info.__version__` or the newest CHANGELOG heading is not that tag — `scripts/generate_release_notes.py` is the validator, reused verbatim, not reimplemented. The test job gates the builds; three build jobs (win-cpu / linux-cpu / macos) run `scripts/build_executable.sh` and attach every artifact plus a `SHA256SUMS.txt`; the publish job regenerates the notes and `gh release create --verify-tag` publishes everything with `contents: write` as the only extra permission. The existing `v1.0.0-beta.1` tag predates the workflow, so its first run needs either a re-push of that tag or the next version bump.
- The black decision got made, in the direction the config could not make alone: one dedicated reformat commit ran black 26.5.1 over `anylabeling tests scripts tools` — 42 files (41 tracked, +471/−441, the tree got smaller), with the two files a parallel refactor batch had in flight excluded from the run so its byte-for-byte verification stays intact; pre-commit settles those when the batch lands. The hook is back in `.pre-commit-config.yaml`, exactly once, rewriting rather than `--check`, pinned to `26.5.1` — the same version now pinned as `black==26.5.1` in the `dev` extra, because black's output style moves between releases and a moving formatter would churn the tree on every upgrade. The flake8 ratchet stayed green and improved 3 entries (`batch.py` E303, `auto_labeling_ui.py` E128×2/E227 — left frozen conservatively, the next `--update` picks them up); the full suite stayed at 739 passed / 1 skipped.
- `tests/test_utils/test_fork_naming.py` scans every text file in the tree for the bare upstream command name and asserts one console script, so docs and help text cannot drift back to a command this install does not provide. The names it deliberately ignores are written down in the file.

## `v1.0.0-beta.1` (Sep 23, 2026)

### ✨ New Features

- Review state per image: `review_state` (`unchecked` / `confirmed` / `rejected`) plus `reviewed_at`; `checked` is kept in sync for existing consumers. New "需返工" filter, progress count, and `mark_rejected_and_next` (Ctrl+Shift+K).
- Provenance per shape: `source` (`human` / `model` / `unknown`) and the producing model name, stamped at all three places predictions are applied.
- `model_version` alongside it: a SHA-1 prefix of the loaded weights file, so boxes drawn before a retrain are still recognisable as older when the loop reuses one YAML and one `best.onnx` path. Only compared when both sides have one — shapes recorded before this field exists are never made stale by it.
- "旧轮模型框盘点" smart-tool: groups stale model boxes by producing model, offers per-row deletion; locked, unattributed and since-edited boxes are never deleted, and affected label files are snapshotted to `.label_backups/<stamp>/` first.
- Reproducibility: dataset `manifest.json` (per-file content hashes, split assignment, classes, seed) and `run_meta.json` per finished run (weights hash, exact arguments, manifest hash, metrics).
- Run history table (`训练 → 实验历史`): every recorded run with its metrics, seed, dataset sizes and hash prefixes, newest first, joined to the iteration round that produced it; CSV export. Runs older than `run_meta.json` are reported as a count instead of blank rows.
- Snapshot restore (`智能工具 → 11. 从备份恢复标注`): lists the runs under `.label_backups`, writes the chosen one back over the labels it came from, and snapshots what it replaces first — so picking the wrong run is itself reversible. The image open in the canvas is skipped while unsaved work is pending.
- Split seed pinned per dataset in `.jllabel/project.json`, so consecutive rounds are comparable.
- Pose and classification loop-back: `yolo26_pose` reuses the training pose config; new `yolov8_cls` adapter returns confirmable whole-image suggestions instead of shapes.
- Active-learning set: threshold calibration, dataset analysis, missed-label scan, iteration dashboard, review-jump queue, label propagation, duplicate archiving, training advice, template pre-labeling.

### 🛠 Improvements

- Custom model limit raised from 5 to 30; models produced by the loop are pinned and never evicted.
- Fork-owned version reported in the window title, status bar, `version` and `checks`, while keeping the upstream name and source visible as required by its GPL terms.
- Dataset build directories no longer collide within the same second; the app offers to reclaim old dataset copies. Label backups got the same treatment, so two snapshots taken in one second stay two runs.
- Deleting stale boxes from the image open in the canvas is a real undo step now: the batch is applied through the canvas snapshot history instead of reloading the file, so one Ctrl+Z brings every deleted box back.
- Translation scripts walk the catalogs that actually exist instead of a fixed four-language list, `language` other than `zh_CN` warns instead of being ignored, and both get-started pages now state that this build ships one catalog.

### 🐛 Bug Fixes

- `import_image_folder` cleared the file list but not `fn_to_index`, and `_apply_file_sort` reordered rows without rebuilding it, so a path could resolve to the wrong row and review state could be read or written against a different image.
- Every smart-tool result dialog raised `NameError` (undefined `QtGui`), and the stale-model audit had an unimported name; both were unreachable for tests because nothing constructed the widget or ran an action.
- `save_config` swallowed the traceback; the training dialog reported "saved successfully" after a failed write; custom-model add/remove ignored persistence failures; `app.log` never rotated and the faulthandler handle could be collected.
- Two review-navigation loops rebuilt the whole file list per scanned row.
- 数据体检 ranked the review queue and then kept only its first 50 entries, and 智能复核 navigated that truncated list: a folder with hundreds of uncertain images reported `1/50` and then "end of queue" while candidates were still waiting. The queue is now complete and the cap lives in the dialog, which states each category's real total and no longer counts review priorities among the problems found.
- Three strings reached a widget without `tr()` (a recommended-model chip's tooltip and both "Skip empty labels" help texts), so nothing could translate them. Wrapping them changes no visible text: `zh_CN.ts` has no Chinese `<source>` entries, which is also why writing fork text in Chinese and passing it through `tr()` is safe here.
- Both translation scripts listed four languages while this checkout ships one catalog, so the documented `compile_languages.py` command died on the missing `.ts` files; the get-started pages advertised an interface language that cannot be selected. `language` in the config was read by the model and the trainer but silently ignored by the translator, which always loaded `zh_CN`.
- Packaging: `.desktop` `Exec` pointed at a non-existent script; linux/macos specs still bundled deleted `configs/bert` and `configs/ram`.
- CI: `tests/test_settings` crashed the process when run on its own (a test created a non-GUI `QCoreApplication` that later widget tests reused).

### 🔗 CI / Tooling

- `.github/workflows/ci.yml` runs the full suite on pushes to `main` and pull requests.
- README and both doc sets now describe only what this build can do, guarded by `tests/test_utils/test_readme_claims.py` (phantom model families, pruned capability claims, local link resolution, upstream credit).
- `tests/test_labeling/test_widget_wiring.py` constructs the real `LabelingWidget` for the first time, so advertised shortcuts, menu entries and action enablement are verified rather than assumed.
- That fixture's parent stub is a `QMainWindow` now, and it stops the debounced auto-save timer on teardown: the timer used to survive the test and raise inside whichever test happened to pump events next (a 1 s model-check timeout took the blame).

---

# X-AnyLabeling Changelog

## `v4.0.0-beta.13` (Jul 12, 2026)

### 🐛 Bug Fixes

- Keep CUDA 12 executable builds on a compatible ONNX Runtime GPU release.
- Validate that Windows CUDA 12 artifacts do not link against CUDA 13 libraries.
- Restore Linux release tests and builds with the required runtime dependencies.

### 🛠️ Improvements

- Add Linux and Windows CUDA 12 executables to automated releases.
- Publish Python packages through PyPI Trusted Publishing.
- Update and pin release workflow actions for reproducible builds.

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v4.0.0-beta.12` (Jul 11, 2026)

### 🚀 New Features

- Add bottom-left canvas controls for label opacity and image brightness and contrast.
- Add a collapsible display adjustment panel with synchronized controls. (#1405,#1406)
- Add a drag rotation handle for rotated boxes. (#1407)
- Show the valid image count for the selected training task.

### 🛠️ Improvements

- Automate cross-platform executable builds and GitHub releases.
- Remove legacy tools and reorganize tests and documentation.

### 🌟 Contributors

A total of 2 developers contributed to this release.

Thank @lovejoohero0228, @CVHub520

## `v4.0.0-beta.11` (Jun 28, 2026)

### 🚀 New Features

- Add brush editing for polygon refinement with paint and erase controls, configurable behavior, and stroke-level undo and redo. (#1401)
- Add per-shape locking to protect annotation geometry and deletion while preserving selection and metadata editing.
- Add interactive group selection and movement with safe group copy, paste, and deletion.
- Improve selection for overlapping and nested shapes by prioritizing nearby vertices and editable edges.
- Prompt users to keep or skip out-of-bounds OBB annotations during YOLO OBB export. (#1402)

### 🐛 Bug Fixes

- Stabilize label review navigation when annotations change and show review progress. (#1403)
- Default to the XCB platform plugin in WSL Wayland environments.
- Replace shell command execution in translation compilation with checked subprocess invocation. (#1398)
- Detect available Qt translation compilers and surface compilation failures.
- Refine the brush editing workflow and undo history.

### 🛠️ Improvements

- Align the Black configuration with the supported Python version and consolidate exclusions.

### 🌟 Contributors

A total of 4 developers contributed to this release.

Thank @tuanaiseo, @lovejoohero0228, @quitmeyer, @CVHub520

## `v4.0.0-beta.10` (Jun 20, 2026)

### 🚀 New Features

- Add YOLO26 TrackTrack model support for detection, segmentation, pose, and oriented bounding box tracking.

### 🐛 Bug Fixes

- Support brightness and contrast adjustment for 16-bit grayscale images. (#1396)
- Update the bug report template checks command. (#1397)

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v4.0.0-beta.9` (Jun 19, 2026)

### 🚀 New Features

- Add PP-OCRv6 local OCR model support.
- Add SCRFD face estimation support. (#1393)
- Add checked-status filtering for image search. (#1394)

### 🐛 Bug Fixes

- Enforce TLS verification for auto-labeling model downloads.
- Avoid NumPy 2D cross product crashes when detecting line edges. (#1395)

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v4.0.0-beta.8` (Jun 15, 2026)

### 🚀 New Features

- Add an AI-assisted video annotation workflow to the video classifier. (#1224,#1330)
- Add vertex eraser support for polygon and line strip annotations. (#892)
- Support temporary Space-drag panning while drawing shapes. (#1368)
- Add PaddleOCR-VL-1.6 API model support.
- Improve Chatbot vision capability detection for supported models.

### 🐛 Bug Fixes

- Stabilize object selection and label rendering in the label list. (#1385)
- Preserve group IDs after auto-labeling results are applied. (#1376)
- Prevent SAM2 interactive segmentation from leaking GPU VRAM during CUDA inference.
- Match auto-labeling model dropdown searches against display names. (#1379)
- Skip partially out-of-bounds OBB exports in label conversion. (#1383)
- Pass all Ultralytics training parameters while excluding internal-only X-AnyLabeling options.
- Align ONNX dependency checks with the package requirements to avoid false missing-package errors.
- Surface Anthropic model fetch errors in Chatbot and honor request timeouts.
- Restore Chatbot model refresh behavior and improve dark mode controls.

### 🛠️ Improvements

- Add LocateAnything grounding documentation and references. (#1382)
- Clarify Rex-Omni GPU selection behavior for the vLLM backend.
- Add bottom spacing to the progress dialog cancel button.

### 🌟 Contributors

A total of 4 developers contributed to this release.

Thank @GIGIGIGIbaby, @Snag9311, @Shuwei Ji,  @CVHub520

## `v4.0.0-beta.7` (May 14, 2026)

### 🐛 Bug Fixes

- Guard stale selections during shape deletion to prevent canvas crashes. (#1369)
- Prevent annotation visualization popup crashes when no image is loaded.
- Keep the left toolbar frame full height without stretching toolbar icons.

### 🛠️ Improvements

- Align label dialog controls, shortcut hints, and input states across light and dark themes.
- Soften digit shortcut combo hover styling for better visual consistency.

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v4.0.0-beta.6` (May 13, 2026)

### 🚀 New Features

- Add a confirmation step before starting PaddleOCR parsing and update the PaddleOCR documentation to match the confirmed import workflow.

### 🐛 Bug Fixes

- Add horizontal scrolling for overflowing auto-labeling toolbar controls. (#1360)
- Export overview CSV files with UTF-8 BOM to prevent garbled filenames in spreadsheet applications. (#1359)

### 🛠️ Improvements

- Polish PaddleOCR dark mode across block editors, preview canvas, result action icons, table editing, and LaTeX preview rendering.
- Align sidebar, file list, shape dialog, and Ultralytics training dialog scroll styling with the current application theme.

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v4.0.0-beta.5` (Apr 26, 2026)

### 🚀 New Features

- Add client-side SAM 3 ONNX support for text-grounded segmentation. (#1232)
- Add HEIC and HEIF image loading support.
- Add configurable Qt image allocation limit via `--qt-image-allocation-limit` flag.

### 🐛 Bug Fixes

- Replace `eval` with `ast.literal_eval` in label dialog to prevent arbitrary code injection.
- Scope SSL verification bypass to model downloads only to avoid unintended side effects.
- Avoid shared mutable defaults in shape and label dialogs.
- Guard `loaded_model_config` reads and writes with a lock to prevent race condition.
- Connect QThread `finished` to `deleteLater` in model manager to prevent use-after-free.
- Load an independent config copy in `fetch_models_async` to eliminate shared-dict race with main thread.
- Move non-video batch inference loop to QThread to prevent UI freeze.
- Call `quit()` on `pre_inference_thread` in GroundingSAM2 unload to actually stop the thread.
- Disconnect `scan_finished` signal before EXIF cleanup to prevent a stale signal from killing a new scan.
- Launch Ultralytics training via a stable worker subprocess. (#1354)
- Return `(None, None)` from `imread_unicode` when `imdecode` fails on corrupt images.
- Guard VOC XML `size` and object `name` element lookups against missing elements.
- Correct "diccicult" typo to "difficult" in MOT export shape lookup.
- Guard all `classes.index` calls against unknown labels to prevent `ValueError`.
- Unpack shape in canvas label-text loop to fix stale variable reference in `paintEvent`.
- Guard `shapes_backups` access in `mouseReleaseEvent` against empty list and out-of-range index.
- Guard `scale_fit_window` and `scale_fit_width` against zero pixmap or widget dimensions.
- Replace `textChanged` disconnect/connect with `QSignalBlocker` to prevent `TypeError` on first load.
- Raise on download failure in `get_model_abs_path` instead of silently returning `None`.
- Remove always-false membership loop in provider config handling.
- Clear stale PPOCR output files before each export run to prevent data accumulation.
- Log unhandled settings keys instead of silently ignoring them.
- Log skipped files in async EXIF scan instead of silently swallowing exceptions.
- Correct remote server debug log to use `current_model_id` and fix `parameters` typo.

### 🛠️ Improvements

- Speed up canvas `fill_drawing` path by replacing `deepcopy` with a shallow copy.
- Avoid redundant base64 decode-encode round-trip in `LabelFile.load`.
- Speed up temporary video handling by using `shutil.copy2` instead of a full in-memory read.
- Add GeCo2 counting example and usage documentation. (#1293)
- Add troubleshooting tip for SOCKS proxy error in the Chatbot FAQ.
- Harden PyInstaller executable build script and normalize repository line endings.

### 🌟 Contributors

A total of 2 developers contributed to this release.

Thank @CVHub520, @fhong-jpg

## `v4.0.0-beta.4` (Apr 21, 2026)

### 🚀 New Features

- Add PaddleOCR document parsing workspace with an official API client mode and asynchronous API job parsing.
- Add TensorRT inference backend support for auto-labeling. (#1343)
- Add annotation check status workflow for labeling quality review. (#1340)
- Add option to train Ultralytics models with checked files only. (#1340)
- Add annotation visualization export for images and videos.
- Add YOLO11 and YOLO26 SAHI support for auto-labeling. (#1321)
- Add file list copy actions and a recent menu action for reopening the last directory. (#1338,#1346)
- Add Japanese UI localization support and Japanese language selection in the labeling widget. (#1331,#1332)

### 🐛 Bug Fixes

- Keep standard models visible in the remote server model dropdown.
- Support custom PPOCR recognition dictionaries in auto-labeling. (#1344)
- Preserve LaTeX arrow commands in PaddleOCR formula previews.
- Keep the PaddleOCR export dialog open when canceling on macOS.
- Prevent PyQt6 attribute panel crashes in the label widget. (#1337)
- Preserve provided image filenames when VOC filenames lack extensions. (#1334)
- Force zlib resource compression for Windows translation loading. (#1332)

### 🛠️ Improvements

- Package macOS PyInstaller release archives with checksums. (#1285)
- Align rotated-box documentation and optimize keyboard rotation repaint behavior. (#1333)
- Update setup guides to install beta pre-release packages by default with quoted optional dependency extras for zsh compatibility.
- Add repository line-ending attributes to keep source, docs, and config files on LF while preserving CRLF for Windows scripts.

### 🌟 Contributors

A total of 3 developers contributed to this release.

Thank @CVHub520, @kame3mikan3, @tribf

## `v4.0.0-beta.3` (Mar 27, 2026)

### 🚀 New Features

- Add a unified settings panel for centralized application configuration. (#1226)
- Add 3D cuboid shape annotation generated from rectangles. (#162)

### 🐛 Bug Fixes

- Prevent crashes when triggering auto-labeling shortcuts with no model loaded.
- Resolve `uv sync` extra conflicts and align supported Python versions. (#1325)

### 🛠️ Improvements

- Batch shape visibility updates and disable visibility toggles while filters are active.
- Clarify model re-download troubleshooting in the Chinese FAQ. (#1328)

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v4.0.0-beta.2` (Mar 06, 2026)

### 🚀 New Features

- Add index search mode for targeting images by their position in the file list.
- Introduce a shape converter dialog for shape transformation workflows.
- Add support for creating line strips when drawing starts outside pixmap boundaries. (#1144)

### 🐛 Bug Fixes

- Bind auto-labeling inference results to their source image to prevent stale apply.
- Update attribute reset logic to follow the last shape on the canvas. (#1316)
- Improve pose config loading validation and error handling in label conversion.
- Update file dialog modes to use `QtWidgets` enumerations for better PyQt6 compatibility.
- Defer GUI imports and lazily resolve config/data paths to fix `--work-dir` startup issues.
- Prevent canvas painting when the current image is null. (#391)

### 🛠️ Improvements

- Add PyInstaller spec files under `packaging/pyinstaller/specs`.
- Enhance MSVC runtime DLL collection in Windows PyInstaller specs.
- Update development dependencies.
- Add a FAQ troubleshooting note for `ReadProcessMemory` startup errors.

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v4.0.0-beta.1` (Mar 01, 2026)

### 🚀 New Features

- [Breaking] Migrate the GUI framework from PyQt5 to PyQt6 across the application, including QtWebEngine and scoped-enum API updates. (#1087)
- Add appearance theme support with `System`, `Light`, and `Dark` modes. (#315,#741,#937)
- Add class filter dialog support in auto-labeling for multi-model workflows (YOLO family, RT-DETR, RF-DETR, DAMO YOLO, YOLO-NAS, and related models). (#905)
- Add cancellable model download with real-time progress display in the auto-labeling panel. (#40)
- Add Shift-key snapping for horizontal/vertical line segments when drawing `line` and `linestrip`. (#1312)
- Add quadrilateral shape annotation (`T`) and quadrilateral import/export support for PPOCR label conversion. (#705)
- Add brush polygon drawing mode with configurable point distance. (#799)
- Add double-click label editing support in Edit Mode.

### 🐛 Bug Fixes

- Fix InternImage configuration type mapping (`internimage_cls`).
- Fix video frame extraction progress hangs caused by unconsumed ffmpeg output pipes. (#1309)
- Fix rotation-shape clipping behavior to keep geometry within pixmap boundaries. (#1268)
- Fix incorrect display of `h` and `w` of shape properties in canvas.

### 🛠️ Improvements

- Optimize image switching performance for large datasets. (#757)
- Reorganize PyInstaller assets into `packaging/pyinstaller/` and improve ONNXRuntime runtime bootstrapping for packaged builds.
- Update packaging/dependency configuration for PyQt6-era environments and remove legacy `requirements*.txt` files.

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v3.3.10` (Feb 15, 2026)

### 🚀 New Features

- Respect auto_highlight_shape and disable wheel editing when it is enabled (wheel rectangle editing)
- Add handling for custom attribute types (group_id, lineedit) in label widget

### 🐛 Bug Fixes

- Add Meta class with widget configuration for YOLO26 variants (#1280)
- Resolve export only from current folder when images are in multiple subfolders (#1303)
- Improve error handling in availability checks for torch, cuda, and mps (#1294)
- Resolve UI freeze when copying app info in packaged exe (about dialog)
- Deduplicate group_id options in attribute combo (#1304)
- Fix several bugs about the update of attributes panel (#1301)
- Fix paint assertion crash issues (#1296)
- Fix occasional GUI crashes when switching modes after automatic labeling
- Fix GUI crashes due to empty self.points in shape.py (#1295)
- Fix typo (#1299)

### 🛠️ Improvements

- Add FAQ entry regarding errors when using precompiled EXE for Ultralytics training (#1100)
- Add example of group_id and lineedit attributes in classification shape-level README

### 🌟 Contributors

A total of 6 developers contributed to this release.

Thank @Jingnan-Jia, @ParshikovMM, @hehuaiyu, @jk4e, @yuliangzhong, @CVHub520

## `v3.3.9` (Feb 02, 2026)

### 🚀 New Features

- Add PP-DocLayoutV3 and PaddleOCR-VL-1.5 model support (#1226)

### 🐛 Bug Fixes

- Fix label decoding issues in Grounding DINO series models (#1286)
- Clear image description when loading unlabeled images

### 🛠️ Improvements

- Update README and model zoo documentation
- Add license notice for Ultralytics under AGPL-3.0

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v3.3.8` (Jan 28, 2026)

### 🚀 New Features

- Add YOLO26 seg/pose/obb model (#1226)

### 🌟 Contributors

A total of 2 developer contributed to this release.

Thank @iPengXPro, @CVHub520

## `v3.3.7` (Jan 25, 2026)

### 🚀 New Features

- Add automatic skip detection support for batch processing mode in PPOCR models (#687)
- Introduce Compare View feature for side-by-side image comparison, enhancing usability for tasks such as infrared/visible fusion, mask preview, and super-resolution (#1269)

### 🌟 Contributors

A total of 2 developer contributed to this release.

Thank @xy200303, @CVHub520

## `v3.3.6` (Jan 24, 2026)

### 🚀 New Features

- Add Rex-Omni unified vision model support (#1223)
- Add YOLO26 object detection model (#1226)
- Add option to export existing model or retrain when a model is detected in the project directory (#1226)
- Add '--work-dir' parameter for configurable working directory (#1226)
- Persist remote server settings in user config (#1267)
- Streamline argument handling for multiprocessing support in PyInstaller builds (#1180)

### 🐛 Bug Fixes

- Fix the problem with the display of the title progress

### 🛠️ Improvements

- Add FAQ entry for YOLO-Pose keypoint ID issue (#1270)
- Update installation guides

### 🌟 Contributors

A total of 2 developers contributed to this release.

Thank @zhixuwei, @CVHub520

## `v3.3.5` (Jan 11, 2026)

### 🚀 New Features

- Introduce powerful file search feature with text, regex, and attribute filtering support (#1264)
- Enhance shape info display with difficult shape highlighting and double-click navigation in overview dialog (#1264)
- Apply dashed line style for difficult shapes in shape and canvas rendering (#1264)
- Integrate mask opacity configuration into canvas rendering
- Add semi-transparent mask rendering for shapes with toggle support (Ctrl+M)

### 🐛 Bug Fixes

- Suppress stderr output and filter command-line arguments
- Refresh canvas immediately after label modification

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v3.3.4` (Jan 01, 2026)

### 🚀 New Features

- Add support for SAM3-based "Track Concepts" with both Visual and Text Prompts (#1258)
- Add file_list_checkbox_editable option to control checkbox editability in file list (#678)
- Add project_readonly configuration to control project editability (#1242)
- Enhance remote server dialog for URL and API key configuration (#1241)
- Add support for modifying the remote_server URL (#1241)
- Add support for verifying PTH and PT model validation (#1241)
- Add double-click functionality to copy label text to clipboard (#1236)

### 🐛 Bug Fixes

- Fix Windows image file counting bug by using pathlib (#1258)
- Normalize task type selection and add warnings for unknown task types (#1253)
- Ensure image is set in navigator dialog when visible (#1220)
- Resolve resource loading failure in venv editable install mode (#1250)
- Handle None value for replace parameter in AutoLabelingResult

### 🛠️ Improvements

- Update user guide with note on YOLO label file directory placement (#1259)
- Update user guide to include new SAM3 video tracking features (#1258)

### 🌟 Contributors

A total of 2 developers contributed to this release.

Thank @Atletico1999, @CVHub520

## `v3.3.3` (Dec 07, 2025)

### 🚀 New Features

- Add cropping mode for improved small object detection in SAM (#1193)

### 🐛 Bug Fixes

- Clarify frame extraction interval label to avoid ambiguity

### 🛠️ Improvements

- Remove deprecated method from remote server

### 🌟 Contributors

A total of 2 developers contributed to this release.

Thank @fystero, @CVHub520

## `v3.3.2` (Dec 01, 2025)

### 🚀 New Features

- Add support for SAM3 model with text and visual promptable segmentation (#1207)
- Add concurrent batch processing support for chatbot (#1222)
- Enable EXIF scanning option in configuration and update label widget to utilize it (#1220)
- Add depth calibration feature for Depth Anything model (#1201)

### 🐛 Bug Fixes

- Improve wheel event handling in chat messages (#1222)
- Handle missing annotations for frames and log warnings in label converter (#1219)
- Improve progress dialog updates and error handling during frame extraction (#1219)
- Prevent unnecessary updates to navigator shapes when dialog is not visible (#1220)
- Resolve list index out of range and timeout issues in chatbot
- Correct indentation for data file loading logic in ultralytics dialog (#1216)

### 🛠️ Improvements

- Enhance FrameExtractionDialog layout and input styling for improved user experience (#1219)
- Increase API timeout to 300s for chatbot (#1222)

### 🌟 Contributors

A total of 2 developers contributed to this release.

Thank @wangxiaobo775, @CVHub520

## `v3.3.1` (Nov 10, 2025)

### 🚀 New Features

- Support dynamic label deletion from unique label list via Label Manager (#1191)
- Add remote server model support for text-prompted batch processing

### 🌟 Contributors

A total of 1 developers contributed to this release.

Thank @CVHub520

## `v3.3.0` (Nov 07, 2025)

### 🚀 New Features

- Add real-time instance segmentation model based on RF-DETR-Seg (#1184)
- Add support for remote inference via X-AnyLabeling-Server (#1175)
- Add shape visibility control in Label Manager for showing/hiding labels on canvas (#1172)
- Add CLI support for conversion tasks (#980)
- Add batch operations for video frame sequences (thanks @ltnetcase) (#1128)
- Add multi-label classification mode support
- Add device support for RTMDet and RTMO models
- Support customizable rotation increments (#1174)
- Support customizable attribute label colors in config file (#1178)
- Auto refresh model list and remove uninstalled models in chatbot
- Reset flags from current data on dialog initialization

### 🐛 Bug Fixes

- Preserve existing color and opacity for labels in LabelModifyDialog (#1185)
- Resolve group ID persistence across undo/edit operations (#1149)
- Ensure shapes are stored after label updates in the labeling widget (#1149)
- Handle non-ASCII paths in VOC annotation export on Windows (#1181)
- Enhance ONNX model validation with error handling and timeout management (#1180)
- Implement subprocess integrity check for ONNX models
- Apply sigmoid to logits for proper threshold comparison in GroundingSAM2 (thanks @tiucamaria) (#1179)
- Restore PyQt5 support for macOS
- Improve bounding box precision by removing int() truncation (thanks @xusuyong) (#1159)
- Fix empty keypoints check in RTMDet pose models

### 🛠️ Improvements

- Add detailed explanation on copy-paste functionality for annotation objects (#1183)
- Add troubleshooting information for ImportError related to expat module (#1158)
- Fix typos in README files
- Fix image panel resizing and simplify background styling in classifier dialog
- Add requests package to dependencies

### 🌟 Contributors

A total of 6 developers contributed to this release.

Thank @Liyulingyue, @ltnetcase, @tiucamaria, @xusuyong, @jk4e, @CVHub520

## `v3.2.6` (Oct 02, 2025)

### 🚀 New Features

- Add support for using backspace key to delete the last vertex when creating polygon and line shapes (#1151)
- Introduce DEIMv2 real-time object detector
- Add the ability to process all images at once with the Florence-2 model (#1152)
- Add max_det parameter for maximum detections in YOLO model (#1142)

### 🐛 Bug Fixes

- Enable auto_use_last_gid for digit shortcuts and reset on image switch (#1149)

### 🛠️ Improvements

- Add troubleshooting steps for exporting empty Mask images (#1153)
- Update rotation increments to radians and format degree display

### 🌟 Contributors

A total of 4 developers contributed to this release.

Thank @lhj5426, @sckiyo, @Vlad188-1, @CVHub520

## `v3.2.5` (Sep 29, 2025)

### 🚀 New Features

- Add Group ID Manager feature with Ctrl+Shift+G shortcut for auto-using last group ID (#1143)

### 🐛 Bug Fixes

- Fix image folder loading delays by implementing async EXIF detection (#e4bf7f6)

### 🛠️ Improvements

- Update Group ID Manager section in user guide (#1146)
- Add --qt-platform argument for improved performance on Fedora KDE environments (#1145)

### 🌟 Contributors

A total of 2 developers contributed to this release.

Thank @vodnikss, @CVHub520

## `v3.2.4` (Sep 28, 2025)

### 🚀 New Features

- Introduce a dedicated multi-class image classifier with a streamlined workflow (#480)
- Add support for Ultralytics image classification tasks
- Add support for deleting group IDs from objects (#1141)
- Add checkboxes for description and label visibility control (#1139)
- Add loop select labels functionality for sequential shape selection (#1138)
- Add support for drawing rectangle shapes outside canvas with auto-clipping (#1137)
- Add radio button support for attribute selection (#1135)
- Add an option to skip empty label files when creating YOLO datasets and update the UI (#1131)
- Add an option to preserve existing annotations when uploading YOLO labels (#1125)
- Add custom provider support for the chatbot and enhance the model dropdown feature
- Add cross-widget reference support in VQA dialog using `@widget_title` syntax
- Add support for paths wrapped in quotes for models and data
- Add select/deselect all shapes feature (#1092)
- Implement keyboard shortcuts for image navigation (A/D)

### 🐛 Bug Fixes

- Resolve inconsistent attribute behavior after shape creation and switching (#1134)
- Ensure linestrip's vertex is drawn regardless of selection state (#1134)
- Resolve issue where CUDA device count returns 0 after model export in Ultralytics training (#1126)
- Fix Windows path separator error in `train_script.py`
- Fix inconsistent shape order when using existing shapes for recognition in PP-OCR
- Fix issue where group ID info was only updated after successful modification

### 🛠️ Improvements

- Auto-update the attributes panel after shape creation (#1134)
- Improve shape selection logic for point and line types to enhance user interaction (#1134)
- Enhance shape selection for partial re-recognition in PP-OCR (#1113)
- Enhance AI prompts in VQA with cross-component and annotation data references
- Preserve original shape properties when skipping detection in OCR (#1116)

### 🌟 Contributors

A total of 3 developers contributed to this release.

Thank @sckiyo, @Vlad188-1, @CVHub520

## `v3.2.3` (Sep 14, 2025)

### 🚀 New Features

- Implement EXIF orientation processing for images during import, with user feedback and backup features
- Add mask fineness control slider for SAM series models to adjust segmentation precision (#1114)
- Add Re-recognition feature for PP-OCR models (#1113)
- Add support for PP-OCRv5 model (#1113)
- Add copy coordinates to clipboard feature
- Add circle to polygon transform feature (#1112)
- Add Navigator feature for high-resolution image navigation and zoom control (#1102)
- Add refresh button to sync data with main window and display success popup for VQA Dialog
- Enable shapes field export for VQA Dialog

### 🐛 Bug Fixes

- Fix 'gbk' codec decode error on windows during Ultralytics traning (#1115)
- Prevent deleting label file when "Keep Previous Annotation" is enabled by showing a warning to disable it first
- Fix Chinese character path support in crop image saving
- Enable ONNX Runtime library linking in x-anylabeling-*-gpu.spec
- Fix first image showing old dataset data after refresh in VQA dialog

### 🛠️ Improvements

- Enhance window title to display current image progress (#936)
- Adjust label bounding box calculations for improved text positioning
- Improve circle label positioning to center display
- Streamline color retrieval by using parent method for RGB values in LabelModifyDialog
- Update field count in VQA ExportLabelsDialog for accurate table height calculation and make table items non-editable
- Enhance button styles and dialog layout for improved user experience
- Enhance Ultralytics train/val dataset split with true randomization (#1095)
- Optimize the experience of adjusting the shape (#1094)

### 🌟 Contributors

A total of 6 developers contributed to this release.

Thank @Einstellung, @lhj5426, @sckiyo, @xiaomaxiao, @zhixuwei, @CVHub520

## `v3.2.2` (Aug 31, 2025)

### 🚀 New Features

- Support batch editing for multiple shapes (#1084)
- Introduce AI Assistant for VQA
- Add prompt template management to VQA
- Enhance VQA dialog with a new UI including sidebar toggles, streamlined navigation controls, improved page navigation, loading indicators, and updated button styles

### 🐛 Bug Fixes

- Fix issue with dragging and moving the image (#1088)

### 🛠️ Improvements

- Optimize SAM inference memory management (#1086)

### 🌟 Contributors

A total of 4 developers contributed to this release.

Thank @jsolobang, @zhaoruibing, @zhixuwei, @CVHub520

## `v3.2.1` (Aug 23, 2025)

### 🚀 New Features

- Add support for showing/hiding shape attributes on the canvas (#1076)
- Add functionality to save training logs with timestamp upon dialog closure (#1077)

### 🐛 Bug Fixes

- Skip validation for auto-labeling special constants
- Prevent closing UltralyticsDialog during active training session (#1077)
- Improve WSL2 detection for image file handling in UltralyticsDialog (#1077)
- Add UTF-8 encoding to file opening in validate_data_file function (#1077)
- Resolve Windows multiprocessing and matplotlib segfault issues

### 🌟 Contributors

A total of 2 developer contributed to this release.

Thank @FreemanTang, @CVHub520

## `v3.2.0` (Aug 19, 2025)

### 🚀 New Features

- Introduce Auto Training Platform for Ultralytics tasks (Detect/Segment/OBB/Pose)

### 🌟 Contributors

A total of 1 developers contributed to this release.

Thank @CVHub520

## `v3.1.2` (Aug 16, 2025)

### 🚀 New Features

- Introduce Auto Mask Decode (AMD) mode for continuous point tracking (#1060)
- Add new RF-DETR models (medium, small, nano) and fix input width typo in configuration files (#1069)
- Enhance range selection for group ID modification with new input fields and validation (#1035)
- Add support for MM-Grounding-DINO annotations upload

### 🐛 Bug Fixes

- Update error message for label validation to specify 'exact' in config file (#1064)
- Fix issues when drawing rectangular boxes (#1063 by zhixuwei)
- Add try-except for mask_to_polygons for supervision version compatibility (#1055 by adarshs)
- Improve segmentation handling by filtering invalid entries and avoiding duplicate points in polygon mode (#1032)
- Resolve KeyError when importing files via drag and drop (#1030)
- Enhance image saving logic to handle non-ASCII paths and improve multiprocessing handling in frozen environments (#1021)
- Improve crop region validation and handle empty cropped images with warnings (#1021)
- Emit model_loaded signal even if loading custom model configuration fails
- Update frame ID extraction logic to handle underscores and non-digit cases (#1020)

### 🛠️ Improvements

- Correct variable name from 'has_vasiable' to 'has_visible' for accurate keypoint processing
- Simplify toggle button text for clarity in label and shape information display
- When looping through shapes, display their fill colors (#1025 by zhixuwei)

### 🌟 Contributors

A total of 3 developers contributed to this release.

Thank @zhixuwei, @adarshs, @CVHub520

## `v3.1.1` (Jul 05, 2025)

### 🚀 New Features

- Add customizable field export options for VQA dialog
- Add ability to adjust the visible area of the image by dragging the mouse (#1019)

### 🐛 Bug Fixes

- Fix VQA keyboard shortcut (Ctrl+Q → Ctrl+1)

### 🌟 Contributors

A total of 2 developer contributed to this release.

Thank @zhixuwei, @CVHub520

## `v3.1.0` (Jul 02, 2025)

### 🚀 New Features

- Support `RMBG v2.0` model for image matting
- Add output_path parameter to COCO label converter methods for custom output paths
- Add real-time result preview for matting and depth estimation tasks
- Add GUI support for uploading custom label classes (#988)
- Add rectangle scaling and edge adjustment with mouse wheel support (#989)
- Add automatic update check on startup
- Add Visual Question Answering tool

### 🐛 Bug Fixes

- Improve error handling and logging for annotation export and upload processes (#974)
- Fix annotation_id increment in COCO data processing (#976)
- Fix failure to click again after custom model loading
- Fix scrollbar slider display issue
- Fix issue where copied shapes fail to be saved
- Fix auto-save bug after undo operations when switching images (#1013)

### 🛠️ Improvements

- Add solution to CUDA dependency error: `Could not locate cublasLt64_12.dll. Please make sure it is in your library path!` (#1014)
- Add solution to efficiency improvement plan for multi-object keypoint annotation and grouping (#982)
- Add CLA, contributing templates, and README contributor section
- Improve QWebEngineView import error handling in chatbot
- Improve thumbnail rendering by mapping file extensions to model types in auto-labeling service
- Improve shape adjustment convenience
- Improve click-to-move editing with state cleanup and cursor feedback

### 🌟 Contributors

A total of 7 developer contributed to this release.

Thank @1955946542, @donkinone, @ljh725, @pipihuang2, @sunmooncode, @zhixuwei, @CVHub520

## `v3.0.3` (May 28, 2025)

### 🚀 New Features

- Added Digit Shortcut Manager for quick shape creation using numeric keys (#945)
- Added support for preserving existing annotations in SegmentAnything2Video model

### 🛠️ Improvements

- Updated FAQ entries for ONNX model IR version issues with resolution steps
- Added FAQ entry on accessing external models like 'Google Gemini' through proxy settings
- Converted BrightnessContrastDialog to singleton to reduce instantiation overhead (#954)

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v3.0.2` (May 24, 2025)

### 🚀 New Features

- Support `YOLOE` model for text/visual prompting and prompt-free grounding

### 🐛 Bug Fixes

- Fixed crash issue during keypoint annotation (#952)

### 🌟 Contributors

A total of 1 developers contributed to this release.

Thank @CVHub520

## `v3.0.1` (May 20, 2025)

### 🚀 New Features

- Add support for Ultralytics RT-DETR object detection models (#944)
- Enhance label history management by adding removal and addition methods for label history

### 🐛 Bug Fixes

- Add 'pillow' to requirements for macOS, Windows, and Linux (#942)
- Initialize image_data before base64 encoding in save_auto_labeling_result (#946)

### 🛠️ Improvements

- Optimize image folder import performance by disabling automatic EXIF processing (#945)
- Update requirements-macos.txt (#939)
- Add FAQ entry for OpenSSL Uplink error during startup (#941)

### 🌟 Contributors

A total of 3 developers contributed to this release.

Thank @DenDen047, @4399123, @CVHub520

## `v3.0.0` (May 15, 2025)

### 🚀 New Features

- Add ffmpeg acceleration and non-ASCII path support (#891)
- Allow downloading models from [ModelScope](https://www.modelscope.cn/collections/X-AnyLabeling-7b0e1798bcda43) in addition to existing sources
- Enable one-click import and export of labels for [VLM-R1-OVD](https://github.com/om-ai-lab/VLM-R1)
- Enable the [Chatbot](./docs/en/chatbot.md) to annotate multimodal datasets for Vision-Language Models (VLMs)
- Enable automatic saving of group IDs when grouping or ungrouping shapes using shortcut keys G (group) and U (ungroup). (#855)
- Introduce GroupID filter and improve label filtering functionality (#686)
- Support [GeCo](./examples/counting/geco/README.md) zero-shot counting model (#863)
- Support [Grounding-DINO-1.6-API](https://algos.deepdataspace.com/en#/model/grounding_dino) open-set object detection model
- Support [YOLO12](https://arxiv.org/abs/2502.12524) object detection model
- Support [D-FINE](./tools/onnx_exporter/export_dfine_onnx.py) object detection model
- Support [RF-DETR](./tools/onnx_exporter/export_rfdetr_onnx.py) object detection model

### 🐛 Bug Fixes

- Fix bug in `predict_shapes` for `Florence-2` model (#913)
- Replace `os_sorted` with `natsorted` to avoid potential segfault (#906)
- Merge multi-part segmentations into single instance on export (#910)
- Handle exceptions in model loading by initializing local_model_data to an empty dictionary for improved stability (#901)
- Prevent UI disappearance when ESC key is pressed during AI annotation (#423)
- Fixed the bug about exporting the empty labels (#881)

### 🛠️ Improvements

- Move image conversion to avoid redundant processing when using cached embeddings (#915)
- Add new FAQs addressing common runtime errors and file loading issues, including solutions and references to related GitHub issues (#869, #906, #907)
- Enhance image processing logic to support dynamic batch handling based on model type, improving efficiency in auto-labeling operations
- Introduce `iou_threshold` and `conf_threshold` parameters across various model configurations for enhanced detection accuracy
- Remove imgviz dependency from requirements and update colormap implementation in labeling utilities for improved modularity
- Optimize batch processing with UI/backend separation (#757)
- Enhance shape visibility handling in labeling interface (#669)
- Updated the merge_shapes method to handle both rectangle and polygon shapes, allowing for more versatile shape unions. (#561)

### 🌟 Contributors

A total of 8 developers contributed to this release.

Thank @Pecako2001, @liutao, @shyhyawJou, @talebolano, @urbaneman, @wangxiang0722, @Little-King2022, @CVHub520

## `v2.5.4` (Feb 18, 2025)

### 🚀 New Features

- Support `YOLOv8-SAM2.1` instance segmentation model

### 🐛 Bug Fixes

- Improve canvas painting state management during image processing
- Reset `pose_data` for each new image in pose mode (#791)

### 🛠️ Improvements

- Add guide for selecting all annotation shapes (#759)
- Remove `YOLOv8-EfficientViT-SAM` model support

### 🌟 Contributors

A total of 2 developers contributed to this release.

Thank @aiyou9, @CVHub520

## `v2.5.3` (Jan 12, 2025)

### 🐛 Bug Fixes

- Fix loading mistake in batch processing (#777)
- Reset `pose_data` for each new image in pose mode (#791)

### 🛠️ Improvements

- Optimize performance for large files (#743)

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.5.2` (Jan 02, 2025)

### 🚀 New Features

- Enhance export functionality with `classes.txt` and zip output (#775)

### 🐛 Bug Fixes

- Fix image dimension validation errors (#762)

### 🛠️ Improvements

- Update downloads badges in `README`

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.5.1` (Jan 01, 2024)

### 🚀 New Features

- Optimize inference efficiency during batch task execution
- Support `Hyper-YOLO`
- Add CPU support and optimize model loading for `Florence-2`

### 🐛 Bug Fixes

- Fix GBK codec decoding error in `RAM` model loading process
- Fix dtype casting in `RAM` model preprocessing
- Fix `text_encoder_type` path in `open_vision.yaml`

### 🛠️ Improvements

- Improve visibility in dark mode for MacOS
- Update `OpenVision` `README` with new installation instructions

### 🌟 Contributors

A total of 2 developers contributed to this release.

Thank @chevydream, @CVHub520

## `v2.5.0` (Oct 15, 2024)

### 🚀 New Features

- Support interactive visual-text prompting for generic vision tasks
- Optimize rectangle mode in auto-labeling to use minimum bounding box
- Support `SAM2.1` model
- Support `Florence-2` model (#679)
- Support `UPN` model for proposal box generation
- Support `YOLOv5-SAHI` model
- Add range selection for label batch modification (#708)
- Add options dialog with additional export path selection (#702)
- Support importing/exporting COCO keypoint annotations (#190)
- Support `DocLayout-YOLO` model
- Add option to color bounding boxes by category or instance
- Add action to loop through each label

### 🐛 Bug Fixes

- Handle invalid file paths in natural sort during import (#734)
- Improve mask overlapping handling in `custom_to_mask` method during export
- Fix path parsing error of `save_crop` function
- Disable delete action when no shapes present
- Fix image normalization in `Recognize-Anything-Model` preprocessing (#657)

### 🛠️ Improvements

- Add ONNX Runtime compatibility information to installation docs
- Modernize `GroupIDModifyDialog` with improved styling

### 🌟 Contributors

A total of 3 developers contributed to this release.

Thank @julianstirling, @CVHub520, @wpNZC

## `v2.4.4` (Sep 30, 2024)

### 🚀 New Features

- Support `YOLOv11` Det/OBB/Pose/Seg/Track models (integrating Ultralytics v8.3.0)

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.4.3` (Sep 08, 2024)

### 🚀 New Features

- Support `RMBG v1.4` model for image matting

### 🐛 Bug Fixes

- Ensure integer values for shape dimensions in `show_shape` signal
- Fix model loading error for `YOLOv6lite` face models (#638)

### 🛠️ Improvements

- Enhance logging with bold and colored headers
- Modify indexing operations to improve file navigation efficiency
- Improve EXIF orientation handling with backup and logging
- Implement natural sorting for `QListWidget` labels (#627)
- Support user-defined labels and track IDs (#629)

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.4.2` (Sep 06, 2024)

### 🚀 New Features

- Support interactive video object tracking by `SAM2` (#602)
- Implement functionality to visualize drawing results

### 🐛 Bug Fixes

- Fix typo in `upload_coco_annotation` function

### 🛠️ Improvements

- Add vscode configuration files for module debugging and profiling

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.4.1` (Aug 29, 2024)

### 🚀 New Features

- Add dialog for modifying `group_id`
- Support exporting MOTS annotations

### 🐛 Bug Fixes

- Fix patch memory leak in image caching during image transitions
- Retain labels during switch model instances

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.4.0` (Jul 14, 2024)

### 🚀 New Features

- Implement masked image saving functionality
- Support tracking by HBB/OBB/SEG/POSE task
- Support `GroundingSAM2` model
- Support lightweight model for Japanese recognition
- Support `Segment-Anything-2` model
- Enable `move_mode` parameter in `label_dialog`
- Add `use_system_clipboard` action
- Enable import/export of ODVG annotations (`Grounding DINO` dataset)
- Support `RT-DETRv2` model
- Support `RAM++` and `YOLOW-RAM++` models
- Implement feature to draw KIE linking lines with arrowheads
- Support displaying and exporting shape-level information
- Enable `Depth-Anything` model prediction (color/grayscale)
- Add import/export functionality for PPOCR-KIE annotations
- Support annotating KIE linking field
- Support annotating out-of-pixmap rotation shapes
- Support `depth-anything-v2` model
- Add import/export functionality for PPOCR label
- Add toggle for continuous drawing mode
- Support union of multiple selected rectangle shapes
- Add system clipboard copy mode
- Add ability to delete label items based on checkbox selection
- Enable opening previous/next labeled image
- Implement crosshair and marking box style customization
- Add widget for converting polygon to HBB
- Add `YOLO-Pose` import/export functionality
- Enable exporting VOC-format annotations for polygon shape
- Add preserve existing annotations checkbox and real-time confidence adjustment
- Add visibility feature for keypoint detection task
- Support `YOLOv8-World` and `YOLOv8-OIV7` models
- Add feature to display confidence score

### 🐛 Bug Fixes

- Fix image distortion issue during brightness/contrast adjustment
- Fix `TypeError` in `fillRect` for higher Python versions
- Fix `too many values to unpack` error during YOLO class post-process
- Fix `invalid literal for int()` with base issue
- Avoid `directory not empty` error when loading model
- Prevent crash when switching from image directory to imported image
- Fix BMP image loading issue (missing `_getexif` attribute)

### 🛠️ Improvements

- Refresh X-Anything app icon
- Implement structured `ISSUE_TEMPLATE`
- Add `SECURITY.md` file
- Optimize code related to "actions"
- Add extensive documentation examples for various tasks (OCR, MOT, Pose, Segmentation, Detection, Depth, Description, Classification)
- Add `faq.md` file

### 🌟 Contributors

A total of 3 developers contributed to this release.

Thank @UnlimitedWand, @PairZhu, @CVHub520

## `v2.3.7` (May 29, 2024) - *Pre-release*

### 🚀 New Features

- Support `YOLOv8-World` and `YOLOv8-OIV7` models

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.3.6` (May 25, 2024)

### 🐛 Bug Fixes

- Fix `TypeError` in YOLO model (ensure `setText` accepts only strings)
- Fix `ValueError` by adding a check for selected shape existence (#388)
- Fix `list index out of range` when exporting DOTA annotations

### 🛠️ Improvements

- Optimize brightness and contrast adjustment performance

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.3.5` (Apr 01, 2024)

### 🚀 New Features

- Enhance image cropping: polygon and rotation `shape_type` support (#331)
- Add widget for converting OBB to HBB

### 🐛 Bug Fixes

- Fix `TypeError` in YOLO model (ensure `setText` accepts only strings)
- Fix `IndexError` in Canvas widget's shape module (#332)
- Fix invalid path issue when loading JSON file in Windows environment

### 🛠️ Improvements

- Refine canvas reset behavior to prevent unintended blank canvas
- Improve performance for loading large image files

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.3.4` (Mar 16, 2024)

### 🚀 New Features

- Support `YOLO-World` model
- Enable label display feature

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.3.3` (Feb 27, 2024)

### 🚀 New Features

- Add expanded sub-image save feature
- Support converting YOLO-HBB/OBB/SEG labels to custom format

### 🛠️ Improvements

- Add real-time progress bar for mask annotation uploads

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.3.2` (Feb 24, 2024)

### 🚀 New Features

- Support `YOLOv9` model
- Support converting horizontal bounding box (HBB) to rotated bounding box (OBB)
- Support label deletion and renaming
- Support quick tag correction

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.3.1` (Jan 31, 2024)

### 🚀 New Features

- Support saving cropped rectangle shapes
- Combine `CLIP` and `SAM` models
- Support `Depth Anything` model for depth estimation

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.3.0` (Jan 13, 2024)

### 🚀 New Features

- Support `YOLOv8-OBB` model
- Support `RTMDet` and `RTMO` models
- Release Chinese license plate detection and recognition model based on `YOLOv5`

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.2.0` (Dec 26, 2023)

### 🚀 New Features

- Add label background color rendering
- Add one-click clear point prompts in SAM annotation mode
- Extend rectangle box editing to four-point editing mode
- Support automatically switching to editing mode on hover
- Implement one-click export for segmented mask images
- Add one-click import/export for YOLO/VOC/COCO/DOTA/MASK/MOT labels
- Introduce data statistics for the current task
- Add functionality to hide/show selected objects
- Add real-time preview of filename and annotation progress
- Support "Difficult" label
- Add bottom status bar displaying mouse coordinates and selected object dimensions
- Enable direct modification of object text descriptions in the label editing box

### 🛠️ Improvements

- Remove confirmation dialog for object deletion

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.1.0` (Nov 24, 2023)

- Support `InternImage` classification model

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v2.0.0` (Nov 13, 2023)

### 🚀 New Features

- Support `Grounding-SAM` (`GroundingDINO` + `HQ-SAM`)
- Enhance support for `HQ-SAM` model
- Support `PersonAttribute` and `VehicleAttribute` models for multi-label classification
- Introduce multi-label attribute annotation functionality

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v1.1.0` (Nov 06, 2023)

### 🚀 New Features

- Support pose estimation: `YOLOv8-Pose` (#103)
- Support object-level tagging with `yolov5_ram`
- Add capability to adjust `keep_prev_brightness` and `keep_prev_contrast` (#104)
- Add feature for batch labeling arbitrary unknown categories based on `Grounding-DINO`

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v1.0.0` (Oct 25, 2023)

### 🚀 New Features

- Release X-AnyLabeling `v1.0.0`
- Add rotation box annotation feature
- Support `YOLOv5-OBB` with `DroneVehicle` and `DOTA` models
- Add `GroundingDINO` model for zero-shot object detection
- Add `Recognize Anything` model for image tagging

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v0.3.0` (Oct 10, 2023)

### 🚀 New Features

- Release `Gold-YOLO` and `DAMO-YOLO` models
- Release MOT algorithm: `OC_Sort` (CVPR'23)
- Add feature for small object detection using `SAHI`

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v0.2.4` (Sep 20, 2023)

### 🚀 New Features

- Support `EfficientViT-SAM` model

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v0.2.3` (Sep 18, 2023)

### 🚀 New Features

- Support `YOLOv5-SAM` model

### 🐛 Bug Fixes

- Fix issues #51, #60, #62

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v0.2.2` (Sep 14, 2023)

### 🚀 New Features

- Support `PP-OCRv4` model
- Add Model Lists

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v0.2.1` (Sep 06, 2023)

*No specific changes listed for this release tag.*

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v0.2.0` (Aug 09, 2023)

### 🚀 New Features

- Add `MobileSAM`, `MedSAM`, `SAM-Med2D` models
- Add `LVM-Med` model (Kvasir, ISIC, BUID segmentation)
- Add `CLRNet` model for lane detection
- Add `DWPose` model for whole-body pose estimation

### 🐛 Bug Fixes

- Fix `YOLOv8` issue
- Fix GPU inference result exception

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v0.1.2` (Jun 20, 2023)

### 🚀 New Features

- Add `YOLO-NAS` model (v3.1.1)
- Add `YOLOv8-Seg` model

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v0.1.1` (May 25, 2023)

*Update executable files.*

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520

## `v0.1.0` (May 23, 2023)

### 🚀 New Features

- Release initial public version of X-AnyLabeling
- Support `YOLOv5` (v7.0)
- Support `YOLOv6` (v0.4.0)
- Support `YOLOv6Face` (v0.4.0)
- Support `YOLOv7` (main)
- Support `YOLOv8` (main)
- Support `YOLOX` (main)
- Support `YOLO-NAS` (v3.1.1)
- Support `YOLOv8-Seg` (main)
- Support `Mobile-SAM`

### 🌟 Contributors

A total of 1 developer contributed to this release.

Thank @CVHub520
