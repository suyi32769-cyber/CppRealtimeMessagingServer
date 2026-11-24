# 第三方组件及许可证

依赖源码目录中保留了各组件原有的许可证和版权声明。分发源码或二进制文件时，请查阅相应上游声明。

| 组件 | 固定版本 | 许可证 | 用途 |
| --- | --- | --- | --- |
| [uWebSockets](https://github.com/uNetworking/uWebSockets) | 05e6c8b55b4d28293cf23570f0f61318f8600560 | Apache-2.0（具体文件以其上游声明为准） | WebSocket |
| [uSockets](https://github.com/uNetworking/uSockets) | 86097c490263ab662d62e8e7b541390bdec7d149 | Apache-2.0，详见上游声明 | uWebSockets 网络依赖 |
| [SQLiteCpp](https://github.com/SRombauts/SQLiteCpp) | 7302cd30b853e2d3d4f2ae1456b01180d068681e | MIT | SQLite 访问 |
| [nlohmann/json](https://github.com/nlohmann/json) | 55f93686c01528224f448c19128836e7df245f72 | MIT | JSON |
| [Hiredis](https://github.com/redis/hiredis) | 6e0d55b3ff42a4801d756f6ebdceee21019c1e86 | BSD-3-Clause | 从固定源码构建并静态链接 |
| [GoogleTest](https://github.com/google/googletest) | a46a6012a133c7c0929fdae55b321c2fe65f3c5f | BSD-3-Clause | 单元测试 |

SQLite、zlib、Redis 及操作系统软件包具有各自的许可证；第三方源码不被视为本项目原创代码。
