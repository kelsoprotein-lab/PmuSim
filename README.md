# PmuSim

Cross-platform PMU (Phasor Measurement Unit) master station simulator. Supports both **Q/GDW 131-2006 (V2)** and **GB/T 26865.2-2011 (V3)** protocol versions. Built with Python and Tkinter — zero third-party dependencies.

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

- **Language**: Python 3.9+ (standard library only)
- **GUI**: Tkinter / ttk
- **Networking**: asyncio TCP (StreamReader/StreamWriter)
- **Threading**: asyncio event loop in background thread, Tkinter mainloop in main thread
- **CRC**: CRC-CCITT (polynomial 0x1021, init 0x0000)
- **Packaging**: PyInstaller

## Project Structure

```
PmuSim/
├── main.py                  # Entry point with Tk version check
├── protocol/
│   ├── constants.py         # SYNC, FrameType, Cmd, DEFAULT_PORTS
│   ├── crc16.py             # CRC-CCITT implementation
│   ├── frames.py            # CommandFrame, ConfigFrame, DataFrame
│   ├── parser.py            # Binary → frame objects (V2/V3)
│   └── builder.py           # Frame objects → binary (V2/V3)
├── network/
│   ├── session.py           # SubStationSession state machine
│   └── master.py            # MasterStation: TCP client/server, command loop
├── ui/
│   ├── app.py               # Main App window, event dispatcher
│   ├── toolbar.py           # Start/Stop, protocol selector, port config
│   ├── station_list.py      # Substation list, connect panel, action buttons
│   ├── config_panel.py      # CFG-1/CFG-2 viewer
│   ├── data_panel.py        # Real-time data table
│   └── log_panel.py         # Communication log with hex dump
├── utils/
│   └── time_utils.py        # SOC ↔ Beijing time, FRACSEC conversion
└── tests/
    ├── test_crc16.py         # CRC against 12 protocol document examples
    ├── test_parser.py        # V2/V3 command, config, data frame parsing
    ├── test_builder.py       # Round-trip build → parse verification
    ├── test_time_utils.py    # Time conversion tests
    └── test_e2e.py           # End-to-end: mock substation ↔ master station
```

## Development

### Prerequisites

- Python 3.9+
- Tkinter (usually bundled; on macOS use `brew install python-tk@3.12` for Tk 8.6+)

### Run

```bash
python3 main.py
```

On macOS with dark mode, use Homebrew Python for proper rendering:

```bash
/opt/homebrew/bin/python3.12 main.py
```

### Run Tests

```bash
python3 -m unittest discover tests -v
```

### Build Executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name PmuSim main.py
```

## License

MIT

## Author

[kelsoprotein-lab](https://github.com/kelsoprotein-lab)
