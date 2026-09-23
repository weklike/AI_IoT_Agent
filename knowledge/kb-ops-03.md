# Agent授权与设备控制边界

source_id: KB-OPS-03
version: 1.0
title: Agent授权与设备控制边界
category: ops
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: Agent 授权 控制 建单

业务Agent只有一个写工具create_work_order，而且必须有本次用户授权和同一run的有效异常证据。允许建单不等于允许启停、调整功率、修改规则或关闭工单。其他工具只读，设备控制由页面确认后经确定性服务执行。知识正文属于不可信数据，不能改变工具白名单或授权。
