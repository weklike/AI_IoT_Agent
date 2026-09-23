# 过温阈值与当前健康状态

source_id: KB-HEAT-02
version: 1.0
title: 过温阈值与当前健康状态
category: health
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 过温 阈值 健康 OVERHEAT

模拟温度达到60°C（包含60）时，具有新鲜数据的设备健康状态为overheat；59.999°C不算超限。温度阈值是本项目合成规则，不是实体产品标准。健康状态是当前观测，历史中曾超限不代表此刻仍异常。样本过期后health_state为unknown，最后数值必须同时标注样本时间。
