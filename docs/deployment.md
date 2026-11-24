# Ubuntu 部署说明

按照 [README](../README.md) 安装依赖、下载固定版本源码并使用 CMake 构建。依赖源码固定到指定提交，系统软件包版本未锁定。SQLite 数据库建议放在 Linux 本地文件系统，数据库父目录必须已存在。

确认 Redis 已运行：

```sh
redis-cli ping
```

使用绝对数据库路径，在前台同时启动两个实例：

```sh
bash scripts/run-demo.sh /absolute/existing-directory/messages.db
```

脚本分别监听 `127.0.0.1:9001`、`127.0.0.1:9002`，使用本机 Redis 6379。按 Ctrl+C 结束进程。Redis 故障期间可能丢失实时转发，已持久化的消息可以通过历史查询恢复。演示令牌和协议见 [phase2.md](phase2.md)。

执行 `ctest --test-dir build --output-on-failure` 运行测试。测试使用临时数据库和独立端口，压测使用 16380、19001、19002；其他测试端口及其限制见 `CMakeLists.txt` 和测试脚本。测试不会使用已部署的 9001/9002 监听端口。

## 已部署的阿里云服务器

此前的部署源码位于 `/opt/CppRealtimeMessagingServer`，数据和日志位于 `/opt/CppRealtimeMessagingServer-data`。两个消息进程没有配置开机自启；Redis 是独立系统服务。启动状态及历史验证见 [server-validation.md](server-validation.md) 和 [server-fix-verification.md](server-fix-verification.md)。

在现有 PID 记录仍有效的情况下，可以从项目目录运行：

```sh
python3 scripts/restart-deployed.py /opt/CppRealtimeMessagingServer-data
python3 scripts/check-demo.py
```

重启脚本先核对两个进程的命令行，检测到活跃客户端时会拒绝断开；它保留数据库并追加日志。它依赖 Linux pidfd，如果进程或 PID 记录不匹配会停止操作。检查脚本会在新房间写入真实测试消息和 ACK。旧 WSL 部署曾使用 `/root/CppRealtimeMessagingServer-data`，与云服务器目录不同。

Windows 可视化界面的启动方式见 [可视化界面使用说明](可视化界面使用说明.md)。
