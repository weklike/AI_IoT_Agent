# 工单处理、待验证与关闭

source_id: KB-OPS-02
version: 1.0
title: 工单处理、待验证与关闭
category: ops
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 工单 处理 关闭 RESOLVED

工单依次OPEN、IN_PROGRESS、RESOLVED、CLOSED；提交待验证时必须填写处理说明。验证失败可回到处理中。关闭过温工单需要本设备新鲜且温度低于60°C，关闭离线工单需要在线且新鲜；如果关联告警仍ACTIVE，也不能关闭。所有未关闭状态共同防止重复建单，关闭后新故障可新建。
