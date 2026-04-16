use crate::error::{PmuError, Result};
use super::constants::{parse_sync, FrameType, ProtocolVersion};
use super::crc16::crc16;
use super::frame::*;

fn read_u16(data: &[u8], off: usize) -> u16 {
    u16::from_be_bytes([data[off], data[off + 1]])
}

fn read_u32(data: &[u8], off: usize) -> u32 {
    u32::from_be_bytes([data[off], data[off + 1], data[off + 2], data[off + 3]])
}

fn read_i16(data: &[u8], off: usize) -> i16 {
    i16::from_be_bytes([data[off], data[off + 1]])
}

fn decode_ascii(data: &[u8]) -> String {
    String::from_utf8_lossy(data)
        .trim_end_matches('\0')
        .to_string()
}

fn decode_gbk(data: &[u8]) -> String {
    let (cow, _, _) = encoding_rs::GBK.decode(data);
    cow.trim_end_matches('\0').to_string()
}

pub fn parse(data: &[u8], phnmr: u16, annmr: u16, dgnmr: u16) -> Result<Frame> {
    if data.len() < 4 {
        return Err(PmuError::Parse("Frame too short".into()));
    }

    let sync = read_u16(data, 0);
    let (frame_type, version) = parse_sync(sync).map_err(|e| PmuError::Parse(e))?;

    let size = read_u16(data, 2) as usize;
    if data.len() < size {
        return Err(PmuError::Parse(format!(
            "Frame truncated: expected {} bytes, got {}",
            size,
            data.len()
        )));
    }

    // CRC check
    let expected_crc = read_u16(data, size - 2);
    let actual_crc = crc16(&data[..size - 2]);
    if expected_crc != actual_crc {
        return Err(PmuError::CrcMismatch {
            expected: expected_crc,
            actual: actual_crc,
        });
    }

    match frame_type {
        FrameType::Command => parse_command(data, version),
        FrameType::Cfg1 | FrameType::Cfg2 => parse_config(data, version, frame_type),
        FrameType::Data => parse_data(data, version, phnmr, annmr, dgnmr),
    }
}

fn parse_command(data: &[u8], version: ProtocolVersion) -> Result<Frame> {
    match version {
        ProtocolVersion::V2 => {
            // V2 Command (20 bytes): SYNC(2) + SIZE(2) + SOC(4) + IDCODE(8) + CMD(2) + CRC(2)
            let soc = read_u32(data, 4);
            let idcode = decode_ascii(&data[8..16]);
            let cmd = read_u16(data, 16);
            Ok(Frame::Command(CommandFrame {
                version,
                idcode,
                soc,
                fracsec: 0,
                cmd,
            }))
        }
        ProtocolVersion::V3 => {
            // V3 Command (24 bytes): SYNC(2) + SIZE(2) + IDCODE(8) + SOC(4) + FRACSEC(4) + CMD(2) + CRC(2)
            let idcode = decode_ascii(&data[4..12]);
            let soc = read_u32(data, 12);
            let fracsec = read_u32(data, 16);
            let cmd = read_u16(data, 20);
            Ok(Frame::Command(CommandFrame {
                version,
                idcode,
                soc,
                fracsec,
                cmd,
            }))
        }
    }
}

fn parse_config(data: &[u8], version: ProtocolVersion, frame_type: FrameType) -> Result<Frame> {
    let cfg_type = match frame_type {
        FrameType::Cfg1 => 2,
        FrameType::Cfg2 => 3,
        _ => unreachable!(),
    };

    let (idcode, soc, fracsec, d_frame, meas_rate, num_pmu, pmu_start) = match version {
        ProtocolVersion::V2 => {
            let soc = read_u32(data, 4);
            let d_frame = read_u16(data, 8);
            let meas_rate = read_u32(data, 10);
            let num_pmu = read_u16(data, 14);
            (String::new(), soc, 0u32, d_frame, meas_rate, num_pmu, 16usize)
        }
        ProtocolVersion::V3 => {
            let idcode = decode_ascii(&data[4..12]);
            let soc = read_u32(data, 12);
            let fracsec = read_u32(data, 16);
            let meas_rate = read_u32(data, 20);
            let num_pmu = read_u16(data, 24);
            (idcode, soc, fracsec, 0u16, meas_rate, num_pmu, 26usize)
        }
    };

    // Parse PMU data block (first PMU only for now)
    let mut off = pmu_start;

    let stn = decode_gbk(&data[off..off + 16]);
    off += 16;

    let pmu_idcode = decode_ascii(&data[off..off + 8]);
    off += 8;

    let format_flags = read_u16(data, off);
    off += 2;

    let phnmr = read_u16(data, off);
    off += 2;
    let annmr = read_u16(data, off);
    off += 2;
    let dgnmr = read_u16(data, off);
    off += 2;

    let total_channels = phnmr as usize + annmr as usize + dgnmr as usize * 16;
    let mut channel_names = Vec::with_capacity(total_channels);
    for _ in 0..total_channels {
        channel_names.push(decode_gbk(&data[off..off + 16]));
        off += 16;
    }

    let mut phunit = Vec::with_capacity(phnmr as usize);
    for _ in 0..phnmr {
        phunit.push(read_u32(data, off));
        off += 4;
    }

    let mut anunit = Vec::with_capacity(annmr as usize);
    for _ in 0..annmr {
        anunit.push(read_u32(data, off));
        off += 4;
    }

    let mut digunit = Vec::with_capacity(dgnmr as usize);
    for _ in 0..dgnmr {
        let hi = read_u16(data, off);
        let lo = read_u16(data, off + 2);
        digunit.push((hi, lo));
        off += 4;
    }

    let fnom = read_u16(data, off);
    off += 2;
    let period = read_u16(data, off);

    // V2: primary idcode comes from per-PMU field; V3: from DC_IDCODE in header
    let primary_idcode = match version {
        ProtocolVersion::V2 => pmu_idcode.clone(),
        ProtocolVersion::V3 => idcode,
    };

    Ok(Frame::Config(ConfigFrame {
        version,
        cfg_type,
        idcode: primary_idcode,
        soc,
        fracsec,
        d_frame,
        meas_rate,
        num_pmu,
        stn,
        pmu_idcode,
        format_flags,
        phnmr,
        annmr,
        dgnmr,
        channel_names,
        phunit,
        anunit,
        digunit,
        fnom,
        period,
    }))
}

fn parse_data(
    data: &[u8],
    version: ProtocolVersion,
    phnmr: u16,
    annmr: u16,
    dgnmr: u16,
) -> Result<Frame> {
    let (idcode, soc, fracsec, stat, val_start) = match version {
        ProtocolVersion::V2 => {
            let soc = read_u32(data, 4);
            let fracsec = read_u32(data, 8);
            let stat = read_u16(data, 12);
            (String::new(), soc, fracsec, stat, 14usize)
        }
        ProtocolVersion::V3 => {
            let idcode = decode_ascii(&data[4..12]);
            let soc = read_u32(data, 12);
            let fracsec = read_u32(data, 16);
            let stat = read_u16(data, 20);
            (idcode, soc, fracsec, stat, 22usize)
        }
    };

    let mut off = val_start;

    let mut phasors = Vec::with_capacity(phnmr as usize);
    for _ in 0..phnmr {
        let mag = read_i16(data, off);
        let angle = read_i16(data, off + 2);
        phasors.push((mag, angle));
        off += 4;
    }

    let freq = read_i16(data, off);
    off += 2;
    let dfreq = read_i16(data, off);
    off += 2;

    let mut analog = Vec::with_capacity(annmr as usize);
    for _ in 0..annmr {
        analog.push(read_i16(data, off));
        off += 2;
    }

    let mut digital = Vec::with_capacity(dgnmr as usize);
    for _ in 0..dgnmr {
        digital.push(read_u16(data, off));
        off += 2;
    }

    Ok(Frame::Data(DataFrame {
        version,
        idcode,
        soc,
        fracsec,
        stat,
        phasors,
        freq,
        dfreq,
        analog,
        digital,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::constants::ProtocolVersion;

    #[test]
    fn v2_request_cfg1() {
        let data = hex::decode("aa4200146757dd1d30475830304750310004a5cb").unwrap();
        let frame = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = frame {
            assert_eq!(cmd.version, ProtocolVersion::V2);
            assert_eq!(cmd.idcode, "0GX00GP1");
            assert_eq!(cmd.soc, 0x6757DD1D);
            assert_eq!(cmd.cmd, 0x0004);
        } else {
            panic!("Expected Command frame");
        }
    }

    #[test]
    fn v2_heartbeat() {
        let data = hex::decode("aa4200146757dd22304758303047503140009cf7").unwrap();
        let frame = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = frame {
            assert_eq!(cmd.cmd, 0x4000);
        } else {
            panic!("Expected Command frame");
        }
    }

    #[test]
    fn v3_request_cfg1() {
        let data =
            hex::decode("aa430018304758303047503167b2c719000000000004ac08").unwrap();
        let frame = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = frame {
            assert_eq!(cmd.version, ProtocolVersion::V3);
            assert_eq!(cmd.idcode, "0GX00GP1");
            assert_eq!(cmd.soc, 0x67B2C719);
            assert_eq!(cmd.fracsec, 0);
            assert_eq!(cmd.cmd, 0x0004);
        } else {
            panic!("Expected Command frame");
        }
    }

    #[test]
    fn v3_heartbeat() {
        let data =
            hex::decode("aa430018304758303047503167b2c71e000000004000f804").unwrap();
        let frame = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = frame {
            assert_eq!(cmd.cmd, 0x4000);
        } else {
            panic!("Expected Command frame");
        }
    }

    #[test]
    fn v2_data() {
        // Correct hex from Python reference tests (44 bytes)
        let data = hex::decode(
            "aa02002c67a99d11000d9490000000000000012c0bb823d700c8000000000000000023d700000000000a21f3",
        )
        .unwrap();
        let frame = parse(&data, 0, 11, 1).unwrap();
        if let Frame::Data(df) = frame {
            assert_eq!(df.version, ProtocolVersion::V2);
            assert_eq!(df.idcode, "");
            assert_eq!(df.soc, 0x67A99D11);
            assert_eq!(df.fracsec, 0x000D9490);
            assert_eq!(df.analog.len(), 11);
            assert_eq!(df.analog[0], 0x012C);
            assert_eq!(df.analog[1], 0x0BB8);
            assert_eq!(df.analog[2], 0x23D7);
            assert_eq!(df.digital, vec![0x000A]);
        } else {
            panic!("Expected Data frame");
        }
    }

    #[test]
    fn v3_data() {
        let data = hex::decode(
            "aa030034304758303047503167b2c71d000000000000000000000190012c23e10000000000000000000023e100000000000ae884",
        )
        .unwrap();
        let frame = parse(&data, 0, 11, 1).unwrap();
        if let Frame::Data(df) = frame {
            assert_eq!(df.version, ProtocolVersion::V3);
            assert_eq!(df.idcode, "0GX00GP1");
            assert_eq!(df.analog[0], 0x0190);
        } else {
            panic!("Expected Data frame");
        }
    }

    #[test]
    fn invalid_sync() {
        let data = hex::decode("bb4200146757dd1d30475830304750310004a5cb").unwrap();
        assert!(parse(&data, 0, 0, 0).is_err());
    }

    #[test]
    fn frame_too_short() {
        let data = hex::decode("aa42").unwrap();
        assert!(parse(&data, 0, 0, 0).is_err());
    }

    #[test]
    fn crc_mismatch() {
        let mut data = hex::decode("aa4200146757dd1d30475830304750310004a5cb").unwrap();
        // Corrupt last 2 bytes
        let len = data.len();
        data[len - 1] = 0xFF;
        data[len - 2] = 0xFF;
        assert!(parse(&data, 0, 0, 0).is_err());
    }
}
