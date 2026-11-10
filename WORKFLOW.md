# 工作流：五个环节的操作手册

> 每一节都写清「你做哪一步、AI 做哪一步、命令是什么」。所有命令在库根目录执行。

## 0. 首次发布（只做一次）

本地已初始化 git 并有首次提交。你只需要做三件事：

1. **建仓库并推送**

```powershell
cd D:\KBMS
# 在 GitHub 新建空仓库（不要勾选 README），然后：
git remote add origin https://github.com/<你的账号>/<仓库名>.git
git branch -M main
git push -u origin main
```

2. **开 Pages**：仓库 Settings → Pages → Build and deployment → Source 选 **GitHub Actions**。

3. **确认 Actions 权限**：Settings → Actions → General → Workflow permissions 选 **Read and write permissions**（部署 Pages 需要）。

推送后 `.github/workflows/deploy.yml` 会自动跑：lint → publish → guard → Quartz 构建 → 部署。首次构建约 3–5 分钟，站点地址在 Actions 的 deploy 步骤里。

> 如果只想本地看效果：`powershell -File 90_Meta\scripts\preview.ps1`，它会 publish 后启动本地 Quartz 预览（需要 Node 20+ 与网络）。

## 1. 读取：素材入库

**你**：把 PDF / 网页 / 视频字幕 / 仓库导出丢进 `00_Inbox/`，或直接对文件跑 ingest。

```powershell
python 90_Meta\scripts\kb.py ingest "00_Inbox\某篇文章.pdf"
```

生成 `10_Raw/YYYYMMDD-标题.md`：带 `sha256`、原始文件引用、提取正文。PDF 的坐标信息建议在「边界框/页码信息」里补一行来源说明，方便审阅时回溯。

**AI**：读 `10_Raw/` 的素材，拆成 3–8 张卡片写入 `20_Staging/`。拆分标准见 `AGENTS.md` 第三节。

> 大文件（>20MB）或版权敏感素材：只登记元数据，正文摘要另存，不要整本进库。

## 2. 整理：卡片进入 staging

**AI** 产出：

```powershell
python 90_Meta\scripts\kb.py new card "标题" --topic "50_Topics/xxx" --source "10_Raw/xxx"
```

或直接按模板写文件（模板在 `90_Meta/templates/`）。要求：

- 一句可反驳的断言；
- 「边界与例外」至少一条；
- `source` 指回具体素材；
- `status: staged`，**不允许**自己改成 confirmed。

**你**：只做二值判断。打开 staging 卡片，读标题 + 断言，30 秒内决定：

```powershell
# 值得存在
python 90_Meta\scripts\kb.py promote "20_Staging/xxx.md" --topic "50_Topics/xxx"

# 不值得：直接删除文件
```

判断标准不必完美，但必须写下来一次（贴在你的工作笔记里），否则每次都在重新发明标准。

## 3. 结构：专题与 MOC

### 3.1 专题只能由你创建

```powershell
python 90_Meta\scripts\kb.py new topic "专题名"
```

AI 的专题相关产出只有一种：`60_Candidates/` 里的候选。你每周花 10 分钟做决策：

```powershell
python 90_Meta\scripts\kb.py accept "60_Candidates/candidate-xxx.md"   # 接受 → 建专题
python 90_Meta\scripts\kb.py reject "60_Candidates/candidate-xxx.md" --reason "理由"
```

拒绝的理由要写，它是下一次候选质量提升的唯一输入。

### 3.2 专题内部用 MOC 组织

```powershell
python 90_Meta\scripts\kb.py new moc "子主题" --topic "50_Topics/xxx"
```

然后把卡片挂进 MOC 的 `cards:`，并回填卡片的 `moc:`。两边都写，`lint` 会检查一致性。

**AI 可以在已有专题下新建 MOC**——这是「在划定结构内填充」，不是越权。但 MOC 的划分方式（按问题还是按来源）属于结构判断，AI 拿不准时应先提在候选里。

## 4. 阅读：留下锚定反馈

**你**在 Obsidian 里读到问题时：

```powershell
python 90_Meta\scripts\kb.py new audit "审阅：卡片标题" --target "30_Cards/xxx" `
  --anchor "原文中的一句话" --severity major --note "哪里不对、期望改成什么"
```

或在 `70_Audit/` 手动建文件。要求：

- `anchor` 必须是目标笔记里**逐字存在**的片段（`lint` 会检查锚点是否还在）；
- `severity`：blocker（断言错误，必须改）/ major（论证有漏洞）/ minor（表述）/ nit（错别字）。

**AI**：读 open 的 audit，按锚点修正目标，改完把 `status` 设为 `applied`，`resolved` 填日期与改法。处理不了的设 `rejected` 并写原因——不允许静默忽略。

## 5. 发布：白名单 + 守卫

```powershell
python 90_Meta\scripts\kb.py publish --out .publish
python 90_Meta\scripts\kb.py guard --dir .publish
```

`publish` 做四件事：

1. 只收 `confirmed` 卡片、`confirmed` 专题、`active` MOC、根 `index.md`；
2. 剥掉内部字段（`status`、`topics`、`source`、`target`、`severity`…）；
3. 把指向内部目录的链接降级为纯文本；
4. 删掉 HTML 注释（草稿备注）。

`guard` 检查：非白名单目录、内部目录名、内部 ID 前缀、内部字段。任何一项命中，CI 失败。

**不要手改 `.publish/`**。它是生成物，改动会在下一次构建时消失。

## 6. 每周维护（15 分钟）

```powershell
python 90_Meta\scripts\kb.py status    # 看板
python 90_Meta\scripts\kb.py lint      # 结构健康度
```

按看板提示处理四类积压：

| 积压 | 处理 |
|---|---|
| staging 卡片 > 7 天 | 晋升或删除，不允许悬空 |
| open audit > 14 天 | 让 AI 处理，或自己改 |
| 候选 > 30 天 | 接受 / 拒绝，二选一 |
| 素材未拆卡 | 安排拆卡，或标记为仅存档 |

`graph` 可以看「被引用最多」和「零入链」：

```powershell
python 90_Meta\scripts\kb.py graph
```

零入链的卡片不一定是孤儿——可能是新卡还没挂 MOC。连续两周零入链，基本可以判定它没有进入任何阅读路径。

## 7. 给 AI 的开场提示词

把下面这段贴在会话开头（或让 AI 先读 `AGENTS.md`）：

```
你在 D:\KBMS 这个知识库里工作。先读 AGENTS.md 和 ARCHITECTURE.md。
本轮任务：<从 10_Raw/<素材> 拆卡到 20_Staging/，或 处理 70_Audit/ 中 open 的意见>
约束：
- 不创建/修改 50_Topics/ 下的任何文件
- 不把卡片状态改成 confirmed
- 每张卡一个可反驳的断言，带边界与例外，source 指回素材
- 结束前运行 python 90_Meta\scripts\kb.py lint --strict，并汇报 warn 的处理
```

## 8. 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `lint` 报 E010 死链 | 改名或链接写错 | 按提示路径改链接；中文名注意全角空格 |
| 发布站出现内部内容 | 有人绕过 publish 手改 | 删 `.publish/` 重建，查 `guard` 输出定位来源 |
| CI 失败在 guard | 新目录未加入白名单，或卡片链了 audit | 看 guard 输出的文件名，改源文件而非产物 |
| Obsidian 里双链变红 | 文件名改了但入链没改 | `kb.py links "<笔记>"` 找入链后修 |
| `promote` 报专题不存在 | 专题名写错或还没建 | 先 `new topic`，或检查路径是否带 `.md` |
