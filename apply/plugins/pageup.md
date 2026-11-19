---
name: pageup
hosts: [pageuppeople.com]
---
PageUp 是老式 ASP 多页表单：每节整页 POST 跳转。跳节方法：向当前 form 注入 hidden input（name 形如 page1.x，值任意坐标）再 form.submit()。

个人信息页字段是"可见 -edit 文本框 + hidden 真值"双结构：Region/State、Employment status 直接对 hidden input（sState、lLKP_*）赋值即可通过必填校验。

combo 控件：button[id=qXXXX-button] 点开 → li[id=qXXXX-VAL-ID] 派发 mousedown/mouseup/click → 值写入同名 hidden。radio 题 value 形如 "Yes||52276|"，按前缀匹配。

⚠️ 已知无解坑：q_type=date 的三段日期控件（qXXXX_day/_month/_year）——LI 点击、hidden 直写、坐标键盘三种方法客户端都能显示但服务器不持久，校验永远判"未完成"。遇到就停，交人工（或选 "Immediately" 类选项避开日期控件）。

问卷节（checkForm.asp）题目 id 为 qXXXX，题干从对应 hidden 向上找含 "?" 的祖先文本再语义匹配。

After sending: 提交页若列出 "pages contain mandatory questions that need to be completed" 即有节未过，按列出的节名回去补。
