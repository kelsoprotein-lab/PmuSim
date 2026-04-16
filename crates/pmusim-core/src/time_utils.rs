use std::time::{SystemTime, UNIX_EPOCH};

pub fn soc_to_beijing(soc: u32) -> String {
    let total_secs = soc as i64 + 8 * 3600;
    let days = total_secs.div_euclid(86400);
    let rem = total_secs.rem_euclid(86400) as u32;
    let h = rem / 3600;
    let m = (rem % 3600) / 60;
    let s = rem % 60;
    let (y, mo, d) = days_to_date(days);
    format!("{y:04}-{mo:02}-{d:02} {h:02}:{m:02}:{s:02}")
}

fn days_to_date(z: i64) -> (i32, u32, u32) {
    let z = z + 719468;
    let era = (if z >= 0 { z } else { z - 146096 }) / 146097;
    let doe = (z - era * 146097) as u32;
    let yoe = (doe - doe / 1460 + doe / 36524 - doe / 146096) / 365;
    let y = yoe as i32 + (era as i32) * 400;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let d = doy - (153 * mp + 2) / 5 + 1;
    let m = if mp < 10 { mp + 3 } else { mp - 9 };
    (if m <= 2 { y + 1 } else { y }, m, d)
}

pub fn fracsec_to_ms(fracsec: u32, meas_rate: u32, version: u8) -> f64 {
    if meas_rate == 0 {
        return 0.0;
    }
    let count = if version >= 3 {
        fracsec & 0x00FFFFFF
    } else {
        fracsec
    };
    count as f64 / (meas_rate as f64 / 1000.0)
}

pub fn current_soc() -> u32 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_secs() as u32
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn soc_epoch_beijing() {
        assert_eq!(soc_to_beijing(0), "1970-01-01 08:00:00");
    }

    #[test]
    fn soc_2024_12_10() {
        assert_eq!(soc_to_beijing(0x6757DD1D), "2024-12-10 14:18:05");
    }

    #[test]
    fn soc_2025_02_17() {
        assert_eq!(soc_to_beijing(0x67B2C719), "2025-02-17 13:20:25");
    }

    #[test]
    fn fracsec_v2_890ms() {
        let ms = fracsec_to_ms(0x000D9490, 1_000_000, 2);
        assert!((ms - 890.0).abs() < 0.1, "expected ~890.0, got {ms}");
    }

    #[test]
    fn fracsec_zero() {
        let ms = fracsec_to_ms(0, 1_000_000, 3);
        assert!((ms - 0.0).abs() < 0.001);
    }

    #[test]
    fn fracsec_v3_quality_bits() {
        // Upper 8 bits are quality flags, lower 24 = 0x07A120 = 500000
        let ms = fracsec_to_ms(0x0F07A120, 1_000_000, 3);
        assert!((ms - 500.0).abs() < 0.1, "expected ~500.0, got {ms}");
    }

    #[test]
    fn fracsec_zero_meas_rate() {
        let ms = fracsec_to_ms(1000, 0, 3);
        assert!((ms - 0.0).abs() < 0.001);
    }
}
