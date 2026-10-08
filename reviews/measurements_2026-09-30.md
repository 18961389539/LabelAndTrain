# 训练模块真机测量（2026-09-30）

> 目的：把「只有真的跑一轮才能回答」的三件事做掉——子进程 worker 协议、停止后 `last.pt` 是否真能续训、
> 续训是否写回同一目录。测试用例能覆盖零件，覆盖不了这三条。
> 环境：Windows，Intel Core i7-14700，**CPU only**，torch 2.14.0+cpu，ultralytics 8.4.165，Python 3.12.14。
> 数据：24 张 320×240 合成图（每张一个矩形，单类 `bolt`），`dataset_ratio=0.8`，`imgsz=64`，
> `batch=4`，`workers=0`。全部跑在临时 work dir 下，不碰用户数据。

## 一句话结论

**三条全部通过**，而且真机跑出了一个单元测试抓不到的 bug：**续训后的 `results.csv` 有 51 行但只有 50 轮**
（中断那一轮被写了两遍），而 `parse_training_metrics` 用行数当轮数 → 50 轮的运行被记成 **51 轮**，
写进 `run_meta.json` 并显示在实验历史里。已修（改读 `epoch` 列），并补了 2 条回归测试。

## 1. 数据集构建（对话框走的那条路）

```
report = {'requested': 24, 'valid': 24, 'train': 19, 'val': 5, 'background': 0,
          'unreadable_labels': [], 'unreadable_labels_count': 0,
          'unchecked_files_count': 0, 'conversion_errors': [], 'dropped_shapes': {}}
```

- `manifest.json` 的 `skipped` 块与 report 一致；`dataset_info.txt` 多了 4 行计数（Unreadable / skipped / dropped / shapes dropped）。
- 24 × 0.8 = 19 train / 5 val，与 manifest 一致。干净数据下四类跳过全是 0，说明新增统计不误报。

## 2. worker 子进程协议（RUN 1：3 轮）

| 观测 | 值 |
|---|---|
| 事件 | `training_started` → **56 条 `training_log`** → `training_completed` |
| 产物 | `results.csv` ✅ `weights/best.pt` ✅ `weights/last.pt` ✅ |
| metrics | `('2.91137', '0', 3)`（loss / mAP50 / 轮数） |
| 墙钟 | 约 20 秒 |

`training_log` 56 条 = ultralytics 的输出确实一路传到了 UI（不是被吞掉）。

## 3. 启动开销 —— 这条决定了怎么解读「停止」

子进程**第一条输出出现在 16.7 秒**（torch import + 模型加载 + 数据集扫描），之后每个 epoch 只有约 0.3 秒
（`time` 列 1→7 轮累计 2.3 秒）。

**第一次测「停止 + 续训」时我给了 15 秒窗口，结果什么都没发生**——不是产品问题，是 15 秒短于启动时间，
进程在第一行输出之前就被我停掉了。这也解释了 UI 里那段 `Starting (elapsed m:ss)...` 的存在：
从点击到第一个 epoch，用户可能等十几秒，而屏幕上不会有任何训练日志。

## 4. 停止后能不能续训（RUN 2：50 轮，15 秒后停）

```
events = ['training_log', 'training_started', 'training_stopped']
last.pt 存在 = True
_read_resume_checkpoint(last.pt) -> {'epochs': 50, 'last_epoch': 5}
```

关键点：判定不是看文件在不在，而是**读 checkpoint 里有没有 optimizer 状态、还剩几轮**——真实的中断
checkpoint 带这些状态，所以 `Resume Training` 会出现。

## 5. 续训是否写回同一目录（RUN 3：从 last.pt 续，跑到自然结束）

```
results.csv 行数      8 → 52        （epoch 列最后一个值是 50）
runs/detect 下的目录  ['exp', 'exp_stop']   没有 exp-2
子进程日志            "44 epochs completed in 0.004 hours."
                      "Optimizer stripped from ...weights/last.pt"
```

- 从第 6 轮续跑，跑满 50 轮，**写回同一个 exp_stop**，`results.csv` 续写而不是新建 —— CHANGELOG 里那句
  「same `exp/`, `results.csv` continues, no `exp-2`」在真机上成立。
- 跑满之后 `_read_resume_checkpoint` 返回 **None**，checkpoint 里 `epoch=-1`、`optimizer=None`
  （ultralytics 会剥离）→ **跑完的运行不会错误地提供「继续训练」**，这条也是对的。

## 6. 🔴 真机跑出来的 bug：轮数被算成行数

续训会在 `results.csv` 里**重复写入中断的那一轮**：

```
epoch 列：1 2 3 4 5 6 7 7 8 9 ... 50     ← 7 出现两次
总行数 52（含表头）= 51 行数据 / 50 轮
```

而 `utils.parse_training_metrics` 返回的第三个值是 `len(rows)`：

- 修复前：50 轮的运行 → **`epochs: 51`**，写进 `run_meta.json`，在实验历史表里显示成 51；
  恰好是拿两轮做对比时最容易被当成"这轮跑得更久"的那个数字。
- `estimate_remaining_seconds` 早就为这件事做过注释（"a resumed run can repeat a row"，所以它用 epoch 列），
  但同一个文件里的 `parse_training_metrics` 没跟上。
- 修复后：`('1.40092', '0.995', 50)` ✅；3 轮的那次仍是 3 ✅（没有回归）。
- 回归测试：`tests/test_auto_training/test_dataset_overview.py` 新增
  `test_parse_training_metrics_counts_epochs_not_rows`（含重复行的 csv）与
  `test_parse_training_metrics_falls_back_to_row_count`（没有 epoch 列时仍返回行数）。

## 7. 真实运行目录上的 `run_meta.json`

```
status=completed  task=Detect
metrics={'loss': '1.40092', 'map50': '0.995', 'epochs': 50}   ← 修复后
weights.sha1=40a78e4920d9（文件存在）
dataset.seed=1234  manifest_sha1=26b58bc446aa
train_args={'data': 'x', 'epochs': 50}
run_history 行 = [('exp_stop', 'completed', 0.995, 50)]
```

参数、种子、manifest 哈希、权重哈希都在，历史表能把这一轮读出来。

## 8. 还没有被验证的（别当成已结论）

- **GPU 路径**：本机 `torch.cuda.is_available() == False`，AMP / CUDA 设备选择 / OOM 补救按钮全都没跑到。
- **拖框手感、缩放流畅度**：offscreen 下测不出（沿用 `measurements_2026-09-27.md` 的结论）。
- **`_offer_dataset_cleanup` 的阈值分支**：要 ≥100 MB 旧数据集副本才会弹，本次合成数据远不到。
- **打包版**（PyInstaller）里的训练与导出一律未验证。
- 观察到的**环境性抖动**（不是回归，已单独复跑确认）：
  `tests/test_labeling/test_widget_wiring.py::TestWidgetLaunchedWithFolder` 偶发 teardown `PermissionError`（png 被占）；
  `pytest tests/test_auto_training/` 有两次结尾没打印 summary 就退出（点全绿、退出码 0/1 不定）。
  两者单跑或重跑都正常。

## 复现命令

```bash
cd /g/LabelAndTrain/LabelAndTrain
# 造数据 + 跑三轮真训练（3 轮 / 停 / 续训），结果打在 stdout
PYTHONPATH=$PWD QT_QPA_PLATFORM=offscreen \
  .venv/Scripts/python.exe -u "C:/Users/Administrator/AppData/Local/Temp/verify_training_run.py"
```

脚本在系统临时目录，未入库：它是**测量**用的，不是回归网；要固化成 CI 需要一台有 GPU 的机器和不短的时间。
