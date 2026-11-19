---
name: icims
hosts: [icims.com]
---
iCIMS 页面把表单包在 iframe #icims_content_iframe 里，且站点会剥掉 URL 的 in_iframe=1。
解法：把职位地址的 query 换成 ?mode=apply&apply=yes&in_iframe=%31（%31 就是 1，写成转义形式才不被剥），
之后表单就是主页面而非 iframe；后续每个地址都保留 in_iframe=%31。这些页永不 network idle，等 DOM 即可。

分步：Candidate Profile（建账号，含 email + 两个必勾接受框 accept_privacy/accept_gdpr）→ Candidate Questions → EEO → Job Specific Questions。
已完成的步骤显示 Completed，别动。CV 先传再填别的：控件 #PortalProfileFields.Resume_File（在 "My Computer" 后），
上传会重排页面并清空已填字段——先传后填。下拉是 iCIMS 自绘：#<id>_icimsDropdown 打开，往 aria-controls 的 input 打字，点 li#result-selectable_<id>_。

提交按钮标 "Submit"（可能是 #quesp_form_submit_i），点它即投递，无独立 review 页。
若首屏是 login.icims.com 且无 guest 路径 → 交人工，不自建账号。
