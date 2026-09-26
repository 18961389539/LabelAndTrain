# JLLabelingAndTrain Changelog

Fork entries are listed first; everything below the upstream marker is
X-AnyLabeling's own history, kept for provenance.

## `v1.0.0-beta.1` (Sep 23, 2026)

### ✨ New Features

- The flake8 gate is real now: `scripts/check_flake8_baseline.py` freezes the fork's inherited findings as `<path> <code> <count>` triples in `scripts/flake8_baseline.txt` (line numbers deliberately excluded, so editing a file above a finding is not a regression, and paths are separator-normalised so a Windows-generated baseline gates a Linux runner). It fails only when a `(path, code)` pair is new or its count rises, reports what improved, and re-freezes with `--update`. 13 tests in `tests/test_utils/test_lint_baseline.py` pin both directions, including that a gate which never fires is not mistaken for protection.

- Startup goes through the project manager: the "继续上次标注？" prompt is replaced by a three-way decision (`project_registry.decide_startup_action`, pure and tested) — a recorded session is restored directly (folder plus last image, no questions asked), a registry with entries but no current session opens the project manager dialog instead, and a true first run keeps the empty-canvas CTA unobstructed. A new `startup_show_project_manager` rc key (default off) shows the manager on every launch; the switch lives as a checkbox inside the dialog itself. The switcher grew into the project manager: four columns (项目 / 上次打开 / 训练 / 最近训练) join `run_meta.json` records to each project by normalized path prefix — the recorded label dir anchor beats the image folder, sibling folders (`plates` vs `plates_extra`) never cross-credit, and runs without a dataset record are skipped rather than guessed (`run_history.project_training_stats`, `dataset_label_dir` now carried on every row). 5 new tests: `test_startup_action_matrix`, `test_startup_show_project_manager_defaults_off`, `test_project_training_stats_match_by_closest_anchor`, `test_project_training_stats_respect_prefix_boundaries`, `test_project_training_stats_without_runs_root_is_all_zero`.
- Review state per image: `review_state` (`unchecked` / `confirmed` / `rejected`) plus `reviewed_at`; `checked` is kept in sync for existing consumers. New "需返工" filter, progress count, and `mark_rejected_and_next` (Ctrl+Shift+K).
- Provenance per shape: `source` (`human` / `model` / `unknown`) and the producing model name, stamped at all three places predictions are applied.
- `model_version` alongside it: a SHA-1 prefix of the loaded weights file, so boxes drawn before a retrain are still recognisable as older when the loop reuses one YAML and one `best.onnx` path. Only compared when both sides have one — shapes recorded before this field exists are never made stale by it.
- "旧轮模型框盘点" smart-tool: groups stale model boxes by producing model, offers per-row deletion; locked, unattributed and since-edited boxes are never deleted, and affected label files are snapshotted to `.label_backups/<stamp>/` first.
- Reproducibility: dataset `manifest.json` (per-file content hashes, split assignment, classes, seed) and `run_meta.json` per finished run (weights hash, exact arguments, manifest hash, metrics).
- Hover text where the fork's data actually lives: an object row now shows class, shape, producing model plus its weight digest, confidence, vertex count and bounding box, attributes, description and what protects it; a file row shows the path, its label file, the review state with timestamp and, for the open image, the model/human/unknown split. The panel grip and collapse button, the zoom box, both filter comboboxes, the label search, the preview sliders and the auto-labeling panel buttons got real tooltips too.
- The status dot's one-line tooltip (`已检查` / `负样本…`) is folded into the row tooltip instead of fighting it for the same property — refreshing the icon can no longer erase the detail, and one builder owns the text.
- Run history table (`训练 → 实验历史`): every recorded run with its metrics, seed, dataset sizes and hash prefixes, newest first, joined to the iteration round that produced it; CSV export. Runs older than `run_meta.json` are reported as a count instead of blank rows.
- Snapshot restore (`智能工具 → 11. 从备份恢复标注`): lists the runs under `.label_backups`, writes the chosen one back over the labels it came from, and snapshots what it replaces first — so picking the wrong run is itself reversible. The image open in the canvas is skipped while unsaved work is pending.
- Split seed pinned per dataset in `.jllabel/project.json`, so consecutive rounds are comparable.
- Multi-project support, layer by layer: the label panel's suggestion list and the annotation output dir now live in `.jllabel/project.json` too (anchored at the image folder — `classes.txt` still wins for classes), so folder B no longer inherits folder A's labels or output dir; a recorded dir that no longer exists is ignored, not cleared. The project switcher (`文件 → Switch Project`, Ctrl+Shift+O) lists every opened dataset with its label dir and last-opened time (registry at `<work_dir>/.jllabel/projects.json`, 20 entries, vanished folders skipped) and carries 打开项目设置文件夹 / 重置本项目设置 (keeps the pinned split seed) / 从列表移除. Training tuning mirrors per dataset through a whitelist (`train_prefs`: `basic.model`/`pose_config` plus the eight pure hyperparameter sections — never `project`/`name`/`data`/`device`/`workers`/`dataset_ratio`): the config tab restores the dataset's last-used values on open, and committing a run records them. A second instance is detected per work directory and logged — project settings are isolated, but the global rc and recent lists stay last-close-wins. `run_meta.json` records the open dataset's label dir, and the experiment-history table gains a 数据集 column so rounds from different datasets can be told apart. Guarded by 25 new tests in `tests/test_utils/test_project_settings.py`.
- Pose and classification loop-back: `yolo26_pose` reuses the training pose config; new `yolov8_cls` adapter returns confirmable whole-image suggestions instead of shapes.
- Active-learning set: threshold calibration, dataset analysis, missed-label scan, iteration dashboard, review-jump queue, label propagation, duplicate archiving, training advice, template pre-labeling.
- Search box in the settings header. 119 settings sat behind four pages and three levels of navigation with no way to filter; the box now matches across every page at once, on key, title, English description *and* the Chinese translation of that description, so typing 撤销 lands on "Undo Backups". Results keep their real editors — a setting found by search can be changed in place, and the edit marks its *owning* page dirty — and each result group carries a breadcrumb plus 打开此页 to open the page it lives on. Shortcut entries also answer to the Chinese name the F1 cheat sheet gives them, so 撤销 finds `shortcuts.undo` too.

### 🛠 Improvements

- God Object diet, batch 7: the settings dialog's chrome (280 lines) moved out of `settings/dialog.py` into `settings/appearance.py` -- the palette, the two icon painters and four stylesheet builders. It was the only cluster in that 2434-line, 94-method class touching nothing but `_palette` and `_nav_icon_size`, so the cut was free: eight thin delegates stay behind and all 76 `self._rgb(...)` call sites keep reading the same. `dialog.py` is 2186 lines now. The move is verbatim after the mechanical `self.` to `widget.` transform (which also rewrote the 14 internal `_rgb` calls); the three CSS templates lost four columns of leading whitespace per continuation line with their code (1524 to 1368, 1814 to 1614, 692 to 608 characters). Checked against the pre-move methods loaded out of `HEAD`: identical line for line once leading whitespace is stripped, every declaration unchanged, and all eight navigation icons come out pixel-identical.
- The fork's own features finally have user documentation. They were described nowhere but this file, which is written for whoever maintains the code. `docs/zh_cn/fork_features.md` covers project management and per-project settings, the review-state workflow, the eleven smart tools in their recommended order, the training loop and its `run_meta.json` / `manifest.json` reproducibility, shape provenance, the settings dialog and the shortcut layer, and where each piece of data lands on disk. It is Chinese on purpose and the English README says why: Chinese is the source language for everything this fork owns and the interface ships only `zh_CN`. Linked from `user_guide.md` section 10 and the README doc index.

- `views/training/ultralytics_dialog.py` no longer star-imports. Five `from ... import *` lines pulled 39 names in from the widgets and auto-training packages and hid 157 findings behind `F405` ("*may* be undefined"); they are now explicit imports listing exactly the 36 names the file uses, resolved in the same order as before. Two of those names (`get_settings_config_path`, `TASK_SHAPE_MAPPINGS`) were claimed by two modules each and three (`get_theme`, `os`/`json`/`csv`/`re`) were shadowing an earlier import -- all verified to be the *same object*, so the rewrite is behaviour-preserving. The file's flake8 count went 157 to 1 (a pre-existing `C901`), and the repository total 331 to 175.
- flake8 had two configs and the authority was the wrong one: `pyproject.toml` carried a `[tool.flake8]` table that flake8 never reads (it needs the third-party Flake8-pyproject plugin), duplicating the `ignore` list that `.flake8` actually applies -- free to drift, and holding the only copy of the `exclude` list, which is why the generated `anylabeling/resources/resources.py` was being linted. The dead table is gone, `.flake8` gained that exclude, and `select = B,C` now means something because `flake8-bugbear` and `flake8-comprehensions` are installed by the `dev` extra everywhere (neither was installed anywhere before, so those rules silently did not run). `B950` is ignored next to the already-ignored `E501`, since it is the same check with 10% tolerance -- leaving it on would have policed 86 columns by the back door, which is 335 of the findings.
- Typo sweep over comments and docstrings: `paramters` to `parameters` in four ONNX exporters, `contorl` and `abreviated` in `__base__/clip.py`, `lables` in `label_widget.py`. `.codespell-ignore` records the four words codespell gets wrong here -- `dota`/`mot` are dataset names, `dfine` is a model name, and `pres` comes from splitting the `pResx`/`pResy` locals of `Canvas.rotate_point`; `degress` is parked there with the reason written down.
- The archived upstream pages now say so on the page. `docs/{en,zh_cn}/{chatbot,vqa,image_classifier,paddle_ocr,model_zoo}.md` are reachable from a search engine or from `user_guide.md` and read as instructions for panels this build does not ship; the README disclosed their status but the pages themselves did not, so each got a banner pointing at "Fork scope". `user_guide.md` section 10 stopped listing them as live features, and dropped a link to upstream's `video_classifier.md`, which is not in `docs/en/` or `docs/zh_cn/` either. `docs/site.yml` had declared that same missing page as a workflow -- a manifest entry no code path reads and no renderer complains about. `tests/test_utils/test_docs_manifest.py` now checks both: every manifest workflow resolves in every declared locale, and every relative `.md` link in the two guides exists.

- Custom model limit raised from 5 to 30; models produced by the loop are pinned and never evicted.
- Fork-owned version reported in the window title, status bar, `version` and `checks`, while keeping the upstream name and source visible as required by its GPL terms.
- Dataset build directories no longer collide within the same second; the app offers to reclaim old dataset copies. Label backups got the same treatment, so two snapshots taken in one second stay two runs.
- Deleting stale boxes from the image open in the canvas is a real undo step now: the batch is applied through the canvas snapshot history instead of reloading the file, so one Ctrl+Z brings every deleted box back.
- Translation scripts walk the catalogs that actually exist instead of a fixed four-language list, `language` other than `zh_CN` warns instead of being ignored, and both get-started pages now state that this build ships one catalog.
- One command name: the `xanylabeling` console-script alias is removed, and the converter's usage text plus every documentation example follow `jllabelingandtrain`. The packaged default config is `jllabeling_config.yaml`, `x-anylabeling.desktop` became `jllabelingandtrain.desktop` (nothing referenced it), and the training payload's temp-file prefix and model-download User-Agent carry the fork's name. On-disk data locations — `~/.xanylabelingrc`, `xanylabeling_data/`, `xanylabeling_logs/`, the Qt settings domain — and the Python package name stay, because renaming those costs either your existing weights/runs/config or upstream mergeability.
- The 1744-line `_build_actions` built the actions, the menus, the tool list **and** the entire layout, so its name described a third of what it did. The layout half is now `_build_layout(widget)` (249 lines, called from `__init__` right after, in the same order), and the split was dependency-free: the laid-out half touches nothing but `widget` attributes, which is why it moved as a byte-identical block (the diff shows those 249 lines as context, not as rewrites). The menus stayed behind on purpose — they consume ~80 of the action handles created just above them, so carving them out would mean threading a namespace through both halves for no gain. `_build_actions` is now 1498 lines and its docstring says what it really does.
- God Object diet, batch 5: the attribute-panel cluster (498 lines) moved out of `label_widget.py` into `widgets/attributes_controller.py` — `update_attributes` (348, the width-wrapping radio/combo/lineedit editor grid with its four nested helpers), `save_attributes` (81, the standard label-file serialization) and `shape_selection_changed` (69, edit-action syncing) as widget-first module functions, byte-identical after the mechanical `self.` → `widget.` transform (verified against `HEAD` blocks, multiline-string token check included). `_measure_text_width` moved to `utils/qt.py` as `measure_text_width` (aliased back so moved bodies stay untouched). The widget keeps thin delegates, so menu wiring and the unbound-call test style hold; the one test patch target that named `label_widget.LabelFile` now names the new module. `label_widget.py` is 8727 → 8238 lines, and its flake8 baseline dropped from 6 to 4 entries (the `update_attributes` C901 and one `blocker` F841 moved out with the code). Full suite 703 passed.

### 🐛 Bug Fixes

- The training-failure dialog could not be shown at all. `on_training_event` built its error box through `QtWidgets.QMessageBox` while the module only imported the widget classes themselves, so every failed run ended in `NameError: name 'QtWidgets' is not defined` instead of a readable "training failed" box with its Retry button. The name was never supplied by any of the five star imports either -- a star import downgrades a missing name from `F821` to `F405`, so it sat inside 157 "probably fine" warnings until the star imports were replaced, at which point the four real uses turned into `F821`. Fixed by importing `QtWidgets` the way `app.py` and `toaster.py` do, and covered by 5 tests in `tests/test_auto_training/test_training_error_dialog.py` that drive the branch with a recording message box.
- `scripts/generate_languages.py` will not silently eat the catalog any more. `pylupdate6` can only attribute a `tr()` call to a context when it can see one, so `widget.tr(...)` inside a module-level function is dropped without a word -- and this fork moved a lot of `LabelingWidget` methods into `widget`-first module functions, leaving 249 of its 421 entries looking obsolete on the next extraction. Running the script today reported "249 obsolete messages were discarded" and recompiled a catalog with 790 entries instead of 1013: 26 user-facing strings would have lost their Chinese, and one of them (`Show Degrees`, the View-menu item) would have fallen back to English because the extractor cannot place it at all. It also leaves the ~249 dropped messages' translations stranded: they are still in the shipped `.qm`, so the loss only shows up at the *next* rebuild. The script now compares the entry count before and after and refuses to go on when a run sheds more than 10%, naming the likely cause. Verified by running it: it raises instead of overwriting. The underlying extraction problem (and the `Show Degress` typo it protects) is left for a dedicated i18n pass -- fixing it properly means an explicit context for every `tr()` that moved out of a class, plus a rebuild of the blob embedded in `resources.py`.

- The shipped Chinese catalog was an inherited upstream artefact, not this fork's own. 69 of its `<location>` entries named files this YOLO-only fork deleted (772 locations total), and it still carried 725 strings for dialogs that do not exist here — `VideoClassifierDialog`, `PPOCRDialog`, `ChatbotDialog`, `VQA`/`Classifier`/`Export` and others. Meanwhile 336 strings actually present in the code were missing from it, so they could never be translated. Re-extracted from the current tree: 1013 entries over 39 live contexts, 0 dangling locations, 0 unfinished translations, and every context name is a class that still exists. `scripts/generate_languages.py` also walked `**/*.py` including `.venv`, which would have drowned the catalog in dependency strings; it now scans `anylabeling/` only, skips generated blobs and build dirs, and fails loudly when the extractor is missing instead of shelling out, ignoring the error and recompiling a stale `.ts`.
- Three model-manager messages could never be translated: `Loading model: {model_name}. Please wait...`, `Error in loading model: {error_message}` and `Error in model prediction: {error_message}` were passed to the translation call as *variables*, and the extractor only reads literals — it recorded one `(unknown)` placeholder instead of the three strings. The literals are now passed at the call site, so they are extracted, translated and reachable at runtime.
- `tests/test_utils/test_translations.py` now holds the catalog to its sources: no location may point at a missing file, every context must name a live class, nothing may be left unfinished, and all 722 English→Chinese entries must match what the compiled `.qm` in `resources.py` returns — a `.ts` edit without a rebuild fails the suite instead of being invisible at runtime.
- `import_image_folder` cleared the file list but not `fn_to_index`, and `_apply_file_sort` reordered rows without rebuilding it, so a path could resolve to the wrong row and review state could be read or written against a different image.
- Every smart-tool result dialog raised `NameError` (undefined `QtGui`), and the stale-model audit had an unimported name; both were unreachable for tests because nothing constructed the widget or ran an action.
- `save_config` swallowed the traceback; the training dialog reported "saved successfully" after a failed write; custom-model add/remove ignored persistence failures; `app.log` never rotated and the faulthandler handle could be collected.
- Two review-navigation loops rebuilt the whole file list per scanned row.
- The floating tools panel showed one button out of 26. Its content is a `QScrollArea`, whose `sizeHint()` is the scroll area's own small default rather than the toolbar inside it, so `adjustSize()` sized the panel to ~76px and everything else went behind a scrollbar; `sync_to_parent()` only ever set a *maximum* height, which cannot make a widget taller. The panel now sizes its content from the largest height any source reports (scroll area, inner toolbar, minimums) and clamps to the viewport when the window is short — the scrollbar stays as the overflow path it was meant to be. Measured on a 1400×900 window: panel 50×76 → 50×711, all 26 tools visible. The existing panel tests fed it a fixed-size `QFrame`, which is why none of them caught it; `TestPanelWithScrollAreaContent` covers the real shape, including the short-parent clamp.
- Launching with `--filename <folder>` died at startup with `AttributeError: 'LabelingWidget' object has no attribute 'settings'`: the recent-folders feature records the opened folder through `self.settings`, but the folder import ran ten lines before `self.settings` was created. Opening a folder from inside the window still worked, so nothing but a folder launch hit it — and no test constructed the widget with a folder. `QSettings` is now restored first, and `TestWidgetLaunchedWithFolder` covers the path (reverting the order fails it with the original traceback).
- `checks` inside a built executable reported `None` for PyQt6, onnxruntime and OpenCV while the app was using them: the versions came from packaging metadata, which PyInstaller does not carry. They are read from the live modules now, and the PyQt6 line names the Qt runtime too.
- 数据体检 ranked the review queue and then kept only its first 50 entries, and 智能复核 navigated that truncated list: a folder with hundreds of uncertain images reported `1/50` and then "end of queue" while candidates were still waiting. The queue is now complete and the cap lives in the dialog, which states each category's real total and no longer counts review priorities among the problems found.
- Three strings reached a widget without `tr()` (a recommended-model chip's tooltip and both "Skip empty labels" help texts), so nothing could translate them. Wrapping them changes no visible text: `zh_CN.ts` has no Chinese `<source>` entries, which is also why writing fork text in Chinese and passing it through `tr()` is safe here.
- Both get-started pages told readers to `pip install --pre "x-anylabeling-cvhub"`, to clone `CVHub520/X-AnyLabeling`, or to download the GUI installer from upstream's Releases. All three get you **upstream's** program, which has none of this fork's loop features; the pages now state that this build is source-install only, publishes nothing, and its executable comes from building it yourself.
- Both translation scripts listed four languages while this checkout ships one catalog, so the documented `compile_languages.py` command died on the missing `.ts` files; the get-started pages advertised an interface language that cannot be selected. `language` in the config was read by the model and the trainer but silently ignored by the translator, which always loaded `zh_CN`.
- Packaging: `.desktop` `Exec` pointed at a non-existent script; linux/macos specs still bundled deleted `configs/bert` and `configs/ram`.
- CI: `tests/test_settings` crashed the process when run on its own (a test created a non-GUI `QCoreApplication` that later widget tests reused).
- `load_recent_dir` was defined twice in `LabelingWidget` (line 2380 and line 5526), so the second silently shadowed the first — and only the earlier one carried the empty-path guard. This is the same failure mode as the five shadowed file-list methods fixed earlier, which were found by eye; the whole tree was re-scanned with an AST pass over every class body in `anylabeling/` and `tests/`, which now reports **0** duplicate definitions (property/setter pairs excluded). The dead copy is gone, the survivor kept the docstring and the guard.
- Three methods had no caller anywhere in the tree, not even a test: `copy_to_clipboard`, `update_selected_options` and `has_labels` (99 lines, zero references across every file type in the checkout). They were orphaned by the review-flow rewrite and the attribute-panel rework; deleted rather than left as an untested surface. `dragEnterEvent`/`dropEvent` stay — Qt calls those.
- Two code paths computed the same label path with the same `output_dir` override written out twice (`get_label_file()` and `_label_path_for_image()`), so a change to the override rule could land in one and miss the other. `get_label_file()` delegates to `_label_path_for_image()` for that part now; only its `self.label_file` / `.json` handling sits above the delegation.

### 🔗 CI / Tooling

- `pytest-cov` is wired up, so "how much is tested" has an answer: **44.3%** of 31891 statements across 158 files, with 35 files complete. The distribution is the interesting part -- `views/labeling` is 49.8%, `services/auto_labeling` 28.1%, `views/training` 21.3%, and `app.py` / `views/mainwindow.py` are at 0%. The single worst offender is the fork's own `views/training/ultralytics_dialog.py`: 1741 statements at **12.3%**, which is exactly where the `QtWidgets` NameError lived, so the two findings are the same finding. No threshold is set: coverage is printed in the test job and nothing more, because a gate nobody can pass is worse than a number somebody reads. `--cov` is deliberately not in `addopts`, so a local `pytest tests` stays the fast path, and the config lives in `[tool.coverage]` in `pyproject.toml`.
- A `lint` job in `.github/workflows/ci.yml` runs `scripts/check_flake8_baseline.py` on every push and pull request. The test job still runs the suite on `windows-latest` / 3.12; a Linux runner is not added because Qt offscreen there needs system libraries nothing in this repo installs, and a red job that is not the fork's fault is worse than no job.
- pre-commit is wired up for the first time. The config existed but nothing ran it: `pre_commit` was not installed, `.git/hooks` held only the two ref-tracking hooks, and CI had no lint step. It is installed now, and the config was repaired while doing it -- `black` was listed twice (once rewriting, once with `--check`, which cannot both be wanted) and it is removed rather than fixed, because `black --check` rejects 44 of the 156 files it reads and wants trailing comments moved onto their own line inside parentheses, against this repo's documented style. Enabling it would reformat the tree as a side effect of the next unrelated commit or fail on whatever file a contributor touches; that is a decision to take deliberately, and the config says so in place. The flake8 plugins `select = B,C` asks for are installed by the `dev` extra so local, CI and the hook all check the same rule set -- `tests/test_utils/test_lint_config_consistency.py` asserts they agree and that `pyproject.toml` does not grow a `[tool.flake8]` table back.
- `end-of-file-fixer` fixed 11 files with no final newline and trimmed two with trailing blank lines. Note for whoever runs pre-commit on this checkout: the hook opens every file `rb+`, and on the G: volume used here it fails about one run in two with a `PermissionError` on a different file each time, even though all 157 `.py` files under `anylabeling/` open `rb+` 20 times out of 20 in a loop. It is the volume, not the config.
- Three scripts with a shebang were not marked executable (`build_and_publish_pypi.sh`, `build_executable.sh`, `generate_release_notes.py`); `git update-index --chmod=+x` fixes the mode. The hook then caught the same thing on `scripts/check_flake8_baseline.py` the moment it was first committed, which is the gate doing its job.
- `.github/workflows/ci.yml` runs the full suite on pushes to `main` and pull requests.
- README and both doc sets now describe only what this build can do, guarded by `tests/test_utils/test_readme_claims.py` (phantom model families, pruned capability claims, local link resolution, upstream credit).
- `tests/test_utils/test_fork_naming.py` scans every text file in the tree for the bare upstream command name and asserts one console script, so docs and help text cannot drift back to a command this install does not provide. The names it deliberately ignores are written down in the file.
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
