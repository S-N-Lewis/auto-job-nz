"""统一岗位记录 schema —— 所有渠道扫描器输出此结构。"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Job:
    id: str                      # 渠道内唯一 ID（SEEK job id / Trade Me listing id / tid）
    channel: str                 # seek | trademe | linkedin | skykiwi | indeed_nz
    title: str
    company: str
    location: str
    url: str
    listed: str = ""             # ISO 日期或原始文本
    salary: str = ""
    worktype: str = ""           # Full time / Part time / Casual / Contract
    description: str = ""        # 摘要或全文
    ats: str = ""                # 投递系统（扫描时留空，apply 阶段解析）
    extra: dict[str, Any] = field(default_factory=dict)

    def key(self) -> str:
        """跨渠道去重键：公司+标题规范化。"""
        import re
        norm = lambda s: re.sub(r"[^a-z0-9]+", "", (s or "").lower())[:40]
        return f"{norm(self.company)}|{norm(self.title)}|{norm(self.location)}"

    def to_dict(self) -> dict:
        return asdict(self)
