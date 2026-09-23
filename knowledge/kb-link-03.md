# 重复乱序与保留消息不能刷新在线

source_id: KB-LINK-03
version: 1.0
title: 重复乱序与保留消息不能刷新在线
category: link
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 重复 乱序 retained 重放

遥测按全局message_id以及设备、boot_id、seq组合去重。同键不同业务内容是conflict，不能覆盖原值。合法旧样本可进入历史，但当前快照只采用严格更新的ts。重复、乱序、重放和MQTT retained消息不得刷新在线时间；Broker连接成功也不代表已有实时数据。
