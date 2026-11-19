---
name: kiwileap
description: kiwileap：新西兰全自动求职服务（扫描→分析→确认→投递→归档→复盘→经验沉淀）。触发词：求职、投岗位、SEEK、Trade Me、Skykiwi、Indeed、LinkedIn 扫描、ATS 投递、季节工申请、求职复盘。任何能跑 shell 的 agent 按 AGENTS.md 七步协议执行；ATS 表单知识在 apply/plugins/*.md；投递前强制 gate 查重。
metadata:
  author: "Simon.L + Alma"
  repository: "https://github.com/S-N-Lewis/kiwileap"
  version: "0.4"
---

# kiwiapply

执行协议全文在 **AGENTS.md**（必读），本文件只是入口摘要。

## 七步循环（铁律版摘要）
①onboard（资料+分版简历，只存本机 data/）→ ②plan（赛道方案，先读 data/lessons.md）→
③scan+next（全渠道扫描入库+按方案打分排序）→ ④confirm/reject（用户确认才进投递队列）→
⑤gate→apply/plugins/<ats>.md→record（查重PASS→按ATS知识执行→回执号归档）→
⑥review（漏斗复盘）→ ⑦lessons（经验沉淀，回②优化）

## 红线（违反=事故）
- 未经用户确认不投递；验证码/注册墙停下交人；不自建账号
- 投前必跑 `python3 cli.py gate <id> --channel <ch>`，DUP(exit 2) 即停
- 同表单卡 3 轮或 30 分钟止损，换路径报告
- 电话等个人数据以 profile 为准，禁止按"看起来对"的格式截位改写
- 一切产出默认 dry-run 思维：宁可停下问，不可自作主张提交

## 快速命令
```bash
python3 cli.py scan --days 1        # 全渠道扫描入库
python3 cli.py next --limit 20      # 按 plan 打分的新岗
python3 cli.py gate JOBID --channel seek && echo 可投
python3 cli.py record JOBID --channel seek --result sent --confirmation 回执号
python3 cli.py review               # 漏斗复盘
python3 server.py                   # 本地面板 http://127.0.0.1:8787
```
