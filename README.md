# PmuSim

Cross-platform PMU (Phasor Measurement Unit) master station simulator. Supports both **Q/GDW 131-2006 (V2)** and **GB/T 26865.2-2011 (V3)** protocol versions. Built with Rust, Tauri 2, and Vue 3.

[中文文档](README_CN.md)

## Download

**[Latest Release](https://github.com/kelsoprotein-lab/PmuSim/releases/latest)**

| Platform | Download |
|----------|----------|
| macOS (Apple Silicon) | [PmuSim-macos-arm64.tar.gz](https://github.com/kelsoprotein-lab/PmuSim/releases/latest/download/PmuSim-macos-arm64.tar.gz) |
| Linux (x64) | [PmuSim-linux-x64.tar.gz](https://github.com/kelsoprotein-lab/PmuSim/releases/latest/download/PmuSim-linux-x64.tar.gz) |
| Windows (x64) | [PmuSim-windows-x64.zip](https://github.com/kelsoprotein-lab/PmuSim/releases/latest/download/PmuSim-windows-x64.zip) |

## Features

- **Dual Protocol Support** — V2 (Q/GDW 131-2006) and V3 (GB/T 26865.2-2011), identical logic with version-specific port numbers and frame formats
- **Multi-Substation** — Connect to 2–10 substations simultaneously, each with independent state machines
- **Correct TCP Model** — Management pipe: master as TCP client → substation; Data pipe: substation as TCP client → master
- **Full Handshake Flow** — Request CFG-1 → Send CFG-2 Command → Send CFG-2 → Request CFG-2 → Open Data Stream
- **One-Click Handshake** — Automated full handshake sequence with a single button
- **Real-Time Data Display** — Live analog/digital values with configurable column headers from CFG-2
- **Configuration Viewer** — Parsed CFG-1/CFG-2 frames with channel names, analog units, digital masks
- **Communication Log** — TX/RX frame log with frame type identification, hex dump, and command name decoding
- **Heartbeat Monitoring** — Automatic heartbeat sending with timeout detection
- **Zero Dependencies** — Python standard library only (asyncio + tkinter)

## Protocol Support

### Frame Types

| SYNC | Frame Type | Direction |
|------|-----------|-----------|
| 0xAA0x | Data Frame | Substation → Master (data pipe) |
| 0xAA2x | CFG-1 | Substation → Master (mgmt pipe) |
| 0xAA3x | CFG-2 | Bidirectional (mgmt pipe) |
| 0xAA4x | Command | Master → Substation (mgmt pipe) |

### Commands

| Code | Command | Description |
|------|---------|-------------|
| 0x0001 | Close Data | Stop real-time data stream |
| 0x0002 | Open Data | Start real-time data stream |
| 0x0004 | Send CFG-1 | Request configuration frame 1 |
| 0x0005 | Send CFG-2 | Request configuration frame 2 |
| 0x4000 | Heartbeat | Keep-alive heartbeat |
| 0x8000 | Send CFG-2 Cmd | Notify substation before sending CFG-2 |

### Connection Model

| Pipe | TCP Role | Default Port (V2) | Default Port (V3) |
|------|----------|-------------------|-------------------|
| Management | Master = Client | 7000 | 8000 |
| Data | Master = Server | 7001 | 8001 |

### V2 vs V3 Differences

| Feature | V2 (2006) | V3 (2011) |
|---------|-----------|-----------|
| Management port | 7000 | 8000 |
| Data port | 7001 | 8001 |
| IDCODE length | 2 bytes | 8 bytes (ASCII) |
| Header field order | SYNC-SIZE-SOC-IDCODE | SYNC-SIZE-IDCODE-SOC |
| Data frame IDCODE | Not present | Present |
| Time quality | 4-bit | 8-bit |

## Tech Stack

- **Backend**: Rust + [tokio](https://tokio.rs/) (async TCP networking)
- **Frontend**: Vue 3 + TypeScript
- **Framework**: [Tauri 2](https://tauri.app/) (desktop application)
- **Protocol**: CRC-CCITT (polynomial 0x1021, init 0x0000)
- **Encoding**: GBK string support via [encoding_rs](https://crates.io/crates/encoding_rs)

## Project Structure

```
PmuSim/
├── Cargo.toml                       # Workspace root
├── crates/
│   ├── pmusim-core/                 # Protocol library (no Tauri dependency)
│   │   └── src/
│   │       ├── error.rs             # PmuError enum
│   │       ├── time_utils.rs        # SOC/FRACSEC conversion
│   │       └── protocol/
│   │           ├── constants.rs     # SYNC, FrameType, Cmd, ProtocolVersion
│   │           ├── crc16.rs         # CRC-CCITT (poly=0x1021, init=0x0000)
│   │           ├── frame.rs         # CommandFrame, ConfigFrame, DataFrame
│   │           ├── parser.rs        # bytes → Frame (V2/V3)
│   │           └── builder.rs       # Frame → bytes (V2/V3)
│   └── pmusim-app/                  # Tauri desktop application
│       └── src/
│           ├── main.rs              # Tauri app entry
│           ├── commands.rs          # Tauri IPC command handlers
│           ├── events.rs            # PmuEvent → frontend
│           ├── state.rs             # AppState
│           └── network/
│               ├── master.rs        # MasterStation (tokio TCP)
│               └── session.rs       # SubStationSession state machine
└── frontend/                        # Vue 3 SPA
    └── src/
        ├── App.vue                  # Root layout
        ├── types/index.ts           # TypeScript interfaces
        ├── composables/             # usePmuEvents, useSessions, useCommLog
        └── components/
            ├── ToolbarPanel.vue     # Start/Stop, protocol, port
            ├── StationListPanel.vue # Station list, connect, actions
            ├── ConfigTab.vue        # CFG viewer
            ├── DataTab.vue          # Real-time data table
            └── LogTab.vue           # Communication log + hex dump
```

## Development

### Prerequisites

- [Rust](https://rustup.rs/) (stable)
- [Node.js](https://nodejs.org/) (v18+)
- [Tauri CLI](https://tauri.app/start/prerequisites/)

### Dev Mode

```bash
cd frontend && npm install
cd ../crates/pmusim-app && cargo tauri dev
```

### Run Tests

```bash
cargo test --workspace
```

### Build

```bash
cd frontend && npm run build
cd ../crates/pmusim-app && cargo tauri build
```

## License

MIT

## Author

[kelsoprotein-lab](https://github.com/kelsoprotein-lab)
