# JLLabelingAndTrain

单机、单用户的图像标注与训练桌面工具。它是 [X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) 的下游分支，保留其标注引擎、画布与模型插件结构，并围绕「标注 → 复核 → 训练 → 回灌 → 再标注」闭环增加了复核状态、形状溯源、智能工具、项目管理与 Ultralytics 训练面板。

一个图片目录 + 同级标签 JSON，没有服务端、账号和任务分配。界面只有简体中文。

- 版本：`1.0.0-beta.8`（基于 X-AnyLabeling `4.0.0-beta.14`）
- 许可：GPL-3.0，详见 [LICENSE](./LICENSE)
- 完整功能说明：[README_zh-CN.md](./README_zh-CN.md) · [分支特性](./docs/zh_cn/fork_features.md) · [FAQ](./docs/zh_cn/faq.md)

> 本文是**能跑起来的最小指南**。所有命令在仓库根目录执行，已在 Windows 10 + Python 3.13.14 + CPU 环境实测通过（2026-11-06，本机路径 `D:\Code\JLLabel\LabelAndTrain`）。

## 1. 环境要求

| 项 | 说明 |
| :--- | :--- |
| Python | `>=3.11`，官方推荐 3.12；本文实测 3.13.14 可用 |
| 系统 | Windows / Linux / macOS；本文为 Windows 10 |
| 显卡 | 非必需，`cpu` 走 ONNX Runtime CPU |
| 网络 | 需能访问 PyPI 镜像；运行时不依赖 GitHub |

## 2. 安装

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -U pip -i https://mirrors.aliyun.com/pypi/simple/
.venv/Scripts/python.exe -m pip install -e ".[cpu]" -i https://mirrors.aliyun.com/pypi/simple/
```

PowerShell 把路径里的 `/` 换成 `\`；Linux / macOS 用 `.venv/bin/python`。`.venv` 已被 `.gitignore` 忽略。

按硬件与用途选 extra：

| Extra | 用途 |
| :--- | :--- |
| `cpu` | 默认。ONNX Runtime CPU，标注与自动标注可用 |
| `cpu-train` | 追加 torch / torchvision / ultralytics / onnxslim / dill，启用「一键训练」与 ONNX 导出 |
| `gpu` / `gpu-cu11` / `gpu-cu13` | CUDA 12 / 11 / 13 推理 |
| `dev` / `test` | 格式化、lint、pytest、打包工具 |

需要训练时（体积较大，默认不装）：

```bash
.venv/Scripts/python.exe -m pip install -e ".[cpu-train]" -i https://mirrors.aliyun.com/pypi/simple/
```

## 3. 验证

```bash
.venv/Scripts/jllabelingandtrain.exe version
.venv/Scripts/jllabelingandtrain.exe checks
```

期望看到（节选）：

```
JLLabelingAndTrain 1.0.0-beta.8 (based on X-AnyLabeling 4.0.0-beta.14)

Application      App Version: 1.0.0-beta.8    Preferred Device: CPU
Packages         PyQt6 6.12.0 (Qt 6.12.0) · ONNX 1.23.2
                 ONNX Runtime 1.31.1 · OpenCV Contrib Headless 5.0.0
```

再用 `.venv/Scripts/python.exe -m pip check` 确认依赖无冲突。

## 4. 启动

```bash
.venv/Scripts/jllabelingandtrain.exe
```

首次启动会生成 `C:\Users\<用户名>\.jllabelingrc`；窗口标题为 `JLLabelingAndTrain`，日志出现 `🚀 ... launched!` 与 `🧮 Auto-labeling device: CPU` 即表示启动成功。关闭窗口即退出。

常用参数与子命令：

| 命令 / 参数 | 作用 |
| :--- | :--- |
| `jllabelingandtrain --filename <目录或图片>` | 启动时直接打开目录或单张图片 |
| `jllabelingandtrain checks` / `version` / `config` | 系统自检 / 版本号 / 配置文件路径 |
| `jllabelingandtrain convert` | 标签格式转换，子命令列出全部任务 |
| `--work-dir <路径>` | 覆盖配置、日志与权重的工作目录 |
| `--reset-config` | 重置 Qt 配置 |
| `--logger-level debug` | 调高日志级别 |
| `--qt-image-allocation-limit 1024` | 提高 Qt 图像内存上限（MB，默认 256） |

完整参数见 `jllabelingandtrain --help` 与 [命令行文档](./docs/zh_cn/cli.md)。

## 5. 第一次标注

1. `Ctrl+U` 打开图片目录（`Ctrl+I` 打开单张图片），标签 JSON 与图片同名同目录。
2. 右侧面板选择自动标注模型，SAM2 需要点选提示，YOLO 直接推理；`一键推理` 可跑完整个目录。
3. `Ctrl+Shift+J` 标记「已检查」，`Ctrl+Shift+K` 标记「需返工」，用复核筛选逐个过一遍。
4. `训练 → Ultralytics`：选任务、保持默认权重（首次自动下载）、`开始训练`。**需先装 `cpu-train`**。
5. `用于自动标注` 把 `best.pt` 导出为 ONNX 并载入，可选择重新推理整个目录，迭代看板给出上一轮收益。

`F1` 可查看快捷键速查表。

## 6. 文件放在哪里

| 路径 | 内容 |
| :--- | :--- |
| `<图片目录>/<同名>.json` | XLABEL 标签，含 `review_state` 与 `shapes[]` 的来源信息 |
| `<图片目录>/.jllabel/project.json` | 项目级记录：类别表、复核计数、划分种子、上次训练参数 |
| `<图片目录>/.label_backups/` | 批量改动前的标注快照 |
| `~/.jllabelingrc` | 全局应用设置 |
| `<work_dir>/jllabeling_logs/` | 轮转日志与启动崩溃日志 |
| `<work_dir>/jllabeling_data/` | 自动标注权重、训练数据集、训练产物 `run_meta.json` 等 |

`--work-dir` 可整体改掉工作目录；图片和标签始终留在原处。

## 7. 功能边界与模型清单

**本构建有**：矩形 / 多边形 / 旋转框 / 圆 / 线 / 点等形状；SAM2 交互分割与自动掩码生成；YOLO 检测 / 实例分割 / 姿态 / 分类及 `yolov8_sam2` 组合；11 个智能工具（阈值校准、数据体检、漏标扫描、迭代看板、旧轮模型框盘点等）；可复现的数据集 `manifest.json` 与训练 `run_meta.json`；YOLO HBB / Seg / OBB / Pose 导入导出。

**本构建没有**：远程推理服务、视频 / 音频 / 点云输入，上游约 90 个模型的模型库，OCR / VQA / 聊天 / 文档解析 / 视觉语言（VLM）等面板（这些面板及其文档、示例、素材已整条删除），多语言界面，以及部分上游交换格式。`examples/` 中仍有少量页面描述上游能力，不代表本构建可用。

本构建支持 **8 loadable model types**（8 种可加载模型类型），但只有 **2** built-in config（`sam2_hiera_tiny` / `sam2_hiera_base`）。

**可加载模型类型**：`segment_anything_2`、`yolov8`、`yolov8_seg`、`yolov8_sam2`、`yolov8_cls`、`yolo26`、`yolo26_seg`、`yolo26_pose`。检测类模型需在界面里用自定义 YAML 注册，或由训练结果导出，见 [自定义模型](./docs/zh_cn/custom_model.md)。

## 8. 排错

| 现象 | 处理 |
| :--- | :--- |
| `Could not find a version that satisfies the requirement setuptools>=70`（`versions: none`） | 清华源在 PEP 517 隔离构建中取不到 setuptools；改用阿里云镜像 `https://mirrors.aliyun.com/pypi/simple/` |
| `pypi.org` 下载慢或超时 | 同样走国内镜像；GitHub 主站在部分代理下会返回 502，但运行阶段不需要它 |
| 安装卡在 `Installing collected packages` 后被中断 | PyQt6-WebEngine-Qt6 等 wheel 达 132 MB，解压较慢。先 `pip check`，再重跑同一条安装命令即可续装，已装包会跳过 |
| 训练菜单点不动 / 提示缺少 torch、ultralytics | 只装了 `cpu`；按第 2 节补装 `cpu-train` |
| 界面配置异常或想恢复初始状态 | `jllabelingandtrain --reset-config` |

启动崩溃时程序会写日志到 `<work_dir>/jllabeling_logs/crash_<时间戳>.log`，并尽量弹出可读的错误框。

## 9. 开发

```bash
.venv/Scripts/python.exe -m pip install -e ".[cpu,dev,test]" -i https://mirrors.aliyun.com/pypi/simple/
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests
```

- 代码主体在 `jllabeling/`（app、config、services、views、resources）。
- 打包脚本 `scripts/build_executable.sh`，各平台 PyInstaller spec 在 `packaging/pyinstaller/specs/`；`win-cpu-train` 会把 CPU torch 与 Ultralytics 一起打进便携版。
- CI 见 `.github/workflows/ci.yml`；lint 采用基线门禁，历史告警记录在 `scripts/flake8_baseline.txt`。
- 完整安装方式（conda / uv / GPU / 便携包）见 [快速入门指南](./docs/zh_cn/get_started.md)。

## 10. 许可与上游

本项目采用 [GPL-3.0](./LICENSE)，是 Wei Wang / CVHub 的 [X-AnyLabeling](https://github.com/CVHub520/X-AnyLabeling) 衍生作品；按其条款保留上游品牌与源地址署名。上游行为的问题请提到[上游仓库](https://github.com/CVHub520/X-AnyLabeling/issues)。
