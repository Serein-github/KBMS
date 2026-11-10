---
type: candidate
id: "{{id}}"
title: "{{title}}"
status: proposed
created: {{date}}
updated: {{date}}
proposed_title: "{{title}}"
cluster_cards: []
rationale: ""
decided: ""
---
# 专题候选：{{title}}

> 这是 AI 的**建议**，不是专题。只有人执行 `kb.py accept` 之后，专题才会出现在 50_Topics/。

## 建议的专题名

{{title}}

## 纳入的卡片

- <!-- [[30_Cards/xxx]] —— 一句话说明它为什么属于这个专题 -->

## 为什么这些卡片值得独立成题

- 它们共同回答的问题：
- 与现有专题的重叠/区别：
- 不成立时会怎样（说明反证条件）：

## 决策

- [ ] 接受 → `python 90_Meta/scripts/kb.py accept "<本文件>"`
- [ ] 拒绝 → `python 90_Meta/scripts/kb.py reject "<本文件>" --reason "……"`
