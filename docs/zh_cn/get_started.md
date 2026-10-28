# 快速入门指南

## 1. 安装部署

本分支（JLLabelingAndTrain）有两种获取方式：**克隆本仓库源码安装**，或使用本仓库 GitHub Releases 里由 CI 从 tag 构建的便携二进制（Windows/Linux/macOS，见 1.2.3）。它没有发布到 PyPI——`pip` 上的 `x-anylabeling-cvhub` 与上游 GitHub Releases 里的安装包都是**上游 X-AnyLabeling 的产物**，装上后没有本仓库 README 所写的这些功能。

> [!NOTE]
> **本构建带的功能**（下面每一项都能在界面里点到，链接指向本仓库文档）：
>
> 1. **交互式分割**：SAM2 前景/背景点提示与 AMG 免提示全图分割。内置模型清单里只有 SAM2 两个尺寸，其它模型要靠「自定义模型」注册 - [自定义模型](./custom_model.md)
> 2. **YOLO 系列自动标注**：检测 / 实例分割 / 姿态 / 分类，以及 YOLOv8+SAM2 组合；置信度与 IoU 阈值、**类别筛选**（只回灌选中的类别，按项目记住）都在智能标注面板的「更多」里 - [用户指南](./user_guide.md)
> 3. **YOLO 导入导出**：HBB / Seg / OBB / Pose 四种模式，读写同一份 `classes.txt`，导出清单与参数跟随项目 - [命令行与转换](./cli.md)
> 4. **一键训练**：基于 Ultralytics 的训练面板，加上漏标扫描、阈值校准、数据体检、迭代看板这条「标注 → 训练 → 回灌」闭环 - [本分支功能](./fork_features.md)
> 5. **项目管理**：多项目切换与续点、按项目保存的标签列表与输出目录与模型与类别筛选、复核状态与打回、项目内搜索、项目包导出、标注快照与恢复 - [本分支功能](./fork_features.md)
>
> 上游有、**本分支没有**的高级功能，别在这里找：远程推理服务（X-AnyLabeling-Server）、视频目标追踪（SAM2/SAM3 video）、UPN 候选框生成、以及靠文本提示工作的全模态模型（YOLOE、SAM 3、LocateAnything、Rex-Omni）—— 本分支的模型类型里没有这些，界面里也没有能触发它们的入口。需要它们请用上游 X-AnyLabeling。

### 1.1 前置条件

#### 1.1.1 Miniconda

如果您已经在使用 Miniconda，可按以下步骤操作：

**步骤 0.** 从 [官方网站](https://docs.anaconda.com/miniconda/) 下载并安装 Miniconda。

**步骤 1.** 创建一个 Python 3.11 ~ 3.13 版本的 conda 环境（推荐 Python 3.12），并激活它。

> [!NOTE]
> 其他 Python 版本需要自行验证兼容性。

```bash
# CPU 环境 [Windows/Linux/macOS]
conda create --name x-anylabeling-cpu python=3.12 -y
conda activate x-anylabeling-cpu

# CUDA 11.x 环境 [Windows/Linux]
conda create --name x-anylabeling-cu11 python=3.12 -y
conda activate x-anylabeling-cu11

# CUDA 12.x 环境 [Windows/Linux]
conda create --name x-anylabeling-cu12 python=3.12 -y
conda activate x-anylabeling-cu12

# CUDA 13.x 环境 [Windows/Linux]
conda create --name x-anylabeling-cu13 python=3.12 -y
conda activate x-anylabeling-cu13
```

#### 1.1.2 Venv

也可以使用 Python 内置的 `venv` 模块创建虚拟环境：

```bash
# CPU [Windows/Linux/macOS]
python3.12 -m venv venv-cpu
source venv-cpu/bin/activate  # Linux/macOS
# venv-cpu\Scripts\activate    # Windows

# CUDA 12.x [Windows/Linux]
python3.12 -m venv venv-cu12
source venv-cu12/bin/activate  # Linux
# venv-cu12\Scripts\activate    # Windows

# CUDA 11.x [Windows/Linux]
python3.12 -m venv venv-cu11
source venv-cu11/bin/activate  # Linux
# venv-cu11\Scripts\activate    # Windows

# CUDA 13.x [Windows/Linux]
python3.12 -m venv venv-cu13
source venv-cu13/bin/activate  # Linux
# venv-cu13\Scripts\activate    # Windows
```

#### 1.1.3 uv

**步骤 0.** 安装 uv：

```bash
# Linux / macOS / WSL2
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows（PowerShell）
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**步骤 1.** 创建虚拟环境（uv 会自动下载所需 Python 版本）并激活：

```bash
# CPU 环境 [Windows/Linux/macOS]
uv venv --python 3.12 .venv-cpu
source .venv-cpu/bin/activate      # Linux/macOS/WSL2
# .venv-cpu\Scripts\activate       # Windows

# CUDA 12.x 环境 [Windows/Linux]
uv venv --python 3.12 .venv-cu12
source .venv-cu12/bin/activate     # Linux
# .venv-cu12\Scripts\activate      # Windows

# CUDA 11.x 环境 [Windows/Linux]
uv venv --python 3.12 .venv-cu11
source .venv-cu11/bin/activate     # Linux
# .venv-cu11\Scripts\activate      # Windows

# CUDA 13.x 环境 [Windows/Linux]
uv venv --python 3.12 .venv-cu13
source .venv-cu13/bin/activate     # Linux
# .venv-cu13\Scripts\activate      # Windows
```

### 1.2 安装

本分支未发布到 PyPI；可以从源码安装（推荐 `uv pip`，用 `pip` 亦可），也可以直接使用 1.2.3 里的 GitHub Releases 便携包。需要训练、GPU 或修改代码时请走下面的源码步骤。

**步骤 a.** 克隆本仓库。

```bash
git clone https://github.com/18961389539/LabelAndTrain.git
cd LabelAndTrain
```

**步骤 b.** 按硬件选择 extra 安装依赖。

```bash
pip install -U uv

# CPU [Windows/Linux/macOS]
uv pip install -e ".[cpu]"

# CUDA 12.x 是 GPU 版本的默认选项 [Windows/Linux]
uv pip install -e ".[gpu]"

# CUDA 11.x [Windows/Linux]
uv pip install -e ".[gpu-cu11]"

# CUDA 13.x [Windows/Linux]
uv pip install -e ".[gpu-cu13]"
```

如需二次开发或打包编译，可同步加上 `dev`，例如：

```bash
uv pip install -e ".[cpu,dev]"
```

> [!NOTE]
> 如果切换到新的工程目录，请在该目录下重新执行一次上述安装命令，否则环境将引用旧目录中的源码。

安装完成后，可执行以下命令进行验证：

```bash
jllabelingandtrain checks   # 显示系统及版本信息
```

您也可以运行以下命令获取其他信息：

```bash
jllabelingandtrain help     # 显示帮助信息
jllabelingandtrain version  # 显示版本号
jllabelingandtrain config   # 显示配置文件路径
```

验证无误后，可直接运行应用程序：

```bash
jllabelingandtrain
```

> [!TIP]
> 您可以通过 `jllabelingandtrain --help` 查看所有可用的命令行选项。完整的参数说明请参考下方的**命令行参数**表格。

| 选项                       | 描述                                                           |
|----------------------------|---------------------------------------------------------------|
| `filename`                 | 指定图像或标签文件名。如果提供目录路径，则加载文件夹中的所有文件。  |
| `--help`, `-h`             | 显示帮助信息并退出。                                            |
| `--reset-config`           | 重置 Qt 配置，清除所有设置。                                    |
| `--logger-level`           | 设置日志记录级别：“debug”、“info”、“warning”、“fatal”、“error”。 |
| `--output`, `-O`, `-o`     | 指定输出文件或目录。以 `.json` 结尾的路径被视为文件。             |
| `--config`                 | 指定配置文件或 YAML 格式的配置字符串。默认为用户特定路径。         |
| `--work-dir`               | 指定配置文件和数据文件的工作目录。默认为用户主目录。               |
| `--qt-image-allocation-limit` | 以 MB 为单位覆盖 Qt 图像分配上限。Qt 默认值为 `256 MB`。设为 `0` 可完全禁用该限制。 |
| `--nodata`                 | 防止在 JSON 文件中存储图像数据。                                |
| `--autosave`               | 启用自动保存标注数据。                                          |
| `--nosortlabels`           | 禁用标签排序。                                                  |
| `--flags`                  | 逗号分隔的标志列表或包含标志的文件路径。                          |
| `--labelflags`             | 用于标签特定标志的 YAML 格式字符串或包含 JSON 格式字符串的文件。   |
| `--labels`                 | 逗号分隔的标签列表或包含标签的文件路径。                          |
| `--validatelabel`          | 指定标签验证的类型。                                            |
| `--keep-prev`              | 保留上一帧的注释。                                              |
| `--no-auto-update-check`   | 禁用启动时的自动更新检查。                                       |

> [!NOTE]
> 依赖项列表以 [pyproject.toml](../../pyproject.toml) 为准。上述命令会安装所选运行环境所需的依赖。

此外，还支持多种标签格式之间的批量转换功能：

```bash
jllabelingandtrain convert         # 列出所有支持的转换任务
jllabelingandtrain convert <task>  # 查看特定转换任务的详细帮助和使用示例，例如：xlabel2yolo
```

> [!IMPORTANT]
> 对于 GPU 加速，请按照以下说明，确保您本地的 CUDA 和 cuDNN 版本与 ONNX Runtime 版本兼容，并安装所需依赖库，以确保 GPU 加速推理正常运行：
>
> - Ⅰ. [CUDA Execution Provider](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)
> - Ⅱ. [Get started with ONNX Runtime in Python](https://onnxruntime.ai/docs/get-started/with-python.html)
> - Ⅲ. [ONNX Runtime Compatibility](https://onnxruntime.ai/docs/reference/compatibility.html)

| CUDA 环境 | 依赖选项 | ONNX Runtime GPU | cuDNN |
|-----------|----------|------------------|-------|
| CUDA 11.x | `gpu-cu11` | `>= 1.15.0, < 1.19.0` | 8.x |
| CUDA 12.x | `gpu` | `>= 1.18.1, < 1.27.0` | 9.x |
| CUDA 13.x | `gpu-cu13` | `>= 1.27.0, < 1.28.0` | 9.x |

> [!WARNING]
> 在同一个环境中只能安装 `cpu`、`gpu-cu11`、`gpu` 或 `gpu-cu13` 其中一个依赖选项。CUDA 11.x 还要求 `onnx >= 1.15.0, < 1.16.1`。

**可选步骤**：刷新翻译与资源文件

本构建只带一份翻译目录（`anylabeling/resources/translations/zh_CN.ts`），因此界面语言实际只有简体中文。
如果修改了界面文案或要维护翻译，下面的命令会处理**已存在**的全部目录，并且需要 Qt 的 `lrelease` 与 `rcc`（PyQt6 的 pip 包不含这两个工具）：

```bash
# 按源码字符串刷新已有目录；也可以显式指定要新建的语言
python scripts/generate_languages.py
python scripts/generate_languages.py zh_CN en_US

# 编译现存目录的 .qm 并重建 Qt 资源
python scripts/compile_languages.py
```

**可选步骤**：设置环境变量

```bash
# Linux 或 macOS
export PYTHONPATH=/path/to/X-AnyLabeling

# Windows
set PYTHONPATH=C:\path\to\X-AnyLabeling
```

> [!CAUTION]
> **避免依赖冲突**：为避免与第三方包冲突，请先执行以下命令卸载旧版本：
> ```bash
> pip uninstall anylabeling -y
> ```

> [!NOTE]
> **Fedora KDE 用户特别说明**：如果遇到鼠标移动缓慢或响应延迟的问题，可以尝试使用 `--qt-platform xcb` 参数来提升性能：
> ```bash
> jllabelingandtrain --qt-platform xcb
> ```

#### 1.2.3 预编译便携包

本分支的 [GitHub Releases](https://github.com/18961389539/LabelAndTrain/releases)
提供由 CI 从 tag 构建的免安装便携包：Windows 单文件 CPU 版、Windows
`-CPU-Train-win64.zip` 训练包（onedir，内置 CPU torch、Ultralytics 与
`onnxslim`，训练完成后的 ONNX 回灌也在包内可用）、Linux CPU 版与 macOS
`.app` 压缩包，随发布附带覆盖全部资产的 `SHA256SUMS.txt`。其中 `win-cpu`、
Linux 与 macOS 包是**仅标注**构建（不含 torch/ultralytics）；需要免安装训练时
下载 Windows `-CPU-Train-win64.zip`，解压后运行目录内的可执行文件。

上游 X-AnyLabeling 的 [GitHub Releases](https://github.com/CVHub520/X-AnyLabeling/releases)
是另一个程序的构建，不要用它来代替本分支。


## 2. 使用方法

有关如何使用 X-AnyLabeling 的详细说明，请参考相应的[用户手册](./user_guide.md)。

## 3. 打包编译

> [!NOTE]
> 请注意，以下步骤是可选的。此部分针对可能需要定制和编译软件以适应特定部署场景的用户。如果您使用软件时没有此类需求，可以跳过此部分。

<details>
<summary>展开/收起</summary>

为了方便用户在不同平台上运行 `X-AnyLabeling`，该工具提供了打包和编译的说明以及相关注意事项。执行对应打包命令前，请先安装目标运行环境的依赖选项。

### 3.1 注意事项

- **验证 GPU 环境**：如果编译 GPU 版本，请先激活相应的 GPU 运行环境，并执行 `pip list | grep onnxruntime-gpu` 以确保其正确安装。

- **GPU 编译**：GPU 规格文件会自动收集 ONNX Runtime Provider 库。构建前安装 `gpu-cu11`、`gpu` 或 `gpu-cu13`，即可分别选择 CUDA 11、12 或 13。详细兼容性信息请参考[官方文档](https://onnxruntime.ai/docs/execution-providers/CUDA-ExecutionProvider.html)。

- **CPU 训练版**：`win-cpu-train` 目标会打包 CPU 版 torch + Ultralytics，使打包后的程序内置训练面板可用。构建前安装训练依赖组：`uv pip install -e ".[cpu,cpu-train]" --torch-backend=cpu`。`onnxslim` 是训练完成后的 ONNX 导出（用于自动标注回灌）所必需的，Ultralytics 在导出时才导入它，不装的话打包版只能弹出 pip 安装提示。由于 torch 体积较大，该目标采用 onedir 目录结构，正式发布时由构建脚本压成 `-CPU-Train-win64.zip`；普通 `win-cpu` 目标仍为仅标注、体积更小的版本。

- **`win-cpu` 不含训练栈，这是规格文件写死的**：`x-anylabeling-win-cpu.spec` 显式 `excludes` 了 `torch` / `torchvision` / `torchaudio` / `ultralytics` / `ultralytics_platform` / `triton`。早先这里是 `excludes=[]`，只因为构建环境里没装这些包才“碰巧”是小的；一旦同一个 venv 装了训练栈，`win-cpu` 就会把它们一起吸进去（2026-10-17 实测：单文件产物 376 MB，而这个目标历来约 154 MB），于是“CPU 版”这个名字不再等于“仅标注”。排除之后，打包版里的训练面板会明确提示无法导入 ultralytics（优雅失败，不是崩溃），标注、自动标注、复核、智能工具、运行历史与备份照常可用；需要打包版能训练就用 `win-cpu-train`。

### 3.2 编译命令

```bash
# Windows-CPU
bash scripts/build_executable.sh win-cpu

# Windows-CPU 含训练（打包 CPU torch + Ultralytics，onedir）
bash scripts/build_executable.sh win-cpu-train

# Windows-GPU
bash scripts/build_executable.sh win-gpu

# Linux-CPU
bash scripts/build_executable.sh linux-cpu

# Linux-GPU
bash scripts/build_executable.sh linux-gpu

# macOS
bash scripts/build_executable.sh macos
```

> [!TIP]
> 如果在 Windows 上执行上述命令时遇到权限问题，在确保完成上述准备步骤后，可以直接执行以下命令：
> ```bash
> pyinstaller --noconfirm packaging/pyinstaller/specs/x-anylabeling-win-cpu.spec
> pyinstaller --noconfirm packaging/pyinstaller/specs/x-anylabeling-win-cpu-train.spec
> pyinstaller --noconfirm packaging/pyinstaller/specs/x-anylabeling-win-gpu.spec
> ```

</details>
