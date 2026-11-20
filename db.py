"""本地 SQLite 存储层 —— 所有数据只存 data/kiwiapply.db，绝不联网。"""
from __future__ import annotations
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

DEFAULT_DATA = Path(__file__).parent / "data"


def data_dir() -> Path:
    """运行时解析存储目录：KIWIAPPLY_DATA 可覆盖（测试隔离用，绝不写进真实库）。"""
    return Path(os.environ.get("KIWIAPPLY_DATA") or DEFAULT_DATA)


def db_path() -> Path:
    return data_dir() / "kiwiapply.db"


# 兼容旧引用（模块级默认值）
DATA = DEFAULT_DATA
DB = DEFAULT_DATA / "kiwiapply.db"


def conn() -> sqlite3.Connection:
    d, f = data_dir(), db_path()
    d.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(f)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def init_db() -> None:
    with conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS profile(
            key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS cv_files(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_type TEXT NOT NULL, filename TEXT NOT NULL,
            stored_as TEXT NOT NULL, uploaded_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs(
            id TEXT NOT NULL, channel TEXT NOT NULL,
            title TEXT, company TEXT, location TEXT, url TEXT,
            salary TEXT, worktype TEXT, listed TEXT, description TEXT,
            extra TEXT, first_seen TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'new',   -- new|shortlisted|applied|blocked|rejected|ignored
            PRIMARY KEY(id, channel));
        CREATE TABLE IF NOT EXISTS applications(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT, job_channel TEXT, job_title TEXT, job_company TEXT,
            result TEXT NOT NULL,               -- sent|blocked|external_ats|failed
            confirmation TEXT, note TEXT, applied_at TEXT NOT NULL);
        """)


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def set_profile(key: str, value: str) -> None:
    with conn() as c:
        c.execute("INSERT INTO profile(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))


def get_profile(key: str = ""):
    with conn() as c:
        if key:
            r = c.execute("SELECT value FROM profile WHERE key=?", (key,)).fetchone()
            return r["value"] if r else None
        return {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM profile")}


def upsert_jobs(jobs: list[dict]) -> int:
    """入库扫描结果，返回新增数。已存在的不覆盖 status。"""
    added = 0
    with conn() as c:
        for j in jobs:
            cur = c.execute("""INSERT INTO jobs(id,channel,title,company,location,url,salary,worktype,listed,description,extra,first_seen)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id,channel) DO NOTHING""",
                (str(j.get("id")), j.get("channel"), j.get("title"), j.get("company"), j.get("location"),
                 j.get("url"), j.get("salary"), j.get("worktype"), j.get("listed"),
                 (j.get("description") or "")[:4000], json.dumps(j.get("extra") or {}, ensure_ascii=False), now()))
            added += cur.rowcount
    return added


def jobs_list(status: str = "", channel: str = "", q: str = "", limit: int = 200) -> list[dict]:
    sql, args = "SELECT * FROM jobs WHERE 1=1", []
    if status:
        sql += " AND status=?"; args.append(status)
    if channel:
        sql += " AND channel=?"; args.append(channel)
    if q:
        sql += " AND (title LIKE ? OR company LIKE ? OR description LIKE ?)"; args += [f"%{q}%"] * 3
    sql += " ORDER BY first_seen DESC LIMIT ?"; args.append(limit)
    with conn() as c:
        return [dict(r) for r in c.execute(sql, args)]


def set_job_status(job_id: str, channel: str, status: str) -> None:
    with conn() as c:
        c.execute("UPDATE jobs SET status=? WHERE id=? AND channel=?", (status, job_id, channel))


def record_application(job: dict, result: str, confirmation: str = "", note: str = "",
                       applied_at: str = "") -> None:
    """applied_at 留空则用当前时间；从历史台账导入时必须传真实投递日期。"""
    with conn() as c:
        c.execute("""INSERT INTO applications(job_id,job_channel,job_title,job_company,result,confirmation,note,applied_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (job.get("id"), job.get("channel"), job.get("title"), job.get("company"),
             result, confirmation, note, applied_at or now()))
        c.execute("UPDATE jobs SET status=? WHERE id=? AND channel=?",
                  ("applied" if result == "sent" else "blocked", str(job.get("id")), job.get("channel")))


def stats() -> dict:
    with conn() as c:
        by_status = {r["status"]: r["n"] for r in c.execute("SELECT status, COUNT(*) n FROM jobs GROUP BY status")}
        by_channel = {r["channel"]: r["n"] for r in c.execute("SELECT channel, COUNT(*) n FROM jobs GROUP BY channel")}
        apps = {r["result"]: r["n"] for r in c.execute("SELECT result, COUNT(*) n FROM applications GROUP BY result")}
        recent = [dict(r) for r in c.execute("SELECT job_title,job_company,job_channel,result,applied_at FROM applications ORDER BY id DESC LIMIT 10")]
    return {"jobs_by_status": by_status, "jobs_by_channel": by_channel, "applications": apps, "recent_apps": recent}


def save_cv(role_type: str, filename: str, content: bytes) -> str:
    up = data_dir() / "uploads"
    up.mkdir(exist_ok=True)
    safe = f"{role_type}_{filename}".replace("/", "_")
    (up / safe).write_bytes(content)
    with conn() as c:
        c.execute("INSERT INTO cv_files(role_type,filename,stored_as,uploaded_at) VALUES(?,?,?,?)",
                  (role_type, filename, safe, now()))
    return safe


def cv_list() -> list[dict]:
    with conn() as c:
        return [dict(r) for r in c.execute("SELECT * FROM cv_files ORDER BY id DESC")]
