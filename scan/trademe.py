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
CATEGORIES = ["customer-service", "administration", "retail", "hospitality-tourism"]


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


def parse_browser_payload(rows: list[dict], category: str, region: str = "Auckland") -> list[Job]:
    """把浏览器通道返回的行转成统一 Job。"""
    jobs: list[Job] = []
    for r in rows:
        text = re.sub(r"\s+", " ", (r.get("title") or "")).strip()
        if not text:
            continue
        # 卡片文本模式："标题 N days/hours ago 地点, 区域 描述…"
        m = re.search(r"(.*?)\s+(\d+\s*(?:minutes?|hours?|days?|weeks?)\s+ago)\s+([A-Z][\w&,\' -]{2,40}?(?:Auckland|Wellington|Christchurch))", text)
        if m:
            title, listed, loc = m.group(1).strip(), m.group(2), m.group(3)
        else:
            title, listed, loc = text[:80], "", region
        sm = re.search(r"\$\d[\d,.]+(?:\s*(?:an?|per)\s*(?:hour|week|year|annum))?", text)
        jobs.append(Job(
            id=str(r["id"]), channel="trademe",
            title=title[:120], company="", location=loc or region,
            url=r.get("url", ""),
            listed=listed,
            salary=sm.group(0) if sm else "",
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
