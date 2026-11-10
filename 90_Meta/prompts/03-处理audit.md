你在 D:\KBMS 工作。先读 `AGENTS.md` 与 `90_Meta/schema/frontmatter.md`。

任务：处理 `70_Audit/` 中 `status: open` 的审阅意见。

对每一条：

1. 读取 `target` 指向的笔记，确认 `anchor` 原文仍在（不在就停下，在回复里说明「锚点失效」）。
2. 按「期望的修改」调整目标笔记；只改被指出的问题，不顺手重写整篇。
3. 把 audit 的 `status` 改为 `applied`，`resolved` 写 `YYYY-MM-DD 一句话改法`。
4. 如果这条意见无法执行（前提不成立、需要人决策），改为 `rejected` 并在「处理记录」写清原因——**不允许静默忽略**。

边界：

- 涉及「这张卡该属于哪个专题 / 是否该新建专题」的意见，不要自行执行，改为在回复里列出来。
- `blocker` 级意见修完后，检查引用了该卡片的所有 MOC 是否需要同步措辞。

完成后：

- 运行 `python 90_Meta\scripts\kb.py lint --strict`；
- 汇报：处理了哪些 A- 编号、各自改了什么、哪些转成了 rejected 及原因。
