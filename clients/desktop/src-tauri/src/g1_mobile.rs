//! Mobile fallback for the desktop G1 bridge.
//!
//! The real Even Realities G1 implementation uses desktop BLE via
//! `btleplug`. Mobile keeps its existing Flutter-native integration for now,
//! so the shared Tauri command surface returns "unsupported" here.

use std::sync::Arc;

use anyhow::{anyhow, Result};
use serde::{Deserialize, Serialize};
use tauri::AppHandle;

use crate::config::DesktopSettings;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum GlassSide {
    Left,
    Right,
}

#[derive(Debug, Clone, Serialize)]
pub struct G1DeviceSummary {
    pub side: GlassSide,
    pub name: String,
    pub id: String,
    pub connected: bool,
}

#[derive(Debug, Clone, Serialize)]
pub struct G1BatteryInfo {
    pub side: GlassSide,
    pub percentage: u8,
    pub voltage: u8,
    pub is_charging: bool,
    pub timestamp: String,
}

#[derive(Debug, Clone, Default, Serialize)]
pub struct G1BatteryStatus {
    pub left: Option<G1BatteryInfo>,
    pub right: Option<G1BatteryInfo>,
    pub last_updated: Option<String>,
}

#[derive(Debug, Clone, Serialize)]
pub struct G1Status {
    pub supported: bool,
    pub scanning: bool,
    pub connected: bool,
    pub left: Option<G1DeviceSummary>,
    pub right: Option<G1DeviceSummary>,
    pub battery: G1BatteryStatus,
    pub last_event: Option<String>,
    pub last_error: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct G1NotificationInput {
    pub title: String,
    #[serde(default)]
    pub subtitle: String,
    #[serde(default)]
    pub message: String,
    #[serde(default)]
    pub app_identifier: String,
    #[serde(default)]
    pub display_name: String,
    #[serde(default)]
    pub msg_id: Option<u64>,
}

#[derive(Debug, Deserialize)]
pub struct G1NoteInput {
    pub note_number: u8,
    pub name: String,
    pub text: String,
}

#[derive(Debug, Deserialize)]
pub struct G1BitmapInput {
    pub data_base64: String,
}

#[derive(Debug, Deserialize)]
pub struct G1DisplayPositionInput {
    pub height: u8,
    pub depth: u8,
}

#[derive(Debug, Serialize)]
pub struct G1MicCapture {
    pub audio_base64: String,
    pub mime_type: String,
    pub size_bytes: usize,
    pub chunk_count: usize,
}

pub struct G1Manager;

impl Default for G1Manager {
    fn default() -> Self {
        Self
    }
}

impl G1Manager {
    pub fn new() -> Self {
        Self
    }

    pub async fn status(&self) -> G1Status {
        unsupported_status()
    }

    pub async fn scan_and_connect(
        self: &Arc<Self>,
        _app: AppHandle,
        _settings: &DesktopSettings,
    ) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn reconnect_saved(
        self: &Arc<Self>,
        _app: AppHandle,
        _settings: &DesktopSettings,
    ) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn disconnect(&self) -> Result<G1Status> {
        Ok(unsupported_status())
    }

    pub async fn send_text(
        &self,
        _text: &str,
        _streaming: bool,
        _delay_ms: u64,
    ) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn clear_display(&self) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn send_notification(&self, _input: G1NotificationInput) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn send_note(&self, _input: G1NoteInput) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn delete_note(&self, _note_number: u8) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn send_bitmap(&self, _input: G1BitmapInput) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn request_battery(&self) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn set_silent_mode(&self, _enabled: bool) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn set_brightness(&self, _level: u8, _auto: bool) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn set_headup_angle(&self, _angle: u8) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn set_wear_detection(&self, _enabled: bool) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn set_display_position(&self, _input: G1DisplayPositionInput) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn set_microphone(&self, _open: bool) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn start_mic_capture(&self) -> Result<G1Status> {
        Err(unsupported())
    }

    pub async fn stop_mic_capture(&self) -> Result<G1MicCapture> {
        Err(unsupported())
    }

    pub async fn sync(&self, _settings: &DesktopSettings) -> Result<G1Status> {
        Err(unsupported())
    }
}

fn unsupported_status() -> G1Status {
    G1Status {
        supported: false,
        scanning: false,
        connected: false,
        left: None,
        right: None,
        battery: G1BatteryStatus::default(),
        last_event: None,
        last_error: Some(
            "Even Realities G1 desktop bridge is not available on this platform".into(),
        ),
    }
}

fn unsupported() -> anyhow::Error {
    anyhow!("Even Realities G1 desktop bridge is not available on this platform")
}
