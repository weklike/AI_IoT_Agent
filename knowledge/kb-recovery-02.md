# 后端重启与未知状态

source_id: KB-RECOVERY-02
version: 1.0
title: 后端重启与未知状态
category: recovery
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 后端 重启 unknown interrupted

后端重启后保留历史，但先把当前连接视为unknown，不能拿旧数据库证明在线。遗留Agent任务和未完成设备控制标记interrupted，不自动重放模型、写工具或控制命令。只有新的新鲜遥测才恢复在线。已有活动告警保留并显示评估未知，不能用历史正常温度自动清除。
