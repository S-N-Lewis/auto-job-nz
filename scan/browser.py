"""浏览器通道：通过 browse CLI 驱动真实 Chrome。

为什么需要它：Trade Me / Indeed 的分类页是 JS 壳，纯 HTTP 拿不到 listing，
必须有真实浏览器上下文。工具自己会调，不依赖上层 agent 帮它跑 JS。

⚠️ 并发标签数是唯一真正的资源风险，不是 swap 比例。
2026-11-21 事故复盘：morning.py 一次调用里开 6 个分类标签（每个 goto+4.5s，空结果
还 reload 重试），8GB 机器上标签同时挂着 → 用户电脑卡死。
反证（同日实测）：swap 已 86% 时，单分类扫描仍 9 秒成功、标签残留 0、系统无感。
所以闸门设计为：
  1. **一次 browse execute 只开 1 个标签，扫完立刻 page.close()**（成败都关）
  2. 分类之间由调用方逐个串行发起，本模块每次只负责一个
  3. swap 只作极端熔断线（SWAP_MAX，默认 0.95）——设太低会让功能永久不可用，
     那也是一种静默失效
绝不静默返回空数据 —— 跳过/失败都写清原因。
"""
from __future__ import annotations
import json
import re
import shutil
import subprocess
from pathlib import Path

BROWSE = shutil.which("browse") or str(Path.home() / ".local/bin/browse")

# 极端熔断线：只有 swap 接近打满才拒绝（实测 86% 下单标签扫描依然安全）
SWAP_MAX = 0.95
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
