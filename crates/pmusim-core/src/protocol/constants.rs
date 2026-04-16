pub const SYNC_BYTE: u8 = 0xAA;
pub const IDCODE_LEN: usize = 8;
pub const STN_LEN: usize = 16;
pub const CHNAM_LEN: usize = 16;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum FrameType {
    Data = 0,
    Cfg1 = 2,
    Cfg2 = 3,
    Command = 4,
}

impl FrameType {
    pub fn from_nibble(nibble: u8) -> Option<Self> {
        match nibble {
            0 => Some(Self::Data),
            2 => Some(Self::Cfg1),
            3 => Some(Self::Cfg2),
            4 => Some(Self::Command),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum ProtocolVersion {
    V2 = 2,
    V3 = 3,
}

impl ProtocolVersion {
    pub fn from_nibble(nibble: u8) -> Option<Self> {
        match nibble {
            2 => Some(Self::V2),
            3 => Some(Self::V3),
            _ => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u16)]
pub enum Cmd {
    CloseData = 0x0001,
    OpenData = 0x0002,
    SendHdr = 0x0003,
    SendCfg1 = 0x0004,
    SendCfg2 = 0x0005,
    RecvRef = 0x0008,
    Heartbeat = 0x4000,
    Reset = 0x6000,
    SendCfg2Cmd = 0x8000,
    Trigger = 0xA000,
    Ack = 0xE000,
    Nack = 0x2000,
}

pub fn make_sync(frame_type: FrameType, version: ProtocolVersion) -> u16 {
    (SYNC_BYTE as u16) << 8 | (frame_type as u16) << 4 | version as u16
}

pub fn parse_sync(sync: u16) -> Result<(FrameType, ProtocolVersion), String> {
    if (sync >> 8) as u8 != SYNC_BYTE {
        return Err(format!("Invalid sync byte: {sync:#06x}"));
    }
    let low = (sync & 0xFF) as u8;
    let ft = FrameType::from_nibble((low >> 4) & 0x07)
        .ok_or_else(|| format!("Unknown frame type: {}", (low >> 4) & 0x07))?;
    let ver = ProtocolVersion::from_nibble(low & 0x0F)
        .ok_or_else(|| format!("Unknown version: {}", low & 0x0F))?;
    Ok((ft, ver))
}

pub fn default_ports(version: ProtocolVersion) -> (u16, u16) {
    match version {
        ProtocolVersion::V2 => (7000, 7001),
        ProtocolVersion::V3 => (8000, 8001),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn make_v2_command() {
        assert_eq!(make_sync(FrameType::Command, ProtocolVersion::V2), 0xAA42);
    }

    #[test]
    fn make_v3_command() {
        assert_eq!(make_sync(FrameType::Command, ProtocolVersion::V3), 0xAA43);
    }

    #[test]
    fn make_v2_data() {
        assert_eq!(make_sync(FrameType::Data, ProtocolVersion::V2), 0xAA02);
    }

    #[test]
    fn parse_roundtrip() {
        for &ft in &[FrameType::Data, FrameType::Cfg1, FrameType::Cfg2, FrameType::Command] {
            for &ver in &[ProtocolVersion::V2, ProtocolVersion::V3] {
                let sync = make_sync(ft, ver);
                let (parsed_ft, parsed_ver) = parse_sync(sync).unwrap();
                assert_eq!(parsed_ft, ft);
                assert_eq!(parsed_ver, ver);
            }
        }
    }

    #[test]
    fn parse_invalid_sync() {
        assert!(parse_sync(0xBB42).is_err());
    }
}
