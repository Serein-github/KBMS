# 60_Candidates · 专题候选

AI 可以在这里提建议，**但不能创建专题**。

一个候选必须包含：至少 2 张卡片、一个共同回答的问题、一个反证条件。

```powershell
python 90_Meta\scripts\kb.py accept "60_Candidates\candidate-xxx.md"        # 接受：建专题
python 90_Meta\scripts\kb.py reject "60_Candidates\candidate-xxx.md" --reason "..."
```

30 天未决策会被 `lint` 提醒（W004）。
