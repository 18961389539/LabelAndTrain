# 大目录导入/切图性能测量与优化（2026-10-26）

针对「数千张图片」的真实使用场景，用离屏的真实 `LabelingWidget` 测量
打开文件夹、首图、连续切图和筛选的同步耗时，再按热点优化。所有数字来自
同一台机器、同一份 3000 张夹具；没有引入新依赖。

## 1. 夹具与方法

- 3000 张 96×128 PNG，每张一个 `defect` 矩形框；每张都有同名 JSON，
  每 3 张有 1 张的框 `score=0.3`（低置信），其余 `0.9`；另有 `classes.txt`。
- 临时 work-dir + 配置副本，不碰真实配置/项目注册表；`QT_QPA_PLATFORM=offscreen`。
- 构造真实 `LabelingWidget`，`import_image_folder(load=False)` 测量同步导入；
  随后 `open_next_image()` 走真实切图路径；`cProfile` 定位热点。
- 导入连续跑 3 次取代表值；切图测 30 次取中位数/95 分位。

## 2. 基线：首次导入 7–12s，切图 32ms

| 指标 | 基线 |
|---|---:|
| 首次导入（冷缓存，3 次独立夹具） | **12.45s / 7.02s / 6.92s** |
| 后续导入（文件缓存已热） | 0.58–0.63s |
| 其中 `_refresh_file_panel` | **6.8–12.3s** |
| 其中 3000 次 `_create_file_list_item` 合计 | 0.10s |
| `scan_all_images` | 0.03s |
| 首图加载 | 0.05s |
| 连续切图 30 次 | **mean 32.8ms / p50 32.7ms / p95 33.6ms** |
| `load_file` 本体（不含导航） | 2.86ms |
| 单次切图的 `scrollToItem` | **27ms** |
| 单次切图的 `setCurrentRow` | 7.5ms |

根因有两个：

1. `_refresh_file_progress()` 为统计「待复核」数量，对每一行调用
   `_file_item_has_low_conf()`；该函数在角色未缓存时打开并解析整个标签
   JSON。3000 个文件的全量解析发生在 UI 线程，且恰好是在文件列表建好、
   异步检查器尚未接管之前。
2. 文件列表没有设置 `QListView.setUniformItemSizes(True)`；Qt 在
   `scrollToItem(EnsureVisible)` 时按整个 3000 行模型计算行高，每次切图
   固定多出约 27ms。

## 3. 优化

### 3.1 「待复核」计数改为后台第二轮扫描

- `utils/async_label_check.py` 新增 `label_file_low_conf(path, thresholds)`；
  读取文件后先关闭再 `json.loads`，缩短 Windows 上文件被占用、阻止删除的窗口。
- `AsyncLabelChecker` 的第一轮仍是便宜的 review-header 扫描（绿点）；
  第二轮在**同一个 QThread** 上解析 shapes，发 `low_conf_ready(start, flags)`
  批次。`FileReviewController.apply_low_conf_batch` 把低置信角色写回行。
- `_refresh_file_progress()` 移到 `utils/file_list_ops.refresh_file_progress`，
  只读缓存的 `FILE_LOW_CONF_ROLE`；第二轮未完成时「待复核」显示 `…`，
  完成后自动刷新为真实数字。`label_widget.py` 只保留一行委托，
  体量预算从 6697 下调到 **6663**。
- 后台扫描仍可被关窗/切文件夹/训练启动前的 `stop()` 中止；测试构造器在
  `deleteLater` 前同步停止扫描，避免临时目录清理撞上打开中的文件。

### 3.2 文件列表 uniform item sizes

`self.file_list_widget.setUniformItemSizes(True)`：行高一致，Qt 不再在
每次 `scrollToItem` 时测量整个模型。`scrollToItem` 从 27ms 降到
profile 里不可见；切图总延迟从 32ms 降到 4.8ms。

## 4. 优化后

| 指标 | 优化后 | 变化 |
|---|---:|---:|
| 首次导入（同步，3 次） | **0.166s / 0.169s / 0.158s** | 约 **40×** |
| 其中 `_refresh_file_panel` | 0.008–0.009s | 约 800× |
| 其中 3000 次行创建合计 | 0.10s | 不变 |
| 首图加载 | 0.024s | 约 2× |
| 连续切图 30 次 | **mean 4.8ms / p50 4.6ms / p95 5.3ms / max 6.7ms** | 约 **7×** |
| 切图期间后台扫描进行中 | p50 5.05ms / p95 5.91ms | 基本无感 |
| 筛选一遍 / 进度一遍 | 8ms / 5ms | 不变（已缓存） |
| 后台低置信第二轮（冷缓存） | **8.1s**（3000 个 JSON，1000 个低置信） | 不阻塞 UI |
| 后台低置信第二轮（热缓存） | 0.89s | — |

后台第二轮完成前，进度行为 `待复核 …`；完成后为 `待复核 1000`，
文件行角色与计数一致。切图测量在扫描进行中与扫描完成后均保持 5ms 量级。

## 5. 测试与门禁

- 新增 `tests/test_utils/test_async_low_conf.py` 8 条：低置信判定、
  阈值覆盖、不可读/缺失文件、worker 两轮批次、批量角色写回、
  `…` 占位到真实计数；`test_widget_wiring` 增加 uniform item sizes 守卫。
- 契约更新：新增 `_low_conf_scan_pending`、`_file_item_annotation_checked`、
  `file_filter_combo`、`file_progress_label` 四个成员（139 → **143**）。
- 全量 **1681 passed / 1 skipped / 61 subtests**；smoke **17/17**；
  acceptance **17/17**；black **206 files unchanged**；flake8 **214 findings
  无回归**；codespell 无新增。

## 6. 边界

- 切图数字来自 96×128 小图；大图解码/画布绘制另计，未做图像缓存优化。
- 后台低置信扫描在冷缓存下仍需 8–11s（3000 个 JSON）；它不占 UI 线程，
  但会占用磁盘/CPU。若以后需要进一步降低，可按文件 mtime 做跨会话缓存，
  或在空闲时再启动第二轮。
- 3000 行列表的 `_visible_rows` 仍会遍历所有行（约 1.4ms/次切图）；
  当前总延迟已低，未继续优化。
