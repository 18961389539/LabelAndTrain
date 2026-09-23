<div align="center">
  <h1>JLLabelingAndTrain</h1>
  <p><b>高级自动标注与训练工具</b>（基于 <a href="https://github.com/CVHub520/X-AnyLabeling">X-AnyLabeling</a> 的单机桌面分支，围绕「标注 → 复核 → 训练 → 回灌」闭环构建）</p>
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

![](https://user-images.githubusercontent.com/18329471/234640541-a6a65fbc-d7a5-4ec3-9b65-55305b01a7aa.png)

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

## 分支更新

- `2026-09-23`: 对象来源补上 `model_version`（加载模型权重文件的内容摘要，按 路径+大小+修改时间 缓存一次）。「旧轮模型框盘点」和删除判定因此能区分同名但已重训的权重；旧文件里没有该字段的框一律不视为陈旧，不会一夜之间变成清理对象。
- `2026-09-23`: 批量删除旧轮模型框不再丢失撤销机会：当前打开的图片改为在画布上删除（一次 Ctrl+Z 撤销整批），并新增「智能工具 → 11. 从备份恢复标注」，可把 `.label_backups` 里的任意一次快照写回（写回前另存当前版本）。
- `2026-09-23`: 界面语言的说法与代码对齐：本构建只有 `zh_CN` 一份翻译目录且总是加载它，README 不再声称可切换英文；两个翻译脚本改为处理实际存在的目录（以前会因为找不到其它语言的 `.ts` 而直接失败）；`language` 配成非 `zh_CN` 时给出明确警告；三处漏掉 `tr()` 的中文文案补上，并新增防复发测试。
- `2026-09-23`: 修复数据体检的复核队列被静默截断到 50 张：「智能复核」继承该列表，会在还有数百张待复核时报「已到复核队列末尾」。队列现在保持完整，截断只发生在显示层（每类 100 条）且标题写明总数，复核建议也不再计入「问题」总数。
- `2026-09-23`: 新增「训练 → 实验历史」：汇总每个 `run_meta.json`（指标、种子、数据量、manifest 与权重哈希），按完成时间倒序并与迭代轮次对齐，可导出 CSV；早于元数据功能的运行以数量提示，不显示为空行。
- `2026-09-22`: 复核状态扩展为 `未检查 / 已检查 / 需返工`（`review_state` + `reviewed_at`），新增「需返工」筛选与「打回并下一张」（Ctrl+Shift+K）；旧字段 `checked` 继续写入，训练筛选语义不变。
- `2026-09-22`: 每个对象记录来源（`source` = 人工 / 模型 / 未知，以及产出模型名），新增「旧轮模型框盘点」：按产出模型分组列出可清理项，人工勾选后删除，锁定与来源不明的对象不参与，删除前自动快照受影响文件。
- `2026-09-22`: 训练可复现：数据集构建写出 `manifest.json`（逐文件内容哈希、划分归属、类别表、种子），训练结束写出 `run_meta.json`（权重哈希、实际参数、manifest 哈希、指标）。
- `2026-09-22`: 划分种子按数据集固定写入 `.jllabel/project.json`，使相邻轮次的指标可比；同秒内的两次构建不再共用目录。
- `2026-09-22`: 打通姿态与分类的回灌：`yolo26_pose` 复用训练所用的 pose 配置，新增分类适配器 `yolov8_cls`，分类结果作为**待确认建议**写入 `predictions`，确认后才落入 `flags`。
- `2026-09-22`: 自定义模型上限由 5 提升到 30，迭代产生的模型被固定、不会被淘汰；`settings.json` 的轮询拷贝由 `run_meta.json` 取代。
- `2026-09-21`: 新增最小 CI（推送与 Pull Request 跑全量测试）；修复 `tests/test_settings` 单独运行导致进程崩溃的顺序依赖。
- `2026-09-21`: 分支自有版本号（状态栏、标题、`version` / `checks` 均显示所基于的上游版本）；修复配置保存与模型注册失败被静默吞掉、`app.log` 无轮转、`.desktop` 入口名错误、以及 spec 引用已删除目录等问题。
- 上游历史见 [CHANGELOG](./CHANGELOG.md)。

## 这个构建是什么

**JLLabelingAndTrain** 是 [X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) 的下游分支，保留其标注引擎、画布交互与模型插件结构，是**单机、单用户**工具：一个图片目录加一个标签 JSON 目录，没有服务端、账号与任务分配。

分支新增的是标注之外的那条闭环：每张图的复核状态、每个对象的来源记录、阈值校准、主动学习样本排序、Ultralytics 训练面板，以及一键把刚训好的权重回灌为自动标注模型 —— 并能报告上一轮模型留在数据里的结果。

## 分支范围

相比上游，本构建**不包含**：

- 远程推理服务（X-AnyLabeling-Server）；不支持视频、音频、点云输入 —— **仅图片**。
- 上游约 90 个模型的库。本构建只有 **8 种可加载模型类型**，内置配置文件只有 **2 个**（SAM2 tiny/base），其余需以自定义模型 YAML 注册。
- 已裁掉的任务面板：OCR / PPOCR / KIE、视觉问答、聊天机器人、文档解析（PaddleOCR-VL）、图像打标与描述、人脸估计、深度估计、目标计数、视觉定位、图像抠图、车道线检测、多目标跟踪、交互式视频分割。
- 大部分交换格式：`DOTA`、`MOT`、`MASK`、`PPOCR`、`MMGD`、`VLM-R1`、`ShareGPT` 已移除。
- 日文与韩文界面。仓库中只有 `zh_CN` 一份翻译目录，英文为源语言，且分支自研功能的部分界面文字为中文。

仓库内仍保留了被裁功能的文档与示例（如 `docs/zh_cn/chatbot.md`、`examples/grounding/`），它们描述的是**上游**能力，不是本构建。

## 特性

- 自动标注：SAM2 交互式提示、免提示自动掩码生成、YOLO 检测 / 分割 / 姿态 / 分类。
- 一键预测当前目录全部图片，可中断，支持跳过已标注并汇总失败清单。
- 不改源码即可扩展模型：在界面里指向一个模型 YAML（最多 30 个，迭代产生的模型被固定、不会被自动淘汰）。
- 推理后端：ONNX Runtime（CPU / CUDA）、TensorRT、OpenCV DNN。
- 标注形状：`矩形`、`多边形`（含笔刷涂抹）、`旋转框`、`长方体`、`四边形`、`圆形`、`直线`、`折线`、`点`；支持对象锁定、群组编号、描述、困难样本与标志位。
- 复核流程：每张图记录 `review_state`（`未检查` / `已检查` / `需返工`）与时间，筛选器与进度统计随之变化。
- 来源记录：每个对象记录人工或模型产出、产出模型名，以及该模型权重文件的内容摘要（`model_version`）。同名权重被重新训练覆盖后，上一轮的框仍然认得出来。
- 训练：仅 Ultralytics，四类任务（检测 / 分割 / 姿态 / 分类），约 40 项可调参数，独立进程、可中止可续训，14 种导出格式。
- 可复现：每次数据集构建写 `manifest.json`，每次训练结束写 `run_meta.json`；划分种子按项目固定。
- 可回退：删除当前打开图片的框就是一次普通 Ctrl+Z（一次撤销整批）；画布之外的文件改动前先快照到 `.label_backups/<时间戳>/`，「智能工具 → 11. 从备份恢复标注」可把某次快照写回，并先把被覆盖的版本另存一份。
- 「智能工具」菜单：阈值校准、数据智能分析、漏标扫描、迭代收益看板、智能复核跳转、标注传播、一键去重归档、训练建议、智能模板预标注、旧轮模型框盘点。复核队列为完整排序结果，只有数据体检对话框按每类 100 条显示并在标题标注真实总数。
- 界面语言：简体中文（唯一的一份翻译目录）。上游的英文源文本靠 `zh_CN` 目录译成中文，而本分支新增的文案直接以中文写入，因此没有可切换的英文界面。

## 标签格式

| 方向 | YOLO（hbb / seg / obb / pose） | VOC | COCO |
| :--- | :--- | :--- | :--- |
| 图形界面 | 导入 + 导出 | 仅命令行 | 仅命令行 |
| 命令行 `convert` | 支持 | 支持 | 支持（导入暂不支持 RLE） |

原生格式为 XLABEL JSON（每图一个 `*.json`）。

## 可加载模型类型

| 任务 | 类型 |
| :--- | :--- |
| 目标检测 | `yolov8`、`yolo26` |
| 实例分割 | `yolov8_seg`、`yolo26_seg` |
| 姿态估计 | `yolo26_pose` |
| 图像分类 | `yolov8_cls` |
| 分割一切 | `segment_anything_2`、`yolov8_sam2` |

内置配置仅 `sam2_hiera_base`、`sam2_hiera_tiny`；其他模型请按[自定义模型](./docs/zh_cn/custom_model.md)注册。上游完整模型库见 [model_zoo](./docs/zh_cn/model_zoo.md)（描述的是上游）。

## 训练闭环

```
标注 → 复核（已检查 / 需返工）→ 仅用已检查图片训练
     → best.pt 导出 ONNX → 载入为自动标注模型
     → 全量重推 → 盘点上一轮模型留下的框
```

- 只有「已检查」图片进入数据集，空标注图片作为背景负样本保留。
- 「用于自动标注」覆盖检测、分割、姿态（需与训练一致的 pose 配置）与分类；分类返回可确认的建议而非对象。
- 「训练 → 实验历史」列出所有写出 `run_meta.json` 的运行（按完成时间倒序、标注所属轮次），可导出 CSV；自定义 Project 路径下的运行不在扫描范围内，对话框会说明所扫描的目录。
- 训练产物位于 `<work_dir>/xanylabeling_data/trainer/ultralytics/`，训练结束会提示清理历史数据集副本。

## 文档

1. [安装文档](./docs/zh_cn/get_started.md)
2. [用户手册](./docs/zh_cn/user_guide.md)
3. [命令行界面](./docs/zh_cn/cli.md)
4. [自定义模型](./docs/zh_cn/custom_model.md)
5. [常见问题答疑](./docs/zh_cn/faq.md)

以下文档描述的是**上游**功能，本构建已移除对应面板，仅作归档参考：
[聊天机器人](./docs/zh_cn/chatbot.md)、
[视觉问答](./docs/zh_cn/vqa.md)、
[图像分类器](./docs/zh_cn/image_classifier.md)、
[文档解析](./docs/zh_cn/paddle_ocr.md)、
[模型库](./docs/zh_cn/model_zoo.md)。
（`docs/en/` 与 `docs/zh_cn/` 并不完全对应，且上游的 `video_classifier.md` 在两个目录中都缺失。）

## 开发

```bash
uv venv --python 3.12 .venv
uv pip install -e ".[cpu]" pytest
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests
```

`.github/workflows/ci.yml` 会在推送到 `main` 与提交 Pull Request 时运行全量测试；格式化与静态检查见 [贡献指南](./CONTRIBUTING.md)（因存在历史遗留告警，lint 暂不作为 CI 阻塞项）。

## 示例

本构建可实际完成的示例：

- [分类](./examples/classification/) —— 图像级与对象级
- [检测](./examples/detection/) —— [水平框](./examples/detection/hbb/README.md)、[旋转框](./examples/detection/obb/README.md)
- [分割](./examples/segmentation/README.md) —— 实例分割、二分类与多分类语义分割
- [训练](./examples/training/ultralytics/README.md)

`examples/` 下的 `optical_character_recognition`、`multiple_object_tracking`、
`interactive_video_object_segmentation`、`matting`、`estimation`、`counting`、
`grounding`、`vision_language`、`description` 等目录保留自上游，对应的模型与面板不在本构建中。

## 贡献指南

我们欢迎社区协作！**X‑AnyLabeling** 项目的成长离不开开发者们的共同参与，无论是修复 Bug、优化文档、还是添加新功能，您的贡献都非常宝贵。

在参与前请阅读我们的 [贡献指南](./CONTRIBUTING.md)，并在提交 Pull Request 前确认您已同意 [贡献者许可协议 (CLA)](./CLA.md)。

如果你觉得这个项目有帮助，请点亮右上角的⭐星标⭐。如有问题或建议，欢迎在本仓库[创建 issue](https://github.com/18961389539/LabelAndTrain/issues)；上游相关问题请到 [X-AnyLabeling issues](https://github.com/CVHub520/X-AnyLabeling/issues) 或邮件 cv_hub@163.com。

衷心感谢每一位为项目贡献力量的朋友 🙏

## 许可

本项目遵循 [GPL-3.0 license](./LICENSE)，完全开源免费（含商用）。

本仓库是 Wei Wang / CVHub 所开发的
[X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) 的衍生作品。按上游许可条款要求，二次开发并商业化时必须保留上游品牌标识并注明源项目地址 —— 本文件、程序状态栏与关于信息中均已保留。

此外，上游要求学术、科研、教学或企业使用者填写其[登记表](https://forms.gle/MZCKhU7UJ4TRSWxR7)（仅用于统计，不产生费用）。

## 赞助

| **微信支付** | **支付宝** |
| :---: | :---: |
| <img src="https://github.com/user-attachments/assets/0178cf76-3627-426e-8432-ec031c9278ae" width="400px" height="400px" style="object-fit: contain;" /> | <img src="https://github.com/user-attachments/assets/87544ff8-3560-4696-b035-1fd26ecd162b" width="400px" height="400px" style="object-fit: contain;" /> |

感谢您的支持！

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
