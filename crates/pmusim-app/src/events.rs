use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
#[serde(tag = "type")]
pub enum PmuEvent {
    SessionCreated { idcode: String, peer_ip: String },
    SessionDisconnected { idcode: String },
    Cfg1Received { idcode: String, cfg: ConfigInfo },
    Cfg2Sent { idcode: String },
    Cfg2Received { idcode: String, cfg: ConfigInfo },
    StreamingStarted { idcode: String },
    StreamingStopped { idcode: String },
    DataFrame { idcode: String, data: DataInfo },
    RawFrame { idcode: String, direction: String, hex: String },
    HeartbeatTimeout { idcode: String },
    Error { idcode: String, error: String },
}

#[derive(Clone, Debug, Serialize)]
pub struct ConfigInfo {
    pub cfg_type: u8,
    pub version: u8,
    pub stn: String,
    pub idcode: String,
    pub format_flags: u16,
    pub period: u16,
    pub meas_rate: u32,
    pub phnmr: u16,
    pub annmr: u16,
    pub dgnmr: u16,
    pub channel_names: Vec<String>,
    pub anunit: Vec<u32>,
}

#[derive(Clone, Debug, Serialize)]
pub struct DataInfo {
    pub soc: u32,
    pub fracsec: u32,
    pub stat: u16,
    pub analog: Vec<f64>,
    pub digital: Vec<u16>,
    pub phasors: Vec<(i16, i16)>,
}

impl From<&pmusim_core::protocol::frame::ConfigFrame> for ConfigInfo {
    fn from(cfg: &pmusim_core::protocol::frame::ConfigFrame) -> Self {
        Self {
            cfg_type: cfg.cfg_type,
            version: cfg.version as u8,
            stn: cfg.stn.clone(),
            idcode: cfg.pmu_idcode.clone(),
            format_flags: cfg.format_flags,
            period: cfg.period,
            meas_rate: cfg.meas_rate,
            phnmr: cfg.phnmr,
            annmr: cfg.annmr,
            dgnmr: cfg.dgnmr,
            channel_names: cfg.channel_names.clone(),
            anunit: cfg.anunit.clone(),
        }
    }
}
