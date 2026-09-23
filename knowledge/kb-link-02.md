# 在线状态与数据新鲜度的区别

source_id: KB-LINK-02
version: 1.0
title: 在线状态与数据新鲜度的区别
category: link
applicable_model: SIM-CHG-V2
source_kind: authored_simulation
source_url: null
license_note: 项目自写模拟系统说明；不代表真实厂商维修资料。
tags: 在线 新鲜 过期 stale

样本年龄不超过10秒，且当前后端进程已经收到新鲜样本，才有data_fresh=true。最后新鲜接收之后超过15秒才判offline，因此online与数据新鲜不是一回事。过期指标仍可展示，但必须带最后样本时间并明确不是实时值。没有本进程新鲜接收记录时连接状态是unknown。
