# LabelAndTrain 改进路线（2026-09-29）

**一句话摘要**：功能面已经过剩，短板全在"手快"和"守护"两条线上——**40 个动作没有任何键盘入口、而且用户连自己绑都做不到**；**撤销栈不跨图、日常落盘没有版本快照**。先补这两个洞，再谈别的。

仓库 `main @ 876c6d7`（v1.0.0-beta.5）｜829 tests｜覆盖率棘轮 44。

---

## 进度（2026-09-29 更新）

| 步骤 | 状态 | 结果 |
|---|---|---|
| **审查新增：crop 目录守护** | ✅ 完成（commit `fe6ca9b`） | 四处"输出目录已存在"对话框统一到 `utils/output_dir.py`；Merge 默认 / Clear 二次确认 / **目标含被标注目录时不给 Clear**；export.py −85 行、crop.py −16 行；14 条测试 + 2 条棘轮 |
| 2 补键位 | ✅ 完成（commit `3197285`） | 18 个动作补齐，模板 78 → 96 键；yaml / runtime / F1 = **96/96/96**，无幽灵键、无"改键需重启"、无"F1 不展示"。`save_to` 拿到 `Ctrl+Shift+E` |
| 2c 防漂移守卫 | ✅ 完成 | `test_shortcut_bindings.py`（AST：绑的键必须在模板里 / 无键动作必须在 `NO_SHORTCUT_BY_DESIGN` 白名单，双向 / 无幽灵键 / 设置页描述不指向不存在的键）＋ `test_widget_wiring.py` 两条（87/87 映射在真 QAction 上对拍；模板键必须"已映射或已登记隐藏"） |
| 3a `save_to` | ✅ 完成 | 见上 |
| 3c black 全仓 | ✅ 完成 | 三个 `auto_labeling` 文件格式化，CI 改为全仓 `black --check`（钉 26.5.1，与 dev extra / pre-commit 三处一致，有测试守）；生成的 `*_ui.py` 从 black 与 flake8 双双排除 |
| **1 守卫：落盘前快照** | ✅ 完成（commit `a7f4bc5`） | `utils/session_snapshot.py`：写盘前按（会话 × 目录）为每个标注文件留一份，落在 `.label_backups` **原有命名空间**（原计划写 `_auto_<stamp>`，实现时改成普通时间戳名——这样既有的「从备份恢复标注」选择器**不用改 UI 就能到达**，保留策略也自动生效）；marker 是 `.txt` 所以不会污染选择器的文件计数；11 条测试，含"快照必须在写之前"的真 `save_labels` 断言。磁盘开销限于标注文件，且只有当前图（自动保存 / Ctrl+S / 审核态切换）走这条路径 |
| 1 守卫：跨图撤销 | ⬜ 未做 | `canvas.py`（预算 3772）与 `label_widget.py`（预算 6813）都在冻结尺寸上，需要一次明确的预算决策 |
| 3b "未绑定动作"可见 | ⬜ 未做 | 需要给 22 个无键动作加 null 键位并让 F1 显示灰行 |
| 4 出口体检 + manifest | ⬜ 未做 | 未动 |
| 5 真机摸底 | ⬜ 未做 | 需要人做 |
| 6 门禁 | 🟡 部分 | black 全仓已进 CI；覆盖率与"键位覆盖"棘轮未动 |

**顺带修的**：`main` 之前是红的——上一批开了 `v1.0.0-beta.6` changelog 段却没把 `app_info.__version__` 从 beta.5 挪走，而 `read_changelog_section` 要求请求的 tag 必须是最新段，四个 release-notes 测试在任何 checkout 上都失败。现已对齐。
尺寸预算 `label_widget.py` 6777 → 6813（+18 键位是 +8 净行 + 10 个 `widget.actions` 成员 + 18 个 `addAction`），理由写进了测试注释。
**新发现（审查得到、已修）**：crop 导出的"输出目录已存在"是四处各写一份的旧模式，9/27 只加固了 YOLO 那份；`utils/export.py` 里 VOC/COCO 两份当时还是"选 No 就 rmtree"。

---

## 一、记分卡（2026-09-29 实测，非转抄）

| 面 | 判据 | 实测结果 | 结论 |
|---|---|---|---|
| 进入 | 打开文件夹即项目 | `projects.json` 注册中心可用 | ✅ |
| 操作 | 动作有键位 | `action()` 调用 **120** 个，**80 有键 / 40 无键** | ⚠️ 最大缺口 |
| 操作 | 用户能自己补键 | 设置页键位字段 **78** = yaml 键位条目数 → **无键的动作根本不在设置页里** | 🔴 补键无门 |
| 操作 | 数字快捷键 | 出厂 `{}`，首见类别自动分配 1-9 | ✅ |
| 守护 | 撤销 | `canvas.py:3691` 注释明确"undo history does not survive a file switch" | ⚠️ 不跨图 |
| 守护 | 自动保存 | 400ms 防抖 + 原子写 | ✅ |
| 守护 | 日常落盘有快照 | 备份只在智能工具批处理里触发（`smart_tools.py:1147`、`:1242`），日常编辑没有 | 🔴 无版本回退 |
| 出口 | 统计 / OBB / 覆盖三选 / 审核态 | 已具备，`test_yolo_obb_roundtrip.py` 守住 | ✅ |
| 出口 | 落 `data.yaml` | `utils/export.py:212`，`:580` 调用 | ✅ |
| 出口 | 导出前体检 | `data_audit` 是独立工具，导出对话框不调用它 | ⚠️ 两条路 |
| 可发现 | F1 ↔ yaml ↔ runtime 三层 | 78 / 78 / 78 一致，无幽灵键，`_HIDDEN_KEYS` 为空 | ✅ |
| 可发现 | `save_to` | yaml `:197` 为 `null` → `build_shortcut_rows` 跳过 → **F1 里永远看不到这一行** | ⚠️ 半截状态 |
| 可发现 | 全仓格式门禁 | `black --check` 3 个文件不合格（全在 `widgets/auto_labeling/`） | ⚠️ CI 只查改动文件会漏 |
| 手感 | 真机 5 步清单 | `measurements_2026-09-27.md` §二 列了，**尚未跑** | ⚠️ 无据可依 |

**40 个无键动作的分层（决定先补哪些）**

| 层 | 动作 | 该不该补 |
|---|---|---|
| 高频调参 | `brightness_contrast`(5748)、`keep_prev_scale/brightness/contrast`(5694/5704/5716) | **必须补** |
| 智能工具 | `smart_calibrate/analysis/missing_scan/iteration/advice/archive/template/restore_backup`(4924-5039) | **必须补**（4 个同类已有键，见 `data_audit` 4912） |
| 显示开关 | `show_groups/scores/degrees`(5766/5838/5850)、`fill_drawing`(6021) | 建议补 |
| 选择 | `select_toggle_shapes`(5629)、`shape_converter`(5602) | 建议补 |
| 一次性 | `export_*`/`upload_*` 8 项(5886-5981)、`save_crop`、`save_visualization_image`、`use_system_clipboard`、`set_cross_line`、`toggle_shape_lock`、`copy_coordinates`、`run_history` | 有意不补，但**要显式登记为"有意"** |

---

## 二、步骤

### 步骤 1 — 守住编辑史（先做，最贵）

**目标**：一次误操作在"切图之后"仍然救得回来。

1a. **自动落盘前留快照**。复用已有约定，不新造轮子：`smart_tools.py:1029` 的 `BACKUP_ROOT_NAME = ".label_backups"` + `backup_label_files()`(`:1065`) + `_prune_backup_runs()`(`:1037`)。
新增触发点：`file_lifecycle.py` 里每次 `auto_save` 真正写盘前，把**当前盘上文件**推一份到 `.label_backups/_auto_<stamp>/`，只保最近 N 次（复用 prune）。
关键约束：**快照必须在写盘之前取**，且 `_auto_*` 目录不能被 `smart_restore_backup` 的列表污染（`list_label_backups()` `:1087` 要过滤）。
1b. **撤销栈跨图**。照 `widgets/view_state.py` 的 `ViewStateStore` 模式（按 filename 索引的会话状态），把 canvas 的 shape history 提成按 filename 分桶的会话状态；切图回来时恢复 `is_shape_restorable`。
1c. 状态栏在"上一张还有可撤销的编辑"时给一次提示，别让用户以为回不去了。

- **验收**：①新测试 ≥6 条（快照内容=写盘前内容、prune 只保 N 份、`_auto_` 不出现在 restore 列表、跨图 undo 往返）；②`test_auto_save_debounce.py` 与 `test_keep_prev_proposal.py` 全绿；③真机场景：标第 3 张 → 切到第 5 张 → 回第 3 张 → `Ctrl+Z` 能退。
- **风险**：快照与防抖的先后顺序弄反会让快照存成"已改过的版本"，测试必须锚在**写盘前**。

### 步骤 2 — 把手从鼠标上解放（收益最直接）

**目标**：标注时手不离键盘。做法是**沿用已有先例，不发明新键族**。

2a. 按上表"必须补"补键：8 个智能工具 → 沿用 `Ctrl+Alt+*` 族（`data_audit=Ctrl+Alt+A`、`smart_review=R`、`smart_propagate=P`、`smart_stale_audit=S` 已占 A/R/P/S，新键要避开并跑冲突检测）；`brightness_contrast` 与 `keep_prev_*` → 用不与 `Ctrl+Z`/`D`/`A` 打架的组合。
2b. 三层同步：`jllabeling_config.yaml` 的 `shortcuts:` → `settings/runtime_applier.py` 的 `build_shortcut_action_map()`（改键免重启）→ `utils/shortcuts_help.py` 的 `SHORTCUT_GROUPS`（F1）。
2c. **更新锚点**：设置页键位字段 78 → 新值，`tests/test_settings/test_schema.py` 里同步。
2d. **新增防漂移守卫**：断言"每个 `action()` 的键位条目都能在 yaml 里找到"，把"无键"从默认状态变成**显式白名单**（`_NO_SHORTCUT_BY_DESIGN`）。这条是整份路线里性价比最高的一条测试。

- **验收**：F1 里查得到；设置页改得动且免重启生效；`SHORTCUT_DUPLICATE_WHITELIST` 不用扩（新键不与 `undo`/`undo_last_point` 撞）；锚点数字与实测一致。
- **风险**：`Ctrl+Alt+*` 可能与输入法/系统热键冲突，补完要在真机上逐个按一遍。

### 步骤 3 — 让"没有的东西"也可见（可发现）

3a. `save_to` 二选一：给默认键（进 F1 与设置页），或从 `SHORTCUT_GROUPS` 移除。**不要留"列表里挂了名、表里永远看不到"的半截状态**。
3b. F1 增加一节「未绑定动作」：灰显 + 一句"可在设置页绑定"。用户能知道"这功能存在但还没键"——现在这件事**在整个 UI 里没有任何出口**。
3c. `black --check` 三个文件格式化（`widgets/auto_labeling/` 下三件套），并把 CI/pre-commit 从"只查改动文件"改成**全仓**，否则永远漏。

- **验收**：F1 行数 = 设置页可绑键数 + 显式未绑定数（三者可互相校验）；CI 全仓 black 通过。

### 步骤 4 — 出口再收一道（导出可信度）

4a. 导出对话框挂**前置体检**：复用 `data_audit` 的判据（空标注 / 重复框 / 类别不在 `classes`），把计数写进导出摘要——现在摘要只报"转换掉了什么"，不报"源数据本身有病"。
4b. 导出目录写 **manifest**（本次筛选条件、类别映射、跳过明细、时间戳），与 `data.yaml` 并列。有了它，"这批数据是怎么导出来的"才可复现。
4c. `utils/export.py` 里 VOC/COCO 两份逐字副本：**同步加固或直接删除**。它们没有 GUI 入口（死代码），但会让后来人以为"三份都一样"。

- **验收**：新增导出摘要/manifest 测试；manifest 能被二次读取并断言。

### 步骤 5 — 真机验证（贯穿，不产出代码）

跑 `measurements_2026-09-27.md` §二 的 5 步清单，产出 `measurements_<日期>.md`：翻页流畅度、自动标注内存回落、亮度滑杆卡顿、50 框撤销、内存曲线。

**这一步排在中间而不是最后**：步骤 1/2 改的就是这几条路径的手感，没有真机数字，"手快"和"守护"都只是推理。任一项不符就把"哪一步 + 数字"记下来，反查缓存释放。

### 步骤 6 — 把上面的成果变成不会退回去的规则（门禁）

6a. 覆盖率棘轮从 44 按新测试实际上调（`pyproject.toml:235`，规则只升不降）。
6b. 新增**键位覆盖棘轮**：无键动作数只减不增。
6c. 契约测试照旧（`CONTRACT_MEMBERS` 是本轮改动的主要风险面——步骤 1b 会把 canvas 状态往 widget 上提）。
6d. 每批一条 CHANGELOG 条目 + `docs/zh_cn/` 对应章节同步。

---

## 三、优先级

| 步骤 | 收益 | 成本 | 依赖 | 建议 |
|---|---|---|---|---|
| 1 守卫：快照 + 跨图撤销 | 高（避免不可逆丢失） | 中 | 无 | **先做** |
| 2 键位补全 + 防漂移守卫 | 高（每天换算成产能） | 低 | 无 | **同步做** |
| 3 可发现（save_to / 未绑定分节 / black） | 中 | 低 | 建议在 2 之后（复用同一张表） | 紧随 2 |
| 4 出口体检 + manifest | 中 | 低 | 无 | 可穿插 |
| 5 真机验证 | —（是判据，不是收益） | 低（10 分钟） | 无 | **尽早插空** |
| 6 门禁 | 中（防退回） | 低 | 依赖 1-4 落地 | 收尾 |

**推荐执行序**：`5（摸底）→ 2（立刻见效）→ 1（补洞）→ 3 → 4 → 6`。
理由：步骤 5 只要 10 分钟却能给其余全部提供判据；步骤 2 是纯配置改动、零逻辑风险；步骤 1 需要动状态归属，最需要真机数据兜底。

---

## 四、明确不做的事

- **不再加智能工具**。`smart_*` 已有 12 个、其中 8 个连键位都没有——功能面早就过剩，继续加只会让"找得到"这件事更难。
- **不为 VOC/COCO 补 GUI 入口**（除非有外部需求）。分叉声明写的是 YOLO-only，复活它们等于自找三份副本的一致性负担。
- **不动 `keep_prev` 的语义**，只确认守护还在（`test_keep_prev_proposal.py` 6 条）。

---

## 五、验证方法（可复现）

```bash
cd /g/LabelAndTrain/LabelAndTrain

# 键位覆盖（本报告的核心数字，120 / 80 / 40 出自这里）
# 见本文件 §一 的 AST 探针：遍历 action() 调用，取第 3 位置参或 shortcut= 关键字

# 三层一致性
# yaml 78 | runtime 78 | F1 78，无幽灵键，无"改键需重启"

# 全仓格式
.venv/Scripts/python.exe -m black --check anylabeling tests scripts

# 测试规模与基线
.venv/Scripts/python.exe -m pytest --collect-only -q | tail -1   # 829
```

---

## 六、铁律（沿用审查规程）

宁可少写一条，不能写一条没验过的。本文件每一条缺口都标了 `file:line`；凡是"我 grep 不到"，先换三种形态再落笔。

---

> **恢复说明（2026-09-29 12:55）**：本文件在工作区根目录被意外删除后由会话上下文重建（原文由本会话撰写），并合并了进度表。**§一 记分卡与 §五 的命令仍是 12:10 的原样**（当时尚未补键位/未修 crop），进度见顶部表格。同时**移动位置**：现在存放在仓库内 `reviews/`（受 git 跟踪），不再放 `G:\LabelAndTrain\` 根目录。
