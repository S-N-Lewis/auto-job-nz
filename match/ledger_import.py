"""外部 markdown 投递台账 → SQLite applications 表。

背景：工具早期用 markdown 台账（outputs/job-applications/APPLIED_*.md）记账，
而 gate 查重只读 SQLite applications 表，导致已投岗位被误判 PASS。
本模块把两者打通：markdown 台账是唯一真相源，DB 只是它的索引。
可重复执行（幂等），已存在的记录不会被覆盖成更差的信息。

台账形态多样，全部覆盖：
  1. 表格行（有/无序号列，表头驱动映射列）
  2. 编号列表行：``1. Marist College — International ... （77000101，PT）``
  3. 正文内联：``SEEK #77000102``
  4. 外站 ATS 链接中的申请 ID（SmartRecruiters / Dayforce / PageUp ...）
  5. 通用 ``#ID`` 形态（含"未投/受阻"记录，按原文保守标注 result）
"""
from __future__ import annotations
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import db as _db  # noqa: E402

# ---------------------------------------------------------------- 正则与常量

ID_ANY = re.compile(r"\d{6,15}")
SEEK_LINE = re.compile(r"SEEK\s*#?\(?(\d{8,9})\)?")
HASH_ID = re.compile(r"#\s*(\d{6,10})")
DAYFORCE_ID = re.compile(r"(?:Dayforce|HCM)\s*(?:id)?\s*#?\s*(\d{4,8})", re.I)
ATS_URL = re.compile(
    r"(smartrecruiters\.com|qjumpers|pageup|dayforce)[^|\s)》】]*?/(\d{6,15})", re.I)
NUM_LIST = re.compile(
    r"^\s*\d+\.\s*(?:(.+?)\s*[—\-]\s*(.+?)|(.+?))\s*[（(]\s*(\d{6,10})[，,\s)）]", re.M)
JOB_CONTEXT = re.compile(
    r"(SEEK|岗位|Casual|Seasonal|PT |FT |Administrator|Assistant|Coordinator|"
    r"Representative|Adviser|Advisor|adidas|Foot Locker|Michael Hill|Skechers|"
    r"OneSchool|Autism|Homex|HungryPanda|Windcave|Noel Leeming|Pandora|Oakley)", re.I)

# 台账里判定"这条没投出去"的标记
BLOCK_MARKS = ("未投", "需注册", "登录墙", "blocked", "✗", "⏸", "放弃", "硬性要求")
# 判定"这条投出去了"的标记
SENT_MARKS = ("Application sent", "已提交", "已投", "投出", "投成", "✅", "sent", "确认", "submitted")

KNOWN_ATS_WORDS = ("SEEK", "LinkedIn", "TWG", "ATS", "SmartRecruiters", "Dayforce",
                   "PageUp", "QJumpers", "iCIMS", "SuccessFactors", "JobAdder", "Elmo")

COMPANIES = ("Skechers", "Noel Leeming", "PANDORA", "Pandora", "Oakley", "Luxottica",
             "Homex", "HungryPanda", "Windcave", "Autism New Zealand", "Autism NZ",
             "Michael Hill", "Foot Locker", "adidas", "OneSchool", "Marist College",
             "Foy & Halse", "Stark Medical", "Crocker Group", "Centra Forklifts",
             "GN Hearing", "Wesley College", "Pacific Health Group", "MG 鲜果")

HEADER_MAP = {
    "title": ("岗位", "职位", "title", "role"),
    "company": ("公司", "雇主", "company", "employer"),
    "id": ("job id", "seek id", "id"),
}

# ---------------------------------------------------------------- 基础工具


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _is_sep(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 3 and not (set(s) - set("|-: "))


def _is_row(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and s.count("|") >= 3 and bool(set(s) - set("|-: "))


def _clean_company(raw: str) -> str:
    """'PANDORA / The Howley Group / SEEK #77000102' → 'PANDORA'。"""
    for seg in re.split(r"\s*/\s*", raw or ""):
        if seg and not re.match(r"(" + "|".join(map(re.escape, KNOWN_ATS_WORDS)) + r")", seg, re.I):
            return seg[:80]
    return (re.split(r"\s*/\s*", raw or "") + [""])[0][:80]


def _guess_title(ctx: str) -> str:
    m = re.search(r"[—\-]\s*([A-Z][A-Za-z&',. /()\-]{5,70}?)\s*(?:\(|#|→|$)", ctx)
    if m:
        return m.group(1).strip()[:120]
    m = re.search(
        r"((?:Christmas|Seasonal|Temporary|Bilingual|International|Student|Office|"
        r"Administration|Admin|Customer|Data|Sales|Receptionist|Teacher|Learning|"
        r"ESOL|Therapy|Attendance|Business|Academic|Medical|Clinic|After|Client|"
        r"Gateway|Account|Campus|Support)[A-Za-z&',. /()\-]{2,60})", ctx)
    return (m.group(1).strip() if m else "")[:120]


def _guess_company(ctx: str) -> str:
    for name in COMPANIES:
        if name.lower() in ctx.lower():
            return name
    return ""


def _header_idx(cells: list[str]) -> dict | None:
    low = [c.lower() for c in cells]
    if not any(("岗位" in c or "职位" in c or "title" in c or "role" in c) for c in low):
        return None
    out: dict[str, int] = {}
    for key, names in HEADER_MAP.items():
        for i, c in enumerate(low):
            if any(n in c for n in names):
                out[key] = i
                break
    return out if "id" in out else None


# ---------------------------------------------------------------- 各形态解析


def parse_tables(text: str, channel: str = "seek") -> list[dict]:
    """markdown 表格行，表头驱动列映射（兼容有/无序号列、ID 在链接列）。"""
    out, hdr = [], None
    for line in text.splitlines():
        if _is_sep(line):
            continue          # 分隔行不重置表头（曾因此丢掉整张表）
        if not _is_row(line):
            hdr = None
            continue
        cs = _cells(line)
        h = _header_idx(cs)
        if h:
            hdr = h
            continue
        if not hdr or hdr["id"] >= len(cs):
            continue
        m = ID_ANY.search(cs[hdr["id"]])
        if not m:
            continue
        title = cs[hdr["title"]] if "title" in hdr and hdr["title"] < len(cs) else ""
        company = _clean_company(cs[hdr["company"]]) if "company" in hdr and hdr["company"] < len(cs) else ""
        if not title and company:
            title, company = company, ""
        out.append({"id": m.group(0), "channel": channel, "title": title,
                    "company": company, "note": line.strip()[:200]})
    return out


def parse_numbered(text: str) -> list[dict]:
    """编号列表投递行。"""
    out = []
    for m in NUM_LIST.finditer(text):
        jid = m.group(4)
        if m.group(1):
            company, title = m.group(1).strip(), m.group(2).strip()
        else:
            company, title = "", (m.group(3) or "").strip()
        out.append({"id": jid, "channel": "seek", "title": title,
                    "company": company, "note": m.group(0).strip()[:200]})
    return out


def parse_inline_seeking(text: str) -> list[dict]:
    """正文里的 'SEEK #77000102' 形态（含表格链接列）。"""
    out = []
    for line in text.splitlines():
        for m in SEEK_LINE.finditer(line):
            if line.strip().startswith("|"):
                cs = _cells(line)
                title = cs[1] if len(cs) > 1 else ""
                company = _clean_company(cs[2]) if len(cs) > 2 else ""
                if not title or "SEEK" in title:
                    title = _guess_title(line)
            else:
                title, company = _guess_title(line), _guess_company(line)
            out.append({"id": m.group(1), "channel": "seek", "title": title,
                        "company": company, "note": line.strip()[:200]})
    return out


def parse_hash_ids(text: str) -> list[dict]:
    """通用 '#ID' 形态，只在岗位语境行生效（覆盖未投/受阻记录）。"""
    out = []
    for line in text.splitlines():
        if not JOB_CONTEXT.search(line):
            continue
        for m in HASH_ID.finditer(line):
            out.append({"id": m.group(1), "channel": "seek",
                        "title": _guess_title(line), "company": _guess_company(line),
                        "note": line.strip()[:200]})
    return out


def parse_ats_urls(text: str) -> list[dict]:
    """外站 ATS 链接里的申请 ID。"""
    out = []
    for m in ATS_URL.finditer(text):
        host, jid = m.group(1).lower(), m.group(2)
        ch = "smartrecruiters" if "smartrecruiters" in host else (
            "dayforce" if "dayforce" in host else (
                "pageup" if "pageup" in host else "qjumpers"))
        ctx = text[max(0, m.start() - 220):m.end() + 80].replace("\n", " ")
        out.append({"id": jid, "channel": ch, "title": _guess_title(ctx),
                    "company": _guess_company(ctx), "note": ctx[:200]})
    return out


def parse_dayforce(text: str) -> list[dict]:
    """'Skechers Manawa Bay（Dayforce id 92271）' 形态。"""
    out = []
    for line in text.splitlines():
        for m in DAYFORCE_ID.finditer(line):
            out.append({"id": m.group(1), "channel": "dayforce",
                        "title": _guess_title(line), "company": _guess_company(line),
                        "note": line.strip()[:200]})
    return out


PARSERS = (parse_tables, parse_numbered, parse_inline_seeking,
           parse_hash_ids, parse_ats_urls, parse_dayforce)


DATE_IN_HEAD = re.compile(r"(20\d\d-\d\d-\d\d)")


def _date_at(text: str, pos: int, fallback: str) -> str:
    """取该行之前最近的小节标题里的日期（11-18 的投递记在 11-17 文件里）。"""
    for ln in reversed(text[:pos].splitlines()):
        if ln.startswith("#"):
            m = DATE_IN_HEAD.search(ln)
            if m:
                return m.group(1)
    return fallback


def parse_file(path: Path) -> list[dict]:
    """单文件全形态解析 + 去重（先到先得，表格优先）。"""
    text = path.read_text()
    m0 = DATE_IN_HEAD.search(text[:200] + path.name)
    file_day = m0.group(1) if m0 else ""
    seen, out = set(), []
    for parser in PARSERS:
        for r in parser(text):
            k = (r["channel"], r["id"])
            if k in seen:
                continue
            seen.add(k)
            pos = text.find(r.get("note", "")[:60]) if r.get("note") else -1
            day = _date_at(text, pos, file_day) if pos >= 0 else file_day
            r["applied_at"] = day + "T00:00:00"
            r["source"] = path.name
            out.append(r)
    return out


# ---------------------------------------------------------------- 状态判定


def classify(rec: dict, ledger_text: str) -> str:
    """以台账原文为准判定 sent / blocked，保守优先 blocked。"""
    jid = rec["id"]
    lines = [ln for ln in ledger_text.splitlines() if jid in ln]
    blob = " ".join(lines) or rec.get("note", "")
    if any(n in blob for n in BLOCK_MARKS):
        return "blocked"
    if any(k in blob for k in SENT_MARKS):
        return "sent"
    # 段落级判断：该行所属小节标题若含"未投/障碍"
    for i, ln in enumerate(ledger_text.splitlines()):
        if jid in ln:
            heads = [x for x in ledger_text.splitlines()[:i] if x.startswith("#")]
            if heads and any(n in heads[-1] for n in ("未投", "障碍", "排除", "待手动")):
                return "blocked"
            break
    return "sent"


# ---------------------------------------------------------------- 主入口


def import_ledger(paths: list[Path], dry_run: bool = False) -> dict:
    _db.init_db()
    recs, blobs = [], {}
    for p in paths:
        if not p.exists():
            print(f"  skip (missing): {p}")
            continue
        blobs[p.name] = p.read_text()
        recs.extend(parse_file(p))

    with _db.conn() as c:
        existing = {(x["job_id"], x["job_channel"]): dict(x) for x in
                    c.execute("SELECT * FROM applications")}

    added = updated = skipped = 0
    details = []
    for r in recs:
        r["result"] = classify(r, blobs.get(r["source"], ""))
        k = (r["id"], r["channel"])
        if k in existing:
            old = existing[k]
            better = (old.get("result") in (None, "", "unknown") and r["result"] != "unknown") \
                or ((not old.get("job_title")) and r["title"])
            if better and not dry_run:
                with _db.conn() as c:
                    if not old.get("job_title") and r["title"]:
                        c.execute("UPDATE applications SET job_title=?, job_company=? WHERE id=?",
                                  (r["title"], r["company"], old["id"]))
                    if old.get("result") in (None, "", "unknown") and r["result"] != "unknown":
                        c.execute("UPDATE applications SET result=?, note=? WHERE id=?",
                                  (r["result"], f"imported from {r['source']}", old["id"]))
                updated += 1
                details.append(f"  update {r['channel']}#{r['id']} {r['title'][:30]}")
            else:
                skipped += 1
            continue
        added += 1
        details.append(f"  +{r['result']:<8} {r['channel']}#{r['id']} "
                       f"{(r['title'] or r['company'])[:38]}")
        if not dry_run:
            _db.record_application({"id": r["id"], "channel": r["channel"],
                                    "title": r["title"], "company": r["company"]},
                                   r["result"], confirmation="",
                                   note=f"imported from {r['source']}",
                                   applied_at=r.get("applied_at", ""))
    return {"parsed": len(recs), "added": added, "updated": updated,
            "skipped_existing": skipped, "dry_run": dry_run, "details": details}
