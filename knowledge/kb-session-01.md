# 开始会话后零功率的含义

source_id: KB-SESSION-01
version: 1.0
title: 开始会话后零功率的含义
category: session
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 会话 启动 零功率 start_session

开始模拟会话需要新鲜的空闲设备状态，后端产生session_id。start_session成功后限制为0W，页面应显示“已启动，等待功率计划下发”。这是为了让提高功率只有经确认的功率计划一条路径，并非硬件故障。停止会话后功率限制也归零，下一会话不会继承旧限制。
