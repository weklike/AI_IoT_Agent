# 过温恢复的滞回与持续时间

source_id: KB-HEAT-03
version: 1.0
title: 过温恢复的滞回与持续时间
category: health
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 过温 恢复 滞回 连续

默认告警恢复需要温度严格低于55°C并连续保持10秒；恰好55°C不会恢复。相邻新鲜唯一样本间隔不得超过3秒。样本缺口会中断计时，失去新鲜数据只让评估变成unknown，不能当成降温。告警确认是已查看；恢复是条件解除，两者分别记录。
