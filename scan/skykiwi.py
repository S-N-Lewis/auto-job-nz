"""天维网（bbs.skykiwi.com）求职招聘版块扫描器 —— 新西兰华人渠道，全球工具零覆盖。

Discuz 论坛，服务端渲染，纯 HTTP 即可（无需登录，RSS 已禁用）。
版块 fid=55（求职招聘）；分类 typeid：前台/行政=482、编辑/文职=485、销售/市场=471、其它=489。
帖子块：<tbody id="normalthread_TID"> … 标题/日期可正则。
华人雇主的联系方式（邮箱/电话）常写在帖子正文里，用 enrich() 抓首帖。
"""
from __future__ import annotations
import html as htmllib
import re
import urllib.request
try:
    from .schema import Job
except ImportError:  # 直接运行本文件
    from schema import Job

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
FORUM = "https://bbs.skykiwi.com/forum.php"
FID = 55
TYPEIDS = {"前台/行政": 482, "编辑/文职": 485, "销售/市场": 471, "其它": 489}


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", "replace")


def scan(typeid: int | None = None, days: int = 7, max_jobs: int = 100) -> list[Job]:
    url = f"{FORUM}?mod=forumdisplay&fid={FID}"
    if typeid:
        url += f"&filter=typeid&typeid={typeid}"
    html = _fetch(url)
    blocks = re.findall(r'<tbody id="normalthread_(\d{6,})">(.*?)</tbody>', html, re.S)
    jobs: list[Job] = []
    for tid, b in blocks:
        m = re.search(r'mod=viewthread[^"]*tid=' + tid + r'[^>]*>([^<]{4,90})<', b)
        title = htmllib.unescape((m.group(1) if m else "").strip())
        if not title:
            continue
        # 排除求职帖（别人找工作，不是雇主发帖）
        if re.search(r"求职|求推荐|求一份|求个|自荐|找工作|求工作", title):
            continue
        dm = re.findall(r"(\d{4}-\d{1,2}-\d{1,2})", b)
        listed = dm[-1] if dm else ""
        if days < 365 and listed:
            # 粗略日期过滤（论坛日期为发帖/最近活动时间）
            from datetime import date, timedelta
            try:
                y, mo, d = map(int, listed.split("-"))
                if date(y, mo, d) < date.today() - timedelta(days=days):
                    continue
            except ValueError:
                pass
        jobs.append(Job(
            id=tid, channel="skykiwi", title=title[:120], company="",
            location="Auckland",  # 该版块默认奥克兰为主
            url=f"{FORUM}?mod=viewthread&tid={tid}",
            listed=listed,
            extra={"typeid": typeid},
        ))
        if len(jobs) >= max_jobs:
            break
    return jobs


def enrich(job: Job) -> Job:
    """抓帖子首楼：正文、联系方式（邮箱/电话/微信）。"""
    try:
        html = _fetch(job.url)
    except Exception:
        return job
    m = re.search(r'<td class="t_f" id="postmessage_\d+">(.*?)</td>', html, re.S)
    if m:
        text = re.sub(r"<[^>]+>", " ", m.group(1))
        text = htmllib.unescape(re.sub(r"\s+", " ", text)).strip()
        job.description = text[:3000]
        email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
        phone = re.search(r"(?:02\d{7,9}|\+64\s?2\d{7,9})", text)
        if email:
            job.extra["contact_email"] = email.group(0)
        if phone:
            job.extra["contact_phone"] = phone.group(0)
    return job


if __name__ == "__main__":
    import sys
    tid = int(sys.argv[1]) if len(sys.argv) > 1 else None
    out = scan(typeid=tid)
    print(f"[skykiwi] typeid={tid} -> {len(out)} threads")
    for j in out[:10]:
        print(f"  tid={j.id} | {j.title[:52]} | {j.listed}")
