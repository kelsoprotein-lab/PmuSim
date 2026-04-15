# PmuSim: Rust + Tauri + Vue 3 Migration Design

## Context

PmuSim is a PMU master station simulator currently built with Python + Tkinter. It supports V2 (Q/GDW 131-2006) and V3 (GB/T 26865.2-2011) protocol versions.

**Why migrate:**
- All sibling projects (ModbusSim, OPCUASim, IEC104) use Rust + Tauri + Vue 3
- Tkinter has persistent rendering issues on macOS dark mode (Tk 8.5)
- Python's shared `sessions` dict has a race condition between UI and asyncio threads
- Unified tech stack reduces maintenance burden across the product family

**Scope:** 1:1 feature parity with the Python version. No new features.

## Architecture

### Project Structure

```
PmuSim/
├── Cargo.toml                  # Workspace root
├── crates/
│   ├── pmusim-core/            # Pure library: protocol + network (no Tauri dependency)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       ├── lib.rs
│   │       ├── error.rs        # PmuError enum
│   │       ├── time_utils.rs   # SOC/FRACSEC conversion
│   │       └── protocol/
│   │           ├── mod.rs
│   │           ├── constants.rs
│   │           ├── crc16.rs
│   │           ├── frame.rs
│   │           ├── parser.rs
│   │           └── builder.rs
│   └── pmusim-app/             # Tauri desktop application
│       ├── Cargo.toml
│       ├── tauri.conf.json
│       ├── build.rs
│       └── src/
│           ├── main.rs
│           ├── commands.rs     # #[tauri::command] handlers
│           ├── state.rs        # AppState (Arc<Mutex<MasterStation>>)
│           ├── events.rs       # PmuEvent enum → Tauri emit
│           └── network/
│               ├── mod.rs
│               ├── master.rs   # MasterStation (tokio TCP)
│               └── session.rs  # SubStationSession + SessionState
├── frontend/                   # Vue 3 SPA
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── src/
│       ├── App.vue
│       ├── main.ts
│       ├── types/              # TypeScript interfaces matching Rust structs
│       │   └── index.ts
│       ├── composables/        # Reactive logic
│       │   ├── usePmuEvents.ts
│       │   ├── useSessions.ts
│       │   └── useCommLog.ts
│       └── components/
│           ├── ToolbarPanel.vue
│           ├── StationListPanel.vue
│           ├── ConfigTab.vue
│           ├── DataTab.vue
│           └── LogTab.vue
├── .github/workflows/
│   └── release.yml             # Cross-platform build (tauri-action)
└── README.md
```

### Layer Separation

```
Vue 3 Frontend (renderer process)
    ↕ Tauri IPC (invoke / emit)
pmusim-app (Tauri commands + tokio runtime)
    ↕ Rust function calls
pmusim-core (protocol parsing, frame building, CRC)
```

## pmusim-core

### protocol/constants.rs

```rust
pub const SYNC_BYTE: u8 = 0xAA;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FrameType { Data = 0, Cfg1 = 2, Cfg2 = 3, Command = 4 }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProtocolVersion { V2 = 2, V3 = 3 }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Cmd {
    CloseData = 0x0001,
    OpenData = 0x0002,
    SendHdr = 0x0003,
    SendCfg1 = 0x0004,
    SendCfg2 = 0x0005,
    Heartbeat = 0x4000,
    SendCfg2Cmd = 0x8000,
    // ... other commands
}

pub fn default_ports(version: ProtocolVersion) -> (u16, u16) {
    match version {
        ProtocolVersion::V2 => (7000, 7001), // (mgmt, data)
        ProtocolVersion::V3 => (8000, 8001),
    }
}
```

### protocol/crc16.rs

CRC-CCITT with polynomial 0x1021, init 0x0000. Port the exact algorithm and all 12 test vectors from the Python version.

### protocol/frame.rs

```rust
#[derive(Debug, Clone)]
pub struct CommandFrame {
    pub version: ProtocolVersion,
    pub idcode: String,
    pub soc: u32,
    pub fracsec: u32,
    pub cmd: u16,
}

#[derive(Debug, Clone)]
pub struct ConfigFrame {
    pub version: ProtocolVersion,
    pub cfg_type: u8,        // 1 or 2
    pub idcode: String,
    pub soc: u32,
    pub fracsec: u32,
    pub meas_rate: u32,
    pub num_pmu: u16,
    pub stn: String,         // GBK decoded station name
    pub pmu_idcode: String,
    pub format_flags: u16,
    pub phnmr: u16,
    pub annmr: u16,
    pub dgnmr: u16,
    pub channel_names: Vec<String>,
    pub phunit: Vec<u32>,
    pub anunit: Vec<u32>,
    pub digunit: Vec<(u16, u16)>,
    pub fnom: u16,
    pub period: u16,
    pub d_frame: u16,
}

#[derive(Debug, Clone)]
pub struct DataFrame {
    pub version: ProtocolVersion,
    pub idcode: String,
    pub soc: u32,
    pub fracsec: u32,
    pub stat: u16,
    pub phasors: Vec<(i16, i16)>,
    pub freq: i16,
    pub dfreq: i16,
    pub analog: Vec<i16>,
    pub digital: Vec<u16>,
}
```

### protocol/parser.rs & builder.rs

- 1:1 port of Python parser/builder logic
- V2/V3 dispatch based on SYNC byte version nibble
- V2: SYNC-SIZE-SOC-IDCODE header order
- V3: SYNC-SIZE-IDCODE-SOC header order
- CRC validation on parse, CRC calculation on build

### error.rs

```rust
#[derive(Debug, thiserror::Error)]
pub enum PmuError {
    #[error("Parse error: {0}")]
    Parse(String),
    #[error("Build error: {0}")]
    Build(String),
    #[error("CRC mismatch: expected {expected:#06x}, got {actual:#06x}")]
    CrcMismatch { expected: u16, actual: u16 },
    #[error("Invalid sync byte: {0:#06x}")]
    InvalidSync(u16),
    #[error("Connection error: {0}")]
    Connection(String),
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}
```

## pmusim-app

### Tauri Commands

```rust
#[tauri::command]
async fn start_server(
    state: tauri::State<'_, AppState>,
    data_port: u16,
    protocol: String,  // "V2" or "V3"
) -> Result<(), String>

#[tauri::command]
async fn stop_server(state: tauri::State<'_, AppState>) -> Result<(), String>

#[tauri::command]
async fn connect_substation(
    state: tauri::State<'_, AppState>,
    host: String,
    port: u16,
) -> Result<(), String>

#[tauri::command]
async fn send_command(
    state: tauri::State<'_, AppState>,
    idcode: String,
    cmd: String,      // "request_cfg1", "open_data", etc.
    period: Option<u32>,
) -> Result<(), String>

#[tauri::command]
async fn auto_handshake(
    state: tauri::State<'_, AppState>,
    idcode: String,
    period: Option<u32>,
) -> Result<(), String>
```

### Events (Rust → Frontend)

```rust
#[derive(Clone, serde::Serialize)]
#[serde(tag = "type")]
enum PmuEvent {
    SessionCreated { idcode: String, peer_ip: String },
    SessionDisconnected { idcode: String },
    Cfg1Received { idcode: String, cfg: ConfigInfo },
    Cfg2Sent { idcode: String },
    Cfg2Received { idcode: String, cfg: ConfigInfo },
    StreamingStarted { idcode: String },
    StreamingStopped { idcode: String },
    DataFrame { idcode: String, data: DataInfo },
    RawFrame { idcode: String, direction: String, hex: String },
    HeartbeatTimeout { idcode: String },
    Error { idcode: String, error: String },
}
```

Frontend listens via `listen("pmu-event", callback)`.

### Network (tokio)

- `MasterStation` owns a `tokio::net::TcpListener` for data pipe
- `connect_to_substation()` uses `tokio::net::TcpStream::connect()` for management pipe
- Sessions stored in `Arc<RwLock<HashMap<String, SubStationSession>>>`
- Heartbeat loop: `tokio::spawn` with `tokio::time::interval(30s)`
- Command dispatch: `tokio::sync::mpsc` channel from Tauri commands to async tasks

### Session State Machine

```
CONNECTED → CFG1_RECEIVED → CFG2_SENT → STREAMING → DISCONNECTED
```

Same states as Python version. Transitions triggered by protocol frame exchange.

## Frontend (Vue 3)

### Component Breakdown

| Component | Responsibility |
|-----------|---------------|
| `ToolbarPanel.vue` | Start/stop server, protocol selector (V2/V3), data port input |
| `StationListPanel.vue` | Connected stations list, connect form (IP + port), action buttons |
| `ConfigTab.vue` | CFG-1/CFG-2 parsed content: basic info + analog channels + digital channels |
| `DataTab.vue` | Real-time data table with virtual scrolling, throttled updates |
| `LogTab.vue` | Communication log tree + hex dump detail panel |

### Composables

| Composable | Purpose |
|------------|---------|
| `usePmuEvents.ts` | `listen("pmu-event")` → dispatch to reactive stores |
| `useSessions.ts` | `ref<Map<string, SessionInfo>>` — reactive session state |
| `useCommLog.ts` | Ring buffer for log entries, max 1000 |

### TypeScript Types

```typescript
interface SessionInfo {
  idcode: string;
  peerIp: string;
  state: "connected" | "cfg1_received" | "cfg2_sent" | "streaming" | "disconnected";
}

interface ConfigInfo {
  cfgType: number;
  version: number;
  stn: string;
  idcode: string;
  formatFlags: number;
  period: number;
  measRate: number;
  phnmr: number;
  annmr: number;
  dgnmr: number;
  channelNames: string[];
  anunit: number[];
}

interface DataInfo {
  soc: number;
  fracsec: number;
  stat: number;
  analog: number[];
  digital: number[];
  phasors: [number, number][];
}

interface RawFrameInfo {
  idcode: string;
  direction: "send" | "recv";
  hex: string;
}
```

## CI/CD (.github/workflows/release.yml)

Replace PyInstaller workflow with tauri-action (matching ModbusSim pattern):

```yaml
strategy:
  matrix:
    include:
      - platform: macos-latest
        args: '--target aarch64-apple-darwin'
      - platform: macos-latest
        args: '--target x86_64-apple-darwin'
      - platform: ubuntu-22.04
        args: ''
      - platform: windows-latest
        args: ''
```

Steps: checkout → setup Node 22 → setup Rust stable → install Linux deps → npm install → build frontend → tauri-action release.

## Testing Strategy

### pmusim-core (Rust unit tests)

- Port all 46 Python test cases to `#[test]` functions
- CRC: 12 known-value tests from protocol docs
- Parser: V2/V3 command, config, data frame parsing
- Builder: round-trip (build → parse → verify)
- Time utils: SOC/FRACSEC conversion

### pmusim-app (integration)

- Tokio test runtime for async network tests
- Mock substation TCP server for end-to-end session flow
- Command dispatch verification

### Frontend

- Component rendering tests (optional, low priority for 1:1 migration)

## Migration Approach

1. Start with `pmusim-core`: protocol layer + tests (can verify independently)
2. Then `pmusim-app`: Tauri scaffold + network layer + commands
3. Then `frontend`: Vue 3 components one by one
4. Then CI/CD: replace PyInstaller workflow with tauri-action
5. Keep Python version in a `legacy/` branch for reference

## Verification

1. `cargo test --workspace` — all protocol tests pass
2. `cargo tauri dev` — app launches, can connect to substation
3. Manual test: connect to real/mock PMU substation, complete full handshake
4. `git tag v0.2.0 && git push origin v0.2.0` — triggers cross-platform release build
