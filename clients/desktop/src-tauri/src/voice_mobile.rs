//! Mobile voice compatibility layer.
//!
//! The desktop-native recorder uses `cpal`, which pulls in Android's Oboe
//! C++ backend. The mobile webview already supports MediaRecorder, so on
//! Android/iOS we intentionally return "unavailable" here and let the
//! frontend use the browser capture path.

use anyhow::{anyhow, Result};
use serde::Serialize;

#[derive(Debug, Serialize)]
pub struct VoiceStartResponse {
    pub device_name: String,
    pub sample_rate: u32,
    pub channels: u16,
}

#[derive(Debug, Serialize)]
pub struct VoiceStopResponse {
    pub audio_base64: String,
    pub mime_type: String,
    pub size_bytes: usize,
    pub duration_ms: u64,
    pub sample_count: usize,
    pub sample_rate: u32,
    pub channels: u16,
}

#[derive(Default)]
pub struct VoiceRecorder;

impl VoiceRecorder {
    pub fn new() -> Self {
        Self
    }

    pub fn start(&self) -> Result<VoiceStartResponse> {
        Err(anyhow!(
            "native voice recording is not available in the mobile build"
        ))
    }

    pub fn stop(&self) -> Result<VoiceStopResponse> {
        Err(anyhow!(
            "native voice recording is not available in the mobile build"
        ))
    }

    pub fn cancel(&self) -> Result<()> {
        Ok(())
    }
}
