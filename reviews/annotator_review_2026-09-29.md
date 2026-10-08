# LabelAndTrain 标注人员视角审查（2026-09-29）

**一句话摘要**：手速这条线基本齐了——画框有单键（`R`/`P`）、数字键 1-9 再补 0、审核流一键到底（`Ctrl+Shift+J`/`K`）、跨图撤销和落盘前快照今天都补上了；但**交付闭环是断的**：审核员只能把一张图打成「需返工」，**留不下一个字**说明哪里错，返工的人只能靠猜；另外**「批量编辑标签」默认作用于整个文件夹、直接改写标注文件且没有备份、没有二次确认**——这是标注工座位上唯一一处"一次点击毁一整类"的活口。

仓库 `main @ 11e505e`（v1.0.0-beta.6）｜909 tests｜覆盖率棘轮 44。
审查立场沿用 `labelandtrain-audit` 规程，但换成**一线标注工**的座位：只问"一张图要几下手"、"被打了回我怎么知道改哪"、"我会不会把整批数据搞坏"。

> 与 `reviews/annotation_review_2026-09-29.md`（使用者视角）的分工：那份聚焦快捷键三层一致性与导出安全；这份只走**标注工日常那条线**——画→选类→翻→交→返工。重叠处我独立复验了，不转抄。

---

## 一、分维度评分

| 维度（标注工视角） | 评分 | 依据（怎么验的） |
|---|---|---|
| 单图手速：画框 → 选类 → 翻下一张 | ★★★★☆ | 创建工具有单键（`jllabeling_config.yaml:162-165`：点 `Shift+P` / 多边形 `P` / 四边形 `T` / 矩形 `R`）；工具画完不重置，同类形状可连画（`canvas.py:91`、`345-354`）；数字键 1-9→0（`digit_controller.py:24`）；扣分项见 🟡 3/4 |
| 类别/标签操作 | ★★★☆☆ | 项目标签开局预分配数字键（`file_lifecycle.py:390`）、对话框有前缀补全（`label_dialog.py:1462`）；但「沿用上一标签」**默认关**（🟡 4），且类别管理器是"全量批量改写"（🔴 2） |
| 交付与返工闭环 | ★★☆☆☆ | 状态机三值齐、筛选有「需返工」；但**打回无原因**（🔴 1）、无「未复核」筛选、「下一张未检查」会把已打回的图算进去（🟡 3） |
| 数据安全（标注工真能碰到的） | ★★★☆☆ | 跨图撤销 + 写前快照今日落地且我独立复验成立；扣分项见 🔴 2 |
| 上手 / 可发现性 | ★★★☆☆ | F1 分组清楚（`shortcuts_help.py:12-147`）、画布空状态有引导（`canvas_empty_state.py:35-44`）；但文档与实现不符（🟡 5） |
| 团队 / 可追溯 | ★★☆☆☆ | 逐框只记 `human`/`model`（`provenance.py:20-23`），**不记人**；无审核人、无逐图备注（🔵 6） |

---

## 二、🔴 高

### 1. 打回没有原因通道：审核员说得出"不行"，说不出"哪里不行"

返工动作只有"置状态 + 跳下一张"，**不携带任何意见**：

```python
# anylabeling/views/labeling/filelist/controller.py:66-77
def mark_rejected_and_next(self, _value=False):
    """Send the current image back for rework and keep moving."""
    ...
    widget._apply_review_state(REVIEW_REJECTED)
    widget.open_next_unchecked_image()
```

`apply_review_state()`（`filelist/controller.py:28-51`）只写三个字段：`review_state` / `checked` / `reviewed_at`。字段清单在 `schema.py:10-16`（`XLABEL_BASIC_FIELDS`）与 `filelist/roles.py:22-24` 里都是这三样，**没有 comment / note / reason 这一类字段**（我按 `comment`/`reject_reason`/`review_note`/`remark`/`feedback`/`打回`/`驳回`/`意见` 逐词搜过，全仓无写入点）。

后果，站在返工人这一侧：

- 打开项目 → 筛选「需返工」能列出被打回的图（`label_widget.py:511-516`），但**每张图的全部信息**是：一个红点图标（`items.py:81-83`）、一句悬停提示「图标含义：已打回，待人工返工」（`items.py:171-176`）、一个 `reviewed_at` 时间戳。**哪一张、哪个框、什么原因，一个字都没有。**
- 逐框层面唯一的"人工意见"是 `difficult`（困难标志，`label_dialog.py:1362`），但它是个布尔勾，而且没有任何地方把"被打回"与"标了困难"关联起来。
- 所以"标完 → 知道要返工"之间，**状态写进去了，意见通道缺失**。这是交付闭环唯一的断点，也是最贵的那个：审核员每一次打回都要另外用微信/口头告诉标注工，工具本身帮不上。

**建议**：给 `review_state` 旁边加一个 `review_note`（自由文本或一组预设原因码，如"漏标/类别错/框偏/多标"），打回时弹一个**可选**的轻量输入；返工时在状态栏或画布顶部显示这条意见。不做逐框批注也能补上 80% 的价值。

### 2. 「批量编辑标签」默认全量、直接改写、无备份、无二次确认

入口是菜单里的「批量编辑标签」（`Alt+L`，`jllabeling_config.yaml:175`；`label_widget.py:1815` → `LabelModifyDialog`）。它的默认作用范围是**整个文件夹**：

```python
# anylabeling/views/labeling/widgets/label_dialog.py:772-773
self.start_index = 1
self.end_index = len(self.image_file_list)
```

勾上某类别的「删除」再点 Go（`update_range` → `confirm_changes` → `modify_label`），发生的是：

```python
# anylabeling/views/labeling/widgets/label_dialog.py:1122-1134
for shape in src_shapes:
    label = shape["label"]
    if self.parent.label_info[label]["delete"] and not shape.get("locked", False):
        continue                      # ← 删掉这个类别的所有框
    if self.parent.label_info[label]["value"]:
        shape["label"] = ...          # ← 或改名
    dst_shapes.append(shape)
...
with open(label_file, "w", encoding="utf-8") as f:
    json.dump(data, f, indent=2, ensure_ascii=False)   # 直接覆盖
```

而且不止 `.json`——`label_dialog.py:1158-1166` 还会连带重写 `classes.txt` 与 YOLO sidecar。**这条路径全程没有备份、没有"你即将删除 X 个文件里的 Y 个框，确定？"的确认**（我搜过 `backup`/`snapshot`/`QMessageBox`/`confirm`，该文件里唯一的确认弹窗是"重置全部快捷键"，`label_dialog.py:259-272`，与此无关；成功提示是**事后**弹的 `Popup`，`label_dialog.py:1088-1093`）。

为什么这比"导出目录被清空"更该管：**写前快照不覆盖它。** `utils/session_snapshot.py` 只在 `file_lifecycle.save_labels()`（当前图）里触发，它自己的文档字符串就写明"批量写不经过 `file_lifecycle.save_labels`"（`session_snapshot.py:24-27`）。画布撤销是内存里当前图的栈，更管不到磁盘上的批量改写。于是：**一次点击 = 整个文件夹里某个类别的框全没了，且没有任何回退路径。**

**建议**：①默认范围改成"当前图片"或"仅所选"，要全量必须手动改数字；②点 Go 前弹一次带**影响计数**的确认（"将改写 N 个文件、删除 M 个框"，默认取消）；③写前复用 `session_snapshot` 同款备份。三条都是低成本。

---

## 三、🟡 中

> **状态更新（2026-09-29 晚）**：**3、4、5 号已修**。
> **3 号**：导航判定从布尔 `UserRole` 换成 `review_state == unchecked`——`filelist/items.py` 新增 `file_item_is_unchecked`（含 legacy 布尔回退），`FileReviewController` 的上一张/下一张两处扫描改用它，因此已打回与已检查的图都不再是「下一张未检查」的目标；筛选下拉框补了「未复核」（`label_widget.py:515`，`_apply_file_filter` 新增 `unreviewed` 分支）。测试：`test_visible_row_navigation.py` +3（正向跳过、反向跳过、rejected 永不成为目标），`test_review_state_flow.py` +2（未复核筛选、rejected 不算未复核）。
> **4 号**：空画布引导（`widgets/canvas_empty_state.py`）加了一行「提示：按 Ctrl+Y 可自动沿用上一标签，成片同类时更省手」。`Ctrl+Y` 此前只在 F1 的「其它设置」组里出现，新标注工发现不了。
> **5 号**：`docs/zh_cn/user_guide.md` 的「绿点=已检查 / 灰点=未检查」两态说法换成五种圆点图标的表（未标注 / 已标注 / 负样本 / 已检查 / 需返工），并补一句「未检查 = 未复核」；`docs/zh_cn/fork_features.md` 补上 `Ctrl+Shift+J`，另加一行「只看未复核」。

### 3. 「下一张未检查」把已打回的图当成未检查，审核员会绕回自己刚打回的图

导航动作判定"是否未检查"用的是布尔值：

```python
# anylabeling/views/labeling/filelist/items.py:95-96
def file_item_annotation_checked(item):
    return item.data(Qt.ItemDataRole.UserRole) is True
```

而 `UserRole` 被写成 `is_confirmed(state)`（`items.py:32`），**`rejected` 因此是 `False` → 被判为"未检查"**。于是 `open_next_unchecked_image()`（`filelist/controller.py:141-161`）会把你刚打回的那张再算作"待检查"，一路翻到头就会**绕回自己打过回的图**。

同时筛选下拉框里**没有「未复核 / 未检查」这一项**——只有 全部 / 未标注 / 已标注 / 已检查 / 需返工 / 待复核（`label_widget.py:511-516`）。审核员想"只看我还没看过的"，工具里没有这条路；只能选「全部」再靠图标颜色分辨。

**建议**：导航判定改成"未复核"= `state == unchecked`；下拉框补一个「未复核」。

### 4. 「自动沿用上一标签」默认是关的

`auto_use_last_label: false`（`jllabeling_config.yaml:7`），开关是 `Ctrl+Y`（`:242`）。代码里它能让新框直接继承上一次的标签（`label_editing.py:500-505`、`644`），在单类占多数或成片同类的数据集上，这是最省鼠标的一个动作。默认关本身可以讨论（负样本图有风险，参见 `fork_features.md:63-75`），但**新标注工不会知道它存在**——F1 里它在「其它设置」组（`shortcuts_help.py:139`），不在画布或首次提示里。

**建议**：首次打开文件夹时给一句状态栏提示，或在画布空状态引导（`canvas_empty_state.py`）里加一行"按 Ctrl+Y 可自动沿用上一标签"。

### 5. 文档与实现不符，正好落在"新标注工怎么认状态"这件事上

- `docs/zh_cn/user_guide.md:109` 说文件列表用**圆点**展示状态：**绿色=已检查、灰色=未检查**（两态）。
  实现是**五种图标**：未标注 / 已标注 / 负样本 / 已检查 / 需返工（`label_widget.py:536-544` + `items.py:71-92`）。一个标注工照文档去找"绿点/灰点"，会看不懂屏幕上的红点和别的颜色。
- `docs/zh_cn/fork_features.md:54` 写「标记已检查并下一张」"快捷键见 F1"，没给键；实际默认是 `Ctrl+Shift+J`（`jllabeling_config.yaml:192`）。同一张表里下一行却写了 `Ctrl+Shift+K`（`:193`），一行有一行无，读起来像是前者没键。

**建议**：把 `user_guide.md:109` 那段改成五种图标的表（照 `items.py:111-122` 的 `review_state_name`），`fork_features.md:54` 补上 `Ctrl+Shift+J`。

---

## 四、🔵 低

> **状态更新（2026-09-29 晚）**：**7 号随 🔴2 一并解决**——点 Go 前先弹带影响计数的确认，已不再是"只有事后反馈"。**8 号是误报**：逐字复验 `resources/translations/zh_CN.qm`，`Manage Labels: Rename, Delete, Hide/Show, Adjust Color`、`Save visualization image`、`Manage Group ID` 等都有译文（`QTranslator.translate` 实测返回中文）；把 `label_widget.py` 里所有英文字面量过一遍，只剩 `YOLO HBB` / `YOLO Seg` / `YOLO Pose` 三个格式名没译文，而它们本就是英文缩写。**6 号未动**：它要先定身份模型（人名从哪来、写不写进 JSON、多人协作怎么合并），是一次功能设计而不是收尾，需要先拍板。

6. **没有逐图备注，也没有"谁标的/谁审的"**：`provenance.py:1-6`、`20-23` 只记录 shape 的 `source`（`human`/`model`/`unknown`）与模型名、权重摘要；全仓搜 `reviewer`/`annotator`/`username` 没有身份字段。多人协作时，一张图标错了无法追到人。文件列表悬停的计数（`items.py:161-170`）也只有"模型/人工/未记录"三分。
7. **批量操作只有事后反馈**：`label_dialog.py:1088-1093` 的"Labels modified successfully!"是写完之后弹的；事前只有范围合法性校验（`label_dialog.py:1231-1257`）。
8. **英文 tooltip 残留**：`label_widget.py:5544` 的 "Manage Labels: Rename, Delete, Hide/Show, Adjust Color" 等仍是英文（与使用者视角报告同源，这里只作记录）。

---

## 五、已达水准的部分（点名 + 我怎么验的）

- **单键创建 + 可连续画**：`R` 矩形 / `P` 多边形 / `Shift+P` 点 / `T` 四边形（`jllabeling_config.yaml:162-165`）；`canvas._create_mode` 只在 `toggle_draw_mode` 里被改（`canvas.py:345-354`），画完一个不会自动退回编辑模式，同类形状可以一个接一个画。
- **数字键免配置**：槽位是 `1-9` 再补 `0`（`digit_controller.py:24`，0 不再是死键）；打开项目即按声明标签预分配（`file_lifecycle.py:390` → `digit_controller.py:94`）；首见类别自动占位（`:62`）。
- **标签对话框能纯键盘用**：装了 `QCompleter`（"startswith"，`label_dialog.py:1462`、`1476`），默认焦点在输入框（`:1735`）——>10 类时这是一条完整的键盘路径。
- **审核流一键到底**：`mark_checked_and_next=Ctrl+Shift+J`、`mark_rejected_and_next=Ctrl+Shift+K`、`toggle_annotation_checked=Ctrl+Alt+K`、`open_next_unchecked=Ctrl+Shift+D`、`open_prev_unchecked=Ctrl+Shift+A`（`jllabeling_config.yaml:192-199`）。
- **打回参与下游，不是死状态**：导出按审核态分流（`export.py:186-213`、`420-436`、`530-532`，未检查与需返工都会被跳过并计数）；训练侧 `only_checked_files`（`services/auto_training/ultralytics/general.py:317-318`）。
- **文件列表不卡 UI**：label JSON 由后台线程分批扫（`utils/async_label_check.py:90-157`），行上只放状态位、不算形状数，计数只给当前打开那张（`items.py:135-141`）。
- **跨图撤销 + 写前快照（今日新修，我独立复验成立）**：撤销栈按图分桶、LRU `MAX_BUCKETS=20`（`shape_history.py:26`、`71-97`），旧属性名由 property 保住（`:109-123`）；快照在 `save_labels` 写盘**之前**取，每个（会话×文件）只留一份（`session_snapshot.py:50-67`、`88-97`）。

---

## 六、下一步建议（按性价比，只列标注工这条线）

| # | 事项 | 成本 | 为什么排这个位置 |
|---|---|---|---|
| 1 | ~~**「需返工」加意见字段 + 返工提示条**（🔴 1）~~ → ✅ | 低 | 交付闭环唯一的断点，不做则每次打回都要人肉传话 |
| 2 | ~~**类别管理器：改默认范围 + 影响计数确认 + 写前备份**（🔴 2）~~ → ✅ | 低 | 标注工座位上唯一"一次点击毁一整类"的活口，且现有快照不覆盖它 |
| 3 | ~~**「下一张未检查」跳过 rejected；筛选加「未复核」**（🟡 3）~~ → ✅ | 低 | 审核员每天绕的坎，两处小改 |
| 4 | ~~**`auto_use_last_label` 首启提示**（🟡 4）~~ → ✅ | 低 | 省鼠标最直接的一个动作，现在是隐藏的 |
| 5 | ~~**文档对齐 5 种图标 + 补 `Ctrl+Shift+J`**（🟡 5）~~ → ✅ | 极低 | 新标注工认状态的第一课，现在文档教错了 |
| 6 | **真机按一遍审核流**：打开项目→`Ctrl+Shift+D` 连翻→打回一张→筛选「需返工」→返工 | 低（10 分钟，人做） | 上面每一条的手感都只有真机能判 |
| 7 | **逐图备注 / 记录谁标的谁审的**（🔵 6） | 中 | 需先定身份模型，是功能设计不是收尾 |

---

## 七、审查方法（可复现）

```bash
cd /g/LabelAndTrain/LabelAndTrain

# 审核态字段与打回动作：确认没有意见通道
sed -n '5,31p'  anylabeling/views/labeling/schema.py
sed -n '20,24p' anylabeling/views/labeling/filelist/roles.py
sed -n '28,77p' anylabeling/views/labeling/filelist/controller.py
rg -ni "comment|reject_reason|review_note|remark|feedback|打回|驳回|意见" anylabeling/views/labeling/

# 类别管理器的批量改写（默认全量 / 直接覆盖 / 无备份）
sed -n '772,773p'   anylabeling/views/labeling/widgets/label_dialog.py
sed -n '1103,1166p' anylabeling/views/labeling/widgets/label_dialog.py
rg -n "backup|snapshot|Are you sure" anylabeling/views/labeling/widgets/label_dialog.py

# 「下一张未检查」把 rejected 当未检查
sed -n '95,96p' anylabeling/views/labeling/filelist/items.py
sed -n '141,161p' anylabeling/views/labeling/filelist/controller.py
sed -n '511,516p' anylabeling/views/labeling/label_widget.py

# 手速侧：数字键槽位 / 沿用上一标签默认值 / 审核流键位
sed -n '20,27p' anylabeling/views/labeling/shortcuts/digit_controller.py
rg -n "auto_use_last_label|mark_checked_and_next|mark_rejected_and_next|edit_labels" anylabeling/configs/jllabeling_config.yaml

# 文档与实现是否一致
sed -n '105,112p' docs/zh_cn/user_guide.md
sed -n '52,57p'   docs/zh_cn/fork_features.md

# 规模基线
.venv/Scripts/python.exe -m pytest tests --collect-only -q | Select-Object -Last 1   # 909
```

**铁律**：本文件每条都给了 `file:line`；凡"我 grep 不到"，都换过三种以上关键词再落笔（如 🔴 1 用了 `comment`/`reject_reason`/`review_note`/`remark`/`feedback`/`打回`/`驳回`/`意见` 八种形态才写"没有"）。

---

> 本文件与 `annotation_review_2026-09-29.md`（使用者视角）是两份互补的审查：那份看"工具整体"，这份看"标注工这一天"。两份对同一处代码的结论如有出入，以 `file:line` 为准。