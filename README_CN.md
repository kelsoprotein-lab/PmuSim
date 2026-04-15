# PmuSim

跨平台 PMU（相量测量装置）主站模拟器。支持 **Q/GDW 131-2006 (V2)** 和 **GB/T 26865.2-2011 (V3)** 两个协议版本。基于 Python + Tkinter 构建，零第三方依赖。

[English](README.md)

## 下载

**[最新版本下载](https://github.com/kelsoprotein-lab/PmuSim/releases/latest)**

| 平台 | 下载 |
|------|------|
| macOS (Apple Silicon) | [PmuSim-macos-arm64.tar.gz](https://github.com/kelsoprotein-lab/PmuSim/releases/latest/download/PmuSim-macos-arm64.tar.gz) |
| Linux (x64) | [PmuSim-linux-x64.tar.gz](https://github.com/kelsoprotein-lab/PmuSim/releases/latest/download/PmuSim-linux-x64.tar.gz) |
| Windows (x64) | [PmuSim-windows-x64.zip](https://github.com/kelsoprotein-lab/PmuSim/releases/latest/download/PmuSim-windows-x64.zip) |

## 功能

- **双版本协议支持** — V2 (Q/GDW 131-2006) 和 V3 (GB/T 26865.2-2011)，逻辑一致，端口号和帧格式按版本区分
- **多子站连接** — 同时连接 2–10 个子站，每个子站独立状态机
- **正确的 TCP 连接模型** — 管理管道：主站作为 TCP 客户端主动连接子站；数据管道：子站作为 TCP 客户端连回主站
- **完整握手流程** — 召唤 CFG-1 → 下传 CFG-2 命令 → 下传 CFG-2 → 召唤 CFG-2 → 开启数据流
- **一键握手** — 一个按钮自动执行完整握手序列
- **实时数据显示** — 模拟量/开关量实时刷新，列头根据 CFG-2 通道名自动配置
- **配置查看器** — 解析 CFG-1/CFG-2 帧内容，显示通道名称、模拟量单位、开关量掩码
- **通信日志** — 收发帧日志，帧类型识别、十六进制转储、命令名解码
- **心跳监测** — 自动发送心跳帧，超时检测
- **零依赖** — 仅使用 Python 标准库（asyncio + tkinter）

## 协议支持

### 帧类型

| SYNC | 帧类型 | 方向 |
|------|--------|------|
| 0xAA0x | 数据帧 | 子站 → 主站（数据管道） |
| 0xAA2x | CFG-1 | 子站 → 主站（管理管道） |
| 0xAA3x | CFG-2 | 双向（管理管道） |
| 0xAA4x | 命令帧 | 主站 → 子站（管理管道） |

### 命令字

| 编码 | 命令 | 说明 |
|------|------|------|
| 0x0001 | 关闭数据 | 停止实时数据流 |
| 0x0002 | 打开数据 | 启动实时数据流 |
| 0x0004 | 召唤 CFG-1 | 请求配置帧 1 |
| 0x0005 | 召唤 CFG-2 | 请求配置帧 2 |
| 0x4000 | 心跳 | 保活心跳帧 |
| 0x8000 | 下传 CFG-2 命令 | 通知子站即将下传 CFG-2 |

### 连接模型

| 管道 | TCP 角色 | 默认端口 (V2) | 默认端口 (V3) |
|------|----------|--------------|--------------|
| 管理管道 | 主站 = 客户端 | 7000 | 8000 |
| 数据管道 | 主站 = 服务端 | 7001 | 8001 |

### V2 与 V3 差异

| 特性 | V2 (2006) | V3 (2011) |
|------|-----------|-----------|
| 管理端口 | 7000 | 8000 |
| 数据端口 | 7001 | 8001 |
| IDCODE 长度 | 2 字节 | 8 字节 (ASCII) |
| 帧头字段顺序 | SYNC-SIZE-SOC-IDCODE | SYNC-SIZE-IDCODE-SOC |
| 数据帧含 IDCODE | 不含 | 含 |
| 时间质量位 | 4 位 | 8 位 |

## 技术栈

- **语言**: Python 3.9+（仅标准库）
- **GUI**: Tkinter / ttk
- **网络**: asyncio TCP (StreamReader/StreamWriter)
- **线程模型**: asyncio 事件循环在后台线程，Tkinter mainloop 在主线程
- **CRC**: CRC-CCITT（多项式 0x1021，初始值 0x0000）
- **打包**: PyInstaller

## 项目结构

```
PmuSim/
├── main.py                  # 入口，含 Tk 版本检查
├── protocol/
│   ├── constants.py         # SYNC、FrameType、Cmd、DEFAULT_PORTS
│   ├── crc16.py             # CRC-CCITT 实现
│   ├── frames.py            # CommandFrame、ConfigFrame、DataFrame
│   ├── parser.py            # 二进制 → 帧对象（V2/V3）
│   └── builder.py           # 帧对象 → 二进制（V2/V3）
├── network/
│   ├── session.py           # SubStationSession 状态机
│   └── master.py            # MasterStation：TCP 客户端/服务端、命令循环
├── ui/
│   ├── app.py               # 主窗口，事件分发
│   ├── toolbar.py           # 启动/停止、协议选择、端口配置
│   ├── station_list.py      # 子站列表、连接面板、操作按钮
│   ├── config_panel.py      # CFG-1/CFG-2 查看器
│   ├── data_panel.py        # 实时数据表
│   └── log_panel.py         # 通信日志与十六进制转储
├── utils/
│   └── time_utils.py        # SOC ↔ 北京时间、FRACSEC 转换
└── tests/
    ├── test_crc16.py         # CRC 校验（12 个协议文档实例）
    ├── test_parser.py        # V2/V3 命令帧、配置帧、数据帧解析
    ├── test_builder.py       # 编码 → 解码往返验证
    ├── test_time_utils.py    # 时间转换测试
    └── test_e2e.py           # 端到端：模拟子站 ↔ 主站
```

## 开发

### 前置条件

- Python 3.9+
- Tkinter（通常自带；macOS 下使用 `brew install python-tk@3.12` 获取 Tk 8.6+）

### 运行

```bash
python3 main.py
```

macOS 暗色模式下，使用 Homebrew Python 以确保正常渲染：

```bash
/opt/homebrew/bin/python3.12 main.py
```

### 运行测试

```bash
python3 -m unittest discover tests -v
```

### 构建可执行文件

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name PmuSim main.py
```

## 许可证

MIT

## 作者

[kelsoprotein-lab](https://github.com/kelsoprotein-lab)
