//! Mobile placeholder for the desktop-only local audiobook transcription flow.
//!
//! The desktop implementation links whisper.cpp and Symphonia for local Audible
//! transcription. Mobile builds keep those native dependencies out of the APK
//! until we build a mobile-specific transcription path.

use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Runtime};

#[derive(Debug, Deserialize)]
pub struct TranscribeAudiobookRequest {
    pub asin: String,
    pub audio_path: String,
    pub server_url: String,
    pub jwt: String,
    #[serde(default)]
    pub agent_id: Option<String>,
    #[serde(default)]
    pub model: Option<String>,
    #[serde(default)]
    pub language: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct TranscribeAudiobookResponse {
    pub asin: String,
    pub segment_count: usize,
    pub duration_seconds: f32,
    pub uploaded: bool,
}

#[tauri::command]
pub async fn audible_transcribe<R: Runtime>(
    _app: AppHandle<R>,
    req: TranscribeAudiobookRequest,
) -> Result<TranscribeAudiobookResponse, String> {
    Err(format!(
        "Local Audible transcription is not available in this mobile preview build for {}.",
        req.asin
    ))
}
