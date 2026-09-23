# 会话报告的可靠投递与积压

source_id: KB-RECOVERY-04
version: 1.0
title: 会话报告的可靠投递与积压
category: recovery
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 报告 ACK 投递 积压

会话报告必须收到后端事务提交后的stored应用ACK才算交付，不能用PUBACK替代。未确认报告以1、2、4秒重发，之后每30秒检查；24小时仍未交付则保留delivery_failed。每会话最多保留起始、最新中间、最终三份待确认快照；达到100个积压会话时拒绝新start，但仍允许stop。
