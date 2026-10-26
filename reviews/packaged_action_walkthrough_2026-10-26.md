# 打包版动作走查（2026-10-26）

上一轮打包验证（`reviews/packaged_build_verification_2026-10-17.md`）只到
「启动 + 装载文件夹 + 标题/设备行」；逐项点击当时被记为人工步骤，因为本机
没有 `pywinauto` / `uiautomation`，且决定不为验证引入新依赖。这次补上了，
用的正是那份文档末尾提到的起点：**PowerShell 的
`System.Windows.Automation` + 合成鼠标/键盘**，不装任何 Python 依赖。

结论：**CPU 单文件包里 83 项动作检查全部通过**；走查同时抓到两个 F1
快捷键缺陷（都已修），并确认了 CPU 包对训练面板的能力边界。应用正常关闭
干净；UIA 客户端附着时的关闭会在 `faulthandler.log` 留一条 COM 异常，
与产品行为无关，见第 5 节。

---

## 1. 构建与夹具

- 源码：当前工作树（含本轮的 F1 修复），`packaging/pyinstaller/specs/x-anylabeling-win-cpu.spec`。
- 隔离输出：`build/verify_dist` / `build/verify_work`，不覆盖 `dist/` 的历史产物。
- 产物：`JLLabelingAndTrain-v1.0.0-beta.6-CPU.exe`，**154,457,439 B ≈ 147 MiB**，
  构建约 90 秒；spec 的 `excludes` 仍把 torch/ultralytics 挡在外面。
- work-dir：临时目录；镜像夹具 `alpha/` 有 3 张 240×160 图片（p0/p1 各一个
  rectangle，p2 无 JSON 的负样本），`classes.txt` 内容为 `defect`。
- 启动：`--work-dir <temp> --filename <alpha>`；`QT_ACCESSIBILITY=1`；
  `SetProcessDPIAware()` 让 UIA 矩形与 `SetCursorPos` 落在同一坐标系。

## 2. 走查方式

- **菜单**：UIA 展开顶层菜单（合成点击顶层菜单栏不稳定），再用真实鼠标
  点击菜单项；弹出窗口的 `InvokePattern` 不用来打开模态框——它会在
  `dialog.exec()` 里同步阻塞，导致整个 UIA 树退化。
- **快捷键**：`keybd_event` 发送；先 `Canvas.SetFocus()` 并确认
  `AutomationElement.FocusedElement` 是 Canvas。启动时的项目管理器若
  持有焦点，先关闭它，否则 D/A、Ctrl+G 都进不了主窗口。
- **对话框**：UIA 读控件名/值，`ValuePattern.SetValue` 填路径，真实鼠标
  点按钮；关闭用 `WindowPattern.Close`。
- **关闭应用**：另做一次不接 UIA 的原生 `WM_CLOSE`，用来区分产品关闭
  路径与自动化附着带来的噪声（见第 5 节）。

## 3. 通过的动作（83/83）

| # | 动作 | 观察到的证据 |
|---|---|---|
| 1 | 启动即加载文件夹 | 标题 `… - [alpha] - p0.png [240x160] [1/3]` |
| 2 | 文件 → 下一张图像 / 上一张图像 | 标题 `[2/3]` ↔ `[1/3]`；菜单标签实际是「下一张图像/上一张图像」 |
| 3 | 视图 → 显示标签 | `ToggleState On → Off`，再点一次恢复 |
| 4 | 工具 → 统计总览 | 表格含 `defect`、矩形列 `2`、Total `2`；范围/跳转/导出控件齐全 |
| 5 | Ctrl+0 设置 | 设置窗口打开，4 个页面；搜索框接受 `F1` |
| 6 | 主题 → 深色主题 | 确认框 → 工作目录 rc `theme: dark`；再选「跟随系统」→ `theme: auto` |
| 7 | 导出 → YOLO HBB | 原生「选择类别文件」选 `classes.txt` → 导出选项设路径 → 确认 |
| 8 | 导出落盘 | `p0.txt` = `0 0.250000 0.468750 0.333333 0.562500`，`p1.txt` = `0 0.312500 0.468750 0.333333 0.562500`；`p2.txt` 为空（负样本）；`classes.txt`、`data.yaml`、`export_manifest.json` 齐全 |
| 9 | 导出记录 | manifest：`mode=hbb`，`images_exported=3`、`shapes_exported=2`、`missing_label_files=1`、`source_data.no_label_file=1`，类别来源 `classes.txt` |
| 10 | 训练 → 实验历史 | 窗口标题「训练历史」，空态文案明确（“没有找到带元数据的训练记录…”），16 列 |
| 11 | 训练 → Ultralytics | CPU 包弹出「缺少 ultralytics」并给出 `pip install` / `uv pip install`；点 OK 后主窗口仍响应 |
| 12 | 文件 → 项目 → 切换项目… | 项目管理器列出 `alpha`、任务「目标检测」、进度 `2/3` |
| 13 | 文件 → 项目 → 项目属性…（无记录） | 提示“这个文件夹还不是正式项目；保存后创建 .jllabel/project.json”；改名 `alpha-final` → 保存 → 标题变 `[alpha-final]` |
| 14 | 再次打开项目属性 | 概览 `已标 2/3 · 已确认 0 · 需返工 0`、`尚未训练`；项目名回读 `alpha-final` |
| 15 | 项目记录 | `.jllabel/project.json`：`name=alpha-final`、`labels=["defect"]`、`last_file=p0.png` |
| 16 | F1 快捷键速查 | 修复后打开「快捷键速查」，搜索框 + 69 条快捷键树；F9 导航器也正常（功能键注入的对照） |
| 17 | 文件 → 项目 → 关闭项目 | 标题退回 `JLLabelingAndTrain v1.0.0-beta.6`，无项目片段 |
| 18 | 正常关闭 | 无 UIA 附着的原生 `WM_CLOSE`：进程 0 残留、`faulthandler.log` 0 字节、无 crash 日志、app.log 无 ERROR |

导出目标目录**故意不预创建**；预先存在会进入「输出目录已存在」的
Merge/Clear/Cancel 分支（这是既有设计，不是缺陷），本次走查测的是普通
新建路径。脚本也保留了对该提示的 Merge 处理，以防夹具目录残留。

## 4. 抓到并修掉的两个 F1 缺陷

### 4.1 可见动作与隐藏动作绑同一个 F1，Qt 判歧义后两个都不触发

- 现象：Tool → 快捷键速查可以点击打开；按 F1 没反应。菜单项的 UIA
  `AccessKey` 明明是 `F1`。D/A/Ctrl+G/Ctrl+0/F9 都正常，排除了功能键注入。
- 原因：`label_widget._build_actions()` 里的菜单动作已经绑了
  `shortcuts["show_shortcuts_help"]`（F1）；`SettingsRuntimeApplier`
  又为同一功能创建了一个隐藏 QAction，同样绑 F1。两个 QAction 的
  shortcut 在同一窗口上下文里重复，Qt 视为 ambiguous，两个都不执行。
- 修法：`runtime_applier.build_shortcut_action_map()` 直接把
  `shortcuts.show_shortcuts_help` 指到可见动作
  `self._widget.actions.shortcuts_help`，不再建隐藏副本。
  `tests/test_settings/test_shortcut_bindings.py` 新增
  `test_no_hidden_shortcut_duplicates_a_menu_action`，用源码结构对比
  “可见 action 的 config key”和“applier 建隐藏 action 的 key”，交集非空即失败。
- 打包复测：F1 打开「快捷键速查」，树 69 项；F9 打开导航器作为对照。

### 4.2 第一版修复引用了不存在的 `actions.shortcuts_help`，打包启动直接崩

- 第一版修法只改了映射；打包版启动即 `AttributeError: 'Struct' object
  has no attribute 'shortcuts_help'`，`crash_*.log` 明确指向
  `build_shortcut_action_map()`。单元测试没发现，是因为它们不构造真实
  `LabelWidget`；这正是本轮打包真机走查补上的盲区。
- 修法：把 `shortcuts_help` 加进 `widget.actions = utils.Struct(...)`
  命名空间；新增 `test_every_action_the_applier_binds_exists_on_the_widget`，
  用 AST 取命名空间 key、用正则取 applier 的
  `self._widget.actions.X` 引用，差集非空即失败——一个缺失名字就会
  让应用启动不了，这条测试把“启动期才炸”的情况前移到 CI。
- 打包复测：启动、菜单、动作全部通过；`app.log` 无 ERROR，无 crash 日志。

## 5. 关闭路径与 `faulthandler.log` 的噪声

- 走查脚本用 `WindowPattern.Close` 关主窗口后，`faulthandler.log` 会写
  `Windows fatal exception: code 0x8001010d`（RPC_E_CANTCALLOUT_ININPUTSYNCCALL），
  堆栈落在 `app.py` 的 `sys.exit(app.exec())`。
- 另做对照：**不接 UIA**，用 Win32 `EnumWindows` 找 HWND 后
  `PostMessage(WM_CLOSE)`（与点标题栏 X 走同一个 `WM_CLOSE` 关闭事件）；
  进程 0 残留，`faulthandler.log` **0 字节**，
  `app.log` 无 ERROR。接了 UIA 的 `WM_CLOSE` 对照组仍会写这条异常。
  因此这是 UIA 客户端附着时的自动化关闭噪声，不是产品关闭缺陷；
  普通用户点标题栏 X 的路径按原生对照判为干净。
- 由于本 RDP 会话截图不可用（见记忆 `ui-visual-verification`），
  所有判断仍来自 UIA 控件名/状态、标题栏和落盘文件，不是像素比较。

## 6. 能力边界与剩余项

- **CPU 单文件包不含训练栈**：训练菜单会明确提示缺少 ultralytics，
  不崩、不假装能训；要在打包版里训练，需构建
  `x-anylabeling-win-cpu-train.spec` 的 onedir 产物。本轮未验证该产物。
- **GPU**：本机无 GPU，按用户要求本轮不做 GPU 相关验证。
- **UIA 附着关闭的 faulthandler 噪声**：已用原生对照定性为自动化问题；
  若以后要把它也变成 CI 判据，应在关闭前释放 UIA 引用，或把关闭动作
  放到不接 UIA 的独立进程。

## 7. 门禁

- 全量：**1663 passed / 1 skipped / 59 subtests passed**（新增 2 条快捷键结构测试）。
- smoke **17/17**；acceptance **17/17**。
- black **197 files unchanged**；flake8 baseline **215 findings，无回归**；
  codespell 对本轮改动无新增命中。
