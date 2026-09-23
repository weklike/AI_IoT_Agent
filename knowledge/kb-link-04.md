# MQTT断连后的遥测与报告恢复

source_id: KB-LINK-04
version: 1.0
title: MQTT断连后的遥测与报告恢复
category: link
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 断连 MQTT 缺报 Broker

Broker断开时，已有模拟会话继续在设备本地计量。重连后不补造缺失遥测，也不重放旧点维持在线。会话报告有明确的持久化投递机制，可在恢复连接后给出累计表底差；这与遥测曲线的缺口并不矛盾。需要检查Broker连通性、主题前缀和独立客户端订阅状态。
