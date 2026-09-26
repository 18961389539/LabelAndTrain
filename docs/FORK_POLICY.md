# Fork 策略（FORK_POLICY）

> 本仓库是 CVHub520/X-AnyLabeling 的 YOLO-only 分叉（JLLabelingAndTrain）。
> 历史根提交为 rebrand 提交，**与上游无共同祖先**：`git merge upstream` 永远不可用，
> 同步上游只能"fetch + 目录级 diff + 手工搬运"。本文档定义搬运规则。

## Remote 约定

| remote | 地址 | 用途 |
|--------|------|------|
| `origin` | `git@github.com:18961389539/LabelAndTrain.git` | 唯一 push 目标 |
| `upstream` | `https://github.com/CVHub520/X-AnyLabeling.git` | 只读对照；push URL 已置为 `DISABLE_push_to_upstream` |

同步对照流程：

```bash
git fetch upstream develop          # 或上游默认分支
git diff upstream/develop -- anylabeling/views/labeling/widgets/canvas.py
```

## 目录领地划分

### 自有领地（upstream 改动不跟进，以本仓库为准）

- `anylabeling/views/labeling/filelist/` — 文件列表/审查流（自建包）
- `anylabeling/views/labeling/settings/` — schema 化设置体系（自建）
- `anylabeling/views/labeling/project*.py` — 项目注册/切换/每项目设置
- `anylabeling/views/labeling/shortcuts/` — 活绑定快捷键
- `anylabeling/views/training/` + `anylabeling/services/auto_training/` — 训练工作流
- `tests/`、`docs/FORK_POLICY.md`、`CHANGELOG.md`
- 根构建/打包配置（pyproject、packaging、scripts）

### 跟随上游（尽量保持小 diff，方便对照搬运）

- `anylabeling/views/labeling/widgets/canvas*.py` — 画布核心
- `anylabeling/views/labeling/shape.py`、`label_file.py` — 数据原语
- `anylabeling/services/auto_labeling/` — 模型 zoo（保持与上游同名文件可对照）
- `anylabeling/config.py`、`app.py` — 启动骨架

### 缓冲区（上游大改时逐案裁决）

- `anylabeling/views/labeling/label_widget.py` — 本仓库持续瘦身中；
  上游同名文件已严重漂移，搬运时只摘单个修复，不做整文件覆盖。
- `anylabeling/views/labeling/utils/`（style/theme/shape 等双轨模块）—
  合并去重完成前，该目录暂列缓冲区。

## 冲突裁决规则

1. 自有领地内：本仓库为准，上游同名改动视为"参考实现"。
2. 跟随上游目录内：以上游为准；本仓库只保留已声明的小改动
   （如 YOLO-only 裁剪、rebrand 文案），改动必须在提交信息中点名文件。
3. 需要上游某个修复时：`git diff upstream/develop -- <file>` 摘取 hunks
   手工套用，**禁止 cherry-pick**（无共同祖先会产生大量假冲突）。
4. 每次搬运上游改动，须在 CHANGELOG.md 记一行来源 commit。

## 已知漂移点（截至 2026-09）

- 全仓 rebrand（JLLabelingAndTrain / jllabelingandtrain）。
- auto-labeling 模型 zoo 已裁剪为 YOLO 系（yolo26/yolov8 族）+ SAM2。
- 负样本处理遵循 YOLO 标准（空标签文件），与上游行为不同。
- 历史根提交 `178bd94`，无上游共同祖先。
