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

SYNC_VERSION = {
    ProtocolVersion.V2: 0x02,
    ProtocolVersion.V3: 0x03,
}

def make_sync(frame_type: FrameType, version: ProtocolVersion) -> int:
    return (SYNC_BYTE << 8) | (frame_type << 4) | SYNC_VERSION[version]

def parse_sync(sync: int) -> tuple[FrameType, ProtocolVersion]:
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
    CLOSE_DATA = 0x0001
    OPEN_DATA = 0x0002
    SEND_HDR = 0x0003
    SEND_CFG1 = 0x0004
    SEND_CFG2 = 0x0005
    RECV_REF = 0x0008
    HEARTBEAT = 0x4000
    RESET = 0x6000
    SEND_CFG2_CMD = 0x8000
    TRIGGER = 0xA000
    ACK = 0xE000
    NACK = 0x2000

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

DEFAULT_PORTS = {
    ProtocolVersion.V2: {"mgmt": 7000, "data": 7001},
    ProtocolVersion.V3: {"mgmt": 8000, "data": 8001},
}

IDCODE_LEN = 8
STN_LEN = 16
CHNAM_LEN = 16
