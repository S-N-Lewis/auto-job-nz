"""SEEK 扫描器 —— 纯 HTTP API（nz.seek.com/api/jobsearch/v5/search）。

参数与端点设计参考 speedyapply/JobSpy (MIT) 的 jobspy/seek 模块：
siteKey=NZ-Main、pageSize、daterange（天）、sortmode=ListedDate。
无需 cookie/token；403/429 视为被限流，退避重试。
"""
from __future__ import annotations
import json
import time
import urllib.parse
import urllib.request
try:
    from .schema import Job
except ImportError:  # 直接 python3 scan/xxx.py 运行时无包上下文
    from schema import Job

BASE = "https://nz.seek.com/api/jobsearch/v5/search"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
PAGE_SIZE = 60
MAX_PAGES = 10


def _get(params: dict, retries: int = 3) -> dict:
    url = BASE + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "seek-request-brand": "seek",
            "seek-request-country": "NZ",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"HTTP {resp.status}")
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            code = getattr(e, "code", None)
            if code in (403, 429):
                wait = 5 * (attempt + 1)
                time.sleep(wait)  # 限流退避
                continue
            if attempt == retries - 1:
                raise
            time.sleep(2)
    raise RuntimeError("SEEK API: rate limited after retries")


def scan(keywords: str, where: str = "Auckland", days: int = 1,
         max_jobs: int = 200) -> list[Job]:
    """按关键词扫描 SEEK NZ，返回统一 Job 列表。"""
    jobs: list[Job] = []
    seen: set[str] = set()
    page = 1
    while page <= MAX_PAGES and len(jobs) < max_jobs:
        data = _get({
            "siteKey": "NZ-Main",
            "pageSize": PAGE_SIZE,
            "keywords": keywords,
            "where": where,
            "daterange": max(1, days),
            "sortmode": "ListedDate",
            "page": page,
        })
        rows = data.get("data") or []
        if not rows:
            break
        for raw in rows:
            jid = str(raw.get("id") or "")
            if not jid or jid in seen:
                continue
            seen.add(jid)
            comp = raw.get("companyName") or (raw.get("advertiser") or {}).get("description") or ""
            locs = raw.get("locations") or []
            loc = locs[0].get("label", "") if locs and isinstance(locs[0], dict) else str(locs[0] if locs else "")
            jobs.append(Job(
                id=jid,
                channel="seek",
                title=(raw.get("title") or "").strip(),
                company=comp.strip(),
                location=loc,
                url=f"https://nz.seek.com/job/{jid}",
                listed=str(raw.get("listingDate") or ""),
                salary=str(raw.get("salaryLabel") or ""),
                worktype=", ".join(raw.get("workTypes") or []),
                description=(raw.get("teaser") or {}).get("text", "")[:2000] if isinstance(raw.get("teaser"), dict) else str(raw.get("teaser") or "")[:2000],
                extra={"classification": (raw.get("classifications") or [{}])[0].get("subclassification", {}).get("description", "") if raw.get("classifications") else "",
                       "isFeatured": bool(raw.get("isFeatured")),
                       "advertiserId": (raw.get("advertiser") or {}).get("id", ""),
                       "dateDisplay": str(raw.get("listingDateDisplay") or "")},
            ))
        total = data.get("totalCount") or 0
        if page * PAGE_SIZE >= total:
            break
        page += 1
        time.sleep(0.4)  # 礼貌间隔
    return jobs


if __name__ == "__main__":
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else "administration"
    out = scan(kw)
    print(f"[seek] keywords={kw!r} -> {len(out)} jobs")
    for j in out[:8]:
        print(f"  #{j.id} {j.title} @ {j.company} | {j.location} | {j.worktype}")
