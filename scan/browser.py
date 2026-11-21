"""浏览器通道：通过 browse CLI 驱动真实 Chrome。

为什么需要它：Trade Me / Indeed 的分类页是 JS 壳，纯 HTTP 拿不到 listing，
必须有真实浏览器上下文。工具自己会调，不依赖上层 agent 帮它跑 JS。

⚠️ 资源归因（2026-11-21 两次实测修正）：
第一次以为是"6 个标签同时挂着"，实测发现标签其实都关干净了（残留 0）、
Chrome 总 RSS 仅 622MB。真因是这台 8GB 机器 swap 长期 ~6.3GB（Alma + WorkBuddy
+ Poki + 多个 Electron 应用顶到天花板），浏览器扫描再推 ~1GB 就压垮。
结论：**在这台机器上，任何浏览器扫描都有真实代价**，不是并发技巧能绕过的。
因此：
  1. 单标签 + 扫完立刻 page.close()（减少峰值，仍然要做）
  2. **默认关闭浏览器通道**：需要显式 --browser 或 plan.json 里 browser=on 才开
  3. 报告如实写明本次是否扫了、为什么跳过——绝不静默出空数据
"""
from __future__ import annotations
import json
import re
import shutil
import subprocess
from pathlib import Path

BROWSE = shutil.which("browse") or str(Path.home() / ".local/bin/browse")

# 熔断线：swap 超此值直接拒绝。这台机器常态 80%+，所以默认走"不启用浏览器"路径
SWAP_MAX = 0.85
# 单次扫描全局时间预算（秒）
BUDGET_DEFAULT = 150


class BrowserUnavailable(RuntimeError):
    """浏览器不可用：扩展未连接、内存紧张或超时。"""


def swap_used_ratio() -> float | None:
    """macOS swap 占用比例；取不到返回 None（不因此阻断）。"""
    try:
        r = subprocess.run(["sysctl", "-n", "vm.swapusage"],
                           capture_output=True, text=True, timeout=8)
        m = re.search(r"total = ([\d.]+)M.*used = ([\d.]+)M", r.stdout)
        if m:
            total, used = float(m.group(1)), float(m.group(2))
            return used / total if total > 0 else 0.0
    except Exception:
        pass
    return None


def browser_enabled() -> bool:
    """默认关闭：只有 data/plan.json 里 browser=true 才允许浏览器通道。"""
    try:
        plan = Path(__file__).resolve().parent.parent / "data" / "plan.json"
        if plan.exists():
            return bool(json.loads(plan.read_text()).get("browser"))
    except Exception:
        pass
    return False


def memory_ok(limit: float = SWAP_MAX) -> tuple[bool, str]:
    ratio = swap_used_ratio()
    if ratio is None:
        return True, "swap 未知（放行）"
    if ratio > limit:
        return False, f"swap 已用 {ratio:.0%} > {limit:.0%}，不启动浏览器扫描"
    return True, f"swap {ratio:.0%}"


def available(timeout: int = 20) -> bool:
    if not BROWSE or not Path(BROWSE).exists():
        return False
    try:
        r = subprocess.run([BROWSE, "status", "--json"], capture_output=True,
                           text=True, timeout=timeout)
        d = json.loads(r.stdout)
        return bool(d.get("connected") or (d.get("extension") or {}).get("connected"))
    except Exception:
        return False


def run_js(js: str, timeout: int = 90) -> str:
    """在真实浏览器执行脚本。内存不足或未连接时抛 BrowserUnavailable。"""
    if not browser_enabled():
        raise BrowserUnavailable("浏览器通道默认关闭（真实浏览器扫描有内存代价）；"
                                 "需要时在 plan.json 设 \"browser\": true")
    ok, why = memory_ok()
    if not ok:
        raise BrowserUnavailable(why)
    if not available():
        raise BrowserUnavailable("browse 扩展未连接（打开 Chrome 并连接 Alma 浏览器扩展）")
    try:
        r = subprocess.run([BROWSE, "execute", "--file", "-"], input=js,
                           capture_output=True, text=True, timeout=timeout)
    # 注意：脚本自身负责 page.close()；这里再加一层兜底由调用方的 JS 模板保证
    except subprocess.TimeoutExpired:
        raise BrowserUnavailable(f"浏览器执行超时（{timeout}s）")
    if r.returncode != 0:
        raise BrowserUnavailable((r.stderr or r.stdout).strip()[:300])
    return r.stdout


def tagged(stdout: str, tag: str) -> list[str]:
    """取 `TAG|...` 行的载荷部分。"""
    return [ln[len(tag):] for ln in stdout.splitlines() if ln.startswith(tag)]
