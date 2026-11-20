"""Trade Me Jobs 扫描器 —— 双通道。

通道 A（纯 HTTP）：分类页是 JS 壳，服务端不渲染 listing（实测 119KB 零条），
  旧 v1 REST API 已下线（连接超时）。→ 保留探测，失败即抛 BrowserRequired。
通道 B（浏览器）：真实列表链接形如
  /a/jobs/{category}/{sub}/auckland/{town}/{worktype}/listing/{listingId}?rsqid=...
  由 EXTRACT_JS 在页面内提取，返回 JSON 行。

调用方：Python 侧解析 scan_trademe.py 产出的 JSON（见 extract_js()）。
"""
from __future__ import annotations
import json
import re
import urllib.request
try:
    from .schema import Job
except ImportError:  # 直接 python3 scan/xxx.py 运行时无包上下文
    from schema import Job

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
BASE = "https://www.trademe.co.nz/a/jobs"
# slug 必须是 Trade Me 真实存在的分类（2026-11-21 实测 /a/jobs/administration/auckland
# 返回 404 "The page you requested was not found"；真实 slug 是 office-administration）。
# 全部 39 个真实分类可从 /a/jobs 首页 a[href*="/a/jobs/"] 抓取。
CATEGORIES = ["office-administration", "customer-service", "education",
              "hospitality-tourism"]


class BrowserRequired(RuntimeError):
    """该渠道需要登录态/浏览器上下文，纯 HTTP 不可用。"""


EXTRACT_JS = r"""
async (category) => {
  const out = {};
  const links = [...document.querySelectorAll('a[href]')]
    .map(a => a.getAttribute('href'))
    .filter(h => h && /\/listing\/\d{9,}/.test(h));
  for (const href of links) {
    const id = (href.match(/listing\/(\d{9,})/) || [])[1];
    if (!id || out[id]) continue;
    const a = document.querySelector(`a[href*="listing/${id}"]`);
    // 锚点自身 innerText = "标题 时间 地点 描述…"（closest 卡片容器会混入广告位，勿用）
    const text = (a ? a.innerText : '').replace(/\s+/g, ' ').trim();
    out[id] = {
      id,
      title: text.slice(0, 120),
      url: 'https://www.trademe.co.nz' + href.split('?')[0],
    };
  }
  return Object.values(out);
}
"""


def probe(category: str = "customer-service", region: str = "auckland") -> None:
    """探测 HTTP 通道；当前 Trade Me 必然抛 BrowserRequired。"""
    req = urllib.request.Request(f"{BASE}/{category}/{region}",
                                headers={"User-Agent": UA, "Accept-Language": "en-NZ,en;q=0.9"})
    with urllib.request.urlopen(req, timeout=25) as resp:
        html = resp.read().decode("utf-8", "replace")
    ids = list(dict.fromkeys(re.findall(r"listing/(\d{9,})", html)))
    if not ids:
        raise BrowserRequired(
            f"Trade Me {category}/{region}: 服务端不渲染 listing，需浏览器通道（用 EXTRACT_JS）")
    return ids


TIME_RE = (r"(?:Listed\s+)?(?:\d+\s*(?:minutes?|hours?|days?|weeks?)\s+ago"
           r"|yesterday|today|Just now)")
AREA_RE = (r"([A-Z][\w&,\' -]{2,40}?(?:"
           r"Auckland|Wellington|Christchurch|Manukau City|Franklin|Rodney|"
           r"North Shore|Waitakere|Papakura|Albany|Peninsula|Northland|Hamilton|Tauranga))")
SALARY_RE = re.compile(r"\$\d[\d,.]+(?:\s*(?:an?|per)\s*(?:hour|week|year|annum|hr|wk))?")


def parse_browser_payload(rows: list[dict], category: str, region: str = "Auckland") -> list[Job]:
    """把浏览器通道返回的卡片文本拆成统一 Job。

    Trade Me 卡片整段挤在锚点 innerText 里，实测形态：
      "Night Shift Administrator Listed yesterday Manukau City, Auckland <描述…>"
      "Customer Service - Portables 4 days ago Auckland City, Auckland <描述…>"
    公司名卡片不给，留空（详情页/enrich 再补）；描述填进 description 供打分用。
    """
    jobs: list[Job] = []
    for r in rows:
        text = re.sub(r"\s+", " ", (r.get("title") or "")).strip()
        if not text:
            continue
        title, listed, loc, rest = text[:90], "", region, ""
        m_area = re.search(TIME_RE + r"\s+" + AREA_RE, text, re.I)
        if m_area:
            title = text[:m_area.start()].strip() or title
            tm = re.search(TIME_RE, text[m_area.start():m_area.end()], re.I)
            listed = tm.group(0).strip() if tm else ""
            loc = m_area.group(1).strip()
            rest = text[m_area.end():].strip()
        else:
            m_t = re.search(TIME_RE, text, re.I)
            if m_t:
                title = text[:m_t.start()].strip() or title
                listed = m_t.group(0).strip()
                rest = text[m_t.end():].strip()
            # 无时间戳的卡片多半是推广位/非常规卡，保持原样，
            # 不做宽泛地点匹配（实测会把 "Customer Service Administrator Rodney, Auckland"
            # 从中间切坏成 title="Customer" loc="Service Administrator Rodney"）
        sm = SALARY_RE.search(text)
        jobs.append(Job(
            id=str(r["id"]), channel="trademe",
            title=title[:120], company="", location=loc or region,
            url=r.get("url", ""), listed=listed,
            salary=sm.group(0) if sm else "",
            description=rest[:1500],
            extra={"category": category},
        ))
    return jobs


if __name__ == "__main__":
    import sys
    cat = sys.argv[1] if len(sys.argv) > 1 else "customer-service"
    try:
        ids = probe(cat)
        print(f"[trademe] HTTP ok: {len(ids)} listings")
    except BrowserRequired as e:
        print(f"[trademe] {e}")
        print("[trademe] 用 Alma 的 browse__execute 跑 EXTRACT_JS 获取数据")
