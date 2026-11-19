---
name: smartrecruiters
hosts: [jobs.smartrecruiters.com]
---
职位页点 "I'm interested" 进 oneclick-ui（iframe 内）。

表单字段藏在**双层 OPEN shadow DOM**（SPL-AUTOCOMPLETE > SPL-INPUT > 真 INPUT，id 相同如 spl-form-element_10）：递归遍历必须进每个 el.shadowRoot 且判断 tagName 为 INPUT 才找得到真元素，找宿主组件没用。

City 类 autocomplete 字段 native setter 无效：拿真 INPUT 的 getBoundingClientRect 坐标 → mouse.click → keyboard.type → ArrowDown+Enter 选中下拉建议（如输入城市名后选中 "City, New Zealand" 建议项）。

电话 spl-phone-field：国家码前缀内置（+64），只输入本地格式（如 "021 555 0123"）。

填值、勾隐私 checkbox、点 Submit 必须在同一次 evaluate 内完成——跨调用重渲染会丢值。Submit 藏在 spl-button 里，穿透取其 shadowRoot 内层 button 点击。

After sending: URL 变 /success 且正文含 "Application submitted!"。表单还在原地 = 未提交，读 [class*=error] 找缺失必填。
