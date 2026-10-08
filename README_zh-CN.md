<div align="center">
  <h1>JLLabelingAndTrain</h1>
  <p><b>高级自动标注与训练工具</b></p>
  <p>基于 <a href="https://github.com/CVHub520/X-AnyLabeling">X-AnyLabeling</a> 的单机桌面分支，围绕「标注 → 复核 → 训练 → 回灌」闭环构建</p>
  <p>
    <a href="https://github.com/18961389539/LabelAndTrain/" target="_blank">
      <img alt="JLLabelingAndTrain" height="200px" src="https://github.com/user-attachments/assets/0714a182-92bd-4b47-b48d-1c5d7c225176"></a>
  </p>

[简体中文](README_zh-CN.md) | [English](README.md)

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
<summary><strong>自动训练</strong></summary>

<video src="https://github.com/user-attachments/assets/c0ab2056-2743-4a2c-ba93-13f478d3481e" width="100%" controls>
</video>
</details>

<details>
<summary><strong>自动标注</strong></summary>

<video src="https://github.com/user-attachments/assets/f517fa94-c49c-4f05-864e-96b34f592079" width="100%" controls>
</video>
</details>

<details>
<summary><strong>分割一切（SAM2）</strong></summary>

<img src="https://github.com/user-attachments/assets/208dc9ed-b8c9-4127-9e5b-e76f53892f03" width="100%" />
</details>

## 这个构建是什么

**JLLabelingAndTrain** 是 [X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) 的下游分支，保留其标注引擎、画布交互与模型插件结构，是**单机、单用户**工具：一个图片目录加一个标签 JSON 目录，没有服务端、账号与任务分配。

分支新增的是标注之外的那条闭环：每张图的复核状态、每个对象的来源记录、阈值校准、主动学习样本排序、Ultralytics 训练面板，以及一键把刚训好的权重回灌为自动标注模型 —— 并能报告上一轮模型留在数据里的结果。

命令只有 `jllabelingandtrain`，没有 `xanylabeling` 别名，文档里的命令同样如此。仍然带 "anylabeling" 字样的，都是改名会丢数据或丢掉上游可合并性的那几处：`~/.xanylabelingrc`、`<work_dir>/xanylabeling_data/`（权重、数据集、训练产物）、`xanylabeling_logs/`、Qt 设置域，以及 Python 包名 `anylabeling` 本身。

界面只有一种语言：简体中文（`zh_CN` 是唯一的翻译目录且总是加载）。上游的英文源文本靠该目录译成中文，而本分支新增的文案直接以中文写入。

## 快速开始

只能源码安装，见[安装文档](./docs/zh_cn/get_started.md)。

1. **打开目录**（`Ctrl+U`；`Ctrl+I` 打开单张图片）：图片从目录读取，每张图的标签 JSON 与图片同名同目录。
2. **标注，或让模型先标**：在右侧面板选一个自动标注模型（SAM2 需要点几下提示，YOLO 直接跑），或用 `一键推理` 对当前打开目录批量推理。
3. **复核**：把每张图标为「已检查」或「需返工」（`Ctrl+Shift+J` / `Ctrl+Shift+K`），让复核筛选器带你把剩下的走完。
4. **训练**（`Training → Ultralytics`）：在「数据」页选任务类型，配置页保持默认即可（权重首次使用会自动下载），点「开始训练」。详见[训练指南](./examples/training/ultralytics/README_zh-CN.md)。
5. **回灌**：`用于自动标注` 会把本次运行的 `best.pt` 导出为 ONNX、载入为自动标注模型，并询问是否重新推理整个目录；迭代收益看板随后报告上一轮模型留下的框代价几何。
6. **循环**：训练/验证划分按数据集固定，下一轮的 mAP 与本轮可比。

界面上几乎所有内容都有悬停说明 —— 字段、按钮、筛选器与列表行都会讲清自己的作用。

## 分支范围

相比上游，本构建**不包含**：

- 远程推理服务（X-AnyLabeling-Server）；不支持视频、音频、点云输入 —— **仅图片**（Qt 能读取的格式，外加 HEIC）。
- 上游约 90 个模型的库。本构建只有 **8 种可加载模型类型**，内置配置文件只有 **2 个**（SAM2 tiny/base），其余需以自定义模型 YAML 注册。
- 已裁掉的任务面板：OCR / PPOCR / KIE、视觉问答、聊天机器人、文档解析（PaddleOCR-VL）、图像打标与描述、人脸估计、深度估计、目标计数、视觉定位、图像抠图、车道线检测、多目标跟踪、交互式视频分割。
- 大部分交换格式：`DOTA`、`MOT`、`MASK`、`PPOCR`、`MMGD`、`VLM-R1`、`ShareGPT` 已移除，见[标签格式](#标签格式)。
- 可切换的界面语言：本构建只带 `zh_CN`。

仓库内仍保留了被裁功能的文档与示例（如 `docs/zh_cn/chatbot.md`、`examples/grounding/`），它们描述的是**上游**能力，不是本构建。

本分支新增的功能过去只写在 `CHANGELOG.md` 里，现在有独立文档页：[`docs/zh_cn/fork_features.md`](./docs/zh_cn/fork_features.md)（项目管理、复核状态流程、十一个智能工具、训练闭环、形状溯源）。旁边还有过程文档，例如 [`docs/zh_cn/split_verification_2026-09-28.md`](./docs/zh_cn/split_verification_2026-09-28.md)（label_widget 拆分批次的机器核对清单）与 [`docs/zh_cn/controller_extraction_roadmap.md`](./docs/zh_cn/controller_extraction_roadmap.md)（契约成员与下一步抽取路线）。

## 特性

### 标注

- 形状：`矩形`、`多边形`（含笔刷涂抹）、`旋转框`、`长方体`、`四边形`、`圆形`、`直线`、`折线`、`点`。
- 单个对象：类别、群组编号、描述、困难样本标记、自由标志位、属性，以及"锁定"（编辑时不干扰其它对象）。
- 画布：缩放/平移、亮度对比度、十字辅助线、顶点编辑与键盘微调、**跨图片保留的撤销栈**（最多 20 张，LRU）、保留上一张叠加显示、缩略图条。
- 标签列表：搜索、类别筛选、群组编号筛选、显示/锁定开关，以及对象行的悬停卡片（类别、形状、产出模型、置信度、顶点数、外接框、属性、描述、锁定/困难/隐藏）。

### 自动标注

- **SAM2**：既可作为交互式提示模型（点/框提示，逐个对象），也可免提示地对整张图自动生成掩码。
- **YOLO**：检测、实例分割、姿态与分类，另有 `yolov8_sam2` 组合模型。
- `一键推理`：对当前打开目录的全部图片批量推理 —— 可中断、可跳过已标注图片，结束后给出处理失败清单。
- 不改源码即可扩展模型：在界面里指向一个模型 YAML（最多 30 个；迭代产生的模型被固定，不会被自动淘汰）。
- 推理后端：ONNX Runtime（CPU / CUDA）、TensorRT、OpenCV DNN。

### 复核与质量

- 每张图记录 `review_state`（`未检查` / `已检查` / `需返工`）与 `reviewed_at`；旧的 `checked` 字段继续写入，兼容老工具。
- 筛选器与进度统计跟随复核状态；`Ctrl+Shift+D` 跳到下一张未检查图片，`Ctrl+Shift+J` / `Ctrl+Shift+K` 确认或打回并前进。
- 智能复核按不确定度排序（低置信度、框数少、模型分歧），让复核从最值得看的地方开始。

### 溯源与返工

- 每个对象记录是人画的还是模型产出的、哪个模型，以及该模型权重文件的内容摘要（`model_version`）—— 同名 `best.onnx` 被重新训练覆盖后，上一轮的框依然认得出来。
- 「旧轮模型框盘点」按产出模型分组列出可清理项，锁定与来源不明的对象不参与，删除前自动快照受影响文件。

### 智能工具

「智能工具」菜单（与其它分支自研界面一样，直接使用中文）：阈值校准、数据智能分析、漏标扫描、迭代收益看板、智能复核跳转、标注传播、一键去重归档、训练建议、智能模板预标注、旧轮模型框盘点、从备份恢复标注。复核队列为完整排序结果，只有数据体检对话框按每类 100 条显示并在标题标注真实总数。

### 项目管理与设置

- 每个数据集的记录写在 `.jllabel/project.json`：类别表、复核计数、训练/验证划分种子、上次训练参数，以及其它属于「这个目录」而非「这台机器」的选择。
- 项目切换器让你在数据集之间走动而不用翻目录；按数据集的筛选选择在重启后保留。
- 设置对话框管理全局行为（自动保存、模型下载源、阈值、路径），也管理**快捷键**：共 118 个键位，96 个已绑定、22 个刻意留空且可自行绑定；`F1` 速查表在没有绑键时会列出「未绑定动作」一节。

### 可复现与可回退

- 每次数据集构建写出 `manifest.json`（逐文件内容哈希、划分归属、类别表、种子），每次训练结束写出 `run_meta.json`（权重哈希、实际参数、manifest 哈希、指标）—— 结果因此能追回到当时的标注与参数。
- 划分种子按数据集固定，使相邻轮次的指标可比。
- 删除当前打开图片的框就是一次普通 Ctrl+Z（一次撤销整批）；画布之外的文件改动前先快照到 `.label_backups/<时间戳>/`，每个标签文件在会话内首次写入前还会留一份自动快照，「智能工具 → 11. 从备份恢复标注」可把任意快照写回（写回前先把被覆盖的版本另存一份）。

## 可加载模型类型

| 任务 | 类型 |
| :--- | :--- |
| 目标检测 | `yolov8`、`yolo26` |
| 实例分割 | `yolov8_seg`、`yolo26_seg` |
| 姿态估计 | `yolo26_pose` |
| 图像分类 | `yolov8_cls` |
| 分割一切 | `segment_anything_2`、`yolov8_sam2` |

内置配置仅 `sam2_hiera_base`、`sam2_hiera_tiny`；其他模型请按[自定义模型](./docs/zh_cn/custom_model.md)注册。

## 标签格式

| 方向 | YOLO（hbb / seg / obb / pose） | VOC | COCO |
| :--- | :--- | :--- | :--- |
| 图形界面 | 导入 + 导出 | 仅命令行 | 仅命令行 |
| 命令行 `convert` | 支持 | 支持 | 支持（导入暂不支持 RLE） |

原生格式为 XLABEL JSON（每图一个 `*.json`，含 `checked` / `review_state` / `shapes[]`，每个 shape 带 `source` 与 `model`）。

批量导出会在输出目录旁写一份 `export_manifest.json`：类别表**及其来源**、导出模式、当时开着的过滤器（仅已确认 / 跳过空标注 / 复制图片 / `classes.txt`）、本次运行的各项计数，以及导出前预检发现的问题。它存在的意义是让「这批数据当时是怎么导出的」在几个月后仍然可答。

## 训练闭环

```
标注 → 复核（已检查 / 需返工）→ 仅用已检查图片训练
     → best.pt 导出 ONNX → 载入为自动标注模型
     → 全量重推 → 盘点上一轮模型留下的框
```

- 仅 Ultralytics，四类任务（检测 / 分割 / 姿态 / 分类），约 40 项可调参数，独立进程运行，可中止、**可从断点续训**，并提供三档一键预置（快速验证 / 标准 / 高精度）。
- 纯 CPU 机器上表单会自动适配：AMP 关闭并禁用，未修改的 epochs/batch/imgsz 填入 CPU 友好档，状态区会区分「准备数据集」并给出预计剩余时间。
- 只有「已检查」图片进入数据集，空标注图片作为背景负样本保留；数据集按固定种子在每次训练前重建。
- 「用于自动标注」覆盖检测、分割、姿态（需与训练一致的 pose 配置）与分类；分类返回可确认的建议而非对象。
- 14 种导出格式（ONNX、TorchScript、OpenVINO、TensorRT、CoreML、TF SavedModel / Lite / Edge TPU / TF.js、PaddlePaddle、MNN、NCNN、IMX500、RKNN）。
- 训练产物位于 `<work_dir>/xanylabeling_data/trainer/ultralytics/runs/<task>/`；训练结束会提示清理历史数据集副本。
- 「训练 → 实验历史」列出所有写出 `run_meta.json` 的运行（按完成时间倒序、标注所属轮次），可导出 CSV；自定义 Project 路径下的运行不在扫描范围内，对话框会说明所扫描的目录。

完整走查 —— 数据要求、每一项设置、续训规则、CPU 训练、报错处置与产物位置 —— 见[训练指南](./examples/training/ultralytics/README_zh-CN.md)（[English](./examples/training/ultralytics/README.md)）。

## 文件放在哪里

```
<work_dir>/                          默认是用户主目录，--work-dir 可覆盖
├── .xanylabelingrc                  应用设置
├── xanylabeling_logs/               轮转的应用日志
└── xanylabeling_data/
    ├── models/                      自动标注模型权重下载目录
    └── trainer/ultralytics/
        ├── weights/                 训练用预训练权重下载目录
        ├── data/                    自动生成的类别表 YAML
        ├── datasets/<task>/         每次训练构建的数据集副本
        └── runs/<task>/<name>/      weights/、results.csv、run_meta.json、logs/
```

你的图片与标签 JSON 留在原地；写在它们旁边的只有可选的 `.jllabel/` 项目记录与 `.label_backups/` 快照。

## 本分支近期变化

更完整的历史见 [CHANGELOG](./CHANGELOG.md)。

- `2026-09-30`：训练面板完成一轮可用性改造 —— 从断点续训、三档参数预置、CPU 自适应（AMP 关闭 + CPU 预置档）、预计剩余时间、失败一键修复（批大小减半 / Workers 归零 / 改用 CPU）、训练图片内置翻页器、日志在终态落盘并限长、配置页全部中文化；训练指南补齐中文版。
- `2026-09-30`：训练表单不再空着 —— Model 提供按任务分组的预训练权重预置并自动下载（下载在训练子进程内完成），Data 按当前标注目录自动生成类别表 YAML，`开始训练` 一步启动，分类任务可留空 Data；「准备数据集」成为独立状态，参数补齐悬停说明。
- `2026-09-29`：导出写入 `export_manifest.json`（类别来源、过滤器、计数、预检结果）；22 个无键动作可绑定（共 118 键：96 绑定 + 22 留空），F1 速查表随之清空"幽灵键"；撤销栈跨图片保留（每图一套，LRU 20）；每个标签文件会话内首次写入前留自动快照（可在「从备份恢复标注」中找回）。
- `2026-09-23`：悬停提示补全；命名收口（只留 `jllabelingandtrain` 命令）；对象来源补 `model_version`；批量删除旧轮模型框可撤销并新增「从备份恢复标注」；界面语言说法与代码对齐（只加载 `zh_CN`）；数据体检复核队列不再被静默截断；新增「训练 → 实验历史」。
- `2026-09-22`：复核状态扩展为 `未检查 / 已检查 / 需返工`；每个对象记录来源；训练可复现（`manifest.json` + `run_meta.json`）；划分种子按数据集固定；打通姿态与分类的回灌；自定义模型上限 5 → 30。
- `2026-09-21`：新增最小 CI（推送与 Pull Request 跑全量测试）；分支自有版本号，并修复若干静默失败。

## 文档

1. [安装文档](./docs/zh_cn/get_started.md)
2. [用户手册](./docs/zh_cn/user_guide.md)
3. [本分支独有功能](./docs/zh_cn/fork_features.md) —— 项目管理、复核状态、智能工具、训练迭代、溯源信息
4. [命令行界面](./docs/zh_cn/cli.md)
5. [自定义模型](./docs/zh_cn/custom_model.md)
6. [训练指南](./examples/training/ultralytics/README_zh-CN.md)
7. [常见问题答疑](./docs/zh_cn/faq.md)

以下文档描述的是**上游**功能，本构建已移除对应面板，仅作归档参考：
[聊天机器人](./docs/zh_cn/chatbot.md)、
[视觉问答](./docs/zh_cn/vqa.md)、
[图像分类器](./docs/zh_cn/image_classifier.md)、
[文档解析](./docs/zh_cn/paddle_ocr.md)、
[模型库](./docs/zh_cn/model_zoo.md)。

## 示例

本构建可实际完成的示例：

- [分类](./examples/classification/) —— 图像级与对象级
- [检测](./examples/detection/) —— [水平框](./examples/detection/hbb/README.md)、[旋转框](./examples/detection/obb/README.md)
- [分割](./examples/segmentation/README.md) —— 实例分割、二分类与多分类语义分割
- [训练](./examples/training/ultralytics/README_zh-CN.md) —— Ultralytics 训练面板（中英对照）

`examples/` 下的 `optical_character_recognition`、`multiple_object_tracking`、
`interactive_video_object_segmentation`、`matting`、`estimation`、`counting`、
`grounding`、`vision_language`、`description` 等目录保留自上游，对应的模型与面板不在本构建中。

## 开发

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[cpu]" pytest
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests
```

可选依赖组：`cpu`、`gpu`（CUDA 12）、`gpu-cu11`、`gpu-cu13`、`dev`；Python 3.11+。

打包走 `scripts/build_executable.sh`，每个目标一份 PyInstaller spec：`win-cpu`、`win-cpu-train`（打包 CPU 版 torch 与 Ultralytics，冻结后的程序也能训练）、`win-gpu`、`linux-cpu`、`linux-gpu`、`macos`。

`.github/workflows/ci.yml` 会在推送到 `main` 与提交 Pull Request 时运行全量测试；格式化与静态检查见[贡献指南](./CONTRIBUTING.md)，其中 lint 采用**基线**门禁：历史遗留告警记录在 `scripts/flake8_baseline.txt`，只有新增告警才会失败。

## 贡献指南

欢迎社区协作！无论是修复 Bug、优化文档还是添加新功能，都请在提交 Pull Request 前阅读[贡献指南](./CONTRIBUTING.md)并确认同意[贡献者许可协议 (CLA)](./CLA.md)。如果这个项目对你有帮助，欢迎点亮右上角的 ⭐；与上游行为相关的问题请到 [X-AnyLabeling issues](https://github.com/CVHub520/X-AnyLabeling/issues) 反馈。

## 赞助

| **微信支付** | **支付宝** |
| :---: | :---: |
| <img src="https://github.com/user-attachments/assets/0178cf76-3627-426e-8432-ec031c9278ae" width="400px" height="400px" style="object-fit: contain;" /> | <img src="https://github.com/user-attachments/assets/87544ff8-3560-4696-b035-1fd26ecd162b" width="400px" height="400px" style="object-fit: contain;" /> |

感谢您的支持！

## 许可

本项目遵循 [GPL-3.0 license](./LICENSE)，完全开源免费（含商用）。

本仓库是 Wei Wang / CVHub 所开发的 [X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) 的衍生作品。按上游许可条款要求，二次开发并商业化时必须保留上游品牌标识并注明源项目地址 —— 本文件、程序状态栏与关于信息中均已保留。

此外，上游要求学术、科研、教学或企业使用者填写其[登记表](https://forms.gle/MZCKhU7UJ4TRSWxR7)（仅用于统计，不产生费用）。

## 致谢

[X-AnyLabeling](https://github.com/vietanhdev/anylabeling)、
[AnyLabeling](https://github.com/vietanhdev/anylabeling)、
[LabelMe](https://github.com/wkentaro/labelme)、
[LabelImg](https://github.com/tzutalin/labelImg)、
[roLabelImg](https://github.com/cgvict/roLabelImg)、
[PPOCRLabel](https://github.com/PFCCLab/PPOCRLabel) 与
[CVAT](https://github.com/opencv/cvat)。

## 引用

如果您在研究中使用了这个软件，请按照以下方式引用它：

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

<div align="center"><a href="#top">🔝 返回顶部</a></div>