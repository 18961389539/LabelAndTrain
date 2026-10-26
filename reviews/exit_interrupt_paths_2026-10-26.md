# 退出/中断路径审计（2026-10-26）

这轮看的是“用户要停下来时，程序是否真的停下来、是否留下半个结果”。
结论：大部分路径已有收尾；找到一个真实缺口——**批量自动标注进行中关窗，
QThread 仍持有 widget，窗口被销毁后线程继续跑**。已修，并补了模型的
协作取消。

## 1. 路径盘点

| 路径 | 现状 |
|---|---|
| 主窗口关闭 | `may_continue()` 保存/放弃/取消；项目与配置落盘；EXIF/标注检查停止；**新增**批量守卫与模型取消 |
| 项目关闭 | `may_continue()` → 写回项目续点 → 清空画布；批量处理时窗口被 WindowModal 进度框挡住，正常入口不可达 |
| 训练停止 | 已验证：worker 终止、`run_meta.json` 记 `stopped`、`last.pt` 可续训、历史表可见 |
| 训练窗口关闭 | 数据集准备/训练中明确拒绝关闭并提示先停止；完成/停止状态先落日志再关闭；导出线程 daemon，回调解绑 |
| 导出停止 | `model.export()` 是阻塞调用，无取消钩子；`stop_export` 只等待 5 秒并如实报告“无法中断”；线程 daemon，关窗不让进程挂着等它 |
| 智能工具 | 进度框取消 → `request_cancel`；线程检查取消标志后停止；结果对话框等线程结束才打开 |
| EXIF / 标注检查 | `stop_scan` / `stop`：quit + 3 秒 wait，超时 terminate；线程/worker deleteLater |
| 批量自动标注 | **本轮新增**：关窗请求取消；线程仍在跑时拒绝关闭，等当前图片结束 |
| 模型下载/推理 | **本轮新增**：关窗走到真正关闭时 `cancel_download()` + `cancel_prediction()`，协作停止 |

## 2. 修掉的缺口

### 批量自动标注关窗

- 现象：批量线程 `BatchProcessingThread` 是 `QThread`，没有 QObject 父对象；
  `closeEvent` 既不设 `cancel_processing` 也不等待。窗口关闭后线程仍持有
  widget 和模型，继续写标签；进程退出时可能在 QThread 仍运行时销毁它。
- 修法：`utils/exit_cleanup.py` 的 `batch_allows_close(widget)`：
  - 不活跃 → 允许关闭；
  - 活跃 → 设 `cancel_processing = True`；线程仍在跑则返回 False，
    `closeEvent` 弹窗并 `event.ignore()`，用户处理完当前图片后再关；
  - 线程已停/包装已删除 → 允许关闭。
  - 守卫放在 `may_continue()` **之前**：批量线程还在写别的图片时，
    不应先弹“保存当前图”的提示。
- 提示文案：`正在停止批量标注，请处理完当前图片再关闭窗口。`（已进
  `zh_CN.ts`，源文本为中文）。

### 模型下载/推理关窗

- `closeEvent` 在保存提示真正通过后调用 `cancel_model_work(widget)`：
  `cancel_download()` + `cancel_prediction()`。这是协作取消，不阻塞关闭；
  下载/推理本身会在检查点退出。
- 放在 `may_continue()` 之后：用户在保存提示里点“取消”时，窗口仍开着，
  不应顺手把正在下载的模型取消掉。

## 3. 测试

`tests/test_labeling/test_exit_cleanup.py` 9 条：

- 空闲窗口关闭不碰批量标志；
- 批量线程运行中：返回 False 且设置取消；
- 线程已停：允许关闭；
- QThread 包装已删除（`RuntimeError`）：允许关闭；
- `cancel_model_work` 同时取消下载与推理，无面板时安全；
- 批量运行中关窗：警告出现、`may_continue` 不被调用、事件被忽略；
- 真正关闭时模型工作被取消；
- 保存提示取消时**不**取消模型工作。

## 4. 验证

- 全量：**1672 passed / 1 skipped / 61 subtests passed**。
- smoke **17/17**；acceptance **17/17**。
- black **206 files unchanged**；flake8 基线 **214 findings，无回归**。
- 翻译目录按流程重新生成并补齐新增提示的中文；`.qm`/`resources.py` 已重建。

## 5. 仍然存在的边界

- **导出不可中断**：`model.export()` 没有取消钩子；关窗只保证进程不被
  非 daemon 线程吊住，导出会在后台完成。要真正支持停止，需要在导出
  实现里加入可中断的检查点，或改为独立进程并 kill。
- 模型下载/推理的取消是协作式的，关窗不等待其 QThread 结束；如果某个
  模型在阻塞调用里不检查取消标志，它仍可能比窗口晚结束。这是模型侧
  契约，当前未逐个模型验证。
- 训练窗口在准备/训练中故意拒绝关闭，必须先停止；这是产品选择，不是
  遗漏。
