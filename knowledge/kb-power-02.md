# 优先级功率分配与剩余预算

source_id: KB-POWER-02
version: 1.0
title: 优先级功率分配与剩余预算
category: power
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 优先级 priority 剩余

priority需要三台设备完整且不重复的顺序。预算45000W，优先顺序CHG-002、CHG-001、CHG-003且每台请求20000W时，002和001各得到20000W，003得到剩余5000W。分配不能超过请求、单台20000W额定值或站点预算。零预算时全部目标为零，没有活动会话的设备也分零。
