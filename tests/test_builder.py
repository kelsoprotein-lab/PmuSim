"""Tests for FrameBuilder: command verification, config/data round-trips."""
import unittest
import struct
from protocol.builder import FrameBuilder
from protocol.parser import FrameParser
from protocol.frames import CommandFrame, ConfigFrame, DataFrame
from protocol.constants import FrameType


class TestBuildCommandFrame(unittest.TestCase):
    def test_v2_request_cfg1_known_hex(self):
        frame = CommandFrame(
            version=2,
            idcode="0GX00GP1",
            soc=0x6757DD1D,
            fracsec=0,
            cmd=0x0004,
        )
        result = FrameBuilder.build(frame)
        expected = bytes.fromhex("aa4200146757dd1d30475830304750310004a5cb")
        self.assertEqual(result, expected)

    def test_v3_request_cfg1_known_hex(self):
        frame = CommandFrame(
            version=3,
            idcode="0GX00GP1",
            soc=0x67B2C719,
            fracsec=0,
            cmd=0x0004,
        )
        result = FrameBuilder.build(frame)
        expected = bytes.fromhex("aa430018304758303047503167b2c719000000000004ac08")
        self.assertEqual(result, expected)

    def test_v2_roundtrip(self):
        frame = CommandFrame(version=2, idcode="TESTID01", soc=0x12345678, fracsec=0, cmd=0x0002)
        data = FrameBuilder.build(frame)
        parsed = FrameParser.parse(data)
        self.assertEqual(parsed.version, frame.version)
        self.assertEqual(parsed.idcode, frame.idcode)
        self.assertEqual(parsed.soc, frame.soc)
        self.assertEqual(parsed.cmd, frame.cmd)

    def test_v3_roundtrip(self):
        frame = CommandFrame(version=3, idcode="TESTID02", soc=0xABCDEF01, fracsec=0x000F4240, cmd=0xE000)
        data = FrameBuilder.build(frame)
        parsed = FrameParser.parse(data)
        self.assertEqual(parsed.version, frame.version)
        self.assertEqual(parsed.idcode, frame.idcode)
        self.assertEqual(parsed.soc, frame.soc)
        self.assertEqual(parsed.fracsec, frame.fracsec)
        self.assertEqual(parsed.cmd, frame.cmd)


class TestBuildConfigFrame(unittest.TestCase):
    def _make_v2_config(self):
        phnmr, annmr, dgnmr = 2, 3, 1
        total_chnam = phnmr + annmr + dgnmr * 16
        return ConfigFrame(
            version=2,
            cfg_type=int(FrameType.CFG1),
            idcode="PMU00001",
            soc=0x67000001,
            fracsec=0,
            d_frame=0x0064,
            meas_rate=100,
            num_pmu=1,
            stn="TestStation",
            pmu_idcode="PMU00001",
            format_flags=0x0000,
            phnmr=phnmr,
            annmr=annmr,
            dgnmr=dgnmr,
            channel_names=["Va", "Vb", "Ia", "Ib", "Ic"] + ["DIG"] * (dgnmr * 16),
            phunit=[0x00000001, 0x00000001],
            anunit=[0x00000064, 0x00000064, 0x00000064],
            digunit=[(0x0000, 0x0000)],
            fnom=0x0001,
            period=100,
        )

    def _make_v3_config(self):
        phnmr, annmr, dgnmr = 0, 11, 1
        total_chnam = phnmr + annmr + dgnmr * 16
        return ConfigFrame(
            version=3,
            cfg_type=int(FrameType.CFG2),
            idcode="0GX00GP1",
            soc=0x67B2C719,
            fracsec=0x00000000,
            d_frame=0,
            meas_rate=100,
            num_pmu=1,
            stn="PMU_Station",
            pmu_idcode="0GX00GP1",
            format_flags=0x0000,
            phnmr=phnmr,
            annmr=annmr,
            dgnmr=dgnmr,
            channel_names=["AN%02d" % i for i in range(annmr)] + ["DIG"] * (dgnmr * 16),
            phunit=[],
            anunit=[0x00000064] * annmr,
            digunit=[(0x0001, 0x0000)],
            fnom=0x0001,
            period=100,
        )

    def test_v2_config_roundtrip(self):
        frame = self._make_v2_config()
        data = FrameBuilder.build(frame)
        parsed = FrameParser.parse(data)
        self.assertIsInstance(parsed, ConfigFrame)
        self.assertEqual(parsed.version, frame.version)
        self.assertEqual(parsed.soc, frame.soc)
        self.assertEqual(parsed.d_frame, frame.d_frame)
        self.assertEqual(parsed.meas_rate, frame.meas_rate)
        self.assertEqual(parsed.num_pmu, frame.num_pmu)
        self.assertEqual(parsed.stn, frame.stn)
        self.assertEqual(parsed.pmu_idcode, frame.pmu_idcode)
        self.assertEqual(parsed.idcode, frame.idcode)
        self.assertEqual(parsed.format_flags, frame.format_flags)
        self.assertEqual(parsed.phnmr, frame.phnmr)
        self.assertEqual(parsed.annmr, frame.annmr)
        self.assertEqual(parsed.dgnmr, frame.dgnmr)
        self.assertEqual(parsed.channel_names, frame.channel_names)
        self.assertEqual(parsed.phunit, frame.phunit)
        self.assertEqual(parsed.anunit, frame.anunit)
        self.assertEqual(parsed.digunit, frame.digunit)
        self.assertEqual(parsed.fnom, frame.fnom)
        self.assertEqual(parsed.period, frame.period)

    def test_v3_config_roundtrip(self):
        frame = self._make_v3_config()
        data = FrameBuilder.build(frame)
        parsed = FrameParser.parse(data)
        self.assertIsInstance(parsed, ConfigFrame)
        self.assertEqual(parsed.version, frame.version)
        self.assertEqual(parsed.idcode, frame.idcode)
        self.assertEqual(parsed.soc, frame.soc)
        self.assertEqual(parsed.fracsec, frame.fracsec)
        self.assertEqual(parsed.meas_rate, frame.meas_rate)
        self.assertEqual(parsed.stn, frame.stn)
        self.assertEqual(parsed.pmu_idcode, frame.pmu_idcode)
        self.assertEqual(parsed.phnmr, frame.phnmr)
        self.assertEqual(parsed.annmr, frame.annmr)
        self.assertEqual(parsed.dgnmr, frame.dgnmr)
        self.assertEqual(parsed.channel_names, frame.channel_names)
        self.assertEqual(parsed.anunit, frame.anunit)
        self.assertEqual(parsed.digunit, frame.digunit)
        self.assertEqual(parsed.fnom, frame.fnom)
        self.assertEqual(parsed.period, frame.period)

    def test_cfg_type_preserved(self):
        frame = self._make_v2_config()
        data = FrameBuilder.build(frame)
        parsed = FrameParser.parse(data)
        self.assertEqual(parsed.cfg_type, frame.cfg_type)


class TestBuildDataFrame(unittest.TestCase):
    def test_v2_data_roundtrip(self):
        frame = DataFrame(
            version=2,
            idcode="",
            soc=0x67A99D11,
            fracsec=0x000D9490,
            stat=0x0000,
            phasors=[(100, -50), (200, 30)],
            freq=0x0000,
            dfreq=0x0000,
            analog=[300, 3000, 9175],
            digital=[0x000A],
        )
        phnmr, annmr, dgnmr = 2, 3, 1
        data = FrameBuilder.build(frame, phnmr=phnmr, annmr=annmr, dgnmr=dgnmr)
        parsed = FrameParser.parse(data, phnmr=phnmr, annmr=annmr, dgnmr=dgnmr)
        self.assertIsInstance(parsed, DataFrame)
        self.assertEqual(parsed.version, frame.version)
        self.assertEqual(parsed.idcode, frame.idcode)
        self.assertEqual(parsed.soc, frame.soc)
        self.assertEqual(parsed.fracsec, frame.fracsec)
        self.assertEqual(parsed.stat, frame.stat)
        self.assertEqual(parsed.phasors, frame.phasors)
        self.assertEqual(parsed.freq, frame.freq)
        self.assertEqual(parsed.dfreq, frame.dfreq)
        self.assertEqual(parsed.analog, frame.analog)
        self.assertEqual(parsed.digital, frame.digital)

    def test_v3_data_roundtrip(self):
        frame = DataFrame(
            version=3,
            idcode="0GX00GP1",
            soc=0x67B2C71D,
            fracsec=0x00000000,
            stat=0x0000,
            phasors=[],
            freq=0x0000,
            dfreq=0x0000,
            analog=[400, 300, 9185, 0, 0, 0, 0, 0, 0, 0, 9185],
            digital=[0x000A],
        )
        phnmr, annmr, dgnmr = 0, 11, 1
        data = FrameBuilder.build(frame, phnmr=phnmr, annmr=annmr, dgnmr=dgnmr)
        parsed = FrameParser.parse(data, phnmr=phnmr, annmr=annmr, dgnmr=dgnmr)
        self.assertIsInstance(parsed, DataFrame)
        self.assertEqual(parsed.version, frame.version)
        self.assertEqual(parsed.idcode, frame.idcode)
        self.assertEqual(parsed.soc, frame.soc)
        self.assertEqual(parsed.analog, frame.analog)
        self.assertEqual(parsed.digital, frame.digital)

    def test_v2_known_data_rebuild(self):
        """Build a V2 data frame matching the known hex from test_parser."""
        # Parse the known-good bytes, then rebuild and compare
        known = bytes.fromhex(
            "aa02002c" "67a99d11" "000d9490" "0000" "0000" "0000"
            "012c0bb823d700c80000000000000000" "23d700000000" "000a" "21f3"
        )
        parsed = FrameParser.parse(known, phnmr=0, annmr=11, dgnmr=1)
        rebuilt = FrameBuilder.build(parsed, phnmr=0, annmr=11, dgnmr=1)
        self.assertEqual(rebuilt, known)

    def test_v3_known_data_rebuild(self):
        """Build a V3 data frame matching the known hex from test_parser."""
        known = bytes.fromhex(
            "aa030034" "3047583030475031" "67b2c71d" "00000000"
            "0000" "0000" "0000"
            "0190012c23e10000000000000000000023e100000000" "000a" "e884"
        )
        parsed = FrameParser.parse(known, phnmr=0, annmr=11, dgnmr=1)
        rebuilt = FrameBuilder.build(parsed, phnmr=0, annmr=11, dgnmr=1)
        self.assertEqual(rebuilt, known)


if __name__ == "__main__":
    unittest.main()
