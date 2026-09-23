# 中断会话的检查点电量质量

source_id: KB-SESSION-03
version: 1.0
title: 中断会话的检查点电量质量
category: session
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 中断 checkpoint 计量

模拟器崩溃重启会把旧活动会话标记为INTERRUPTED，原因是SIMULATOR_RESTART。只能使用最后原子持久化的表底，meter_quality为checkpoint；未记录区间不能精确计量。不要按停机时长估算充电，也不能把检查点值说成完整结算电量。时间和结束原因来自会话报告。
