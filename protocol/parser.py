"""PMU protocol frame parser."""
import struct
from protocol.constants import parse_sync, FrameType
from protocol.crc16 import crc16
from protocol.frames import CommandFrame


class ParseError(Exception):
    pass


class FrameParser:
    @staticmethod
    def parse(data: bytes, phnmr: int = 0, annmr: int = 0, dgnmr: int = 0):
        # Need at least SYNC(2) + FRAMESIZE(2) = 4 bytes
        if len(data) < 4:
            raise ParseError(f"Data too short: {len(data)} bytes")

        sync = struct.unpack_from(">H", data, 0)[0]
        frame_size = struct.unpack_from(">H", data, 2)[0]

        if len(data) < frame_size:
            raise ParseError(
                f"Data length {len(data)} < frame_size {frame_size}"
            )

        computed = crc16(data[:frame_size - 2])
        received = struct.unpack_from(">H", data, frame_size - 2)[0]
        if computed != received:
            raise ParseError(
                f"CRC mismatch: computed {computed:#06x}, received {received:#06x}"
            )

        try:
            frame_type, version = parse_sync(sync)
        except ValueError as e:
            raise ParseError(str(e)) from e

        if frame_type == FrameType.COMMAND:
            return FrameParser._parse_command(data, version)
        elif frame_type in (FrameType.CFG1, FrameType.CFG2):
            raise ParseError("Config frame parsing not yet implemented")
        elif frame_type == FrameType.DATA:
            raise ParseError("Data frame parsing not yet implemented")
        else:
            raise ParseError(f"Unknown frame type: {frame_type}")

    @staticmethod
    def _parse_command(data: bytes, version) -> CommandFrame:
        """
        V2: SYNC(2) SIZE(2) SOC(4) IDCODE(8) CMD(2) CHK(2) = 20 bytes
        V3: SYNC(2) SIZE(2) IDCODE(8) SOC(4) FRACSEC(4) CMD(2) CHK(2) = 24 bytes
        """
        version_int = int(version)
        if version_int == 2:
            soc = struct.unpack_from(">I", data, 4)[0]
            idcode = data[8:16].decode("ascii")
            cmd = struct.unpack_from(">H", data, 16)[0]
            fracsec = 0
        elif version_int == 3:
            idcode = data[4:12].decode("ascii")
            soc = struct.unpack_from(">I", data, 12)[0]
            fracsec = struct.unpack_from(">I", data, 16)[0]
            cmd = struct.unpack_from(">H", data, 20)[0]
        else:
            raise ParseError(f"Unknown protocol version: {version_int}")

        return CommandFrame(
            version=version_int,
            idcode=idcode,
            soc=soc,
            fracsec=fracsec,
            cmd=cmd,
        )
