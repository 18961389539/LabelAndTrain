# 结构拆分收尾（2026-10-26）

`reviews/module_review_2026-10-08.md` 把 `smart_tools.py` 和
`ultralytics_dialog.py` 列为最后两个 God Object。这一批把两者都推进到
可维护的边界：智能工具按职责拆成 8 个模块并删除原文件，训练对话框把
运行记录与数据集清理搬到独立模块，两个文件都纳入体量棘轮。

## 1. 智能工具：1920 行单模块 → 8 个职责模块

`utils/smart_tools.py` 原本 1920 行，40 个顶层定义混了阈值校准、数据分析、
漏标扫描、陈旧框审计、迭代看板、复核跳转、重复归档、备份恢复、模板预标注
等职责。拆分后：

| 模块 | 行数 | 职责 |
|---|---:|---|
| `smart_common.py` | 62 | 标签/图片路径、读标签、已确认表的共享助手 |
| `smart_analysis.py` | 302 | 阈值校准、数据智能分析 |
| `smart_missing.py` | 305 | 漏标扫描线程、结果写入 |
| `smart_stale.py` | 470 | 陈旧框审计、清理报告、批量删除 |
| `smart_review.py` | 278 | 迭代看板、复核跳转、重标监听、训练建议 |
| `smart_archive.py` | 132 | 重复图片归档 |
| `smart_backup.py` | 136 | 从备份恢复标注 |
| `smart_prelabel.py` | 256 | 模板传播、预标注写入 |
| `smart_ui.py` | 385 | 共享结果树对话框 + 后台任务线程/进度框 |

- `_SmartTaskThread` / `_make_progress_dialog` 从旧模块移到 `smart_ui.py`，
  四个动作模块共用它，不再各自复制线程/进度 UI。
- `smart_tools.py` **删除**，没有留 re-export façade；`label_widget.py`、
  `ultralytics_dialog.py` 和测试改为直接从功能模块导入。菜单分组
  （检查与诊断 / 复核与建议 / 批量与恢复）保持原样。
- 最大新模块 470 行；没有任何一个再接近原 1920 行的体量。

## 2. 训练对话框：4559 → 4406 行

`UltralyticsDialog.write_run_metadata` 与 `_offer_dataset_cleanup` 搬到
`views/training/run_maintenance.py`（202 行）：

- `run_meta.json` 的 schema、权重/manifest 的 SHA-1、停训/完成状态的记录
  与 `KEEP_DATASET_BUILDS` / `MIN_CLEANUP_OFFER_BYTES` / `MAX_LISTED_SKIPS`
  的清理策略归这个模块；
- 对话框只保留两个委托方法，`on_training_event` 的调用点和测试的
  `UltralyticsDialog.write_run_metadata.__get__(fake)` 都不变；
- 清理由 `self.tr` 改为 `QCoreApplication.translate("LabelingWidget", ...)`，
  保持 `pylupdate6` 可见；翻译目录已重新生成，移动后的 6 条清理文案已补中文；
- `ultralytics_dialog.py` 纳入体量棘轮，冻结在 **4406** 行，下一次候选是
  `start_export` / `use_weights_for_autolabel` 所在的导出/自动标注块。

`label_widget.py` 拆分后导入块从 12 行变为 14 行，文件 6684 → 6686 行，
仍在 6697 的预算内；`canvas.py` 预算 3381 未动。

## 3. 翻译与门禁同步

- 按仓库流程运行 `scripts/generate_languages.py`（`pylupdate6` +
  `pyside6-lrelease` + `pyside6-rcc`）：位置随代码移动更新，6 条清理文案
  从 `UltralyticsDialog` 移到 `LabelingWidget` 上下文。
- 补齐 lupdate 产生的空翻译：中文源串沿用源文本，英文的
  `Uploading annotations successfully!` 与
  `Error occurred while exporting annotations statistics file.` 手工补中文；
  catalog 现在无空翻译。
- 拆分改变了 flake8 的 `(path, code)` 键：旧 `smart_tools.py` 的条目消失，
  新模块没有引入回归；用 `--update` 把基线刷新为 **214 findings / 93 对**。
- `black --check` **205 files unchanged**；codespell 对新模块无命中。

## 4. 验证

- 全量：**1663 passed / 1 skipped / 61 subtests passed**。
- smoke **17/17**；acceptance **17/17**。
- 单元测试覆盖拆分后的入口：漏标写入/模板预标注/陈旧删除/备份恢复/
  重标监听/重复归档/复核队列/运行记录/停训状态，均通过。
- 没有行为改动：函数体按原文搬移；`smart_ui` 的结果对话框、线程签名与
  进度框样式保持不变；`run_maintenance` 的 JSON 字段、SHA-1 与清理策略
  逐字保留。

## 5. 还剩什么

- `ultralytics_dialog.py` 仍 4406 行；下一刀是导出/自动标注块，它有独立
  状态与错误处理，适合按“导出控制器”抽，而不是继续搬小方法。
- `canvas.py` 的 4 个 mixin 仍是“方法桶”，状态仍在 `Canvas.__init__`；
  这属于 canvas 的控制器化，不在本轮范围内。
- 本轮改动仍未提交；`zh_CN.ts/.qm/resources.py` 的重新生成会带来较大的
  机械 diff，评审时按生成物看即可。
