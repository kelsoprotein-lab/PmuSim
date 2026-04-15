/// CRC-CCITT: polynomial 0x1021, init 0x0000, MSB-first
pub fn crc16(data: &[u8]) -> u16 {
    let mut crc: u16 = 0x0000;
    for &byte in data {
        crc ^= (byte as u16) << 8;
        for _ in 0..8 {
            if crc & 0x8000 != 0 {
                crc = (crc << 1) ^ 0x1021;
            } else {
                crc <<= 1;
            }
            crc &= 0xFFFF;
        }
    }
    crc
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_data() {
        assert_eq!(crc16(&[]), 0x0000);
    }

    #[test]
    fn v2_command_request_cfg1() {
        let data = hex::decode("aa4200146757dd1d30475830304750310004").unwrap();
        assert_eq!(crc16(&data), 0xA5CB);
    }

    #[test]
    fn v2_command_heartbeat() {
        let data = hex::decode("aa4200146757dd2230475830304750314000").unwrap();
        assert_eq!(crc16(&data), 0x9CF7);
    }

    #[test]
    fn v2_command_ack() {
        let data = hex::decode("aa4200146757dd9d3047583030475031e000").unwrap();
        assert_eq!(crc16(&data), 0x7C57);
    }

    #[test]
    fn v2_command_open_data() {
        let data = hex::decode("aa4200146757dd1e30475830304750310002").unwrap();
        assert_eq!(crc16(&data), 0xBDF7);
    }

    #[test]
    fn v2_command_send_cfg2_cmd() {
        let data = hex::decode("aa4200146757dd1e30475830304750318000").unwrap();
        assert_eq!(crc16(&data), 0x862D);
    }

    #[test]
    fn v3_command_request_cfg1() {
        let data = hex::decode("aa430018304758303047503167b2c719000000000004").unwrap();
        assert_eq!(crc16(&data), 0xAC08);
    }

    #[test]
    fn v3_command_ack() {
        let data = hex::decode("aa430018304758303047503167b2c71a00000000e000").unwrap();
        assert_eq!(crc16(&data), 0x24BC);
    }

    #[test]
    fn v3_command_heartbeat() {
        let data = hex::decode("aa430018304758303047503167b2c71e000000004000").unwrap();
        assert_eq!(crc16(&data), 0xF804);
    }

    #[test]
    fn v2_data_frame() {
        let data = hex::decode(
            "aa02002c67a99d11000d9490000000000000\
             012c0bb823d700c8000000000000000023d700000000000a"
        ).unwrap();
        assert_eq!(crc16(&data), 0x21F3);
    }

    #[test]
    fn v3_data_frame() {
        let data = hex::decode(
            "aa030034304758303047503167b2c71d00000000\
             0000000000000190012c23e100000000000000000000\
             23e100000000000a"
        ).unwrap();
        assert_eq!(crc16(&data), 0xE884);
    }
}
