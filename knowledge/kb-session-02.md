# 电量积分、表底与瓦时单位

source_id: KB-SESSION-02
version: 1.0
title: 电量积分、表底与瓦时单位
category: session
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 电量 积分 表底 Wh

模拟器用实际经过的单调时间积分功率，并保留整数余数，避免每次采样向下取整造成累计损失。20kW持续600秒的精确电量是3333.333…Wh，整数显示3333Wh，即3.333kWh。会话电量等于结束表底减起始表底；重复报告不能再次相加。变功率必须分段积分。
