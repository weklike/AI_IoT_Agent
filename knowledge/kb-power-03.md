# 先降后升、过渡预算与部分失败

source_id: KB-POWER-03
version: 1.0
title: 先降后升、过渡预算与部分失败
category: power
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 先降后升 PARTIAL 过渡

调整功率必须先下发全部降低，并用新鲜遥测核验后，才能提升其他设备。同一阶段不同设备并行执行。每次提升按已知限制和未确认命令的最坏上界检查，保护上限是旧预算与目标预算的较大值。任一步拒绝、超时或未知就停止后续提升；PARTIAL不是全部成功，不盲重试或自动回滚。
