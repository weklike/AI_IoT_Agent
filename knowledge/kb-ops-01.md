# 告警确认与恢复是不同维度

source_id: KB-OPS-01
version: 1.0
title: 告警确认与恢复是不同维度
category: ops
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 告警 确认 恢复 acknowledged

ACTIVE表示异常条件仍存在，CLEARED表示已经有恢复证据；acknowledged_at只表示用户查看过。确认过温告警不会降温，确认离线告警不会恢复通信。持续同类异常复用一个活动告警，更新峰值和观测证据。排查时同时查看条件、确认时间、数据新鲜度和规则版本。
