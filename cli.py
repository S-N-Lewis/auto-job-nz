"""kiwiapply CLI —— 新西兰求职工具箱入口。

用法:
  python cli.py scan --keywords "administration assistant" --days 1 [--channel seek|trademe|all]
  python cli.py ledger --add <job_id> --result sent
"""
from __future__ import annotations
import argparse
import json
import sys

from scan.seek import scan as seek_scan
from scan.skykiwi import scan as skykiwi_scan, TYPEIDS
from match.dedupe import load_ledger, filter_new, job_key

SEEK_DEFAULT_TERMS = [
    "administration assistant",
    "student services",
    "teacher aide",
    "customer service representative",
    "receptionist",
]


def cmd_scan(args: argparse.Namespace) -> None:
    _db.init_db()
    plan = _load_plan()
    if not args.where: args.where = plan.get("where", "Auckland")
    if not args.days: args.days = plan.get("days", 1)
    ledger = load_ledger()
    all_fresh = []
    terms = [args.keywords] if args.keywords else _load_plan().get("keywords", SEEK_DEFAULT_TERMS)
    if args.channel in ("seek", "all"):
        for kw in terms:
            jobs = seek_scan(kw, where=args.where, days=args.days, max_jobs=args.max)
            fresh, dup = filter_new(jobs, ledger)
            all_fresh.extend(fresh)
            print(f"[seek] {kw!r}: {len(jobs)} 条，新 {len(fresh)}（去重 {len(dup)}）")
    if args.channel in ("skykiwi", "all"):
        for type_name, tid in TYPEIDS.items():
            jobs = skykiwi_scan(typeid=tid, days=args.days, max_jobs=args.max)
            fresh, dup = filter_new(jobs, ledger)
            all_fresh.extend(fresh)
            print(f"[skykiwi] {type_name}: {len(jobs)} 帖，新 {len(fresh)}（去重 {len(dup)}）")
    if args.channel in ("trademe", "all"):
        print("[trademe] 浏览器渠道：请由 agent 执行 scan/trademe.py EXTRACT_JS 后喂 parse_browser_payload")
    if args.channel in ("indeed", "all"):
        print("[indeed] 浏览器渠道（Cloudflare 拦 HTTP）：请由 agent 执行 scan/indeed.py EXTRACT_JS 后喂 parse_browser_payload")
    seen = set()
    uniq = []
    for j in all_fresh:
        k = job_key(j)
        if k not in seen:
            seen.add(k)
            uniq.append(j)
    print(f"\n=== 新岗位 {len(uniq)} 个（近 {args.days} 天，{args.where}）===")
    for j in sorted(uniq, key=lambda x: x.listed, reverse=True)[:40]:
        print(f"#{j.id} | {j.title[:48]:<48} | {j.company[:28]:<28} | {j.salary[:18]:<18} | {j.extra.get('dateDisplay','')}")
    out = [j.to_dict() for j in uniq]
    if args.json:
        with open(args.json, "w") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        print(f"\n[json] -> {args.json} ({len(out)} 条)")
    # 默认同步入库（面板数据源）；--no-db 关闭
    if not args.no_db:
        try:
            import db as local_db
            local_db.init_db()
            added = local_db.upsert_jobs(out)
            print(f"[db] 入库新增 {added} 条 -> data/kiwiapply.db")
        except Exception as e:
            print(f"[db] 入库跳过: {e}")


import db as _db
from pathlib import Path as _P

PLAN_FILE = _P("data/plan.json")
LESSONS_FILE = _P("data/lessons.md")


def _load_plan() -> dict:
    if PLAN_FILE.exists():
        return json.loads(PLAN_FILE.read_text())
    return {"keywords": SEEK_DEFAULT_TERMS, "where": "Auckland", "days": 1, "tracks": []}


def cmd_onboard(a):
    _db.init_db()
    if a.check:
        p = _db.get_profile() or {}
        ready = bool(p.get("name") and p.get("email"))
        print(json.dumps({"onboarded": ready, "profile_keys": sorted(p), "cvs": len(_db.cv_list())}))
        return
    for k in ("name", "email", "phone", "workrights"):
        v = getattr(a, k)
        if v:
            _db.set_profile(k, v)
    if a.tracks:
        _db.set_profile("tracks", a.tracks)
    print("profile saved (local only)")


def cmd_plan(a):
    _db.init_db()
    if a.show or not a.json:
        print(json.dumps(_load_plan(), ensure_ascii=False, indent=1))
        return
    PLAN_FILE.parent.mkdir(exist_ok=True)
    PLAN_FILE.write_text(a.json)
    print("plan saved")


def cmd_confirm(a):
    _db.init_db(); _db.set_job_status(a.job_id, a.channel, "shortlisted"); print("shortlisted")


def cmd_reject(a):
    _db.init_db(); _db.set_job_status(a.job_id, a.channel, "ignored")
    if a.reason:
        _append_lesson("rejected", f"{a.job_id}: {a.reason}")
    print("ignored" + (" (reason logged to lessons)" if a.reason else ""))


def cmd_gate(a):
    _db.init_db()
    with _db.conn() as c:
        dup_app = c.execute("SELECT * FROM applications WHERE job_id=? AND job_channel=? ORDER BY id DESC LIMIT 1", (a.job_id, a.channel)).fetchone()
        if dup_app and dup_app["result"] not in ("sent", "interview"):
            dup_app = None
        job = c.execute("SELECT * FROM jobs WHERE id=? AND channel=?", (a.job_id, a.channel)).fetchone()
        same = []
        if job:
            k = f"{_norm_key(job['company'])}|{_norm_key(job['title'])}"
            for r in c.execute("SELECT id,channel,status,company,title FROM jobs"):
                if f"{_norm_key(r['company'])}|{_norm_key(r['title'])}" == k and (r["id"], r["channel"]) != (a.job_id, a.channel) and r["status"] in ("applied", "shortlisted"):
                    same.append(dict(r))
    if dup_app:
        print("DUP: already applied (" + (dup_app["applied_at"] or "") + ", conf=" + (dup_app["confirmation"] or "-") + ")"); sys.exit(2)
    if same:
        print("DUP: same role already in pipeline via " + ", ".join(f"{s['channel']}#{s['id']}" for s in same)); sys.exit(2)
    print("PASS")


def _norm_key(s):
    import re
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())[:40]


def cmd_record(a):
    _db.init_db()
    with _db.conn() as c:
        job = dict(c.execute("SELECT * FROM jobs WHERE id=? AND channel=?", (a.job_id, a.channel)).fetchone() or {"id": a.job_id, "channel": a.channel})
    _db.record_application(job, a.result, a.confirmation or "", a.note or "")
    print(f"recorded: {a.result}")



def cmd_import_ledger(a):
    """把外部 markdown 投递台账吸收进 DB，让 gate 查重对历史记录生效。"""
    from match.ledger_import import import_ledger
    from pathlib import Path
    paths = []
    if a.files:
        paths = [Path(f) for f in a.files]
    else:
        for d in a.dirs or [Path(__file__).resolve().parent.parent / "job-applications"]:
            paths.extend(sorted(Path(d).glob("APPLIED_*.md")))
    if not paths:
        print("no ledger files found (use --dirs or --files)"); sys.exit(1)
    res = import_ledger(paths, dry_run=a.dry_run)
    tag = "DRY-RUN" if a.dry_run else "IMPORTED"
    print(f"{tag}: parsed={res['parsed']} added={res['added']} "
          f"updated={res['updated']} skipped_existing={res['skipped_existing']}")
    for line in res["details"][:a.show]:
        print(line)
    if len(res["details"]) > a.show:
        print(f"  ... {len(res['details']) - a.show} more")

def cmd_next(a):
    _db.init_db()
    plan = _load_plan()
    kws = [k.lower() for k in plan.get("keywords", [])] + [t.lower() for t in plan.get("tracks", [])]
    scored = []
    excl = [e.lower() for e in plan.get("exclude_employers", [])]
    n_excluded = 0
    for j in _db.jobs_list(status="new", limit=500):
        comp = (j["company"] or "").lower()
        if any(e.split(" (")[0] in comp for e in excl):
            n_excluded += 1
            continue
        text = (j["title"] + " " + (j["description"] or "") + " " + comp).lower()
        score = sum(1 for k in kws if k.split()[0] in text)
        if any(w in text for w in ("mandarin", "chinese", "中文", "双语", "bilingual")):
            score += 3   # 中文走廊加权
        if any(w in text for w in ("student", "international", "inclusion", "disabilit", "vision", "blind")):
            score += 2   # 特教/留学生加权
        scored.append((score, j))
    scored.sort(key=lambda x: -x[0])
    if excl:
        print(f"(exclude_employers 生效：{len(excl)} 条规则，本次过滤掉 {n_excluded} 个岗位)")
    elif not plan.get("exclude_employers", None) and plan.get("keywords"):
        print("⚠️ plan 里没有 exclude_employers 字段——若有硬性不投的雇主，请用 cli.py plan --json 补上")
    for s, j in scored[:a.limit]:
        print(f"[{s:>2}] {j['channel']}#{j['id']} | {j['title'][:52]} | {j['company'][:26]} | {j['salary'][:16]}")


def _append_lesson(kind, text):
    LESSONS_FILE.parent.mkdir(exist_ok=True)
    if not LESSONS_FILE.exists():
        LESSONS_FILE.write_text("# 本地经验库（每次求职循环前必读，复盘后追加）\n")
    from datetime import date
    with LESSONS_FILE.open("a") as f:
        f.write(f"- {date.today()} [{kind}] {text} " + chr(10))


def cmd_lessons(a):
    if a.add:
        _append_lesson(a.add_kind or "note", a.add)
        print("lesson appended")
    else:
        print(LESSONS_FILE.read_text() if LESSONS_FILE.exists() else "(暂无经验记录——第一次循环)")


def cmd_review(a):
    _db.init_db()
    st = _db.stats()
    js, apps = st["jobs_by_status"], st["applications"]
    total = sum(js.values())
    lines = ["== 投递漏斗 ==",
             f"库内岗位 {total} → 收藏 {js.get('shortlisted',0)} → 已投 {js.get('applied',0)} → 受阻 {js.get('blocked',0)}",
             f"投递结果: {apps}",
             "== 渠道分布 ==", str(st['jobs_by_channel']),
             "== 最近投递 =="]
    for r in st["recent_apps"]:
        lines.append(f"  {r['applied_at']} [{r['result']}] {r['job_title'][:40]} @ {r['job_company']} ({r['job_channel']})")
    lines.append(chr(10) + "→ 复盘后把可泛化教训写入: python3 cli.py lessons --add \"...\"")
    print(chr(10).join(lines))


def cmd_cv(a):
    _db.init_db()
    if a.add:
        role, path = a.add
        p = _P(path)
        if not p.exists():
            print(f"file not found: {path}"); sys.exit(1)
        safe = _db.save_cv(role, p.name, p.read_bytes())
        print(f"cv stored: {safe} (local data/uploads/)")
    else:
        for r in _db.cv_list():
            print(f"  [{r['role_type']}] {r['filename']}")


def cmd_ats(a):
    from apply.detect import detect
    if a.job_id:
        _db.init_db()
        with _db.conn() as cn:
            row = cn.execute("SELECT * FROM jobs WHERE id=? AND channel=?", (a.job_id, a.channel)).fetchone()
        if not row:
            print("job not found"); sys.exit(1)
        row = dict(row)
        d = detect(row.get("url", ""), row.get("channel", ""))
        hint = ""
        if d.get("plugin_path"):
            try:
                hint = _P(d["plugin_path"]).read_text()[:600]
            except Exception:
                pass
        print(json.dumps({"job": row["title"], "company": row["company"], "url": row.get("url"), **d, "plugin_head": hint}, ensure_ascii=False, indent=1))
    else:
        d = detect(a.url or "")
        print(json.dumps(d, ensure_ascii=False))


def main() -> None:
    p = argparse.ArgumentParser(prog="kiwiapply")
    sub = p.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("onboard"); o.add_argument("--check", action="store_true")
    o.add_argument("--name"); o.add_argument("--email"); o.add_argument("--phone"); o.add_argument("--workrights"); o.add_argument("--tracks")
    o.set_defaults(func=cmd_onboard)
    pl = sub.add_parser("plan"); pl.add_argument("--json", default=""); pl.add_argument("--show", action="store_true")
    pl.set_defaults(func=cmd_plan)
    cn = sub.add_parser("confirm"); cn.add_argument("job_id"); cn.add_argument("--channel", default="seek"); cn.set_defaults(func=cmd_confirm)
    rj = sub.add_parser("reject"); rj.add_argument("job_id"); rj.add_argument("--channel", default="seek"); rj.add_argument("--reason", default=""); rj.set_defaults(func=cmd_reject)
    g = sub.add_parser("gate"); g.add_argument("job_id"); g.add_argument("--channel", default="seek"); g.set_defaults(func=cmd_gate)
    rc = sub.add_parser("record"); rc.add_argument("job_id"); rc.add_argument("--channel", default="seek")
    rc.add_argument("--result", required=True, choices=["sent", "blocked", "manual", "failed", "interview", "rejected"])
    rc.add_argument("--confirmation", default=""); rc.add_argument("--note", default=""); rc.set_defaults(func=cmd_record)
    nx = sub.add_parser("next"); nx.add_argument("--limit", type=int, default=20); nx.set_defaults(func=cmd_next)
    le = sub.add_parser("lessons"); le.add_argument("--add", default=""); le.add_argument("--add-kind", default=""); le.set_defaults(func=cmd_lessons)
    rv = sub.add_parser("review"); rv.set_defaults(func=cmd_review)
    cv = sub.add_parser("cv"); cv.add_argument("--add", nargs=2, metavar=("ROLE_TYPE", "PDF_PATH")); cv.set_defaults(func=cmd_cv)
    il = sub.add_parser("import-ledger"); il.add_argument("--files", nargs="*", default=[])
    il.add_argument("--dirs", nargs="*", default=[]); il.add_argument("--dry-run", action="store_true")
    il.add_argument("--show", type=int, default=60); il.set_defaults(func=cmd_import_ledger)
    at = sub.add_parser("ats"); at.add_argument("job_id", nargs="?"); at.add_argument("--channel", default="seek"); at.add_argument("--url", default=""); at.set_defaults(func=cmd_ats)
    s = sub.add_parser("scan")
    s.add_argument("--keywords", default="")
    s.add_argument("--where", default="")
    s.add_argument("--days", type=int, default=0)
    s.add_argument("--max", type=int, default=100)
    s.add_argument("--channel", default="all", choices=["seek", "trademe", "skykiwi", "indeed", "all"])
    s.add_argument("--json", default="")
    s.add_argument("--no-db", action="store_true")
    s.set_defaults(func=cmd_scan)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
