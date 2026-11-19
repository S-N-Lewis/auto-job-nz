# kiwiapply — 新西兰求职工具箱 设计文档 v0.1
（2026-11-19 调研后定稿；目标：开源到 GitHub，NZ 市场空白）

## 0. 调研结论（谁值得学、学什么）
| 项目 | ★ | 学什么 | 许可 |
|---|---|---|---|
| speedyapply/JobSpy | 4.8k | SEEK 纯 HTTP API 抓取（jobs_per_page=100、TLS 轮换、去重、分页） | MIT ✅ |
| feder-cr/AIHawk | 32.6k | ATS 知识=markdown 插件文件（prompt 不是代码）；插件六段式结构 | MIT ✅ |
| DaKheera47/job-ops | 4.2k | extractors 插件制 manifest、"辅助不代投"定位、visa sponsorship 检查 | 无许可 ❌只学思路 |
| GodsScion/auto_job_applier | 3k | （反面）纯浏览器自动化易被识别 | - |

**NZ 空白**：无任何项目聚合 Trade Me/Skykiwi/SEEK-NZ 三渠道；无 Dayforce/PageUp/SmartRecruiters/QJumpers NZ 常用 ATS 插件；无 visa 工作权答题映射。

## 1. 架构（三层）
```
kiwiapply/
├── scan/            # 渠道扫描器（每渠道一个模块，输出统一 JobPost）
│   ├── seek.py      #   ← 借鉴 JobSpy：nz.seek.com/api/jobsearch/v5/search 纯 HTTP
│   ├── trademe.py   #   页面抓取（旧 v1 API 已死，实测超时）
│   ├── linkedin.py  #   登录态浏览器通道（guest API 已收紧，如实标注）
│   ├── skykiwi.py   #   天维 fid=55 typeid 表（华人渠道，全球独一份）
│   └── indeed_nz.py
├── match/           # 去重（本地 ledger + 远端）+ 关键词/薪资/区域打分 + 工作权标注
├── apply/           # ATS 插件（markdown 知识文件，AIHawk 式六段式）
│   └── plugins/
│       ├── seek.md / dayforce.md / pageup.md / smartrecruiters.md
│       ├── qjumpers.md / successfactors.md / icims.md(引 AIHawk %31 解法)
│       └── greenhouse.md / workday.md / lever.md / jobadder.md
├── track/           # 台账（ledger.md + CSV）+ 五步归档钩子 + 周报
└── profile.example/ # 脱敏模板：答案映射表（工作权=学生签无限制等）、CV 分岗规则
```

## 2. 核心设计决策
1. **ATS 知识=markdown 插件**（AIHawk 模式）：选择器、陷阱、止损点用散文写，LLM agent 执行；代码只做扫描/去重/台账。与 Alma skill 生态天然兼容
2. **质量红线内置**（job-ops 教训）：默认 dry-run；reCAPTCHA 永远交人；单岗 3 轮止损；投前查重是 scan→match 的强制步骤
3. **NZ 专属**：工作权答题映射表（学生签/PSWV/AEWE 三种 profile）、50 城区域表、季节岗日历（11-1 圣诞零售周期）
4. **隐私铁律**：仓库永不出现真实个人信息；profile/ 全 example；文档演示用占位符
5. **许可 MIT**，README 明确致谢 JobSpy/AIHawk（MIT 可引用实现思路）

## 3. 与现有全球工具的差异声明（README 素材）
> JobSpy 能抓 SEEK 但不懂 NZ 渠道；AIHawk 能投 ATS 但没有 Dayforce/PageUp/Skykiwi；
> job-ops 能聚合但没有 NZ 数据源。kiwiapply = NZ 五渠道 × 六种本地 ATS × 工作权知识。

## 4. MVP 里程碑
- M1（本周）：scan/seek.py + scan/trademe.py 跑通真实数据，CLI 输出统一 JSON
- M2：match/ 去重+打分 + ledger 台账
- M3：apply/plugins 四篇 NZ 特色插件（dayforce/pageup/smartrecruiters/qjumpers，全部来自实战逆向）
- M4：README+文档+profile.example，开源发布
- M5（后）：skykiwi 渠道、周报、Notion 归档适配器

## 5. 风险记录
- LinkedIn 通道不稳定（guest API 时通时堵）→ 标注 experimental，不作卖点
- SEEK API 参数可能变（JobSpy 也依赖它，跟社区同步）
- 各 ATS 改版风险 → 插件是 md 文件，改起来零代码
