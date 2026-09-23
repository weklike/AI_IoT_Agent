# 功率预览的有效期与控制指纹

source_id: KB-POWER-04
version: 1.0
title: 功率预览的有效期与控制指纹
category: power
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 预览 指纹 PLAN_STALE

预览保存具体分配，不发送设备控制。用户确认后才执行，预览有效期120秒。会话身份、请求功率、现有限制或站点revision改变会使预览失效，返回PLAN_STALE；单纯新message_id或温度变化不使相同控制内容失效，但新鲜度仍要满足。未知限制时禁止提升。
