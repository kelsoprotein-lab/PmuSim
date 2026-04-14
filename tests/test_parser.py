import unittest
from protocol.parser import FrameParser, ParseError


class TestParseCommandFrame(unittest.TestCase):
    def test_v2_request_cfg1(self):
        # aa 42 00 14 67 57 dd 1d 30 47 58 30 30 47 50 31 00 04 a5 cb
        data = bytes.fromhex("aa4200146757dd1d30475830304750310004a5cb")
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
        # aa 43 00 18 30 47 58 30 30 47 50 31 67 b2 c7 19 00 00 00 00 00 04 ac 08
        data = bytes.fromhex("aa430018304758303047503167b2c719000000000004ac08")
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
        data = bytes.fromhex("bb4200146757dd1d30475830304750310004a5cb")
        with self.assertRaises(ParseError):
            FrameParser.parse(data)

    def test_crc_mismatch(self):
        data = bytes.fromhex("aa4200146757dd1d30475830304750310004a5cc")
        with self.assertRaises(ParseError):
            FrameParser.parse(data)

    def test_frame_too_short(self):
        data = bytes.fromhex("aa4200")
        with self.assertRaises(ParseError):
            FrameParser.parse(data)


if __name__ == "__main__":
    unittest.main()
