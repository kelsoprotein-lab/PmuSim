# PmuSim Master Station Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Tkinter-based PMU master station simulator supporting V2/V3 protocols, managing 2-10 substation connections for testing.

**Architecture:** Three-layer architecture (Protocol -> Network -> UI) with asyncio in a background thread for TCP, Tkinter in the main thread, communicating via thread-safe queues.

**Tech Stack:** Python 3.10+ standard library only (tkinter, asyncio, struct, dataclasses, enum, threading, queue, unittest)

**Design Spec:** `docs/superpowers/specs/2026-04-14-pmu-master-station-simulator-design.md`

---

## File Structure

```
PmuSim/
├── main.py                      # Entry point: starts UI + asyncio backend
├── protocol/
│   ├── __init__.py              # Re-exports public API
│   ├── constants.py             # Frame types, CMD codes, SYNC magic, enums
│   ├── crc16.py                 # CRC-CCITT checksum
│   ├── frames.py                # Dataclasses: CommandFrame, ConfigFrame, DataFrame
│   ├── parser.py                # FrameParser: bytes -> frame objects (V2/V3)
│   └── builder.py               # FrameBuilder: frame objects -> bytes (V2/V3)
├── network/
│   ├── __init__.py
│   ├── session.py               # SubStationSession + SessionState enum
│   └── master.py                # MasterStation: asyncio TCP servers + command dispatch
├── ui/
│   ├── __init__.py
│   ├── app.py                   # Main window: assembles panels, runs event queue polling
│   ├── toolbar.py               # Start/stop, protocol selector, port config
│   ├── station_list.py          # Left panel: substation list + action buttons
│   ├── config_panel.py          # Tab: CFG-1/CFG-2 viewer + PERIOD editor
│   ├── data_panel.py            # Tab: real-time analog/digital table
│   └── log_panel.py             # Tab: communication log (hex + summary)
├── utils/
│   ├── __init__.py
│   └── time_utils.py            # SOC -> Beijing time, FRACSEC -> ms
└── tests/
    ├── __init__.py
    ├── test_crc16.py
    ├── test_parser.py
    ├── test_builder.py
    ├── test_time_utils.py
    └── test_e2e.py              # End-to-end: mock substation connects to MasterStation
```

---

## Task 1: Protocol Constants + CRC16

**Files:**
- Create: `protocol/__init__.py`
- Create: `protocol/constants.py`
- Create: `protocol/crc16.py`
- Create: `tests/__init__.py`
- Create: `tests/test_crc16.py`

- [ ] **Step 1: Create `protocol/constants.py`**

```python
"""PMU protocol constants for V2 and V3."""
from enum import IntEnum

SYNC_BYTE = 0xAA

class FrameType(IntEnum):
    """Frame type from SYNC byte Bit6~4."""
    DATA = 0b000
    CFG1 = 0b010
    CFG2 = 0b011
    COMMAND = 0b100

class ProtocolVersion(IntEnum):
    V2 = 2
    V3 = 3

# SYNC low nibble for each version
SYNC_VERSION = {
    ProtocolVersion.V2: 0x02,
    ProtocolVersion.V3: 0x03,
}

def make_sync(frame_type: FrameType, version: ProtocolVersion) -> int:
    """Build 2-byte SYNC value: 0xAA | (frame_type << 4) | version_nibble."""
    return (SYNC_BYTE << 8) | (frame_type << 4) | SYNC_VERSION[version]

def parse_sync(sync: int) -> tuple[FrameType, ProtocolVersion]:
    """Extract frame type and version from 2-byte SYNC value."""
    if (sync >> 8) != SYNC_BYTE:
        raise ValueError(f"Invalid sync byte: {sync:#06x}")
    low = sync & 0xFF
    frame_type = FrameType((low >> 4) & 0x07)
    version_nibble = low & 0x0F
    if version_nibble == 0x02:
        version = ProtocolVersion.V2
    elif version_nibble == 0x03:
        version = ProtocolVersion.V3
    else:
        raise ValueError(f"Unknown protocol version nibble: {version_nibble:#x}")
    return frame_type, version

class Cmd(IntEnum):
    """CMD field values (Bit15~0)."""
    CLOSE_DATA = 0x0001      # Bit3~0 = 0001
    OPEN_DATA = 0x0002       # Bit3~0 = 0010
    SEND_HDR = 0x0003        # Bit3~0 = 0011
    SEND_CFG1 = 0x0004      # Bit3~0 = 0100
    SEND_CFG2 = 0x0005      # Bit3~0 = 0101
    RECV_REF = 0x0008        # Bit3~0 = 1000
    HEARTBEAT = 0x4000       # Bit15~13 = 010
    RESET = 0x6000           # Bit15~13 = 011
    SEND_CFG2_CMD = 0x8000   # Bit15~13 = 100
    TRIGGER = 0xA000         # Bit15~13 = 101
    ACK = 0xE000             # Bit15~13 = 111 (positive ack)
    NACK = 0x2000            # Bit15~13 = 001 (negative ack, V3 only)

# Human-readable command names
CMD_NAMES = {
    Cmd.CLOSE_DATA: "关闭实时数据",
    Cmd.OPEN_DATA: "打开实时数据",
    Cmd.SEND_HDR: "发送头文件",
    Cmd.SEND_CFG1: "召唤CFG-1",
    Cmd.SEND_CFG2: "召唤CFG-2",
    Cmd.RECV_REF: "接收参考相量",
    Cmd.HEARTBEAT: "心跳",
    Cmd.RESET: "系统复位",
    Cmd.SEND_CFG2_CMD: "下传CFG-2命令",
    Cmd.TRIGGER: "联网触发",
    Cmd.ACK: "确认",
    Cmd.NACK: "否定确认",
}

# Default ports
DEFAULT_PORTS = {
    ProtocolVersion.V2: {"mgmt": 7000, "data": 7001},
    ProtocolVersion.V3: {"mgmt": 8000, "data": 8001},
}

# IDCODE length in bytes
IDCODE_LEN = 8
# Station name length in bytes
STN_LEN = 16
# Channel name length in bytes
CHNAM_LEN = 16
```

- [ ] **Step 2: Create `protocol/crc16.py`**

```python
"""CRC-CCITT (0xFFFF) checksum for PMU protocol frames."""

def crc16(data: bytes) -> int:
    """Calculate CRC-CCITT checksum.

    Polynomial: x^16 + x^12 + x^5 + 1 (0x1021)
    Initial value: 0xFFFF
    """
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return crc
```

- [ ] **Step 3: Create `protocol/__init__.py` and `tests/__init__.py`**

`protocol/__init__.py`:
```python
"""PMU protocol V2/V3 encoding and decoding."""
```

`tests/__init__.py`:
```python
```

- [ ] **Step 4: Write CRC16 tests using known protocol data**

Create `tests/test_crc16.py`:
```python
"""Test CRC16 against known values from PMU protocol docs."""
import unittest
from protocol.crc16 import crc16


class TestCRC16(unittest.TestCase):
    def test_v2_command_request_cfg1(self):
        # V2 command frame: request CFG-1 (doc report 1)
        # Full frame: aa 42 00 14 67 57 dd 1d 30 47 58 30 30 47 50 31 00 04 a5 cb
        data = bytes.fromhex("aa420014 6757dd1d 3047583030475031 0004".replace(" ", ""))
        self.assertEqual(crc16(data), 0xA5CB)

    def test_v2_command_heartbeat(self):
        # V2 heartbeat: aa 42 00 14 67 57 dd 22 30 47 58 30 30 47 50 31 40 00 9c f7
        data = bytes.fromhex("aa420014 6757dd22 3047583030475031 4000".replace(" ", ""))
        self.assertEqual(crc16(data), 0x9CF7)

    def test_v2_command_ack(self):
        # V2 ack: aa 42 00 14 67 57 dd 9d 30 47 58 30 30 47 50 31 e0 00 7c 57
        data = bytes.fromhex("aa420014 6757dd9d 3047583030475031 e000".replace(" ", ""))
        self.assertEqual(crc16(data), 0x7C57)

    def test_v2_command_open_data(self):
        # V2 open data: aa 42 00 14 67 57 dd 1e 30 47 58 30 30 47 50 31 00 02 bd f7
        data = bytes.fromhex("aa420014 6757dd1e 3047583030475031 0002".replace(" ", ""))
        self.assertEqual(crc16(data), 0xBDF7)

    def test_v2_command_send_cfg2_cmd(self):
        # V2 send CFG-2 command: aa 42 00 14 67 57 dd 1e 30 47 58 30 30 47 50 31 80 00 86 2d
        data = bytes.fromhex("aa420014 6757dd1e 3047583030475031 8000".replace(" ", ""))
        self.assertEqual(crc16(data), 0x862D)

    def test_v3_command_request_cfg1(self):
        # V3 command: request CFG-1
        # aa 43 00 18 30 47 58 30 30 47 50 31 67 b2 c7 19 00 00 00 00 00 04 ac 08
        data = bytes.fromhex(
            "aa430018 3047583030475031 67b2c719 00000000 0004".replace(" ", "")
        )
        self.assertEqual(crc16(data), 0xAC08)

    def test_v3_command_ack(self):
        # V3 ack: aa 43 00 18 30 47 58 30 30 47 50 31 67 b2 c7 1a 00 00 00 00 e0 00 24 bc
        data = bytes.fromhex(
            "aa430018 3047583030475031 67b2c71a 00000000 e000".replace(" ", "")
        )
        self.assertEqual(crc16(data), 0x24BC)

    def test_v3_command_heartbeat(self):
        # V3 heartbeat: aa 43 00 18 30 47 58 30 30 47 50 31 67 b2 c7 1e 00 00 00 00 40 00 f8 04
        data = bytes.fromhex(
            "aa430018 3047583030475031 67b2c71e 00000000 4000".replace(" ", "")
        )
        self.assertEqual(crc16(data), 0xF804)

    def test_v2_data_frame(self):
        # V2 data frame (44 bytes, CRC=21f3)
        data = bytes.fromhex(
            "aa02002c 67a99d11 000d9490"
            "0000 0000 0000"
            "012c 0bb8 23d7 00c8 0000 0000 0000 0000 23d7 0000 0000"
            "000a".replace(" ", "")
        )
        self.assertEqual(crc16(data), 0x21F3)

    def test_v3_data_frame(self):
        # V3 data frame (52 bytes, CRC=e884)
        data = bytes.fromhex(
            "aa030034 3047583030475031 67b2c71d 00000000"
            "0000 0000 0000"
            "0190 012c 23e1 0000 0000 0000 0000 0000 23e1 0000 0000"
            "000a".replace(" ", "")
        )
        self.assertEqual(crc16(data), 0xE884)

    def test_empty_data(self):
        self.assertEqual(crc16(b""), 0xFFFF)

    def test_single_byte(self):
        result = crc16(b"\x00")
        self.assertIsInstance(result, int)
        self.assertTrue(0 <= result <= 0xFFFF)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 5: Run CRC16 tests**

Run: `cd /Users/daichangyu/Library/Mobile\ Documents/com~apple~CloudDocs/code/PmuSim && python -m unittest tests.test_crc16 -v`

Expected: All tests PASS. If any CRC test fails, the CRC algorithm variant may need adjustment (try initial value 0x0000 or different polynomial).

- [ ] **Step 6: Commit**

```bash
git add protocol/ tests/
git commit -m "feat: add protocol constants and CRC16 with tests"
```

---

## Task 2: Frame Data Classes + Time Utils

**Files:**
- Create: `protocol/frames.py`
- Create: `utils/__init__.py`
- Create: `utils/time_utils.py`
- Create: `tests/test_time_utils.py`

- [ ] **Step 1: Create `protocol/frames.py`**

```python
"""Frame dataclasses for PMU protocol V2/V3."""
from dataclasses import dataclass, field


@dataclass
class CommandFrame:
    """Command frame (SYNC Bit6~4 = 100)."""
    version: int          # 2 or 3
    idcode: str           # 8-char ASCII, e.g. "0GX00GP1"
    soc: int              # Unix timestamp (seconds)
    fracsec: int          # V3: includes time quality in Bit27~24. V2: 0
    cmd: int              # CMD field (see constants.Cmd)


@dataclass
class ConfigFrame:
    """Configuration frame CFG-1 (SYNC Bit6~4=010) or CFG-2 (011)."""
    version: int          # 2 or 3
    cfg_type: int         # 1 or 2
    idcode: str           # Primary IDCODE for session identification
    soc: int
    fracsec: int          # V3 only, 0 for V2
    d_frame: int          # V2 only: checksum flag. 0 for V3
    meas_rate: int        # Microseconds per second division
    num_pmu: int          # Number of PMUs (typically 1)
    stn: str              # Station name (decoded from 16 bytes)
    pmu_idcode: str       # Per-PMU IDCODE (8-char ASCII)
    format_flags: int     # FORMAT field bits
    phnmr: int            # Phasor count
    annmr: int            # Analog count
    dgnmr: int            # Digital word count (1 word = 16 channels)
    channel_names: list[str] = field(default_factory=list)
    phunit: list[int] = field(default_factory=list)
    anunit: list[int] = field(default_factory=list)
    digunit: list[tuple[int, int]] = field(default_factory=list)  # (normal_status, valid_mask)
    fnom: int = 0         # Rated frequency flags (Bit0=1 -> 50Hz)
    period: int = 0       # Transmission period (base_wave_multiple * 100)

    @property
    def period_ms(self) -> float:
        """Transmission period in milliseconds."""
        base_freq = 50 if (self.fnom & 0x01) else 60
        base_period_ms = 1000.0 / base_freq  # 20ms for 50Hz
        multiplier = self.period / 100.0
        return multiplier * base_period_ms

    def analog_factor(self, index: int) -> float:
        """Get analog conversion factor for channel index."""
        if 0 <= index < len(self.anunit):
            return self.anunit[index] * 0.00001
        return 1.0


@dataclass
class DataFrame:
    """Data frame (SYNC Bit6~4 = 000)."""
    version: int
    idcode: str           # V3: from header. V2: empty (filled by session)
    soc: int
    fracsec: int          # Raw 4-byte value
    stat: int             # Status word
    phasors: list[tuple[int, int]] = field(default_factory=list)
    freq: int = 0         # Frequency offset (signed 16-bit)
    dfreq: int = 0        # Rate of frequency change (signed 16-bit)
    analog: list[int] = field(default_factory=list)   # Raw integer values
    digital: list[int] = field(default_factory=list)   # Raw digital words

    @property
    def data_valid(self) -> bool:
        """Bit15 of STAT: 0=valid, 1=invalid."""
        return (self.stat & 0x8000) == 0

    @property
    def sync_ok(self) -> bool:
        """Bit13 of STAT: 0=synchronized."""
        return (self.stat & 0x2000) == 0
```

- [ ] **Step 2: Create `utils/__init__.py` and `utils/time_utils.py`**

`utils/__init__.py`:
```python
```

`utils/time_utils.py`:
```python
"""Time conversion utilities for PMU protocol."""
import time as _time


def soc_to_beijing(soc: int) -> str:
    """Convert SOC (Unix timestamp) to Beijing time string.

    Args:
        soc: Seconds since 1970-01-01 00:00:00 UTC.

    Returns:
        String like '2025-02-17 13:20:25'.
    """
    # Beijing time = UTC + 8h
    t = _time.gmtime(soc + 8 * 3600)
    return _time.strftime("%Y-%m-%d %H:%M:%S", t)


def fracsec_to_ms(fracsec: int, meas_rate: int, version: int = 3) -> float:
    """Convert FRACSEC field to milliseconds.

    Args:
        fracsec: Raw FRACSEC value.
        meas_rate: MEAS_RATE from config frame (microseconds).
        version: Protocol version (2 or 3).

    Returns:
        Milliseconds within the current second.
    """
    if meas_rate == 0:
        return 0.0
    # V3: Bit27~24 are time quality, Bit23~0 are count
    # V2: all 32 bits are count (but values fit in 24 bits)
    if version == 3:
        count = fracsec & 0x00FFFFFF
    else:
        count = fracsec
    return count / (meas_rate / 1000.0)


def current_soc() -> int:
    """Get current time as SOC (Unix timestamp, integer seconds)."""
    return int(_time.time())
```

- [ ] **Step 3: Write time utils tests**

Create `tests/test_time_utils.py`:
```python
"""Test time conversion utilities."""
import unittest
from utils.time_utils import soc_to_beijing, fracsec_to_ms


class TestSocToBeijing(unittest.TestCase):
    def test_v2_doc_example(self):
        # From V2 doc: 0x6757DD1D = 1733811485 -> 2024-12-10 14:18:05
        self.assertEqual(soc_to_beijing(0x6757DD1D), "2024-12-10 14:18:05")

    def test_v3_doc_example(self):
        # From V3 doc: 0x67b2c719 = 1739769625 -> 2025-02-17 13:20:25
        self.assertEqual(soc_to_beijing(0x67B2C719), "2025-02-17 13:20:25")

    def test_epoch(self):
        # Unix epoch -> Beijing time (UTC+8)
        self.assertEqual(soc_to_beijing(0), "1970-01-01 08:00:00")


class TestFracsecToMs(unittest.TestCase):
    def test_v2_doc_example(self):
        # V2: FRACSEC=0x000D9490=890000, MEAS_RATE=1000000
        # ms = 890000 / (1000000/1000) = 890.0
        result = fracsec_to_ms(0x000D9490, 1000000, version=2)
        self.assertAlmostEqual(result, 890.0)

    def test_v3_zero(self):
        result = fracsec_to_ms(0x00000000, 1000000, version=3)
        self.assertAlmostEqual(result, 0.0)

    def test_v3_with_quality_bits(self):
        # Simulate V3 FRACSEC with quality bits in Bit27~24
        # Quality = 0xF (clock invalid), count = 500000
        fracsec = 0x0F07A120  # 0x0F << 24 | 500000
        result = fracsec_to_ms(fracsec, 1000000, version=3)
        self.assertAlmostEqual(result, 500.0)

    def test_zero_meas_rate(self):
        self.assertAlmostEqual(fracsec_to_ms(1000, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/daichangyu/Library/Mobile\ Documents/com~apple~CloudDocs/code/PmuSim && python -m unittest tests.test_time_utils -v`

Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add protocol/frames.py utils/ tests/test_time_utils.py
git commit -m "feat: add frame dataclasses and time utilities"
```

---

## Task 3: Frame Parser - Command Frames

**Files:**
- Create: `protocol/parser.py`
- Create: `tests/test_parser.py`

- [ ] **Step 1: Write command frame parser tests**

Create `tests/test_parser.py`:
```python
"""Test frame parser against known protocol data from docs."""
import unittest
from protocol.parser import FrameParser, ParseError


class TestParseCommandFrame(unittest.TestCase):
    """Test command frame parsing with real hex data from protocol docs."""

    def test_v2_request_cfg1(self):
        # V2: aa 42 00 14 67 57 dd 1d 30 47 58 30 30 47 50 31 00 04 a5 cb
        data = bytes.fromhex("aa4200146757dd1d304758303047503100 04a5cb".replace(" ", ""))
        frame = FrameParser.parse(data)
        self.assertEqual(frame.version, 2)
        self.assertEqual(frame.idcode, "0GX00GP1")
        self.assertEqual(frame.soc, 0x6757DD1D)
        self.assertEqual(frame.fracsec, 0)
        self.assertEqual(frame.cmd, 0x0004)

    def test_v2_heartbeat(self):
        data = bytes.fromhex("aa4200146757dd22304758303047503140009cf7")
        frame = FrameParser.parse(data)
        self.assertEqual(frame.version, 2)
        self.assertEqual(frame.cmd, 0x4000)

    def test_v2_ack(self):
        data = bytes.fromhex("aa4200146757dd9d3047583030475031e0007c57")
        frame = FrameParser.parse(data)
        self.assertEqual(frame.cmd, 0xE000)

    def test_v2_open_data(self):
        data = bytes.fromhex("aa4200146757dd1e30475830304750310002bdf7")
        frame = FrameParser.parse(data)
        self.assertEqual(frame.cmd, 0x0002)

    def test_v2_send_cfg2_cmd(self):
        data = bytes.fromhex("aa4200146757dd1e30475830304750318000862d")
        frame = FrameParser.parse(data)
        self.assertEqual(frame.cmd, 0x8000)

    def test_v3_request_cfg1(self):
        # V3: aa 43 00 18 30 47 58 30 30 47 50 31 67 b2 c7 19 00 00 00 00 00 04 ac 08
        data = bytes.fromhex("aa43001830475830304750316 7b2c71900000000 0004ac08".replace(" ", ""))
        frame = FrameParser.parse(data)
        self.assertEqual(frame.version, 3)
        self.assertEqual(frame.idcode, "0GX00GP1")
        self.assertEqual(frame.soc, 0x67B2C719)
        self.assertEqual(frame.fracsec, 0)
        self.assertEqual(frame.cmd, 0x0004)

    def test_v3_ack(self):
        data = bytes.fromhex("aa430018304758303047503167b2c71a00000000e00024bc")
        frame = FrameParser.parse(data)
        self.assertEqual(frame.version, 3)
        self.assertEqual(frame.cmd, 0xE000)

    def test_v3_heartbeat(self):
        data = bytes.fromhex("aa430018304758303047503167b2c71e000000004000f804")
        frame = FrameParser.parse(data)
        self.assertEqual(frame.cmd, 0x4000)

    def test_v3_open_data(self):
        data = bytes.fromhex("aa430018304758303047503167b2c71b000000000002ac2d")
        frame = FrameParser.parse(data)
        self.assertEqual(frame.cmd, 0x0002)

    def test_v3_send_cfg2_cmd(self):
        data = bytes.fromhex("aa430018304758303047503167b2c71a0000000080002f96")
        frame = FrameParser.parse(data)
        self.assertEqual(frame.cmd, 0x8000)

    def test_invalid_sync_byte(self):
        data = bytes.fromhex("bb4200146757dd1d304758303047503100 04a5cb".replace(" ", ""))
        with self.assertRaises(ParseError):
            FrameParser.parse(data)

    def test_crc_mismatch(self):
        # Corrupt last byte
        data = bytes.fromhex("aa4200146757dd1d304758303047503100 04a5cc".replace(" ", ""))
        with self.assertRaises(ParseError):
            FrameParser.parse(data)

    def test_frame_too_short(self):
        data = bytes.fromhex("aa4200")
        with self.assertRaises(ParseError):
            FrameParser.parse(data)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_parser -v`

Expected: FAIL (FrameParser not yet implemented).

- [ ] **Step 3: Implement command frame parser**

Create `protocol/parser.py`:
```python
"""Parse raw bytes into frame objects."""
import struct
from protocol.constants import (
    SYNC_BYTE, FrameType, ProtocolVersion, parse_sync, IDCODE_LEN,
    STN_LEN, CHNAM_LEN,
)
from protocol.crc16 import crc16
from protocol.frames import CommandFrame, ConfigFrame, DataFrame


class ParseError(Exception):
    """Raised when frame data is invalid."""
    pass


class FrameParser:
    """Parse raw frame bytes into typed frame objects."""

    @staticmethod
    def parse(data: bytes) -> CommandFrame | ConfigFrame | DataFrame:
        """Parse a complete frame from raw bytes.

        Args:
            data: Complete frame bytes including SYNC, FRAMESIZE, payload, and CHK.

        Returns:
            A CommandFrame, ConfigFrame, or DataFrame.

        Raises:
            ParseError: If data is invalid, too short, or CRC fails.
        """
        if len(data) < 4:
            raise ParseError(f"Frame too short: {len(data)} bytes (minimum 4)")

        sync = struct.unpack_from("!H", data, 0)[0]
        frame_size = struct.unpack_from("!H", data, 2)[0]

        if len(data) < frame_size:
            raise ParseError(f"Data length {len(data)} < declared frame_size {frame_size}")

        # Verify CRC (last 2 bytes)
        payload = data[:frame_size - 2]
        expected_crc = struct.unpack_from("!H", data, frame_size - 2)[0]
        actual_crc = crc16(payload)
        if actual_crc != expected_crc:
            raise ParseError(
                f"CRC mismatch: expected {expected_crc:#06x}, got {actual_crc:#06x}"
            )

        try:
            frame_type, version = parse_sync(sync)
        except ValueError as e:
            raise ParseError(str(e))

        if frame_type == FrameType.COMMAND:
            return FrameParser._parse_command(data, frame_size, version)
        elif frame_type == FrameType.CFG1:
            return FrameParser._parse_config(data, frame_size, version, cfg_type=1)
        elif frame_type == FrameType.CFG2:
            return FrameParser._parse_config(data, frame_size, version, cfg_type=2)
        elif frame_type == FrameType.DATA:
            return FrameParser._parse_data(data, frame_size, version)
        else:
            raise ParseError(f"Unknown frame type: {frame_type}")

    @staticmethod
    def _parse_command(data: bytes, frame_size: int, version: ProtocolVersion) -> CommandFrame:
        """Parse command frame.

        V2 (20 bytes): SYNC(2) SIZE(2) SOC(4) IDCODE(8) CMD(2) CHK(2)
        V3 (24 bytes): SYNC(2) SIZE(2) IDCODE(8) SOC(4) FRACSEC(4) CMD(2) CHK(2)
        """
        if version == ProtocolVersion.V2:
            if frame_size < 20:
                raise ParseError(f"V2 command frame too short: {frame_size}")
            soc = struct.unpack_from("!I", data, 4)[0]
            idcode = data[8:8 + IDCODE_LEN].decode("ascii", errors="replace")
            fracsec = 0
            cmd = struct.unpack_from("!H", data, 16)[0]
        else:
            if frame_size < 24:
                raise ParseError(f"V3 command frame too short: {frame_size}")
            idcode = data[4:4 + IDCODE_LEN].decode("ascii", errors="replace")
            soc = struct.unpack_from("!I", data, 12)[0]
            fracsec = struct.unpack_from("!I", data, 16)[0]
            cmd = struct.unpack_from("!H", data, 20)[0]

        return CommandFrame(
            version=int(version),
            idcode=idcode,
            soc=soc,
            fracsec=fracsec,
            cmd=cmd,
        )

    @staticmethod
    def _parse_config(data: bytes, frame_size: int,
                      version: ProtocolVersion, cfg_type: int) -> ConfigFrame:
        """Parse config frame (CFG-1 or CFG-2). Implemented in Task 4."""
        raise ParseError("Config frame parsing not yet implemented")

    @staticmethod
    def _parse_data(data: bytes, frame_size: int,
                    version: ProtocolVersion) -> DataFrame:
        """Parse data frame. Implemented in Task 5."""
        raise ParseError("Data frame parsing not yet implemented")
```

- [ ] **Step 4: Run command frame tests**

Run: `python -m unittest tests.test_parser.TestParseCommandFrame -v`

Expected: All command frame tests PASS. Config/data tests will fail (not yet implemented).

- [ ] **Step 5: Commit**

```bash
git add protocol/parser.py tests/test_parser.py
git commit -m "feat: add command frame parser with V2/V3 support"
```

---

## Task 4: Frame Parser - Config Frames

**Files:**
- Modify: `protocol/parser.py` (implement `_parse_config`)
- Modify: `tests/test_parser.py` (add config frame tests)

- [ ] **Step 1: Add config frame tests to `tests/test_parser.py`**

Append to `tests/test_parser.py`:
```python
from protocol.frames import ConfigFrame
from protocol.builder import FrameBuilder  # used in round-trip test


class TestParseConfigFrame(unittest.TestCase):
    """Test config frame parsing."""

    def _make_v2_config(self, cfg_type: int = 1) -> ConfigFrame:
        """Create a known ConfigFrame for testing."""
        return ConfigFrame(
            version=2, cfg_type=cfg_type, idcode="0GX00GP1",
            soc=0x6757DD9D, fracsec=0, d_frame=0,
            meas_rate=1000000, num_pmu=1,
            stn="0000TestStation1", pmu_idcode="0GX00GP1",
            format_flags=0x0011, phnmr=0, annmr=3, dgnmr=1,
            channel_names=["AN1_name_pad12345", "AN2_name_pad12345", "AN3_name_pad12345",
                           "DG01_name_pad1234", "DG02_name_pad1234", "DG03_name_pad1234",
                           "DG04_name_pad1234", "DG05_name_pad1234", "DG06_name_pad1234",
                           "DG07_name_pad1234", "DG08_name_pad1234", "DG09_name_pad1234",
                           "DG10_name_pad1234", "DG11_name_pad1234", "DG12_name_pad1234",
                           "DG13_name_pad1234", "DG14_name_pad1234", "DG15_name_pad1234",
                           "DG16_name_pad1234"],
            phunit=[], anunit=[1000, 546, 10000],
            digunit=[(0x09F6, 0x000F)],
            fnom=1, period=50,
        )

    def _make_v3_config(self, cfg_type: int = 1) -> ConfigFrame:
        """Create a known V3 ConfigFrame for testing."""
        return ConfigFrame(
            version=3, cfg_type=cfg_type, idcode="0GX00GP1",
            soc=0x67B2C71A, fracsec=0, d_frame=0,
            meas_rate=1000000, num_pmu=1,
            stn="0000TestStation1", pmu_idcode="0GX00GP1",
            format_flags=0x0011, phnmr=0, annmr=3, dgnmr=1,
            channel_names=["AN1_name_pad12345", "AN2_name_pad12345", "AN3_name_pad12345",
                           "DG01_name_pad1234", "DG02_name_pad1234", "DG03_name_pad1234",
                           "DG04_name_pad1234", "DG05_name_pad1234", "DG06_name_pad1234",
                           "DG07_name_pad1234", "DG08_name_pad1234", "DG09_name_pad1234",
                           "DG10_name_pad1234", "DG11_name_pad1234", "DG12_name_pad1234",
                           "DG13_name_pad1234", "DG14_name_pad1234", "DG15_name_pad1234",
                           "DG16_name_pad1234"],
            phunit=[], anunit=[1000, 546, 10000],
            digunit=[(0x09F6, 0x000F)],
            fnom=1, period=50,
        )

    def test_v2_cfg1_round_trip(self):
        original = self._make_v2_config(cfg_type=1)
        raw = FrameBuilder.build(original)
        parsed = FrameParser.parse(raw)
        self.assertIsInstance(parsed, ConfigFrame)
        self.assertEqual(parsed.version, 2)
        self.assertEqual(parsed.cfg_type, 1)
        self.assertEqual(parsed.idcode, original.idcode)
        self.assertEqual(parsed.soc, original.soc)
        self.assertEqual(parsed.meas_rate, original.meas_rate)
        self.assertEqual(parsed.num_pmu, 1)
        self.assertEqual(parsed.pmu_idcode, "0GX00GP1")
        self.assertEqual(parsed.phnmr, 0)
        self.assertEqual(parsed.annmr, 3)
        self.assertEqual(parsed.dgnmr, 1)
        self.assertEqual(len(parsed.channel_names), 3 + 16)
        self.assertEqual(parsed.anunit, [1000, 546, 10000])
        self.assertEqual(parsed.digunit, [(0x09F6, 0x000F)])
        self.assertEqual(parsed.fnom, 1)
        self.assertEqual(parsed.period, 50)

    def test_v2_cfg2_round_trip(self):
        original = self._make_v2_config(cfg_type=2)
        raw = FrameBuilder.build(original)
        parsed = FrameParser.parse(raw)
        self.assertEqual(parsed.cfg_type, 2)

    def test_v3_cfg1_round_trip(self):
        original = self._make_v3_config(cfg_type=1)
        raw = FrameBuilder.build(original)
        parsed = FrameParser.parse(raw)
        self.assertIsInstance(parsed, ConfigFrame)
        self.assertEqual(parsed.version, 3)
        self.assertEqual(parsed.cfg_type, 1)
        self.assertEqual(parsed.idcode, "0GX00GP1")
        self.assertEqual(parsed.soc, original.soc)
        self.assertEqual(parsed.fracsec, 0)
        self.assertEqual(parsed.annmr, 3)
        self.assertEqual(parsed.period, 50)

    def test_v3_cfg2_round_trip(self):
        original = self._make_v3_config(cfg_type=2)
        original.period = 100  # CFG-2 may have different period
        raw = FrameBuilder.build(original)
        parsed = FrameParser.parse(raw)
        self.assertEqual(parsed.cfg_type, 2)
        self.assertEqual(parsed.period, 100)

    def test_config_period_ms(self):
        cfg = self._make_v2_config()
        # period=50, fnom=1 (50Hz): 50/100*20ms = 10ms
        self.assertAlmostEqual(cfg.period_ms, 10.0)

    def test_config_analog_factor(self):
        cfg = self._make_v2_config()
        self.assertAlmostEqual(cfg.analog_factor(0), 0.01)    # 1000 * 0.00001
        self.assertAlmostEqual(cfg.analog_factor(1), 0.00546) # 546 * 0.00001
        self.assertAlmostEqual(cfg.analog_factor(2), 0.1)     # 10000 * 0.00001
```

- [ ] **Step 2: Implement `_parse_config` in `protocol/parser.py`**

Replace the `_parse_config` method stub:
```python
    @staticmethod
    def _parse_config(data: bytes, frame_size: int,
                      version: ProtocolVersion, cfg_type: int) -> ConfigFrame:
        """Parse config frame (CFG-1 or CFG-2).

        V2: SYNC(2) SIZE(2) SOC(4) D_FRAME(2) MEAS_RATE(4) NUM_PMU(2) [PMU_DATA...] CHK(2)
        V3: SYNC(2) SIZE(2) DC_IDCODE(8) SOC(4) FRACSEC(4) MEAS_RATE(4) NUM_PMU(2) [PMU_DATA...] CHK(2)

        PMU_DATA: STN(16) IDCODE(8) FORMAT(2) PHNMR(2) ANNMR(2) DGNMR(2)
                  CHNAM(16*(PHNMR+ANNMR+DGNMR*16))
                  PHUNIT(4*PHNMR) ANUNIT(4*ANNMR) DIGUNIT(4*DGNMR)
                  FNOM(2) PERIOD(2)
        """
        offset = 4  # past SYNC + SIZE

        if version == ProtocolVersion.V2:
            soc = struct.unpack_from("!I", data, offset)[0]; offset += 4
            d_frame = struct.unpack_from("!H", data, offset)[0]; offset += 2
            meas_rate = struct.unpack_from("!I", data, offset)[0]; offset += 4
            num_pmu = struct.unpack_from("!H", data, offset)[0]; offset += 2
            fracsec = 0
            dc_idcode = ""
        else:
            dc_idcode = data[offset:offset + IDCODE_LEN].decode("ascii", errors="replace"); offset += IDCODE_LEN
            soc = struct.unpack_from("!I", data, offset)[0]; offset += 4
            fracsec = struct.unpack_from("!I", data, offset)[0]; offset += 4
            meas_rate = struct.unpack_from("!I", data, offset)[0]; offset += 4
            num_pmu = struct.unpack_from("!H", data, offset)[0]; offset += 2
            d_frame = 0

        # Parse first PMU data (we only support num_pmu=1 for now)
        stn_raw = data[offset:offset + STN_LEN]; offset += STN_LEN
        try:
            stn = stn_raw.decode("gbk", errors="replace").rstrip("\x00")
        except Exception:
            stn = stn_raw.decode("ascii", errors="replace").rstrip("\x00")

        pmu_idcode = data[offset:offset + IDCODE_LEN].decode("ascii", errors="replace"); offset += IDCODE_LEN
        format_flags = struct.unpack_from("!H", data, offset)[0]; offset += 2
        phnmr = struct.unpack_from("!H", data, offset)[0]; offset += 2
        annmr = struct.unpack_from("!H", data, offset)[0]; offset += 2
        dgnmr = struct.unpack_from("!H", data, offset)[0]; offset += 2

        # Channel names: phasors + analogs + digitals (16 per word)
        num_channels = phnmr + annmr + dgnmr * 16
        channel_names = []
        for _ in range(num_channels):
            name_raw = data[offset:offset + CHNAM_LEN]; offset += CHNAM_LEN
            try:
                name = name_raw.decode("gbk", errors="replace").rstrip("\x00")
            except Exception:
                name = name_raw.decode("ascii", errors="replace").rstrip("\x00")
            channel_names.append(name)

        # Phasor conversion factors
        phunit = []
        for _ in range(phnmr):
            phunit.append(struct.unpack_from("!I", data, offset)[0]); offset += 4

        # Analog conversion factors
        anunit = []
        for _ in range(annmr):
            anunit.append(struct.unpack_from("!I", data, offset)[0]); offset += 4

        # Digital status word masks
        digunit = []
        for _ in range(dgnmr):
            normal_status = struct.unpack_from("!H", data, offset)[0]; offset += 2
            valid_mask = struct.unpack_from("!H", data, offset)[0]; offset += 2
            digunit.append((normal_status, valid_mask))

        fnom = struct.unpack_from("!H", data, offset)[0]; offset += 2
        period = struct.unpack_from("!H", data, offset)[0]; offset += 2

        # Primary IDCODE: V3 uses DC_IDCODE from header, V2 uses per-PMU IDCODE
        idcode = dc_idcode if dc_idcode else pmu_idcode

        return ConfigFrame(
            version=int(version), cfg_type=cfg_type, idcode=idcode,
            soc=soc, fracsec=fracsec, d_frame=d_frame,
            meas_rate=meas_rate, num_pmu=num_pmu,
            stn=stn, pmu_idcode=pmu_idcode,
            format_flags=format_flags,
            phnmr=phnmr, annmr=annmr, dgnmr=dgnmr,
            channel_names=channel_names,
            phunit=phunit, anunit=anunit, digunit=digunit,
            fnom=fnom, period=period,
        )
```

- [ ] **Step 3: Run tests (config tests will fail because FrameBuilder not yet implemented)**

Run: `python -m unittest tests.test_parser.TestParseCommandFrame -v`

Expected: All command tests still PASS. Config round-trip tests need FrameBuilder (Task 6). Skip to Task 5, then come back.

**Note:** Config frame round-trip tests depend on FrameBuilder (Task 6). These tests will be validated after Task 6.

- [ ] **Step 4: Commit**

```bash
git add protocol/parser.py tests/test_parser.py
git commit -m "feat: add config frame parser for V2/V3"
```

---

## Task 5: Frame Parser - Data Frames

**Files:**
- Modify: `protocol/parser.py` (implement `_parse_data`)
- Modify: `tests/test_parser.py` (add data frame tests)

- [ ] **Step 1: Add data frame tests to `tests/test_parser.py`**

Append to `tests/test_parser.py`:
```python
class TestParseDataFrame(unittest.TestCase):
    """Test data frame parsing with real hex data from docs."""

    def test_v2_data_frame(self):
        # V2 data: aa 02 00 2c 67 a9 9d 11 00 0d 94 90
        #          00 00  (STAT)
        #          00 00  (FREQ)
        #          00 00  (DFREQ)
        #          01 2c 0b b8 23 d7 00 c8 00 00 00 00 00 00 00 00 23 d7 00 00 00 00  (ANALOG x11)
        #          00 0a  (DIGITAL x1)
        #          21 f3  (CHK)
        data = bytes.fromhex(
            "aa02002c"
            "67a99d11"
            "000d9490"
            "0000"
            "0000"
            "0000"
            "012c0bb823d700c80000000000000000"
            "23d700000000"
            "000a"
            "21f3"
        )
        frame = FrameParser.parse(data, phnmr=0, annmr=11, dgnmr=1)
        self.assertIsInstance(frame, DataFrame)
        self.assertEqual(frame.version, 2)
        self.assertEqual(frame.idcode, "")  # V2 data has no IDCODE
        self.assertEqual(frame.soc, 0x67A99D11)
        self.assertEqual(frame.fracsec, 0x000D9490)
        self.assertEqual(frame.stat, 0x0000)
        self.assertEqual(frame.freq, 0)
        self.assertEqual(frame.dfreq, 0)
        self.assertEqual(len(frame.analog), 11)
        self.assertEqual(frame.analog[0], 0x012C)   # 300
        self.assertEqual(frame.analog[1], 0x0BB8)   # 3000
        self.assertEqual(frame.analog[2], 0x23D7)   # 9175
        self.assertEqual(frame.analog[3], 0x00C8)   # 200
        self.assertEqual(len(frame.digital), 1)
        self.assertEqual(frame.digital[0], 0x000A)

    def test_v3_data_frame(self):
        # V3 data: aa 03 00 34 30 47 58 30 30 47 50 31
        #          67 b2 c7 1d 00 00 00 00
        #          00 00  (STAT)
        #          00 00  (FREQ)
        #          00 00  (DFREQ)
        #          01 90 01 2c 23 e1 00 00 00 00 00 00 00 00 00 00 23 e1 00 00 00 00  (ANALOG x11)
        #          00 0a  (DIGITAL x1)
        #          e8 84  (CHK)
        data = bytes.fromhex(
            "aa030034"
            "3047583030475031"
            "67b2c71d"
            "00000000"
            "0000"
            "0000"
            "0000"
            "0190012c23e10000000000000000000023e100000000"
            "000a"
            "e884"
        )
        frame = FrameParser.parse(data, phnmr=0, annmr=11, dgnmr=1)
        self.assertIsInstance(frame, DataFrame)
        self.assertEqual(frame.version, 3)
        self.assertEqual(frame.idcode, "0GX00GP1")
        self.assertEqual(frame.soc, 0x67B2C71D)
        self.assertEqual(frame.fracsec, 0)
        self.assertEqual(frame.stat, 0)
        self.assertEqual(len(frame.analog), 11)
        self.assertEqual(frame.analog[0], 0x0190)  # 400
        self.assertEqual(frame.analog[1], 0x012C)  # 300
        self.assertEqual(frame.analog[2], 0x23E1)  # 9185
        self.assertEqual(len(frame.digital), 1)
        self.assertEqual(frame.digital[0], 0x000A)
```

- [ ] **Step 2: Update `FrameParser.parse` to accept optional config info for data frames**

Update the `parse` method signature and data frame dispatch in `protocol/parser.py`:
```python
    @staticmethod
    def parse(data: bytes, phnmr: int = 0, annmr: int = 0,
              dgnmr: int = 0) -> CommandFrame | ConfigFrame | DataFrame:
        """Parse a complete frame from raw bytes.

        Args:
            data: Complete frame bytes including SYNC, FRAMESIZE, payload, and CHK.
            phnmr: Phasor count from config frame (needed for data frames).
            annmr: Analog count from config frame (needed for data frames).
            dgnmr: Digital word count from config frame (needed for data frames).
        ...
        """
```

Update the dispatch to pass these through:
```python
        elif frame_type == FrameType.DATA:
            return FrameParser._parse_data(data, frame_size, version, phnmr, annmr, dgnmr)
```

- [ ] **Step 3: Implement `_parse_data`**

Replace the stub in `protocol/parser.py`:
```python
    @staticmethod
    def _parse_data(data: bytes, frame_size: int, version: ProtocolVersion,
                    phnmr: int, annmr: int, dgnmr: int) -> DataFrame:
        """Parse data frame.

        V2: SYNC(2) SIZE(2) SOC(4) FRACSEC(4) STAT(2) [phasors] FREQ(2) DFREQ(2)
            [analog] [digital] CHK(2)
        V3: SYNC(2) SIZE(2) IDCODE(8) SOC(4) FRACSEC(4) STAT(2) [phasors] FREQ(2) DFREQ(2)
            [analog] [digital] CHK(2)
        """
        offset = 4  # past SYNC + SIZE

        if version == ProtocolVersion.V2:
            idcode = ""
            soc = struct.unpack_from("!I", data, offset)[0]; offset += 4
            fracsec = struct.unpack_from("!I", data, offset)[0]; offset += 4
        else:
            idcode = data[offset:offset + IDCODE_LEN].decode("ascii", errors="replace"); offset += IDCODE_LEN
            soc = struct.unpack_from("!I", data, offset)[0]; offset += 4
            fracsec = struct.unpack_from("!I", data, offset)[0]; offset += 4

        stat = struct.unpack_from("!H", data, offset)[0]; offset += 2

        # Phasors: depends on FORMAT (16-bit int = 4 bytes per phasor)
        phasors = []
        for _ in range(phnmr):
            mag = struct.unpack_from("!h", data, offset)[0]; offset += 2
            ang = struct.unpack_from("!h", data, offset)[0]; offset += 2
            phasors.append((mag, ang))

        freq = struct.unpack_from("!h", data, offset)[0]; offset += 2
        dfreq = struct.unpack_from("!h", data, offset)[0]; offset += 2

        analog = []
        for _ in range(annmr):
            analog.append(struct.unpack_from("!h", data, offset)[0]); offset += 2

        digital = []
        for _ in range(dgnmr):
            digital.append(struct.unpack_from("!H", data, offset)[0]); offset += 2

        return DataFrame(
            version=int(version), idcode=idcode,
            soc=soc, fracsec=fracsec, stat=stat,
            phasors=phasors, freq=freq, dfreq=dfreq,
            analog=analog, digital=digital,
        )
```

- [ ] **Step 4: Run all parser tests**

Run: `python -m unittest tests.test_parser.TestParseCommandFrame tests.test_parser.TestParseDataFrame -v`

Expected: All command and data frame tests PASS.

- [ ] **Step 5: Commit**

```bash
git add protocol/parser.py tests/test_parser.py
git commit -m "feat: add data frame parser for V2/V3"
```

---

## Task 6: Frame Builder

**Files:**
- Create: `protocol/builder.py`
- Create: `tests/test_builder.py`

- [ ] **Step 1: Write builder tests**

Create `tests/test_builder.py`:
```python
"""Test frame builder: build frames and verify via round-trip with parser."""
import unittest
from protocol.frames import CommandFrame, ConfigFrame, DataFrame
from protocol.builder import FrameBuilder
from protocol.parser import FrameParser
from protocol.crc16 import crc16


class TestBuildCommandFrame(unittest.TestCase):
    def test_v2_build_matches_doc(self):
        """Build V2 command and compare to known hex from protocol doc."""
        frame = CommandFrame(version=2, idcode="0GX00GP1",
                             soc=0x6757DD1D, fracsec=0, cmd=0x0004)
        raw = FrameBuilder.build(frame)
        expected = bytes.fromhex("aa4200146757dd1d3047583030475031 0004".replace(" ", ""))
        # Compare payload (excluding CRC)
        self.assertEqual(raw[:-2], expected)
        # Verify CRC matches doc
        self.assertEqual(raw[-2:], bytes.fromhex("a5cb"))

    def test_v3_build_matches_doc(self):
        frame = CommandFrame(version=3, idcode="0GX00GP1",
                             soc=0x67B2C719, fracsec=0, cmd=0x0004)
        raw = FrameBuilder.build(frame)
        expected = bytes.fromhex("aa43001830475830304750316 7b2c71900000000 0004".replace(" ", ""))
        self.assertEqual(raw[:-2], expected)
        self.assertEqual(raw[-2:], bytes.fromhex("ac08"))

    def test_v2_round_trip(self):
        frame = CommandFrame(version=2, idcode="TESTID01", soc=1000000, fracsec=0, cmd=0x4000)
        raw = FrameBuilder.build(frame)
        parsed = FrameParser.parse(raw)
        self.assertEqual(parsed.version, 2)
        self.assertEqual(parsed.idcode, "TESTID01")
        self.assertEqual(parsed.soc, 1000000)
        self.assertEqual(parsed.cmd, 0x4000)

    def test_v3_round_trip(self):
        frame = CommandFrame(version=3, idcode="TESTID01", soc=1000000, fracsec=0x0F000000, cmd=0xE000)
        raw = FrameBuilder.build(frame)
        parsed = FrameParser.parse(raw)
        self.assertEqual(parsed.version, 3)
        self.assertEqual(parsed.idcode, "TESTID01")
        self.assertEqual(parsed.fracsec, 0x0F000000)
        self.assertEqual(parsed.cmd, 0xE000)


class TestBuildConfigFrame(unittest.TestCase):
    def _make_config(self, version: int, cfg_type: int = 1) -> ConfigFrame:
        return ConfigFrame(
            version=version, cfg_type=cfg_type, idcode="0GX00GP1",
            soc=1000000, fracsec=0, d_frame=0,
            meas_rate=1000000, num_pmu=1,
            stn="0000TestStation1", pmu_idcode="0GX00GP1",
            format_flags=0x0011, phnmr=0, annmr=3, dgnmr=1,
            channel_names=["AnalogChannel001", "AnalogChannel002", "AnalogChannel003",
                           "DigitalChan0001", "DigitalChan0002", "DigitalChan0003",
                           "DigitalChan0004", "DigitalChan0005", "DigitalChan0006",
                           "DigitalChan0007", "DigitalChan0008", "DigitalChan0009",
                           "DigitalChan0010", "DigitalChan0011", "DigitalChan0012",
                           "DigitalChan0013", "DigitalChan0014", "DigitalChan0015",
                           "DigitalChan0016"],
            phunit=[], anunit=[1000, 546, 10000],
            digunit=[(0x09F6, 0x000F)],
            fnom=1, period=50,
        )

    def test_v2_cfg1_round_trip(self):
        original = self._make_config(version=2, cfg_type=1)
        raw = FrameBuilder.build(original)
        parsed = FrameParser.parse(raw)
        self.assertEqual(parsed.version, 2)
        self.assertEqual(parsed.cfg_type, 1)
        self.assertEqual(parsed.pmu_idcode, "0GX00GP1")
        self.assertEqual(parsed.annmr, 3)
        self.assertEqual(parsed.anunit, [1000, 546, 10000])
        self.assertEqual(parsed.period, 50)

    def test_v3_cfg2_round_trip(self):
        original = self._make_config(version=3, cfg_type=2)
        original.period = 100
        raw = FrameBuilder.build(original)
        parsed = FrameParser.parse(raw)
        self.assertEqual(parsed.version, 3)
        self.assertEqual(parsed.cfg_type, 2)
        self.assertEqual(parsed.period, 100)

    def test_crc_valid(self):
        frame = self._make_config(version=2)
        raw = FrameBuilder.build(frame)
        payload = raw[:-2]
        expected_crc = int.from_bytes(raw[-2:], "big")
        self.assertEqual(crc16(payload), expected_crc)


class TestBuildDataFrame(unittest.TestCase):
    def test_v2_round_trip(self):
        original = DataFrame(
            version=2, idcode="", soc=0x67A99D11, fracsec=0x000D9490,
            stat=0, phasors=[], freq=0, dfreq=0,
            analog=[300, 3000, 9175, 200, 0, 0, 0, 0, 9175, 0, 0],
            digital=[0x000A],
        )
        raw = FrameBuilder.build(original, phnmr=0, annmr=11, dgnmr=1)
        parsed = FrameParser.parse(raw, phnmr=0, annmr=11, dgnmr=1)
        self.assertEqual(parsed.soc, original.soc)
        self.assertEqual(parsed.fracsec, original.fracsec)
        self.assertEqual(parsed.analog, original.analog)
        self.assertEqual(parsed.digital, original.digital)

    def test_v3_round_trip(self):
        original = DataFrame(
            version=3, idcode="0GX00GP1", soc=0x67B2C71D, fracsec=0,
            stat=0, phasors=[], freq=0, dfreq=0,
            analog=[400, 300, 9185, 0, 0, 0, 0, 0, 9185, 0, 0],
            digital=[0x000A],
        )
        raw = FrameBuilder.build(original, phnmr=0, annmr=11, dgnmr=1)
        parsed = FrameParser.parse(raw, phnmr=0, annmr=11, dgnmr=1)
        self.assertEqual(parsed.version, 3)
        self.assertEqual(parsed.idcode, "0GX00GP1")
        self.assertEqual(parsed.analog, original.analog)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Implement `protocol/builder.py`**

Create `protocol/builder.py`:
```python
"""Build frame bytes from frame objects."""
import struct
from protocol.constants import (
    FrameType, ProtocolVersion, SYNC_VERSION, SYNC_BYTE,
    IDCODE_LEN, STN_LEN, CHNAM_LEN,
)
from protocol.crc16 import crc16
from protocol.frames import CommandFrame, ConfigFrame, DataFrame


class FrameBuilder:
    """Serialize frame objects into raw bytes."""

    @staticmethod
    def build(frame: CommandFrame | ConfigFrame | DataFrame,
              phnmr: int = 0, annmr: int = 0, dgnmr: int = 0) -> bytes:
        """Build complete frame bytes including SYNC, FRAMESIZE, payload, and CHK.

        Args:
            frame: Frame object to serialize.
            phnmr/annmr/dgnmr: Only needed for DataFrame (ignored for other types).
        """
        if isinstance(frame, CommandFrame):
            return FrameBuilder._build_command(frame)
        elif isinstance(frame, ConfigFrame):
            return FrameBuilder._build_config(frame)
        elif isinstance(frame, DataFrame):
            return FrameBuilder._build_data(frame, phnmr, annmr, dgnmr)
        else:
            raise TypeError(f"Unknown frame type: {type(frame)}")

    @staticmethod
    def _build_command(frame: CommandFrame) -> bytes:
        """Build command frame bytes.

        V2 (20B): SYNC(2) SIZE(2) SOC(4) IDCODE(8) CMD(2) CHK(2)
        V3 (24B): SYNC(2) SIZE(2) IDCODE(8) SOC(4) FRACSEC(4) CMD(2) CHK(2)
        """
        version = ProtocolVersion(frame.version)
        sync = (SYNC_BYTE << 8) | (FrameType.COMMAND << 4) | SYNC_VERSION[version]
        idcode_bytes = frame.idcode.encode("ascii")[:IDCODE_LEN].ljust(IDCODE_LEN, b"\x00")

        if version == ProtocolVersion.V2:
            frame_size = 20
            payload = struct.pack("!HH", sync, frame_size)
            payload += struct.pack("!I", frame.soc)
            payload += idcode_bytes
            payload += struct.pack("!H", frame.cmd)
        else:
            frame_size = 24
            payload = struct.pack("!HH", sync, frame_size)
            payload += idcode_bytes
            payload += struct.pack("!I", frame.soc)
            payload += struct.pack("!I", frame.fracsec)
            payload += struct.pack("!H", frame.cmd)

        chk = crc16(payload)
        return payload + struct.pack("!H", chk)

    @staticmethod
    def _build_config(frame: ConfigFrame) -> bytes:
        """Build config frame bytes.

        V2: SYNC(2) SIZE(2) SOC(4) D_FRAME(2) MEAS_RATE(4) NUM_PMU(2) [PMU_DATA] CHK(2)
        V3: SYNC(2) SIZE(2) DC_IDCODE(8) SOC(4) FRACSEC(4) MEAS_RATE(4) NUM_PMU(2) [PMU_DATA] CHK(2)
        """
        version = ProtocolVersion(frame.version)
        frame_type = FrameType.CFG1 if frame.cfg_type == 1 else FrameType.CFG2
        sync = (SYNC_BYTE << 8) | (frame_type << 4) | SYNC_VERSION[version]

        # Build header (without SYNC/SIZE prefix and without CHK)
        header = b""
        if version == ProtocolVersion.V2:
            header += struct.pack("!I", frame.soc)
            header += struct.pack("!H", frame.d_frame)
            header += struct.pack("!I", frame.meas_rate)
            header += struct.pack("!H", frame.num_pmu)
        else:
            idcode_bytes = frame.idcode.encode("ascii")[:IDCODE_LEN].ljust(IDCODE_LEN, b"\x00")
            header += idcode_bytes
            header += struct.pack("!I", frame.soc)
            header += struct.pack("!I", frame.fracsec)
            header += struct.pack("!I", frame.meas_rate)
            header += struct.pack("!H", frame.num_pmu)

        # PMU data
        pmu_data = b""
        stn_bytes = frame.stn.encode("gbk", errors="replace")[:STN_LEN].ljust(STN_LEN, b"\x00")
        pmu_data += stn_bytes
        pmu_id_bytes = frame.pmu_idcode.encode("ascii")[:IDCODE_LEN].ljust(IDCODE_LEN, b"\x00")
        pmu_data += pmu_id_bytes
        pmu_data += struct.pack("!H", frame.format_flags)
        pmu_data += struct.pack("!H", frame.phnmr)
        pmu_data += struct.pack("!H", frame.annmr)
        pmu_data += struct.pack("!H", frame.dgnmr)

        # Channel names
        for name in frame.channel_names:
            name_bytes = name.encode("gbk", errors="replace")[:CHNAM_LEN].ljust(CHNAM_LEN, b"\x00")
            pmu_data += name_bytes

        # Conversion factors
        for ph in frame.phunit:
            pmu_data += struct.pack("!I", ph)
        for an in frame.anunit:
            pmu_data += struct.pack("!I", an)
        for normal_status, valid_mask in frame.digunit:
            pmu_data += struct.pack("!HH", normal_status, valid_mask)

        pmu_data += struct.pack("!H", frame.fnom)
        pmu_data += struct.pack("!H", frame.period)

        # Calculate frame size: SYNC(2) + SIZE(2) + header + pmu_data + CHK(2)
        frame_size = 2 + 2 + len(header) + len(pmu_data) + 2

        payload = struct.pack("!HH", sync, frame_size) + header + pmu_data
        chk = crc16(payload)
        return payload + struct.pack("!H", chk)

    @staticmethod
    def _build_data(frame: DataFrame, phnmr: int, annmr: int, dgnmr: int) -> bytes:
        """Build data frame bytes.

        V2: SYNC(2) SIZE(2) SOC(4) FRACSEC(4) STAT(2) [phasors] FREQ(2) DFREQ(2)
            [analog] [digital] CHK(2)
        V3: SYNC(2) SIZE(2) IDCODE(8) SOC(4) FRACSEC(4) STAT(2) [phasors] FREQ(2) DFREQ(2)
            [analog] [digital] CHK(2)
        """
        version = ProtocolVersion(frame.version)
        sync = (SYNC_BYTE << 8) | (FrameType.DATA << 4) | SYNC_VERSION[version]

        body = b""
        if version == ProtocolVersion.V3:
            idcode_bytes = frame.idcode.encode("ascii")[:IDCODE_LEN].ljust(IDCODE_LEN, b"\x00")
            body += idcode_bytes

        body += struct.pack("!I", frame.soc)
        body += struct.pack("!I", frame.fracsec)
        body += struct.pack("!H", frame.stat)

        for mag, ang in frame.phasors:
            body += struct.pack("!hh", mag, ang)

        body += struct.pack("!h", frame.freq)
        body += struct.pack("!h", frame.dfreq)

        for val in frame.analog:
            body += struct.pack("!h", val)

        for val in frame.digital:
            body += struct.pack("!H", val)

        frame_size = 2 + 2 + len(body) + 2  # SYNC + SIZE + body + CHK
        payload = struct.pack("!HH", sync, frame_size) + body
        chk = crc16(payload)
        return payload + struct.pack("!H", chk)
```

- [ ] **Step 3: Run all tests**

Run: `python -m unittest discover tests -v`

Expected: All tests PASS (CRC, time utils, command frames, data frames, builder round-trips, config round-trips).

- [ ] **Step 4: Commit**

```bash
git add protocol/builder.py tests/test_builder.py
git commit -m "feat: add frame builder with round-trip tests"
```

---

## Task 7: Network Session + MasterStation

**Files:**
- Create: `network/__init__.py`
- Create: `network/session.py`
- Create: `network/master.py`

- [ ] **Step 1: Create `network/__init__.py`**

```python
```

- [ ] **Step 2: Create `network/session.py`**

```python
"""Substation session management and state machine."""
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from protocol.frames import ConfigFrame


class SessionState(Enum):
    CONNECTED = auto()         # At least one pipe connected
    CFG1_RECEIVED = auto()     # CFG-1 received from substation
    CFG2_SENT = auto()         # CFG-2 sent to substation
    STREAMING = auto()         # Real-time data flowing
    DISCONNECTED = auto()      # All connections closed


@dataclass
class SubStationSession:
    """Represents one connected substation with its management and data pipes."""
    idcode: str
    version: int = 0                    # Detected from first frame
    peer_ip: str = ""                   # Remote IP for V2 pairing
    state: SessionState = SessionState.CONNECTED

    # Asyncio streams (set when pipes connect)
    mgmt_reader: asyncio.StreamReader | None = field(default=None, repr=False)
    mgmt_writer: asyncio.StreamWriter | None = field(default=None, repr=False)
    data_reader: asyncio.StreamReader | None = field(default=None, repr=False)
    data_writer: asyncio.StreamWriter | None = field(default=None, repr=False)

    cfg1: ConfigFrame | None = None
    cfg2: ConfigFrame | None = None

    last_heartbeat: float = field(default_factory=time.time)
    missed_heartbeats: int = 0

    @property
    def mgmt_connected(self) -> bool:
        return self.mgmt_writer is not None and not self.mgmt_writer.is_closing()

    @property
    def data_connected(self) -> bool:
        return self.data_writer is not None and not self.data_writer.is_closing()

    @property
    def fully_connected(self) -> bool:
        return self.mgmt_connected and self.data_connected

    def close(self):
        """Close all connections."""
        for writer in (self.mgmt_writer, self.data_writer):
            if writer and not writer.is_closing():
                writer.close()
        self.state = SessionState.DISCONNECTED
```

- [ ] **Step 3: Create `network/master.py`**

```python
"""MasterStation: asyncio TCP servers for management and data pipes."""
import asyncio
import logging
import queue
import struct
import time
from protocol.constants import (
    FrameType, ProtocolVersion, Cmd, IDCODE_LEN, SYNC_BYTE, parse_sync,
)
from protocol.parser import FrameParser, ParseError
from protocol.builder import FrameBuilder
from protocol.frames import CommandFrame, ConfigFrame, DataFrame
from network.session import SubStationSession, SessionState
from utils.time_utils import current_soc

logger = logging.getLogger(__name__)


class MasterStation:
    """PMU master station simulator managing multiple substation connections."""

    def __init__(self, event_queue: queue.Queue, mgmt_port: int = 8000,
                 data_port: int = 8001, heartbeat_interval: float = 30.0):
        self.event_queue = event_queue
        self.mgmt_port = mgmt_port
        self.data_port = data_port
        self.heartbeat_interval = heartbeat_interval

        self.sessions: dict[str, SubStationSession] = {}
        # Pending connections waiting for pairing (keyed by IP for V2, idcode for V3)
        self._pending_mgmt: dict[str, SubStationSession] = {}
        self._pending_data: dict[str, tuple[asyncio.StreamReader, asyncio.StreamWriter, str]] = {}

        self._mgmt_server: asyncio.Server | None = None
        self._data_server: asyncio.Server | None = None
        self._cmd_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._tasks: list[asyncio.Task] = []

    def send_command(self, cmd_type: str, **kwargs):
        """Thread-safe: enqueue a command from UI to be processed in asyncio loop."""
        self._cmd_queue.put_nowait((cmd_type, kwargs))

    async def start(self):
        """Start management and data TCP servers."""
        self._running = True
        self._mgmt_server = await asyncio.start_server(
            self._handle_mgmt_connection, "0.0.0.0", self.mgmt_port
        )
        self._data_server = await asyncio.start_server(
            self._handle_data_connection, "0.0.0.0", self.data_port
        )
        self._tasks.append(asyncio.create_task(self._command_loop()))
        self._tasks.append(asyncio.create_task(self._heartbeat_loop()))
        self._emit("server_started", mgmt_port=self.mgmt_port, data_port=self.data_port)
        logger.info(f"MasterStation started on mgmt:{self.mgmt_port} data:{self.data_port}")

    async def stop(self):
        """Stop servers and close all sessions."""
        self._running = False
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()
        if self._mgmt_server:
            self._mgmt_server.close()
            await self._mgmt_server.wait_closed()
        if self._data_server:
            self._data_server.close()
            await self._data_server.wait_closed()
        for session in list(self.sessions.values()):
            session.close()
        self.sessions.clear()
        self._pending_mgmt.clear()
        self._pending_data.clear()
        self._emit("server_stopped")
        logger.info("MasterStation stopped")

    # --- Connection Handlers ---

    async def _handle_mgmt_connection(self, reader: asyncio.StreamReader,
                                       writer: asyncio.StreamWriter):
        """Handle a new management pipe connection."""
        peer = writer.get_extra_info("peername")
        peer_ip = peer[0] if peer else "unknown"
        logger.info(f"Management connection from {peer_ip}")

        try:
            # Read first frame to identify substation
            frame_data = await self._read_frame(reader)
            frame = FrameParser.parse(frame_data)
            version = frame.version

            if isinstance(frame, (CommandFrame, ConfigFrame)):
                idcode = frame.idcode
            else:
                logger.warning(f"Unexpected first frame type on mgmt pipe: {type(frame)}")
                writer.close()
                return

            # Find or create session
            session = self._get_or_create_session(idcode, peer_ip, version)
            session.mgmt_reader = reader
            session.mgmt_writer = writer
            session.version = version

            self._emit("mgmt_connected", idcode=idcode, peer_ip=peer_ip)

            # Process the first frame
            await self._process_mgmt_frame(session, frame, frame_data)

            # Continue reading management frames
            while self._running and not reader.at_eof():
                try:
                    frame_data = await self._read_frame(reader)
                    frame = FrameParser.parse(frame_data)
                    await self._process_mgmt_frame(session, frame, frame_data)
                except ParseError as e:
                    self._emit("parse_error", idcode=idcode, error=str(e))
                except asyncio.IncompleteReadError:
                    break

        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"Management connection error: {e}")
        finally:
            if not writer.is_closing():
                writer.close()
            # Find session by writer and mark mgmt disconnected
            for s in self.sessions.values():
                if s.mgmt_writer is writer:
                    s.mgmt_writer = None
                    if not s.data_connected:
                        s.state = SessionState.DISCONNECTED
                        self._emit("session_disconnected", idcode=s.idcode)
                    break

    async def _handle_data_connection(self, reader: asyncio.StreamReader,
                                       writer: asyncio.StreamWriter):
        """Handle a new data pipe connection."""
        peer = writer.get_extra_info("peername")
        peer_ip = peer[0] if peer else "unknown"
        logger.info(f"Data connection from {peer_ip}")

        session = None
        try:
            # Read first frame to determine version
            frame_data = await self._read_frame(reader)

            # Peek at SYNC to determine version
            sync = struct.unpack_from("!H", frame_data, 0)[0]
            _, version = parse_sync(sync)

            if version == ProtocolVersion.V3:
                # V3 data frames contain IDCODE
                idcode = frame_data[4:4 + IDCODE_LEN].decode("ascii", errors="replace")
                session = self._get_or_create_session(idcode, peer_ip, int(version))
            else:
                # V2 data frames don't contain IDCODE - pair by IP
                session = self._find_session_by_ip(peer_ip)
                if not session:
                    logger.warning(f"No management session found for data connection from {peer_ip}")
                    writer.close()
                    return

            session.data_reader = reader
            session.data_writer = writer
            self._emit("data_connected", idcode=session.idcode, peer_ip=peer_ip)

            # Parse and process the first data frame
            if session.cfg2:
                frame = FrameParser.parse(
                    frame_data,
                    phnmr=session.cfg2.phnmr,
                    annmr=session.cfg2.annmr,
                    dgnmr=session.cfg2.dgnmr,
                )
                if isinstance(frame, DataFrame):
                    if not frame.idcode:
                        frame.idcode = session.idcode
                    self._emit("data_frame", idcode=session.idcode, frame=frame)

            # Continue reading data frames
            while self._running and not reader.at_eof():
                try:
                    frame_data = await self._read_frame(reader)
                    if session.cfg2:
                        frame = FrameParser.parse(
                            frame_data,
                            phnmr=session.cfg2.phnmr,
                            annmr=session.cfg2.annmr,
                            dgnmr=session.cfg2.dgnmr,
                        )
                        if isinstance(frame, DataFrame):
                            if not frame.idcode:
                                frame.idcode = session.idcode
                            self._emit("data_frame", idcode=session.idcode, frame=frame)
                    self._emit("raw_frame", idcode=session.idcode, direction="recv",
                               data=frame_data)
                except ParseError as e:
                    self._emit("parse_error", idcode=session.idcode if session else "?",
                               error=str(e))
                except asyncio.IncompleteReadError:
                    break

        except asyncio.IncompleteReadError:
            pass
        except Exception as e:
            logger.error(f"Data connection error: {e}")
        finally:
            if not writer.is_closing():
                writer.close()
            if session:
                session.data_writer = None
                if not session.mgmt_connected:
                    session.state = SessionState.DISCONNECTED
                    self._emit("session_disconnected", idcode=session.idcode)

    # --- Frame Processing ---

    async def _process_mgmt_frame(self, session: SubStationSession, frame, raw: bytes):
        """Process a frame received on the management pipe."""
        self._emit("raw_frame", idcode=session.idcode, direction="recv", data=raw)

        if isinstance(frame, CommandFrame):
            if frame.cmd == Cmd.HEARTBEAT:
                session.last_heartbeat = time.time()
                session.missed_heartbeats = 0
                self._emit("heartbeat_recv", idcode=session.idcode)
            elif frame.cmd == Cmd.ACK:
                self._emit("ack_recv", idcode=session.idcode)
            elif frame.cmd == Cmd.NACK:
                self._emit("nack_recv", idcode=session.idcode)

        elif isinstance(frame, ConfigFrame):
            if frame.cfg_type == 1:
                session.cfg1 = frame
                session.state = SessionState.CFG1_RECEIVED
                self._emit("cfg1_received", idcode=session.idcode, cfg=frame)
            elif frame.cfg_type == 2:
                session.cfg2 = frame
                self._emit("cfg2_received", idcode=session.idcode, cfg=frame)

    # --- Command Sending ---

    async def _send_command(self, session: SubStationSession, cmd: int):
        """Send a command frame to a substation via management pipe."""
        if not session.mgmt_connected:
            self._emit("error", idcode=session.idcode, error="Management pipe not connected")
            return

        frame = CommandFrame(
            version=session.version,
            idcode=session.idcode,
            soc=current_soc(),
            fracsec=0,
            cmd=cmd,
        )
        raw = FrameBuilder.build(frame)
        session.mgmt_writer.write(raw)
        await session.mgmt_writer.drain()
        self._emit("raw_frame", idcode=session.idcode, direction="send", data=raw)

    async def _send_cfg2(self, session: SubStationSession, period: int | None = None):
        """Send CFG-2 config frame to substation."""
        if not session.cfg1:
            self._emit("error", idcode=session.idcode, error="No CFG-1 available")
            return
        if not session.mgmt_connected:
            self._emit("error", idcode=session.idcode, error="Management pipe not connected")
            return

        # Build CFG-2 based on CFG-1
        cfg2 = ConfigFrame(
            version=session.cfg1.version,
            cfg_type=2,
            idcode=session.cfg1.idcode,
            soc=current_soc(),
            fracsec=0,
            d_frame=session.cfg1.d_frame,
            meas_rate=session.cfg1.meas_rate,
            num_pmu=session.cfg1.num_pmu,
            stn=session.cfg1.stn,
            pmu_idcode=session.cfg1.pmu_idcode,
            format_flags=session.cfg1.format_flags,
            phnmr=session.cfg1.phnmr,
            annmr=session.cfg1.annmr,
            dgnmr=session.cfg1.dgnmr,
            channel_names=list(session.cfg1.channel_names),
            phunit=list(session.cfg1.phunit),
            anunit=list(session.cfg1.anunit),
            digunit=list(session.cfg1.digunit),
            fnom=session.cfg1.fnom,
            period=period if period is not None else session.cfg1.period,
        )
        session.cfg2 = cfg2

        raw = FrameBuilder.build(cfg2)
        session.mgmt_writer.write(raw)
        await session.mgmt_writer.drain()
        session.state = SessionState.CFG2_SENT
        self._emit("raw_frame", idcode=session.idcode, direction="send", data=raw)
        self._emit("cfg2_sent", idcode=session.idcode, cfg=cfg2)

    # --- Command Loop (processes UI commands) ---

    async def _command_loop(self):
        """Process commands from the UI thread."""
        while self._running:
            try:
                cmd_type, kwargs = await asyncio.wait_for(self._cmd_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            idcode = kwargs.get("idcode", "")
            session = self.sessions.get(idcode)

            if cmd_type == "request_cfg1" and session:
                await self._send_command(session, Cmd.SEND_CFG1)
            elif cmd_type == "send_cfg2_cmd" and session:
                await self._send_command(session, Cmd.SEND_CFG2_CMD)
            elif cmd_type == "send_cfg2" and session:
                await self._send_cfg2(session, period=kwargs.get("period"))
            elif cmd_type == "request_cfg2" and session:
                await self._send_command(session, Cmd.SEND_CFG2)
            elif cmd_type == "open_data" and session:
                await self._send_command(session, Cmd.OPEN_DATA)
                session.state = SessionState.STREAMING
                self._emit("streaming_started", idcode=idcode)
            elif cmd_type == "close_data" and session:
                await self._send_command(session, Cmd.CLOSE_DATA)
                session.state = SessionState.CFG2_SENT
                self._emit("streaming_stopped", idcode=idcode)
            elif cmd_type == "auto_handshake" and session:
                await self._auto_handshake(session, period=kwargs.get("period"))

    async def _auto_handshake(self, session: SubStationSession, period: int | None = None):
        """Automated handshake: request CFG-1 -> send CFG-2 cmd -> send CFG-2 -> request CFG-2 -> open data."""
        try:
            # Step 1: Request CFG-1
            await self._send_command(session, Cmd.SEND_CFG1)
            await asyncio.sleep(1.0)  # Wait for response

            if not session.cfg1:
                self._emit("error", idcode=session.idcode, error="CFG-1 not received after request")
                return

            # Step 2: Send CFG-2 command
            await self._send_command(session, Cmd.SEND_CFG2_CMD)
            await asyncio.sleep(0.5)

            # Step 3: Send CFG-2 config
            await self._send_cfg2(session, period=period)
            await asyncio.sleep(0.5)

            # Step 4: Request CFG-2 back
            await self._send_command(session, Cmd.SEND_CFG2)
            await asyncio.sleep(0.5)

            # Step 5: Open data
            await self._send_command(session, Cmd.OPEN_DATA)
            session.state = SessionState.STREAMING
            self._emit("streaming_started", idcode=session.idcode)

        except Exception as e:
            self._emit("error", idcode=session.idcode, error=f"Auto handshake failed: {e}")

    # --- Heartbeat ---

    async def _heartbeat_loop(self):
        """Periodically send heartbeats to all connected substations."""
        while self._running:
            await asyncio.sleep(self.heartbeat_interval)
            for session in list(self.sessions.values()):
                if session.mgmt_connected and session.state != SessionState.DISCONNECTED:
                    try:
                        await self._send_command(session, Cmd.HEARTBEAT)
                        session.missed_heartbeats += 1
                        if session.missed_heartbeats >= 3:
                            session.state = SessionState.DISCONNECTED
                            self._emit("heartbeat_timeout", idcode=session.idcode)
                    except Exception:
                        pass

    # --- Helpers ---

    async def _read_frame(self, reader: asyncio.StreamReader) -> bytes:
        """Read a complete frame from a TCP stream."""
        header = await reader.readexactly(4)
        sync = struct.unpack_from("!H", header, 0)[0]
        if (sync >> 8) != SYNC_BYTE:
            raise ParseError(f"Invalid sync byte: {sync:#06x}")
        frame_size = struct.unpack_from("!H", header, 2)[0]
        if frame_size < 4:
            raise ParseError(f"Invalid frame size: {frame_size}")
        remaining = await reader.readexactly(frame_size - 4)
        return header + remaining

    def _get_or_create_session(self, idcode: str, peer_ip: str, version: int) -> SubStationSession:
        """Find existing session by idcode or create a new one."""
        if idcode in self.sessions:
            session = self.sessions[idcode]
            session.peer_ip = peer_ip
            return session
        session = SubStationSession(idcode=idcode, version=version, peer_ip=peer_ip)
        self.sessions[idcode] = session
        self._emit("session_created", idcode=idcode, peer_ip=peer_ip)
        return session

    def _find_session_by_ip(self, peer_ip: str) -> SubStationSession | None:
        """Find a session by peer IP (for V2 data pipe pairing)."""
        for session in self.sessions.values():
            if session.peer_ip == peer_ip:
                return session
        return None

    def _emit(self, event_type: str, **kwargs):
        """Send an event to the UI thread via queue."""
        self.event_queue.put_nowait((event_type, kwargs))
```

- [ ] **Step 4: Commit**

```bash
git add network/
git commit -m "feat: add network session and master station core"
```

---

## Task 8: UI Shell + Toolbar

**Files:**
- Create: `ui/__init__.py`
- Create: `ui/app.py`
- Create: `ui/toolbar.py`

- [ ] **Step 1: Create `ui/__init__.py`**

```python
```

- [ ] **Step 2: Create `ui/toolbar.py`**

```python
"""Toolbar: start/stop server, protocol selector, port config."""
import tkinter as tk
from tkinter import ttk


class Toolbar(ttk.Frame):
    """Top toolbar with server controls and protocol/port configuration."""

    def __init__(self, parent, on_start, on_stop):
        super().__init__(parent)
        self._on_start = on_start
        self._on_stop = on_stop

        # Start/Stop buttons
        self.start_btn = ttk.Button(self, text="\u25b6 \u542f\u52a8", command=self._start)
        self.start_btn.pack(side=tk.LEFT, padx=(5, 2))
        self.stop_btn = ttk.Button(self, text="\u25a0 \u505c\u6b62", command=self._stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Protocol selector
        ttk.Label(self, text="\u534f\u8bae:").pack(side=tk.LEFT, padx=(5, 2))
        self.protocol_var = tk.StringVar(value="V3")
        proto_combo = ttk.Combobox(self, textvariable=self.protocol_var,
                                    values=["V2", "V3"], width=4, state="readonly")
        proto_combo.pack(side=tk.LEFT, padx=2)
        proto_combo.bind("<<ComboboxSelected>>", self._on_protocol_change)

        ttk.Separator(self, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=5)

        # Port config
        ttk.Label(self, text="\u7ba1\u7406\u7aef\u53e3:").pack(side=tk.LEFT, padx=(5, 2))
        self.mgmt_port_var = tk.StringVar(value="8000")
        ttk.Entry(self, textvariable=self.mgmt_port_var, width=6).pack(side=tk.LEFT, padx=2)

        ttk.Label(self, text="\u6570\u636e\u7aef\u53e3:").pack(side=tk.LEFT, padx=(5, 2))
        self.data_port_var = tk.StringVar(value="8001")
        ttk.Entry(self, textvariable=self.data_port_var, width=6).pack(side=tk.LEFT, padx=2)

    def _on_protocol_change(self, _event=None):
        if self.protocol_var.get() == "V2":
            self.mgmt_port_var.set("7000")
            self.data_port_var.set("7001")
        else:
            self.mgmt_port_var.set("8000")
            self.data_port_var.set("8001")

    def _start(self):
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        try:
            mgmt_port = int(self.mgmt_port_var.get())
            data_port = int(self.data_port_var.get())
        except ValueError:
            mgmt_port, data_port = 8000, 8001
        self._on_start(mgmt_port, data_port)

    def _stop(self):
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._on_stop()
```

- [ ] **Step 3: Create `ui/app.py`**

```python
"""Main application window."""
import asyncio
import queue
import threading
import tkinter as tk
from tkinter import ttk

from network.master import MasterStation
from ui.toolbar import Toolbar
from ui.station_list import StationListPanel
from ui.config_panel import ConfigPanel
from ui.data_panel import DataPanel
from ui.log_panel import LogPanel


class App:
    """Main PmuSim application."""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("PmuSim - PMU\u4e3b\u7ad9\u6a21\u62df\u5668")
        self.root.geometry("1100x700")
        self.root.minsize(900, 500)

        self.event_queue: queue.Queue = queue.Queue()
        self.master_station: MasterStation | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

        self._build_ui()
        self._poll_events()

    def _build_ui(self):
        # Toolbar
        self.toolbar = Toolbar(self.root, on_start=self._start_server, on_stop=self._stop_server)
        self.toolbar.pack(fill=tk.X, padx=5, pady=5)

        # Main content: left panel + right notebook
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=(0, 5))

        # Left: station list + action buttons
        self.station_panel = StationListPanel(paned, on_action=self._on_station_action)
        paned.add(self.station_panel, weight=0)

        # Right: notebook with tabs
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)

        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.config_panel = ConfigPanel(self.notebook)
        self.notebook.add(self.config_panel, text=" \u914d\u7f6e ")

        self.data_panel = DataPanel(self.notebook)
        self.notebook.add(self.data_panel, text=" \u5b9e\u65f6\u6570\u636e ")

        self.log_panel = LogPanel(self.notebook)
        self.notebook.add(self.log_panel, text=" \u901a\u4fe1\u65e5\u5fd7 ")

        # Status bar
        self.status_var = tk.StringVar(value="\u5c31\u7eea")
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, padx=5, pady=(0, 5))

    def _start_server(self, mgmt_port: int, data_port: int):
        """Start the asyncio backend in a background thread."""
        self.master_station = MasterStation(
            event_queue=self.event_queue,
            mgmt_port=mgmt_port,
            data_port=data_port,
        )
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self.status_var.set(f"\u670d\u52a1\u8fd0\u884c\u4e2d - \u7ba1\u7406:{mgmt_port} \u6570\u636e:{data_port}")

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.master_station.start())
        self._loop.run_forever()

    def _stop_server(self):
        """Stop the asyncio backend."""
        if self._loop and self.master_station:
            asyncio.run_coroutine_threadsafe(self.master_station.stop(), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=3)
            self._loop = None
            self._thread = None
            self.master_station = None
        self.station_panel.clear()
        self.config_panel.clear()
        self.data_panel.clear()
        self.log_panel.clear()
        self.status_var.set("\u5df2\u505c\u6b62")

    def _on_station_action(self, action: str, idcode: str, **kwargs):
        """Handle action button clicks from station list panel."""
        if not self.master_station or not self._loop:
            return

        if action == "request_cfg1":
            self.master_station.send_command("request_cfg1", idcode=idcode)
        elif action == "send_cfg2_cmd":
            self.master_station.send_command("send_cfg2_cmd", idcode=idcode)
        elif action == "send_cfg2":
            period = kwargs.get("period")
            self.master_station.send_command("send_cfg2", idcode=idcode, period=period)
        elif action == "request_cfg2":
            self.master_station.send_command("request_cfg2", idcode=idcode)
        elif action == "open_data":
            self.master_station.send_command("open_data", idcode=idcode)
        elif action == "close_data":
            self.master_station.send_command("close_data", idcode=idcode)
        elif action == "auto_handshake":
            period = kwargs.get("period")
            self.master_station.send_command("auto_handshake", idcode=idcode, period=period)

    def _poll_events(self):
        """Poll the event queue and update UI."""
        try:
            while True:
                event_type, kwargs = self.event_queue.get_nowait()
                self._handle_event(event_type, kwargs)
        except queue.Empty:
            pass
        self.root.after(50, self._poll_events)

    def _handle_event(self, event_type: str, kwargs: dict):
        """Dispatch an event from the backend to the appropriate UI panel."""
        idcode = kwargs.get("idcode", "")

        if event_type == "session_created":
            self.station_panel.add_station(idcode, kwargs.get("peer_ip", ""))
            self._update_status()

        elif event_type == "session_disconnected":
            self.station_panel.update_station_state(idcode, "\u79bb\u7ebf")
            self._update_status()

        elif event_type in ("mgmt_connected", "data_connected"):
            self.station_panel.update_station_state(idcode, "\u5728\u7ebf")

        elif event_type == "cfg1_received":
            self.station_panel.update_station_state(idcode, "CFG1\u5df2\u63a5\u6536")
            selected = self.station_panel.get_selected()
            if selected == idcode:
                self.config_panel.show_config(kwargs.get("cfg"))

        elif event_type == "cfg2_sent":
            self.station_panel.update_station_state(idcode, "CFG2\u5df2\u4e0b\u53d1")

        elif event_type == "cfg2_received":
            selected = self.station_panel.get_selected()
            if selected == idcode:
                self.config_panel.show_config(kwargs.get("cfg"))

        elif event_type == "streaming_started":
            self.station_panel.update_station_state(idcode, "\u6570\u636e\u6d41")

        elif event_type == "streaming_stopped":
            self.station_panel.update_station_state(idcode, "CFG2\u5df2\u4e0b\u53d1")

        elif event_type == "data_frame":
            selected = self.station_panel.get_selected()
            if selected == idcode:
                self.data_panel.add_data(kwargs.get("frame"))

        elif event_type == "raw_frame":
            self.log_panel.add_log(
                idcode=idcode,
                direction=kwargs.get("direction", "?"),
                data=kwargs.get("data", b""),
            )

        elif event_type == "heartbeat_recv":
            pass  # Silent

        elif event_type == "heartbeat_timeout":
            self.station_panel.update_station_state(idcode, "\u5fc3\u8df3\u8d85\u65f6")

        elif event_type in ("error", "parse_error"):
            self.log_panel.add_error(idcode=idcode, error=kwargs.get("error", ""))

    def _update_status(self):
        if self.master_station:
            n = len(self.master_station.sessions)
            self.status_var.set(f"\u5df2\u8fde\u63a5\u5b50\u7ad9: {n}")

    def run(self):
        self.root.mainloop()
```

- [ ] **Step 4: Commit**

```bash
git add ui/__init__.py ui/app.py ui/toolbar.py
git commit -m "feat: add UI shell with toolbar and app framework"
```

---

## Task 9: UI Panels (Station List, Config, Data, Log)

**Files:**
- Create: `ui/station_list.py`
- Create: `ui/config_panel.py`
- Create: `ui/data_panel.py`
- Create: `ui/log_panel.py`

- [ ] **Step 1: Create `ui/station_list.py`**

```python
"""Left panel: substation list and action buttons."""
import tkinter as tk
from tkinter import ttk


class StationListPanel(ttk.Frame):
    """Shows connected substations and action buttons."""

    def __init__(self, parent, on_action):
        super().__init__(parent, width=220)
        self.pack_propagate(False)
        self._on_action = on_action
        self._stations: dict[str, dict] = {}  # idcode -> {state, peer_ip}

        # Station list
        ttk.Label(self, text="\u5b50\u7ad9\u5217\u8868", font=("", 10, "bold")).pack(pady=(5, 2))
        self.listbox = tk.Listbox(self, width=25, height=12, exportselection=False)
        self.listbox.pack(fill=tk.X, padx=5, pady=2)
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        # State label
        self.state_var = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.state_var, foreground="gray").pack(pady=2)

        # Action buttons
        btn_frame = ttk.LabelFrame(self, text="\u64cd\u4f5c")
        btn_frame.pack(fill=tk.X, padx=5, pady=5)

        actions = [
            ("\u53ec\u5524CFG-1", "request_cfg1"),
            ("\u4e0b\u4f20CFG-2\u547d\u4ee4", "send_cfg2_cmd"),
            ("\u4e0b\u4f20CFG-2", "send_cfg2"),
            ("\u53ec\u5524CFG-2", "request_cfg2"),
            ("\u5f00\u542f\u6570\u636e", "open_data"),
            ("\u5173\u95ed\u6570\u636e", "close_data"),
        ]
        for label, action in actions:
            btn = ttk.Button(btn_frame, text=label,
                             command=lambda a=action: self._do_action(a))
            btn.pack(fill=tk.X, padx=5, pady=1)

        ttk.Separator(btn_frame).pack(fill=tk.X, padx=5, pady=3)

        # PERIOD editor for CFG-2
        period_row = ttk.Frame(btn_frame)
        period_row.pack(fill=tk.X, padx=5, pady=2)
        ttk.Label(period_row, text="PERIOD:").pack(side=tk.LEFT)
        self.period_var = tk.StringVar(value="")
        ttk.Entry(period_row, textvariable=self.period_var, width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(period_row, text="(\u7a7a=\u6cbf\u7528CFG-1)").pack(side=tk.LEFT)

        ttk.Button(btn_frame, text="\u4e00\u952e\u63e1\u624b",
                   command=lambda: self._do_action("auto_handshake")).pack(fill=tk.X, padx=5, pady=1)

    def add_station(self, idcode: str, peer_ip: str):
        if idcode not in self._stations:
            self._stations[idcode] = {"state": "\u5728\u7ebf", "peer_ip": peer_ip}
            self._refresh_list()

    def update_station_state(self, idcode: str, state: str):
        if idcode in self._stations:
            self._stations[idcode]["state"] = state
            self._refresh_list()
            if self.get_selected() == idcode:
                self.state_var.set(f"\u72b6\u6001: {state}")

    def get_selected(self) -> str | None:
        sel = self.listbox.curselection()
        if sel:
            text = self.listbox.get(sel[0])
            return text.split(" ")[0]
        return None

    def clear(self):
        self._stations.clear()
        self.listbox.delete(0, tk.END)
        self.state_var.set("")

    def _refresh_list(self):
        selected = self.get_selected()
        self.listbox.delete(0, tk.END)
        for idcode, info in self._stations.items():
            self.listbox.insert(tk.END, f"{idcode}  [{info['state']}]")
        # Re-select
        if selected:
            for i in range(self.listbox.size()):
                if self.listbox.get(i).startswith(selected):
                    self.listbox.selection_set(i)
                    break

    def _on_select(self, _event=None):
        idcode = self.get_selected()
        if idcode and idcode in self._stations:
            self.state_var.set(f"\u72b6\u6001: {self._stations[idcode]['state']}")

    def _do_action(self, action: str):
        idcode = self.get_selected()
        if idcode:
            period = None
            period_str = self.period_var.get().strip()
            if period_str:
                try:
                    period = int(period_str)
                except ValueError:
                    pass
            self._on_action(action, idcode, period=period)
```

- [ ] **Step 2: Create `ui/config_panel.py`**

```python
"""Config panel: shows CFG-1/CFG-2 parsed content."""
import tkinter as tk
from tkinter import ttk
from protocol.frames import ConfigFrame


class ConfigPanel(ttk.Frame):
    """Tab showing configuration frame details."""

    def __init__(self, parent):
        super().__init__(parent)
        self._build()

    def _build(self):
        # Basic info
        info_frame = ttk.LabelFrame(self, text="\u57fa\u672c\u4fe1\u606f")
        info_frame.pack(fill=tk.X, padx=5, pady=5)

        self._info_labels = {}
        fields = [
            ("cfg_type", "\u914d\u7f6e\u7c7b\u578b"),
            ("version", "\u534f\u8bae\u7248\u672c"),
            ("stn", "\u7ad9\u540d"),
            ("idcode", "IDCODE"),
            ("format_flags", "FORMAT"),
            ("period_ms", "\u4f20\u9001\u5468\u671f"),
            ("meas_rate", "MEAS_RATE"),
        ]
        for i, (key, label) in enumerate(fields):
            ttk.Label(info_frame, text=f"{label}:").grid(row=i, column=0, sticky=tk.W, padx=5, pady=1)
            var = tk.StringVar(value="-")
            ttk.Label(info_frame, textvariable=var).grid(row=i, column=1, sticky=tk.W, padx=5, pady=1)
            self._info_labels[key] = var

        # Analog channels
        an_frame = ttk.LabelFrame(self, text="\u6a21\u62df\u91cf\u901a\u9053")
        an_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        cols = ("\u5e8f\u53f7", "\u540d\u79f0", "ANUNIT", "\u7cfb\u6570")
        self.an_tree = ttk.Treeview(an_frame, columns=cols, show="headings", height=8)
        for c in cols:
            self.an_tree.heading(c, text=c)
            self.an_tree.column(c, width=80)
        self.an_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        # Digital channels
        dg_frame = ttk.LabelFrame(self, text="\u5f00\u5173\u91cf\u901a\u9053")
        dg_frame.pack(fill=tk.X, padx=5, pady=5)

        dg_cols = ("\u5e8f\u53f7", "\u540d\u79f0", "\u6709\u6548")
        self.dg_tree = ttk.Treeview(dg_frame, columns=dg_cols, show="headings", height=4)
        for c in dg_cols:
            self.dg_tree.heading(c, text=c)
            self.dg_tree.column(c, width=100)
        self.dg_tree.pack(fill=tk.X, padx=2, pady=2)

    def show_config(self, cfg: ConfigFrame | None):
        if not cfg:
            self.clear()
            return

        self._info_labels["cfg_type"].set(f"CFG-{cfg.cfg_type}")
        self._info_labels["version"].set(f"V{cfg.version}")
        self._info_labels["stn"].set(cfg.stn)
        self._info_labels["idcode"].set(cfg.pmu_idcode)
        self._info_labels["format_flags"].set(f"0x{cfg.format_flags:04X}")
        self._info_labels["period_ms"].set(f"{cfg.period_ms:.1f} ms (PERIOD={cfg.period})")
        self._info_labels["meas_rate"].set(f"{cfg.meas_rate} \u5fae\u79d2")

        # Analog channels
        self.an_tree.delete(*self.an_tree.get_children())
        for i in range(cfg.annmr):
            name = cfg.channel_names[cfg.phnmr + i] if (cfg.phnmr + i) < len(cfg.channel_names) else "?"
            anunit_val = cfg.anunit[i] if i < len(cfg.anunit) else 0
            factor = cfg.analog_factor(i)
            self.an_tree.insert("", tk.END, values=(i + 1, name, anunit_val, f"{factor:.5f}"))

        # Digital channels
        self.dg_tree.delete(*self.dg_tree.get_children())
        ch_offset = cfg.phnmr + cfg.annmr
        for w in range(cfg.dgnmr):
            _, valid_mask = cfg.digunit[w] if w < len(cfg.digunit) else (0, 0)
            for bit in range(16):
                idx = ch_offset + w * 16 + bit
                name = cfg.channel_names[idx] if idx < len(cfg.channel_names) else ""
                is_valid = "\u2713" if (valid_mask >> bit) & 1 else ""
                if name and name.strip("\x00"):
                    self.dg_tree.insert("", tk.END, values=(w * 16 + bit + 1, name, is_valid))

    def clear(self):
        for var in self._info_labels.values():
            var.set("-")
        self.an_tree.delete(*self.an_tree.get_children())
        self.dg_tree.delete(*self.dg_tree.get_children())
```

- [ ] **Step 3: Create `ui/data_panel.py`**

```python
"""Data panel: real-time analog/digital data display."""
import tkinter as tk
from tkinter import ttk
import time
from protocol.frames import DataFrame, ConfigFrame
from utils.time_utils import soc_to_beijing, fracsec_to_ms


class DataPanel(ttk.Frame):
    """Tab showing real-time data from substations."""

    def __init__(self, parent):
        super().__init__(parent)
        self._cfg: ConfigFrame | None = None
        self._last_refresh = 0.0
        self._pending_frame: DataFrame | None = None
        self._build()

    def _build(self):
        # Data table
        self.tree = ttk.Treeview(self, show="headings", height=20)
        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Default columns
        self._setup_columns(["时间戳", "STAT"])

    def _setup_columns(self, columns: list[str]):
        self.tree["columns"] = columns
        for col in columns:
            self.tree.heading(col, text=col)
            width = 150 if col == "\u65f6\u95f4\u6233" else 80
            self.tree.column(col, width=width, minwidth=50)

    def set_config(self, cfg: ConfigFrame):
        """Update column headers based on config frame."""
        self._cfg = cfg
        cols = ["\u65f6\u95f4\u6233"]
        for i in range(cfg.annmr):
            idx = cfg.phnmr + i
            name = cfg.channel_names[idx] if idx < len(cfg.channel_names) else f"AN{i+1}"
            cols.append(name)
        cols.append("\u5f00\u5173\u91cf")
        cols.append("STAT")
        self._setup_columns(cols)

    def add_data(self, frame: DataFrame | None):
        """Add a data frame (throttled to 200ms refresh)."""
        if not frame:
            return
        self._pending_frame = frame
        now = time.time()
        if now - self._last_refresh >= 0.2:
            self._flush()
            self._last_refresh = now

    def _flush(self):
        if not self._pending_frame:
            return
        frame = self._pending_frame
        self._pending_frame = None

        meas_rate = self._cfg.meas_rate if self._cfg else 1000000
        ms = fracsec_to_ms(frame.fracsec, meas_rate, frame.version)
        timestamp = f"{soc_to_beijing(frame.soc)}.{int(ms):03d}"

        values = [timestamp]
        if self._cfg:
            for i, raw in enumerate(frame.analog):
                factor = self._cfg.analog_factor(i)
                values.append(f"{raw * factor:.4f}")
        else:
            for raw in frame.analog:
                values.append(str(raw))

        # Digital as binary string
        digital_str = " ".join(f"{d:016b}" for d in frame.digital)
        values.append(digital_str)
        values.append(f"0x{frame.stat:04X}")

        self.tree.insert("", 0, values=values)
        # Keep max 500 rows
        children = self.tree.get_children()
        if len(children) > 500:
            for child in children[500:]:
                self.tree.delete(child)

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._cfg = None
        self._pending_frame = None
```

- [ ] **Step 4: Create `ui/log_panel.py`**

```python
"""Log panel: communication log with hex dump."""
import tkinter as tk
from tkinter import ttk
import time
from protocol.constants import FrameType, ProtocolVersion, Cmd, CMD_NAMES, parse_sync


class LogPanel(ttk.Frame):
    """Tab showing communication log entries."""

    def __init__(self, parent):
        super().__init__(parent)
        self._max_entries = 1000
        self._build()

    def _build(self):
        # Log tree
        cols = ("\u65f6\u95f4", "\u5b50\u7ad9", "\u65b9\u5411", "\u5e27\u7c7b\u578b", "\u6458\u8981")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=20)
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.column("\u65f6\u95f4", width=100)
        self.tree.column("\u5b50\u7ad9", width=90)
        self.tree.column("\u65b9\u5411", width=40)
        self.tree.column("\u5e27\u7c7b\u578b", width=80)
        self.tree.column("\u6458\u8981", width=300)

        vsb = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # Hex detail at bottom
        self.hex_text = tk.Text(self, height=4, state=tk.DISABLED, font=("Courier", 10))
        self.hex_text.pack(fill=tk.X, padx=2, pady=2)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self._raw_data: dict[str, bytes] = {}  # tree item id -> raw bytes

    def add_log(self, idcode: str, direction: str, data: bytes):
        """Add a communication log entry."""
        ts = time.strftime("%H:%M:%S")
        arrow = "\u2192" if direction == "send" else "\u2190"
        frame_type, summary = self._summarize(data)

        item_id = self.tree.insert("", 0, values=(ts, idcode, arrow, frame_type, summary))
        self._raw_data[item_id] = data

        # Trim old entries
        children = self.tree.get_children()
        if len(children) > self._max_entries:
            for child in children[self._max_entries:]:
                self._raw_data.pop(child, None)
                self.tree.delete(child)

    def add_error(self, idcode: str, error: str):
        ts = time.strftime("%H:%M:%S")
        self.tree.insert("", 0, values=(ts, idcode, "!", "\u9519\u8bef", error))

    def clear(self):
        self.tree.delete(*self.tree.get_children())
        self._raw_data.clear()
        self.hex_text.config(state=tk.NORMAL)
        self.hex_text.delete("1.0", tk.END)
        self.hex_text.config(state=tk.DISABLED)

    def _summarize(self, data: bytes) -> tuple[str, str]:
        """Extract frame type and human-readable summary from raw bytes."""
        if len(data) < 4:
            return ("?", data.hex())
        try:
            sync = int.from_bytes(data[0:2], "big")
            frame_type, version = parse_sync(sync)
        except ValueError:
            return ("?", data[:20].hex())

        type_names = {
            FrameType.DATA: "\u6570\u636e\u5e27",
            FrameType.CFG1: "CFG-1",
            FrameType.CFG2: "CFG-2",
            FrameType.COMMAND: "\u547d\u4ee4\u5e27",
        }
        type_str = f"{type_names.get(frame_type, '?')}(V{version})"

        summary = f"{len(data)}\u5b57\u8282"
        if frame_type == FrameType.COMMAND:
            # Extract CMD field
            if version == ProtocolVersion.V2:
                cmd = int.from_bytes(data[16:18], "big") if len(data) >= 18 else 0
            else:
                cmd = int.from_bytes(data[20:22], "big") if len(data) >= 22 else 0
            cmd_name = CMD_NAMES.get(cmd, f"0x{cmd:04X}")
            summary = cmd_name

        return type_str, summary

    def _on_select(self, _event=None):
        sel = self.tree.selection()
        if sel:
            raw = self._raw_data.get(sel[0], b"")
            hex_str = " ".join(f"{b:02X}" for b in raw)
            self.hex_text.config(state=tk.NORMAL)
            self.hex_text.delete("1.0", tk.END)
            self.hex_text.insert("1.0", hex_str)
            self.hex_text.config(state=tk.DISABLED)


```

- [ ] **Step 5: Commit**

```bash
git add ui/station_list.py ui/config_panel.py ui/data_panel.py ui/log_panel.py
git commit -m "feat: add UI panels (station list, config, data, log)"
```

---

## Task 10: Integration + Main Entry

**Files:**
- Create: `main.py`
- Modify: `ui/app.py` (wire up config panel update on station selection)

- [ ] **Step 1: Create `main.py`**

```python
"""PmuSim entry point."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.app import App


def main():
    app = App()
    app.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add station selection handler in `ui/app.py`**

In `App._build_ui`, after creating the station panel, add a selection callback:

```python
        self.station_panel.listbox.bind("<<ListboxSelect>>", self._on_station_selected)
```

Add the handler method to `App`:
```python
    def _on_station_selected(self, _event=None):
        """When user selects a station, update config and data panels."""
        idcode = self.station_panel.get_selected()
        if idcode and self.master_station:
            session = self.master_station.sessions.get(idcode)
            if session:
                # Show the latest config (prefer CFG-2 over CFG-1)
                cfg = session.cfg2 or session.cfg1
                self.config_panel.show_config(cfg)
                if cfg:
                    self.data_panel.set_config(cfg)
```

Also update the `cfg1_received` and `cfg2_received` event handlers to auto-update data panel columns:

In `_handle_event`, update the `cfg1_received` handler:
```python
        elif event_type == "cfg1_received":
            self.station_panel.update_station_state(idcode, "CFG1\u5df2\u63a5\u6536")
            cfg = kwargs.get("cfg")
            selected = self.station_panel.get_selected()
            if selected == idcode:
                self.config_panel.show_config(cfg)
                self.data_panel.set_config(cfg)
```

And the `cfg2_received` handler:
```python
        elif event_type == "cfg2_received":
            cfg = kwargs.get("cfg")
            selected = self.station_panel.get_selected()
            if selected == idcode:
                self.config_panel.show_config(cfg)
                self.data_panel.set_config(cfg)
```

- [ ] **Step 3: Run the app to verify it starts**

Run: `cd /Users/daichangyu/Library/Mobile\ Documents/com~apple~CloudDocs/code/PmuSim && python main.py`

Expected: A Tkinter window opens with the toolbar, empty station list, and three tabs. Start/Stop buttons work. Window can be resized and closed.

- [ ] **Step 4: Commit**

```bash
git add main.py ui/app.py
git commit -m "feat: add main entry point and UI integration"
```

---

## Task 11: End-to-End Smoke Test

**Files:**
- Create: `tests/test_e2e.py`

- [ ] **Step 1: Write E2E test with mock substation**

Create `tests/test_e2e.py`:
```python
"""End-to-end test: mock substation connects to MasterStation."""
import asyncio
import queue
import struct
import unittest
from protocol.builder import FrameBuilder
from protocol.frames import CommandFrame, ConfigFrame, DataFrame
from protocol.parser import FrameParser
from protocol.constants import Cmd, SYNC_BYTE, IDCODE_LEN
from network.master import MasterStation


class TestE2E(unittest.TestCase):
    """Test MasterStation with a mock V3 substation."""

    def test_full_handshake_v3(self):
        """Simulate: substation connects -> master requests CFG-1 -> substation sends CFG-1
        -> master sends CFG-2 -> substation acks -> master opens data -> substation sends data."""
        event_queue = queue.Queue()
        loop = asyncio.new_event_loop()

        async def run_test():
            master = MasterStation(event_queue, mgmt_port=0, data_port=0)
            await master.start()

            # Get dynamically assigned ports
            mgmt_port = master._mgmt_server.sockets[0].getsockname()[1]
            data_port = master._data_server.sockets[0].getsockname()[1]

            # --- Mock substation connects management pipe ---
            mgmt_r, mgmt_w = await asyncio.open_connection("127.0.0.1", mgmt_port)

            # Substation sends a CFG-1 as its first frame (in response to a future request)
            # But first, master needs to read something to identify the substation.
            # Let's send a heartbeat to identify ourselves
            hb = FrameBuilder.build(CommandFrame(
                version=3, idcode="TESTSUB1", soc=1000, fracsec=0, cmd=Cmd.HEARTBEAT
            ))
            mgmt_w.write(hb)
            await mgmt_w.drain()
            await asyncio.sleep(0.3)

            # Check session was created
            self.assertIn("TESTSUB1", master.sessions)

            # Master requests CFG-1
            master.send_command("request_cfg1", idcode="TESTSUB1")
            await asyncio.sleep(0.3)

            # Substation reads the request
            raw = await asyncio.wait_for(self._read_frame(mgmt_r), timeout=2)
            frame = FrameParser.parse(raw)
            self.assertIsInstance(frame, CommandFrame)
            self.assertEqual(frame.cmd, Cmd.SEND_CFG1)

            # Substation sends CFG-1
            cfg1 = ConfigFrame(
                version=3, cfg_type=1, idcode="TESTSUB1",
                soc=1001, fracsec=0, d_frame=0,
                meas_rate=1000000, num_pmu=1,
                stn="0000TestStation1", pmu_idcode="TESTSUB1",
                format_flags=0x0011, phnmr=0, annmr=2, dgnmr=1,
                channel_names=[
                    "AnalogChannel001", "AnalogChannel002",
                    "DigitalChan0001", "DigitalChan0002", "DigitalChan0003",
                    "DigitalChan0004", "DigitalChan0005", "DigitalChan0006",
                    "DigitalChan0007", "DigitalChan0008", "DigitalChan0009",
                    "DigitalChan0010", "DigitalChan0011", "DigitalChan0012",
                    "DigitalChan0013", "DigitalChan0014", "DigitalChan0015",
                    "DigitalChan0016",
                ],
                phunit=[], anunit=[1000, 546],
                digunit=[(0x0000, 0x0003)],
                fnom=1, period=50,
            )
            cfg1_raw = FrameBuilder.build(cfg1)
            mgmt_w.write(cfg1_raw)
            await mgmt_w.drain()
            await asyncio.sleep(0.3)

            # Verify master received CFG-1
            session = master.sessions["TESTSUB1"]
            self.assertIsNotNone(session.cfg1)
            self.assertEqual(session.cfg1.annmr, 2)

            # --- Connect data pipe ---
            data_r, data_w = await asyncio.open_connection("127.0.0.1", data_port)

            # Send a data frame to identify on data pipe
            df = DataFrame(
                version=3, idcode="TESTSUB1", soc=1002, fracsec=500000,
                stat=0, phasors=[], freq=0, dfreq=0,
                analog=[300, 9175], digital=[0x0003],
            )
            df_raw = FrameBuilder.build(df, phnmr=0, annmr=2, dgnmr=1)
            data_w.write(df_raw)
            await data_w.drain()
            await asyncio.sleep(0.3)

            # Verify data was received
            found_data = False
            while not event_queue.empty():
                evt_type, evt_kwargs = event_queue.get_nowait()
                if evt_type == "data_frame":
                    found_data = True
                    recv_frame = evt_kwargs["frame"]
                    self.assertEqual(recv_frame.analog, [300, 9175])

            self.assertTrue(found_data, "No data_frame event received")

            # Cleanup
            mgmt_w.close()
            data_w.close()
            await master.stop()

        async def _read_frame_helper(reader):
            header = await reader.readexactly(4)
            frame_size = struct.unpack_from("!H", header, 2)[0]
            remaining = await reader.readexactly(frame_size - 4)
            return header + remaining

        self._read_frame = _read_frame_helper

        try:
            loop.run_until_complete(asyncio.wait_for(run_test(), timeout=10))
        finally:
            loop.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the E2E test**

Run: `python -m unittest tests.test_e2e -v`

Expected: PASS. The mock substation successfully connects, exchanges configuration, and sends data.

- [ ] **Step 3: Run all tests to verify nothing is broken**

Run: `python -m unittest discover tests -v`

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_e2e.py
git commit -m "feat: add end-to-end smoke test with mock substation"
```

---

## Summary

| Task | Description | Key Files | Tests |
|------|-------------|-----------|-------|
| 1 | Constants + CRC16 | protocol/constants.py, crc16.py | test_crc16.py (12 tests) |
| 2 | Frame dataclasses + time utils | protocol/frames.py, utils/time_utils.py | test_time_utils.py (6 tests) |
| 3 | Command frame parser | protocol/parser.py | test_parser.py (12 tests) |
| 4 | Config frame parser | protocol/parser.py | test_parser.py (6 tests) |
| 5 | Data frame parser | protocol/parser.py | test_parser.py (2 tests) |
| 6 | Frame builder | protocol/builder.py | test_builder.py (8 tests) |
| 7 | Network session + master | network/session.py, master.py | - |
| 8 | UI shell + toolbar | ui/app.py, toolbar.py | Manual |
| 9 | UI panels | ui/station_list.py, config/data/log_panel.py | Manual |
| 10 | Integration + main | main.py | Manual |
| 11 | E2E smoke test | tests/test_e2e.py | test_e2e.py (1 integration test) |
