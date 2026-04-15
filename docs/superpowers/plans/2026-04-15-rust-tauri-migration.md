# PmuSim Rust + Tauri + Vue 3 Migration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite PmuSim from Python+Tkinter to Rust+Tauri+Vue3 with 1:1 feature parity.

**Architecture:** Dual-crate Rust workspace (pmusim-core library + pmusim-app Tauri desktop app) with Vue 3 frontend. Core handles protocol parsing/building and CRC. App handles tokio TCP networking and Tauri IPC. Frontend renders UI with reactive composables.

**Tech Stack:** Rust, tokio, serde, thiserror, encoding_rs (GBK), Tauri 2, Vue 3, TypeScript, Vite, @tanstack/vue-virtual

**Reference:** Design spec at `docs/superpowers/specs/2026-04-15-rust-tauri-migration-design.md`. Python source in `protocol/`, `network/`, `ui/`, `tests/`.

---

## File Structure

### pmusim-core (protocol library)

| File | Responsibility |
|------|---------------|
| `crates/pmusim-core/Cargo.toml` | Dependencies: thiserror, encoding_rs |
| `crates/pmusim-core/src/lib.rs` | Re-exports protocol, error, time_utils modules |
| `crates/pmusim-core/src/error.rs` | `PmuError` enum |
| `crates/pmusim-core/src/time_utils.rs` | SOC↔Beijing time, FRACSEC→ms |
| `crates/pmusim-core/src/protocol/mod.rs` | Re-exports submodules |
| `crates/pmusim-core/src/protocol/constants.rs` | SYNC_BYTE, FrameType, Cmd, ProtocolVersion, ports |
| `crates/pmusim-core/src/protocol/crc16.rs` | CRC-CCITT (poly=0x1021, init=0x0000) |
| `crates/pmusim-core/src/protocol/frame.rs` | CommandFrame, ConfigFrame, DataFrame structs |
| `crates/pmusim-core/src/protocol/parser.rs` | bytes→Frame (V2/V3 dispatch) |
| `crates/pmusim-core/src/protocol/builder.rs` | Frame→bytes (V2/V3 dispatch) |

### pmusim-app (Tauri application)

| File | Responsibility |
|------|---------------|
| `crates/pmusim-app/Cargo.toml` | Dependencies: pmusim-core, tauri, tokio, serde |
| `crates/pmusim-app/tauri.conf.json` | Tauri window/bundle config |
| `crates/pmusim-app/build.rs` | Tauri build script |
| `crates/pmusim-app/src/main.rs` | Tauri app setup, register commands |
| `crates/pmusim-app/src/state.rs` | AppState wrapping MasterStation |
| `crates/pmusim-app/src/events.rs` | PmuEvent enum (serde→frontend) |
| `crates/pmusim-app/src/commands.rs` | #[tauri::command] handlers |
| `crates/pmusim-app/src/network/mod.rs` | Re-exports |
| `crates/pmusim-app/src/network/session.rs` | SubStationSession + SessionState |
| `crates/pmusim-app/src/network/master.rs` | MasterStation (tokio TCP, event emission) |

### frontend (Vue 3)

| File | Responsibility |
|------|---------------|
| `frontend/package.json` | Vue 3 + Tauri API + vite |
| `frontend/vite.config.ts` | Vite config |
| `frontend/tsconfig.json` | TypeScript config |
| `frontend/index.html` | SPA entry |
| `frontend/src/main.ts` | Vue app mount |
| `frontend/src/App.vue` | Root layout |
| `frontend/src/types/index.ts` | TS interfaces (SessionInfo, ConfigInfo, DataInfo, etc.) |
| `frontend/src/composables/usePmuEvents.ts` | Listen Tauri events → dispatch |
| `frontend/src/composables/useSessions.ts` | Reactive session map |
| `frontend/src/composables/useCommLog.ts` | Ring buffer for log entries |
| `frontend/src/components/ToolbarPanel.vue` | Start/stop, protocol, port |
| `frontend/src/components/StationListPanel.vue` | Station list + connect form + actions |
| `frontend/src/components/ConfigTab.vue` | CFG viewer |
| `frontend/src/components/DataTab.vue` | Real-time data table |
| `frontend/src/components/LogTab.vue` | Communication log + hex dump |

---

## Task 1: Workspace Scaffold + Error Types

**Files:**
- Create: `Cargo.toml` (workspace root)
- Create: `crates/pmusim-core/Cargo.toml`
- Create: `crates/pmusim-core/src/lib.rs`
- Create: `crates/pmusim-core/src/error.rs`

- [ ] **Step 1: Create workspace Cargo.toml**

```toml
[workspace]
members = ["crates/pmusim-core", "crates/pmusim-app"]
resolver = "2"
```

- [ ] **Step 2: Create pmusim-core Cargo.toml**

```toml
[package]
name = "pmusim-core"
version = "0.1.0"
edition = "2021"

[dependencies]
thiserror = "2"
encoding_rs = "0.8"
```

- [ ] **Step 3: Create error.rs**

```rust
use thiserror::Error;

#[derive(Debug, Error)]
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

pub type Result<T> = std::result::Result<T, PmuError>;
```

- [ ] **Step 4: Create lib.rs**

```rust
pub mod error;
pub mod protocol;
pub mod time_utils;
```

Note: `protocol` and `time_utils` modules will be created in subsequent tasks. Add `mod protocol;` and `mod time_utils;` stubs or comment them until those files exist.

- [ ] **Step 5: Verify it compiles**

Run: `cargo build -p pmusim-core`
Expected: Compiles with no errors (comment out missing module imports for now)

- [ ] **Step 6: Commit**

```bash
git add Cargo.toml crates/
git commit -m "feat: scaffold Rust workspace with pmusim-core crate and error types"
```

---

## Task 2: CRC-16 Implementation + Tests

**Files:**
- Create: `crates/pmusim-core/src/protocol/mod.rs`
- Create: `crates/pmusim-core/src/protocol/crc16.rs`

- [ ] **Step 1: Create protocol/mod.rs**

```rust
pub mod crc16;
```

- [ ] **Step 2: Write CRC-16 tests first**

In `crates/pmusim-core/src/protocol/crc16.rs`:

```rust
/// CRC-CCITT: polynomial 0x1021, init 0x0000
pub fn crc16(data: &[u8]) -> u16 {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_data() {
        assert_eq!(crc16(&[]), 0x0000);
    }

    #[test]
    fn v2_command_request_cfg1() {
        let data = hex::decode("aa4200146757dd1d30475830304750310004").unwrap();
        assert_eq!(crc16(&data), 0xA5CB);
    }

    #[test]
    fn v2_command_heartbeat() {
        let data = hex::decode("aa4200146757dd22304758303047503140009cf7").unwrap();
        // CRC is computed over bytes BEFORE the CRC field
        let data = hex::decode("aa4200146757dd2230475830304750314000").unwrap();
        assert_eq!(crc16(&data), 0x9CF7);
    }

    #[test]
    fn v2_command_ack() {
        let data = hex::decode("aa4200146757dd9d3047583030475031e000").unwrap();
        assert_eq!(crc16(&data), 0x7C57);
    }

    #[test]
    fn v2_command_open_data() {
        let data = hex::decode("aa4200146757dd1e30475830304750310002").unwrap();
        assert_eq!(crc16(&data), 0xBDF7);
    }

    #[test]
    fn v2_command_send_cfg2_cmd() {
        let data = hex::decode("aa4200146757dd1e30475830304750318000").unwrap();
        assert_eq!(crc16(&data), 0x862D);
    }

    #[test]
    fn v3_command_request_cfg1() {
        let data = hex::decode("aa430018304758303047503167b2c719000000000004").unwrap();
        assert_eq!(crc16(&data), 0xAC08);
    }

    #[test]
    fn v3_command_ack() {
        let data = hex::decode("aa430018304758303047503167b2c71a00000000e000").unwrap();
        assert_eq!(crc16(&data), 0x24BC);
    }

    #[test]
    fn v3_command_heartbeat() {
        let data = hex::decode("aa430018304758303047503167b2c71e000000004000").unwrap();
        assert_eq!(crc16(&data), 0xF804);
    }

    #[test]
    fn v2_data_frame() {
        let data = hex::decode(
            "aa02002c67a99d11000d94900000000000000012c0bb823d700c80000000000000000023d700000000000a"
        ).unwrap();
        assert_eq!(crc16(&data), 0x21F3);
    }

    #[test]
    fn v3_config_frame() {
        let data = hex::decode(
            "aa030034304758303047503167b2c71d000000000000000000000190012c23e10000000000000000000023e100000000000a"
        ).unwrap();
        assert_eq!(crc16(&data), 0xE884);
    }
}
```

- [ ] **Step 3: Add hex dev-dependency to pmusim-core/Cargo.toml**

```toml
[dev-dependencies]
hex = "0.4"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cargo test -p pmusim-core -- crc16`
Expected: All tests FAIL with "not yet implemented"

- [ ] **Step 5: Implement CRC-16**

```rust
/// CRC-CCITT: polynomial 0x1021, init 0x0000, MSB-first
pub fn crc16(data: &[u8]) -> u16 {
    let mut crc: u16 = 0x0000;
    for &byte in data {
        crc ^= (byte as u16) << 8;
        for _ in 0..8 {
            if crc & 0x8000 != 0 {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc <<= 1;
            }
            crc &= 0xFFFF;
        }
    }
    crc
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cargo test -p pmusim-core -- crc16`
Expected: All 10 tests PASS

- [ ] **Step 7: Commit**

```bash
git add crates/pmusim-core/
git commit -m "feat(core): add CRC-16 CCITT with 10 protocol doc test vectors"
```

---

## Task 3: Protocol Constants

**Files:**
- Create: `crates/pmusim-core/src/protocol/constants.rs`
- Modify: `crates/pmusim-core/src/protocol/mod.rs`

- [ ] **Step 1: Write constants.rs**

```rust
pub const SYNC_BYTE: u8 = 0xAA;
pub const IDCODE_LEN: usize = 8;
pub const STN_LEN: usize = 16;
pub const CHNAM_LEN: usize = 16;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum FrameType {
    Data = 0,
    Cfg1 = 2,
    Cfg2 = 3,
    Command = 4,
}

impl FrameType {
    pub fn from_nibble(nibble: u8) -> Option<Self> {
        match nibble {
            0 => Some(Self::Data),
            2 => Some(Self::Cfg1),
            3 => Some(Self::Cfg2),
            4 => Some(Self::Command),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum ProtocolVersion {
    V2 = 2,
    V3 = 3,
}

impl ProtocolVersion {
    pub fn from_nibble(nibble: u8) -> Option<Self> {
        match nibble {
            2 => Some(Self::V2),
            3 => Some(Self::V3),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u16)]
pub enum Cmd {
    CloseData = 0x0001,
    OpenData = 0x0002,
    SendHdr = 0x0003,
    SendCfg1 = 0x0004,
    SendCfg2 = 0x0005,
    RecvRef = 0x0008,
    Heartbeat = 0x4000,
    Reset = 0x6000,
    SendCfg2Cmd = 0x8000,
    Trigger = 0xA000,
    Ack = 0xE000,
    Nack = 0x2000,
}

/// Construct SYNC word: (0xAA << 8) | (frame_type << 4) | version
pub fn make_sync(frame_type: FrameType, version: ProtocolVersion) -> u16 {
    (SYNC_BYTE as u16) << 8 | (frame_type as u16) << 4 | version as u16
}

/// Parse SYNC word → (FrameType, ProtocolVersion)
pub fn parse_sync(sync: u16) -> Result<(FrameType, ProtocolVersion), String> {
    if (sync >> 8) as u8 != SYNC_BYTE {
        return Err(format!("Invalid sync byte: {sync:#06x}"));
    }
    let low = (sync & 0xFF) as u8;
    let ft = FrameType::from_nibble((low >> 4) & 0x07)
        .ok_or_else(|| format!("Unknown frame type: {}", (low >> 4) & 0x07))?;
    let ver = ProtocolVersion::from_nibble(low & 0x0F)
        .ok_or_else(|| format!("Unknown version: {}", low & 0x0F))?;
    Ok((ft, ver))
}

/// Default ports: (mgmt_port, data_port)
pub fn default_ports(version: ProtocolVersion) -> (u16, u16) {
    match version {
        ProtocolVersion::V2 => (7000, 7001),
        ProtocolVersion::V3 => (8000, 8001),
    }
}
```

- [ ] **Step 2: Update protocol/mod.rs**

```rust
pub mod constants;
pub mod crc16;
```

- [ ] **Step 3: Add tests for parse_sync / make_sync**

Add to bottom of constants.rs:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn make_v2_command() {
        assert_eq!(make_sync(FrameType::Command, ProtocolVersion::V2), 0xAA42);
    }

    #[test]
    fn make_v3_command() {
        assert_eq!(make_sync(FrameType::Command, ProtocolVersion::V3), 0xAA43);
    }

    #[test]
    fn make_v2_data() {
        assert_eq!(make_sync(FrameType::Data, ProtocolVersion::V2), 0xAA02);
    }

    #[test]
    fn parse_roundtrip() {
        let sync = make_sync(FrameType::Cfg1, ProtocolVersion::V3);
        let (ft, ver) = parse_sync(sync).unwrap();
        assert_eq!(ft, FrameType::Cfg1);
        assert_eq!(ver, ProtocolVersion::V3);
    }

    #[test]
    fn parse_invalid_sync() {
        assert!(parse_sync(0xBB42).is_err());
    }
}
```

- [ ] **Step 4: Run tests**

Run: `cargo test -p pmusim-core -- constants`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add crates/pmusim-core/src/protocol/
git commit -m "feat(core): add protocol constants, FrameType, Cmd, sync helpers"
```

---

## Task 4: Frame Structs

**Files:**
- Create: `crates/pmusim-core/src/protocol/frame.rs`
- Modify: `crates/pmusim-core/src/protocol/mod.rs`

- [ ] **Step 1: Write frame.rs with all three frame structs**

```rust
use super::constants::ProtocolVersion;

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
    pub cfg_type: u8,
    pub idcode: String,
    pub soc: u32,
    pub fracsec: u32,
    pub d_frame: u16,
    pub meas_rate: u32,
    pub num_pmu: u16,
    pub stn: String,
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
}

impl ConfigFrame {
    /// Measurement period in milliseconds.
    pub fn period_ms(&self) -> f64 {
        let base_freq: f64 = if self.fnom & 0x01 != 0 { 50.0 } else { 60.0 };
        (self.period as f64 / 100.0) * (1000.0 / base_freq)
    }

    /// Analog scaling factor for channel at `index`.
    pub fn analog_factor(&self, index: usize) -> f64 {
        self.anunit.get(index).copied().unwrap_or(0) as f64 * 0.00001
    }
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

impl DataFrame {
    /// STAT bit15: data valid when 0
    pub fn data_valid(&self) -> bool {
        (self.stat & 0x8000) == 0
    }

    /// STAT bit13: sync ok when 0
    pub fn sync_ok(&self) -> bool {
        (self.stat & 0x2000) == 0
    }
}

/// Union type for parsed frames.
pub enum Frame {
    Command(CommandFrame),
    Config(ConfigFrame),
    Data(DataFrame),
}
```

- [ ] **Step 2: Update protocol/mod.rs**

```rust
pub mod constants;
pub mod crc16;
pub mod frame;
```

- [ ] **Step 3: Verify it compiles**

Run: `cargo build -p pmusim-core`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add crates/pmusim-core/src/protocol/
git commit -m "feat(core): add CommandFrame, ConfigFrame, DataFrame structs"
```

---

## Task 5: Frame Parser

**Files:**
- Create: `crates/pmusim-core/src/protocol/parser.rs`
- Modify: `crates/pmusim-core/src/protocol/mod.rs`

This is the largest core task. The parser handles V2/V3 command, config, and data frames.

- [ ] **Step 1: Write parser tests first**

Create `crates/pmusim-core/src/protocol/parser.rs` with tests at the bottom. Key test vectors from the Python test suite:

```rust
use crate::error::{PmuError, Result};
use super::constants::*;
use super::crc16::crc16;
use super::frame::*;

/// Parse raw bytes into a Frame. For data frames, provide channel counts from CFG-2.
pub fn parse(data: &[u8], phnmr: u16, annmr: u16, dgnmr: u16) -> Result<Frame> {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;

    // --- V2 Command Frames ---

    #[test]
    fn v2_request_cfg1() {
        let data = hex::decode("aa4200146757dd1d30475830304750310004a5cb").unwrap();
        let frame = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = frame {
            assert_eq!(cmd.version, ProtocolVersion::V2);
            assert_eq!(cmd.idcode, "0GX00GP1");
            assert_eq!(cmd.soc, 0x6757DD1D);
            assert_eq!(cmd.cmd, 0x0004); // SEND_CFG1
        } else {
            panic!("Expected CommandFrame");
        }
    }

    #[test]
    fn v2_heartbeat() {
        let data = hex::decode("aa4200146757dd22304758303047503140009cf7").unwrap();
        let frame = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = frame {
            assert_eq!(cmd.cmd, 0x4000); // HEARTBEAT
        } else {
            panic!("Expected CommandFrame");
        }
    }

    #[test]
    fn v3_request_cfg1() {
        let data = hex::decode("aa430018304758303047503167b2c719000000000004ac08").unwrap();
        let frame = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = frame {
            assert_eq!(cmd.version, ProtocolVersion::V3);
            assert_eq!(cmd.idcode, "0GX00GP1");
            assert_eq!(cmd.soc, 0x67B2C719);
            assert_eq!(cmd.fracsec, 0);
            assert_eq!(cmd.cmd, 0x0004);
        } else {
            panic!("Expected CommandFrame");
        }
    }

    #[test]
    fn v3_heartbeat() {
        let data = hex::decode("aa430018304758303047503167b2c71e000000004000f804").unwrap();
        let frame = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = frame {
            assert_eq!(cmd.cmd, 0x4000);
        } else {
            panic!("Expected CommandFrame");
        }
    }

    #[test]
    fn invalid_sync_byte() {
        let data = hex::decode("bb4200146757dd1d30475830304750310004a5cb").unwrap();
        assert!(parse(&data, 0, 0, 0).is_err());
    }

    #[test]
    fn frame_too_short() {
        let data = hex::decode("aa42").unwrap();
        assert!(parse(&data, 0, 0, 0).is_err());
    }

    // --- V2 Data Frame ---

    #[test]
    fn v2_data_frame() {
        let data = hex::decode(
            "aa02002c67a99d11000d9490000000000000\
             012c0bb823d700c800000000000000000023d700000000000a21f3"
        ).unwrap();
        let frame = parse(&data, 0, 11, 1).unwrap();
        if let Frame::Data(df) = frame {
            assert_eq!(df.version, ProtocolVersion::V2);
            assert_eq!(df.idcode, ""); // V2 data has no IDCODE
            assert_eq!(df.soc, 0x67A99D11);
            assert_eq!(df.fracsec, 0x000D9490);
            assert_eq!(df.analog.len(), 11);
            assert_eq!(df.analog[0], 0x012C); // 300
            assert_eq!(df.analog[1], 0x0BB8); // 3000
            assert_eq!(df.digital, vec![0x000A]);
        } else {
            panic!("Expected DataFrame");
        }
    }

    // --- V3 Data Frame ---

    #[test]
    fn v3_data_frame() {
        let data = hex::decode(
            "aa030034304758303047503167b2c71d00000000\
             0000000000000190012c23e100000000000000000000\
             23e100000000000ae884"
        ).unwrap();
        let frame = parse(&data, 0, 11, 1).unwrap();
        if let Frame::Data(df) = frame {
            assert_eq!(df.version, ProtocolVersion::V3);
            assert_eq!(df.idcode, "0GX00GP1");
            assert_eq!(df.analog[0], 0x0190); // 400
            assert_eq!(df.digital, vec![0x000A]);
        } else {
            panic!("Expected DataFrame");
        }
    }

    #[test]
    fn crc_mismatch() {
        let mut data = hex::decode("aa4200146757dd1d30475830304750310004a5cb").unwrap();
        data[18] = 0xFF; // corrupt CRC
        assert!(parse(&data, 0, 0, 0).is_err());
    }
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cargo test -p pmusim-core -- parser`
Expected: All FAIL with "not yet implemented"

- [ ] **Step 3: Implement the parser**

Replace `todo!()` with full implementation. Key logic:

1. Validate length >= 4
2. Read SYNC (big-endian u16 at offset 0), parse_sync → (FrameType, Version)
3. Read SIZE (u16 at offset 2), validate data.len() >= SIZE
4. CRC check: `crc16(&data[..size-2])` must equal u16 at `data[size-2..size]`
5. Dispatch by FrameType:
   - **Command V2** (20 bytes): SOC at [4..8], IDCODE at [8..16] (ASCII), CMD at [16..18]
   - **Command V3** (24 bytes): IDCODE at [4..12], SOC at [12..16], FRACSEC at [16..20], CMD at [20..22]
   - **Config V2**: SOC at [4..8], D_FRAME at [8..10], MEAS_RATE at [10..14], NUM_PMU at [14..16], then PMU data
   - **Config V3**: IDCODE at [4..12], SOC at [12..16], FRACSEC at [16..20], MEAS_RATE at [20..24], NUM_PMU at [24..26], then PMU data
   - **Data V2**: SOC at [4..8], FRACSEC at [8..12], STAT at [12..14], then phasors/freq/analog/digital
   - **Data V3**: IDCODE at [4..12], SOC at [12..16], FRACSEC at [16..20], STAT at [20..22], then phasors/freq/analog/digital

String decoding: IDCODE → ASCII (trim null), STN → GBK via `encoding_rs::GBK`, channel names → GBK.

Reference: Python `protocol/parser.py` for exact offsets.

- [ ] **Step 4: Run tests**

Run: `cargo test -p pmusim-core -- parser`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add crates/pmusim-core/src/protocol/parser.rs
git commit -m "feat(core): implement frame parser with V2/V3 support"
```

---

## Task 6: Frame Builder

**Files:**
- Create: `crates/pmusim-core/src/protocol/builder.rs`
- Modify: `crates/pmusim-core/src/protocol/mod.rs`

- [ ] **Step 1: Write builder with round-trip tests**

The builder is the inverse of the parser. Key tests: build a frame from struct, then parse it back and verify fields match. Also test against known hex from the Python test suite.

```rust
use crate::error::Result;
use super::constants::*;
use super::crc16::crc16;
use super::frame::*;

/// Build a CommandFrame into bytes.
pub fn build_command(frame: &CommandFrame) -> Result<Vec<u8>> {
    todo!()
}

/// Build a ConfigFrame into bytes.
pub fn build_config(frame: &ConfigFrame) -> Result<Vec<u8>> {
    todo!()
}

/// Build a DataFrame into bytes.
pub fn build_data(frame: &DataFrame, phnmr: u16, annmr: u16, dgnmr: u16) -> Result<Vec<u8>> {
    todo!()
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::parser;

    #[test]
    fn v2_command_roundtrip() {
        let frame = CommandFrame {
            version: ProtocolVersion::V2,
            idcode: "0GX00GP1".into(),
            soc: 0x6757DD1D,
            fracsec: 0,
            cmd: Cmd::SendCfg1 as u16,
        };
        let bytes = build_command(&frame).unwrap();
        let parsed = parser::parse(&bytes, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = parsed {
            assert_eq!(cmd.idcode, "0GX00GP1");
            assert_eq!(cmd.soc, 0x6757DD1D);
            assert_eq!(cmd.cmd, Cmd::SendCfg1 as u16);
        } else {
            panic!("Expected CommandFrame");
        }
    }

    #[test]
    fn v2_command_known_hex() {
        let frame = CommandFrame {
            version: ProtocolVersion::V2,
            idcode: "0GX00GP1".into(),
            soc: 0x6757DD1D,
            fracsec: 0,
            cmd: Cmd::SendCfg1 as u16,
        };
        let bytes = build_command(&frame).unwrap();
        assert_eq!(hex::encode(&bytes), "aa4200146757dd1d30475830304750310004a5cb");
    }

    #[test]
    fn v3_command_known_hex() {
        let frame = CommandFrame {
            version: ProtocolVersion::V3,
            idcode: "0GX00GP1".into(),
            soc: 0x67B2C719,
            fracsec: 0,
            cmd: Cmd::SendCfg1 as u16,
        };
        let bytes = build_command(&frame).unwrap();
        assert_eq!(hex::encode(&bytes), "aa430018304758303047503167b2c719000000000004ac08");
    }

    #[test]
    fn v2_data_roundtrip() {
        let frame = DataFrame {
            version: ProtocolVersion::V2,
            idcode: String::new(),
            soc: 0x67A99D11,
            fracsec: 0x000D9490,
            stat: 0x0000,
            phasors: vec![],
            freq: 0,
            dfreq: 0,
            analog: vec![300, 3000, 9175, 200, 0, 0, 0, 0, 0, 0, 0],
            digital: vec![0x000A],
        };
        let bytes = build_data(&frame, 0, 11, 1).unwrap();
        let parsed = parser::parse(&bytes, 0, 11, 1).unwrap();
        if let Frame::Data(df) = parsed {
            assert_eq!(df.soc, 0x67A99D11);
            assert_eq!(df.analog[0], 300);
            assert_eq!(df.digital[0], 0x000A);
        } else {
            panic!("Expected DataFrame");
        }
    }

    #[test]
    fn v3_config_roundtrip() {
        let frame = ConfigFrame {
            version: ProtocolVersion::V3,
            cfg_type: FrameType::Cfg2 as u8,
            idcode: "0GX00GP1".into(),
            soc: 0x67B2C719,
            fracsec: 0,
            d_frame: 0,
            meas_rate: 100,
            num_pmu: 1,
            stn: "TestStation".into(),
            pmu_idcode: "0GX00GP1".into(),
            format_flags: 0,
            phnmr: 0,
            annmr: 2,
            dgnmr: 1,
            channel_names: vec!["AN1".into(), "AN2".into(),
                "D01".into(), "D02".into(), "D03".into(), "D04".into(),
                "D05".into(), "D06".into(), "D07".into(), "D08".into(),
                "D09".into(), "D10".into(), "D11".into(), "D12".into(),
                "D13".into(), "D14".into(), "D15".into(), "D16".into()],
            phunit: vec![],
            anunit: vec![100, 200],
            digunit: vec![(0, 0)],
            fnom: 1,
            period: 100,
        };
        let bytes = build_config(&frame).unwrap();
        let parsed = parser::parse(&bytes, 0, 0, 0).unwrap();
        if let Frame::Config(cfg) = parsed {
            assert_eq!(cfg.stn.trim_end_matches('\0'), "TestStation");
            assert_eq!(cfg.annmr, 2);
            assert_eq!(cfg.period, 100);
        } else {
            panic!("Expected ConfigFrame");
        }
    }
}
```

- [ ] **Step 2: Implement builder functions**

V2 Command (20 bytes): `SYNC(2) + SIZE(2) + SOC(4) + IDCODE(8) + CMD(2) + CRC(2)`
V3 Command (24 bytes): `SYNC(2) + SIZE(2) + IDCODE(8) + SOC(4) + FRACSEC(4) + CMD(2) + CRC(2)`

String encoding: IDCODE → 8 bytes ASCII null-padded, STN → 16 bytes GBK null-padded, Channel names → 16 bytes GBK each.

All integers big-endian. CRC appended last.

Reference: Python `protocol/builder.py` for exact byte layout.

- [ ] **Step 3: Run tests**

Run: `cargo test -p pmusim-core -- builder`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add crates/pmusim-core/src/protocol/builder.rs
git commit -m "feat(core): implement frame builder with round-trip verification"
```

---

## Task 7: Time Utilities

**Files:**
- Create: `crates/pmusim-core/src/time_utils.rs`

- [ ] **Step 1: Write tests first**

```rust
use std::time::{SystemTime, UNIX_EPOCH};

/// Convert SOC (seconds since Unix epoch) to Beijing time string (UTC+8).
pub fn soc_to_beijing(soc: u32) -> String {
    todo!()
}

/// Convert FRACSEC to milliseconds.
pub fn fracsec_to_ms(fracsec: u32, meas_rate: u32, version: u8) -> f64 {
    todo!()
}

/// Current time as SOC.
pub fn current_soc() -> u32 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs() as u32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn soc_epoch() {
        assert_eq!(soc_to_beijing(0), "1970-01-01 08:00:00");
    }

    #[test]
    fn soc_v2_doc_example() {
        assert_eq!(soc_to_beijing(0x6757DD1D), "2024-12-10 14:18:05");
    }

    #[test]
    fn soc_v3_doc_example() {
        assert_eq!(soc_to_beijing(0x67B2C719), "2025-02-17 13:20:25");
    }

    #[test]
    fn fracsec_v2_doc() {
        let ms = fracsec_to_ms(0x000D9490, 1_000_000, 2);
        assert!((ms - 890.0).abs() < 0.1);
    }

    #[test]
    fn fracsec_v3_zero() {
        let ms = fracsec_to_ms(0, 1_000_000, 3);
        assert!((ms - 0.0).abs() < 0.01);
    }

    #[test]
    fn fracsec_v3_quality_bits() {
        // Upper 8 bits are quality flags in V3, lower 24 are count
        let ms = fracsec_to_ms(0x0F07A120, 1_000_000, 3);
        assert!((ms - 500.0).abs() < 0.1);
    }

    #[test]
    fn fracsec_zero_meas_rate() {
        assert!((fracsec_to_ms(1000, 0, 3) - 0.0).abs() < 0.01);
    }
}
```

- [ ] **Step 2: Implement**

```rust
pub fn soc_to_beijing(soc: u32) -> String {
    let total_secs = soc as i64 + 8 * 3600; // UTC+8
    let days = total_secs / 86400;
    let time_of_day = (total_secs % 86400) as u32;
    let hours = time_of_day / 3600;
    let minutes = (time_of_day % 3600) / 60;
    let seconds = time_of_day % 60;

    // Civil date from days since epoch (Rata Die algorithm)
    let (year, month, day) = days_to_date(days);
    format!("{year:04}-{month:02}-{day:02} {hours:02}:{minutes:02}:{seconds:02}")
}

fn days_to_date(days_since_epoch: i64) -> (i32, u32, u32) {
    // Algorithm from Howard Hinnant
    let z = days_since_epoch + 719468;
    let era = (if z >= 0 { z } else { z - 146096 }) / 146097;
    let doe = (z - era * 146097) as u32;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i32 + (era * 400) as i32;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    let y = if m <= 2 { y + 1 } else { y };
    (y, m, d)
}

pub fn fracsec_to_ms(fracsec: u32, meas_rate: u32, version: u8) -> f64 {
    if meas_rate == 0 {
        return 0.0;
    }
    let count = if version >= 3 {
        fracsec & 0x00FFFFFF
    } else {
        fracsec
    };
    count as f64 / (meas_rate as f64 / 1000.0)
}
```

- [ ] **Step 3: Run tests**

Run: `cargo test -p pmusim-core -- time_utils`
Expected: All 7 tests PASS

- [ ] **Step 4: Commit**

```bash
git add crates/pmusim-core/src/time_utils.rs
git commit -m "feat(core): add SOC/FRACSEC time conversion utilities"
```

---

## Task 8: Tauri App Scaffold

**Files:**
- Create: `crates/pmusim-app/Cargo.toml`
- Create: `crates/pmusim-app/build.rs`
- Create: `crates/pmusim-app/tauri.conf.json`
- Create: `crates/pmusim-app/src/main.rs`
- Create: `crates/pmusim-app/src/state.rs`
- Create: `crates/pmusim-app/src/events.rs`

- [ ] **Step 1: Create pmusim-app/Cargo.toml**

```toml
[package]
name = "pmusim-app"
version = "0.1.0"
edition = "2021"

[dependencies]
pmusim-core = { path = "../pmusim-core" }
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
log = "0.4"
tauri = { version = "2", features = [] }
tauri-plugin-log = "2"
tokio = { version = "1", features = ["full"] }

[build-dependencies]
tauri-build = { version = "2", features = [] }
```

- [ ] **Step 2: Create build.rs**

```rust
fn main() {
    tauri_build::build()
}
```

- [ ] **Step 3: Create tauri.conf.json**

```json
{
  "productName": "PmuSim",
  "version": "0.2.0",
  "identifier": "com.pmusim.dev",
  "build": {
    "devUrl": "http://localhost:5173",
    "beforeDevCommand": { "script": "npm run dev", "cwd": "../../frontend" },
    "frontendDist": "../../frontend/dist"
  },
  "app": {
    "windows": [
      {
        "title": "PmuSim - PMU Master Station Simulator",
        "width": 1100,
        "height": 700,
        "minWidth": 900,
        "minHeight": 500,
        "resizable": true,
        "fullscreen": false
      }
    ],
    "security": { "csp": null }
  },
  "bundle": {
    "active": true,
    "targets": "all",
    "icon": [
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.icns",
      "icons/icon.ico"
    ]
  }
}
```

- [ ] **Step 4: Create events.rs**

```rust
use serde::Serialize;

#[derive(Clone, Serialize)]
#[serde(tag = "type")]
pub enum PmuEvent {
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

#[derive(Clone, Serialize)]
pub struct ConfigInfo {
    pub cfg_type: u8,
    pub version: u8,
    pub stn: String,
    pub idcode: String,
    pub format_flags: u16,
    pub period: u16,
    pub meas_rate: u32,
    pub phnmr: u16,
    pub annmr: u16,
    pub dgnmr: u16,
    pub channel_names: Vec<String>,
    pub anunit: Vec<u32>,
}

#[derive(Clone, Serialize)]
pub struct DataInfo {
    pub soc: u32,
    pub fracsec: u32,
    pub stat: u16,
    pub analog: Vec<f64>,
    pub digital: Vec<u16>,
    pub phasors: Vec<(i16, i16)>,
}
```

- [ ] **Step 5: Create state.rs**

```rust
use std::sync::Arc;
use tokio::sync::Mutex;

pub struct AppState {
    pub master: Arc<Mutex<Option<MasterStationHandle>>>,
}

pub struct MasterStationHandle {
    pub shutdown_tx: tokio::sync::oneshot::Sender<()>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            master: Arc::new(Mutex::new(None)),
        }
    }
}
```

- [ ] **Step 6: Create main.rs (minimal)**

```rust
mod commands;
mod events;
mod state;
mod network;

use state::AppState;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_log::Builder::new().build())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            commands::start_server,
            commands::stop_server,
            commands::connect_substation,
            commands::send_command,
            commands::auto_handshake,
        ])
        .run(tauri::generate_context!())
        .expect("error while running PmuSim");
}
```

- [ ] **Step 7: Create stub commands.rs**

```rust
use tauri::State;
use crate::state::AppState;

#[tauri::command]
pub async fn start_server(state: State<'_, AppState>, data_port: u16, protocol: String) -> Result<(), String> {
    Ok(()) // stub
}

#[tauri::command]
pub async fn stop_server(state: State<'_, AppState>) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
pub async fn connect_substation(state: State<'_, AppState>, host: String, port: u16) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
pub async fn send_command(state: State<'_, AppState>, idcode: String, cmd: String, period: Option<u32>) -> Result<(), String> {
    Ok(())
}

#[tauri::command]
pub async fn auto_handshake(state: State<'_, AppState>, idcode: String, period: Option<u32>) -> Result<(), String> {
    Ok(())
}
```

- [ ] **Step 8: Create network module stubs**

`crates/pmusim-app/src/network/mod.rs`:
```rust
pub mod master;
pub mod session;
```

`crates/pmusim-app/src/network/session.rs` and `master.rs`: empty stubs for now.

- [ ] **Step 9: Verify cargo check passes**

Run: `cargo check -p pmusim-app`
Expected: Compiles (Tauri won't fully build without frontend, but check should pass)

- [ ] **Step 10: Commit**

```bash
git add crates/pmusim-app/
git commit -m "feat(app): scaffold Tauri app with stub commands and events"
```

---

## Task 9: Network Session + MasterStation

**Files:**
- Create: `crates/pmusim-app/src/network/session.rs`
- Create: `crates/pmusim-app/src/network/master.rs`

Port the Python `network/session.py` and `network/master.py` logic to Rust with tokio.

- [ ] **Step 1: Implement session.rs**

Port `SubStationSession` and `SessionState` from Python. Use `tokio::net::tcp::{OwnedReadHalf, OwnedWriteHalf}` instead of asyncio StreamReader/Writer. Session owns `Arc<RwLock<...>>` for concurrent access safety.

Reference: Python `network/session.py`

- [ ] **Step 2: Implement master.rs**

Port `MasterStation` from Python. Key differences from Python:
- Use `tokio::net::TcpListener` instead of `asyncio.start_server`
- Use `tokio::net::TcpStream::connect()` instead of `asyncio.open_connection`
- Use `tokio::sync::mpsc` for command queue (replaces `asyncio.Queue`)
- Use `Arc<RwLock<HashMap<String, SubStationSession>>>` for sessions (replaces bare dict)
- Use `AppHandle::emit("pmu-event", &event)` to push events to frontend

The MasterStation should accept an `AppHandle` and emit `PmuEvent` variants.

Reference: Python `network/master.py` (429 lines) — all event emissions, TCP read/write logic, heartbeat, auto-handshake.

- [ ] **Step 3: Wire up commands.rs to MasterStation**

Implement `start_server`, `stop_server`, `connect_substation`, `send_command`, `auto_handshake` in `commands.rs` by calling MasterStation methods.

- [ ] **Step 4: Write integration test**

Port `tests/test_e2e.py` to Rust:
- Mock substation as tokio TCP server (mgmt pipe)
- Master connects as client
- Exchange heartbeat → CFG-1 → data frames
- Verify events received

Run: `cargo test -p pmusim-app -- e2e`

- [ ] **Step 5: Commit**

```bash
git add crates/pmusim-app/src/
git commit -m "feat(app): implement MasterStation network layer with tokio"
```

---

## Task 10: Vue 3 Frontend Scaffold

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.ts`
- Create: `frontend/src/App.vue`
- Create: `frontend/src/types/index.ts`

- [ ] **Step 1: Initialize frontend**

```bash
cd frontend
npm create vite@latest . -- --template vue-ts
```

Or create files manually.

- [ ] **Step 2: Install dependencies**

```bash
npm install @tauri-apps/api @tanstack/vue-virtual
npm install -D @tauri-apps/cli
```

- [ ] **Step 3: Create types/index.ts**

```typescript
export interface SessionInfo {
  idcode: string
  peerIp: string
  state: 'connected' | 'cfg1_received' | 'cfg2_sent' | 'streaming' | 'disconnected'
}

export interface ConfigInfo {
  cfgType: number
  version: number
  stn: string
  idcode: string
  formatFlags: number
  period: number
  measRate: number
  phnmr: number
  annmr: number
  dgnmr: number
  channelNames: string[]
  anunit: number[]
}

export interface DataInfo {
  soc: number
  fracsec: number
  stat: number
  analog: number[]
  digital: number[]
  phasors: [number, number][]
}

export interface RawFrameInfo {
  idcode: string
  direction: 'send' | 'recv'
  hex: string
}

export type PmuEvent =
  | { type: 'SessionCreated'; idcode: string; peer_ip: string }
  | { type: 'SessionDisconnected'; idcode: string }
  | { type: 'Cfg1Received'; idcode: string; cfg: ConfigInfo }
  | { type: 'Cfg2Sent'; idcode: string }
  | { type: 'Cfg2Received'; idcode: string; cfg: ConfigInfo }
  | { type: 'StreamingStarted'; idcode: string }
  | { type: 'StreamingStopped'; idcode: string }
  | { type: 'DataFrame'; idcode: string; data: DataInfo }
  | { type: 'RawFrame'; idcode: string; direction: string; hex: string }
  | { type: 'HeartbeatTimeout'; idcode: string }
  | { type: 'Error'; idcode: string; error: string }
```

- [ ] **Step 4: Create composables**

Create `usePmuEvents.ts`, `useSessions.ts`, `useCommLog.ts` as described in design spec.

- [ ] **Step 5: Create App.vue with layout skeleton**

```
Toolbar | separator
StationList (left 220px) | Tabs (right, fill)
Status bar
```

- [ ] **Step 6: Verify dev server starts**

Run: `cd frontend && npm run dev`
Expected: Vite dev server on http://localhost:5173

- [ ] **Step 7: Commit**

```bash
git add frontend/
git commit -m "feat(frontend): scaffold Vue 3 + TypeScript + Tauri types"
```

---

## Task 11: Frontend Components

**Files:**
- Create: `frontend/src/components/ToolbarPanel.vue`
- Create: `frontend/src/components/StationListPanel.vue`
- Create: `frontend/src/components/ConfigTab.vue`
- Create: `frontend/src/components/DataTab.vue`
- Create: `frontend/src/components/LogTab.vue`

- [ ] **Step 1: ToolbarPanel.vue**

Start/Stop buttons, protocol selector (V2/V3 dropdown), data port input. Calls `invoke("start_server", { dataPort, protocol })` and `invoke("stop_server")`.

Reference: Python `ui/toolbar.py` for button labels and protocol change handler.

- [ ] **Step 2: StationListPanel.vue**

Left panel (220px fixed width):
- Station list with state badges
- Connect form: IP input (default 127.0.0.1), port input (default 8000, synced to protocol)
- Action buttons: 召唤CFG-1, 下传CFG-2命令, 下传CFG-2, 召唤CFG-2, 开启数据, 关闭数据
- PERIOD input + 一键握手 button

Reference: Python `ui/station_list.py` for layout and button labels.

- [ ] **Step 3: ConfigTab.vue**

Basic info table (cfg_type, version, stn, idcode, format, period, meas_rate) + analog channels table (name, anunit, factor) + digital channels table (name, valid mask).

Reference: Python `ui/config_panel.py`.

- [ ] **Step 4: DataTab.vue**

Treeview-style table with columns from CFG-2 channel names. Throttled updates (200ms). Max 500 rows. Uses `@tanstack/vue-virtual` for virtual scrolling.

Reference: Python `ui/data_panel.py`.

- [ ] **Step 5: LogTab.vue**

Log table (time, station, direction arrow, frame type, summary) + hex dump detail panel at bottom. Max 1000 entries. Click row to show hex.

Reference: Python `ui/log_panel.py`.

- [ ] **Step 6: Verify Tauri dev mode works**

Run: `cd crates/pmusim-app && cargo tauri dev`
Expected: Window opens with all panels rendered

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/
git commit -m "feat(frontend): implement all UI components (toolbar, stations, config, data, log)"
```

---

## Task 12: CI/CD + README + Cleanup

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `README.md`
- Modify: `README_CN.md`

- [ ] **Step 1: Replace release.yml with tauri-action workflow**

```yaml
name: Release

on:
  push:
    tags:
      - 'v*'

jobs:
  release:
    permissions:
      contents: write
    strategy:
      fail-fast: false
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
    runs-on: ${{ matrix.platform }}

    steps:
      - uses: actions/checkout@v4

      - name: Install Node.js
        uses: actions/setup-node@v4
        with:
          node-version: 22

      - name: Install Rust stable
        uses: dtolnay/rust-toolchain@stable
        with:
          targets: ${{ matrix.platform == 'macos-latest' && 'aarch64-apple-darwin,x86_64-apple-darwin' || '' }}

      - name: Install Linux dependencies
        if: matrix.platform == 'ubuntu-22.04'
        run: |
          sudo apt-get update
          sudo apt-get install -y libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev patchelf

      - name: Install frontend dependencies
        run: |
          cd frontend
          npm install

      - name: Build frontend
        working-directory: frontend
        run: npm run build

      - name: Build and release
        uses: tauri-apps/tauri-action@v0
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        with:
          projectPath: crates/pmusim-app
          tagName: ${{ github.ref_name }}
          releaseName: 'PmuSim ${{ github.ref_name }}'
          releaseBody: |
            ## Downloads

            **PmuSim** — PMU 主站模拟器 / PMU Master Station Simulator

            See the assets below to download for your platform.
          releaseDraft: false
          prerelease: false
          args: ${{ matrix.args }}
```

- [ ] **Step 2: Update README.md**

Update tech stack section from Python to Rust+Tauri+Vue. Update download links for Tauri artifacts (.dmg, .msi, .deb, .AppImage). Keep protocol documentation unchanged.

- [ ] **Step 3: Update README_CN.md**

Same changes in Chinese.

- [ ] **Step 4: Move Python code to legacy branch**

```bash
git checkout -b legacy/python-tkinter
git checkout main
```

- [ ] **Step 5: Run full test suite**

```bash
cargo test --workspace
```

Expected: All protocol + E2E tests pass.

- [ ] **Step 6: Tag and push**

```bash
git tag v0.2.0
git push origin main v0.2.0
```

Expected: GitHub Actions triggers cross-platform Tauri build.

- [ ] **Step 7: Commit**

```bash
git add .github/ README.md README_CN.md
git commit -m "feat: replace PyInstaller CI with Tauri cross-platform build"
```

---

## Summary

| Task | Component | Estimated Complexity |
|------|-----------|---------------------|
| 1 | Workspace + error types | Small |
| 2 | CRC-16 + 10 test vectors | Small |
| 3 | Protocol constants | Small |
| 4 | Frame structs | Small |
| 5 | Frame parser (V2/V3) | Large |
| 6 | Frame builder + round-trip | Medium |
| 7 | Time utilities | Small |
| 8 | Tauri app scaffold | Medium |
| 9 | Network (session + master + E2E) | Large |
| 10 | Frontend scaffold + types | Medium |
| 11 | Frontend components (5 panels) | Large |
| 12 | CI/CD + README + cleanup | Small |
