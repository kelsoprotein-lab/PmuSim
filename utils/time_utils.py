"""Time conversion utilities for PMU protocol."""
import time as _time

def soc_to_beijing(soc: int) -> str:
    t = _time.gmtime(soc + 8 * 3600)
    return _time.strftime("%Y-%m-%d %H:%M:%S", t)

def fracsec_to_ms(fracsec: int, meas_rate: int, version: int = 3) -> float:
    if meas_rate == 0:
        return 0.0
    if version == 3:
        count = fracsec & 0x00FFFFFF
    else:
        count = fracsec
    return count / (meas_rate / 1000.0)

def current_soc() -> int:
    return int(_time.time())
