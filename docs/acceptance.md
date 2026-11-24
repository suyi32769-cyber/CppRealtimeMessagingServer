# 验收记录（2026-11-23 至 2026-11-24）

本文件保留历史测试记录，不能代替对当前版本重新运行测试。原 WSL2 环境使用 GCC 15.2.0、CMake 4.2.3、Redis 8.0.5 和 SQLite 3.46.1；云服务器环境及单独测试结果见 [服务器验证](server-validation.md)。Hiredis 1.6.0 从固定源码构建。此前云服务器隔离目录中的一次构建通过 14 项 CTest，用时 53.25 秒；后续成员功能版本另一次隔离测试通过 15 项。可使用 `cmake --build build -j2` 和 `ctest --test-dir build --output-on-failure` 复现，测试需要空闲端口。

| 验收项目 | 已观察到的证据 |
| --- | --- |
| Ubuntu 源码构建 | WSL 上 CMake 配置和构建成功；固定依赖下载和独立构建也已验证。 |
| 启动单个 WebSocket 服务 | `phase1_smoke` 从临时实例收到 HTTP 101 和 JSON pong。 |
| 客户端加入并交换消息 | `phase2_rooms` 验证认证、双向房间广播和退出。 |
| 持久化真实消息 | `phase2_rooms` 通过真实服务写入和读取消息；仓库单元测试验证数据行。 |
| 重启后读取历史 | `phase2_rooms` 使用同一数据库重启服务，读取消息和 ACK 游标。 |
| 两个真实进程 | `phase4_multi_instance` 启动两个独立进程，共用 SQLite 文件。 |
| 跨实例 Redis 消息 | `phase4_multi_instance` 在隔离端口验证双向通信；`scripts/check-demo.py` 另在实际部署的 9001/9002 上验证消息和 ACK。 |
| 离线补拉 | `phase4_multi_instance` 断开 B、通过 A 发送、重连 B、重复查询历史并确认消息。 |
| 非法 JSON | `robustness` 发送非法 JSON 后继续正常工作；协议测试包含数字溢出和字段边界。 |
| Redis 故障恢复 | `phase4_multi_instance` 停启临时 Redis，检查故障期间历史查询，并在重新订阅后验证投递。 |
| 基础自动化测试 | 覆盖仓库、数据库迁移、事件去重、协议、单/双实例、错误处理、启动、心跳和背压；成员功能增加了单独测试。 |
| Ubuntu 部署说明 | 见 README、固定依赖下载脚本及 [deployment.md](deployment.md)。 |

另一次实测中，不回复 pong 的客户端约 31.90 秒后被关闭，回复 ping 的客户端保持连接；背压测试中，不读取消息的客户端在 625 条 4 KiB 广播后被关闭，正常客户端仍可接收。这些只是单次观察，不保证固定时序。另见 [性能记录](performance.md)，包括 tmpfs 环境和早前 9p 测试失败的情况。

以上证据仅覆盖单机演示及实际测试的场景。固定演示令牌、无服务端 TLS、SQLite 与 Redis 非原子提交、Redis 无持久队列和前缀 ACK 游标都不支持宣称生产级安全、高可用或端到端严格只投递一次。
