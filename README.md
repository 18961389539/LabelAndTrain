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
provenance per shape, threshold calibration, active-learning sample ranking, a
Ultralytics training panel, and a one-click path that feeds the freshly trained
weights back into auto labeling - then reports what the previous round's model
left behind.

The command is `jllabelingandtrain`, and nothing else: there is no
`xanylabeling` alias, and the docs say so. The names that still read
"anylabeling" are the ones where a rename would cost you data or mergeability —
`~/.xanylabelingrc`, `<work_dir>/xanylabeling_data/` (weights, datasets,
training runs), `xanylabeling_logs/`, the Qt settings domain, and the Python
package `anylabeling` itself.

## Fork scope

This is a trimmed build. Compared with upstream it does **not** include:

- Remote inference service (X-AnyLabeling-Server), video, audio or point-cloud input — **images only**.
- The ~90-model upstream zoo. This build ships **8 loadable model types** and **two** built-in config files (SAM2 tiny/base); everything else is registered by you as a custom model YAML.
- Pruned task panels: OCR / PPOCR / KIE, VQA, chatbot, document parsing (PaddleOCR-VL), tagging & captioning, face estimation, depth, counting, grounding, matting, lane detection, multi-object tracking, interactive video segmentation.
- Most exchange formats: `DOTA`, `MOT`, `MASK`, `PPOCR`, `MMGD`, `VLM-R1`, `ShareGPT` are gone. See [Formats](#formats).
- Japanese / Korean UI, and no English interface either: the only catalog is `zh_CN` and it is always the one loaded. Upstream text is English source translated by that catalog, while text this fork adds is written in Chinese directly - so Chinese is the source language for everything the fork owns.

Docs and examples for pruned features are still in the tree (`docs/en/chatbot.md`,
`examples/grounding/`, …). They describe **upstream**, not this build.

The features this fork *adds* used to be documented nowhere but `CHANGELOG.md`.
They now have a page of their own — project management, the review-state
workflow, the eleven smart tools, the training loop and shape provenance:
[`docs/zh_cn/fork_features.md`](./docs/zh_cn/fork_features.md). It is in Chinese
on purpose; Chinese is the source language for everything this fork owns (see
above), and the interface it describes only ships `zh_CN`.

## Features

- Auto-labeling: SAM2 interactive prompts, prompt-free automatic mask generation, YOLO detection / segmentation / pose / classification.
- One-click inference over the whole open folder, cancellable, with skip-existing and a failure report.
- Custom models without editing source: point the UI at a model YAML (up to 30 stored, iteration models are pinned and never evicted).
- Backends: ONNX Runtime (CPU / CUDA), TensorRT, OpenCV DNN.
- Annotation shapes: `rectangle`, `polygon` (with brush painting), `rotation` (OBB), `cuboid`, `quadrilateral`, `circle`, `line`, `linestrip`, `point`; per-shape lock, group id, description, difficulty, flags.
- Review workflow: every image carries `review_state` (`unchecked` / `confirmed` / `rejected`) plus a timestamp; filter and progress counts follow.
- Provenance: every shape records whether a human or a model drew it, and which model — plus a content digest of that model's weights, so retraining over `best.onnx` under the same name does not hide the previous round's boxes. "Send back for rework" and "clear the old round's boxes" stay answerable questions rather than guesses.
- Training: Ultralytics only, four tasks (Detect / Segment / Pose / Classify), ~40 tunable parameters, runs in a separate process that can be stopped or resumed, 14 export formats.
- Reproducibility: each build writes a dataset `manifest.json` (every label file with its content hash, split assignment, class list, seed) and each finished run writes `run_meta.json` (weights hash, exact arguments, manifest hash, metrics).
- Recovery: deleting boxes on the image currently open is an ordinary Ctrl+Z (one press undoes the whole batch). Files the canvas is not holding are snapshotted to `.label_backups/<stamp>/` before the write, and 智能工具 → 11. 从备份恢复标注 writes a chosen snapshot back after snapshotting what it replaces.
- Hover detail: an object row shows its class, shape, producer (model name + weight digest), confidence, vertex count and bounding box, attributes, description and what protects it (locked / difficult / hidden); a file row shows its path, label file, review state with timestamp and, for the open image, the model/human/unknown split. The floating panel's grip and collapse button, the zoom box, both filters and the preview sliders explain themselves the same way.
- Smart-tools set (Chinese-labelled menu 智能工具): threshold calibration, dataset analysis, missed-label scan, iteration dashboard, review-jump queue, label propagation, duplicate archiving, training advice, template pre-labeling, stale model-box audit. The review-jump queue holds every uncertain image; only the audit dialog limits what it lists (100 per category, with the real total in the heading).
- Settings survive restarts through a `Settings` dialog; per-dataset choices live in `.jllabel/project.json`.

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

## Formats

| Direction | YOLO (hbb / seg / obb / pose) | VOC | COCO |
| :--- | :--- | :--- | :--- |
| GUI menu | import + export | CLI only | CLI only |
| CLI `convert` | yes | yes | yes (import lacks RLE) |

Native format is the XLABEL JSON (`*.json` per image, `checked` /
`review_state` / `shapes[]` with `source` and `model`).

## Training loop

```
annotate → review (confirmed / rejected) → train on checked files
        → export best.pt → ONNX → load as auto-label model
        → re-predict folder → report the previous round's boxes
```

- Only checked images enter the dataset; negatives (empty JSONs) are kept as background samples.
- Split seed is pinned per dataset in `.jllabel/project.json`, so round N and round N+1 are comparable.
- `用于自动标注` covers detection, segmentation, pose (needs the same pose config as training) and classification; a classifier returns confirmable suggestions rather than shapes.
- Runs live under `<work_dir>/xanylabeling_data/trainer/ultralytics/runs/<task>/`; after a run the app offers to reclaim old dataset copies.
- `Training → 实验历史` (run history) tables every run that wrote `run_meta.json`, newest first, with the iteration round that produced it, and exports to CSV. Runs trained into a custom `Project` path are not listed, and the dialog says which folder it scanned.

## Docs

1. [Installation & Quickstart](./docs/en/get_started.md)
2. [Usage](./docs/en/user_guide.md)
3. [Command Line Interface](./docs/en/cli.md)
4. [Customize a model](./docs/en/custom_model.md)
5. [Model zoo (upstream)](./docs/en/model_zoo.md)

## Examples

- [Classification](./examples/classification/) — image-level and shape-level
- [Detection](./examples/detection/) — HBB and OBB
- [Segmentation](./examples/segmentation/) — instance, binary and multiclass semantic
- [Training](./examples/training/ultralytics/README.md)

## Development

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[cpu]" pytest
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests
```

`.github/workflows/ci.yml` runs the suite on every push to `main` and on pull
requests. Formatting and lint run through [pre-commit](./CONTRIBUTING.md); lint
is not a blocking CI job because the repo carries pre-existing findings.

## License

This project is licensed under the [GPL-3.0 license](./LICENSE). It is a
derivative work of [X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling)
by Wei Wang / CVHub, and per its terms the upstream brand and source address
must stay credited — here and in the about/status text of the application.

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
