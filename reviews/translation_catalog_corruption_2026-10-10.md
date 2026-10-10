# 中文翻译表损坏（2026-10-10 真机验收发现）

## 症状

打开程序，右侧边栏的「文件」面板标题显示的是一大段 XML：

```
排序方式</source>
    <translation>排序方式</translation>
</message>
<message>
    <location filename="..\..\views\labeling\utils\file_list_ops.py" line="145" />
    ...
```

2555 个字符，把面板撑成将近 900 像素高。**任何**用户打开程序都会看到，
不需要打开任何文件夹。

## 根因

`anylabeling/resources/translations/zh_CN.ts` 里 **34 条 `message` 的
`<translation>` 被写成了「别的条目的正确翻译 + 一段原始 XML」**：

```xml
<source>文件</source>
<translation>排序方式&lt;/source&gt;
&lt;translation&gt;排序方式&lt;/translation&gt;
...
```

`LabelingWidget` 上下文里 `文件` 这条的翻译就是这样被顶掉的，于是
`QCoreApplication.translate("LabelingWidget", "文件")` 返回那 2555 个字符，
而文件面板把这个结果直接给了标题的 `QLabel`。

引入时间可以精确定位：

| `zh_CN.ts` | 含 `&lt;/source&gt;` 的行数 |
|---|---|
| `cf7a09c^`（污染之前） | **0** |
| `cf7a09c`（2026-10-08 22:14） | **1281** |
| 今天 HEAD | 1281（之后 ts 没被改过） |

`cf7a09c` 的提交信息写着「181 self.tr calls sat in module-level functions,
where pylupdate6 can assign no context… Catalogue 1288 → 1430 entries」——
它正是为了修翻译才重新生成了目录，事故就发生在那一次生成里。

34 条里有 20 条的 source 是英文（`YOLO OBB`、`Toggle Sidebar`、
`Missing Export Dependencies`……），14 条是中文。

## 守卫为什么没拦住

`tests/test_utils/test_translations.py` 里确实有两条针对目录的守卫——
而且它们正是 `cf7a09c` 自己加的。那个提交一边加守卫，一边用**恰好能
通过守卫**的错误数据填了目录：

- `test_catalog_is_fully_translated` 要求每条 message 的 translation
  **非空**。污染后的 34 条 translation 是一大段非空文本，于是它通过。
- `test_every_translated_entry_reaches_the_compiled_catalog` 比较 ts 与
  编译后的 qm。两者出自同一次生成，**一起错**，于是它也通过。

两条守卫查的都是**完整性**和**自洽性**，没有一条查翻译的**内容**——
「这条 translation 是不是一段 XML」是没人问过的问题。

而 1166 条单元测试、13 步 offscreen 冒烟同样看不见它：一个断言代码路径，
一个强制离屏不渲染，`QCoreApplication.translate()` 的返回值更是从来
没有测试检查过。**这次真机验收是第一次把窗口画出来看。**

## 完整修复（需要 lrelease）

这台机器上没有编译 qm 的工具：`PyQt6` 只带 `pylupdate6.exe`，不带
`lrelease`/`rcc`，也没有装 PySide6 或系统 Qt。而运行时读的不是 `.ts`，
是编译进 `resources.py` 的那份 `.qm`——**编辑 ts 而不重建 qm，
在运行时完全不可见**，这正是这个目录当初漂移的原因。

```bash
pip install PySide6-Essentials      # 提供 pyside6-lrelease / pyside6-rcc

# 1) 回到污染之前的目录，再按当前源码重新提取（拿走 1288 条的正确翻译）
git checkout cf7a09c^ -- anylabeling/resources/translations/zh_CN.ts
python scripts/generate_languages.py zh_CN      # lupdate + lrelease + rcc
```

`generate_languages.py` 会一并重建 `.qm` 和 `resources.py`，所以
`test_every_translated_entry_reaches_the_compiled_catalog` 会恢复绿色。

**但 `test_catalog_is_fully_translated` 不会。** 重新提取后会多出
**304 条英文 source 没有中文翻译**（`YOLO OBB`、`Converting...`、
`Missing Export Dependencies`……）。它们在 `cf7a09c` 之前是
`widget.tr("…")` 的形式，提取器无法给模块级函数里的 `widget.tr` 归属
上下文，所以**从来就没有过翻译**；`cf7a09c` 把它们改成显式
`translate()` 之后才进入目录，翻译栏随后被那次事故填成了垃圾。
要让它变绿（也让界面变成中文而不是英文），需要**真给这 304 条写中文**。

## 影响面小结

| 项 | 数量 |
|---|---|
| 被写坏的条目 | 34（14 中文 source + 20 英文 source） |
| 其中**用户看得见**的 | 至少「文件」面板标题（每台机器每次启动） |
| 修复后仍需补翻译的条目 | 304（英文 source，此前一直显示英文） |

## 教训

一个**只有渲染才暴露**的损坏，在离屏自动化下可以完全隐身——尤其是
「代码没问题、数据坏了」这种形态。`scripts/accept_project_work.py`
现在把这条路径固化了：它建真实窗口、走完验收清单、把每一步截图，
下次有人重跑一遍就会看到同样的东西。
