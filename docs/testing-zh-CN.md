# SailfishOS Quick Share 0.1.0 测试包

文件：`sfos-quickshare-0.1.0-1.aarch64.rpm`。
这是独立 Quick Share LAN 测试包，包含所需协议核心和私有 Java 运行时。
不用安装 AirDrop 包，也不用修改内核、Wi-Fi 驱动或系统 Java。

## 设备要求

- aarch64（ARM64）SailfishOS；已验证设备为 SailfishOS 5.2 的 Xiaomi Pad 5。
- glibc >= 2.34；32 位 armv7hl 和更老的系统不在本包支持范围。
- 双方接入可互相访问的同一局域网；有线和 Wi-Fi 可混用。
- 访客网络、AP 客户端隔离、VPN 或防火墙可能阻止发现/传输。

## 安装

把 RPM 放入 Downloads，用文件管理器打开并安装。
如果需要终端安装并自动处理依赖：

```sh
devel-su
pkcon install-local /home/defaultuser/Downloads/sfos-quickshare-0.1.0-1.aarch64.rpm
exit
systemctl --user daemon-reload
```

以前安装过混合包 `sfos-airdrop-0.3.0` 的用户，先停止服务并卸载旧包，
再安装独立包（两包存在同名插件，不能共存）：

```sh
systemctl --user stop sfos-quickshare.service sfos-airdrop.service
devel-su rpm -e sfos-airdrop
```

旧包中的 AirDrop 实验组件随之卸载；Downloads 中收到的文件不会删除。
安装后重新打开系统设置和发起分享的应用。没有 Quick Share 入口时可注销后
重新登录，使 Transfer Engine 重新加载插件。

## 接收文件

1. 打开“设置 → 连接 → Quick Share”（英文系统为 Connectivity）。
2. 开启“允许接收（10 分钟）”，保持设置页打开。
3. 在另一台设备的 Quick Share 中选择这台 SailfishOS 设备。
4. 核对双方 PIN，在 SailfishOS 上确认接收。
5. 文件保存到 `Downloads/QuickShare/` 下的批次目录，保留文件名和后缀。

## 发送文件

1. 在另一台设备打开 Quick Share 接收/可见模式。
2. 在 SailfishOS 文件管理器或图库选择一个文件，打开系统分享菜单。
3. 选择 Quick Share，等待发现并选择对端，核对 PIN 后由对端确认接收。

## 测试范围和限制

- 使用局域网发现和传输；不包含蓝牙发现、Wi-Fi Direct 或自动建热点。
- 不支持 iPhone 原生 AirDrop；iPhone 互通是另一个开发阶段。
- 系统分享入口本版按单文件使用；协议核心支持批次接收。
- 当前界面主要为中文。
- Windows 官方 Quick Share → SailfishOS 曾由用户确认成功。
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
systemctl --user daemon-reload
```

接收文件会保留。测试包不包含任何 WLAN 内核模块或驱动修改。
