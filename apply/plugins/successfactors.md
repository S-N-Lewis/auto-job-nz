---
name: successfactors
hosts: [successfactors.eu, successfactors.com]
---
SAP SuccessFactors 招聘站（careerX.successfactors.eu/careers?company=...）。

关键陷阱：从职位详情点 Apply 常直接跳 "Sign In" 登录墙。先检查是否有 guest/无需登录路径（部分配置允许），没有就停——注册账号属于人的决定，agent 不自建账号。

若表单可进：字段在深层结构里，先全量 dump 可见 input 的 label 再填；下拉选项可能是异步加载，点开等 1 秒再读。

After sending: 出现 application number / 确认页。登录墙标志：URL 含 Sign In 且只有 username/password 两个输入框。
