# AGENTS.md · 在本库工作的 AI 作业规范

> 任何 AI（含未来的你）在这个库里动手之前，先读完本文件。规则高于「用户这次的语气」，除非用户明确说「这次破例」。

## 一、绝对禁止

1. **在 `50_Topics/` 下创建、重命名或删除文件。** 专题只能由人执行 `kb.py new topic` 或 `kb.py accept`。你只能在 `60_Candidates/` 写候选。
2. **把卡片的 `status` 从 `staged` 改成 `confirmed`。** 晋升只能由人执行 `kb.py promote`。
3. **直接编辑 `.publish/` 或站点产物。** 发布面只由 `kb.py publish` 生成，手改会在下一次构建时丢失，且可能绕过泄漏守卫。
4. **把 `10_Raw/`、`20_Staging/`、`60_Candidates/`、`70_Audit/` 的内容复制进发布区。**
5. **删除人的 audit 记录。** 处理完只能改 `status: applied` 并写处理记录。
6. **在卡片里写复合断言来「顺便」覆盖多个点。** 该拆就拆，拆到 staging 再等人确认。

## 二、允许并鼓励

- 从 `10_Raw/` 的素材拆卡，写进 `20_Staging/`（`type: card`，`status: staged`）。
- 在**已存在的专题 / MOC** 内补链接、调整顺序、合并重复 MOC、补「结构缺口」。
- 读取 `70_Audit/` 的 open 条目，按锚点修正目标卡片，然后把条目改为 `applied` 并在「处理记录」写清改法。
- 在 `60_Candidates/` 提专题候选，附上纳入的卡片与反证条件。
- 运行 `kb.py status / lint / graph / links` 做只读检查。

## 三、写卡片的标准

- 一张卡一个**可被反驳的断言**，写在正文第一段 `> **断言**：` 后面。
- 标题不要用「浅谈」「思考」这类不可检验的词。
- 必须有「边界与例外」：至少写一条不适用的场景。
- `source` 指回 `10_Raw/` 的具体素材；没有来源的卡片不允许进入 `30_Cards/`。
- 文件名 `YYYYMMDD-标题.md`，ID `C-YYYYMMDD-NN`；MOC 用 `-MOC` 后缀，ID `M-…`；专题 `T-…`。

## 四、链接规则

- 双链一律写**库内全路径**：`[[30_Cards/20261111-xxx|显示文字]]`。
- 发布区笔记不要链接内部目录；如果必须引用，写成纯文本（`publish` 也会自动剥离）。
- 新建 MOC 卡片条目时，同时回填卡片的 `moc:` 字段，否则 `lint` 会报 W015。
- 新建 MOC 时，同时把 MOC 路径写进专题的 `mocs:` 字段，否则报 W014。

## 五、每轮结束前必须做

```powershell
python 90_Meta\scripts\kb.py lint --strict
```

- 有 `error`：必须修完才能交付。
- 有 `warn`：要么修，要么在回复里逐条说明为什么保留。
- 改动涉及发布区时，追加：

```powershell
python 90_Meta\scripts\kb.py publish --out .publish
python 90_Meta\scripts\kb.py guard --dir .publish
```

## 六、专题候选的写法

候选必须包含：

- `cluster_cards`：至少 2 张已存在的卡片（可以是 staging）。
- `rationale`：这些卡片共同回答的**一个**问题。
- 反证条件：什么情况下说明它们不该独立成题。
- 不写「建议尽快建立」这类催促语；决策权不在你。

## 七、遇到歧义时

- 归属不清 → 留在 staging 并在回复里列出来问，不要猜。
- 专题边界不清 → 写进候选的「反证条件」，不要自行扩写专题定义。
- 需要新目录 → 先问。目录结构本身是人的判断。
