use super::constants::ProtocolVersion;

#[derive(Debug, Clone)]
pub struct CommandFrame {
    pub version: ProtocolVersion,
    pub idcode: String,
    pub soc: u32,
    pub fracsec: u32,
    pub cmd: u16,
}

#[derive(Debug, Clone)]
pub struct ConfigFrame {
    pub version: ProtocolVersion,
    pub cfg_type: u8,
    pub idcode: String,
    pub soc: u32,
    pub fracsec: u32,
    pub d_frame: u16,
    pub meas_rate: u32,
    pub num_pmu: u16,
    pub stn: String,
    pub pmu_idcode: String,
    pub format_flags: u16,
    pub phnmr: u16,
    pub annmr: u16,
    pub dgnmr: u16,
    pub channel_names: Vec<String>,
    pub phunit: Vec<u32>,
    pub anunit: Vec<u32>,
    pub digunit: Vec<(u16, u16)>,
    pub fnom: u16,
    pub period: u16,
}

impl ConfigFrame {
    pub fn period_ms(&self) -> f64 {
        let base_freq: f64 = if self.fnom & 1 != 0 { 50.0 } else { 60.0 };
        (self.period as f64 / 100.0) * (1000.0 / base_freq)
    }

    pub fn analog_factor(&self, index: usize) -> f64 {
        self.anunit[index] as f64 * 0.00001
    }
}

#[derive(Debug, Clone)]
pub struct DataFrame {
    pub version: ProtocolVersion,
    pub idcode: String,
    pub soc: u32,
    pub fracsec: u32,
    pub stat: u16,
    pub phasors: Vec<(i16, i16)>,
    pub freq: i16,
    pub dfreq: i16,
    pub analog: Vec<i16>,
    pub digital: Vec<u16>,
}

impl DataFrame {
    pub fn data_valid(&self) -> bool {
        (self.stat & 0x8000) == 0
    }

    pub fn sync_ok(&self) -> bool {
        (self.stat & 0x2000) == 0
    }
}

#[derive(Debug, Clone)]
pub enum Frame {
    Command(CommandFrame),
    Config(ConfigFrame),
    Data(DataFrame),
}
