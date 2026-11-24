# CppRealtimeMessagingServer：实时消息服务演示

基于 C++17 的单机双进程消息演示项目，支持 WebSocket 连接、演示令牌认证、聊天室、SQLite 消息持久化与历史补拉，并通过 Redis Pub/Sub 在实例间转发消息。项目还提供 Windows 本地网页，方便观察消息和 ACK。

本项目是演示原型，不是生产级高可用系统。房间是公开的，固定演示令牌不适合作为真实认证；服务默认只监听回环地址。

## 环境与依赖

项目使用 C++17、CMake、uWebSockets/uSockets、SQLiteCpp、nlohmann/json、Hiredis、GoogleTest、Redis 和 Python 3。SQLiteCpp 使用系统 SQLite，要求版本不低于 3.38；Hiredis 1.6.0 从固定版本源码构建。各依赖来源和许可见 [LICENSES.md](LICENSES.md)。

已验证环境包括 WSL2 Ubuntu（GCC 15.2、CMake 4.2、SQLite 3.46.1、Redis 8.0.5）和阿里云 Ubuntu 24.04；服务器版本及实测记录见 [服务器验证记录](docs/server-validation.md)。

在 Ubuntu 安装依赖：

```sh
sudo apt update
sudo apt install build-essential cmake git pkg-config zlib1g-dev libsqlite3-dev redis-server python3
```

在空的 `third_party` 目录中下载固定版本依赖。脚本不会覆盖已有源码目录：

```sh
bash scripts/fetch-deps.sh
```

## 运行服务

确认本机 Redis 正在运行，可用 `redis-cli ping` 检查。两个实例使用同一个本地数据库，分别在两个终端运行：

```sh
./build/realtime_server --port 9001 --instance-id A --db /path/to/messages.db --redis-host 127.0.0.1 --redis-port 6379
./build/realtime_server --port 9002 --instance-id B --db /path/to/messages.db --redis-host 127.0.0.1 --redis-port 6379
```

也可以使用 `bash scripts/run-demo.sh /absolute/existing-directory/messages.db` 一起启动两个前台进程。实例 ID 必须不同；`--no-redis` 可用于单实例测试。数据库建议放在 Linux 本地文件系统，父目录须已存在。按 Ctrl+C 结束前台服务。

默认实例监听 `127.0.0.1:9001`；双实例分别监听 `9001` 和 `9002`。演示认证、创建房间、消息和 ACK 格式见 [消息协议](docs/phase2.md)。


## 项目文档

- [架构与边界](docs/architecture.md)
- [部署说明](docs/deployment.md)
- [消息协议](docs/phase2.md)
- [验收记录](docs/acceptance.md)
- [性能测试记录](docs/performance.md)与[服务器修复验证记录](docs/server-fix-verification.md)
- [简历描述与面试问题](docs/resume-interview.md)

服务收到 SIGINT 或 SIGTERM 后会关闭连接并回收后台线程。数据库提交和 Redis 发布不构成原子事务，未成功实时投递的消息可通过历史查询恢复；详见协议文档。
