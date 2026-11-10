# 架构：把「判断权」写进结构

## 一句话

AI 负责**填充与维护**，人负责**结构判断**。这条边界不是靠提示词自觉，而是靠目录、状态机、lint 和发布守卫四层机制强制。

## 一、三层知识结构

```
10_Raw（素材） → 20_Staging（草稿） → 30_Cards（原子卡片）
                                          ↓
                                      40_MOC（主题地图）
                                          ↓
                                      50_Topics（专题）
```

为什么 MOC 必须在中间：

- 专题页只回答「这个专题是什么、边界在哪」，保持稳定；
- MOC 回答「这条线索怎么读」，可以频繁调整；
- 卡片回答「一个断言」，最小可引用单位。

没有 MOC 时，卡片直接挂专题，专题页会随卡片数线性膨胀，且交叉关系无处表达。这就是把 MOC 作为**默认层**、而不是可选层的原因。

## 二、判权表

| 动作 | 谁 | 机制 |
|---|---|---|
| 决定某素材值不值得拆卡 | AI 提议，人默认接受 | 素材进 `10_Raw` 后由 AI 拆 |
| 决定一张卡是否存在 | **人** | `promote` 命令；staged 不能出现在 `30_Cards` |
| 决定专题是否成立 | **人** | 只有 `new topic` / `accept` 能写 `50_Topics` |
| 决定卡片归属哪个专题 | **人** | `promote --topic`；AI 只能提候选 |
| 决定专题内 MOC 如何划分 | 人定骨架，AI 填充 | AI 可新建 MOC，但必须在已存在专题下 |
| 重命名后修复入链 | 工具 | `lint` 报死链；`move` 时手工改或后续脚本 |
| 死链 / 孤儿 / 重复检测 | 工具 | `lint` |
| 按锚点修正文案 | AI | 处理 `70_Audit`，改完置 `applied` |
| 决定发布什么 | 工具（白名单），人定义白名单 | `publish` + `guard` |

**核心不变量**：AI 的任何输出都必须落在「已存在的结构」里；唯一例外是 `20_Staging` 和 `60_Candidates` 这两个**缓冲区**。

## 三、状态机

```
card:      staged ──promote──▶ confirmed ──▶ retired
             │                     ▲
             └──丢弃（删除）        └── audit 修正后仍是 confirmed

topic:     draft ──▶ confirmed ──▶ archived

moc:       active ──▶ archived

candidate: proposed ──accept──▶ accepted（同时创建 topic）
                    └─reject──▶ rejected

audit:     open ──▶ applied
              └───▶ rejected（无法处理，写明原因）
```

状态即权限：`staged` 不能发布，`proposed` 不能出现在专题区，`open` 的 audit 必须出现在看板待办里。

## 四、四层强制机制

1. **目录**：工作面与知识面物理分离。`publish` 只读 `30/40/50`。
2. **状态字段**：`publish` 只收 `confirmed` 卡片、`confirmed` 专题、`active` MOC。
3. **lint**：必填字段、枚举、双向一致性（card↔moc、moc↔topic）、死链、孤儿、过期 staging/audit/候选、未拆卡的素材。
4. **guard**：构建产物里出现任何内部目录名、内部 ID（K-/A-/S-）、内部字段（severity/target/rationale）即失败。

任何一层单独都可能被绕过；四层同时成立时，「AI 越权」和「内部内容泄露」都会在 CI 里变成红色失败，而不是靠事后发现。

## 五、发布链路

```
Obsidian 库（本仓库）
   │  kb.py publish        # 白名单 → .publish/
   │  kb.py guard          # 泄漏检查
   ▼
Quartz（site/ 配置）──build──▶ public/ ──GitHub Actions──▶ Pages
```

- `.publish/` 是**构建中间物**，不进版本库。
- 站点配置放在 `site/`，与库内容分离；Quartz 框架在 CI 里临时 clone，不把几万行框架代码塞进知识库仓库。
- 本地预览用 `90_Meta/scripts/preview.ps1`，它会先 publish 再构建。

## 六、可选外部工具怎么接

本库不依赖任何特定插件也能跑。下列工具是**增强**，不是前提：

| 需求 | 可选工具 | 接入点 |
|---|---|---|
| 语义唤醒旧卡 | Smart Connections | Obsidian 插件，只读，不影响结构 |
| 论文/网页解析 | OpenDataLoader PDF、阅读器导出 | 产出物放 `00_Inbox/`，再 `kb.py ingest` |
| 自动生成卡片 | 任意 LLM | 输出必须落 `20_Staging/`，遵守 `AGENTS.md` |
| 自动同步 | Obsidian Git | 只 commit，不改变目录约定 |
| 更细的双链运维 | 任意 MCP / 脚本 | 只能改链接，不能建专题 |

原则：**工具可以读全库、写缓冲区、维护已有结构；不能写 `50_Topics/`，不能改 `confirmed`。**

## 七、已知的取舍

- **MOC 是人工成本**：专题卡片少于 10 张时，MOC 是负收益。本库用 lint 的 I002 提示，但不强制。
- **白名单会漂移**：新增目录后必须同步 `kb.py` 的 `PUBLISHED_DIRS` 与 `site/quartz.config.ts`。`guard` 只能发现「产物里有内部内容」，发现不了「本该发布却没发布」。
- **YAML 子集**：为免依赖，`kb.py` 只解析简单 frontmatter（标量、行内列表、短横线列表）。不要写嵌套对象。
- **无数据库**：所有状态都在文件里，靠 lint 保持一致性；文件数到几万时 `lint` 会变慢，届时再考虑缓存。
