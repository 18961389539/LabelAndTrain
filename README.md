<div align="center">
  <h1>JLLabelingAndTrain</h1>
  <p><b>Advanced Auto Labeling &amp; Training Tool</b></p>
  <p>a single-user desktop fork of <a href="https://github.com/CVHub520/X-AnyLabeling">X-AnyLabeling</a>, built around the label → review → train → auto-label loop</p>
  <p>
    <a href="https://github.com/18961389539/LabelAndTrain/" target="_blank">
      <img alt="JLLabelingAndTrain" height="200px" src="https://github.com/user-attachments/assets/0714a182-92bd-4b47-b48d-1c5d7c225176"></a>
  </p>

[English](README.md) | [简体中文](README_zh-CN.md)

</div>

<p align="center">
    <a href="./LICENSE"><img src="https://img.shields.io/badge/License-GPL%20v3-blue.svg"></a>
    <a href="https://github.com/18961389539/LabelAndTrain/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/18961389539/LabelAndTrain/ci.yml?label=CI"></a>
    <a href=""><img src="https://img.shields.io/badge/python-3.11+-aff.svg"></a>
    <a href=""><img src="https://img.shields.io/badge/os-linux%2C%20win%2C%20mac-pink.svg"></a>
</p>

<video src="https://github.com/user-attachments/assets/25957cae-4dbd-494c-9923-e959d985674e" width="100%" controls>
</video>

<details>
<summary><strong>Auto-Training</strong></summary>

<video src="https://github.com/user-attachments/assets/c0ab2056-2743-4a2c-ba93-13f478d3481e" width="100%" controls>
</video>
</details>

<details>
<summary><strong>Auto-Labeling</strong></summary>

<video src="https://github.com/user-attachments/assets/f517fa94-c49c-4f05-864e-96b34f592079" width="100%" controls>
</video>
</details>

<details>
<summary><strong>Segment Anything (SAM2)</strong></summary>

<img src="https://github.com/user-attachments/assets/208dc9ed-b8c9-4127-9e5b-e76f53892f03" width="100%" />
</details>

## What this build is

**JLLabelingAndTrain** is a downstream fork of
[X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) and keeps its
annotation engine, canvas and model plug-in architecture. It is deliberately
**local and single-user**: one folder of images plus one folder of label JSONs,
no server, no accounts, no task assignment.

What the fork adds is the loop around annotation: review state per image,
provenance per shape, threshold calibration, active-learning sample ranking, an
Ultralytics training panel, and a one-click path that feeds the freshly trained
weights back into auto labeling — then reports what the previous round's model
left behind.

The command is `jllabelingandtrain`, and nothing else: there is no
`xanylabeling` alias, and the docs say so. The names that still read
"anylabeling" are the ones where a rename would cost you data or mergeability —
`~/.xanylabelingrc`, `<work_dir>/xanylabeling_data/` (weights, datasets,
training runs), `xanylabeling_logs/`, the Qt settings domain, and the Python
package `anylabeling` itself.

The interface ships one language: Simplified Chinese (`zh_CN` is the only
catalog and it is always loaded). Upstream text is English source translated by
that catalog; text this fork adds is written in Chinese directly.

## Quick start

Installation is source-only — see [Installation & Quickstart](./docs/en/get_started.md).

1. **Open a folder** (`Ctrl+U`; `Ctrl+I` opens a single image). Images are read
   from the folder, and each label JSON lives beside its image under the same
   stem.
2. **Annotate or let a model do it.** Pick an auto-labeling model in the
   panel on the right (SAM2 wants a click or two, YOLO just runs), or use
   `一键推理` to run the current model over the whole open folder.
3. **Review.** Mark every image 已检查 (confirmed) or 需返工 (needs rework) —
   `Ctrl+Shift+J` / `Ctrl+Shift+K` — and let the review filters walk you
   through what is left.
4. **Train** (`Training → Ultralytics`). Pick the task on the Data tab, keep the
   defaults on the Config tab (weights download on first use), and press
   `Start Training`. See the [training guide](./examples/training/ultralytics/README.md).
5. **Feed it back.** `用于自动标注` exports the run's `best.pt` to ONNX, loads it
   as an auto-label model and offers to re-predict the folder; the iteration
   dashboard then reports what the previous round's boxes cost you.
6. **Repeat.** The train/val split is pinned per dataset, so the next round's
   mAP is comparable with this one.

Every screen explains itself on hover — field labels, buttons, filters and rows
carry a tooltip saying what they do.

## Fork scope

This is a trimmed build. Compared with upstream it does **not** include:

- Remote inference service (X-AnyLabeling-Server), video, audio or point-cloud input — **images only** (any format Qt can read, plus HEIC).
- The ~90-model upstream zoo. This build ships **8 loadable model types** and **two** built-in config files (SAM2 tiny/base); everything else is registered by you as a custom model YAML.
- Pruned task panels: OCR / PPOCR / KIE, VQA, chatbot, document parsing (PaddleOCR-VL), tagging & captioning, face estimation, depth, counting, grounding, matting, lane detection, multi-object tracking, interactive video segmentation.
- Most exchange formats: `DOTA`, `MOT`, `MASK`, `PPOCR`, `MMGD`, `VLM-R1`, `ShareGPT` are gone. See [Formats](#label-formats).
- A translatable UI: only `zh_CN` ships.

Docs and examples for pruned features are still in the tree (`docs/en/chatbot.md`,
`examples/grounding/`, …). They describe **upstream**, not this build.

The features this fork *adds* used to be documented nowhere but `CHANGELOG.md`.
They now have a page of their own — project management, the review-state
workflow, the eleven smart tools, the training loop and shape provenance:
[`docs/zh_cn/fork_features.md`](./docs/zh_cn/fork_features.md). It is in Chinese
on purpose; Chinese is the source language for everything this fork owns (see
above), and the interface it describes only ships `zh_CN`.
Process documents live next to it — e.g.
[`docs/zh_cn/split_verification_2026-09-28.md`](./docs/zh_cn/split_verification_2026-09-28.md),
the machine-verification checklist that gated the label-widget split batches.
[`docs/zh_cn/controller_extraction_roadmap.md`](./docs/zh_cn/controller_extraction_roadmap.md)
maps what the contract still owns and where the next extractions would go.

## Features

### Annotation

- Shapes: `rectangle`, `polygon` (with brush painting), `rotation` (OBB),
  `cuboid`, `quadrilateral`, `circle`, `line`, `linestrip`, `point`.
- Per shape: label, group id, description, difficulty flag, free-form flags,
  attributes, and a lock that keeps it out of the way while you edit.
- Canvas: zoom/pan, brightness & contrast, crosshair, vertex editing with
  keyboard nudges, per-image undo that survives switching files (up to 20
  images), keep-previous-image overlays, and a thumbnail strip.
- Label list: search, class filters, group-id filters, visibility/lock toggles,
  and a per-object hover card (class, shape, producer, confidence, vertex
  count, bounding box, attributes, description, protection state).

### Auto-labeling

- **SAM2** as an interactive prompt model (click/box prompts, one object at a
  time) and as prompt-free automatic mask generation over a whole image.
- **YOLO** detection, instance segmentation, pose and classification, plus a
  `yolov8_sam2` combination model.
- `一键推理` runs the current model over every image in the open folder — it can
  be cancelled, can skip images that already have labels, and ends with a
  failure report listing whatever it could not process.
- Custom models without touching source: point the UI at a model YAML (up to 30
  stored; models produced by an iteration are pinned and never evicted).
- Backends: ONNX Runtime (CPU / CUDA), TensorRT, OpenCV DNN.

### Review & quality

- Every image carries `review_state` (`unchecked` / `confirmed` / `rejected` —
  未检查 / 已检查 / 需返工) plus `reviewed_at`; the legacy `checked` field is
  still written so older tools keep working.
- Filters and progress counts follow the review state; `Ctrl+Shift+D` opens the
  next unchecked image, `Ctrl+Shift+J`/`Ctrl+Shift+K` confirm or send back and
  move on.
- 智能复核 walks the images ranked by uncertainty (low confidence, few shapes,
  model disagreement), so the review session starts where it matters.

### Provenance & rework

- Every shape records whether a human or a model drew it, which model, and a
  content digest of that model's weights (`model_version`) — so retraining over
  `best.onnx` under the same name does not hide the previous round's boxes.
- 旧轮模型框盘点 lists boxes by producing model with stale ones ticked for
  removal; locked and unattributed shapes never participate, and affected files
  are snapshotted before the write.

### Smart tools

The 智能工具 menu (Chinese-labelled, like every fork-added surface):
threshold calibration, dataset analysis, missed-label scan, iteration dashboard,
review-jump queue, label propagation, duplicate archiving, training advice,
template pre-labeling, stale model-box audit, and restore-from-backup. The
review-jump queue holds every uncertain image; only the audit dialog limits what
it lists (100 per category, with the real total in the heading).

### Project management & settings

- Per-dataset record in `.jllabel/project.json`: class list, review counts,
  train/val split seed, last training tuning, and other choices that belong to
  *this* folder rather than to the machine.
- A project switcher to move between datasets without hunting for folders, and
  per-dataset filters that survive restarts.
- Settings dialog for global behaviour (auto-save, model hub, thresholds,
  paths) — and for **shortcuts**: 118 keys ship, 96 bound and 22 deliberately
  unbound and rebindable; `F1` shows a cheat sheet that includes a 未绑定动作
  section while a key is unassigned.

### Reproducibility & recovery

- Each dataset build writes a `manifest.json` (every label file with its content
  hash, split assignment, class list and seed) and each finished run writes
  `run_meta.json` (weights hash, exact arguments, manifest hash, metrics), so a
  result can be tied back to the annotations and arguments that produced it.
- The split seed is pinned per dataset, so round N and round N+1 are comparable.
- Deleting boxes on the image currently open is an ordinary Ctrl+Z (one press
  undoes the whole batch). Files the canvas is not holding are snapshotted to
  `.label_backups/<stamp>/` before the write, a session snapshot is kept for the
  first write to each label file, and 智能工具 → 11. 从备份恢复标注 writes a
  chosen snapshot back after snapshotting what it replaces.

## Auto-labeling model types

| Task | Loadable types |
| :--- | :--- |
| Object detection | `yolov8`, `yolo26` |
| Instance segmentation | `yolov8_seg`, `yolo26_seg` |
| Pose estimation | `yolo26_pose` |
| Image classification | `yolov8_cls` |
| Segment anything | `segment_anything_2`, `yolov8_sam2` |

Built-in configs: `sam2_hiera_base`, `sam2_hiera_tiny`. Add your own through
[Customize a model](./docs/en/custom_model.md).

## Label formats

| Direction | YOLO (hbb / seg / obb / pose) | VOC | COCO |
| :--- | :--- | :--- | :--- |
| GUI menu | import + export | CLI only | CLI only |
| CLI `convert` | yes | yes | yes (import lacks RLE) |

Native format is the XLABEL JSON (`*.json` per image, `checked` /
`review_state` / `shapes[]` with `source` and `model`).

A batch export writes an `export_manifest.json` next to its output: the class
list *and where it came from*, the mode, which filters were on (仅已确认 /
跳过空标注 / 复制图片 / `classes.txt`), the counts the run reported, and what the
pre-export check found. It exists so "how was this batch exported" is answerable
months later.

## Training loop

```
annotate → review (confirmed / rejected) → train on checked files
        → export best.pt → ONNX → load as auto-label model
        → re-predict folder → report the previous round's boxes
```

- Ultralytics only, four tasks (Detect / Segment / Pose / Classify), ~40 tunable
  parameters, runs in a separate process that can be stopped and **resumed from
  its checkpoint**, with three one-click presets (快速验证 / 标准 / 高精度).
- On a CPU-only machine the form adapts: AMP is switched off, untouched
  epochs/batch/imgsz are filled with a CPU-friendly preset, and the status area
  reports the dataset build and an estimated time left.
- Only checked images enter the dataset; negatives (empty JSONs) are kept as
  background samples. The dataset is rebuilt per run from a pinned seed.
- `用于自动标注` covers detection, segmentation, pose (needs the same pose config
  as training) and classification; a classifier returns confirmable suggestions
  rather than shapes.
- 14 export formats (ONNX, TorchScript, OpenVINO, TensorRT, CoreML, TF
  SavedModel / Lite / Edge TPU / TF.js, PaddlePaddle, MNN, NCNN, IMX500, RKNN).
- Runs live under `<work_dir>/xanylabeling_data/trainer/ultralytics/runs/<task>/`;
  after a run the app offers to reclaim old dataset copies.
- `Training → 实验历史` (run history) tables every run that wrote `run_meta.json`,
  newest first, with the iteration round that produced it, and exports to CSV.
  Runs trained into a custom `Project` path are not listed, and the dialog says
  which folder it scanned.

The full walkthrough — data requirements, every setting, resume rules, CPU
training, error remedies and where the outputs land — is in the
[training guide](./examples/training/ultralytics/README.md)
([中文](./examples/training/ultralytics/README_zh-CN.md)).

## Where the files live

```
<work_dir>/                          ~ by default; --work-dir overrides it
├── .xanylabelingrc                  application settings
├── xanylabeling_logs/               rotating application log
└── xanylabeling_data/
    ├── models/                      downloaded auto-labeling weights
    └── trainer/ultralytics/
        ├── weights/                 downloaded pretrained .pt for training
        ├── data/                    generated class-list YAMLs
        ├── datasets/<task>/         one dataset build per training run
        └── runs/<task>/<name>/      weights/, results.csv, run_meta.json, logs/
```

Your images and label JSONs stay where you put them; the only thing written
beside them is the optional `.jllabel/` project record and `.label_backups/`.

## What's new in this fork

Recent, user-visible changes; the full history is in [CHANGELOG.md](./CHANGELOG.md).

- Training is a usable loop end to end: resume from a stopped run's checkpoint,
  one-click presets, CPU-aware defaults, an estimated time left, a failure
  dialog that offers the fix (halve the batch / reset workers / switch to CPU),
  an in-dialog pager over every training image, and logs written to disk when a
  run ends instead of only when the window closes.
- Training reproducibility: dataset `manifest.json` and per-run `run_meta.json`,
  plus a per-dataset split seed; `Training → 实验历史` tables the runs.
- Review as a first-class state: `未检查 / 已检查 / 需返工` with timestamps,
  filters, and a queue ranked by uncertainty.
- Provenance per shape (`source`, model name, weight digest) and the stale-box
  audit that uses it.
- Recovery: Ctrl+Z across images, `.label_backups` snapshots, session snapshots
  and 从备份恢复标注.
- Smart tools (11), hover detail nearly everywhere, rebindable shortcuts with an
  F1 cheat sheet, and a Chinese-only interface whose fork-added text is Chinese
  at the source.
- A CPU-only training build (`win-cpu-train`) that bundles CPU torch and
  Ultralytics.

## Docs

1. [Installation & Quickstart](./docs/en/get_started.md)
2. [Usage](./docs/en/user_guide.md)
3. [Command Line Interface](./docs/en/cli.md)
4. [Customize a model](./docs/en/custom_model.md)
5. [Training guide](./examples/training/ultralytics/README.md)

Fork-only features are documented in Chinese in
[`docs/zh_cn/fork_features.md`](./docs/zh_cn/fork_features.md), with
[FAQ](./docs/zh_cn/faq.md) beside it. The pages below describe **upstream**
features this build does not ship — they remain in the tree for reference:
[Chatbot](./docs/en/chatbot.md), [VQA](./docs/en/vqa.md),
[Image classifier](./docs/en/image_classifier.md),
[Document parsing](./docs/en/paddle_ocr.md),
[Model zoo](./docs/en/model_zoo.md).

## Examples

What this build can actually do end to end:

- [Classification](./examples/classification/) — image-level and shape-level
- [Detection](./examples/detection/) — [HBB](./examples/detection/hbb/README.md) and [OBB](./examples/detection/obb/README.md)
- [Segmentation](./examples/segmentation/) — instance, binary and multiclass semantic
- [Training](./examples/training/ultralytics/README.md) — the Ultralytics panel, in English and Chinese

The other directories under `examples/` (OCR, tracking, video segmentation,
matting, estimation, counting, grounding, vision-language, description) come
from upstream; their models and panels are not part of this build.

## Development

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[cpu]" pytest
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests
```

Extras: `cpu`, `gpu` (CUDA 12), `gpu-cu11`, `gpu-cu13`, `dev`. Python 3.11+.

Packaging goes through `scripts/build_executable.sh`, one PyInstaller spec per
target: `win-cpu`, `win-cpu-train` (bundles CPU torch + Ultralytics so training
works in the frozen app), `win-gpu`, `linux-cpu`, `linux-gpu`, `macos`.

`.github/workflows/ci.yml` runs the suite on every push to `main` and on pull
requests. Formatting and lint run through [pre-commit](./CONTRIBUTING.md); lint
is a **baseline** gate — the repo carries inherited findings in
`scripts/flake8_baseline.txt` and fails only when a change adds new ones.

## Contributing

Bug reports, documentation fixes and features are all welcome. Please read the
[contribution guide](./CONTRIBUTING.md) and confirm the
[CLA](./CLA.md) before opening a pull request. If this project helps you, a ⭐
on the repository is appreciated; issues about upstream behaviour belong in the
[X-AnyLabeling tracker](https://github.com/CVHub520/X-AnyLabeling/issues).

## Sponsor

| **WeChat Pay** | **Alipay** |
| :---: | :---: |
| <img src="https://github.com/user-attachments/assets/0178cf76-3627-426e-8432-ec031c9278ae" width="400px" height="400px" style="object-fit: contain;" /> | <img src="https://github.com/user-attachments/assets/87544ff8-3560-4696-b035-1fd26ecd162b" width="400px" height="400px" style="object-fit: contain;" /> |

## License

This project is licensed under the [GPL-3.0 license](./LICENSE). It is a
derivative work of [X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling)
by Wei Wang / CVHub, and per its terms the upstream brand and source address
must stay credited — here and in the about/status text of the application.

Upstream also asks academic, research, teaching and enterprise users to fill in
its [registration form](https://forms.gle/MZCKhU7UJ4TRSWxR7) (statistics only,
no cost).

## Acknowledgement

[X-AnyLabeling](https://github.com/vietanhdev/anylabeling),
[AnyLabeling](https://github.com/vietanhdev/anylabeling),
[LabelMe](https://github.com/wkentaro/labelme),
[LabelImg](https://github.com/tzutalin/labelImg),
[roLabelImg](https://github.com/cgvict/roLabelImg),
[PPOCRLabel](https://github.com/PFCCLab/PPOCRLabel) and
[CVAT](https://github.com/opencv/cvat).

## Citing

```
@misc{X-AnyLabeling,
  year = {2023},
  author = {Wei Wang},
  publisher = {Github},
  organization = {CVHub},
  journal = {Github repository},
  title = {Advanced Auto Labeling Solution with Added Features},
  howpublished = {\url{https://github.com/CVHub520/X-AnyLabeling}}
}
```

<div align="center"><a href="#top">🔝 Back to Top</a></div>