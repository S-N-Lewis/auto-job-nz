#!/usr/bin/env python3
"""冒烟测试：全新环境一条命令自检。python3 tests_smoke.py"""
import json
import subprocess
import sys

CHECKS = [
    ("CLI scan (seek)", [sys.executable, "cli.py", "scan", "--keywords", "receptionist", "--days", "1", "--channel", "seek", "--max", "5"], "新岗位"),
    ("module -m scan", [sys.executable, "-m", "scan.seek", "admin"], "-> "),
    ("direct seek.py", [sys.executable, "scan/seek.py", "admin"], "-> "),
    ("direct trademe.py", [sys.executable, "scan/trademe.py"], "trademe"),
    ("weekly report", [sys.executable, "track/weekly.py"], ""),
    ("skykiwi scan", [sys.executable, "scan/skykiwi.py"], "-> "),
    ("indeed probe", [sys.executable, "-c", "import sys; sys.path.insert(0,'scan'); from indeed import probe; print(probe())"], "通道"),
    ("onboard check", [sys.executable, "cli.py", "onboard", "--check"], "onboarded"),
    ("plan show", [sys.executable, "cli.py", "plan", "--show"], "keywords"),
    ("next scoring", [sys.executable, "cli.py", "next", "--limit", "3"], "]"),
    ("gate seed+dup", [sys.executable, "-c",
        "import sys; sys.path.insert(0,'.'); import db; db.init_db();"
        "db.record_application({'id':'SMOKE-1','channel':'seek','title':'t','company':'c'},'sent','X'); "
        "import subprocess; r=subprocess.run([sys.executable,'cli.py','gate','SMOKE-1','--channel','seek'],capture_output=True,text=True); "
        "sys.exit(0 if 'DUP' in r.stdout and r.returncode==2 else 1)"], ""),
    ("gate pass-newid", [sys.executable, "cli.py", "gate", "SMOKE-NEVER-APPLIED", "--channel", "seek"], "PASS"),
    ("review funnel", [sys.executable, "cli.py", "review"], "漏斗"),
    ("lessons read", [sys.executable, "cli.py", "lessons"], "经验"),
    ("ats detect", [sys.executable, "cli.py", "ats", "--url", "https://careers.michaelhill.com/x"], "pageup"),
]

def main() -> int:
    failed = 0
    for name, cmd, expect in CHECKS:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            # gate 命中 DUP 按设计返回 exit 2；其余命令要求 0
            code_ok = (expect == "DUP" and r.returncode == 2) or r.returncode == 0
            ok = code_ok and (expect in (r.stdout + r.stderr))
        except Exception as e:
            ok, r = False, None
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + ("" if ok else f"\n         out: {(r.stdout + r.stderr)[:200] if r else 'exception'}"))
        failed += 0 if ok else 1
    # 离线单测：解析+查重
    try:
        from scan.trademe import parse_browser_payload
        from match.dedupe import job_key
        rows = json.loads('[{"id":"111111111","title":"Test Role 2 days ago Auckland City, Auckland desc","url":"https://x/1"}]')
        jobs = parse_browser_payload(rows, "test")
        assert len(jobs) == 1 and jobs[0].title == "Test Role" and jobs[0].listed == "2 days ago", f"parse wrong: {jobs}"
        assert job_key(jobs[0]), "empty key"
        print("  [PASS] trademe parser offline")
    except Exception as e:
        print(f"  [FAIL] trademe parser offline: {e}")
        failed += 1
    print("ALL PASS ✓" if not failed else f"{failed} FAILED")
    return 1 if failed else 0

if __name__ == "__main__":
    sys.exit(main())
