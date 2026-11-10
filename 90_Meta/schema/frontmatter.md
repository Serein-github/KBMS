# Frontmatter 规范

`kb.py` 只解析一个**很小的 YAML 子集**，目的是零依赖、可预测：

- 只支持 `key: 标量`、`key: [a, b]`、`key:` 后跟 `- item` 列表；
- 不支持嵌套对象、多行字符串、锚点/别名；
- 字符串含 `:` `#` `[` `]` `,` `"` 时必须用双引号包起来（`kb.py` 生成的会自动处理）；
- 日期一律 `YYYY-MM-DD` 字符串。

## 通用字段

| 字段 | 说明 |
|---|---|
| `type` | `card` / `topic` / `moc` / `candidate` / `audit` / `source`（根 `index.md` 用 `home`） |
| `id` | 全局唯一。卡片 `C-YYYYMMDD-NN`，专题 `T-`，MOC `M-`，候选 `K-`，审阅 `A-`，素材 `S-` |
| `title` | 人类可读标题；同类型内唯一 |
| `status` | 见各类型状态机 |
| `created` / `updated` | `YYYY-MM-DD`；`kb.py` 保存时自动刷新 `updated` |

## card

| 字段 | 必填 | 说明 |
|---|---|---|
| `topics` | 确认后必填 | 指向 `50_Topics/...`，1–2 个 |
| `moc` | 否 | 指向 `40_MOC/...`，MOC 的 `cards` 必须反向登记 |
| `source` | 否（建议必填） | 指向 `10_Raw/...` 素材 |
| `confidence` | 否 | `high` / `medium` / `low`，表示断言的可信度，不是重要度 |
| `tags` | 否 | 行内列表 |

状态：`staged`（仅 `20_Staging`）→ `confirmed`（仅 `30_Cards`）→ `retired`（不发布）。

## topic

| 字段 | 必填 | 说明 |
|---|---|---|
| `mocs` | 建议 | 指向 `40_MOC/...`；每个 MOC 的 `parent_topic` 必须反向指回 |

状态：`draft` / `confirmed` / `archived`。**只能由人创建。**

## moc

| 字段 | 必填 | 说明 |
|---|---|---|
| `parent_topic` | 是 | 有且仅有一个 |
| `cards` | 建议 | 按阅读顺序排列，不是按字母序 |

状态：`active` / `archived`。

## candidate

| 字段 | 必填 | 说明 |
|---|---|---|
| `cluster_cards` | 是（≥2） | 引用触发这个候选的卡片 |
| `rationale` | 是 | 这些卡片共同回答的**一个**问题 |
| `proposed_title` | 是 | 建议的专题名 |
| `decided` | 决策后 | `accept` / `reject` 写入日期 |

状态：`proposed` → `accepted` / `rejected`。

## audit

| 字段 | 必填 | 说明 |
|---|---|---|
| `target` | 是 | 被审阅的笔记，一个 |
| `anchor` | 是 | 目标正文中**逐字存在**的片段；失效时 lint 报 W005 |
| `severity` | 是 | `blocker` / `major` / `minor` / `nit` |
| `resolved` | 处理后 | 日期 + 一句话改法 |

状态：`open` → `applied` / `rejected`。

## source

| 字段 | 必填 | 说明 |
|---|---|---|
| `sha256` | 是 | 原件哈希，用于判断素材是否被替换 |
| `asset` | 否 | 原件路径（文本类素材不复制，留空） |
| `origin` | 否 | 原始位置（URL 或本地路径） |
| `extracted` | 否 | 正文是否成功提取 |
| `source_type` | 否 | `pdf` / `html` / `md` / `video` … |

状态：`new` / `extracted` / `processed`。

## 链接写法

- 一律写库内全路径：`[[30_Cards/20261111-xxx|显示文字]]`。
- 允许省略 `.md`，`kb.py` 两种都认。
- 只写裸文件名时，若库内重名会报 E011（不唯一），因此不要偷懒。
- `publish` 会把指向内部目录的链接降级为别名文本；内部链接本身不报错，但会出现在 lint 的 I001 提示里。
