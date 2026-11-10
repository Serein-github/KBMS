#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KBMS 知识库治理工具（仅用标准库）。

设计契约：
  - AI 只负责「在既有结构内填充」：拆卡、写卡片、维护专题内双链、执行 audit 修正。
  - 本工具不提供「自动建专题」的入口；专题只能由 `new topic` / `accept` 这类
    显式人工命令创建，candidates 目录只是建议区。

常用命令：
  python 90_Meta/scripts/kb.py status
  python 90_Meta/scripts/kb.py lint [--strict] [--json]
  python 90_Meta/scripts/kb.py publish --out .publish --clean
  python 90_Meta/scripts/kb.py guard --dir .publish
  python 90_Meta/scripts/kb.py new card "标题" --topic 50_Topics/xxx
  python 90_Meta/scripts/kb.py promote "20_Staging/xxx.md" --topic 50_Topics/xxx
  python 90_Meta/scripts/kb.py accept "60_Candidates/xxx.md"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_ROOT = Path(__file__).resolve().parents[2]
ROOT = Path(os.environ.get("KBMS_ROOT", DEFAULT_ROOT)).resolve()

INBOX = "00_Inbox"
RAW = "10_Raw"
STAGING = "20_Staging"
CARDS = "30_Cards"
MOC = "40_MOC"
TOPICS = "50_Topics"
CANDIDATES = "60_Candidates"
AUDIT = "70_Audit"
META = "90_Meta"

PUBLISHED_DIRS = (CARDS, MOC, TOPICS)
INTERNAL_DIRS = (INBOX, RAW, STAGING, CANDIDATES, AUDIT, META)

# 不参与建索引/链接图的目录
EXCLUDE_PARTS = {
    ".git", ".github", ".obsidian", ".publish", ".quartz", "public",
    "node_modules", "site", "templates", "state",
}

TYPE_STATUS = {
    "card": {"staged", "confirmed", "retired"},
    "topic": {"draft", "confirmed", "archived"},
    "moc": {"active", "archived"},
    "candidate": {"proposed", "accepted", "rejected"},
    "audit": {"open", "applied", "rejected"},
    "source": {"new", "extracted", "processed"},
    "home": {"active"},
}

REQUIRED = {
    "card": ["type", "id", "title", "status", "created", "updated"],
    "topic": ["type", "id", "title", "status", "created", "updated"],
    "moc": ["type", "id", "title", "status", "parent_topic", "created", "updated"],
    "candidate": ["type", "id", "title", "status", "created", "cluster_cards", "rationale"],
    "audit": ["type", "id", "target", "severity", "status", "created"],
    "source": ["type", "id", "title", "created", "sha256"],
}

ID_PREFIX = {"card": "C", "topic": "T", "moc": "M", "candidate": "K", "audit": "A", "source": "S"}

SEVERITY = {"blocker", "major", "minor", "nit"}

# 发布白名单字段：只保留站点需要的最小集合
PUBLISH_FM_KEYS = ("type", "title", "aliases", "tags", "created", "updated")

LINK_RE = re.compile(r"(!?)\[\[([^\[\]\n]+?)\]\]")
FM_KEY_RE = re.compile(r"^([A-Za-z0-9_\-\u4e00-\u9fff]+):\s*(.*)$")
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# --------------------------------------------------------------------------- #
# 基础工具
# --------------------------------------------------------------------------- #
class KBError(Exception):
    pass


def today() -> str:
    return date.today().isoformat()


def compact(d: str | None = None) -> str:
    return (d or today()).replace("-", "")


def relpath(p: Path) -> str:
    return p.resolve().relative_to(ROOT).as_posix()


def safe_name(title: str, limit: int = 48) -> str:
    s = re.sub(r'[\\/:*?"<>|\r\n\t]', "-", title).strip().strip(".")
    s = re.sub(r"\s+", " ", s)
    s = s[:limit].strip()
    return s or "untitled"


def norm(target: str) -> str:
    """去掉可能存在的 .md 后缀，统一成库内路径写法。"""
    t = str(target).strip()
    return t[:-3] if t.lower().endswith(".md") else t


def strip_code(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", "", text)
    return text


def parse_scalar(raw: str) -> Any:
    s = raw.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if not inner:
            return []
        return [unquote(x.strip()) for x in split_commas(inner)]
    return unquote(s)


def split_commas(s: str) -> list[str]:
    out, buf, quote = [], [], ""
    for ch in s:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch == ",":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        out.append("".join(buf))
    return out


def unquote(s: str) -> Any:
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        body = s[1:-1]
        if s[0] == '"':
            try:
                return json.loads(s)
            except Exception:
                return body
        return body.replace("''", "'")
    if s == "true":
        return True
    if s == "false":
        return False
    return s


def dump_scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(dump_scalar(x) for x in v) + "]"
    s = str(v)
    if s == "":
        return '""'
    if s != s.strip() or any(c in s for c in ':#[]{}",\n') or s.lower() in ("true", "false", "null"):
        return json.dumps(s, ensure_ascii=False)
    return s


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """解析本库使用的 YAML 子集；没有 frontmatter 返回 ({}, text)。"""
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            end = i
            break
    if end is None:
        raise KBError("frontmatter 未闭合（缺少结束的 ---）")

    data: dict[str, Any] = {}
    key: str | None = None
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        stripped = line.lstrip()
        if stripped.startswith("- ") and key is not None:
            if not isinstance(data.get(key), list):
                data[key] = []
            data[key].append(parse_scalar(stripped[2:]))
            continue
        m = FM_KEY_RE.match(line)
        if not m:
            raise KBError(f"无法解析 frontmatter 行：{line!r}")
        key, value = m.group(1), m.group(2)
        data[key] = parse_scalar(value) if value.strip() else []
    body = "\n".join(lines[end + 1:])
    return data, body


def dump_frontmatter(fm: dict[str, Any]) -> str:
    out = ["---"]
    for k, v in fm.items():
        out.append(f"{k}: {dump_scalar(v)}")
    out.append("---")
    return "\n".join(out)


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


# --------------------------------------------------------------------------- #
# 笔记模型与链接索引
# --------------------------------------------------------------------------- #
@dataclass
class Note:
    path: Path
    rel: str
    fm: dict[str, Any] = field(default_factory=dict)
    body: str = ""
    text: str = ""

    @property
    def type(self) -> str:
        t = self.fm.get("type")
        return t if isinstance(t, str) else ""

    @property
    def title(self) -> str:
        t = self.fm.get("title")
        return t if isinstance(t, str) and t else self.path.stem

    @property
    def status(self) -> str:
        s = self.fm.get("status")
        return s if isinstance(s, str) else ""

    @property
    def dir(self) -> str:
        return self.rel.rsplit("/", 1)[0] if "/" in self.rel else ""


def load_note(path: Path) -> Note:
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        fm, body = parse_frontmatter(text)
    except KBError:
        fm, body = {}, text
    return Note(path=path, rel=relpath(path), fm=fm, body=body, text=text)


def iter_markdown() -> Iterable[Path]:
    """只遍历受管内容：根 index.md 与八个内容目录。文档、站点、脚本不参与。"""
    managed = {INBOX, RAW, STAGING, CARDS, MOC, TOPICS, CANDIDATES, AUDIT}
    for p in ROOT.rglob("*.md"):
        if p.name == "README.md":
            continue
        rel = p.relative_to(ROOT)
        if rel.as_posix() == "index.md":
            yield p
            continue
        if rel.parts and rel.parts[0] in managed:
            yield p


def load_notes() -> list[Note]:
    notes = []
    for p in iter_markdown():
        try:
            notes.append(load_note(p))
        except Exception:
            continue
    return notes


class Index:
    def __init__(self, notes: list[Note]):
        self.notes = notes
        self.by_rel: dict[str, Note] = {}
        self.by_stem: dict[str, list[Note]] = defaultdict(list)
        for n in notes:
            key = n.rel[:-3].lower() if n.rel.lower().endswith(".md") else n.rel.lower()
            self.by_rel[key] = n
            self.by_stem[n.path.stem.lower()].append(n)

    def resolve(self, target: str) -> tuple[Note | None, str]:
        """返回 (note, 解析状态)；状态 ok / missing / ambiguous。"""
        t = target.strip().replace("\\", "/")
        if t.startswith("./"):
            t = t[2:]
        t = t[:-3] if t.lower().endswith(".md") else t
        key = t.lower()
        if key in self.by_rel:
            return self.by_rel[key], "ok"
        if "/" not in t:
            hits = self.by_stem.get(key, [])
            if len(hits) == 1:
                return hits[0], "ok"
            if len(hits) > 1:
                return None, "ambiguous"
        return None, "missing"


def links_in(text: str) -> list[tuple[bool, str, str]]:
    """[(是否嵌入, 目标, 原始 inner)]"""
    out = []
    for m in LINK_RE.finditer(strip_code(text)):
        inner = m.group(2)
        target = inner.split("|")[0].split("#")[0].strip()
        if target:
            out.append((m.group(1) == "!", target, inner))
    return out


# --------------------------------------------------------------------------- #
# 校验 / lint
# --------------------------------------------------------------------------- #
@dataclass
class Issue:
    level: str      # error / warn / info
    code: str
    rel: str
    message: str

    def fmt(self) -> str:
        tag = {"error": "错误", "warn": "警告", "info": "提示"}[self.level]
        return f"[{tag}] {self.code}  {self.rel}  {self.message}"


def as_list(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x) for x in v]
    if v is None or v == "":
        return []
    return [str(v)]


def check_note(note: Note, idx: Index, issues: list[Issue]) -> None:
    t = note.type
    rel = note.rel
    if t not in REQUIRED:
        # 根目录 index.md 允许 type: home；其余必须声明类型
        if rel == "index.md" and t == "home":
            pass
        else:
            issues.append(Issue("error", "E001", rel, "缺少 type 字段或类型不在 card/topic/moc/candidate/audit/source 之内"))
            return

    for key in REQUIRED.get(t, []):
        if key not in note.fm:
            issues.append(Issue("error", "E002", rel, f"缺少必填字段 `{key}`"))
        elif note.fm[key] in ("", [], None):
            issues.append(Issue("error", "E002", rel, f"字段 `{key}` 为空"))

    if t in TYPE_STATUS:
        st = note.status
        if st and st not in TYPE_STATUS[t]:
            issues.append(Issue("error", "E003", rel, f"status=`{st}` 不合法（允许：{', '.join(sorted(TYPE_STATUS[t]))}）"))

    for key in ("created", "updated"):
        v = note.fm.get(key)
        if v and (not isinstance(v, str) or not DATE_RE.match(v)):
            issues.append(Issue("error", "E004", rel, f"`{key}` 必须是 YYYY-MM-DD"))

    # 文件位置与类型一致性
    expect_dir = {
        "card": {CARDS, STAGING},
        "topic": {TOPICS},
        "moc": {MOC},
        "candidate": {CANDIDATES},
        "audit": {AUDIT},
        "source": {RAW},
    }.get(t)
    if expect_dir and note.dir not in expect_dir:
        issues.append(Issue("error", "E005", rel, f"{t} 类型只能放在 {' 或 '.join(sorted(expect_dir))}"))

    if t == "card":
        if note.dir == STAGING and note.status == "confirmed":
            issues.append(Issue("warn", "W010", rel, "staging 中的卡片已标记 confirmed，应 promote 到 30_Cards"))
        if note.dir == CARDS and note.status == "staged":
            issues.append(Issue("error", "E006", rel, "30_Cards 中出现 staged 卡片，未确认内容不能进入正式卡片区"))
        if note.dir == CARDS and not as_list(note.fm.get("topics")):
            issues.append(Issue("error", "E007", rel, "正式卡片必须声明 topics"))
        if not note.path.stem[:8].isdigit():
            issues.append(Issue("warn", "W011", rel, "卡片文件名应以 YYYYMMDD- 开头"))
        if note.status == "confirmed":
            for m in re.finditer(r"\b(" + ID_PREFIX["card"] + r"-\d{8}-\d{2})\b", note.text):
                if m.group(1) != str(note.fm.get("id")):
                    pass

    if t == "audit":
        sev = note.fm.get("severity")
        if sev not in SEVERITY:
            issues.append(Issue("error", "E008", rel, f"severity=`{sev}` 不合法（blocker/major/minor/nit）"))
        tgt = as_list(note.fm.get("target"))
        if not tgt:
            issues.append(Issue("error", "E009", rel, "audit 缺少 target"))
        if note.status == "open" and tgt:
            anchor = str(note.fm.get("anchor", "")).strip()
            hit, _ = idx.resolve(tgt[0])
            if anchor and hit and anchor not in hit.text:
                issues.append(Issue("warn", "W005", rel, "锚点在目标笔记中已不存在，需要重新定位后再处理"))

    if t == "candidate":
        if len(as_list(note.fm.get("cluster_cards"))) < 2:
            issues.append(Issue("warn", "W012", rel, "专题候选至少应引用 2 张卡片，否则不足以支撑一个专题"))

    if t == "topic" and note.status == "confirmed" and not as_list(note.fm.get("mocs")):
        issues.append(Issue("warn", "W016", rel, "专题还没有挂 MOC，内部结构尚未搭起来"))
    if t == "moc" and not as_list(note.fm.get("cards")):
        issues.append(Issue("warn", "W017", rel, "MOC 还没有登记卡片"))

    # 链接
    for embed, target, inner in links_in(note.text):
        hit, state = idx.resolve(target)
        if state == "missing":
            if target.startswith((".", "http")):
                continue
            issues.append(Issue("error", "E010", rel, f"死链 [[{inner}]]"))
        elif state == "ambiguous":
            issues.append(Issue("error", "E011", rel, f"链接目标不唯一 [[{inner}]]，请写全路径"))

    if t in ("card", "moc", "topic"):
        for embed, target, inner in links_in(note.body):
            hit, state = idx.resolve(target)
            if hit and hit.dir in INTERNAL_DIRS and (hit.dir != RAW or t != "card"):
                issues.append(Issue("info", "I001", rel, f"正文引用了内部笔记 [[{inner}]]，发布时会被剥离为纯文本"))


def lint() -> list[Issue]:
    notes = load_notes()
    idx = Index(notes)
    issues: list[Issue] = []

    for n in notes:
        check_note(n, idx, issues)

    # 全局唯一性：id 全局唯一；title 仅在同类笔记内唯一
    seen_ids: dict[str, list[str]] = defaultdict(list)
    for n in notes:
        v = str(n.fm.get("id", "")).strip().lower()
        if v:
            seen_ids[v].append(n.rel)
    for v, rels in seen_ids.items():
        if len(rels) > 1:
            for r in rels:
                issues.append(Issue("error", "E012", r, f"id 重复：`{v}` 同时出现在 {', '.join(rels)}"))

    for t in ("card", "topic", "moc", "candidate", "audit", "source"):
        seen_titles: dict[str, list[str]] = defaultdict(list)
        for n in notes:
            if n.type == t:
                v = str(n.fm.get("title", "")).strip().lower()
                if v:
                    seen_titles[v].append(n.rel)
        for v, rels in seen_titles.items():
            if len(rels) > 1:
                for r in rels:
                    issues.append(Issue("error", "E012", r, f"同类标题重复（{t}）：`{v}` 同时出现在 {', '.join(rels)}"))

    by_rel = {n.rel: n for n in notes}

    # 双向一致性：card.topics / topic.mocs / moc.parent_topic / moc.cards
    for n in notes:
        if n.type == "card":
            for tgt in as_list(n.fm.get("topics")):
                hit, _ = idx.resolve(tgt)
                if hit is None:
                    issues.append(Issue("error", "E013", n.rel, f"topics 指向不存在的笔记：{tgt}"))
                elif hit.type != "topic":
                    issues.append(Issue("error", "E013", n.rel, f"topics 只能指向 topic，实际是 {hit.type}：{tgt}"))
            for tgt in as_list(n.fm.get("moc")):
                hit, _ = idx.resolve(tgt)
                if hit is None:
                    issues.append(Issue("error", "E013", n.rel, f"moc 指向不存在的笔记：{tgt}"))
                elif hit.type != "moc":
                    issues.append(Issue("error", "E013", n.rel, f"moc 只能指向 moc：{tgt}"))
                else:
                    back = [idx.resolve(c)[0] for c in as_list(hit.fm.get("cards"))]
                    if not any(b and b.rel == n.rel for b in back):
                        issues.append(Issue("warn", "W013", n.rel, f"MOC 未登记本卡片：{hit.rel}"))

        if n.type == "moc":
            parent = as_list(n.fm.get("parent_topic"))
            if len(parent) != 1:
                issues.append(Issue("error", "E014", n.rel, "MOC 必须且只能有一个 parent_topic"))
            else:
                hit, _ = idx.resolve(parent[0])
                if hit is None:
                    issues.append(Issue("error", "E014", n.rel, f"parent_topic 不存在：{parent[0]}"))
                elif hit.type != "topic":
                    issues.append(Issue("error", "E014", n.rel, "parent_topic 必须指向 topic"))
                elif norm(n.rel) not in [norm(h) for h in as_list(hit.fm.get("mocs"))]:
                    issues.append(Issue("warn", "W014", n.rel, f"上级专题未登记本 MOC：{hit.rel}"))
            for c in as_list(n.fm.get("cards")):
                hit, _ = idx.resolve(c)
                if hit is None:
                    issues.append(Issue("error", "E015", n.rel, f"cards 指向不存在的卡片：{c}"))
                elif hit.type != "card":
                    issues.append(Issue("error", "E015", n.rel, f"cards 只能指向 card：{c}"))
                else:
                    declared = [norm(h).lower() for h in as_list(hit.fm.get("moc"))]
                    if norm(n.rel).lower() not in declared:
                        issues.append(Issue("warn", "W015", n.rel, f"卡片未回填 moc 字段：{c}"))

        if n.type == "topic":
            for m in as_list(n.fm.get("mocs")):
                hit, _ = idx.resolve(m)
                if hit is None:
                    issues.append(Issue("error", "E016", n.rel, f"mocs 指向不存在的笔记：{m}"))
                elif hit.type != "moc":
                    issues.append(Issue("error", "E016", n.rel, f"mocs 只能指向 moc：{m}"))

    # 孤儿：发布区内既无入链也无出链
    inbound: Counter[str] = Counter()
    outbound: dict[str, set[str]] = defaultdict(set)
    for n in notes:
        for _, target, _ in links_in(n.text):
            hit, state = idx.resolve(target)
            if hit and state == "ok":
                inbound[hit.rel] += 1
                outbound[n.rel].add(hit.rel)
    for n in notes:
        if n.dir in PUBLISHED_DIRS and not inbound.get(n.rel) and not outbound.get(n.rel):
            issues.append(Issue("warn", "W001", n.rel, "孤儿笔记：没有任何入链或出链"))

    # 专题内容量
    for n in notes:
        if n.type == "topic":
            mocs = [idx.resolve(m)[0] for m in as_list(n.fm.get("mocs"))]
            cards = set()
            for m in mocs:
                if m:
                    for c in as_list(m.fm.get("cards")):
                        hit = idx.resolve(c)[0]
                        if hit:
                            cards.add(hit.rel)
            if n.status == "confirmed" and len(cards) < 3:
                issues.append(Issue("info", "I002", n.rel, f"专题当前只聚合了 {len(cards)} 张卡片（<3），可考虑先养在 candidates/"))

    # 时效性
    now = date.today()
    for n in notes:
        try:
            created = datetime.strptime(str(n.fm.get("created", "")), "%Y-%m-%d").date()
        except Exception:
            continue
        if n.type == "card" and n.dir == STAGING and (now - created).days > 7:
            issues.append(Issue("warn", "W002", n.rel, f"staging 卡片已停留 {(now - created).days} 天，尽快确认或丢弃"))
        if n.type == "audit" and n.status == "open" and (now - created).days > 14:
            issues.append(Issue("warn", "W003", n.rel, f"audit 已开启 {(now - created).days} 天未处理"))
        if n.type == "candidate" and n.status == "proposed" and (now - created).days > 30:
            issues.append(Issue("warn", "W004", n.rel, f"专题候选已提出 {(now - created).days} 天未决策"))

    # 原始素材是否被卡片引用
    referenced = set()
    for n in notes:
        if n.type == "card":
            for s in as_list(n.fm.get("source")):
                hit, _ = idx.resolve(s)
                if hit:
                    referenced.add(hit.rel)
    for n in notes:
        if n.type == "source" and n.rel not in referenced:
            issues.append(Issue("info", "I003", n.rel, "原始素材尚未被任何卡片引用（未拆卡）"))

    return sorted(issues, key=lambda i: ({"error": 0, "warn": 1, "info": 2}[i.level], i.rel, i.code))


def cmd_lint(args: argparse.Namespace) -> int:
    issues = lint()
    counts = Counter(i.level for i in issues)
    if args.json:
        print(json.dumps({
            "errors": counts["error"], "warnings": counts["warn"], "infos": counts["info"],
            "issues": [i.__dict__ for i in issues],
        }, ensure_ascii=False, indent=2))
    else:
        for i in issues:
            print(i.fmt())
        print()
        print(f"合计：错误 {counts['error']} · 警告 {counts['warn']} · 提示 {counts['info']}")
        if counts["error"]:
            print("提示：先修错误，再发布。`kb.py lint --json` 可机器读取。")
    if counts["error"] or (args.strict and counts["warn"]):
        return 1
    return 0


# --------------------------------------------------------------------------- #
# 发布：白名单复制 + 链接重写 + 泄漏守卫
# --------------------------------------------------------------------------- #
def resolve_out(arg: str) -> Path:
    p = Path(arg)
    return (ROOT / p).resolve() if not p.is_absolute() else p.resolve()


def published_notes(notes: list[Note]) -> list[Note]:
    out = []
    for n in notes:
        if n.rel == "index.md":
            out.append(n)
            continue
        if n.dir == CARDS and n.status == "confirmed":
            out.append(n)
        elif n.dir == TOPICS and n.status == "confirmed":
            out.append(n)
        elif n.dir == MOC and n.status == "active":
            out.append(n)
    return out


def rewrite_for_publish(note: Note, idx: Index, keep: set[str]) -> str:
    fm = {k: note.fm[k] for k in PUBLISH_FM_KEYS if k in note.fm}
    fm["title"] = note.title
    text = note.body
    text = re.sub(r"(?s)<!--.*?-->", "", text)

    def repl(m: re.Match[str]) -> str:
        embed, inner = m.group(1), m.group(2)
        target, sep, alias = inner.partition("|")
        pure = target.split("#")[0].strip()
        hit, state = idx.resolve(pure)
        if hit and state == "ok" and hit.rel in keep:
            suffix = f"#{target.split('#', 1)[1]}" if "#" in target else ""
            label = alias.strip() if sep else ""
            link = f"{hit.rel[:-3]}{suffix}"
            return f"![[{link}|{label}]]" if (embed and label) else (f"![[{link}]]" if embed else (f"[[{link}|{label}]]" if label else f"[[{link}]]"))
        label = alias.strip() if sep else ""
        if label:
            return label
        return hit.title if hit else pure

    body = LINK_RE.sub(repl, text)
    body = re.sub(r"\n{4,}", "\n\n\n", body).strip() + "\n"
    return dump_frontmatter(fm) + "\n" + body


def cmd_publish(args: argparse.Namespace) -> int:
    out = resolve_out(args.out)
    try:
        inside = out.relative_to(ROOT)
    except ValueError:
        inside = None
    if out == ROOT or (inside is not None and inside.parts and inside.parts[0] in INTERNAL_DIRS + PUBLISHED_DIRS):
        print(f"拒绝发布到源目录：{out}", file=sys.stderr)
        return 2

    notes = load_notes()
    idx = Index(notes)
    picks = published_notes(notes)
    if args.include_drafts:
        picks = [n for n in notes
                 if n.rel == "index.md" or (n.dir in PUBLISHED_DIRS and n.type in ("card", "topic", "moc"))]
    keep = {n.rel for n in picks}

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    manifests = []
    for n in picks:
        rendered = rewrite_for_publish(n, idx, keep)
        dest = out / n.rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(rendered, encoding="utf-8", newline="\n")
        manifests.append({
            "source": n.rel,
            "output": n.rel,
            "type": n.type,
            "sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
        })

    manifest = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "output": str(out),
        "note_count": len(picks),
        "by_type": dict(Counter(m["type"] for m in manifests)),
        "notes": manifests,
    }
    state = ROOT / META / "state"
    state.mkdir(parents=True, exist_ok=True)
    write_text(state / "publish-manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

    print(f"已生成发布面：{out}")
    print(f"  文件数 {len(picks)} · " + " · ".join(f"{k} {v}" for k, v in manifest["by_type"].items()))
    if not args.include_drafts:
        skipped = [n for n in notes if n.dir in PUBLISHED_DIRS and n not in picks]
        if skipped:
            print(f"  已排除 {len(skipped)} 个未确认/草稿笔记（staged、draft、archived）")
    print("  下一步：python 90_Meta/scripts/kb.py guard --dir .publish")
    return 0


def guard_dir(out: Path) -> list[str]:
    problems: list[str] = []
    if not out.exists():
        return [f"发布目录不存在：{out}"]
    files = [p for p in out.rglob("*") if p.is_file()]
    if not files:
        problems.append("发布目录为空")
    allowed_top = set(PUBLISHED_DIRS)
    for p in files:
        relp = p.relative_to(out).as_posix()
        if p.suffix.lower() != ".md":
            problems.append(f"非 Markdown 文件进入发布面：{relp}")
            continue
        if "/" not in relp:
            if relp != "index.md":
                problems.append(f"根目录出现白名单外文件：{relp}")
            continue
        top = relp.split("/")[0]
        if top not in allowed_top:
            problems.append(f"目录不在发布白名单：{relp}")
    bad_markers = [d + "/" for d in INTERNAL_DIRS] + [
        "type: audit", "type: source", "type: candidate",
        "severity:", "cluster_cards", "proposed_title", "anchor:",
    ]
    for p in files:
        if p.suffix.lower() != ".md":
            continue
        relp = p.relative_to(out).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        for marker in bad_markers:
            if marker in text:
                problems.append(f"{relp} 含内部标记 `{marker}`")
        if re.search(r"\b[KAS]-\d{8}-\d{2}\b", text):
            problems.append(f"{relp} 含内部 ID（K-/A-/S- 前缀）")
        try:
            fm, _ = parse_frontmatter(text)
        except KBError as e:
            problems.append(f"{relp} frontmatter 损坏：{e}")
            continue
        t = fm.get("type")
        if relp != "index.md" and t not in ("card", "topic", "moc"):
            problems.append(f"{relp} 类型 `{t}` 不应出现在发布面")
        if t in ("audit", "candidate", "source"):
            problems.append(f"{relp} 内部类型泄露：{t}")
        for key in ("status", "topics", "mocs", "cards", "source", "rationale", "target", "severity"):
            if key in fm and key not in ("type", "title"):
                problems.append(f"{relp} 保留了内部字段 `{key}`")
    return problems


def cmd_guard(args: argparse.Namespace) -> int:
    out = resolve_out(args.dir)
    problems = guard_dir(out)
    if problems:
        print(f"守卫未通过（{len(problems)} 项）：", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"守卫通过：发布面只含 {', '.join(PUBLISHED_DIRS)} 与 index.md，无内部目录、字段或 ID。")
    return 0


# --------------------------------------------------------------------------- #
# 生成 / 晋升 / 候选决策
# --------------------------------------------------------------------------- #
def templates_dir() -> Path:
    return ROOT / META / "templates"


def read_template(name: str) -> str:
    p = templates_dir() / f"{name}.md"
    if not p.exists():
        raise KBError(f"模板缺失：{p}")
    return p.read_text(encoding="utf-8")


def next_id(prefix: str) -> str:
    notes = load_notes()
    pat = re.compile(rf"^{prefix}-{compact()}-(\d{{2}})$")
    seqs = [int(m.group(1)) for n in notes for m in [pat.match(str(n.fm.get("id", "")))] if m]
    return f"{prefix}-{compact()}-{max(seqs, default=0) + 1:02d}"


def unique_path(p: Path) -> Path:
    if not p.exists():
        return p
    for i in range(2, 100):
        cand = p.with_name(f"{p.stem}-{i}{p.suffix}")
        if not cand.exists():
            return cand
    raise KBError(f"无法生成唯一文件名：{p}")


def new_from_template(kind: str, values: dict[str, str], path: Path) -> Note:
    """先解析模板 frontmatter，再替换占位符，避免标题里的引号破坏 YAML。"""
    text = read_template(kind)
    fm, body = parse_frontmatter(text)
    for k, v in values.items():
        body = body.replace("{{" + k + "}}", v)
        for fk, fv in list(fm.items()):
            if isinstance(fv, str):
                fm[fk] = fv.replace("{{" + k + "}}", v)
            elif isinstance(fv, list):
                fm[fk] = [str(x).replace("{{" + k + "}}", v) for x in fv]
    body = re.sub(r"\{\{[a-z_]+\}\}", "", body)
    return Note(path=path, rel=relpath(path), fm=fm, body=body, text=text)


def save(note: Note) -> None:
    note.fm["updated"] = today()
    text = dump_frontmatter(note.fm) + "\n" + note.body.lstrip("\n")
    write_text(note.path, text)


def warn_if_template_placeholders(note: Note) -> None:
    if "{{" in note.text:
        print(f"提示：仍有未替换的占位符 {note.rel}")


def cmd_new(args: argparse.Namespace) -> int:
    kind = args.kind
    title = args.title.strip()
    if not title:
        print("标题不能为空", file=sys.stderr)
        return 2
    d = compact()
    if kind == "card":
        path = unique_path(ROOT / STAGING / f"{d}-{safe_name(title)}.md")
        note = new_from_template("card", {"title": title, "id": next_id("C"), "date": today()}, path)
        note.fm["topics"] = []
        note.fm["moc"] = []
        note.fm["source"] = []
        for t in args.topic or []:
            hit = Index(load_notes()).resolve(t)[0]
            note.fm["topics"].append(hit.rel[:-3] if hit else t)
        for m in args.source or []:
            note.fm["source"].append(m)
    elif kind == "topic":
        path = unique_path(ROOT / TOPICS / f"{safe_name(title)}.md")
        note = new_from_template("topic", {"title": title, "id": next_id("T"), "date": today()}, path)
        note.fm["mocs"] = []
    elif kind == "moc":
        if not args.topic:
            print("MOC 需要 --topic 指定上级专题", file=sys.stderr)
            return 2
        moc_stem = safe_name(re.sub(r"\s*MOC$", "", title, flags=re.I))
        path = unique_path(ROOT / MOC / f"{moc_stem}-MOC.md")
        parent = args.topic[0]
        hit = Index(load_notes()).resolve(parent)[0]
        parent_rel = (hit.rel[:-3] if hit else parent)
        note = new_from_template("moc", {
            "title": title, "id": next_id("M"), "date": today(),
            "parent_topic": f"[[{parent_rel}]]",
        }, path)
        note.fm["parent_topic"] = [parent_rel]
        note.fm["cards"] = list(args.card or [])
        if hit and hit.type == "topic":
            mocs = as_list(hit.fm.get("mocs"))
            if note.rel[:-3] not in [m[:-3] for m in mocs]:
                mocs.append(note.rel[:-3])
                hit.fm["mocs"] = mocs
                save(hit)
    elif kind == "candidate":
        path = unique_path(ROOT / CANDIDATES / f"candidate-{d}-{safe_name(title)}.md")
        note = new_from_template("candidate", {"title": title, "id": next_id("K"), "date": today()}, path)
        note.fm["cluster_cards"] = list(args.card or [])
        if args.rationale:
            note.fm["rationale"] = args.rationale
    elif kind == "audit":
        if not args.target:
            print("audit 需要 --target", file=sys.stderr)
            return 2
        aid = next_id("A")
        seq = aid.rsplit("-", 1)[1]
        target_stem = args.target.rsplit("/", 1)[-1].replace(".md", "")
        target_stem = re.sub(r"^\d{8}-", "", target_stem)
        path = unique_path(ROOT / AUDIT / f"audit-{d}-{seq}-{safe_name(target_stem, 24)}.md")
        note = new_from_template("audit", {
            "id": aid, "date": today(), "target": f"[[{args.target}]]",
            "severity": args.severity or "minor", "anchor": args.anchor or "",
        }, path)
        note.fm["title"] = f"审阅：{args.target.rsplit('/', 1)[-1].replace('.md', '')}"
        note.fm["target"] = [args.target]
        note.fm["severity"] = args.severity or "minor"
        if args.anchor:
            note.fm["anchor"] = args.anchor
        if args.note:
            note.body = note.body.replace("在这里写清楚：哪里不对、为什么不对、期望改成什么。", args.note)
    else:
        print(f"未知类型：{kind}", file=sys.stderr)
        return 2

    save(note)
    print(f"已创建：{note.rel}")
    return 0


def find_note(arg: str) -> Note:
    p = Path(arg)
    path = p if p.is_absolute() else (ROOT / p)
    if not path.exists():
        # 允许只给文件名
        hits = [x for x in iter_markdown() if x.stem == p.stem]
        if len(hits) == 1:
            path = hits[0]
        else:
            raise KBError(f"找不到笔记：{arg}")
    return load_note(path)


def relink_all(old_rel: str, new_rel: str, skip_rel: str) -> int:
    """把全库指向 old_rel 的双链改写成 new_rel（机械修复，不做归属判断）。"""
    old_base = norm(old_rel)
    new_base = norm(new_rel)
    pat = re.compile(r"\[\[" + re.escape(old_base) + r"(?:\.md)?(?=[\]|#])")
    changed = 0
    for n in load_notes():
        if n.rel == skip_rel:
            continue
        if not pat.search(n.text):
            continue
        write_text(n.path, pat.sub(f"[[{new_base}", n.text))
        changed += 1
    return changed


def cmd_promote(args: argparse.Namespace) -> int:
    note = find_note(args.path)
    if note.dir != STAGING:
        print(f"只能晋升 20_Staging 中的卡片：{note.rel}", file=sys.stderr)
        return 2
    if note.type != "card":
        print("只能晋升 card", file=sys.stderr)
        return 2
    topics = list(args.topic or [])
    if not topics:
        print("必须用 --topic 指定归属专题（专题必须已存在）", file=sys.stderr)
        return 2
    idx = Index(load_notes())
    resolved = []
    for t in topics:
        hit, state = idx.resolve(t)
        if not hit or hit.type != "topic":
            print(f"专题不存在或不是 topic：{t}", file=sys.stderr)
            return 2
        resolved.append(hit.rel[:-3])
    dest = unique_path(ROOT / CARDS / note.path.name)
    old = note.path
    old_rel = relpath(old)
    note.fm["status"] = "confirmed"
    note.fm["topics"] = resolved
    note.path = dest
    note.rel = relpath(dest)
    save(note)
    if old.exists() and old != dest:
        old.unlink()
        print(f"  已从 staging 移除 {old_rel}")
    rewired = relink_all(old_rel, note.rel, note.rel)
    if rewired:
        print(f"  已改写 {rewired} 篇笔记中指向 staging 的链接")
    print(f"已晋升：{note.rel}")
    return 0


def cmd_accept(args: argparse.Namespace) -> int:
    cand = find_note(args.path)
    if cand.type != "candidate":
        print("只能接受 candidate", file=sys.stderr)
        return 2
    if cand.status == "accepted":
        print("该候选已被接受过", file=sys.stderr)
        return 2
    title = args.title or str(cand.fm.get("proposed_title") or cand.fm.get("title") or cand.path.stem)
    path = unique_path(ROOT / TOPICS / f"{safe_name(title)}.md")
    topic = new_from_template("topic", {"title": title, "id": next_id("T"), "date": today()}, path)
    topic.fm["mocs"] = []
    topic.fm["origin_candidate"] = cand.rel
    save(topic)

    cand.fm["status"] = "accepted"
    cand.fm["decided"] = today()
    cand.fm["accepted_as"] = [topic.rel[:-3]]
    save(cand)
    print(f"候选已接受，创建专题：{topic.rel}")
    print(f"  下一步：kb.py new moc \"{title} MOC\" --topic {topic.rel[:-3]}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    cand = find_note(args.path)
    if cand.type != "candidate":
        print("只能拒绝 candidate", file=sys.stderr)
        return 2
    cand.fm["status"] = "rejected"
    cand.fm["decided"] = today()
    if args.reason:
        cand.fm["decision_reason"] = args.reason
    save(cand)
    print(f"候选已拒绝：{cand.rel}")
    return 0


# --------------------------------------------------------------------------- #
# 状态 / 图 / 链接
# --------------------------------------------------------------------------- #
def cmd_status(args: argparse.Namespace) -> int:
    notes = load_notes()
    by_type = Counter(n.type for n in notes)
    cards = [n for n in notes if n.type == "card"]
    audits = [n for n in notes if n.type == "audit"]
    cands = [n for n in notes if n.type == "candidate"]
    sources = [n for n in notes if n.type == "source"]
    topics = [n for n in notes if n.type == "topic"]

    print("KBMS 状态")
    print("-" * 46)
    print(f"卡片      {len(cards):>3}  （confirmed {sum(n.status == 'confirmed' for n in cards)} / staged {sum(n.status == 'staged' for n in cards)} / retired {sum(n.status == 'retired' for n in cards)}）")
    print(f"专题      {len(topics):>3}  （confirmed {sum(n.status == 'confirmed' for n in topics)} / draft {sum(n.status == 'draft' for n in topics)}）")
    print(f"MOC       {by_type['moc']:>3}")
    print(f"候选      {len(cands):>3}  （待决策 {sum(n.status == 'proposed' for n in cands)}）")
    print(f"审阅      {len(audits):>3}  （open {sum(n.status == 'open' for n in audits)}）")
    print(f"原始素材  {len(sources):>3}")
    print("-" * 46)

    inbox = [p for p in (ROOT / INBOX).glob("*")
             if p.is_file() and p.name not in (".gitkeep", "README.md")]
    staged = [n for n in cards if n.status == "staged"]
    open_audits = [n for n in audits if n.status == "open"]
    proposed = [n for n in cands if n.status == "proposed"]

    actions = []
    if inbox:
        actions.append(f"处理 {len(inbox)} 个收件箱文件：kb.py ingest <file>")
    if staged:
        actions.append(f"审阅 {len(staged)} 张 staging 卡片：kb.py promote <file> --topic <topic>")
    if open_audits:
        actions.append(f"处理 {len(open_audits)} 条 open 审阅意见")
    if proposed:
        actions.append(f"决策 {len(proposed)} 个专题候选：kb.py accept/reject")
    issues = lint()
    errs = sum(i.level == "error" for i in issues)
    if errs:
        actions.append(f"修复 {errs} 个 lint 错误：kb.py lint")
    print("下一步：")
    if actions:
        for a in actions:
            print(f"  · {a}")
    else:
        print("  · 无待办。可以开始读、写卡片了。")
    return 0


def build_graph() -> dict[str, Any]:
    notes = load_notes()
    idx = Index(notes)
    nodes = {n.rel: {"type": n.type, "title": n.title, "status": n.status} for n in notes}
    edges = []
    indeg: Counter[str] = Counter()
    for n in notes:
        for embed, target, _ in links_in(n.text):
            hit, state = idx.resolve(target)
            if hit and state == "ok" and hit.rel != n.rel:
                edges.append({"from": n.rel, "to": hit.rel, "embed": embed})
                indeg[hit.rel] += 1
    return {"nodes": nodes, "edges": edges, "indegree": dict(indeg)}


def cmd_graph(args: argparse.Namespace) -> int:
    g = build_graph()
    if args.json:
        print(json.dumps(g, ensure_ascii=False, indent=2))
        return 0
    print(f"节点 {len(g['nodes'])} · 边 {len(g['edges'])}")
    hubs = sorted(g["indegree"].items(), key=lambda x: -x[1])[:10]
    print("被引用最多：")
    for rel, n in hubs:
        print(f"  {n:>3}  {rel}")
    orphans = [rel for rel, meta in g["nodes"].items()
               if meta["type"] in ("card", "topic", "moc") and g["indegree"].get(rel, 0) == 0]
    if orphans:
        print(f"零入链（{len(orphans)}）：")
        for rel in orphans[:20]:
            print(f"       {rel}")
    return 0


def cmd_links(args: argparse.Namespace) -> int:
    note = find_note(args.path)
    notes = load_notes()
    idx = Index(notes)
    out = []
    for _, target, inner in links_in(note.text):
        hit, state = idx.resolve(target)
        out.append((inner, hit.rel if hit else f"<{state}>"))
    back = []
    for n in notes:
        for _, target, _ in links_in(n.text):
            hit, state = idx.resolve(target)
            if hit and hit.rel == note.rel:
                back.append(n.rel)
    print(f"{note.rel}  ({note.type}/{note.status})")
    print("出链：")
    for inner, dest in out:
        print(f"  [[{inner}]] -> {dest}")
    if not out:
        print("  （无）")
    print("入链：")
    for r in sorted(set(back)):
        print(f"  {r}")
    if not back:
        print("  （无）")
    return 0


# --------------------------------------------------------------------------- #
# 原始素材入库
# --------------------------------------------------------------------------- #
def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|li|h[1-6]|tr|section|article)>", "\n", raw)
    raw = re.sub(r"<[^>]+>", "", raw)
    import html as _html
    text = _html.unescape(raw)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract_pdf(path: Path) -> tuple[str, str]:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception:
        return "", "pypdf 未安装，未提取正文（见 90_Meta/schema/ingest.md）"
    try:
        reader = PdfReader(str(path))
        pages = [(i + 1, (p.extract_text() or "").strip()) for i, p in enumerate(reader.pages)]
        text = "\n\n".join(f"<!-- page {i} -->\n{t}" for i, t in pages if t)
        return text, f"pypdf 提取 {len(reader.pages)} 页"
    except Exception as e:
        return "", f"PDF 提取失败：{e}"


def cmd_ingest(args: argparse.Namespace) -> int:
    src = Path(args.file)
    if not src.is_absolute():
        src = (Path.cwd() / src).resolve()
    if not src.exists():
        print(f"文件不存在：{src}", file=sys.stderr)
        return 2
    data = src.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    d = compact()
    title = args.title or src.stem
    ext = src.suffix.lower()
    text_formats = {".md", ".txt", ".html", ".htm"}
    asset_rel = ""
    if ext not in text_formats:
        assets = ROOT / RAW / "assets"
        assets.mkdir(parents=True, exist_ok=True)
        asset = unique_path(assets / f"{d}-{safe_name(title)}{ext}")
        asset.write_bytes(data)
        asset_rel = asset.relative_to(ROOT).as_posix()

    if ext == ".pdf":
        body, how = extract_pdf((ROOT / asset_rel) if asset_rel else src)
    elif ext in (".html", ".htm"):
        body, how = html_to_text(data.decode("utf-8", errors="replace")), "HTML 转纯文本"
    elif ext in (".md", ".txt"):
        body, how = data.decode("utf-8", errors="replace"), "直接读取"
    else:
        body, how = "", f"未识别的扩展名 {ext}，仅归档原文件"

    note_path = unique_path(ROOT / RAW / f"{d}-{safe_name(title)}.md")
    note = new_from_template("source", {"title": title, "id": next_id("S"), "date": today()}, note_path)
    note.fm["id"] = next_id("S")
    note.fm["source_type"] = ext.lstrip(".") or "file"
    note.fm["sha256"] = sha
    note.fm["asset"] = [asset_rel] if asset_rel else []
    note.fm["origin"] = str(src)
    note.fm["extracted"] = bool(body)
    note.body = note.body.replace("- 原始文件：", f"- 原始文件：`{src}`")
    note.body = note.body.replace("- 获取方式：", f"- 获取方式：{how}")
    note.body = note.body.replace("<!-- 把提取到的正文粘贴到这里，或由导入脚本写入 -->", body)
    save(note)

    dest = ROOT / INBOX / src.name
    if not args.keep and dest.resolve() != src.resolve():
        try:
            shutil.move(str(src), str(dest))
            moved = f"，原文件已移入 {INBOX}/"
        except Exception as e:
            moved = f"，原文件保留在原位（移动失败：{e}）"
    elif not args.keep:
        moved = "，原文件已在收件箱"
    else:
        moved = ""
    print(f"已入库：{note.rel}")
    asset_msg = f"资产：{asset_rel}  " if asset_rel else ""
    print(f"  {asset_msg}sha256={sha[:12]}…  {how}{moved}")
    print("  下一步：让 AI 从该素材拆卡到 20_Staging。")
    return 0


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--root", help="覆盖库根目录（默认从脚本位置推断，或 KBMS_ROOT）")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="kb.py", description="KBMS 知识库治理工具")
    add_common(ap)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="看板与下一步动作")
    add_common(p)

    p = sub.add_parser("lint", help="结构与链接检查")
    add_common(p)
    p.add_argument("--json", action="store_true")
    p.add_argument("--strict", action="store_true", help="警告也视为失败（CI 用）")

    p = sub.add_parser("publish", help="生成发布面（白名单）")
    add_common(p)
    p.add_argument("--out", default=".publish")
    p.add_argument("--clean", action="store_true", help="兼容参数：总是重建")
    p.add_argument("--include-drafts", action="store_true", help="本地预览时包含草稿")

    p = sub.add_parser("guard", help="检查发布面是否泄漏内部内容")
    add_common(p)
    p.add_argument("--dir", default=".publish")

    p = sub.add_parser("new", help="按模板创建笔记")
    add_common(p)
    p.add_argument("kind", choices=["card", "topic", "moc", "candidate", "audit"])
    p.add_argument("title")
    p.add_argument("--topic", action="append")
    p.add_argument("--moc", action="append")
    p.add_argument("--card", action="append")
    p.add_argument("--source", action="append")
    p.add_argument("--target")
    p.add_argument("--anchor")
    p.add_argument("--severity", default="minor")
    p.add_argument("--rationale")
    p.add_argument("--note")

    p = sub.add_parser("promote", help="把 staging 卡片晋升为正式卡片")
    add_common(p)
    p.add_argument("path")
    p.add_argument("--topic", action="append", required=True)

    p = sub.add_parser("accept", help="接受专题候选（唯一会创建专题的命令）")
    add_common(p)
    p.add_argument("path")
    p.add_argument("--title")

    p = sub.add_parser("reject", help="拒绝专题候选")
    add_common(p)
    p.add_argument("path")
    p.add_argument("--reason")

    p = sub.add_parser("graph", help="链接图摘要")
    add_common(p)
    p.add_argument("--json", action="store_true")

    p = sub.add_parser("links", help="查看单条笔记的出链/入链")
    add_common(p)
    p.add_argument("path")

    p = sub.add_parser("ingest", help="原始素材入库")
    add_common(p)
    p.add_argument("file")
    p.add_argument("--title")
    p.add_argument("--keep", action="store_true", help="保留原文件位置，不移动到 00_Inbox")

    return ap


def main(argv: list[str] | None = None) -> int:
    global ROOT
    ap = build_parser()
    args = ap.parse_args(argv)
    if getattr(args, "root", None):
        ROOT = Path(args.root).resolve()
    handlers = {
        "status": cmd_status,
        "lint": cmd_lint,
        "publish": cmd_publish,
        "guard": cmd_guard,
        "new": cmd_new,
        "promote": cmd_promote,
        "accept": cmd_accept,
        "reject": cmd_reject,
        "graph": cmd_graph,
        "links": cmd_links,
        "ingest": cmd_ingest,
    }
    try:
        return handlers[args.cmd](args)
    except KBError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
