#!/usr/bin/env python3
"""考证笔记与刷题辅助工具。

功能：
    add      记录一道题目（默认记为错题）
    list     查看记录
    review   查看今日待复习，并对条目做通过/未通过评级
    stats    统计正确率（按科目聚合）
    note     新建一条笔记
    index    扫描 notes/ 生成索引
    export   导出错题本为 Markdown

数据文件：data/attempts.jsonl（追加写，纯文本，便于版本管理与人工审阅）
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
import uuid
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
ATTEMPT_FILE = DATA_DIR / "attempts.jsonl"
NOTE_DIR = BASE_DIR / "notes"

DEFAULT_EASE = 2.5


# ---------------------------------------------------------------- 基础设施

def setup_console() -> None:
    """Windows 控制台默认 GBK，强制切到 UTF-8 避免中文输出报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def today() -> date:
    return date.today()


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def load_attempts() -> list[dict]:
    if not ATTEMPT_FILE.exists():
        return []
    records = []
    with ATTEMPT_FILE.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def rewrite_attempts(records: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with ATTEMPT_FILE.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def append_attempt(rec: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with ATTEMPT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def find_record(records: list[dict], prefix: str) -> dict | None:
    matches = [r for r in records if r["id"].startswith(prefix)]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        print(f"未找到 id 以 {prefix} 开头的记录")
    else:
        print(f"id 前缀 {prefix} 匹配到 {len(matches)} 条记录，请写得更具体")
    return None


def display_width(text: str) -> int:
    # W=宽，F=全角，A=歧义（如 ✓、…，在中文终端里按 2 格渲染）
    return sum(2 if unicodedata.east_asian_width(c) in "WFA" else 1 for c in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    widths = [display_width(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], display_width(cell))
    print("  ".join(pad(h, widths[i]) for i, h in enumerate(headers)))
    print("  ".join("-" * widths[i] for i in range(len(headers))))
    for row in rows:
        print("  ".join(pad(cell, widths[i]) for i, cell in enumerate(row)))


# ---------------------------------------------------------------- 间隔重复

def schedule(rec: dict, passed: bool) -> None:
    """简化版 SM-2：通过则拉长间隔，未通过则重置。"""
    ease = rec.get("ease", DEFAULT_EASE)
    reps = rec.get("reps", 0)

    if passed:
        reps += 1
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 3
        else:
            interval = max(1, round(rec.get("interval", 1) * ease))
        ease = min(3.0, ease + 0.1)
    else:
        reps = 0
        interval = 1
        ease = max(1.3, ease - 0.2)

    rec["reps"] = reps
    rec["interval"] = interval
    rec["ease"] = round(ease, 2)
    rec["due"] = (today() + timedelta(days=interval)).isoformat()
    rec["last_review"] = today().isoformat()


def is_due(rec: dict, on: date | None = None) -> bool:
    on = on or today()
    raw = rec.get("due")
    if not raw:
        return True
    try:
        return date.fromisoformat(raw) <= on
    except ValueError:
        return True


# ---------------------------------------------------------------- 子命令

def cmd_add(args: argparse.Namespace) -> int:
    correct = args.correct
    rec = {
        "id": new_id(),
        "ts": now_iso(),
        "subject": args.subject,
        "topic": args.topic or "",
        "question": args.question,
        "mine": args.mine or "",
        "answer": args.answer or "",
        "correct": correct,
        "reason": args.reason or "",
        "ref": args.ref or "",
        "reps": 0,
        "interval": 1,
        "ease": DEFAULT_EASE,
        "due": (today() + timedelta(days=1)).isoformat(),
        "last_review": "",
    }
    append_attempt(rec)
    tag = "正确" if correct else "错题"
    print(f"已记录（{tag}） id={rec['id']}  科目={rec['subject']}  下次复习={rec['due']}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    records = load_attempts()
    if args.subject:
        records = [r for r in records if r.get("subject") == args.subject]
    if args.wrong:
        records = [r for r in records if not r.get("correct")]
    records.sort(key=lambda r: r.get("ts", ""), reverse=True)
    records = records[: args.limit]

    if not records:
        print("暂无记录")
        return 0

    rows = []
    for r in records:
        mark = "✓" if r.get("correct") else "✗"
        rows.append([
            r["id"], mark, r.get("subject", ""), r.get("topic", ""),
            r.get("question", "")[:28], r.get("due", ""),
        ])
    print_table(["ID", "结果", "科目", "章节", "题目", "下次复习"], rows)
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    records = load_attempts()

    if args.pass_id or args.fail_id:
        prefix = args.pass_id or args.fail_id
        rec = find_record(records, prefix)
        if rec is None:
            return 1
        schedule(rec, passed=bool(args.pass_id))
        rewrite_attempts(records)
        state = "通过" if args.pass_id else "未通过"
        print(f"{rec['id']} 已评级为「{state}」，下次复习 {rec['due']}（间隔 {rec['interval']} 天）")
        return 0

    due = [r for r in records if is_due(r) and not r.get("correct")]
    if args.subject:
        due = [r for r in due if r.get("subject") == args.subject]
    due.sort(key=lambda r: r.get("due", ""))
    due = due[: args.limit]

    if not due:
        print("今日没有待复习的错题")
        return 0

    print(f"今日待复习 {len(due)} 条：\n")
    for i, r in enumerate(due, 1):
        print(f"[{i}] {r['id']}  {r.get('subject','')} / {r.get('topic','')}")
        print(f"    题目：{r.get('question','')}")
        if r.get("mine"):
            print(f"    我的答案：{r['mine']}    正确答案：{r.get('answer','')}")
        if r.get("reason"):
            print(f"    错因：{r['reason']}")
        if r.get("ref"):
            print(f"    依据：{r['ref']}")
        print()
    print("评级：python scripts/study.py review --pass <id> | --fail <id>")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    records = load_attempts()
    if args.days:
        cutoff = today() - timedelta(days=args.days)
        filtered = []
        for r in records:
            try:
                if date.fromisoformat(r["ts"][:10]) >= cutoff:
                    filtered.append(r)
            except (KeyError, ValueError):
                continue
        records = filtered

    if not records:
        print("暂无数据")
        return 0

    total = len(records)
    correct = sum(1 for r in records if r.get("correct"))
    print(f"总题数 {total}    正确 {correct}    正确率 {correct / total:.1%}\n")

    by_subject: dict[str, Counter] = {}
    for r in records:
        counter = by_subject.setdefault(r.get("subject", "未分类"), Counter())
        counter["total"] += 1
        counter["correct"] += int(bool(r.get("correct")))

    rows = []
    for subject, c in sorted(by_subject.items(), key=lambda kv: -kv[1]["total"]):
        rate = c["correct"] / c["total"] if c["total"] else 0
        rows.append([subject, str(c["total"]), str(c["correct"]), f"{rate:.1%}"])
    print_table(["科目", "总题数", "正确", "正确率"], rows)

    pending = sum(1 for r in load_attempts() if is_due(r) and not r.get("correct"))
    if pending:
        print(f"\n今日待复习错题：{pending} 条")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    NOTE_DIR.mkdir(parents=True, exist_ok=True)
    slug = args.title.replace(" ", "-").replace("/", "-")
    path = NOTE_DIR / f"{today().isoformat()}-{slug}.md"
    if path.exists():
        print(f"文件已存在：{path.relative_to(BASE_DIR)}")
        return 1

    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    tag_line = ", ".join(tags) if tags else ""
    body = (
        "---\n"
        f"title: {args.title}\n"
        f"created: {today().isoformat()}\n"
        f"tags: [{tag_line}]\n"
        "---\n\n"
        f"# {args.title}\n\n"
        "## 要点\n\n\n"
        "## 易错点\n\n\n"
        "## 法条依据\n\n"
    )
    path.write_text(body, encoding="utf-8")
    print(f"已创建 {path.relative_to(BASE_DIR)}")
    return 0


def parse_front_matter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}
    meta = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta


def cmd_index(args: argparse.Namespace) -> int:
    if not NOTE_DIR.exists():
        print("notes/ 目录不存在")
        return 1

    rows = []
    for path in sorted(NOTE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        meta = parse_front_matter(text)
        # 只收录由 note 子命令创建、带 front matter 的笔记，
        # 避免把 INDEX.md、导出的错题本等生成文件算进去。
        if not meta:
            continue
        title = meta.get("title") or path.stem
        created = meta.get("created", "")
        tags = meta.get("tags", "").strip("[]")
        rows.append([created, title, tags, path.name])

    if not rows:
        print("notes/ 中没有笔记")
        return 0

    rows.sort(reverse=True)
    lines = [
        "# 笔记索引",
        "",
        f"共 {len(rows)} 条，更新于 {today().isoformat()}。",
        "",
        "| 日期 | 标题 | 标签 | 文件 |",
        "| --- | --- | --- | --- |",
    ]
    for created, title, tags, name in rows:
        lines.append(f"| {created} | {title} | {tags} | [{name}]({name}) |")
    lines.append("")

    out = NOTE_DIR / "INDEX.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"索引已生成：{out.relative_to(BASE_DIR)}（{len(rows)} 条）")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    records = [r for r in load_attempts() if not r.get("correct")]
    if args.subject:
        records = [r for r in records if r.get("subject") == args.subject]
    if not records:
        print("没有可导出的错题")
        return 0

    by_subject: dict[str, list[dict]] = {}
    for r in records:
        by_subject.setdefault(r.get("subject", "未分类"), []).append(r)

    lines = ["# 错题本", "", f"导出时间：{now_iso()}", ""]
    for subject, items in sorted(by_subject.items()):
        lines.append(f"## {subject}（{len(items)} 题）")
        lines.append("")
        for i, r in enumerate(items, 1):
            lines.append(f"### {i}. {r.get('topic') or '未分类'} — `{r['id']}`")
            lines.append("")
            lines.append(f"- 题目：{r.get('question','')}")
            if r.get("mine"):
                lines.append(f"- 我的答案：{r['mine']}")
            if r.get("answer"):
                lines.append(f"- 正确答案：{r['answer']}")
            if r.get("reason"):
                lines.append(f"- 错因：{r['reason']}")
            if r.get("ref"):
                lines.append(f"- 依据：{r['ref']}")
            lines.append(f"- 复习进度：{r.get('reps', 0)} 次通过，下次 {r.get('due','')}")
            lines.append("")

    out = Path(args.out) if args.out else BASE_DIR / "notes" / "错题本.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"已导出 {len(records)} 条错题到 {out}")
    return 0


# ---------------------------------------------------------------- 入口

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="study.py",
        description="考证笔记与刷题辅助工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add", help="记录一道题目")
    p.add_argument("question", help="题干")
    p.add_argument("-s", "--subject", required=True, help="科目，如 民法")
    p.add_argument("-t", "--topic", help="章节/知识点")
    p.add_argument("--mine", help="我的答案")
    p.add_argument("--answer", help="正确答案")
    p.add_argument("--reason", help="错因")
    p.add_argument("--ref", help="法条或教材依据")
    p.add_argument("--correct", action="store_true", help="标记为答对（默认记错题）")
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("list", help="查看记录")
    p.add_argument("-s", "--subject", help="按科目筛选")
    p.add_argument("--wrong", action="store_true", help="只看错题")
    p.add_argument("-n", "--limit", type=int, default=20, help="显示条数")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("review", help="今日待复习 / 评级")
    p.add_argument("-s", "--subject", help="按科目筛选")
    p.add_argument("-n", "--limit", type=int, default=10, help="显示条数")
    p.add_argument("--pass", dest="pass_id", metavar="ID", help="标记该条已掌握")
    p.add_argument("--fail", dest="fail_id", metavar="ID", help="标记该条仍未掌握")
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("stats", help="统计正确率")
    p.add_argument("--days", type=int, help="仅统计最近 N 天")
    p.set_defaults(func=cmd_stats)

    p = sub.add_parser("note", help="新建笔记")
    p.add_argument("title", help="笔记标题")
    p.add_argument("--tags", help="标签，逗号分隔")
    p.set_defaults(func=cmd_note)

    p = sub.add_parser("index", help="生成笔记索引")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("export", help="导出错题本")
    p.add_argument("-s", "--subject", help="按科目导出")
    p.add_argument("-o", "--out", help="输出路径")
    p.set_defaults(func=cmd_export)

    return parser


def main(argv: list[str] | None = None) -> int:
    setup_console()
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
