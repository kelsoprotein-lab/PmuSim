use pmusim_core::protocol::constants::ProtocolVersion;
use pmusim_core::protocol::frame::ConfigFrame;
use tokio::net::tcp::{OwnedReadHalf, OwnedWriteHalf};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SessionState {
    Connected,
    Cfg1Received,
    Cfg2Sent,
    Streaming,
    Disconnected,
}

pub struct SubStationSession {
    pub idcode: String,
    pub version: ProtocolVersion,
    pub peer_ip: String,
    pub peer_host: String,
    pub peer_mgmt_port: u16,
    pub state: SessionState,

    pub mgmt_reader: Option<OwnedReadHalf>,
    pub mgmt_writer: Option<OwnedWriteHalf>,
    pub data_reader: Option<OwnedReadHalf>,
    pub data_writer: Option<OwnedWriteHalf>,

    pub cfg1: Option<ConfigFrame>,
    pub cfg2: Option<ConfigFrame>,

    pub last_heartbeat: std::time::Instant,
    pub missed_heartbeats: u32,
}

impl SubStationSession {
    pub fn new(idcode: String, version: ProtocolVersion, peer_ip: String) -> Self {
        Self {
            idcode,
            version,
            peer_ip: peer_ip.clone(),
            peer_host: peer_ip,
            peer_mgmt_port: 0,
            state: SessionState::Connected,
            mgmt_reader: None,
            mgmt_writer: None,
            data_reader: None,
            data_writer: None,
            cfg1: None,
            cfg2: None,
            last_heartbeat: std::time::Instant::now(),
            missed_heartbeats: 0,
        }
    }

    pub fn mgmt_connected(&self) -> bool {
        self.mgmt_writer.is_some()
    }

    pub fn data_connected(&self) -> bool {
        self.data_writer.is_some()
    }

    pub fn close(&mut self) {
        // Dropping OwnedWriteHalf / OwnedReadHalf closes the underlying socket.
        self.mgmt_reader.take();
        self.mgmt_writer.take();
        self.data_reader.take();
        self.data_writer.take();
        self.state = SessionState::Disconnected;
    }
}
