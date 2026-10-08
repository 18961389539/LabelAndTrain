# Training with Ultralytics

[English](README.md) | [简体中文](README_zh-CN.md)

The training panel turns the folder you are annotating into a YOLO dataset,
trains a model on it in a separate process, and hands the result back to auto
labeling. It covers four tasks — **Detect / Segment / Pose / Classify** — and
exposes the ~40 parameters of the Ultralytics trainer, with the ones you
actually iterate on up front and the rest behind one disclosure.

> [!NOTE]
> The interface is Chinese-only (`zh_CN`), like the rest of this build; this
> guide uses the English names for the fields and notes the Chinese label where
> the exact wording matters.

## Before you start

- **Ultralytics must be importable by the app.** Source installs:
  `pip install ultralytics` (or `uv pip install ultralytics --torch-backend=auto`).
  Without it the menu entry explains the command instead of opening the panel.
  The `win-cpu-train` packaging target exists for machines without a GPU: it
  bundles CPU torch and Ultralytics, so training works inside the frozen app.
- **Labels come from this tool.** The dataset is built from the label JSONs
  sitting next to your images; no other annotation format is read here.
- **At least 20 images with a usable shape for the chosen task.** The Data tab
  counts them and says how many are still missing; "usable" means at least one
  `rectangle` (Detect), `polygon` (Segment), `point` (Pose) or an image-level
  flag (Classify).
- **Pose needs a pose config YAML** (class → keypoint names), which the panel
  asks for on the Config tab. See
  [`assets/yolov8_pose.yaml`](../../../assets/yolov8_pose.yaml) for the format.

## The loop

```
annotate → review (已检查 / 需返工) → train on 已检查 files
        → best.pt → ONNX → load as auto-label model
        → re-predict the folder → 迭代收益看板 reports the round
```

Training and re-predicting are two different steps on purpose: the panel never
relabels your folder behind your back. `用于自动标注` (Use for Auto-Labeling) is
the one-click bridge, and it asks before it runs.

## 1. Data tab

| Control | What it does |
| :--- | :--- |
| Task type | `Classify`, `Detect`, `Segment`, `Pose` — one of them must be selected; the rest of the wizard follows from it (which shapes count, which model presets are offered). |
| Valid images | `有效图片: N  需要: 20` — green when N clears the threshold, red otherwise. Cached per task type. |
| Dataset summary | A headline (`N 张图 · M 类 · X 已标注 · Y 空标`) plus a per-class table of shape counts, so a missing class shows up before training rather than in the confusion matrix. |
| `Load Images` | Opens a folder (`Ctrl+U`) if none is open yet. |

Empty labels are not a problem: an image whose JSON has no shapes is kept as a
**background (negative) sample** in the training split. Tick `Skip Empty Files`
in the advanced settings if you would rather leave them out.

## 2. Config tab

### Basic settings

| Field | Notes |
| :--- | :--- |
| `Project` / `Name` | The run directory is `<Project>/<Name>`; Project defaults to `<work_dir>/xanylabeling_data/trainer/ultralytics/runs/<task>`. |
| `Model` | Pretrained checkpoint. The dropdown offers the usual weights for the selected task (`yolov8n.pt`, `yolo11s-seg.pt`, …); a **bare name is downloaded on first use** — progress shows up in the training log, not as a frozen window — and `Browse` takes a local `.pt`. |
| `Data` | Class-list YAML. For Detect/Segment/Pose only the `names` mapping is read: the panel generates a file for the open folder automatically (under the trainer's `data/` directory, named after the folder and task), regenerates it whenever you enter the Config tab, and `从标注生成` (From Labels) refreshes it on demand. A YAML you picked yourself is never overwritten. **Classify may leave it empty** (the dataset is built from image flags) or point it at a pre-organized `train/ val/ class/` directory. |
| `Pose Config` | Pose only: the keypoint definition used to convert the labels. |
| `Device` | `cuda` / `mps` / `cpu` as available; with CUDA you can pick which GPUs to use. On **CPU** the form adapts: AMP is switched off and disabled, and untouched epochs/batch/imgsz are filled from a CPU preset (50 / 8 / 416) with a note under the field saying what was replaced. Nothing you changed yourself is overwritten. |
| `Dataset Ratio` | Train/validation split (default 0.8). The split is drawn with a seed pinned per dataset in `.jllabel/project.json`, so two rounds are comparable. |

### Presets

`快速验证` (Quick check), `标准` (Standard) and `高精度` (High quality) set the
pace in one click — epochs, image size, patience, close-mosaic and cosine LR:

| Preset | epochs | imgsz | patience | close_mosaic | cos_lr |
| :--- | ---: | ---: | ---: | ---: | :--- |
| Quick check | 30 | 416 | 10 | 5 | off |
| Standard | 100 | 640 | 100 | 10 | off |
| High quality | 300 | 640 | 100 | 20 | on |

Presets replace what is in those fields (that is what they are for) and record
what they applied in the log. `智能推荐参数` (Smart Recommend) is the data-driven
variant: it reads the class distribution of the open folder and this dataset's
training history, then fills epochs / batch / imgsz.

### Basic train settings

| Field | Default | Notes |
| :--- | :--- | :--- |
| `Epochs` | 100 | — |
| `Batch` | 16 | `-1` picks the batch automatically **on GPU** (on CPU it falls back to 16). Lower it if training runs out of memory. |
| `Image Size` | 640 | Smaller trains faster; 416 is a common CPU choice. |
| `Workers` | 8 | Data-loader processes. Ultralytics forces 0 on CPU; 0–2 is the safest range on Windows. |
| `Classes` | all | Indices to train, e.g. `0,1,2`. |
| `Single Class` | off | Treat every label as one class. |

### Advanced settings

<details>
<summary>Defaults for every advanced field</summary>

| Group | Field | Default |
| :--- | :--- | :--- |
| Training strategy | Time limit (h) | none |
| | Patience | 100 |
| | Close mosaic | 10 |
| | Optimizer | `auto` |
| | Cosine LR | off |
| | AMP | on (forced off on CPU) |
| | Multi scale | off |
| Learning rate | LR0 | 0.01 |
| | LRF | 0.01 |
| | Momentum | 0.937 |
| | Weight decay | 0.0005 |
| Warmup | Epochs | 3.0 |
| | Momentum | 0.8 |
| | Bias LR | 0.1 |
| Augmentation | HSV hue / saturation / value | 0.015 / 0.7 / 0.4 |
| | Rotation | 0 |
| | Translate / scale | 0.1 / 0.5 |
| | Shear / perspective | 0 / 0 |
| Regularization | Dropout | 0 |
| | Fraction | 1.0 |
| | Rectangular | off |
| Loss weights | box / cls / dfl | 7.5 / 0.5 / 1.5 |
| | pose / kobj | 12.0 / 2.0 |
| Checkpoint | Save period | disabled |
| | Validation / plots / save | on / off / on |
| | Resume | off (see below) |
| | Cache | off |
| | Skip empty files | off |
| | Only checked files | off |

Every field carries a tooltip that says what the parameter is and which way to
push it. `Skip Empty Files` leaves images without shapes out of training;
`Only Checked Files` trains on 已检查 images only — the same filter the review
workflow maintains.
</details>

`Import Config` / `Save Config` move the whole form to and from a JSON file.
The panel also remembers per-dataset tuning: the model, pose config and every
tuning section are mirrored into `.jllabel/project.json`, so reopening a folder
restores the parameters it was last trained with instead of inheriting the
previous dataset's.

## 3. Train tab

### Status and progress

| Status | Meaning |
| :--- | :--- |
| `Ready to train` | Idle. |
| `Preparing dataset` | The dataset is being built (copied, converted, split) on a background thread — the dialog stays responsive. |
| `Training in progress` | The worker process is running. |
| `Completed` / `Error` | Terminal states; the log is written to disk at this point. |

The progress bar counts epochs from `results.csv`; before the first row appears
it shows `Starting (elapsed m:ss)`. Under it, the metrics line shows the latest
`loss`, `mAP50` and epoch count — and, once two epochs are in, an estimated time
left (`About 12 min left`) computed from the recent epochs' pace, so a resumed
run with a restarted clock still estimates correctly.

### Logs

The log view streams the training process's stdout/stderr (ANSI colour codes
stripped, capped at 10 000 lines). It is **written to the run's `logs/` folder
as soon as the run finishes, fails or is stopped** — not only when the window
closes — and never twice for the same content. `Clear` and `Copy` act on the
view.

### Training images

Six thumbnails show the first training batch and the latest curves. Clicking any
of them opens a pager over **every** image the run has written — all train
batches, both validation batches, `results.png`, the PR/F1 curves, the confusion
matrix — with `←`/`→` or the Previous/Next buttons (wrapping at both ends), and
`Open in System Viewer` to hand the current one to the desktop's viewer.

### Actions

- `Open Directory` — the run folder.
- `Previous` — back to the Config tab.
- `Start Training` — one click; it becomes disabled while the dataset is being
  prepared.
- `Stop Training` — asks first, then terminates the worker process tree.
- `Resume Training` — appears after a stop, when `weights/last.pt` is resumable.
- `Export` — after a successful run.
- `用于自动标注` — export to ONNX and load into the auto-labeling panel.

### Stopping and resuming

A stopped run keeps its `weights/last.pt` (epoch + optimizer state), so it can
continue instead of starting over:

- `Resume Training` on the Train tab continues the current run directly.
- Starting again from the Config tab offers **Resume** for an existing run
  directory, next to `Use Existing Model` (export what is there) and
  `Retrain (overwrite)` (the destructive option, with its own confirmation).
- Resume is only offered when the checkpoint is really resumable — a run that
  finished its epochs has no optimizer state left, and is correctly not offered.
- Ultralytics restores project, epochs and every hyperparameter **from the
  checkpoint**; the device can still be changed (handy when moving between
  machines), and the dataset is rebuilt with the pinned split seed and handed
  over as a data override, so a pruned dataset copy does not break the resume.
- Resume ignores config-form changes to epochs/batch/imgsz; the log says so when
  the run starts.

### When a run fails

The dialog names the cause (Windows exit codes are translated) and, when the
cause is one it can act on, offers the fix as the default button:

| Symptom | Button | What it changes |
| :--- | :--- | :--- |
| Out of memory (CUDA or system) | `Halve Batch & Retry` | batch size halved (from `-1` it lands on 8) |
| Exit code `-1073741819` / `-1073740940` (access violation / heap corruption) | `Set Workers to 0 & Retry` | workers → 0 |
| No usable CUDA device | `Switch to CPU & Retry` | device → cpu (and the CPU adaptations above) |

`Retry Training` (as-is) and `Back to Config` are always there. The fix is
applied to the form and written to the log before the retry starts, and the full
traceback stays in the log view.

## Outputs

```
<work_dir>/xanylabeling_data/trainer/ultralytics/
├── weights/                       downloaded pretrained .pt (cache)
├── data/                          generated class-list YAMLs
├── datasets/<task>/<name>_<stamp>/    one build per run
│   ├── images/{train,val}/  labels/{train,val}/   (copied on Windows, symlinked elsewhere)
│   ├── data.yaml                  what Ultralytics actually reads
│   └── manifest.json              every label file + content hash, split, classes, seed
└── runs/<task>/<name>/
    ├── weights/best.pt, last.pt
    ├── results.csv                the progress/metrics source
    ├── args.yaml                  the exact arguments
    ├── plots (PR/F1 curves, confusion matrix, batches — when enabled)
    ├── logs/training_log_<status>_<stamp>.txt
    └── run_meta.json              weights hash, train args, dataset manifest hash + counts, metrics
```

After a run the panel may offer to delete old dataset copies — they are full
image copies, so the folder only grows otherwise. The most recent five builds
plus the one the finished run used are always kept, and only if the candidates
exceed 100 MB does it ask.

## Export

`Export` writes the run's `best.pt` to any of 14 formats: ONNX, TorchScript,
OpenVINO, TensorRT, CoreML, TensorFlow SavedModel / Lite / Edge TPU / TF.js,
PaddlePaddle, MNN, NCNN, IMX500, RKNN (several need extra packages; the dialog
says so).

`用于自动标注` is the shortcut that closes the loop: it exports ONNX into
`weights/` beside the checkpoint, writes the model YAML the panel needs (name,
classes — for pose, the same keypoint mapping training used — and a confidence
threshold of 0.25, or 0.0 for classifiers so a top-k suggestion is never
filtered out), loads it as a pinned custom model, and then offers to re-predict
the folder. That re-prediction skips 已确认 empty labels (negatives) and, when it
finishes, the 迭代收益看板 updates with what the round produced.

## Run history

`训练 → 实验历史` tables every run that wrote `run_meta.json`: metrics, seed,
dataset size, iteration round, weights/manifest hashes and timestamps, newest
first, with CSV export and an "open this run's directory" action. Runs trained
into a custom `Project` path are outside the scanned folder and the dialog says
which folder it looked at.

## CPU-only training

Everything above works without a GPU — it is just slower per epoch:

- The form switches AMP off and fills the CPU preset (50 epochs at 416, batch 8)
  unless you already changed those fields, so a first pass can tell you whether
  the data is right within a reasonable time.
- Ultralytics forces dataloader workers to 0 on CPU; leave `Workers` alone.
- `win-cpu-train` packaging (`scripts/build_executable.sh win-cpu-train`,
  `packaging/pyinstaller/specs/x-anylabeling-win-cpu-train.spec`) bundles CPU
  torch and Ultralytics for machines that have no CUDA at all.

## Troubleshooting

| Symptom | Fix |
| :--- | :--- |
| The menu entry says Ultralytics is missing | `pip install ultralytics` (or `uv pip install ultralytics --torch-backend=auto`) in the environment the app runs from; the frozen `win-cpu-train` build already has it. |
| `Halve Batch & Retry` offered | Training ran out of memory — accept, or lower `Batch`/`Image Size` yourself. |
| Worker crashed with an access violation | Accept `Set Workers to 0 & Retry`, or switch to CPU. |
| Training looks frozen at 0/N | The first epochs are the slowest (model load, cache build); the progress bar shows elapsed time, then switches to epochs. Watch the log for real progress. |
| `Resume Training` is missing after a run finished | A completed run strips its optimizer state; there is nothing to resume — start a new training instead. |
| A new run overwrote my old one | `Retrain (overwrite)` deletes the run directory (with a confirmation listing what is inside). Change `Name` to keep both. |
| Training runs on the wrong GPU | Pick the GPUs next to `Device`; on a multi-GPU box every GPU is ticked by default. |

## Related docs

- [Installation & Quickstart](../../../docs/en/get_started.md)
- [Usage](../../../docs/en/user_guide.md)
- [Customize a model](../../../docs/en/custom_model.md) — what the exported ONNX
  becomes in the auto-labeling panel
- [Fork-only features](../../../docs/zh_cn/fork_features.md) — the review
  workflow, smart tools and iteration dashboard the loop depends on (Chinese)