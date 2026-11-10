# 20_Staging · 待确认卡片

AI 拆卡后的第一站。**这里的内容不发布。**

审阅只做二值判断（读标题 + 断言，30 秒）：

```powershell
# 值得存在
python 90_Meta\scripts\kb.py promote "20_Staging\xxx.md" --topic "50_Topics\xxx"
# 不值得
Remove-Item "20_Staging\xxx.md"
```

停留超过 7 天会被 `lint` 提醒（W002）。
