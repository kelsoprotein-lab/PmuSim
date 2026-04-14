"""PMU protocol frame parser."""
import struct
from protocol.constants import parse_sync, FrameType, IDCODE_LEN, STN_LEN, CHNAM_LEN
from protocol.crc16 import crc16
from protocol.frames import CommandFrame, ConfigFrame, DataFrame


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
            return FrameParser._parse_config(data, version, frame_type)
        elif frame_type == FrameType.DATA:
            return FrameParser._parse_data(data, version, phnmr, annmr, dgnmr)
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

    @staticmethod
    def _parse_config(data: bytes, version, frame_type) -> ConfigFrame:
        """
        V2: SYNC(2) SIZE(2) SOC(4) D_FRAME(2) MEAS_RATE(4) NUM_PMU(2) [PMU_DATA] CHK(2)
        V3: SYNC(2) SIZE(2) DC_IDCODE(8) SOC(4) FRACSEC(4) MEAS_RATE(4) NUM_PMU(2) [PMU_DATA] CHK(2)
        PMU_DATA: STN(16) IDCODE(8) FORMAT(2) PHNMR(2) ANNMR(2) DGNMR(2)
                  CHNAM(16*(PHNMR+ANNMR+DGNMR*16)) PHUNIT(4*PHNMR) ANUNIT(4*ANNMR)
                  DIGUNIT(4*DGNMR) FNOM(2) PERIOD(2)
        """
        version_int = int(version)
        offset = 4  # after SYNC + SIZE

        if version_int == 2:
            soc = struct.unpack_from(">I", data, offset)[0]; offset += 4
            d_frame = struct.unpack_from(">H", data, offset)[0]; offset += 2
            meas_rate = struct.unpack_from(">I", data, offset)[0]; offset += 4
            num_pmu = struct.unpack_from(">H", data, offset)[0]; offset += 2
            dc_idcode = ""
            fracsec = 0
        elif version_int == 3:
            dc_idcode = data[offset:offset + IDCODE_LEN].decode("ascii"); offset += IDCODE_LEN
            soc = struct.unpack_from(">I", data, offset)[0]; offset += 4
            fracsec = struct.unpack_from(">I", data, offset)[0]; offset += 4
            meas_rate = struct.unpack_from(">I", data, offset)[0]; offset += 4
            num_pmu = struct.unpack_from(">H", data, offset)[0]; offset += 2
            d_frame = 0
        else:
            raise ParseError(f"Unknown protocol version: {version_int}")

        # Parse first PMU's data (single-PMU assumption per ConfigFrame dataclass)
        if num_pmu < 1:
            raise ParseError("NUM_PMU must be >= 1")

        stn = data[offset:offset + STN_LEN].decode("gbk").rstrip("\x00"); offset += STN_LEN
        pmu_idcode = data[offset:offset + IDCODE_LEN].decode("ascii"); offset += IDCODE_LEN
        format_flags = struct.unpack_from(">H", data, offset)[0]; offset += 2
        phnmr = struct.unpack_from(">H", data, offset)[0]; offset += 2
        annmr = struct.unpack_from(">H", data, offset)[0]; offset += 2
        dgnmr = struct.unpack_from(">H", data, offset)[0]; offset += 2

        # Channel names: PHNMR + ANNMR + DGNMR*16 names, each 16 bytes
        total_chnam = phnmr + annmr + dgnmr * 16
        channel_names = []
        for _ in range(total_chnam):
            name = data[offset:offset + CHNAM_LEN].decode("gbk").rstrip("\x00")
            channel_names.append(name)
            offset += CHNAM_LEN

        phunit = list(struct.unpack_from(f">{phnmr}I", data, offset)); offset += 4 * phnmr
        anunit = list(struct.unpack_from(f">{annmr}I", data, offset)); offset += 4 * annmr

        digunit = []
        for _ in range(dgnmr):
            word = struct.unpack_from(">I", data, offset)[0]; offset += 4
            digunit.append((word >> 16, word & 0xFFFF))

        fnom = struct.unpack_from(">H", data, offset)[0]; offset += 2
        period = struct.unpack_from(">H", data, offset)[0]; offset += 2

        # Primary idcode: V2 from per-PMU, V3 from DC_IDCODE
        primary_idcode = dc_idcode if version_int == 3 else pmu_idcode

        return ConfigFrame(
            version=version_int,
            cfg_type=int(frame_type),
            idcode=primary_idcode,
            soc=soc,
            fracsec=fracsec,
            d_frame=d_frame,
            meas_rate=meas_rate,
            num_pmu=num_pmu,
            stn=stn,
            pmu_idcode=pmu_idcode,
            format_flags=format_flags,
            phnmr=phnmr,
            annmr=annmr,
            dgnmr=dgnmr,
            channel_names=channel_names,
            phunit=phunit,
            anunit=anunit,
            digunit=digunit,
            fnom=fnom,
            period=period,
        )

    @staticmethod
    def _parse_data(data: bytes, version, phnmr: int, annmr: int, dgnmr: int) -> DataFrame:
        """
        V2: SYNC(2) SIZE(2) SOC(4) FRACSEC(4) STAT(2) [phasors] FREQ(2) DFREQ(2) [analog] [digital] CHK(2)
        V3: SYNC(2) SIZE(2) IDCODE(8) SOC(4) FRACSEC(4) STAT(2) [phasors] FREQ(2) DFREQ(2) [analog] [digital] CHK(2)
        """
        version_int = int(version)
        offset = 4  # after SYNC + SIZE

        if version_int == 2:
            idcode = ""
            soc = struct.unpack_from(">I", data, offset)[0]; offset += 4
            fracsec = struct.unpack_from(">I", data, offset)[0]; offset += 4
        elif version_int == 3:
            idcode = data[offset:offset + IDCODE_LEN].decode("ascii"); offset += IDCODE_LEN
            soc = struct.unpack_from(">I", data, offset)[0]; offset += 4
            fracsec = struct.unpack_from(">I", data, offset)[0]; offset += 4
        else:
            raise ParseError(f"Unknown protocol version: {version_int}")

        stat = struct.unpack_from(">H", data, offset)[0]; offset += 2

        # Phasors: 2 signed shorts each (mag, angle)
        phasors = []
        for _ in range(phnmr):
            mag, ang = struct.unpack_from(">hh", data, offset)
            phasors.append((mag, ang))
            offset += 4

        freq = struct.unpack_from(">H", data, offset)[0]; offset += 2
        dfreq = struct.unpack_from(">H", data, offset)[0]; offset += 2

        # Analog: signed 16-bit integers
        analog = list(struct.unpack_from(f">{annmr}h", data, offset)); offset += 2 * annmr

        # Digital: unsigned 16-bit words
        digital = list(struct.unpack_from(f">{dgnmr}H", data, offset)); offset += 2 * dgnmr

        return DataFrame(
            version=version_int,
            idcode=idcode,
            soc=soc,
            fracsec=fracsec,
            stat=stat,
            phasors=phasors,
            freq=freq,
            dfreq=dfreq,
            analog=analog,
            digital=digital,
        )
