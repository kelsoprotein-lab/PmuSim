"""Test CRC16 against known values from PMU protocol docs."""
import unittest
from protocol.crc16 import crc16

class TestCRC16(unittest.TestCase):
    def test_v2_command_request_cfg1(self):
        data = bytes.fromhex("aa4200146757dd1d30475830304750310004")
        self.assertEqual(crc16(data), 0xA5CB)

    def test_v2_command_heartbeat(self):
        data = bytes.fromhex("aa4200146757dd2230475830304750314000")
        self.assertEqual(crc16(data), 0x9CF7)

    def test_v2_command_ack(self):
        data = bytes.fromhex("aa4200146757dd9d3047583030475031e000")
        self.assertEqual(crc16(data), 0x7C57)

    def test_v2_command_open_data(self):
        data = bytes.fromhex("aa4200146757dd1e30475830304750310002")
        self.assertEqual(crc16(data), 0xBDF7)

    def test_v2_command_send_cfg2_cmd(self):
        data = bytes.fromhex("aa4200146757dd1e30475830304750318000")
        self.assertEqual(crc16(data), 0x862D)

    def test_v3_command_request_cfg1(self):
        data = bytes.fromhex("aa430018304758303047503167b2c719000000000004")
        self.assertEqual(crc16(data), 0xAC08)

    def test_v3_command_ack(self):
        data = bytes.fromhex("aa430018304758303047503167b2c71a00000000e000")
        self.assertEqual(crc16(data), 0x24BC)

    def test_v3_command_heartbeat(self):
        data = bytes.fromhex("aa430018304758303047503167b2c71e000000004000")
        self.assertEqual(crc16(data), 0xF804)

    def test_v2_data_frame(self):
        data = bytes.fromhex(
            "aa02002c67a99d11000d9490"
            "000000000000"
            "012c0bb823d700c80000000000000000"
            "23d700000000"
            "000a"
        )
        self.assertEqual(crc16(data), 0x21F3)

    def test_v3_data_frame(self):
        data = bytes.fromhex(
            "aa030034304758303047503167b2c71d00000000"
            "000000000000"
            "0190012c23e10000000000000000000023e100000000"
            "000a"
        )
        self.assertEqual(crc16(data), 0xE884)

    def test_empty_data(self):
        self.assertEqual(crc16(b""), 0x0000)

    def test_single_byte(self):
        result = crc16(b"\x00")
        self.assertIsInstance(result, int)
        self.assertTrue(0 <= result <= 0xFFFF)

if __name__ == "__main__":
    unittest.main()
