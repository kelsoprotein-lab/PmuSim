"""PMU protocol frame builder."""
import struct
from protocol.constants import make_sync, FrameType, ProtocolVersion, IDCODE_LEN, STN_LEN, CHNAM_LEN
from protocol.crc16 import crc16
from protocol.frames import CommandFrame, ConfigFrame, DataFrame


class BuildError(Exception):
    pass


class FrameBuilder:
    @staticmethod
    def build(frame, phnmr: int = 0, annmr: int = 0, dgnmr: int = 0) -> bytes:
        if isinstance(frame, CommandFrame):
            return FrameBuilder._build_command(frame)
        elif isinstance(frame, ConfigFrame):
            return FrameBuilder._build_config(frame)
        elif isinstance(frame, DataFrame):
            return FrameBuilder._build_data(frame, phnmr, annmr, dgnmr)
        else:
            raise BuildError(f"Unknown frame type: {type(frame)}")

    @staticmethod
    def _append_crc(payload: bytes) -> bytes:
        """Append 2-byte CRC16 to payload."""
        return payload + struct.pack(">H", crc16(payload))

    @staticmethod
    def _build_command(frame: CommandFrame) -> bytes:
        """
        V2: SYNC(2) SIZE(2) SOC(4) IDCODE(8) CMD(2) CHK(2) = 20 bytes
        V3: SYNC(2) SIZE(2) IDCODE(8) SOC(4) FRACSEC(4) CMD(2) CHK(2) = 24 bytes
        """
        version = frame.version
        if version == 2:
            frame_size = 20
            sync = make_sync(FrameType.COMMAND, ProtocolVersion.V2)
            idcode_bytes = frame.idcode.encode("ascii").ljust(IDCODE_LEN, b"\x00")[:IDCODE_LEN]
            payload = struct.pack(">HHI", sync, frame_size, frame.soc)
            payload += idcode_bytes
            payload += struct.pack(">H", frame.cmd)
        elif version == 3:
            frame_size = 24
            sync = make_sync(FrameType.COMMAND, ProtocolVersion.V3)
            idcode_bytes = frame.idcode.encode("ascii").ljust(IDCODE_LEN, b"\x00")[:IDCODE_LEN]
            payload = struct.pack(">HH", sync, frame_size)
            payload += idcode_bytes
            payload += struct.pack(">IIH", frame.soc, frame.fracsec, frame.cmd)
        else:
            raise BuildError(f"Unknown protocol version: {version}")

        return FrameBuilder._append_crc(payload)

    @staticmethod
    def _build_config(frame: ConfigFrame) -> bytes:
        """
        V2: SYNC(2) SIZE(2) SOC(4) D_FRAME(2) MEAS_RATE(4) NUM_PMU(2) [PMU_DATA] CHK(2)
        V3: SYNC(2) SIZE(2) DC_IDCODE(8) SOC(4) FRACSEC(4) MEAS_RATE(4) NUM_PMU(2) [PMU_DATA] CHK(2)
        """
        version = frame.version
        cfg_type = frame.cfg_type

        # Determine FrameType from cfg_type integer
        if cfg_type == int(FrameType.CFG1):
            ft = FrameType.CFG1
        elif cfg_type == int(FrameType.CFG2):
            ft = FrameType.CFG2
        else:
            raise BuildError(f"Unknown cfg_type: {cfg_type}")

        if version == 2:
            pv = ProtocolVersion.V2
        elif version == 3:
            pv = ProtocolVersion.V3
        else:
            raise BuildError(f"Unknown protocol version: {version}")

        sync = make_sync(ft, pv)

        # Build PMU_DATA block
        pmu_block = b""
        stn_bytes = frame.stn.encode("gbk").ljust(STN_LEN, b"\x00")[:STN_LEN]
        pmu_idcode_bytes = frame.pmu_idcode.encode("ascii").ljust(IDCODE_LEN, b"\x00")[:IDCODE_LEN]
        pmu_block += stn_bytes + pmu_idcode_bytes
        pmu_block += struct.pack(">HHHH", frame.format_flags, frame.phnmr, frame.annmr, frame.dgnmr)

        for name in frame.channel_names:
            name_bytes = name.encode("gbk").ljust(CHNAM_LEN, b"\x00")[:CHNAM_LEN]
            pmu_block += name_bytes

        for u in frame.phunit:
            pmu_block += struct.pack(">I", u)
        for u in frame.anunit:
            pmu_block += struct.pack(">I", u)
        for high, low in frame.digunit:
            pmu_block += struct.pack(">I", (high << 16) | (low & 0xFFFF))

        pmu_block += struct.pack(">HH", frame.fnom, frame.period)

        # Build header (without SIZE placeholder)
        if version == 2:
            header = struct.pack(">HHIH", sync, 0, frame.soc, frame.d_frame)
            header += struct.pack(">IH", frame.meas_rate, frame.num_pmu)
        else:
            dc_idcode_bytes = frame.idcode.encode("ascii").ljust(IDCODE_LEN, b"\x00")[:IDCODE_LEN]
            header = struct.pack(">HH", sync, 0)
            header += dc_idcode_bytes
            header += struct.pack(">IIIH", frame.soc, frame.fracsec, frame.meas_rate, frame.num_pmu)

        # Assemble full frame (without CRC) to compute size
        body = header + pmu_block
        frame_size = len(body) + 2  # +2 for CHK

        # Patch SIZE field (bytes 2-3)
        body = body[:2] + struct.pack(">H", frame_size) + body[4:]

        return FrameBuilder._append_crc(body)

    @staticmethod
    def _build_data(frame: DataFrame, phnmr: int, annmr: int, dgnmr: int) -> bytes:
        """
        V2: SYNC(2) SIZE(2) SOC(4) FRACSEC(4) STAT(2) [phasors] FREQ(2) DFREQ(2) [analog] [digital] CHK(2)
        V3: SYNC(2) SIZE(2) IDCODE(8) SOC(4) FRACSEC(4) STAT(2) [phasors] FREQ(2) DFREQ(2) [analog] [digital] CHK(2)
        """
        version = frame.version
        if version == 2:
            pv = ProtocolVersion.V2
        elif version == 3:
            pv = ProtocolVersion.V3
        else:
            raise BuildError(f"Unknown protocol version: {version}")

        sync = make_sync(FrameType.DATA, pv)

        if version == 2:
            header = struct.pack(">HHIIH", sync, 0, frame.soc, frame.fracsec, frame.stat)
        else:
            idcode_bytes = frame.idcode.encode("ascii").ljust(IDCODE_LEN, b"\x00")[:IDCODE_LEN]
            header = struct.pack(">HH", sync, 0)
            header += idcode_bytes
            header += struct.pack(">IIH", frame.soc, frame.fracsec, frame.stat)

        body = header
        for mag, ang in frame.phasors:
            body += struct.pack(">hh", mag, ang)
        body += struct.pack(">HH", frame.freq, frame.dfreq)
        for a in frame.analog:
            body += struct.pack(">h", a)
        for d in frame.digital:
            body += struct.pack(">H", d)

        frame_size = len(body) + 2
        body = body[:2] + struct.pack(">H", frame_size) + body[4:]

        return FrameBuilder._append_crc(body)
