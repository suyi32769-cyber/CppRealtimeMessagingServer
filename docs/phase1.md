# 第一阶段记录

以下为早期阶段的历史记录，不能代表当前完整功能：

- 环境：WSL2 Ubuntu 内核 6.18.40.1、GCC 15.2.0、CMake 4.2.3、Git 2.53.0。
- 经授权安装 Ubuntu 软件包 redis-server 8.0.5 和 libhiredis-dev 1.2.0；系统同时创建并启用了 Redis systemd 服务链接。
- 使用 `make -C uSockets WITH_LTO=0` 构建上游 uSockets。复制官方 EchoServer 示例，仅将监听地址改为 127.0.0.1；使用真实 WebSocket 客户端观察到 HTTP 101 和 `hello` 回显。
- 使用 `cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug` 和 `cmake --build build -j2` 构建项目。
- `python3 tests/run_phase1.py` 中 SQLiteCpp 插入读取、JSON 解析、Hiredis PING/PONG、WebSocket ping/pong 和非法输入错误均通过。
- 当时测试数据库在内存中，尚未验证持久化；GoogleTest 集成、依赖全新下载、房间、认证、Redis Pub/Sub、离线恢复和最终验收当时尚未实现或验证。后续进展见 [验收记录](acceptance.md)和[服务器验证](server-validation.md)。
- WSL 当时打印了 localhost 代理/NAT 警告，但 Ubuntu 内部测试通过；该记录不证明 Windows 到 WSL 的访问可用。
