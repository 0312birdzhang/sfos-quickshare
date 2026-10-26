# SailfishOS Quick Share 0.2.2 测试包

> 0.2.2 默认使用 C++/OpenSSL 收发文件。从 runtime 1.0.0 升级时，需同时安装
> 主包与 runtime 2.0.0；后者只包含 Python 发现依赖，升级会移除旧 JRE/JAR。
> JVM 后端已彻底删除；构建和运行均无需 Java/Kotlin/Gradle。

文件：

- `sfos-quickshare-0.2.2-1.aarch64.rpm`：日常更新的服务、界面、翻译和系统分享插件。
- `sfos-quickshare-runtime-2.0.0-1.aarch64.rpm`：Python 发现依赖，不包含 JVM。

这是独立 Quick Share LAN 测试包。依赖包独立版本管理，后续主包更新无需重复下载依赖。
不用安装 AirDrop 包，也不用修改内核、Wi-Fi 驱动或系统 Java。

## 设备要求

- aarch64（ARM64）SailfishOS；已验证设备为 SailfishOS 5.2 的 Xiaomi Pad 5。
- glibc >= 2.34；32 位 armv7hl 和更老的系统不在本包支持范围。
- 双方接入可互相访问的同一局域网；有线和 Wi-Fi 可混用。
- 访客网络、AP 客户端隔离、VPN 或防火墙可能阻止发现/传输。

## 安装

把两个 RPM 放入 Downloads。首次安装或从旧版合并包升级时，必须在同一事务安装两个包。
已安装 runtime 1.0.0 的设备需要在同一事务升级至 2.0.0，之后日常只需更新主包。
如果需要终端安装并自动处理依赖：

```sh
devel-su
pkcon install-local /home/defaultuser/Downloads/sfos-quickshare-runtime-2.0.0-1.aarch64.rpm /home/defaultuser/Downloads/sfos-quickshare-0.2.2-1.aarch64.rpm
exit
```

升级前先等待当前传输完成。0.1.6 起安装/升级和卸载会自动停止 Quick Share 服务及子进程，
安装结束后恢复按需启动；无需手动重启服务。旧版遗留进程会在安装新版时停止。
安装后关闭并重新打开设置页及分享面板，让宿主应用重新加载 QML 和翻译。

无需安装 AirDrop 即可使用 Quick Share。两个独立包已无显式冲突，可与只含 AirDrop 的
`sfos-airdrop-0.4.0-1.aarch64.rpm` 共存。旧混合包 `sfos-airdrop-0.3.0`
仍拥有同名 Quick Share 文件，已有该包的设备应在同一事务把 AirDrop 升级到 0.4.0，
并安装上述两个 Quick Share 包；仅去掉冲突声明不能解决旧包的文件重叠。
Downloads 中收到的文件不会删除。

安装后重新打开系统设置和发起分享的应用。没有 Quick Share 入口时可注销后
重新登录，使 Transfer Engine 重新加载插件。

## 接收文件

1. 打开“设置 → 连接 → Quick Share”（英文系统为 Connectivity）。
2. 开启“允许接收（10 分钟）”，开关显示剩余分秒；关闭再打开页面不会重置计时。
3. 在另一台设备的 Quick Share 中选择这台 SailfishOS 设备。
4. 核对双方 PIN，在 SailfishOS 上确认接收。
5. 文件保存到 `Downloads/QuickShare/` 下的批次目录，保留文件名和后缀。

## 发送文件

1. 在另一台设备打开 Quick Share 接收/可见模式。
2. 在 SailfishOS 文件管理器或图库选择一个文件，打开系统分享菜单。
3. 选择 Quick Share，自动搜索并选择对端，核对 PIN 后由对端确认接收。
   每次打开分享面板都会自动搜索；仍有效的缓存先显示，后台刷新。
   面板可见时持续刷新；无新搜索结果超过 15 秒时清空旧列表。
   正常退出接收的对端通过 mDNS 离线通知移除，突然断网可能需要等待协议缓存过期。

发送完成、失败或取消后，设置页记录在 60 秒后自动消失；系统 Quick Share 发送记录约一分钟后移除。
不清理进行中的发送、接收记录或实际文件。

设备名优先使用系统蓝牙名称，读取不到时使用 hostname；收发双方显示一致。
修改名称后关闭再开启 Quick Share 接收，使新名称生效。

## 测试范围和限制

- 使用局域网发现和传输；不包含蓝牙发现、Wi-Fi Direct 或自动建热点。
- 不支持 iPhone 原生 AirDrop；iPhone 互通是另一个开发阶段。
- 系统分享入口本版按单文件使用；协议核心支持批次接收。
- 支持英文、简体中文、繁体中文、德语、法语和俄语，其他语言回退英文。
- 跟随系统语言；切换后重新打开设置或分享页，通知语言随页面同步。
- 底层协议的未知诊断保留原文，文件名和设备名不翻译。
- Windows 官方 Quick Share 与 C++ 后端双向收发及 0.2.1 接收误报修复已由用户确认通过。
- 原生 Android、Windows 反向发送仍需要测试者验证；受控 Linux 对端测试
  与官方客户端互通测试应分别报告，不能相互替代。

## 建议反馈

请提供设备型号、SailfishOS 版本、对端系统/Quick Share 版本、发送方向，
以及以下结果：能否发现、PIN 是否一致、能否确认、进度是否完成、文件名/后缀
和大小是否正确。建议测试 JPG、PDF、中文文件名、空文件、大文件及拒绝接收。
日志可在复现后导出（分享前自行检查是否含设备名或文件名）：

```sh
journalctl --user -u sfos-quickshare.service -b --no-pager > ~/Downloads/quickshare.log
```

## 卸载

```sh
systemctl --user stop sfos-quickshare.service
devel-su rpm -e sfos-quickshare
# 如不再使用，也可单独卸载依赖包：
# devel-su rpm -e sfos-quickshare-runtime
systemctl --user daemon-reload
```

接收文件会保留。测试包不包含任何 WLAN 内核模块或驱动修改。
