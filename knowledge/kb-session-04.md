# 跨窗口会话统计与缺报告

source_id: KB-SESSION-04
version: 1.0
title: 跨窗口会话统计与缺报告
category: session
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 统计 跨窗口 缺报告

completed_session_energy_wh只汇总结束于查询窗口内的完整会话表底差，每个会话计一次。跨越窗口起点的会话如果在窗口内结束，仍按整段电量计入；这不是该自然时段实际消耗的电量。仍在进行和缺少报告的会话分别计数。没有可用计量时保留null，不把缺报告当零耗电。
