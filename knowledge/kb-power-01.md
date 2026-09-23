# 平均分配与站点预算

source_id: KB-POWER-01
version: 1.0
title: 平均分配与站点预算
category: power
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 平均分配 equal 预算

equal策略给活动且新鲜的会话分配相同份额；达到请求功率或额定上限的设备退出，余量继续分给其他设备。三台各请求20000W、预算45000W时，每台限制15000W。分配以100W为单位，不能整分时按设备ID升序逐份分配，例如45100W得到15100、15000、15000W。
