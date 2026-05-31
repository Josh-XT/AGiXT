//! Mobile bridge for Even Realities G1 glasses.
//!
//! Android cannot use the desktop `btleplug` bridge reliably from inside the
//! Tauri shell, so this module keeps the existing Rust command surface and
//! delegates BLE transport to a native Kotlin Tauri plugin.

use std::sync::{Arc, OnceLock};

use anyhow::{anyhow, Context, Result};
use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine;
use chrono::{Local, Utc};
use crc32fast::Hasher;
use serde::{Deserialize, Serialize};
use serde_json::json;
use tauri::plugin::{Builder as PluginBuilder, PluginHandle, TauriPlugin};
use tauri::{AppHandle, Wry};
use tokio::sync::Mutex;

use crate::config::DesktopSettings;

const OPEN_MIC: u8 = 0x0E;
const SEND_RESULT: u8 = 0x4E;
const QUICK_NOTE_ADD: u8 = 0x1E;
const NOTIFICATION: u8 = 0x4B;
const SILENT_MODE: u8 = 0x03;
const BRIGHTNESS: u8 = 0x01;
const DISPLAY_POSITION: u8 = 0x26;
const HEADUP_ANGLE: u8 = 0x0B;
const WEAR_DETECTION: u8 = 0x27;
const BMP: u8 = 0x15;
const CRC: u8 = 0x16;
const SETUP: u8 = 0x04;
const GET_BATTERY: u8 = 0x2C;

#[cfg(target_os = "android")]
static ANDROID_G1_BRIDGE: OnceLock<PluginHandle<Wry>> = OnceLock::new();

pub fn init() -> TauriPlugin<Wry> {
    PluginBuilder::new("g1")
        .setup(|_app, api| {
            #[cfg(target_os = "android")]
            {
                // The G1 (Even Realities glasses) Android bridge is optional —
                // builds that don't ship the `G1Plugin` Kotlin class (e.g. the
                // kiosk/tablet builds) must not abort startup over it. Register
                // best-effort and carry on if the class isn't present.
                match api.register_android_plugin("systems.xt.agixt.desktop", "G1Plugin") {
                    Ok(handle) => {
                        let _ = ANDROID_G1_BRIDGE.set(handle);
                    }
                    Err(e) => {
                        eprintln!("G1 Android plugin unavailable, glasses disabled: {e}");
                    }
                }
            }
            #[cfg(not(target_os = "android"))]
            {
                let _ = api;
            }
            Ok(())
        })
        .build()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum GlassSide {
    Left,
    Right,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct G1DeviceSummary {
    pub side: GlassSide,
    pub name: String,
    pub id: String,
    pub connected: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct G1BatteryInfo {
    pub side: GlassSide,
    pub percentage: u8,
    pub voltage: u8,
    pub is_charging: bool,
    pub timestamp: String,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct G1BatteryStatus {
    pub left: Option<G1BatteryInfo>,
    pub right: Option<G1BatteryInfo>,
    pub last_updated: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
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
    #[serde(default = "default_app_identifier")]
    pub app_identifier: String,
    #[serde(default = "default_display_name")]
    pub display_name: String,
    #[serde(default)]
    pub msg_id: Option<u64>,
}

fn default_app_identifier() -> String {
    "systems.xt.agixt.desktop".to_string()
}

fn default_display_name() -> String {
    "AGiXT".to_string()
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

#[derive(Debug, Serialize, Deserialize)]
pub struct G1MicCapture {
    pub audio_base64: String,
    pub mime_type: String,
    pub size_bytes: usize,
    pub chunk_count: usize,
}

#[derive(Debug, Deserialize)]
struct MobileMicCapture {
    audio_base64: String,
    chunk_count: usize,
}

#[derive(Debug, Clone, Serialize, Default)]
struct SavedDevices {
    left_device_id: Option<String>,
    left_device_name: Option<String>,
    right_device_id: Option<String>,
    right_device_name: Option<String>,
}

impl SavedDevices {
    fn from_settings(settings: &DesktopSettings) -> Self {
        Self {
            left_device_id: settings.g1_left_device_id.clone(),
            left_device_name: settings.g1_left_device_name.clone(),
            right_device_id: settings.g1_right_device_id.clone(),
            right_device_name: settings.g1_right_device_name.clone(),
        }
    }
}

#[derive(Debug, Serialize)]
struct WritePacketsRequest {
    side: String,
    packets_base64: Vec<String>,
    delay_ms: u64,
    final_event: String,
}

pub struct G1Manager {
    sequence: Mutex<u8>,
}

impl Default for G1Manager {
    fn default() -> Self {
        Self {
            sequence: Mutex::new(0),
        }
    }
}

impl G1Manager {
    pub fn new() -> Self {
        Self::default()
    }

    pub async fn status(&self) -> G1Status {
        match mobile_bridge() {
            Ok(handle) => handle
                .run_mobile_plugin_async("status", ())
                .await
                .unwrap_or_else(|err| unsupported_status(Some(err.to_string()))),
            Err(err) => unsupported_status(Some(err.to_string())),
        }
    }

    pub async fn scan_and_connect(
        self: &Arc<Self>,
        _app: AppHandle,
        settings: &DesktopSettings,
    ) -> Result<G1Status> {
        let status = self
            .mobile_status_command("scanAndConnect", SavedDevices::from_settings(settings))
            .await?;
        self.sync_after_mobile_connect(status, settings).await
    }

    pub async fn reconnect_saved(
        self: &Arc<Self>,
        _app: AppHandle,
        settings: &DesktopSettings,
    ) -> Result<G1Status> {
        let status = self
            .mobile_status_command("reconnectSaved", SavedDevices::from_settings(settings))
            .await?;
        self.sync_after_mobile_connect(status, settings).await
    }

    pub async fn disconnect(&self) -> Result<G1Status> {
        self.mobile_status_command("disconnect", ()).await
    }

    pub async fn send_text(&self, text: &str, streaming: bool, delay_ms: u64) -> Result<G1Status> {
        let packets = if streaming {
            vec![build_streaming_text_packet(text)]
        } else {
            build_text_packets(text)
        };
        let delay = if streaming { 0 } else { delay_ms.max(100) };
        self.write_packets(
            "both",
            packets,
            delay,
            format!("Displayed text on G1 ({} bytes)", text.len()),
        )
        .await
    }

    pub async fn clear_display(&self) -> Result<G1Status> {
        self.send_text(" ", false, 100).await
    }

    pub async fn send_notification(&self, input: G1NotificationInput) -> Result<G1Status> {
        let title = input.title.clone();
        let packets = build_notification_packets(&input)?;
        self.write_packets(
            "both",
            packets,
            50,
            format!("Forwarded G1 notification: {title}"),
        )
        .await
    }

    pub async fn send_note(&self, input: G1NoteInput) -> Result<G1Status> {
        let packet = build_note_add_packet(input.note_number, &input.name, &input.text)?;
        self.write_packets(
            "both",
            vec![packet],
            50,
            format!("Synced G1 note {}", input.note_number),
        )
        .await
    }

    pub async fn delete_note(&self, note_number: u8) -> Result<G1Status> {
        let packet = build_note_delete_packet(note_number)?;
        self.write_packets(
            "both",
            vec![packet],
            50,
            format!("Deleted G1 note {note_number}"),
        )
        .await
    }

    pub async fn send_bitmap(&self, input: G1BitmapInput) -> Result<G1Status> {
        let bitmap = BASE64
            .decode(input.data_base64.as_bytes())
            .context("decode bitmap base64")?;
        let mut sent = Vec::new();
        let mut packets = Vec::new();
        for (seq, chunk) in bitmap.chunks(194).enumerate() {
            let mut packet = build_bmp_packet(seq as u8, chunk);
            if seq == 0 {
                packet.splice(2..2, [0x00, 0x1c, 0x00, 0x00]);
            }
            sent.extend_from_slice(&packet);
            packets.push(packet);
        }
        packets.push(vec![0x20, 0x0d, 0x0e]);
        packets.push(build_crc_packet(&sent));
        self.write_packets(
            "both",
            packets,
            120,
            format!("Sent G1 bitmap ({} bytes)", bitmap.len()),
        )
        .await
    }

    pub async fn request_battery(&self) -> Result<G1Status> {
        self.write_packets(
            "both",
            vec![vec![GET_BATTERY, 0x01]],
            50,
            "Requested G1 battery status".to_string(),
        )
        .await
    }

    pub async fn set_silent_mode(&self, enabled: bool) -> Result<G1Status> {
        self.write_packets(
            "both",
            vec![vec![SILENT_MODE, if enabled { 0x0C } else { 0x0A }]],
            50,
            format!("G1 silent mode {}", if enabled { "on" } else { "off" }),
        )
        .await
    }

    pub async fn set_brightness(&self, level: u8, auto: bool) -> Result<G1Status> {
        let level = level.min(0x2A);
        self.write_packets(
            "right",
            vec![vec![BRIGHTNESS, level, if auto { 1 } else { 0 }]],
            50,
            format!("G1 brightness set to {level}"),
        )
        .await
    }

    pub async fn set_headup_angle(&self, angle: u8) -> Result<G1Status> {
        let angle = angle.min(0x3C);
        self.write_packets(
            "right",
            vec![vec![HEADUP_ANGLE, angle, 0x01]],
            50,
            format!("G1 head-up angle set to {angle}"),
        )
        .await
    }

    pub async fn set_wear_detection(&self, enabled: bool) -> Result<G1Status> {
        self.write_packets(
            "both",
            vec![vec![WEAR_DETECTION, if enabled { 1 } else { 0 }]],
            50,
            format!(
                "G1 wear detection {}",
                if enabled { "enabled" } else { "disabled" }
            ),
        )
        .await
    }

    pub async fn set_display_position(&self, input: G1DisplayPositionInput) -> Result<G1Status> {
        let height = input.height.min(8);
        let depth = input.depth.clamp(1, 9);
        let seq_preview = self.next_sequence().await;
        let seq_apply = self.next_sequence().await;
        self.write_packets(
            "right",
            vec![
                vec![
                    DISPLAY_POSITION,
                    0x08,
                    0x00,
                    seq_preview,
                    0x02,
                    0x01,
                    height,
                    depth,
                ],
                vec![
                    DISPLAY_POSITION,
                    0x08,
                    0x00,
                    seq_apply,
                    0x02,
                    0x00,
                    height,
                    depth,
                ],
            ],
            2000,
            format!("G1 display position set to height {height}, depth {depth}"),
        )
        .await
    }

    pub async fn set_microphone(&self, open: bool) -> Result<G1Status> {
        self.write_packets(
            "right",
            vec![vec![OPEN_MIC, if open { 1 } else { 0 }]],
            50,
            format!("G1 microphone {}", if open { "opened" } else { "closed" }),
        )
        .await
    }

    pub async fn start_mic_capture(&self) -> Result<G1Status> {
        self.mobile_status_command("startMicCapture", ()).await
    }

    pub async fn stop_mic_capture(&self) -> Result<G1MicCapture> {
        #[cfg(not(target_os = "android"))]
        {
            return Err(anyhow!(
                "G1 microphone capture is not available on this mobile platform"
            ));
        }

        #[cfg(target_os = "android")]
        {
            let handle = mobile_bridge()?;
            let capture: MobileMicCapture = handle
                .run_mobile_plugin_async("stopMicCapture", ())
                .await
                .context("stop Android G1 microphone capture")?;
            let lc3 = BASE64
                .decode(capture.audio_base64.as_bytes())
                .context("decode Android G1 microphone payload")?;
            let wav =
                crate::g1_lc3::decode_lc3_to_wav(&lc3).context("decode G1 LC3 microphone audio")?;
            Ok(G1MicCapture {
                audio_base64: BASE64.encode(&wav),
                mime_type: "audio/wav".to_string(),
                size_bytes: wav.len(),
                chunk_count: capture.chunk_count,
            })
        }
    }

    pub async fn sync(&self, settings: &DesktopSettings) -> Result<G1Status> {
        let time_packet = self.build_time_weather_packet(settings).await?;
        self.write_packets("both", vec![time_packet], 50, "Synced G1 time".into())
            .await?;
        self.set_dashboard_layout(&settings.g1_dashboard_layout)
            .await?;
        self.send_setup(settings).await?;
        self.set_silent_mode(!settings.g1_display_enabled).await?;
        self.set_brightness(settings.g1_brightness, settings.g1_auto_brightness)
            .await?;
        self.set_headup_angle(settings.g1_headup_angle).await?;
        self.set_wear_detection(settings.g1_wear_detection).await?;
        let hint = G1NoteInput {
            note_number: 1,
            name: "AGiXT".to_string(),
            text:
                "Touch left touchbar\nto ask AGiXT\nTouch right touchbar\nto record a conversation"
                    .to_string(),
        };
        let _ = self.send_note(hint).await;
        self.request_battery().await?;
        Ok(self
            .mobile_status_command("setLastEvent", json!({"message": "G1 dashboard synced"}))
            .await?)
    }

    async fn mobile_status_command<P: Serialize>(
        &self,
        command: &str,
        payload: P,
    ) -> Result<G1Status> {
        mobile_bridge()?
            .run_mobile_plugin_async(command, payload)
            .await
            .map_err(|err| anyhow!("{err}"))
    }

    async fn sync_after_mobile_connect(
        &self,
        status: G1Status,
        settings: &DesktopSettings,
    ) -> Result<G1Status> {
        if !status.connected {
            return Ok(status);
        }

        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        self.sync(settings).await
    }

    async fn write_packets(
        &self,
        side: &str,
        packets: Vec<Vec<u8>>,
        delay_ms: u64,
        final_event: String,
    ) -> Result<G1Status> {
        if packets.is_empty() {
            return Ok(self.status().await);
        }
        let request = WritePacketsRequest {
            side: side.to_string(),
            packets_base64: packets.iter().map(|packet| BASE64.encode(packet)).collect(),
            delay_ms,
            final_event,
        };
        self.mobile_status_command("writePackets", request).await
    }

    async fn set_dashboard_layout(&self, layout: &str) -> Result<()> {
        let option = match layout {
            "full" => [0x08, 0x06, 0x00, 0x00],
            "minimal" => [0x31, 0x06, 0x02, 0x00],
            _ => [0x1E, 0x06, 0x01, 0x00],
        };
        let mut packet = vec![0x06, 0x07, 0x00];
        packet.extend_from_slice(&option);
        self.write_packets(
            "both",
            vec![packet],
            50,
            "Updated G1 dashboard layout".into(),
        )
        .await?;
        Ok(())
    }

    async fn send_setup(&self, settings: &DesktopSettings) -> Result<()> {
        let apps = if settings.g1_notification_forwarding {
            vec![json!({"id": "systems.xt.agixt.desktop", "name": "AGiXT"})]
        } else {
            Vec::new()
        };
        let payload = json!({
            "calendar_enable": true,
            "Call_enable": true,
            "Msg_enable": settings.g1_notification_forwarding,
            "Ios_mail_enable": settings.g1_notification_forwarding,
            "app": {
                "List": apps,
                "enable": settings.g1_notification_forwarding
            }
        });
        let bytes = serde_json::to_vec(&payload).context("serialize G1 setup")?;
        self.write_packets(
            "both",
            chunk_with_header(SETUP, &bytes, 176),
            50,
            "Synced G1 setup".into(),
        )
        .await?;
        Ok(())
    }

    async fn build_time_weather_packet(&self, settings: &DesktopSettings) -> Result<Vec<u8>> {
        let now = Local::now();
        let offset_seconds = i64::from(now.offset().local_minus_utc());
        let epoch_seconds = Utc::now().timestamp() + offset_seconds;
        let epoch_millis = Utc::now().timestamp_millis() + offset_seconds * 1000;

        let (weather_icon, temperature) =
            match (settings.g1_weather_latitude, settings.g1_weather_longitude) {
                (Some(lat), Some(lon)) => fetch_weather(lat, lon)
                    .await
                    .unwrap_or_else(|_| fallback_weather(now.hour())),
                _ => fallback_weather(now.hour()),
            };
        let temp_byte = (temperature.clamp(i8::MIN as i16, i8::MAX as i16) as i8) as u8;
        let unit = if settings
            .g1_temperature_unit
            .eq_ignore_ascii_case("fahrenheit")
        {
            1
        } else {
            0
        };
        let time_format = if settings.g1_time_format.eq_ignore_ascii_case("24h") {
            0
        } else {
            1
        };
        let seq = self.next_sequence().await;

        let mut packet = vec![0u8; 21];
        packet[0] = 0x06;
        packet[1] = 21;
        packet[2] = 0x00;
        packet[3] = seq;
        packet[4] = 0x01;
        packet[5..9].copy_from_slice(&(epoch_seconds as u32).to_le_bytes());
        packet[9..17].copy_from_slice(&(epoch_millis as u64).to_le_bytes());
        packet[17] = weather_icon;
        packet[18] = temp_byte;
        packet[19] = unit;
        packet[20] = time_format;
        Ok(packet)
    }

    async fn next_sequence(&self) -> u8 {
        let mut sequence = self.sequence.lock().await;
        *sequence = sequence.wrapping_add(1);
        *sequence
    }
}

fn mobile_bridge() -> Result<&'static PluginHandle<Wry>> {
    #[cfg(target_os = "android")]
    {
        ANDROID_G1_BRIDGE
            .get()
            .ok_or_else(|| anyhow!("Even Realities G1 Android bridge is not initialized"))
    }
    #[cfg(not(target_os = "android"))]
    {
        Err(anyhow!(
            "Even Realities G1 mobile bridge is not available on this platform"
        ))
    }
}

fn unsupported_status(last_error: Option<String>) -> G1Status {
    G1Status {
        supported: false,
        scanning: false,
        connected: false,
        left: None,
        right: None,
        battery: G1BatteryStatus::default(),
        last_event: None,
        last_error: Some(last_error.unwrap_or_else(|| {
            "Even Realities G1 mobile bridge is not available on this platform".into()
        })),
    }
}

fn sanitize_glasses_text(text: &str) -> String {
    text.chars()
        .map(|ch| {
            if ch == '\n' || ch == '\r' || ch == '\t' || ch.is_ascii_graphic() || ch == ' ' {
                ch
            } else {
                '?'
            }
        })
        .collect()
}

fn format_text_lines(text: &str) -> Vec<String> {
    const MAX_LINE_LENGTH: usize = 20;
    let clean = sanitize_glasses_text(text);
    let mut lines = Vec::new();
    for raw_line in clean.lines() {
        let mut current = String::new();
        for word in raw_line.split_whitespace() {
            let next_len = if current.is_empty() {
                word.len()
            } else {
                current.len() + 1 + word.len()
            };
            if next_len <= MAX_LINE_LENGTH {
                if !current.is_empty() {
                    current.push(' ');
                }
                current.push_str(word);
            } else {
                if !current.is_empty() {
                    lines.push(std::mem::take(&mut current));
                }
                if word.len() <= MAX_LINE_LENGTH {
                    current = word.to_string();
                } else {
                    let mut start = 0;
                    while start < word.len() {
                        let end = (start + MAX_LINE_LENGTH).min(word.len());
                        lines.push(word[start..end].to_string());
                        start = end;
                    }
                    current.clear();
                }
            }
        }
        if !current.is_empty() {
            lines.push(current);
        }
    }
    if lines.is_empty() {
        lines.push(String::new());
    }
    lines
}

fn send_text_packet(text: &str, page_number: u8, max_pages: u8, screen_status: u8) -> Vec<u8> {
    let mut packet = vec![
        SEND_RESULT,
        0x00,
        0x01,
        0x00,
        screen_status,
        0x00,
        0x00,
        page_number,
        max_pages,
    ];
    packet.extend_from_slice(text.as_bytes());
    packet
}

fn centered_page_lines(lines: &[String]) -> Vec<String> {
    let mut page = lines.to_vec();
    if page.len() < 5 {
        let pad_before = (5 - page.len()) / 2;
        let pad_after = 5 - page.len() - pad_before;
        let mut centered = Vec::with_capacity(5);
        centered.extend(std::iter::repeat(String::new()).take(pad_before));
        centered.append(&mut page);
        centered.extend(std::iter::repeat(String::new()).take(pad_after));
        centered
    } else {
        page
    }
}

fn build_text_packets(text: &str) -> Vec<Vec<u8>> {
    const DISPLAYING: u8 = 0x20;
    const DISPLAY_COMPLETE: u8 = 0x40;
    const NEW_CONTENT: u8 = 0x10;

    let lines = format_text_lines(text);
    let total_pages = ((lines.len() + 4) / 5).max(1) as u8;
    let mut packets = Vec::new();
    if total_pages > 1 {
        packets.push(send_text_packet(
            &lines[0],
            1,
            total_pages,
            DISPLAYING | NEW_CONTENT,
        ));
    }

    let mut last_page_text = String::new();
    let mut page_number = 1u8;
    for page_start in (0..lines.len()).step_by(5) {
        let page_end = (page_start + 5).min(lines.len());
        let page = centered_page_lines(&lines[page_start..page_end]);
        let page_text = page.join("\n");
        last_page_text = page_text.clone();
        packets.push(send_text_packet(
            &page_text,
            page_number,
            total_pages,
            DISPLAYING | NEW_CONTENT,
        ));
        page_number = page_number.saturating_add(1);
    }

    packets.push(send_text_packet(
        &last_page_text,
        total_pages,
        total_pages,
        DISPLAY_COMPLETE,
    ));
    packets
}

fn build_streaming_text_packet(text: &str) -> Vec<u8> {
    const DISPLAYING: u8 = 0x20;
    const NEW_CONTENT: u8 = 0x10;

    let lines = format_text_lines(text);
    let total_pages = ((lines.len() + 4) / 5).max(1) as u8;
    let start = usize::from(total_pages.saturating_sub(1)) * 5;
    let end = (start + 5).min(lines.len());
    let page = centered_page_lines(&lines[start..end]);
    send_text_packet(
        &page.join("\n"),
        total_pages,
        total_pages,
        DISPLAYING | NEW_CONTENT,
    )
}

fn chunk_with_header(command: u8, payload: &[u8], max_chunk_size: usize) -> Vec<Vec<u8>> {
    let total = ((payload.len() + max_chunk_size - 1) / max_chunk_size).max(1);
    payload
        .chunks(max_chunk_size)
        .enumerate()
        .map(|(index, chunk)| {
            let mut packet = vec![command, total as u8, index as u8];
            packet.extend_from_slice(chunk);
            packet
        })
        .collect()
}

fn build_notification_packets(input: &G1NotificationInput) -> Result<Vec<Vec<u8>>> {
    let payload = json!({
        "ncs_notification": {
            "msg_id": input.msg_id.unwrap_or_else(|| Utc::now().timestamp_millis() as u64),
            "action": 0,
            "app_identifier": input.app_identifier,
            "title": sanitize_glasses_text(&input.title),
            "subtitle": sanitize_glasses_text(&input.subtitle),
            "message": sanitize_glasses_text(&input.message),
            "time_s": Utc::now().timestamp(),
            "date": Local::now().format("%Y-%m-%d %H:%M:%S").to_string(),
            "display_name": sanitize_glasses_text(&input.display_name),
        }
    });
    let bytes = serde_json::to_vec(&payload).context("serialize G1 notification")?;
    Ok(chunk_with_header(NOTIFICATION, &bytes, 177))
}

fn build_note_add_packet(note_number: u8, name: &str, text: &str) -> Result<Vec<u8>> {
    if !(1..=4).contains(&note_number) {
        return Err(anyhow!("note_number must be between 1 and 4"));
    }
    let name_bytes = sanitize_glasses_text(name).into_bytes();
    let text_bytes = sanitize_glasses_text(text).into_bytes();
    let fixed = [0x03, 0x01, 0x00, 0x01, 0x00];
    let payload_length =
        1 + 1 + fixed.len() + 1 + 1 + 1 + name_bytes.len() + 1 + 1 + text_bytes.len() + 2;
    let versioning_byte = (Utc::now().timestamp() % 256) as u8;
    let mut packet = vec![
        QUICK_NOTE_ADD,
        (payload_length & 0xFF) as u8,
        0x00,
        versioning_byte,
    ];
    packet.extend_from_slice(&fixed);
    packet.extend_from_slice(&[note_number, 0x01, name_bytes.len() as u8]);
    packet.extend_from_slice(&name_bytes);
    packet.extend_from_slice(&[text_bytes.len() as u8, 0x00]);
    packet.extend_from_slice(&text_bytes);
    Ok(packet)
}

fn build_note_delete_packet(note_number: u8) -> Result<Vec<u8>> {
    if !(1..=4).contains(&note_number) {
        return Err(anyhow!("note_number must be between 1 and 4"));
    }
    Ok(vec![
        0x1E,
        0x10,
        0x00,
        0xE0,
        0x03,
        0x01,
        0x00,
        0x01,
        0x00,
        note_number,
        0x00,
        0x01,
        0x00,
        0x01,
        0x00,
        0x00,
    ])
}

fn build_bmp_packet(seq: u8, data: &[u8]) -> Vec<u8> {
    let mut packet = vec![BMP, seq];
    packet.extend_from_slice(data);
    packet
}

fn build_crc_packet(data: &[u8]) -> Vec<u8> {
    let mut hasher = Hasher::new();
    hasher.update(data);
    let crc = hasher.finalize();
    vec![
        CRC,
        ((crc >> 24) & 0xFF) as u8,
        ((crc >> 16) & 0xFF) as u8,
        ((crc >> 8) & 0xFF) as u8,
        (crc & 0xFF) as u8,
    ]
}

async fn fetch_weather(latitude: f64, longitude: f64) -> Result<(u8, i16)> {
    #[derive(Deserialize)]
    struct WeatherResponse {
        current: WeatherCurrent,
    }
    #[derive(Deserialize)]
    struct WeatherCurrent {
        temperature_2m: f64,
        weather_code: i32,
        is_day: i32,
    }

    let url = format!(
        "https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,weather_code,is_day&timezone=auto"
    );
    let data = reqwest::get(&url)
        .await
        .context("fetch Open-Meteo weather")?
        .error_for_status()
        .context("Open-Meteo weather status")?
        .json::<WeatherResponse>()
        .await
        .context("parse Open-Meteo weather")?;
    let icon = weather_icon_id(data.current.weather_code, data.current.is_day == 1);
    Ok((icon, data.current.temperature_2m.round() as i16))
}

fn fallback_weather(hour: u32) -> (u8, i16) {
    let is_day = (6..20).contains(&hour);
    let icon = if (12..18).contains(&hour) && (hour == 14 || hour == 15) {
        0x02
    } else if is_day {
        0x10
    } else {
        0x01
    };
    let temp = if (6..12).contains(&hour) {
        18 + ((hour - 6) as i16 * 2)
    } else if (12..18).contains(&hour) {
        25
    } else if (18..22).contains(&hour) {
        22 - ((hour - 18) as i16 * 2)
    } else {
        15
    };
    (icon, temp)
}

fn weather_icon_id(code: i32, is_day: bool) -> u8 {
    match code {
        0 | 1 | 2 => {
            if is_day {
                0x10
            } else {
                0x01
            }
        }
        3 => 0x02,
        45 | 48 => 0x0B,
        51 | 53 => 0x03,
        55 => 0x04,
        56 | 57 | 66 | 67 => 0x0F,
        61 | 63 | 80 | 81 => 0x05,
        65 | 82 => 0x06,
        71 | 73 | 75 | 77 | 85 | 86 => 0x09,
        95 => 0x07,
        96 | 99 => 0x08,
        _ => {
            if is_day {
                0x10
            } else {
                0x01
            }
        }
    }
}

trait LocalHour {
    fn hour(&self) -> u32;
}

impl LocalHour for chrono::DateTime<Local> {
    fn hour(&self) -> u32 {
        use chrono::Timelike;
        Timelike::hour(self)
    }
}
