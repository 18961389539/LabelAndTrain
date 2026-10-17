# 打包版真机验证（2026-10-17）

`reviews/training_review_2026-09-30.md` 记的三条未验证里，有一条是「打包版仍未验证」。
这次补上了：**从当前源码构建 CPU 单文件包并真机启动**，看的是用户能看到的东西
（窗口标题、是否响应、崩溃日志），不是进程是否存在。

结论：**打包版跑的确实是现在这条功能线**，但顺带查出一个产物层面的退化，已修。

---

## 1. 怎么复现

用独立输出目录，绝不覆盖 `dist/` 里的历史产物；work-dir 也指到临时目录，
免得一次验证把真实机器的最近项目注册表和 `.xanylabelingrc` 写脏。

```bash
X_ANYLABELING_ROOT="<repo>" .venv/Scripts/python.exe -m PyInstaller \
  --noconfirm --clean \
  --distpath dist-verify --workpath build/pyinstaller-verify \
  packaging/pyinstaller/specs/x-anylabeling-win-cpu.spec

dist-verify/JLLabelingAndTrain-v1.0.0-beta.6-CPU.exe \
  --work-dir "<temp>/pkgcheck_work" --filename "<temp>/pkgcheck_imgs"
```

`--filename` 传目录即可自动装载整个文件夹（本仓库 CLI 已有该行为），这样标题栏的
项目名 / 文件名 / `[1/3]` 计数都会被真正走一遍。

验证判据（PowerShell）：

```powershell
Get-Process | Where-Object { $_.ProcessName -like 'JLLabeling*' } |
  Select-Object Id,Responding,MainWindowTitle | Format-List
```

- 实测标题：`JLLabelingAndTrain v1.0.0-beta.6 - [pkgcheck_imgs] - p0.png [240x160] [1/3]`
  → 项目名回退目录名、文件名、尺寸、`[i/N]` 计数在打包版里都成立。
- `Responding = True`；两个进程（onefile 引导进程 + 子进程）属正常。
- `<work_dir>/xanylabeling_logs/` 下**无** `crash_*.log`；`app.log` 4 行、无 ERROR：
  启动横幅、config 从隔离的 work-dir 初始化、以及 `🧮 Auto-labeling device: CPU`
  （9851f5ba 那条设备说明行在打包版里同样生效）。
- 截图在本 RDP 会话不可用（见记忆 `ui-visual-verification`），因此上述判据全部来自
  进程属性与应用日志。

## 2. 查出的问题：`win-cpu` 不再等于「仅标注」

| 构建 | 产物大小 | 构建耗时 |
|---|---|---|
| `win-cpu`（修前，venv 已装训练栈） | **376 MB** | ~5 分钟 |
| `win-cpu`（修后） | **154,417,283 B ≈ 147 MiB** | ~63 秒 |
| 历史 `dist/JLLabelingAndTrain-v1.0.0-beta.*-CPU.exe` | ~154 MB | — |

原因不是多打了个 Qt（日志里 PySide6 出现 0 次），而是环境漂移：`x-anylabeling-win-cpu.spec`
原本是 `excludes=[]`，只因为当时 venv 里**没有**训练栈才碰巧保持小巧。torch 2.14+cpu /
torchvision / ultralytics 8.4 装进同一个 venv 之后，「CPU 版」把整坨训练栈吸进了单文件包里
（日志可见 `hook-torch.py` 被处理）。这既让产物膨胀 2.4×、拖慢每次启动的解包，也和
`docs/zh_cn/get_started.md` 里写明的契约冲突：

> 普通 `win-cpu` 目标仍为仅标注、体积更小的版本。

`win-cpu-train.spec` 自己的文件头也说了：torch ~250 MB 的东西不该被 onefile 每次重新解压，
所以它才是 onedir。

## 3. 修法

`x-anylabeling-win-cpu.spec` 显式排除训练栈：`torch`、`torchvision`、`torchaudio`、
`ultralytics`、`ultralytics_platform`、`triton`。修后的包真机启动验证同上：标题、响应、
无崩溃日志、设备行都在。

打包版的能力边界因此重新与文档一致（这是**修前修后一致的行为**，不是新退化）：

- ✅ 标注、文件列表/复核、智能工具、项目切换与续点、自动标注（CPU / ONNX）、导出、运行历史与备份
- ❌ 内置训练面板：提示无法导入 ultralytics（优雅失败，不崩）；要打包版能训练请构建 `win-cpu-train`
- ⬜ GPU 路径仍未验证：本机 onnxruntime 无 CUDA provider（`accept_project_work.py` 第 12 步
  在这台机器上只列得出 `CPU` 一个可选项），需要一块能用 CUDA EP 的机器

## 4. 还剩什么

- 打包版**功能面**只验到「启动 + 装载文件夹 + 标题与设备行」。真正逐项点打包版 UI 需要
  UI Automation（`ui-visual-verification` 记的办法），本轮未做。
- `dist/` 里 9 月 29 日的 `beta.6-CPU.exe` 已经落后当前源码 7 周、落后几十条提交。
  要不要重新发布一个正式产物（以及是否顺手升 version），由你定。
