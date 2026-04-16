use pmusim_core::protocol::constants::ProtocolVersion;
use tauri::{AppHandle, State};

use crate::network::master::MasterStation;
use crate::state::AppState;

#[tauri::command]
pub async fn start_server(
    app_handle: AppHandle,
    state: State<'_, AppState>,
    data_port: u16,
    _protocol: String,
) -> Result<(), String> {
    let mut guard = state.master.lock().await;
    if guard.is_some() {
        return Err("Server already running".into());
    }
    let mut master = MasterStation::new(app_handle, data_port, 30.0);
    master.start().await?;
    *guard = Some(master);
    Ok(())
}

#[tauri::command]
pub async fn stop_server(state: State<'_, AppState>) -> Result<(), String> {
    let mut guard = state.master.lock().await;
    if let Some(master) = guard.as_mut() {
        master.stop().await;
    }
    *guard = None;
    Ok(())
}

#[tauri::command]
pub async fn connect_substation(
    state: State<'_, AppState>,
    host: String,
    port: u16,
) -> Result<(), String> {
    let guard = state.master.lock().await;
    let master = guard.as_ref().ok_or("Server not running")?;
    master
        .connect_to_substation(host, port, ProtocolVersion::V3)
        .await
}

#[tauri::command]
pub async fn send_command(
    state: State<'_, AppState>,
    idcode: String,
    cmd: String,
    period: Option<u32>,
) -> Result<(), String> {
    let guard = state.master.lock().await;
    let master = guard.as_ref().ok_or("Server not running")?;
    master.send_command(idcode, cmd, period).await
}

#[tauri::command]
pub async fn auto_handshake(
    state: State<'_, AppState>,
    idcode: String,
    period: Option<u32>,
) -> Result<(), String> {
    let guard = state.master.lock().await;
    let master = guard.as_ref().ok_or("Server not running")?;
    master.auto_handshake(idcode, period).await
}
