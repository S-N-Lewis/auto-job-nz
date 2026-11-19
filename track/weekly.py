"""周报生成：读 ledger.jsonl 出投递统计。"""
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path


def report(path: Path = Path("ledger.jsonl")) -> str:
    if not path.exists():
        return "暂无投递记录。"
    recs = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    by_result = Counter(r.get("result", "?") for r in recs)
    by_channel = Counter(r.get("channel", "?") for r in recs)
    lines = [f"本周投递 {len(recs)} 单", f"  结果: {dict(by_result)}", f"  渠道: {dict(by_channel)}"]
    blocked = [r for r in recs if r.get("result") in ("blocked", "failed")]
    if blocked:
        lines.append("  受阻清单:")
        lines += [f"    - {r['title'][:50]} ({r.get('note','')[:40]})" for r in blocked[:10]]
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
