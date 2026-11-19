"""Indeed NZ 扫描器 —— 浏览器通道。

现实约束：RSS feedXML 已下线（404），HTML 直连被 Cloudflare 拦（403）。
与 Trade Me 同类：需要真实浏览器上下文。EXTRACT_JS 在 nz.indeed.com/search? 结果页运行。
"""
from __future__ import annotations
try:
    from .schema import Job
except ImportError:
    from schema import Job

BASE = "https://nz.indeed.com"

EXTRACT_JS = r"""
async () => {
  const out = {};
  document.querySelectorAll('a[jk], a[data-jk]').forEach(a => {
    const jk = a.getAttribute('jk') || a.getAttribute('data-jk');
    if (!jk || out[jk]) return;
    const card = a.closest('div[data-testid="slider_item"], .tapItem, [class*="card"]');
    const text = (card ? card.innerText : a.innerText).replace(/\s+/g, ' ').trim();
    out[jk] = { id: jk, title: text.slice(0, 160), url: 'https://nz.indeed.com' + (a.getAttribute('href') || '') };
  });
  return Object.values(out);
}
"""


def parse_browser_payload(rows: list[dict]) -> list[Job]:
    jobs: list[Job] = []
    for r in rows:
        text = (r.get("title") or "").strip()
        if not text:
            continue
        jobs.append(Job(
            id=str(r["id"]), channel="indeed_nz",
            title=text[:120], company="", location="Auckland",
            url=r.get("url", ""),
        ))
    return jobs


def probe() -> str:
    """确认 Indeed 通道状态；纯 HTTP 必然 403。"""
    import urllib.request
    req = urllib.request.Request(BASE + "/jobs?q=admin&l=Auckland",
                                 headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return f"HTTP {resp.status} — 若 200 且含 data-jk 可直接 HTTP；否则用浏览器通道"
    except Exception as e:
        code = getattr(e, "code", None)
        return f"blocked ({code or e}) — 用浏览器通道跑 EXTRACT_JS"
