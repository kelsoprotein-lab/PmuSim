use std::collections::HashMap;
use std::sync::Arc;

use log::{error, info, warn};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::tcp::OwnedReadHalf;
use tokio::net::{TcpListener, TcpStream};
use tokio::sync::{mpsc, RwLock};
use tokio::task::JoinHandle;

use pmusim_core::protocol::builder::{build_command, build_config};
use pmusim_core::protocol::constants::{
    Cmd, FrameType, ProtocolVersion, IDCODE_LEN, SYNC_BYTE,
};
use pmusim_core::protocol::frame::{CommandFrame, ConfigFrame, Frame};
use pmusim_core::protocol::parser::parse;
use pmusim_core::time_utils::current_soc;
use tauri::{AppHandle, Emitter};

use crate::events::{ConfigInfo, DataInfo, PmuEvent};
use crate::network::session::{SessionState, SubStationSession};

/// Internal command dispatched from the UI thread via mpsc.
#[derive(Debug)]
enum MasterCmd {
    Connect {
        host: String,
        port: u16,
        version: ProtocolVersion,
    },
    RequestCfg1 {
        idcode: String,
    },
    SendCfg2Cmd {
        idcode: String,
    },
    SendCfg2 {
        idcode: String,
        period: Option<u16>,
    },
    RequestCfg2 {
        idcode: String,
    },
    OpenData {
        idcode: String,
    },
    CloseData {
        idcode: String,
    },
    AutoHandshake {
        idcode: String,
        period: Option<u16>,
    },
}

pub struct MasterStation {
    pub data_port: u16,
    pub heartbeat_interval: f64,
    pub sessions: Arc<RwLock<HashMap<String, SubStationSession>>>,
    cmd_tx: mpsc::Sender<MasterCmd>,
    cmd_rx: Option<mpsc::Receiver<MasterCmd>>,
    app_handle: AppHandle,
    tasks: Vec<JoinHandle<()>>,
}

impl MasterStation {
    pub fn new(app_handle: AppHandle, data_port: u16, heartbeat_interval: f64) -> Self {
        let (cmd_tx, cmd_rx) = mpsc::channel(64);
        Self {
            data_port,
            heartbeat_interval,
            sessions: Arc::new(RwLock::new(HashMap::new())),
            cmd_tx,
            cmd_rx: Some(cmd_rx),
            app_handle,
            tasks: Vec::new(),
        }
    }

    /// Start the data TCP listener, command loop, and heartbeat loop.
    pub async fn start(&mut self) -> Result<(), String> {
        let listener = TcpListener::bind(("0.0.0.0", self.data_port))
            .await
            .map_err(|e| format!("Failed to bind data port {}: {e}", self.data_port))?;

        // Update port in case 0 was used (OS-assigned).
        self.data_port = listener
            .local_addr()
            .map(|a| a.port())
            .unwrap_or(self.data_port);

        info!("MasterStation started, data server on port {}", self.data_port);

        // Spawn data listener task.
        let sessions = self.sessions.clone();
        let handle = self.app_handle.clone();
        self.tasks.push(tokio::spawn(async move {
            Self::data_listener_loop(listener, sessions, handle).await;
        }));

        // Spawn command loop.
        let cmd_rx = self
            .cmd_rx
            .take()
            .ok_or_else(|| "start() called twice".to_string())?;
        let sessions = self.sessions.clone();
        let handle = self.app_handle.clone();
        let hb_interval = self.heartbeat_interval;
        self.tasks.push(tokio::spawn(async move {
            Self::command_loop(cmd_rx, sessions.clone(), handle.clone()).await;
        }));

        // Spawn heartbeat loop.
        let sessions = self.sessions.clone();
        let handle = self.app_handle.clone();
        self.tasks.push(tokio::spawn(async move {
            Self::heartbeat_loop(sessions, handle, hb_interval).await;
        }));

        Ok(())
    }

    /// Stop everything.
    pub async fn stop(&mut self) {
        for task in self.tasks.drain(..) {
            task.abort();
        }
        let mut sessions = self.sessions.write().await;
        for session in sessions.values_mut() {
            session.close();
        }
        sessions.clear();
        info!("MasterStation stopped");
    }

    // --- Public command senders (called from tauri commands) ---

    pub async fn connect_to_substation(
        &self,
        host: String,
        port: u16,
        version: ProtocolVersion,
    ) -> Result<(), String> {
        self.cmd_tx
            .send(MasterCmd::Connect {
                host,
                port,
                version,
            })
            .await
            .map_err(|e| e.to_string())
    }

    pub async fn send_command(&self, idcode: String, cmd: String, period: Option<u32>) -> Result<(), String> {
        let mc = match cmd.as_str() {
            "request_cfg1" => MasterCmd::RequestCfg1 { idcode },
            "send_cfg2_cmd" => MasterCmd::SendCfg2Cmd { idcode },
            "send_cfg2" => MasterCmd::SendCfg2 {
                idcode,
                period: period.map(|p| p as u16),
            },
            "request_cfg2" => MasterCmd::RequestCfg2 { idcode },
            "open_data" => MasterCmd::OpenData { idcode },
            "close_data" => MasterCmd::CloseData { idcode },
            other => return Err(format!("Unknown command: {other}")),
        };
        self.cmd_tx.send(mc).await.map_err(|e| e.to_string())
    }

    pub async fn auto_handshake(&self, idcode: String, period: Option<u32>) -> Result<(), String> {
        self.cmd_tx
            .send(MasterCmd::AutoHandshake {
                idcode,
                period: period.map(|p| p as u16),
            })
            .await
            .map_err(|e| e.to_string())
    }

    // =========================================================================
    // Internal loops (run as spawned tasks)
    // =========================================================================

    /// Accept incoming data pipe connections from substations.
    async fn data_listener_loop(
        listener: TcpListener,
        sessions: Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: AppHandle,
    ) {
        loop {
            let Ok((stream, addr)) = listener.accept().await else {
                break;
            };
            let peer_ip = addr.ip().to_string();
            info!("Data connection from {peer_ip}");

            let sessions = sessions.clone();
            let handle = app_handle.clone();
            tokio::spawn(async move {
                Self::handle_data_connection(stream, peer_ip, sessions, handle).await;
            });
        }
    }

    /// Handle a single inbound data pipe connection.
    async fn handle_data_connection(
        stream: TcpStream,
        peer_ip: String,
        sessions: Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: AppHandle,
    ) {
        let (mut reader, writer) = stream.into_split();

        // Read first frame to determine version and idcode.
        let frame_data = match read_frame(&mut reader).await {
            Ok(d) => d,
            Err(e) => {
                warn!("Data connection read error: {e}");
                return;
            }
        };

        if frame_data.len() < 4 {
            return;
        }

        let sync = u16::from_be_bytes([frame_data[0], frame_data[1]]);
        let version = match pmusim_core::protocol::constants::parse_sync(sync) {
            Ok((_, v)) => v,
            Err(e) => {
                warn!("Invalid sync on data pipe: {e}");
                return;
            }
        };

        let session_idcode = if version == ProtocolVersion::V3 {
            // V3 data frames carry IDCODE at offset 4.
            if frame_data.len() < 4 + IDCODE_LEN {
                return;
            }
            String::from_utf8_lossy(&frame_data[4..4 + IDCODE_LEN])
                .trim_end_matches('\0')
                .to_string()
        } else {
            // V2: match by IP.
            let sessions_r = sessions.read().await;
            let found = sessions_r
                .values()
                .find(|s| s.peer_ip == peer_ip)
                .map(|s| s.idcode.clone());
            drop(sessions_r);
            match found {
                Some(id) => id,
                None => {
                    warn!("No mgmt session for V2 data connection from {peer_ip}");
                    return;
                }
            }
        };

        // Attach data writer to session.
        {
            let mut sessions_w = sessions.write().await;
            if let Some(session) = sessions_w.get_mut(&session_idcode) {
                session.data_writer = Some(writer);
            } else {
                // Create a minimal session if not yet known.
                let mut session = SubStationSession::new(session_idcode.clone(), version, peer_ip.clone());
                session.data_writer = Some(writer);
                sessions_w.insert(session_idcode.clone(), session);
                emit_event(
                    &app_handle,
                    PmuEvent::SessionCreated {
                        idcode: session_idcode.clone(),
                        peer_ip: peer_ip.clone(),
                    },
                );
            }
        }

        // Parse first data frame.
        {
            let sessions_r = sessions.read().await;
            if let Some(session) = sessions_r.get(&session_idcode) {
                if let Some(cfg2) = &session.cfg2 {
                    if let Ok(Frame::Data(df)) = parse(&frame_data, cfg2.phnmr, cfg2.annmr, cfg2.dgnmr) {
                        emit_event(
                            &app_handle,
                            PmuEvent::DataFrame {
                                idcode: session_idcode.clone(),
                                data: data_frame_to_info(&df),
                            },
                        );
                    }
                }
            }
        }

        // Continue reading data frames.
        loop {
            let frame_data = match read_frame(&mut reader).await {
                Ok(d) => d,
                Err(_) => break,
            };

            let sessions_r = sessions.read().await;
            if let Some(session) = sessions_r.get(&session_idcode) {
                if let Some(cfg2) = &session.cfg2 {
                    if let Ok(Frame::Data(df)) = parse(&frame_data, cfg2.phnmr, cfg2.annmr, cfg2.dgnmr) {
                        emit_event(
                            &app_handle,
                            PmuEvent::DataFrame {
                                idcode: session_idcode.clone(),
                                data: data_frame_to_info(&df),
                            },
                        );
                    }
                }
            }
            drop(sessions_r);

            emit_event(
                &app_handle,
                PmuEvent::RawFrame {
                    idcode: session_idcode.clone(),
                    direction: "recv".into(),
                    hex: hex_encode(&frame_data),
                },
            );
        }

        // Cleanup.
        let mut sessions_w = sessions.write().await;
        if let Some(session) = sessions_w.get_mut(&session_idcode) {
            session.data_writer = None;
            if !session.mgmt_connected() {
                session.state = SessionState::Disconnected;
                emit_event(
                    &app_handle,
                    PmuEvent::SessionDisconnected {
                        idcode: session_idcode.clone(),
                    },
                );
            }
        }
    }

    /// Process commands from the UI thread.
    async fn command_loop(
        mut cmd_rx: mpsc::Receiver<MasterCmd>,
        sessions: Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: AppHandle,
    ) {
        while let Some(cmd) = cmd_rx.recv().await {
            match cmd {
                MasterCmd::Connect { host, port, version } => {
                    Self::do_connect(host, port, version, sessions.clone(), app_handle.clone()).await;
                }
                MasterCmd::RequestCfg1 { idcode } => {
                    Self::do_send_cmd(&sessions, &app_handle, &idcode, Cmd::SendCfg1 as u16).await;
                }
                MasterCmd::SendCfg2Cmd { idcode } => {
                    Self::do_send_cmd(&sessions, &app_handle, &idcode, Cmd::SendCfg2Cmd as u16).await;
                }
                MasterCmd::SendCfg2 { idcode, period } => {
                    Self::do_send_cfg2(&sessions, &app_handle, &idcode, period).await;
                }
                MasterCmd::RequestCfg2 { idcode } => {
                    Self::do_send_cmd(&sessions, &app_handle, &idcode, Cmd::SendCfg2 as u16).await;
                }
                MasterCmd::OpenData { idcode } => {
                    Self::do_send_cmd(&sessions, &app_handle, &idcode, Cmd::OpenData as u16).await;
                    let mut sessions_w = sessions.write().await;
                    if let Some(s) = sessions_w.get_mut(&idcode) {
                        s.state = SessionState::Streaming;
                    }
                    emit_event(&app_handle, PmuEvent::StreamingStarted { idcode });
                }
                MasterCmd::CloseData { idcode } => {
                    Self::do_send_cmd(&sessions, &app_handle, &idcode, Cmd::CloseData as u16).await;
                    let mut sessions_w = sessions.write().await;
                    if let Some(s) = sessions_w.get_mut(&idcode) {
                        s.state = SessionState::Cfg2Sent;
                    }
                    emit_event(&app_handle, PmuEvent::StreamingStopped { idcode });
                }
                MasterCmd::AutoHandshake { idcode, period } => {
                    Self::do_auto_handshake(&sessions, &app_handle, &idcode, period).await;
                }
            }
        }
    }

    /// Send heartbeats periodically.
    async fn heartbeat_loop(
        sessions: Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: AppHandle,
        interval_secs: f64,
    ) {
        let interval = tokio::time::Duration::from_secs_f64(interval_secs);
        loop {
            tokio::time::sleep(interval).await;

            let idcodes: Vec<String> = {
                let sessions_r = sessions.read().await;
                sessions_r
                    .iter()
                    .filter(|(_, s)| s.mgmt_connected() && s.state != SessionState::Disconnected)
                    .map(|(id, _)| id.clone())
                    .collect()
            };

            for idcode in idcodes {
                Self::do_send_cmd(&sessions, &app_handle, &idcode, Cmd::Heartbeat as u16).await;

                let mut sessions_w = sessions.write().await;
                if let Some(session) = sessions_w.get_mut(&idcode) {
                    session.missed_heartbeats += 1;
                    if session.missed_heartbeats >= 3 {
                        session.state = SessionState::Disconnected;
                        emit_event(
                            &app_handle,
                            PmuEvent::HeartbeatTimeout {
                                idcode: idcode.clone(),
                            },
                        );
                    }
                }
            }
        }
    }

    // =========================================================================
    // Command helpers
    // =========================================================================

    /// Connect to a substation's management port (master = TCP client).
    async fn do_connect(
        host: String,
        port: u16,
        version: ProtocolVersion,
        sessions: Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: AppHandle,
    ) {
        let stream = match TcpStream::connect((host.as_str(), port)).await {
            Ok(s) => s,
            Err(e) => {
                error!("Failed to connect to {host}:{port}: {e}");
                emit_event(
                    &app_handle,
                    PmuEvent::Error {
                        idcode: String::new(),
                        error: format!("Failed to connect {host}:{port}: {e}"),
                    },
                );
                return;
            }
        };

        let (reader, writer) = stream.into_split();

        let tmp_id = format!("{host}:{port}");
        let mut session = SubStationSession::new(tmp_id.clone(), version, host.clone());
        session.peer_host = host.clone();
        session.peer_mgmt_port = port;
        session.mgmt_reader = Some(reader);
        session.mgmt_writer = Some(writer);

        {
            let mut sessions_w = sessions.write().await;
            sessions_w.insert(tmp_id.clone(), session);
        }

        emit_event(
            &app_handle,
            PmuEvent::SessionCreated {
                idcode: tmp_id.clone(),
                peer_ip: host,
            },
        );
        info!("Management pipe connected to {tmp_id}");

        // Spawn management read loop - needs to take ownership of the reader.
        let sessions2 = sessions.clone();
        let handle2 = app_handle.clone();
        tokio::spawn(async move {
            Self::mgmt_read_loop(tmp_id, sessions2, handle2).await;
        });
    }

    /// Read loop for an outbound management connection.
    async fn mgmt_read_loop(
        initial_id: String,
        sessions: Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: AppHandle,
    ) {
        let mut current_id = initial_id.clone();

        // Take the reader out of the session so we can use it without holding the lock.
        let reader = {
            let mut sessions_w = sessions.write().await;
            sessions_w
                .get_mut(&current_id)
                .and_then(|s| s.mgmt_reader.take())
        };
        let Some(mut reader) = reader else {
            return;
        };

        loop {
            let frame_data = match read_frame(&mut reader).await {
                Ok(d) => d,
                Err(_) => break,
            };

            let parsed = {
                // For command/config frames, phnmr/annmr/dgnmr are not needed.
                parse(&frame_data, 0, 0, 0).ok()
            };

            // Re-key session on first real IDCODE.
            if let Some(ref frame) = parsed {
                let real_id = match frame {
                    Frame::Command(c) => Some(c.idcode.clone()),
                    Frame::Config(c) => Some(c.idcode.clone()),
                    Frame::Data(d) => Some(d.idcode.clone()),
                };
                if let Some(real_id) = real_id {
                    if !real_id.is_empty() && real_id != current_id {
                        let mut sessions_w = sessions.write().await;
                        if let Some(mut session) = sessions_w.remove(&current_id) {
                            // Update version from frame if needed.
                            let frame_version = match frame {
                                Frame::Command(c) => c.version,
                                Frame::Config(c) => c.version,
                                Frame::Data(d) => d.version,
                            };
                            session.version = frame_version;
                            session.idcode = real_id.clone();
                            sessions_w.insert(real_id.clone(), session);
                        }
                        drop(sessions_w);

                        emit_event(
                            &app_handle,
                            PmuEvent::SessionCreated {
                                idcode: real_id.clone(),
                                peer_ip: {
                                    let sessions_r = sessions.read().await;
                                    sessions_r
                                        .get(&real_id)
                                        .map(|s| s.peer_ip.clone())
                                        .unwrap_or_default()
                                },
                            },
                        );
                        current_id = real_id;
                    }
                }
            }

            // Process the frame.
            if let Some(frame) = parsed {
                Self::process_mgmt_frame(&sessions, &app_handle, &current_id, &frame, &frame_data)
                    .await;
            }
        }

        // Cleanup on disconnect.
        let mut sessions_w = sessions.write().await;
        if let Some(session) = sessions_w.get_mut(&current_id) {
            session.mgmt_writer = None;
            if !session.data_connected() {
                session.state = SessionState::Disconnected;
                emit_event(
                    &app_handle,
                    PmuEvent::SessionDisconnected {
                        idcode: current_id,
                    },
                );
            }
        }
    }

    /// Process a frame received on the management pipe.
    async fn process_mgmt_frame(
        sessions: &Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: &AppHandle,
        idcode: &str,
        frame: &Frame,
        raw: &[u8],
    ) {
        emit_event(
            app_handle,
            PmuEvent::RawFrame {
                idcode: idcode.to_string(),
                direction: "recv".into(),
                hex: hex_encode(raw),
            },
        );

        match frame {
            Frame::Command(cmd) => {
                if cmd.cmd == Cmd::Heartbeat as u16 {
                    let mut sessions_w = sessions.write().await;
                    if let Some(session) = sessions_w.get_mut(idcode) {
                        session.last_heartbeat = std::time::Instant::now();
                        session.missed_heartbeats = 0;
                    }
                }
                // ACK / NACK are informational - no state change needed.
            }
            Frame::Config(cfg) => {
                if cfg.cfg_type == FrameType::Cfg1 as u8 {
                    let info = ConfigInfo::from(cfg);
                    let mut sessions_w = sessions.write().await;
                    if let Some(session) = sessions_w.get_mut(idcode) {
                        session.cfg1 = Some(cfg.clone());
                        session.state = SessionState::Cfg1Received;
                    }
                    drop(sessions_w);
                    emit_event(
                        app_handle,
                        PmuEvent::Cfg1Received {
                            idcode: idcode.to_string(),
                            cfg: info,
                        },
                    );
                } else if cfg.cfg_type == FrameType::Cfg2 as u8 {
                    let info = ConfigInfo::from(cfg);
                    let mut sessions_w = sessions.write().await;
                    if let Some(session) = sessions_w.get_mut(idcode) {
                        session.cfg2 = Some(cfg.clone());
                    }
                    drop(sessions_w);
                    emit_event(
                        app_handle,
                        PmuEvent::Cfg2Received {
                            idcode: idcode.to_string(),
                            cfg: info,
                        },
                    );
                }
            }
            Frame::Data(_) => {
                // Data on management pipe is unusual; ignore.
            }
        }
    }

    /// Send a command frame to a substation.
    async fn do_send_cmd(
        sessions: &Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: &AppHandle,
        idcode: &str,
        cmd: u16,
    ) {
        let (version, has_writer) = {
            let sessions_r = sessions.read().await;
            match sessions_r.get(idcode) {
                Some(s) => (s.version, s.mgmt_connected()),
                None => return,
            }
        };

        if !has_writer {
            emit_event(
                app_handle,
                PmuEvent::Error {
                    idcode: idcode.to_string(),
                    error: "Management pipe not connected".into(),
                },
            );
            return;
        }

        let frame = CommandFrame {
            version,
            idcode: idcode.to_string(),
            soc: current_soc(),
            fracsec: 0,
            cmd,
        };

        let raw = match build_command(&frame) {
            Ok(r) => r,
            Err(e) => {
                error!("Failed to build command: {e}");
                return;
            }
        };

        let mut sessions_w = sessions.write().await;
        if let Some(session) = sessions_w.get_mut(idcode) {
            if let Some(writer) = session.mgmt_writer.as_mut() {
                if let Err(e) = writer.write_all(&raw).await {
                    error!("Failed to send command to {idcode}: {e}");
                    return;
                }
                let _ = writer.flush().await;
            }
        }
        drop(sessions_w);

        emit_event(
            app_handle,
            PmuEvent::RawFrame {
                idcode: idcode.to_string(),
                direction: "send".into(),
                hex: hex_encode(&raw),
            },
        );
    }

    /// Build and send CFG-2 based on the stored CFG-1 template.
    async fn do_send_cfg2(
        sessions: &Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: &AppHandle,
        idcode: &str,
        period: Option<u16>,
    ) {
        // Build cfg2 from cfg1.
        let cfg2 = {
            let sessions_r = sessions.read().await;
            let session = match sessions_r.get(idcode) {
                Some(s) => s,
                None => return,
            };
            if !session.mgmt_connected() {
                emit_event(
                    app_handle,
                    PmuEvent::Error {
                        idcode: idcode.to_string(),
                        error: "Management pipe not connected".into(),
                    },
                );
                return;
            }
            let cfg1 = match &session.cfg1 {
                Some(c) => c,
                None => {
                    emit_event(
                        app_handle,
                        PmuEvent::Error {
                            idcode: idcode.to_string(),
                            error: "No CFG-1 available".into(),
                        },
                    );
                    return;
                }
            };

            ConfigFrame {
                version: cfg1.version,
                cfg_type: 2, // CFG-1 type value reused for builder (maps to Cfg1 frame type)
                idcode: cfg1.idcode.clone(),
                soc: current_soc(),
                fracsec: 0,
                d_frame: cfg1.d_frame,
                meas_rate: cfg1.meas_rate,
                num_pmu: cfg1.num_pmu,
                stn: cfg1.stn.clone(),
                pmu_idcode: cfg1.pmu_idcode.clone(),
                format_flags: cfg1.format_flags,
                phnmr: cfg1.phnmr,
                annmr: cfg1.annmr,
                dgnmr: cfg1.dgnmr,
                channel_names: cfg1.channel_names.clone(),
                phunit: cfg1.phunit.clone(),
                anunit: cfg1.anunit.clone(),
                digunit: cfg1.digunit.clone(),
                fnom: cfg1.fnom,
                period: period.unwrap_or(cfg1.period),
            }
        };

        let raw = match build_config(&cfg2) {
            Ok(r) => r,
            Err(e) => {
                error!("Failed to build CFG-2: {e}");
                return;
            }
        };

        // Write and update session.
        {
            let mut sessions_w = sessions.write().await;
            if let Some(session) = sessions_w.get_mut(idcode) {
                if let Some(writer) = session.mgmt_writer.as_mut() {
                    if let Err(e) = writer.write_all(&raw).await {
                        error!("Failed to send CFG-2 to {idcode}: {e}");
                        return;
                    }
                    let _ = writer.flush().await;
                }
                session.cfg2 = Some(cfg2);
                session.state = SessionState::Cfg2Sent;
            }
        }

        emit_event(
            app_handle,
            PmuEvent::RawFrame {
                idcode: idcode.to_string(),
                direction: "send".into(),
                hex: hex_encode(&raw),
            },
        );
        emit_event(
            app_handle,
            PmuEvent::Cfg2Sent {
                idcode: idcode.to_string(),
            },
        );
    }

    /// Automated handshake sequence.
    async fn do_auto_handshake(
        sessions: &Arc<RwLock<HashMap<String, SubStationSession>>>,
        app_handle: &AppHandle,
        idcode: &str,
        period: Option<u16>,
    ) {
        // Step 1: Request CFG-1.
        Self::do_send_cmd(sessions, app_handle, idcode, Cmd::SendCfg1 as u16).await;
        tokio::time::sleep(tokio::time::Duration::from_secs(1)).await;

        // Check if CFG-1 was received.
        {
            let sessions_r = sessions.read().await;
            if let Some(session) = sessions_r.get(idcode) {
                if session.cfg1.is_none() {
                    emit_event(
                        app_handle,
                        PmuEvent::Error {
                            idcode: idcode.to_string(),
                            error: "CFG-1 not received after request".into(),
                        },
                    );
                    return;
                }
            } else {
                return;
            }
        }

        // Step 2: Send CFG-2 command.
        Self::do_send_cmd(sessions, app_handle, idcode, Cmd::SendCfg2Cmd as u16).await;
        tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;

        // Step 3: Send CFG-2 config.
        Self::do_send_cfg2(sessions, app_handle, idcode, period).await;
        tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;

        // Step 4: Request CFG-2 back.
        Self::do_send_cmd(sessions, app_handle, idcode, Cmd::SendCfg2 as u16).await;
        tokio::time::sleep(tokio::time::Duration::from_millis(500)).await;

        // Step 5: Open data.
        Self::do_send_cmd(sessions, app_handle, idcode, Cmd::OpenData as u16).await;
        {
            let mut sessions_w = sessions.write().await;
            if let Some(session) = sessions_w.get_mut(idcode) {
                session.state = SessionState::Streaming;
            }
        }
        emit_event(
            app_handle,
            PmuEvent::StreamingStarted {
                idcode: idcode.to_string(),
            },
        );
    }
}

// =============================================================================
// Free helpers
// =============================================================================

/// Read a complete frame from a TCP stream.
async fn read_frame(reader: &mut OwnedReadHalf) -> Result<Vec<u8>, String> {
    let mut header = [0u8; 4];
    reader
        .read_exact(&mut header)
        .await
        .map_err(|e| format!("read header: {e}"))?;

    if header[0] != SYNC_BYTE {
        return Err(format!("Invalid sync byte: {:#04x}", header[0]));
    }

    let frame_size = u16::from_be_bytes([header[2], header[3]]) as usize;
    if frame_size < 4 {
        return Err(format!("Invalid frame size: {frame_size}"));
    }

    let mut buf = vec![0u8; frame_size];
    buf[..4].copy_from_slice(&header);
    reader
        .read_exact(&mut buf[4..])
        .await
        .map_err(|e| format!("read body: {e}"))?;

    Ok(buf)
}

fn hex_encode(data: &[u8]) -> String {
    data.iter().map(|b| format!("{b:02x}")).collect()
}

fn data_frame_to_info(df: &pmusim_core::protocol::frame::DataFrame) -> DataInfo {
    DataInfo {
        soc: df.soc,
        fracsec: df.fracsec,
        stat: df.stat,
        analog: df.analog.iter().map(|&v| v as f64).collect(),
        digital: df.digital.clone(),
        phasors: df.phasors.clone(),
    }
}

fn emit_event(app_handle: &AppHandle, event: PmuEvent) {
    if let Err(e) = app_handle.emit("pmu-event", &event) {
        error!("Failed to emit event: {e}");
    }
}
