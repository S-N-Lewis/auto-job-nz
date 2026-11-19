"""kiwiapply 本地面板 —— 只绑 127.0.0.1，数据不出这台电脑。

启动: python3 server.py  → http://127.0.0.1:8787
API:  /api/stats /api/jobs /api/profile /api/scan /api/status /api/cv (multipart)
"""
from __future__ import annotations
import json
import subprocess
import sys
import threading
from email.parser import BytesParser
from email.policy import HTTP
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import db

PORT = 8787
ROOT = Path(__file__).parent
_scan_lock = threading.Lock()


def parse_multipart(body: bytes, ctype: str) -> dict:
    """3.13+ 移除 cgi 后的手解：返回 {field: value} 与 {filefield: (filename, bytes)}。"""
    header = f"Content-Type: {ctype}\r\nMIME-Version: 1.0\r\n\r\n".encode()
    msg = BytesParser(policy=HTTP).parsebytes(header + body)
    fields, files = {}, {}
    for part in msg.iter_parts():
        cd = part.get("Content-Disposition", "")
        if 'name="' not in cd:
            continue
        name = cd.split('name="')[1].split('"')[0]
        if "filename=" in cd:
            fn = cd.split('filename="')[1].split('"')[0]
            if fn:
                files[name] = (fn, part.get_payload(decode=True) or b"")
        else:
            fields[name] = part.get_payload(decode=True).decode("utf-8", "replace")
    return {"fields": fields, "files": files}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 安静
        pass

    def _json(self, obj, code=200):
        data = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        qs = parse_qs(u.query)
        if u.path in ("/", "/index.html"):
            html = (ROOT / "ui" / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)
        elif u.path == "/api/stats":
            self._json(db.stats())
        elif u.path == "/api/jobs":
            self._json(db.jobs_list(
                status=(qs.get("status") or [""])[0],
                channel=(qs.get("channel") or [""])[0],
                q=(qs.get("q") or [""])[0]))
        elif u.path == "/api/profile":
            self._json(db.get_profile())
        elif u.path == "/api/cv":
            self._json(db.cv_list())
        elif u.path == "/api/ats":
            from apply.detect import detect
            jid = (qs.get("id") or [""])[0]
            ch = (qs.get("channel") or ["seek"])[0]
            with db.conn() as c:
                row = c.execute("SELECT * FROM jobs WHERE id=? AND channel=?", (jid, ch)).fetchone()
            if not row:
                self._json({"error": "job not found"}, 404)
                return
            row = dict(row)
            d = detect(row.get("url", ""), row.get("channel", ""))
            plugin_text = ""
            if d.get("plugin_path"):
                pp = ROOT / d["plugin_path"]
                if pp.exists():
                    plugin_text = pp.read_text()
            # profile 摘要（供 agent 提示词用，本机自用）
            prof = db.get_profile() or {}
            d.update({"job": row, "plugin_text": plugin_text,
                      "agent_prompt": (
                          f"你是求职执行 agent。先读 AGENTS.md 七步协议与 {d.get('plugin_path') or '(无插件)'}，"
                          f"帮我投递：{row.get('url')}（{row.get('title')} @ {row.get('company')}）。"
                          f"投前跑 python3 cli.py gate {jid} --channel {ch} 查重；"
                          f"我的信息在面板资料与 data/ 本地库；验证码/登录墙停下问我；"
                          f"成功后 python3 cli.py record {jid} --channel {ch} --result sent --confirmation <回执号>"
                      ) if d.get("plugin_path") else (
                          f"帮我手动投递并归档：{row.get('url')}（ATS 未识别）。"
                          f"投前查重：python3 cli.py gate {jid} --channel {ch}；"
                          f"投后：python3 cli.py record {jid} --channel {ch} --result sent --confirmation <回执号>"
                      )})
            self._json(d)
        elif u.path == "/api/onboarded":
            p = db.get_profile() or {}
            self._json({"onboarded": bool(p.get("name") and p.get("email")),
                        "cv_count": len(db.cv_list())})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length) if length else b""
        if u.path == "/api/profile":
            data = json.loads(body or b"{}")
            for k, v in data.items():
                if isinstance(v, str) and len(v) < 4000:
                    db.set_profile(k, v)
            self._json({"ok": True})
        elif u.path == "/api/status":
            data = json.loads(body or b"{}")
            db.set_job_status(str(data.get("id", "")), data.get("channel", ""), data.get("status", "new"))
            self._json({"ok": True})
        elif u.path == "/api/enrich":
            data = json.loads(body or b"{}")
            try:
                from scan.skykiwi import enrich
                from scan.schema import Job
                j = Job(id=str(data.get("id")), channel=data.get("channel", "skykiwi"),
                        title="", company="", location="", url=data.get("url", ""))
                j = enrich(j)
                x = j.extra or {}
                with db.conn() as c:
                    c.execute("UPDATE jobs SET description=?, extra=? WHERE id=? AND channel=?",
                              (j.description[:4000], json.dumps(x, ensure_ascii=False), str(data.get("id")), j.channel))
                self._json({"ok": True, "email": x.get("contact_email", ""), "phone": x.get("contact_phone", ""), "desc": j.description[:300]})
            except Exception as e:
                self._json({"error": str(e)[:200]}, 500)
        elif u.path == "/api/apply":
            data = json.loads(body or b"{}")
            db.record_application(data.get("job", {}), data.get("result", "sent"),
                                  data.get("confirmation", ""), data.get("note", ""))
            self._json({"ok": True})
        elif u.path == "/api/scan":
            if not _scan_lock.acquire(blocking=False):
                self._json({"error": "scan already running"}, 409)
                return
            def run():
                try:
                    r = subprocess.run([sys.executable, str(ROOT / "cli.py"), "scan",
                                        "--days", "1", "--channel", "all"],
                                       capture_output=True, text=True, timeout=300, cwd=ROOT)
                    print("[scan done]", (r.stdout or "")[-200:])
                finally:
                    _scan_lock.release()
            threading.Thread(target=run, daemon=True).start()
            self._json({"ok": True, "note": "scan started; refresh jobs in ~10s"})
        elif u.path == "/api/cv":
            ctype = self.headers.get("Content-Type", "")
            parsed = parse_multipart(body, ctype)
            role = parsed["fields"].get("role_type", "general")
            fname, content = parsed["files"].get("cv", ("cv.pdf", b""))
            if not content:
                self._json({"error": "no file"}, 400)
                return
            safe = db.save_cv(role, Path(fname).name, content)
            self._json({"ok": True, "stored_as": safe})
        else:
            self._json({"error": "not found"}, 404)


def main():
    db.init_db()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"kiwiapply 面板: http://127.0.0.1:{PORT}  (Ctrl+C 停止)")
    print("数据仅存本机 data/ 目录，服务只监听 127.0.0.1")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
