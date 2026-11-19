"""ATS 识别：从岗位 URL/渠道 判断投递系统 → 对应插件文件 + 避坑要点。"""
from __future__ import annotations
import re
from pathlib import Path

PLUGINS = Path(__file__).parent / "plugins"

# host 片段 → (插件名, 一句话要点)
RULES = [
    (r"seek\.com|seek\.co\.nz", "seek", "站内申请；简历槽位先删满；答案按语义匹配别选第一项"),
    (r"dayforcehcm", "dayforce", "点 Apply without an account；无草稿别关标签；CV 第一页传；验证码交人"),
    (r"pageuppeople|/apply/\d+/cw", "pageup", "老 ASP 多页；日期控件可能无解→选 Immediately 或转人工"),
    (r"smartrecruiters", "smartrecruiters", "oneclick 双层 shadow；City 用键盘选建议；填+勾+提交一次做完"),
    (r"qjumpers", "qjumpers", "SurveyJS；textarea 要键盘输入；文件上传交人工；卡 SUBMIT 两轮即停"),
    (r"successfactors", "successfactors", "常跳登录墙；无 guest 路径就停，别自建账号"),
    (r"icims", "icims", "URL 加 ?mode=apply&apply=yes&in_iframe=%31 绕登录墙直进表单"),
    (r"workday", "workday", "Winnco 表单；shadow DOM；常有独立问卷步"),
    (r"lever", "lever", "简单表单；CV+封面+几问；Apply 按钮可能在新标签"),
    (r"greenhouse", "greenhouse", "标准表单；embed 时注意 iframe"),
    (r"bamboohr", "bamboohr", "字段少；下拉多；提交即成功页"),
    (r"jobadder", "jobadder", "可能需账号；视频简历常见，可跳过"),
]

# 已知用某 ATS 的雇主招聘站（点 Apply 后才跳，光看职位页域名识别不出）
EMPLOYER_ATS = [
    (r"michaelhill|richelieu", "pageup", "点 Apply 跳 pageuppeople.com 后按 pageup 插件走"),
    (r"footlocker", "icims", "点 Apply 跳 icims；用 %31 地址法绕登录墙"),
    (r"adidas", "successfactors", "点 Apply 跳 successfactors.eu，多有登录墙"),
    (r"oneschoolglobal", "dayforce", "跳 oneschoolglobal 的 Dayforce portal"),
    (r"luxottica|ray-ban|oakley", "seek", "Oakley 等经 SEEK 站内投"),
    (r"twg|thewarehouse|noelleeming", "smartrecruiters", "TWG 用 SmartRecruiters oneclick"),
    (r"accentgroup|skechers", "dayforce", "Accent Group(Skechers等)用 Dayforce guest"),
]


def detect(url: str, channel: str = "") -> dict:
    u = (url or "").lower()
    for pat, name, tip in RULES:
        if re.search(pat, u):
            plugin = PLUGINS / f"{name}.md"
            return {
                "ats": name,
                "tip": tip,
                "has_plugin": plugin.exists(),
                "plugin_path": str(plugin.relative_to(PLUGINS.parent.parent)) if plugin.exists() else "",
            }
    if channel == "skykiwi":
        return {"ats": "email", "tip": "华人论坛帖：联系方式在帖内，邮件附 CV+CL 直投", "has_plugin": False, "plugin_path": ""}
    for pat, name, tip in EMPLOYER_ATS:
        if re.search(pat, u):
            plugin = PLUGINS / f"{name}.md"
            return {"ats": name, "tip": tip, "has_plugin": plugin.exists(),
                    "plugin_path": str(plugin.relative_to(PLUGINS.parent.parent)) if plugin.exists() else ""}
    return {"ats": "unknown", "tip": "打不开就找页面上的 Apply 按钮，按其跳转域名判断 ATS", "has_plugin": False, "plugin_path": ""}
