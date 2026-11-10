# 70_Audit · 审阅意见

一条反馈 = 一条锚定到原文的独立笔记。**不发布。**

```powershell
python 90_Meta\scripts\kb.py new audit "审阅：xxx" --target "30_Cards\xxx" `
  --anchor "原文里逐字存在的一句" --severity major --note "哪里不对、期望改成什么"
```

`severity`：`blocker` / `major` / `minor` / `nit`。

AI 处理后把 `status` 改为 `applied`，在「处理记录」写清改法；无法处理则 `rejected` 并写原因。锚点失效会触发 W005。
