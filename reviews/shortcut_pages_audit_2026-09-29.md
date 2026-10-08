# 快捷键三张页面审查（2026-09-29）

针对「设置页快捷键页 / F1 速查表 / 数字键管理器」三张页面的健康度核查。
前情：键位已从 78 扩到 96（有键动作），22 个无键动作以 `null` 进模板并可在设置页绑键，
F1 加了「未绑定动作」分节。本次聚焦**页面本身有没有问题**。

## 结论速览

| 页面 | 状态 | 说明 |
|---|---|---|
| F1 速查表 | ✅ 健康 | 22 无键动作有中文描述，单独「未绑定动作」分节，绑键后自动消失 |
| 数字键管理器（Alt+D） | ✅ 健康 | `DIGIT_SLOTS = (1..9, 0)`，槽位 0 不死，自动分配覆盖 |
| 改键冲突检测 | ✅ 健康 | `controller._validate_shortcut_conflicts` 生效，重复即标红+提示 |
| **设置页快捷键页** | 🔴 1 处缺陷 | 22 无键动作被塞进「视图」分组 + 显示为英文机器标签 |

## 1. 🔴 设置页：22 个无键动作呈现不一致（唯一实质缺陷）

### 现象
打开「设置 → 快捷键 → 视图」分组，里面混着两类东西：
- 真正的视图类快捷键（放大/缩小/适应窗口/显示标注…）
- 22 个导出/回导/保存类动作（导出 YOLO 水平框、回导 YOLO 分割、保存裁剪图…）

且这 22 个在中文构建里**显示为英文机器标签**：

| 配置键 | 设置页显示 | F1 速查表显示 |
|---|---|---|
| `export_yolo_hbb_annotation` | `Export Yolo Hbb Annotation` | `导出 YOLO 水平框` |
| `upload_yolo_seg_annotation` | `Upload Yolo Seg Annotation` | `回导 YOLO 分割` |
| `use_system_clipboard` | `Use System Clipboard` | `使用系统剪贴板` |
| `copy_coordinates` | `Copy Coordinates` | `复制选中标注的坐标` |
| `save_crop` | `Save Crop` | `保存裁剪图` |
| `toggle_shape_lock` | `Toggle Shape Lock` | `锁定/解锁选中标注` |

### 根因（两层）
1. **分组错误**：`settings/schema.py` 的 `_shortcut_fields()`（约 1159-1173 行）把模板里
   凡不在 `_shortcut_category_map()` 中的动作，统一 fallback 到 `secondary="View"`。
   22 个无键动作都不在 category_map 里，于是被丢进「视图」分组，与真实视图快捷键混排，
   分组标题变成 `视图 (35)`，用户很难在「视图」里找到「导出 YOLO」。
2. **标签未本地化**：这些动作的标签走 `_shortcut_label()` 的兜底分支
   `chunk.capitalize()` 现场拼英文（`Export Yolo Hbb Annotation`）。
   该串是运行时生成、不在 `zh_CN.ts` 翻译目录里，因此 `self.tr()` 找不到译文、原样输出英文。
   而 F1 速查表用的是 `UNBOUND_ACTIONS` 里**硬编码的中文**，永远中文。

> 性质：功能可用（能绑键、有冲突检测），但**呈现层面**与 F1 不一致、且破坏中文 UI 完整性。

### 建议修复（两处，均小改）
- **统一中文描述来源**：在 `settings/schema.py` 建一张
  `SHORTCUT_DISPLAY_NAMES = {<config_key>: <中文>}`（复用 `shortcuts_help.UNBOUND_ACTIONS`
  + `SHORTCUT_GROUPS` 的描述），`_shortcut_label()` 优先查这张表，命中即返回中文。
  这样设置页与 F1 用同一份文案，单一数据源。
- **单独的 secondary 分组**：在 `SETTINGS_SHORTCUT_SECTIONS` 增加一个
  `("Other", "未绑定（可绑键）")` 之类的分组，把 22 个无键动作归入它，而不是 `View`。
  绑键后该分组自动变空（与 F1 行为一致）。

## 2. ✅ 已确认健康的部分（消除此前疑点）

- **改键冲突检测存在**：`settings/controller.py:388 _validate_shortcut_conflicts`
  在 `update_field` 的三处入口（229/331/338）触发；重复键抛 `SettingsValidationError`，
  对话框对源字段与冲突字段双方标红并提示 `Shortcut 'X' conflicts with Y`。
  `SHORTCUT_DUPLICATE_WHITELIST` 已放行 `undo`/`undo_last_point` 共用 Ctrl+Z。
- **数字键槽位 0 不死**：`shortcuts/digit_controller.py:24` `DIGIT_SLOTS = tuple(range(1,10)) + (0,)`
  `_free_slot()` 遍历它，自动分配/预分配都覆盖槽位 0；管理器对话框 `label_dialog.DigitShortcutDialog`
  按 `DIGIT_SLOTS` 渲染 10 个槽位（含 0）。
- **F1 速查表**：`build_shortcut_rows` 正确跳过空键、把 22 个无键动作归到
  `UNBOUND_GROUP_TITLE = "未绑定动作（可在设置页绑键）"`，绑键后该分节自动消失，文案全中文。

## 下一步

仅设置页一处缺陷可修。是否执行修复，等你确认（按惯例「按照建议执行」即开工）。
