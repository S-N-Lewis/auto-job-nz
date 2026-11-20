#!/usr/bin/env python3
"""kiwileap 晨扫：纯 Python，不依赖 agent / WebSocket / 浏览器。

设计原因：agent 驱动的 cron 在 Alma 内部连接断开时 0ms 直接失败（2026-11-21 实测
两次），晨报根本没产出。本脚本把「采集」与「播报」解耦——采集由 macOS launchd
定时执行，结果写成文件；播报（给 Simon 看）是轻量步骤，即使当时没连上，
报告也已经躺在磁盘上，不会丢。

用法：
    python3 morning.py                 # 扫描 + 出报告
    python3 morning.py --days 2        # 指定回溯天数
    python3 morning.py --quiet         # 只写文件不打印

输出：data/morning-YYYY-MM-DD.md（同日重跑覆盖）+ stdout
"""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import db as _db                      # noqa: E402
from match.dedupe import load_ledger  # noqa: E402
from scan import seek as seek_scan    # noqa: E402


def _run(argv: list[str], timeout: int = 180) -> tuple[int, str]:
    try:
        r = subprocess.run(argv, cwd=HERE, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, "missing command"
    except subprocess.TimeoutExpired:
        return 124, "timeout"


DB_ADDED = re.compile(r"入库新增\s*(\d+)\s*条")


def scan_channels(days: int) -> dict:
    """API 通道（SEEK + 天维）自动扫；浏览器通道如实标注跳过。

    注意：scan 每关键词打印的「新 N」是按 ledger.jsonl 去重的结果，
    而 ledger.jsonl 可能不存在（历史投递记录在 DB applications 表里）。
    真实入库数以 DB 的 INSERT OR IGNORE 计数为准，这里单独提取。
    """
    out = {"seek": "", "skykiwi": "", "trademe": "skipped (需要浏览器/agent)",
           "indeed": "skipped (需要浏览器/agent)", "added": {}}
    for ch in ("seek", "skykiwi"):
        rc, txt = _run([sys.executable, "cli.py", "scan", "--channel", ch,
                        "--days", str(days)], timeout=240)
        if rc != 0:
            out[ch] = f"FAILED rc={rc}: {txt.strip()[:200]}"
            continue
        out[ch] = txt.strip()
        m = DB_ADDED.search(txt)
        out["added"][ch] = int(m.group(1)) if m else None
    return out


NEXT_LINE = re.compile(r"^\s*\[\s*(\d+)\]\s+(\w+)#(\S+)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*$")


def ranked(limit: int = 20) -> list[dict]:
    """复用 cli.py next 的打分逻辑（单一真相源），解析其固定格式输出。"""
    rc, txt = _run([sys.executable, "cli.py", "next", "--limit", str(limit)])
    if rc != 0:
        return []
    out = []
    for line in txt.splitlines():
        m = NEXT_LINE.match(line)
        if not m:
            continue
        score, ch, jid, title, company, salary = m.groups()
        out.append({"score": int(score), "channel": ch, "id": jid,
                    "title": title, "company": company, "salary": salary})
    return out


def prior_outcome(jid: str, channel: str) -> dict | None:
    """查该岗位以往的处理结果（blocked 尤其重要：别再当新岗推）。"""
    with _db.conn() as c:
        r = c.execute("SELECT result,note FROM applications "
                      "WHERE job_id=? AND job_channel=? ORDER BY id DESC LIMIT 1",
                      (str(jid), channel)).fetchone()
    return dict(r) if r else None


def enrich(cands: list[dict]) -> list[dict]:
    """cli.py next 只给 4 个字段，其余从 DB 补齐（报告需要地点与链接）。"""
    with _db.conn() as c:
        for j in cands:
            row = c.execute("SELECT location,url,description FROM jobs WHERE id=? AND channel=?",
                            (str(j["id"]), j["channel"])).fetchone()
            if row:
                j["location"] = row["location"] or ""
                j["url"] = row["url"] or ""
                j["snippet"] = (row["description"] or "")[:220]
            j.setdefault("location", "")
            j.setdefault("url", "")
            j.setdefault("snippet", "")
            j["prior"] = prior_outcome(j["id"], j["channel"])
    return cands


def gate_check(cands: list[dict]) -> tuple[list[dict], list[str]]:
    """投递前查重：DUP 的直接剔除，PASS 的留下。"""
    ok, dropped = [], []
    for j in cands:
        rc, txt = _run([sys.executable, "cli.py", "gate", str(j["id"]),
                        "--channel", j["channel"]])
        if rc == 2:
            dropped.append(f"{j['channel']}#{j['id']} {j['title'][:36]} — {txt.strip()}")
        else:
            ok.append(j)
    return ok, dropped


def ats_for(j: dict) -> str:
    """cli.py ats 输出 JSON，取 ats/has_plugin/tip。"""
    rc, txt = _run([sys.executable, "cli.py", "ats", str(j["id"]), "--channel", j["channel"]])
    if rc != 0 or not txt.strip():
        return "未知"
    try:
        d = json.loads(txt)
    except json.JSONDecodeError:
        return (txt.strip().splitlines() or ["未知"])[0][:60]
    parts = [d.get("ats", "?")]
    if d.get("has_plugin"):
        parts.append("有插件")
    else:
        parts.append("⚠️无插件")
    if d.get("tip"):
        parts.append(d["tip"][:70])
    return " · ".join(parts)


def build_report(days: int, scan_out: dict, cands: list[dict],
                 dropped: list[str], lessons: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    L = [f"# kiwileap 晨扫 · {now}", ""]

    with _db.conn() as c:
        total = c.execute("SELECT COUNT(*) n FROM jobs").fetchone()["n"]
        applied = c.execute("SELECT COUNT(*) n FROM applications WHERE result='sent'").fetchone()["n"]
        blocked = c.execute("SELECT COUNT(*) n FROM applications WHERE result='blocked'").fetchone()["n"]
        today_in = c.execute("SELECT COUNT(*) n FROM jobs WHERE substr(first_seen,1,10)=?",
                            (datetime.now().strftime("%Y-%m-%d"),)).fetchone()["n"]
    added = scan_out.get("added", {})
    real_new = sum(v for v in added.values() if v is not None) if added else 0
    L += [f"- 通道：SEEK / 天维 走 API；TradeMe / Indeed 需 agent 浏览器（本次跳过）",
          f"- **本次真实入库 {real_new} 条**"
          + ("（" + " + ".join(f"{k} {v}" for k, v in added.items() if v is not None) + "）" if added else ""),
          f"- 库内共 {total} 条岗位（今天首次见到 {today_in} 条）；历史已投 **{applied}** 条，受阻 {blocked} 条",
          f"- 每关键词报「DB 未见 N」= 库里从没见过的岗位数（去重以 DB 为准，不是 ledger.jsonl）", ""]

    for ch in ("seek", "skykiwi"):
        if scan_out.get(ch):
            L.append(f"**[{ch}]**")
            for line in scan_out[ch].splitlines()[:8]:
                L.append(f"- {line}")
            L.append("")
    for ch in ("trademe", "indeed"):
        L.append(f"**[{ch}]** {scan_out.get(ch, 'skipped')}")

    L += ["", "## 推荐候选（已过 gate 查重）", ""]
    if not cands:
        L.append("（无新候选，或全部命中查重）")
    for i, j in enumerate(cands, 1):
        loc = f"（{j['location'][:22]}）" if j.get("location") else ""
        prior = j.get("prior") or {}
        flag = ""
        if prior.get("result") == "blocked":
            flag = " ⚠️**曾放弃**"
        L.append(f"{i}. **[score {j['score']}] {j['title'][:60]}** — {j['company'][:30]}{loc}"
                 f"｜{j['channel']}#{j['id']}{flag}")
        if flag:
            L.append(f"   - ⚠️ 以往处理：blocked — {prior.get('note', '')[:120]}")
        if j.get("salary"):
            L.append(f"   - 薪资：{j['salary']}")
        L.append(f"   - ATS：{ats_for(j)}")
        if j.get("snippet"):
            L.append(f"   - 摘要：{j['snippet']}")
        if j.get("url"):
            L.append(f"   - {j['url']}")
    if dropped:
        L += ["", "## 已剔除（命中查重）", ""]
        L += [f"- {d}" for d in dropped]
    if lessons:
        L += ["", "## 上次沉淀的教训", "", lessons.strip()[:1200]]
    L += ["", "---", "本晨报只扫描与报告，**未投递、未发邮件**。要投哪个回我岗位号即可。"]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    _db.init_db()
    scan_out = scan_channels(a.days)
    cands_all = enrich(ranked(a.limit * 3))
    cands, dropped = gate_check(cands_all)
    cands = cands[:a.limit]

    lessons_file = HERE / "data" / "lessons.md"
    lessons = lessons_file.read_text() if lessons_file.exists() else ""

    report = build_report(a.days, scan_out, cands, dropped, lessons)
    out = HERE / "data" / f"morning-{datetime.now().strftime('%Y-%m-%d')}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report)
    if not a.quiet:
        print(report)
    print(f"\n[saved] {out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
