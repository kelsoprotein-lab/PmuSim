use std::sync::Arc;
use tokio::sync::Mutex;

use crate::network::master::MasterStation;

pub struct AppState {
    pub master: Arc<Mutex<Option<MasterStation>>>,
}

impl Default for AppState {
    fn default() -> Self {
        Self {
            master: Arc::new(Mutex::new(None)),
        }
    }
}
