# LabelAndTrain 使用者视角审查（2026-09-29）

**一句话摘要**：键盘这条线今天补完了（96/96/96 一致），但**裁剪导出还留着 9/27 修掉的那个洞**——它会把用户选的目录 `rmtree` 掉、不显示路径、不列内容，而它旁边那条路已经改成 Merge/Clear/Cancel 了；**撤销不跨图 + 日常落盘无快照**这两个叠在一起，是"标完 30 张发现第 3 张删错"没有退路的根因。

仓库 `main @ 3197285`（v1.0.0-beta.6）｜836 tests｜覆盖率棘轮 44。
审查立场按 `labelandtrain-audit` 规程：只问手快不快、写错救不救得回来、导出的东西敢不敢直接用。

---

## 一、分维度评分

| 维度 | 评分 | 依据（怎么验的） |
|---|---|---|
| 日常操作效率 | ★★★★☆ | 120 个 `action()` 里 88 个绑配置键 + 10 个数字字面量 = **98 有键**；扣分项见 🟡 3/4/5 |
| 数据安全 | ★★★☆☆ | `keep_prev`×`auto_save` 守护在（6 条回归）、删除默认焦点"取消"、原子写；**扣分项见 🔴 1/2** |
| 导出可信度 | ★★★★☆ | stats 出参 / OBB 往返逐字节 / `classes.txt` + `data.yaml` 落盘 / 审核态筛选齐；扣分项见 🟡 6/7 |
| 质量与审核闭环 | ★★★★☆ | 审核态三值 + 文件列表圆点 + 打回参与训练与导出 + 12 个智能工具 + 漏标扫描；导出侧不联动体检（🟡 6） |
| 可发现性 | ★★★☆☆ | F1 96 条与设置页字段数、真 QAction 三者一致，无幽灵键；**扣分项见 🟡 3、🔵 9/10** |
| 与文档一致性 | ★★★★☆ | `user_guide.md` 有 YOLO-only 横幅、检查状态一节与程序一致；扣分点：🔵 9（文档写 0–9，自动分配只到 9） |

---

## 二、🔴 高（会静默毁数据 / 断了退路）

> **状态更新（2026-09-29 晚，commit `fe6ca9b` / `a7f4bc5`）**
> **1 号已修**：四处对话框统一到 `utils/output_dir.py`，"目标目录含被标注目录"时不再提供 Clear，Merge 成为默认按钮，Clear 仍需二次确认并显示绝对路径；新增 14 条测试 + 两条棘轮（`utils/` 下除 helper 外不得出现 `rmtree(save_path)`；每个调用必须声明 `protected_paths`）。
> **2 号已修一半**：**快照部分完成**（`a7f4bc5`，11 条测试）——`utils/session_snapshot.py` 在 `file_lifecycle.save_labels` 写盘前，把每个标注文件按（会话 × 目录）各留一份，落在批量工具同一个 `.label_backups` 命名空间里，因此直接出现在既有的「从备份恢复标注」选择器中并标注「自动快照」，保留策略不变。**剩下的是撤销栈本身仍不跨图**——`canvas.py`（预算 3772）与 `label_widget.py`（预算 6813）都在冻结的尺寸上，需要一次明确的预算决策，而不是顺手塞两行。

### 1. 裁剪导出会把用户选的目录整个删掉，且不告诉你删的是什么

`anylabeling/views/labeling/utils/crop.py:328-355`：

```python
save_path = path_edit.text()
if osp.exists(save_path):
    msg_box.setText(self.tr("Directory already exists. Choose an action:"))
    ...
    msg_box.addButton(self.tr("Overwrite"), YesRole)
    msg_box.addButton(self.tr("Cancel"), RejectRole)
    ...
    if clicked_button == cancel_button: return
    else:
        shutil.rmtree(save_path)      # ← Windows 下不进回收站
        os.makedirs(save_path)
```

- 后果：点一次 Overwrite，`save_path` 里原有内容**递归删除且不可恢复**。对话框只说"目录已存在"，**不显示绝对路径、不列条目数、不提供合并**。
- 可达性：**可达**——`save_crop` 挂在菜单上（`label_widget.py:5508/5510`，`6427` 进菜单），不是死代码。
- 默认值本身是安全的（`<图像目录上一层>/crops`，`crop.py:260-262`），但那一栏是自由文本 + 浏览选择，填成已有数据集根目录或图像目录本身都是一次点击的事；且**没有任何"输出目录 == 输入目录或其父目录"的硬拦截**（全文件 grep 只有一处 `osp.exists`，无路径比较）。
- 对照：同一天（9/27）修过的 YOLO 导出已经是 `Merge`(默认) / `Clear` / `Cancel`，Clear 需二次确认并列出路径（`utils/export.py:566` 一带）。**同一个对话框模式，修了三份里的一份，漏了 crop。**

**建议**：把 crop 的输出目录校验抽成与导出同一套（Merge/Clear/Cancel + 显示绝对路径与条目数），并硬拦截"输出等于图像目录 / 图像目录的父目录 / 项目根"。

### 2. 撤销不跨图 + 日常落盘没有版本快照

- `widgets/canvas.py:3691` 注释写得很直白：`# Undo history does not survive a file switch; neither may redo.`
- 备份只在智能工具的批处理流程里触发（`utils/smart_tools.py:1147`、`:1242`）；`auto_save` 走 400ms 防抖 + `mkstemp+fsync+safe_replace`，但**每次写的都是同一个文件**，没有版本。

叠加效果：切图即失去撤销；切走之后那一张的写入是最终状态。**"标完 30 张才发现第 3 张删错了"既回不去，也没有任何版本可回退。**

**建议**：①落盘前把当前盘上文件推一份到 `.label_backups/_auto_<stamp>/`，只保最近 N 次（复用 `backup_label_files` / `_prune_backup_runs` 的约定）；②把 canvas 的 shape history 按 filename 分桶（照 `widgets/view_state.py` 的 `ViewStateStore` 模式）。

---

## 三、🟡 中（每天绕的坎）

### 3. 22 个动作仍然没有键盘入口，而且用户自己也绑不了

现在"无键"是**白名单**（`tests/test_settings/test_shortcut_bindings.py` 的 `NO_SHORTCUT_BY_DESIGN`），不是缺口——但这 22 个里有几个是标注过程中真的会遇到的：`save_crop`、`save_visualization_image`、`save_with_image_data`、`use_system_clipboard`、`toggle_shape_lock`、`copy_coordinates`、`confirm_classification`（另有 8 个 export/upload 与 `save_auto`、`set_cross_line`、`run_history`、`ultralytics_train` 属一次性，确实不必绑）。

关键不在"没键"，而在**它们连 yaml 键位条目都没有** → 设置页看不到、F1 看不到、**用户没有任何途径自己绑**。今天补的 18 个正是因为这一点才被当成缺口。

**建议**：给这批加 null 键位条目（`_shortcut_fields()` 由模板派生，加进 yaml 即自动进设置页），F1 增加「未绑定动作」分节灰显 + 一句"可在设置页绑定"。

### 4. 类别超过 9 个就没有直接键盘路径

`shortcuts/digit_controller.py:75`：`for digit in range(1, 10)`，且 `if len(used) >= 9: break`。第 10 个类别起只能走 `Ctrl+E` 的标签对话框，或用 `Ctrl+Shift+N` 循环——多类别数据集每天都会碰到。

**建议**：数字键扩到两位序列（先按首位再按次位），或给标签对话框加前缀过滤 + 默认焦点落在输入框。

### 5. 空项目里按 1-9 没反应

自动分配挂在 `load_shapes` 的尾部（`label_widget.py:2885 → 2887`），**没有 shape 就不分配**。所以新项目第一步仍然必须用鼠标在对话框里选一次标签（每个类别一次），而这恰恰是数字键要消除的那一步。

**建议**：打开项目时若 `config.labels` 非空，直接按顺序分配给 1-9；或在状态栏给一句"按 Alt+D 配置数字键"的提示。

### 6. 导出前没有体检

`utils/export.py` 里 grep 不到 `data_audit` / `run_data_audit`——数据体检（`Ctrl+Alt+A`）是独立工具。所以可以导出"200 张空标注 / 类别不在 `classes.txt`"的数据集，而摘要只报**转换**跳过了什么，不报**源数据**本身有病。

**建议**：导出对话框挂一次前置体检（复用 `data_audit` 的判据），把计数写进导出摘要。

### 7. 导出没有 manifest

写了 `data.yaml`（`utils/export.py:212`，`:580` 调用），但没记录"这次用了哪些筛选条件、类别映射、跳过了哪些文件"。同一批数据导两次，不同之处无法复现。

---

## 四、🔵 低（收尾项）

8. **VOC/COCO 两份逐字副本仍是旧行为（当前无 GUI 入口的死代码）**：~~`utils/export.py:801`（Yes/No/Cancel → `rmtree`）、`:1007`（Overwrite/Cancel → `rmtree`）~~ → **✅ 2026-09-29 已随 `fe6ca9b` 一并统一**（两份副本的行为现在与 YOLO 完全一致，`rmtree` 只剩 `output_dir.py:96` 一处，由棘轮守住）。剩下的是"三份重复代码"这个结构问题本身：现在四处调用同一个实现，重复已经消失。
9. **`digit_shortcut_0` 是半个死键**：action 存在（字面量 `"0"`），但自动分配只填 1-9，出厂 `digit_shortcuts: {}`，所以 `0` 只有手动 `Alt+D` 映射后才可用；而 `docs/zh_cn/user_guide.md:769` 写的是"数字键（0–9）"。
10. **55 个模板叶子在设置页够不到**：多数是有意排除（语言/主题/dock 显隐/flags 走菜单或对话框）。逐项确认过有其它入口的：`store_data`（`label_widget.py:5123` 菜单勾选）、`device` / `custom_models`（自动标注面板）、`startup_show_project_manager`（项目切换器）、`show_*` / `keep_prev_*`（View 菜单勾选）。**真正只能手改 `~/.xanylabelingrc` 的剩 5 个**：`canvas.attributes.background_color` / `border_color` / `text_color`、`canvas.brush.max_undo_steps`（=30）、`canvas.brush.max_undo_memory_mb`。
11. **真机手感仍未测，且今天新加的 18 个键位一次都没按过**：`measurements_2026-09-27.md` §二 的 5 步清单没跑；另外 `Ctrl+Alt+1/2/3` 在部分输入法/系统热键下可能被截胡，`Ctrl+Alt+D/E/G/O/V` 也需要逐个实按确认（offline 测试只能证明 QAction 上挂了对应序列，证不了系统不抢）。

---

## 五、已达水准的部分（点名 + 我怎么验的）

- **快捷键四层结构**：模板 96 键 / runtime 映射 96 / F1 96，三者等值；AST 分类 120 个 `action()` 得 88 config + 10 字面量 = 98 有键，无幽灵键、无"改键需重启"、无"F1 不展示"。守卫在 `test_shortcut_bindings.py`（4 条）与 `test_widget_wiring.py`（真 QAction 逐条对拍 87/87）。
- **导出可信度**：`custom_to_yolo(stats=...)` 出参 + 兜底摘要；OBB 端到端往返坐标误差 < 0.001 px、二次导出逐字节相同（`test_yolo_obb_roundtrip.py`）；`classes.txt` 优先取项目 `config.labels`；导出目录写 `data.yaml`；审核态筛选与训练侧 `only_checked_files` 对齐（`test_export_summary.py`）。
- **`keep_prev` × `auto_save` 静默写盘的守护**：`set_dirty(from_inherited=True)` 跳过自动保存 + 状态栏区分两种 dirty + `test_keep_prev_proposal.py` 6 条（含"普通图片切图仍静默保存"的反向守卫）。
- **破坏性操作的交互**：`_confirm_destructive_action` 默认焦点在"取消"、回车不会误删，且"本次会话不再询问"只存内存（`label_widget.py:4149`）。
- **数字键免配置**：`digit_controller.auto_assign_digit_shortcuts` 首次见到的类别自动占用 1-9，无需先按 `Alt+D` 配。
- **门禁体系**：全仓 `black --check`（钉 26.5.1，四处一致有测试守）、flake8 基线（101 条 236 findings）、覆盖率 44、尺寸预算、widget 契约双向锁定、release 三段校验。

---

## 六、下一步建议（按性价比，只列本项目）

| # | 事项 | 成本 | 为什么排这个位置 |
|---|---|---|---|
| 1 | ~~**crop 的目录守护**~~ → ✅ `fe6ca9b` | 低 | 唯一一处"一次点击毁一整目录"的活口，且它所在路径从没被加固过 |
| 2 | **落盘前快照** ✅ `a7f4bc5` ／ **跨图撤销** ⬜ | 中 | 快照已落地；撤销栈跨图需要一次尺寸预算决策 |
| 3 | **22 个无键动作进 yaml + F1「未绑定」分节** | 低 | 直接复用今天建好的三层机制，一次配置改动 |
| 4 | **数字键 >9 与空项目冷启动** | 中 | 多类别数据集每天碰到，且现在没有任何提示 |
| 5 | **导出前置体检 + manifest** | 低 | 出口最后一个"不告诉你"的地方 |
| 6 | **真机 5 步清单 + 逐按 18 个新键位**（人做，10 分钟） | 低 | 唯一能验证"手快"和系统热键冲突的一步 |

---

## 七、审查方法（可复现）

```bash
cd /g/LabelAndTrain/LabelAndTrain

# 动作键位覆盖：AST 取第 3 位置参 + shortcut= 关键字，分类 config/字面量/无键
#   → 120 / 88 / 10 / 22（本报告 §一 的数字出自这条）

# 三层一致性（yaml / runtime / F1）与幽灵键、死键
#   → 96 / 96 / 96，幽灵 0，死键 0

# 导出/裁剪的目录策略
grep -rn "rmtree" anylabeling/views/labeling/ --include=*.py
grep -rn "manifest\|run_data_audit" anylabeling/views/labeling/utils/export.py   # 空

# 撤销与快照
grep -n "does not survive a file switch" anylabeling/views/labeling/widgets/canvas.py
grep -rn "backup_label_files" anylabeling/ | grep -v "def "

# 数字键范围
sed -n '70,86p' anylabeling/views/labeling/shortcuts/digit_controller.py

# 门禁
QT_QPA_PLATFORM=offscreen .venv/Scripts/python.exe -m pytest tests -q
.venv/Scripts/python.exe scripts/check_flake8_baseline.py
.venv/Scripts/python.exe -m black --check anylabeling tests scripts
```

**铁律**：本文件每条都给了 `file:line`；凡"我 grep 不到"，都换过三种形态再落笔（`manifest`、`run_data_audit`、`data_audit` 各查了一遍才写"没有"）。

---

> **恢复说明（2026-09-29 12:55）**：本文件在工作区根目录被意外删除后由会话上下文重建（原文由本会话撰写，内容一致），并把"恢复后已完成的修复"合并进上面的状态更新。同时**移动位置**：现在存放在仓库内 `reviews/`（受 git 跟踪），不再放 `G:\LabelAndTrain\` 根目录。
