use thiserror::Error;

#[derive(Debug, Error)]
pub enum PmuError {
    #[error("Parse error: {0}")]
    Parse(String),

    #[error("Build error: {0}")]
    Build(String),

    #[error("CRC mismatch: expected {expected:#06x}, got {actual:#06x}")]
    CrcMismatch { expected: u16, actual: u16 },

    #[error("Invalid sync byte: {0:#06x}")]
    InvalidSync(u16),

    #[error("Connection error: {0}")]
    Connection(String),

    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
}

pub type Result<T> = std::result::Result<T, PmuError>;
