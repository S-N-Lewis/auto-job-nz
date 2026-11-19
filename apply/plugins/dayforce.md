---
name: dayforce
hosts: [jobs.dayforcehcm.com]
apply_path: /apply
---
Dayforce guest 申请（无需注册）：/apply 页点 "Apply without an account"（中文界面为「无需注册即可申请」——注意按钮文本两种语言不同，匹配两个变体）。

无草稿：标签关闭或刷新即全丢。单向前进——回点顶部步骤按钮（Candidate info 等）会随机清空已填数据。

字段是 id 不是 name（#jobPostingApplication_personalInfo_email 等）。受控组件（antd/Vue）：native value setter + input/change/blur 三事件可写 state。但 NEXT 翻页会随机丢部分字段（confirmEmail、下拉最常见）——每次翻页后读 .ant-form-item-explain-error，按报错补填再翻，循环直到页面出现 questions radio。

下拉（Prefix/Preferred contact/Country/State/How did you hear）：对 .ant-form-item 按标签找 .ant-select，向 .ant-select-selector 派发 mousedown+click 打开；选项在 .ant-select-dropdown（排除 hidden 类），按 title/innerText 匹配——页面可能被浏览器翻译，选项文本要双语匹配（如 "先生" 或 "Mr"）。手机国家码 select 在 mobilePhone 字段的 parentElement 里。

简历上传必须在第一页完成（page.locator('input[type=file]').setInputFiles）；file input 被 React 消费后 files.length 归零是正常现象，看页面是否显示文件名。

问卷每页 1-5 题，radio name 含 questions,N。按每题 closest('.ant-form-item') 的题干文本做语义匹配（用整页文本会串题）：visa→Yes；physical demands/fit for work→Yes；pre-existing injury/medical→No；criminal→No；年龄确认→Yes。条款弹窗（行为准则）只勾 checkbox，不要点它的保存按钮——会重置整个表单。

最终 Submit 步有 Google reCAPTCHA v2（"我不是机器人"）。不要尝试绕过，交给人完成。

After sending: URL 含 /apply/success 且页面出现 "Congratulations, your application has been submitted. Confirmation number: XXXX" —— 记录回执号进台账。
