# 遥测静默排查

source_id: GUIDE-OFFLINE
version: 1.0

1. 核对最后样本和新鲜接收时间；离线设备的最后指标不是实时值。
2. 检查模拟器进程是否运行，是否切换到了 offline 场景。
3. 检查 MQTT Broker 与客户端连接、主题前缀及订阅日志。
4. offline 场景保留控制订阅；恢复 normal 后以新鲜遥测确认在线。真实断网需先恢复网络或进程。
