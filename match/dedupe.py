"""去重与台账 —— 三重查重的本地两层。

1. ledger.jsonl：本工具投递记录（append-only，一行一投）
2. 扫描结果内部去重：Job.key()（公司+标题+地点规范化）
3. 远端查重（Notion 台账等）留给上层适配器，本模块提供 hook 接口。
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from scan.schema import Job

DEFAULT_LEDGER = Path("ledger.jsonl")


def _norm(s: str) -> str:
    # 保留中日韩字符：纯中文雇主名若被删空，不同公司会塌成同一个 key 造成误判重复
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", (s or "").lower())[:40]


def job_key(job: Job) -> str:
    return f"{_norm(job.company)}|{_norm(job.title)}|{_norm(job.location)}"


def load_ledger(path: Path = DEFAULT_LEDGER) -> set[str]:
    keys: set[str] = set()
    if not path.exists():
        return keys
    for line in path.read_text().splitlines():
        try:
            rec = json.loads(line)
            keys.add(rec.get("key", ""))
            if rec.get("external_id"):
                keys.add("ext:" + str(rec["external_id"]))
        except json.JSONDecodeError:
            continue
    keys.discard("")
    return keys


def filter_new(jobs: list[Job], ledger_keys: set[str]) -> tuple[list[Job], list[Job]]:
    """返回 (新岗位, 被去重掉的岗位)。"""
    fresh, dup = [], []
    seen: set[str] = set()
    for j in jobs:
        k = job_key(j)
        if k in seen or k in ledger_keys or f"ext:{j.id}" in ledger_keys:
            dup.append(j)
        else:
            seen.add(k)
            fresh.append(j)
    return fresh, dup


def record_apply(job: Job, result: str, note: str = "", path: Path = DEFAULT_LEDGER) -> None:
    """投递成功后追加台账（完工必归档的第一步）。"""
    rec = {
        "key": job_key(job),
        "channel": job.channel,
        "external_id": job.id,
        "title": job.title,
        "company": job.company,
        "url": job.url,
        "result": result,          # sent | blocked | external_ats | failed
        "note": note,
    }
    with path.open("a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
