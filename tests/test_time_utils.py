"""Test time conversion utilities."""
import unittest
from utils.time_utils import soc_to_beijing, fracsec_to_ms

class TestSocToBeijing(unittest.TestCase):
    def test_v2_doc_example(self):
        self.assertEqual(soc_to_beijing(0x6757DD1D), "2024-12-10 14:18:05")

    def test_v3_doc_example(self):
        self.assertEqual(soc_to_beijing(0x67B2C719), "2025-02-17 13:20:25")

    def test_epoch(self):
        self.assertEqual(soc_to_beijing(0), "1970-01-01 08:00:00")

class TestFracsecToMs(unittest.TestCase):
    def test_v2_doc_example(self):
        result = fracsec_to_ms(0x000D9490, 1000000, version=2)
        self.assertAlmostEqual(result, 890.0)

    def test_v3_zero(self):
        result = fracsec_to_ms(0x00000000, 1000000, version=3)
        self.assertAlmostEqual(result, 0.0)

    def test_v3_with_quality_bits(self):
        fracsec = 0x0F07A120
        result = fracsec_to_ms(fracsec, 1000000, version=3)
        self.assertAlmostEqual(result, 500.0)

    def test_zero_meas_rate(self):
        self.assertAlmostEqual(fracsec_to_ms(1000, 0), 0.0)

if __name__ == "__main__":
    unittest.main()
