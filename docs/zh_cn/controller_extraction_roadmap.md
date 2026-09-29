# 控制器提炼路线图（基于 widget 契约面分析）

数据来源：`label_widget_contract.py` 的 132 个契约成员，逐一统计
「哪些领域模块消费」与「LabelingWidget 类内使用密度」。分析脚本口径
见 `tests/test_labeling/test_label_widget_contract.py`。

## 核心发现：73/132 的成员是领域私有的

| 消费模式 | 成员数 | 类内平均使用 | 独占度 |
|---|---|---|---|
| 仅 file_lifecycle | 48 | 2.1 | 29 个类内几乎不用 |
| 仅 label_editing | 30 | 2.0 | 21 个 |
| 仅 file_list_ops | 19 | 1.1 | 17 个 |
| 仅 file_navigation | 8 | 1.2 | 6 个 |
| 仅 panel_visibility | 1 | — | — |
| 两模块共享 | 17 | 3–7 | 多为 load_file 与翻页共享的翻页/审核态 |
| 三/四模块共享 | 10 | 10–48 | **真正的中央状态** |

**41 个成员类内零使用**——它们是搬运批次留下的薄桩或领域模块自赋值的
暂态，语义上属于领域模块而非 widget。

## 真正的中央状态（留在 widget 的理由清单）

被 3+ 模块消费且类内高密度使用（10–48 次）：

`_config`、`canvas`、`file_list_widget`、`filename`、`image_data`、
`label_file`、`label_list`、`output_dir`、`unique_label_list`、
`error_message`、`status`（另 `image`、`other_data` 等近邻）。

这就是 widget 未来的合理形态：**会话状态 + 信号装配**，约 11–15 个成员
的持有者，而不是 132 个成员的搬运站。

## 三阶段路线

### 阶段一：收缩私有面（132 → ~92，低风险，可机械化）

41 个类内零使用成员中，约 27 个同时无测试引用——删除对应薄桩、把领域
模块内的 `widget.xxx(...)` 调用改为模块本地调用即可。每删一批，
`CONTRACT_MEMBERS` 同步收缩（契约测试会强制这一步）。

剩 14 个有测试引用的零使用成员（`_apply_file_sort`、`shape_attributes`、
`update_attributes` 等）逐个评估：改测试接线或保留桩。

### 阶段二：两个控制器候选（契约面 92 → ~60）

按独占成员聚类，两个切片内聚度最高：

| 控制器 | 独占成员 | 形态 |
|---|---|---|
| **FileListController** | file_list_ops 独占 19 个 + 缩略图 3 个（`thumbnail_*`）+ 排序/删除/右键菜单状态 | 持有 `file_list_widget`/`thumbnail_*` 引用与 `_file_sort_mode`/`_syncing_file_item` 暂态 |
| **LabelDialogController**（或并入 LabelDialog 父类） | label_editing 独占 30 个中的对话框组（`label_dialog`/`label_list`/`attributes`/`shape_attributes`/`update_attributes`/`reset_attribute`…） | 标签对话框流程与其列表联动 |

### 阶段三：收敛到会话状态（~60 → ~40）

file_lifecycle（48 个独占成员）是最大的单块，但其中 `_set_file_item_*`、
`_sync_*` 一族与文件列表强耦合——阶段二的 FileListController 落地后，
这批成员自然划过去。剩余的 `filename`/`image_data`/`label_file`/
`recent_files` 等就是会话状态本体。

## 度量与纪律

- 每阶段完成后 `CONTRACT_MEMBERS` 必须收缩，契约测试强制。
- **不新增**控制器类除非某切片的独占成员 ≥ 15 且类内使用 ≤ 2——避免
  为拆而拆（类爆炸防线，见 9/28 会话结论）。
- 每批照旧：全量测试 + flake8 基线 + CHANGELOG。
