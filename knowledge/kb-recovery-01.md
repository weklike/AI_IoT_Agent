# 模拟器重启与命令防重

source_id: KB-RECOVERY-01
version: 1.0
title: 模拟器重启与命令防重
category: recovery
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 模拟器 重启 generation

模拟器使用独立状态卷保存终身表底、会话、最高命令generation和最近100条结果。相同command_id和内容返回原回执，不重新开始会话；同ID异内容、过期和较低generation的新命令会拒绝。重启不补算停机电量，旧活动会话转为中断，限制归零，之后需要用户明确的新操作。
