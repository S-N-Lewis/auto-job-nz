---
name: qjumpers
hosts: [qjumpersjobs.co]
---
QJumpers（新西兰 childcare/教育类雇主常用）表单 = React JSON Schema Form 头部 + SurveyJS 问卷。

SurveyJS 陷阱：textarea 用 page.fill 不进 state，必须 click + keyboard.insertText；radio 的 label 是包裹式（input.closest('label') 点击）；file 上传组件不吃 setInputFiles（UI 显示文件名但组件 state 不认）——文件环节交人工。电话字段是 intl-tel-input 美式掩码，直接 insertText 完整号码。

⚠️ 已知平台 bug：SUBMIT 校验失败时错误明细被 showErrorList:false 藏死，"Errors in form" 无定位信息，逆向到 schema 层也难修。卡 SUBMIT 两轮即止损，转人工或邮件雇主。

问卷虚拟渲染：滚动到题目才挂载，dump 前先滚全页。
