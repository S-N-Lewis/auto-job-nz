# kiwileap 🥝

> 几维鸟是新西兰唯一不会飞的鸟。**kiwileap** 帮你跃一次。

**新西兰求职工具箱** —— NZ 五渠道聚合扫描 × 本地常用 ATS 知识插件 × 投递台账。

求职不是投得多，是投得准、跟得住。kiwiapply 把新西兰求职市场的真实渠道（SEEK、Trade Me Jobs、LinkedIn、天维网华人论坛、Indeed NZ）和本地雇主最常用的 ATS（Dayforce、PageUp、SmartRecruiters、QJumpers、SuccessFactors、iCIMS…）收进一套工具，帮你把每个新岗位在几分钟内扫到、去重、打分、跟踪。

## 为什么又一个求职工具？

现有开源方案都是美国/印度中心：
- [JobSpy](https://github.com/speedyapply/JobSpy)（MIT）能抓 SEEK，但没有 Trade Me / Skykiwi，不懂 NZ 渠道全貌
- [AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent)（MIT）ATS 插件最全，但没有 Dayforce / PageUp / QJumpers——这些恰恰是 NZ/澳洲雇主的主流系统
- [job-ops](https://github.com/DaKheera47/job-ops) 聚合+定制+追踪做得漂亮，但数据源零 NZ 覆盖

kiwiapply = **NZ 渠道 × 本地 ATS × 工作签证知识**（工作权利怎么答、PSWV 时间线、季节岗日历）。

## 全自动一体化：七步闭环（agent 无关）

把仓库发给任何能跑 shell 的 AI agent（Claude Code / Codex / Cursor / Alma…），它读 `AGENTS.md` 就能驱动完整求职循环——工具提供知识+数据+账本，执行引擎用用户自己的 agent：

```
① 需求了解   onboard：资料 + 分版简历（首次）
② 确定方案   plan：赛道/关键词/区域/薪资底线，存 data/plan.json
③ 数据分析   scan 全渠道入库 → next 按方案打分排序（双语/特教自动加权）
④ 确认投递   confirm/reject（reject 原因自动进经验库）
⑤ 投递归档   gate 强制查重 → 读 apply/plugins/<ats>.md 执行 → record 回执号
⑥ 数据复盘   review：漏斗 + 各渠道/ATS/赛道转化率
⑦ 经验沉淀   lessons → data/lessons.md；下轮 ② 前必读并优化 plan
```

第 ⑦→② 的回环是复利引擎：每轮投递都让下一轮的方案更准。所有状态走 CLI + SQLite，不绑定任何 agent 框架。

## 设计哲学（三条红线）

1. **辅助，不冒充**。默认 dry-run；reCAPTCHA/验证码永远交给人；不自建账号。招聘方能识别低质量自动投递，批量 spam 只会毁掉账号和名声。
2. **ATS 知识是文档不是代码**。每个 ATS 的表单结构、陷阱、止损点写成 markdown 插件（`apply/plugins/*.md`），LLM agent 读了执行。ATS 改版改文档，不改代码。
3. **投前查重、投后归档**。台账（ledger.jsonl）是强制环节：同一岗位不重复投，每投一单必有记录，周报自动生成。

## 快速开始

```bash
git clone https://github.com/<you>/kiwiapply && cd kiwiapply
python3 tests_smoke.py          # 一键自检（8 项，验证环境与网络）
python3 server.py               # 打开本地面板 → http://127.0.0.1:8787
```

**第一次使用**：面板会自动弹出引导（填资料 + 按岗位类型上传分版简历），全部只写入本机
`data/kiwiapply.db`（SQLite）与 `data/uploads/`。之后点「扫描新岗位」即可：SEEK/天维网
纯 HTTP 直扫入库，岗位列表里可收藏 ★、标记已投 ✓（填回执号）、忽略 ✕，天维岗位一键
提取帖内招聘邮箱/电话。也可用命令行：`python3 cli.py scan --days 1`。

### 投递卡片（面板 🎯 按钮）

每个岗位自动识别 ATS（12 种规则 + 7 家 NZ 常见雇主映射），卡片给出：
- 该 ATS 的一句话避坑要点 + 完整插件手册（人和 agent 都能读）
- 一键复制 **agent 指令**：粘给任何 AI agent 即可按七步协议执行投递（含 gate 查重与 record 归档）
- 无 agent 的用户：打开申请页照手册手动投，回面板标"已投"

### 隐私设计

- 服务只绑定 `127.0.0.1`，不监听任何对外接口
- 所有数据（资料、简历、岗位、投递记录）只存本机 `data/`，已在 `.gitignore` 中
- 扫描请求只到公开职位页面，不携带任何个人标识
- 卸载 = 删除项目文件夹，无残留

要求：Python 3.9+，零第三方依赖（纯标准库）。

输出示例（4 秒扫完 5 组关键词 × 近 24h × Auckland）：

```
[seek] 'administration assistant': 39 条，新 12（去重 27）
=== 新岗位 26 个 ===
#00000001 | Administration Assistant (Mandarin preferred)  | Example Retail Co     | $25 – $35 per hour | 3h ago
#00000002 | Student Services Officer                       | Example Institute     | $60,000 per year   | 5h ago
```

## 架构

```
scan/    渠道扫描器 → 统一 Job schema
         seek=纯 HTTP API | skykiwi=纯 HTTP(论坛) | trademe/indeed=浏览器通道 | linkedin=roadmap
match/   三重查重（本地 ledger + 结果集内去重 + 远端 hook）
apply/   ATS markdown 插件（六段式：页面结构→字段→CV→问题→发送→成功判定）
track/   台账 ledger.jsonl + 周报
profile.example/  脱敏答案映射模板
```

## Roadmap

- [x] SEEK API 扫描器（借鉴 JobSpy 端点设计）
- [x] Trade Me 双通道（HTTP 探测 + 浏览器提取）
- [x] 6 个 NZ 主流 ATS 插件
- [x] Skykiwi 天维网渠道（华人雇主聚集地，全球工具零覆盖；自动提取帖子里的招聘邮箱/电话）
- [x] Indeed NZ（浏览器通道 + probe 自检，Cloudflare 拦纯 HTTP）
- [ ] 岗位打分（关键词 × 薪资 × 区域 × 工作权匹配）
- [ ] 周报生成 & 远端台账适配器（Notion/Google Sheets）
- [ ] LinkedIn 通道（依赖登录态，experimental）

## 免责声明

使用者需遵守各平台服务条款。本项目不提供任何绕过验证码、反爬或登录机制的方法；所有 ATS 插件知识来自公开页面的行为观察。请勿用于批量 spam。

## License

MIT © 2026 —— 感谢 [JobSpy](https://github.com/speedyapply/JobSpy) 与 [AIHawk](https://github.com/feder-cr/Jobs_Applier_AI_Agent) 的开源启发。

## 台账与查重（重要）

投递记录有两个来源：工具自己的 `record`，以及外部 markdown 台账。`gate` 查重只读 SQLite，
所以历史台账必须先吸收进来，否则已投岗位会被误判 PASS：

```bash
python3 cli.py import-ledger --dry-run   # 先看会导入什么
python3 cli.py import-ledger             # 幂等，可反复执行
```

支持表格行（表头驱动列映射）、编号列表、`SEEK #ID` 内联、ATS 链接 ID、`#ID` 形态；
投递日期取所在小节标题里的日期（不是导入时间），回音率统计才准。

## 晨扫：采集与播报解耦

```bash
python3 morning.py --days 2 --limit 10 --quiet   # 纯 Python，无 agent / 无浏览器依赖
```

结果写 `data/morning-YYYY-MM-DD.md`。推荐用 macOS launchd 每天定时跑（不依赖任何
agent 连接状态），agent 只负责读文件播报：

```bash
launchctl load ~/Library/LaunchAgents/com.kiwileap.morning.plist
```

求职约束写在 `data/plan.json` 的 `exclude_employers`，`cli.py next` 会打印过滤掉多少条
（过滤必须可见，静默失效等于没生效）。
