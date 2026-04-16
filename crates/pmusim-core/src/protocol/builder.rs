use crate::error::{PmuError, Result};
use super::constants::{make_sync, FrameType, ProtocolVersion, IDCODE_LEN, STN_LEN, CHNAM_LEN};
use super::crc16::crc16;
use super::frame::*;

fn write_u16(buf: &mut Vec<u8>, val: u16) {
    buf.extend_from_slice(&val.to_be_bytes());
}

fn write_u32(buf: &mut Vec<u8>, val: u32) {
    buf.extend_from_slice(&val.to_be_bytes());
}

fn write_i16(buf: &mut Vec<u8>, val: i16) {
    buf.extend_from_slice(&val.to_be_bytes());
}

fn encode_ascii_padded(s: &str, len: usize) -> Vec<u8> {
    let mut buf = s.as_bytes().to_vec();
    buf.resize(len, 0);
    buf.truncate(len);
    buf
}

fn encode_gbk_padded(s: &str, len: usize) -> Vec<u8> {
    let (cow, _, _) = encoding_rs::GBK.encode(s);
    let mut buf = cow.into_owned();
    buf.resize(len, 0);
    buf.truncate(len);
    buf
}

fn append_crc(buf: &mut Vec<u8>) {
    let crc = crc16(buf);
    write_u16(buf, crc);
}

fn patch_size(buf: &mut [u8], size: u16) {
    let bytes = size.to_be_bytes();
    buf[2] = bytes[0];
    buf[3] = bytes[1];
}

pub fn build_command(frame: &CommandFrame) -> Result<Vec<u8>> {
    let mut buf = Vec::new();

    match frame.version {
        ProtocolVersion::V2 => {
            let sync = make_sync(FrameType::Command, ProtocolVersion::V2);
            let frame_size: u16 = 20;
            write_u16(&mut buf, sync);
            write_u16(&mut buf, frame_size);
            write_u32(&mut buf, frame.soc);
            buf.extend_from_slice(&encode_ascii_padded(&frame.idcode, IDCODE_LEN));
            write_u16(&mut buf, frame.cmd);
        }
        ProtocolVersion::V3 => {
            let sync = make_sync(FrameType::Command, ProtocolVersion::V3);
            let frame_size: u16 = 24;
            write_u16(&mut buf, sync);
            write_u16(&mut buf, frame_size);
            buf.extend_from_slice(&encode_ascii_padded(&frame.idcode, IDCODE_LEN));
            write_u32(&mut buf, frame.soc);
            write_u32(&mut buf, frame.fracsec);
            write_u16(&mut buf, frame.cmd);
        }
    }

    append_crc(&mut buf);
    Ok(buf)
}

pub fn build_config(frame: &ConfigFrame) -> Result<Vec<u8>> {
    let ft = match frame.cfg_type {
        2 => FrameType::Cfg1,
        3 => FrameType::Cfg2,
        _ => return Err(PmuError::Build(format!("Unknown cfg_type: {}", frame.cfg_type))),
    };

    let sync = make_sync(ft, frame.version);

    // Build PMU data block
    let mut pmu_block = Vec::new();
    pmu_block.extend_from_slice(&encode_gbk_padded(&frame.stn, STN_LEN));
    pmu_block.extend_from_slice(&encode_ascii_padded(&frame.pmu_idcode, IDCODE_LEN));
    write_u16(&mut pmu_block, frame.format_flags);
    write_u16(&mut pmu_block, frame.phnmr);
    write_u16(&mut pmu_block, frame.annmr);
    write_u16(&mut pmu_block, frame.dgnmr);

    for name in &frame.channel_names {
        pmu_block.extend_from_slice(&encode_gbk_padded(name, CHNAM_LEN));
    }

    for &u in &frame.phunit {
        write_u32(&mut pmu_block, u);
    }
    for &u in &frame.anunit {
        write_u32(&mut pmu_block, u);
    }
    for &(hi, lo) in &frame.digunit {
        write_u32(&mut pmu_block, ((hi as u32) << 16) | (lo as u32 & 0xFFFF));
    }

    write_u16(&mut pmu_block, frame.fnom);
    write_u16(&mut pmu_block, frame.period);

    // Build header
    let mut buf = Vec::new();
    write_u16(&mut buf, sync);
    write_u16(&mut buf, 0); // SIZE placeholder

    match frame.version {
        ProtocolVersion::V2 => {
            write_u32(&mut buf, frame.soc);
            write_u16(&mut buf, frame.d_frame);
            write_u32(&mut buf, frame.meas_rate);
            write_u16(&mut buf, frame.num_pmu);
        }
        ProtocolVersion::V3 => {
            buf.extend_from_slice(&encode_ascii_padded(&frame.idcode, IDCODE_LEN));
            write_u32(&mut buf, frame.soc);
            write_u32(&mut buf, frame.fracsec);
            write_u32(&mut buf, frame.meas_rate);
            write_u16(&mut buf, frame.num_pmu);
        }
    }

    buf.extend_from_slice(&pmu_block);

    let frame_size = (buf.len() + 2) as u16; // +2 for CRC
    patch_size(&mut buf, frame_size);

    append_crc(&mut buf);
    Ok(buf)
}

pub fn build_data(frame: &DataFrame, _phnmr: u16, _annmr: u16, _dgnmr: u16) -> Result<Vec<u8>> {
    let sync = make_sync(FrameType::Data, frame.version);

    let mut buf = Vec::new();
    write_u16(&mut buf, sync);
    write_u16(&mut buf, 0); // SIZE placeholder

    match frame.version {
        ProtocolVersion::V2 => {
            write_u32(&mut buf, frame.soc);
            write_u32(&mut buf, frame.fracsec);
            write_u16(&mut buf, frame.stat);
        }
        ProtocolVersion::V3 => {
            buf.extend_from_slice(&encode_ascii_padded(&frame.idcode, IDCODE_LEN));
            write_u32(&mut buf, frame.soc);
            write_u32(&mut buf, frame.fracsec);
            write_u16(&mut buf, frame.stat);
        }
    }

    for &(mag, ang) in &frame.phasors {
        write_i16(&mut buf, mag);
        write_i16(&mut buf, ang);
    }

    // FREQ and DFREQ written as u16 (matching Python builder's ">HH")
    write_u16(&mut buf, frame.freq as u16);
    write_u16(&mut buf, frame.dfreq as u16);

    for &a in &frame.analog {
        write_i16(&mut buf, a);
    }
    for &d in &frame.digital {
        write_u16(&mut buf, d);
    }

    let frame_size = (buf.len() + 2) as u16;
    patch_size(&mut buf, frame_size);

    append_crc(&mut buf);
    Ok(buf)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::protocol::parser::parse;

    #[test]
    fn v2_command_known_hex() {
        let frame = CommandFrame {
            version: ProtocolVersion::V2,
            idcode: "0GX00GP1".into(),
            soc: 0x6757DD1D,
            fracsec: 0,
            cmd: 0x0004,
        };
        let result = build_command(&frame).unwrap();
        let expected = hex::decode("aa4200146757dd1d30475830304750310004a5cb").unwrap();
        assert_eq!(result, expected);
    }

    #[test]
    fn v3_command_known_hex() {
        let frame = CommandFrame {
            version: ProtocolVersion::V3,
            idcode: "0GX00GP1".into(),
            soc: 0x67B2C719,
            fracsec: 0,
            cmd: 0x0004,
        };
        let result = build_command(&frame).unwrap();
        let expected =
            hex::decode("aa430018304758303047503167b2c719000000000004ac08").unwrap();
        assert_eq!(result, expected);
    }

    #[test]
    fn v2_command_roundtrip() {
        let frame = CommandFrame {
            version: ProtocolVersion::V2,
            idcode: "TESTID01".into(),
            soc: 0x12345678,
            fracsec: 0,
            cmd: 0x0002,
        };
        let data = build_command(&frame).unwrap();
        let parsed = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Command(cmd) = parsed {
            assert_eq!(cmd.version, frame.version);
            assert_eq!(cmd.idcode, frame.idcode);
            assert_eq!(cmd.soc, frame.soc);
            assert_eq!(cmd.cmd, frame.cmd);
        } else {
            panic!("Expected Command frame");
        }
    }

    #[test]
    fn v2_data_roundtrip() {
        let frame = DataFrame {
            version: ProtocolVersion::V2,
            idcode: String::new(),
            soc: 0x67A99D11,
            fracsec: 0x000D9490,
            stat: 0x0000,
            phasors: vec![(100, -50), (200, 30)],
            freq: 0,
            dfreq: 0,
            analog: vec![300, 3000, 9175],
            digital: vec![0x000A],
        };
        let phnmr = 2u16;
        let annmr = 3u16;
        let dgnmr = 1u16;
        let data = build_data(&frame, phnmr, annmr, dgnmr).unwrap();
        let parsed = parse(&data, phnmr, annmr, dgnmr).unwrap();
        if let Frame::Data(df) = parsed {
            assert_eq!(df.version, frame.version);
            assert_eq!(df.idcode, frame.idcode);
            assert_eq!(df.soc, frame.soc);
            assert_eq!(df.fracsec, frame.fracsec);
            assert_eq!(df.stat, frame.stat);
            assert_eq!(df.phasors, frame.phasors);
            assert_eq!(df.freq, frame.freq);
            assert_eq!(df.dfreq, frame.dfreq);
            assert_eq!(df.analog, frame.analog);
            assert_eq!(df.digital, frame.digital);
        } else {
            panic!("Expected Data frame");
        }
    }

    #[test]
    fn v3_config_roundtrip() {
        let annmr = 2u16;
        let dgnmr = 1u16;
        let mut channel_names: Vec<String> = (0..annmr)
            .map(|i| format!("AN{:02}", i))
            .collect();
        for _ in 0..(dgnmr * 16) {
            channel_names.push("DIG".into());
        }

        let frame = ConfigFrame {
            version: ProtocolVersion::V3,
            cfg_type: 3,
            idcode: "0GX00GP1".into(),
            soc: 0x67B2C719,
            fracsec: 0,
            d_frame: 0,
            meas_rate: 100,
            num_pmu: 1,
            stn: "PMU_Station".into(),
            pmu_idcode: "0GX00GP1".into(),
            format_flags: 0,
            phnmr: 0,
            annmr,
            dgnmr,
            channel_names,
            phunit: vec![],
            anunit: vec![0x00000064; annmr as usize],
            digunit: vec![(0x0001, 0x0000)],
            fnom: 0x0001,
            period: 100,
        };

        let data = build_config(&frame).unwrap();
        let parsed = parse(&data, 0, 0, 0).unwrap();
        if let Frame::Config(cfg) = parsed {
            assert_eq!(cfg.version, frame.version);
            assert_eq!(cfg.cfg_type, frame.cfg_type);
            assert_eq!(cfg.idcode, frame.idcode);
            assert_eq!(cfg.soc, frame.soc);
            assert_eq!(cfg.fracsec, frame.fracsec);
            assert_eq!(cfg.meas_rate, frame.meas_rate);
            assert_eq!(cfg.stn, frame.stn);
            assert_eq!(cfg.pmu_idcode, frame.pmu_idcode);
            assert_eq!(cfg.phnmr, frame.phnmr);
            assert_eq!(cfg.annmr, frame.annmr);
            assert_eq!(cfg.dgnmr, frame.dgnmr);
            assert_eq!(cfg.channel_names, frame.channel_names);
            assert_eq!(cfg.anunit, frame.anunit);
            assert_eq!(cfg.digunit, frame.digunit);
            assert_eq!(cfg.fnom, frame.fnom);
            assert_eq!(cfg.period, frame.period);
        } else {
            panic!("Expected Config frame");
        }
    }

    #[test]
    fn v2_known_data_rebuild() {
        // Parse the known-good V2 data frame, rebuild it, and compare bytes
        let known = hex::decode(
            "aa02002c67a99d11000d9490000000000000012c0bb823d700c8000000000000000023d700000000000a21f3",
        )
        .unwrap();
        let parsed = parse(&known, 0, 11, 1).unwrap();
        if let Frame::Data(df) = parsed {
            let rebuilt = build_data(&df, 0, 11, 1).unwrap();
            assert_eq!(rebuilt, known);
        } else {
            panic!("Expected Data frame");
        }
    }

    #[test]
    fn v3_known_data_rebuild() {
        let known = hex::decode(
            "aa030034304758303047503167b2c71d000000000000000000000190012c23e10000000000000000000023e100000000000ae884",
        )
        .unwrap();
        let parsed = parse(&known, 0, 11, 1).unwrap();
        if let Frame::Data(df) = parsed {
            let rebuilt = build_data(&df, 0, 11, 1).unwrap();
            assert_eq!(rebuilt, known);
        } else {
            panic!("Expected Data frame");
        }
    }
}
