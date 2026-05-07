//! Mobile-safe terminal compatibility layer.
//!
//! AGiXT Desktop's PTY and sudo helpers are desktop-only. Tauri mobile
//! builds still compile the same IPC surface so the shared frontend can
//! load, but these commands return explicit unavailable results.

use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    pub id: String,
    pub shell: String,
    pub cwd: String,
    pub cols: u16,
    pub rows: u16,
    pub closed: bool,
    pub total_bytes: u64,
    pub uptime_secs: u64,
    pub idle_secs: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ReadResult {
    pub data: String,
    pub next_offset: u64,
    pub closed: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct ExecResult {
    pub data: String,
    pub next_offset: u64,
    pub closed: bool,
    pub timed_out: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct ShellRunResult {
    pub command: String,
    pub stdout: String,
    pub stderr: String,
    pub exit_code: i32,
    pub timed_out: bool,
}

#[derive(Default)]
pub struct TerminalManager;

impl TerminalManager {
    pub fn new() -> Self {
        Self
    }

    pub fn open(
        &self,
        _shell: Option<String>,
        _cwd: Option<String>,
        _cols: Option<u16>,
        _rows: Option<u16>,
    ) -> Result<SessionInfo> {
        Err(unavailable_error())
    }

    pub fn list(&self) -> Vec<SessionInfo> {
        Vec::new()
    }

    pub fn close(&self, _id: &str) -> Result<()> {
        Err(unavailable_error())
    }

    pub fn write(&self, _id: &str, _data: &[u8]) -> Result<()> {
        Err(unavailable_error())
    }

    pub fn signal(&self, _id: &str, _signal: &str) -> Result<()> {
        Err(unavailable_error())
    }

    pub fn resize(&self, _id: &str, _cols: u16, _rows: u16) -> Result<()> {
        Err(unavailable_error())
    }

    pub fn read(&self, _id: &str, _offset: u64) -> Result<ReadResult> {
        Err(unavailable_error())
    }

    pub fn exec(
        &self,
        _id: &str,
        _command: &str,
        _idle_ms: u64,
        _timeout_ms: u64,
    ) -> Result<ExecResult> {
        Err(unavailable_error())
    }
}

fn unavailable_error() -> anyhow::Error {
    anyhow!("terminal sessions are not available in the mobile preview build")
}

fn unavailable(command: String) -> ShellRunResult {
    ShellRunResult {
        command,
        stdout: String::new(),
        stderr: "terminal commands are not available in the mobile preview build".into(),
        exit_code: 1,
        timed_out: false,
    }
}

pub async fn shell_run(command: String, _timeout_ms: u64) -> Result<ShellRunResult> {
    Ok(unavailable(command))
}

pub async fn sudo_validate(_password: String) -> Result<ShellRunResult> {
    Ok(unavailable("sudo -v".into()))
}

pub async fn sudo_stored_password() -> Result<Option<String>> {
    Ok(None)
}

pub async fn sudo_password_is_stored() -> Result<bool> {
    Ok(false)
}

pub async fn sudo_store_password(_password: String) -> Result<()> {
    Ok(())
}

pub async fn sudo_delete_stored_password() -> Result<()> {
    Ok(())
}

pub async fn sudo_refresh() -> Result<ShellRunResult> {
    Ok(unavailable("sudo -n -v".into()))
}

pub async fn sudo_refresh_or_restore() -> Result<ShellRunResult> {
    sudo_refresh().await
}

pub async fn sudo_clear() -> Result<ShellRunResult> {
    Ok(unavailable("sudo -k".into()))
}

pub async fn sudo_run(command: String, _timeout_ms: u64) -> Result<ShellRunResult> {
    Ok(unavailable(format!("sudo {command}")))
}

pub async fn sudo_run_with_stored_password(
    command: String,
    timeout_ms: u64,
) -> Result<ShellRunResult> {
    sudo_run(command, timeout_ms).await
}

pub fn sudo_auth_required(_result: &ShellRunResult) -> bool {
    false
}
