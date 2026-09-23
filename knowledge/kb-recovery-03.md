# 回执与效果验证的两个阶段

source_id: KB-RECOVERY-03
version: 1.0
title: 回执与效果验证的两个阶段
category: recovery
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 回执 applied verified unconfirmed

HTTP202只表示受理；MQTT PUBACK只表示Broker收到。匹配业务回执在5秒内到达才可标applied或rejected。applied后还要最多等待4秒，由新鲜遥测的设备、会话和generation核对效果，才是verified。没有证据则unconfirmed；晚回执单独保留，不改写原timed_out历史，也不自动重发。
