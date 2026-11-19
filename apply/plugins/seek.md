---
name: seek
hosts: [nz.seek.com, seek.co.nz]
apply_path: /apply
---
SEEK 申请走站内流程，界面语言跟随浏览器（NZ 常见中文界面）：按钮可能是「继续」/「提交申请」或 Continue/Submit application。页面顺序固定：Choose documents → Answer employer questions（可多页）→ Update SEEK Profile → Review and submit。成功标志：页面标题含 "Application sent"。

基本信息来自 SEEK 账户档案（姓名/邮箱/电话），不要在表单里手改档案字段——档案电话是什么投递单就是什么，投递前先核对档案。

简历槽位上限约 5 个。上传前先删旧简历腾位：GraphQL deleteResume（mutation DeleteResumeInput），token 在 localStorage 中含 auth0spajs+openid 的键的 body.access_token。必须循环删到列表里没有多余 radio 为止（最多 10 轮），只删一两个会导致上传控件卡死。上传按钮先点击才会出现 #resume-fileFile，然后 setInputFiles。

Cover letter：radio 组 name 含 coverLetter-method，选「写一封求职信/Write a cover letter」，填 textarea[id^="coverLetter-text"]。

问题页答案必须按语义匹配，禁止 fallback 到第一个选项（会答错工作权利和定罪题）。常见映射：工作权利题（NZ_Q_358 或含 work rights/visa）→ 选"学生签证无工时限制"类选项（student visa with no restrictions on work hours）；期望薪资区间题 → 按 profile 设定值；经验年限 → "超过5年/More than 5 years"；通知期（NZ_Q_13/NZ_Q_53/notice）→ "No/不用了，即刻可到"；刑事/交通定罪 → 永远选「不/No」；roster/weekend/public holiday/shift 可用性 → 「是/Yes」；获知渠道 → SEEK/寻找。

结构陷阱：自定义题的 select 不在 fieldset 里（id 形如 question-indirect_*），按 id 或选项文本匹配；select 触发用 selectedIndex + change 事件；radio 验证读 input.checked（label innerText 可能为空）。

卡在 "Answer employer questions" 循环 = 有 select 未匹配。dump 全部 select 的 id+options 逐个核对，别盲点继续。

After sending: 标题出现 "Application sent" 即成功；页面还在 Choose documents 即未提交。
