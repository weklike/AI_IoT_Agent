# 合成过温告警排查

source_id: GUIDE-OVERHEAT
version: 1.0
title: 合成过温告警排查
category: health
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 过温 OVERHEAT 排查

1. 核对设备 ID、样本时间和数据新鲜度；60 °C 是本项目演示阈值。
2. 查看最近窗口的温度和超限样本，区分当前异常与已经恢复的历史异常。
3. 可能原因包括模拟器处于 overheat 场景；若迁移到实体设备，应由专业人员核对环境、传感器与散热。
4. 需要检修时先获得本次工单授权，并关联工具数据。不能仅凭合成遥测断言具体硬件损坏。
