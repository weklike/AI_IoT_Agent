# 过温触发持续时间与采样断档

source_id: KB-HEAT-04
version: 1.0
title: 过温触发持续时间与采样断档
category: health
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 过温 触发 断档 持续

OVERHEAT的触发持续时间允许配置0至60秒，默认0秒。设置为10秒时，需要连续新鲜温度超限观测覆盖10秒。重复样本不能推进计时，乱序和超过3秒的间隔中断连续性。修改规则只作用于后续观测；已有活动告警保存原规则版本并按原恢复参数跟踪。
