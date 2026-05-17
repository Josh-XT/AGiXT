//! Even Realities G1 glasses bridge.
//!
//! The mobile app already owns the behavior we want: Nordic UART BLE
//! pairing, heartbeat, battery parsing, dashboard/weather sync, notifications,
//! notes, text rendering, and touchpad/mic events. This module ports those
//! protocol packets into the Tauri desktop backend and keeps all hardware I/O
//! in Rust so the vanilla-JS frontend can treat the glasses like another
//! native device.

use std::collections::BTreeMap;
use std::sync::Arc;
use std::time::Duration;

use anyhow::{anyhow, Context, Result};
use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine;
use btleplug::api::{Central, Manager as _, Peripheral as _, ScanFilter, WriteType};
use btleplug::platform::{Manager, Peripheral};
use chrono::{Local, Utc};
use crc32fast::Hasher;
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use serde_json::json;
use tauri::{AppHandle, Emitter};
use tokio::sync::Mutex;
use tokio::task::JoinHandle;
use uuid::Uuid;

use crate::config::DesktopSettings;

const UART_SERVICE_UUID: &str = "6E400001-B5A3-F393-E0A9-E50E24DCCA9E";
const UART_TX_CHAR_UUID: &str = "6E400002-B5A3-F393-E0A9-E50E24DCCA9E";
const UART_RX_CHAR_UUID: &str = "6E400003-B5A3-F393-E0A9-E50E24DCCA9E";

const START_AI: u8 = 0xF5;
const OPEN_MIC: u8 = 0x0E;
const MIC_RESPONSE: u8 = 0x0E;
const RECEIVE_MIC_DATA: u8 = 0xF1;
const HEARTBEAT: u8 = 0x25;
const SEND_RESULT: u8 = 0x4E;
const QUICK_NOTE: u8 = 0x21;
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
const BUTTON_PRESS: u8 = 0x23;
const GET_BATTERY: u8 = 0x2C;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum GlassSide {
    Left,
    Right,
}

impl GlassSide {
    fn as_str(self) -> &'static str {
        match self {
            Self::Left => "left",
            Self::Right => "right",
        }
    }
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

impl G1BatteryInfo {
    fn from_response(data: &[u8], side: GlassSide) -> Option<Self> {
        if data.len() < 4 || data[0] != GET_BATTERY {
            return None;
        }
        Some(Self {
            side,
            percentage: data[2].min(100),
            voltage: data.get(3).copied().unwrap_or_default(),
            is_charging: data.get(4).map(|v| (v & 0x01) == 1).unwrap_or(false),
            timestamp: Utc::now().to_rfc3339(),
        })
    }
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

#[derive(Debug, Clone, Serialize)]
pub struct G1Event {
    #[serde(rename = "type")]
    pub event_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub side: Option<GlassSide>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub action: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub subcommand: Option<u8>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub message: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub battery: Option<G1BatteryInfo>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub status: Option<G1Status>,
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

#[derive(Debug, Serialize)]
pub struct G1MicCapture {
    pub audio_base64: String,
    pub mime_type: String,
    pub size_bytes: usize,
    pub chunk_count: usize,
}

#[derive(Clone)]
struct G1Writer {
    side: GlassSide,
    peripheral: Peripheral,
    tx: btleplug::api::Characteristic,
}

#[derive(Clone)]
struct G1Candidate {
    side: GlassSide,
    name: String,
    peripheral: Peripheral,
}

struct GlassConnection {
    side: GlassSide,
    name: String,
    id: String,
    peripheral: Peripheral,
    tx: btleplug::api::Characteristic,
    notify_task: Option<JoinHandle<()>>,
    heartbeat_task: Option<JoinHandle<()>>,
    connected: bool,
}

impl GlassConnection {
    fn summary(&self) -> G1DeviceSummary {
        G1DeviceSummary {
            side: self.side,
            name: self.name.clone(),
            id: self.id.clone(),
            connected: self.connected,
        }
    }

    fn writer(&self) -> G1Writer {
        G1Writer {
            side: self.side,
            peripheral: self.peripheral.clone(),
            tx: self.tx.clone(),
        }
    }

    fn abort_tasks(&mut self) {
        if let Some(task) = self.notify_task.take() {
            task.abort();
        }
        if let Some(task) = self.heartbeat_task.take() {
            task.abort();
        }
    }
}

#[derive(Default)]
struct VoiceCollector {
    recording: bool,
    chunks: BTreeMap<u32, Vec<u8>>,
    seq_add: u32,
}

impl VoiceCollector {
    fn reset(&mut self) {
        self.chunks.clear();
        self.seq_add = 0;
    }

    fn add_chunk(&mut self, seq: u8, data: &[u8]) {
        if seq == 255 {
            self.seq_add = self.seq_add.saturating_add(255);
        }
        self.chunks
            .insert(self.seq_add + u32::from(seq), data.to_vec());
    }

    fn take(&mut self) -> (Vec<u8>, usize) {
        let count = self.chunks.len();
        let mut data = Vec::new();
        for chunk in self.chunks.values() {
            data.extend_from_slice(chunk);
        }
        self.reset();
        (data, count)
    }
}

#[derive(Default)]
struct G1Runtime {
    scanning: bool,
    left: Option<GlassConnection>,
    right: Option<GlassConnection>,
    battery: G1BatteryStatus,
    sequence: u8,
    last_event: Option<String>,
    last_error: Option<String>,
    voice: VoiceCollector,
}

impl G1Runtime {
    fn status(&self) -> G1Status {
        let left = self.left.as_ref().map(GlassConnection::summary);
        let right = self.right.as_ref().map(GlassConnection::summary);
        G1Status {
            supported: true,
            scanning: self.scanning,
            connected: left.as_ref().map(|d| d.connected).unwrap_or(false)
                && right.as_ref().map(|d| d.connected).unwrap_or(false),
            left,
            right,
            battery: self.battery.clone(),
            last_event: self.last_event.clone(),
            last_error: self.last_error.clone(),
        }
    }
}

pub struct G1Manager {
    runtime: Mutex<G1Runtime>,
}

impl Default for G1Manager {
    fn default() -> Self {
        Self {
            runtime: Mutex::new(G1Runtime::default()),
        }
    }
}

#[cfg(target_os = "linux")]
async fn connect_g1_peripheral(peripheral: &Peripheral, id: &str, side: GlassSide) -> Result<bool> {
    for attempt in 1..=3 {
        if peripheral.is_connected().await.unwrap_or(false) {
            return Ok(true);
        }

        match tokio::time::timeout(
            Duration::from_secs(28),
            linux_bluez_connect_and_wait(id, side),
        )
        .await
        {
            Ok(Ok(())) => return Ok(true),
            Ok(Err(bluez_err)) => {
                let detail = format!("{bluez_err:#}");
                tracing::warn!(
                    "G1 {} BlueZ connect attempt {attempt}/3 failed: {detail}",
                    side.as_str()
                );

                if bluez_device_object_is_stale(&detail) || bluez_device_pairing_failed(&detail) {
                    return Err(anyhow!("{detail}"));
                }
                if attempt == 3 {
                    return Err(anyhow!("connect attempt {attempt}/3 failed: {detail}"));
                }

                let _ = peripheral.disconnect().await;
                tokio::time::sleep(Duration::from_secs(1)).await;
            }
            Err(_) => {
                tracing::warn!(
                    "G1 {} BlueZ connect attempt {attempt}/3 timed out",
                    side.as_str()
                );
                if attempt == 3 {
                    return Err(anyhow!("connect attempt {attempt}/3 timed out"));
                }
                let _ = peripheral.disconnect().await;
                tokio::time::sleep(Duration::from_secs(1)).await;
            }
        }
    }

    Ok(false)
}

#[cfg(target_os = "linux")]
fn bluez_device_object_is_stale(message: &str) -> bool {
    message.contains("doesn't exist")
        || message.contains("UnknownObject")
        || message.contains("No such object")
        || message.contains("object disappeared")
}

#[cfg(target_os = "linux")]
fn bluez_device_pairing_failed(message: &str) -> bool {
    message.contains("BlueZ Pair failed")
        || message.contains("AuthenticationFailed")
        || message.contains("AuthenticationCanceled")
}

#[cfg(not(target_os = "linux"))]
async fn connect_g1_peripheral(
    peripheral: &Peripheral,
    _id: &str,
    side: GlassSide,
) -> Result<bool> {
    for attempt in 1..=3 {
        match peripheral.is_connected().await {
            Ok(true) => return Ok(true),
            _ => {
                if let Err(err) = peripheral.connect().await {
                    tokio::time::sleep(Duration::from_millis(150)).await;
                    if peripheral.is_connected().await.unwrap_or(false) {
                        tracing::warn!(
                            "G1 {} connect attempt {attempt}/3 returned {err:#}, but the link is up; continuing",
                            side.as_str()
                        );
                        return Ok(true);
                    }
                    if attempt == 3 {
                        return Err(anyhow!("connect attempt {attempt}/3 failed: {err:#}"));
                    }
                    tokio::time::sleep(Duration::from_secs(1)).await;
                } else {
                    return Ok(true);
                }
            }
        }
    }
    Ok(false)
}

#[cfg(target_os = "linux")]
fn bluez_object_path(device_id: &str) -> Result<String> {
    let device_id = device_id.trim();
    if device_id.starts_with("/org/bluez/") {
        return Ok(device_id.to_string());
    }
    if device_id.starts_with("hci") && device_id.contains("/dev_") {
        return Ok(format!("/org/bluez/{device_id}"));
    }
    if device_id.contains(':') {
        return Ok(format!(
            "/org/bluez/hci0/dev_{}",
            device_id.replace(':', "_")
        ));
    }
    Err(anyhow!("unsupported BlueZ G1 device id '{device_id}'"))
}

#[cfg(target_os = "linux")]
async fn linux_bluez_connect_and_wait(device_id: &str, side: GlassSide) -> Result<()> {
    use dbus::nonblock::stdintf::org_freedesktop_dbus::Properties;

    let object_path = bluez_object_path(device_id)?;
    let path = dbus::Path::new(object_path.clone())
        .map_err(|err| anyhow!("invalid BlueZ object path {object_path}: {err}"))?;
    let (resource, conn) =
        dbus_tokio::connection::new_system_sync().context("connect to system D-Bus")?;

    struct ResourceTask(JoinHandle<()>);
    impl Drop for ResourceTask {
        fn drop(&mut self) {
            self.0.abort();
        }
    }
    let _resource_task = ResourceTask(tokio::spawn(async move {
        let err = resource.await;
        tracing::debug!("BlueZ D-Bus connection ended: {err}");
    }));

    let proxy =
        dbus::nonblock::Proxy::new("org.bluez", path, Duration::from_secs(30), conn.clone());

    let paired: bool = proxy
        .get("org.bluez.Device1", "Paired")
        .await
        .unwrap_or(false);
    if !paired {
        tracing::debug!(
            "BlueZ pairing {} glass at {object_path} before GATT connect",
            side.as_str()
        );
        let pair_result = tokio::time::timeout(Duration::from_secs(25), async {
            let result: std::result::Result<(), dbus::Error> =
                proxy.method_call("org.bluez.Device1", "Pair", ()).await;
            result
        })
        .await;
        match pair_result {
            Ok(Ok(())) => {
                let _: std::result::Result<(), dbus::Error> =
                    proxy.set("org.bluez.Device1", "Trusted", true).await;
                tokio::time::sleep(Duration::from_millis(300)).await;
            }
            Ok(Err(err)) => {
                return Err(anyhow!(
                    "BlueZ Pair failed for {} glass at {object_path}: {err}. Unpair G1 in the Even app, forget both G1 devices in phone Bluetooth settings, quick-restart the glasses, then try Connect again.",
                    side.as_str()
                ));
            }
            Err(_) => {
                return Err(anyhow!(
                    "BlueZ Pair timed out for {} glass at {object_path}. Unpair G1 in the Even app, forget both G1 devices in phone Bluetooth settings, quick-restart the glasses, then try Connect again.",
                    side.as_str()
                ));
            }
        }
    }

    let mut connected: bool = proxy
        .get("org.bluez.Device1", "Connected")
        .await
        .unwrap_or(false);
    if !connected {
        let connect_result: std::result::Result<(), dbus::Error> =
            proxy.method_call("org.bluez.Device1", "Connect", ()).await;
        if let Err(err) = connect_result {
            tokio::time::sleep(Duration::from_millis(250)).await;
            connected = proxy
                .get("org.bluez.Device1", "Connected")
                .await
                .unwrap_or(false);
            if !connected {
                let detail = err.to_string();
                if bluez_device_object_is_stale(&detail) {
                    return Err(anyhow!(
                        "BlueZ device object disappeared for {} glass at {object_path}; rescan needed: {detail}",
                        side.as_str()
                    ));
                }
                return Err(anyhow!(
                    "BlueZ Connect failed for {} glass at {object_path}: {err}",
                    side.as_str()
                ));
            }
            tracing::warn!(
                "BlueZ Connect for {} returned {err}, but the link is up; waiting for GATT services",
                side.as_str()
            );
        }
    }

    let deadline = tokio::time::Instant::now() + Duration::from_secs(20);
    loop {
        let services_resolved: bool = proxy
            .get("org.bluez.Device1", "ServicesResolved")
            .await
            .unwrap_or(false);
        if services_resolved {
            tracing::debug!(
                "BlueZ services resolved for {} glass at {object_path}",
                side.as_str()
            );
            return Ok(());
        }

        connected = proxy
            .get("org.bluez.Device1", "Connected")
            .await
            .unwrap_or(false);
        if !connected {
            return Err(anyhow!(
                "BlueZ link dropped before GATT services resolved for {} glass at {object_path}",
                side.as_str()
            ));
        }

        if tokio::time::Instant::now() >= deadline {
            return Err(anyhow!(
                "BlueZ GATT services did not resolve within 20s for {} glass at {object_path}",
                side.as_str()
            ));
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    }
}

impl G1Manager {
    pub fn new() -> Self {
        Self::default()
    }

    pub async fn status(&self) -> G1Status {
        self.runtime.lock().await.status()
    }

    pub async fn scan_and_connect(
        self: &Arc<Self>,
        app: AppHandle,
        settings: &DesktopSettings,
    ) -> Result<G1Status> {
        self.disconnect().await?;
        {
            let mut rt = self.runtime.lock().await;
            rt.scanning = true;
            rt.last_event = Some("Scanning for Even Realities G1 glasses".to_string());
            rt.last_error = None;
        }
        self.emit_status(&app).await;

        let manager = Manager::new()
            .await
            .context("initialize Bluetooth manager")?;
        let adapters = manager
            .adapters()
            .await
            .context("list Bluetooth adapters")?;
        let adapter = adapters
            .into_iter()
            .next()
            .ok_or_else(|| anyhow!("No Bluetooth adapter is available"))?;

        adapter
            .start_scan(ScanFilter::default())
            .await
            .context("start G1 BLE scan")?;

        let mut left: Option<GlassConnection> = None;
        let mut right: Option<GlassConnection> = None;
        let mut left_candidate: Option<G1Candidate> = None;
        let mut right_candidate: Option<G1Candidate> = None;
        let mut errors = Vec::new();
        let scan_deadline = tokio::time::Instant::now() + Duration::from_secs(30);
        while tokio::time::Instant::now() < scan_deadline
            && (left_candidate.is_none() || right_candidate.is_none())
        {
            tokio::time::sleep(Duration::from_millis(900)).await;
            let peripherals = adapter.peripherals().await.context("read scan results")?;
            for peripheral in peripherals {
                let props = match peripheral.properties().await {
                    Ok(Some(props)) => props,
                    _ => continue,
                };
                let name = props.local_name.unwrap_or_default();
                if name.is_empty() {
                    continue;
                }
                let side = if name.contains("_L_") {
                    GlassSide::Left
                } else if name.contains("_R_") {
                    GlassSide::Right
                } else {
                    continue;
                };
                if (side == GlassSide::Left && left_candidate.is_some())
                    || (side == GlassSide::Right && right_candidate.is_some())
                {
                    continue;
                }
                tracing::info!("G1 found {} candidate: {name}", side.as_str());
                let candidate = G1Candidate {
                    side,
                    name: name.clone(),
                    peripheral: peripheral.clone(),
                };
                if side == GlassSide::Left {
                    left_candidate = Some(candidate);
                } else {
                    right_candidate = Some(candidate);
                }
                {
                    let mut rt = self.runtime.lock().await;
                    rt.last_event = Some(format!("Found {} G1 glass: {name}", side.as_str()));
                }
                self.emit_status(&app).await;
            }
        }

        let _ = adapter.stop_scan().await;
        tokio::time::sleep(Duration::from_millis(500)).await;

        if left_candidate.is_some() || right_candidate.is_some() {
            {
                let mut rt = self.runtime.lock().await;
                rt.last_event = Some("Connecting to discovered G1 glasses".to_string());
            }
            self.emit_status(&app).await;
        }
        if let Some(candidate) = left_candidate.take() {
            self.connect_collected_candidate(
                app.clone(),
                candidate,
                &mut left,
                &mut right,
                &mut errors,
            )
            .await;
        }
        if let Some(candidate) = right_candidate.take() {
            self.connect_collected_candidate(
                app.clone(),
                candidate,
                &mut left,
                &mut right,
                &mut errors,
            )
            .await;
        }

        {
            let mut rt = self.runtime.lock().await;
            rt.scanning = false;
            rt.left = left;
            rt.right = right;
            rt.last_error = if errors.is_empty() {
                None
            } else {
                Some(errors.join("; "))
            };
            rt.last_event = Some(if rt.left.is_some() && rt.right.is_some() {
                "G1 glasses connected".to_string()
            } else if rt.left.is_none() && rt.right.is_none() && rt.last_error.is_none() {
                "No G1 glasses found".to_string()
            } else {
                "G1 connection completed with missing glasses".to_string()
            });
        }
        self.emit_status(&app).await;

        let status = self.status().await;
        if status.connected {
            self.sync(settings).await?;
        }
        Ok(status)
    }

    pub async fn reconnect_saved(
        self: &Arc<Self>,
        app: AppHandle,
        settings: &DesktopSettings,
    ) -> Result<G1Status> {
        if settings.g1_left_device_id.is_none() && settings.g1_right_device_id.is_none() {
            return self.scan_and_connect(app, settings).await;
        }

        self.disconnect().await?;
        {
            let mut rt = self.runtime.lock().await;
            rt.scanning = true;
            rt.last_event = Some("Looking for saved G1 glasses".to_string());
            rt.last_error = None;
        }
        self.emit_status(&app).await;

        let manager = Manager::new()
            .await
            .context("initialize Bluetooth manager")?;
        let adapters = manager
            .adapters()
            .await
            .context("list Bluetooth adapters")?;
        let adapter = adapters
            .into_iter()
            .next()
            .ok_or_else(|| anyhow!("No Bluetooth adapter is available"))?;
        adapter
            .start_scan(ScanFilter::default())
            .await
            .context("start G1 BLE reconnect scan")?;

        let mut left: Option<GlassConnection> = None;
        let mut right: Option<GlassConnection> = None;
        let mut left_candidate: Option<G1Candidate> = None;
        let mut right_candidate: Option<G1Candidate> = None;
        let mut errors = Vec::new();
        let scan_deadline = tokio::time::Instant::now() + Duration::from_secs(20);
        while tokio::time::Instant::now() < scan_deadline
            && (left_candidate.is_none() || right_candidate.is_none())
        {
            tokio::time::sleep(Duration::from_millis(900)).await;
            for peripheral in adapter.peripherals().await.context("read scan results")? {
                let id = peripheral.id().to_string();
                let props = match peripheral.properties().await {
                    Ok(Some(props)) => props,
                    _ => continue,
                };
                let name = props.local_name.unwrap_or_default();
                let matches_left = settings
                    .g1_left_device_id
                    .as_deref()
                    .map(|saved| saved == id)
                    .unwrap_or(false)
                    || settings
                        .g1_left_device_name
                        .as_deref()
                        .map(|saved| !saved.is_empty() && saved == name)
                        .unwrap_or(false);
                let matches_right = settings
                    .g1_right_device_id
                    .as_deref()
                    .map(|saved| saved == id)
                    .unwrap_or(false)
                    || settings
                        .g1_right_device_name
                        .as_deref()
                        .map(|saved| !saved.is_empty() && saved == name)
                        .unwrap_or(false);
                let side = if matches_left {
                    GlassSide::Left
                } else if matches_right {
                    GlassSide::Right
                } else {
                    continue;
                };
                if (side == GlassSide::Left && left_candidate.is_some())
                    || (side == GlassSide::Right && right_candidate.is_some())
                {
                    continue;
                }
                tracing::info!("G1 found saved {} candidate: {name}", side.as_str());
                let candidate = G1Candidate {
                    side,
                    name: name.clone(),
                    peripheral: peripheral.clone(),
                };
                if side == GlassSide::Left {
                    left_candidate = Some(candidate);
                } else {
                    right_candidate = Some(candidate);
                }
                {
                    let mut rt = self.runtime.lock().await;
                    rt.last_event = Some(format!("Found saved {} G1 glass: {name}", side.as_str()));
                }
                self.emit_status(&app).await;
            }
        }

        let _ = adapter.stop_scan().await;
        tokio::time::sleep(Duration::from_millis(500)).await;

        if left_candidate.is_some() || right_candidate.is_some() {
            {
                let mut rt = self.runtime.lock().await;
                rt.last_event = Some("Connecting to saved G1 glasses".to_string());
            }
            self.emit_status(&app).await;
        }
        if let Some(candidate) = left_candidate.take() {
            self.connect_collected_candidate(
                app.clone(),
                candidate,
                &mut left,
                &mut right,
                &mut errors,
            )
            .await;
        }
        if let Some(candidate) = right_candidate.take() {
            self.connect_collected_candidate(
                app.clone(),
                candidate,
                &mut left,
                &mut right,
                &mut errors,
            )
            .await;
        }

        {
            let mut rt = self.runtime.lock().await;
            rt.scanning = false;
            rt.left = left;
            rt.right = right;
            rt.last_error = if errors.is_empty() {
                None
            } else {
                Some(errors.join("; "))
            };
            rt.last_event = Some("Saved G1 reconnect completed".to_string());
        }
        self.emit_status(&app).await;
        let status = self.status().await;
        if status.connected {
            self.sync(settings).await?;
        }
        Ok(status)
    }

    async fn connect_collected_candidate(
        self: &Arc<Self>,
        app: AppHandle,
        candidate: G1Candidate,
        left: &mut Option<GlassConnection>,
        right: &mut Option<GlassConnection>,
        errors: &mut Vec<String>,
    ) {
        let side = candidate.side;
        tracing::info!(
            "G1 connecting {} candidate: {} ({})",
            side.as_str(),
            candidate.name,
            candidate.peripheral.id()
        );
        {
            let mut rt = self.runtime.lock().await;
            rt.last_event = Some(format!(
                "Connecting {} G1 glass: {}",
                side.as_str(),
                candidate.name
            ));
        }
        self.emit_status(&app).await;

        match self
            .connect_peripheral(app, candidate.peripheral, candidate.name, side)
            .await
        {
            Ok(conn) if side == GlassSide::Left => *left = Some(conn),
            Ok(conn) => *right = Some(conn),
            Err(err) => {
                tracing::warn!("G1 connect {} failed: {err:#}", side.as_str());
                errors.push(format!("{} glass: {err:#}", side.as_str()));
            }
        }
    }

    async fn connect_peripheral(
        self: &Arc<Self>,
        app: AppHandle,
        peripheral: Peripheral,
        name: String,
        side: GlassSide,
    ) -> Result<GlassConnection> {
        let id = peripheral.id().to_string();
        let connected = connect_g1_peripheral(&peripheral, &id, side).await?;
        if !connected && !peripheral.is_connected().await.unwrap_or(false) {
            return Err(anyhow!("G1 {} glass did not connect", side.as_str()));
        }

        peripheral
            .discover_services()
            .await
            .context("discover G1 UART service")?;
        let uart_service = Uuid::parse_str(UART_SERVICE_UUID).expect("valid UART service UUID");
        let tx_uuid = Uuid::parse_str(UART_TX_CHAR_UUID).expect("valid UART TX UUID");
        let rx_uuid = Uuid::parse_str(UART_RX_CHAR_UUID).expect("valid UART RX UUID");
        let chars = peripheral.characteristics();
        let tx = chars
            .iter()
            .find(|c| c.service_uuid == uart_service && c.uuid == tx_uuid)
            .cloned()
            .ok_or_else(|| anyhow!("G1 UART TX characteristic not found"))?;
        let rx = chars
            .iter()
            .find(|c| c.service_uuid == uart_service && c.uuid == rx_uuid)
            .cloned()
            .ok_or_else(|| anyhow!("G1 UART RX characteristic not found"))?;

        peripheral
            .subscribe(&rx)
            .await
            .context("subscribe to G1 UART RX notifications")?;

        let notify_peripheral = peripheral.clone();
        let notify_manager = self.clone();
        let notify_app = app.clone();
        let notify_task = tokio::spawn(async move {
            match notify_peripheral.notifications().await {
                Ok(mut notifications) => {
                    while let Some(notification) = notifications.next().await {
                        if notification.uuid == rx_uuid {
                            notify_manager
                                .handle_notification(&notify_app, side, notification.value)
                                .await;
                        }
                    }
                }
                Err(err) => {
                    tracing::warn!(
                        "G1 notifications unavailable for {}: {err:#}",
                        side.as_str()
                    );
                }
            }
            notify_manager.mark_disconnected(&notify_app, side).await;
        });

        let heartbeat_peripheral = peripheral.clone();
        let heartbeat_tx = tx.clone();
        let heartbeat_task = tokio::spawn(async move {
            let mut seq = 0u8;
            loop {
                let packet = build_heartbeat(seq);
                seq = seq.wrapping_add(1);
                match heartbeat_peripheral
                    .write(&heartbeat_tx, &packet, WriteType::WithResponse)
                    .await
                {
                    Ok(_) => {}
                    Err(err) => {
                        tracing::warn!("G1 heartbeat failed for {}: {err:#}", side.as_str());
                        break;
                    }
                }
                tokio::time::sleep(Duration::from_secs(5)).await;
            }
        });

        Ok(GlassConnection {
            side,
            name,
            id,
            peripheral,
            tx,
            notify_task: Some(notify_task),
            heartbeat_task: Some(heartbeat_task),
            connected: true,
        })
    }

    pub async fn disconnect(&self) -> Result<G1Status> {
        let (mut left, mut right) = {
            let mut rt = self.runtime.lock().await;
            rt.scanning = false;
            rt.battery = G1BatteryStatus::default();
            rt.last_event = Some("Disconnecting G1 glasses".to_string());
            (rt.left.take(), rt.right.take())
        };

        for conn in [&mut left, &mut right].into_iter().flatten() {
            conn.abort_tasks();
            let _ = conn.peripheral.disconnect().await;
            conn.connected = false;
        }

        let mut rt = self.runtime.lock().await;
        rt.last_event = Some("G1 glasses disconnected".to_string());
        Ok(rt.status())
    }

    pub async fn send_text(&self, text: &str, streaming: bool, delay_ms: u64) -> Result<G1Status> {
        let packets = if streaming {
            vec![build_streaming_text_packet(text)]
        } else {
            build_text_packets(text)
        };
        for (index, packet) in packets.iter().enumerate() {
            self.send_to_both(packet).await?;
            if !streaming && index + 1 < packets.len() {
                let delay = if index < 2 { 300 } else { delay_ms.max(100) };
                tokio::time::sleep(Duration::from_millis(delay)).await;
            }
        }
        self.set_last_event(format!("Displayed text on G1 ({} bytes)", text.len()))
            .await;
        Ok(self.status().await)
    }

    pub async fn clear_display(&self) -> Result<G1Status> {
        self.send_text(" ", false, 100).await
    }

    pub async fn send_notification(&self, input: G1NotificationInput) -> Result<G1Status> {
        let chunks = build_notification_packets(&input)?;
        for chunk in chunks {
            self.send_to_both(&chunk).await?;
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
        self.set_last_event(format!("Forwarded G1 notification: {}", input.title))
            .await;
        Ok(self.status().await)
    }

    pub async fn send_note(&self, input: G1NoteInput) -> Result<G1Status> {
        let packet = build_note_add_packet(input.note_number, &input.name, &input.text)?;
        self.send_to_both(&packet).await?;
        self.set_last_event(format!("Synced G1 note {}", input.note_number))
            .await;
        Ok(self.status().await)
    }

    pub async fn delete_note(&self, note_number: u8) -> Result<G1Status> {
        let packet = build_note_delete_packet(note_number)?;
        self.send_to_both(&packet).await?;
        self.set_last_event(format!("Deleted G1 note {note_number}"))
            .await;
        Ok(self.status().await)
    }

    pub async fn send_bitmap(&self, input: G1BitmapInput) -> Result<G1Status> {
        let bitmap = BASE64
            .decode(input.data_base64.as_bytes())
            .context("decode bitmap base64")?;
        let mut sent = Vec::new();
        for (seq, chunk) in bitmap.chunks(194).enumerate() {
            let mut packet = build_bmp_packet(seq as u8, chunk);
            if seq == 0 {
                packet.splice(2..2, [0x00, 0x1c, 0x00, 0x00]);
            }
            sent.extend_from_slice(&packet);
            self.send_to_both(&packet).await?;
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        self.send_to_both(&[0x20, 0x0d, 0x0e]).await?;
        tokio::time::sleep(Duration::from_millis(500)).await;
        let crc_packet = build_crc_packet(&sent);
        self.send_to_both(&crc_packet).await?;
        self.set_last_event(format!("Sent G1 bitmap ({} bytes)", bitmap.len()))
            .await;
        Ok(self.status().await)
    }

    pub async fn request_battery(&self) -> Result<G1Status> {
        self.send_to_both(&[GET_BATTERY, 0x01]).await?;
        self.set_last_event("Requested G1 battery status".to_string())
            .await;
        Ok(self.status().await)
    }

    pub async fn set_silent_mode(&self, enabled: bool) -> Result<G1Status> {
        self.send_to_both(&[SILENT_MODE, if enabled { 0x0C } else { 0x0A }])
            .await?;
        self.set_last_event(format!(
            "G1 silent mode {}",
            if enabled { "on" } else { "off" }
        ))
        .await;
        Ok(self.status().await)
    }

    pub async fn set_brightness(&self, level: u8, auto: bool) -> Result<G1Status> {
        let level = level.min(0x2A);
        self.send_to_side(
            GlassSide::Right,
            &[BRIGHTNESS, level, if auto { 1 } else { 0 }],
        )
        .await?;
        self.set_last_event(format!("G1 brightness set to {level}"))
            .await;
        Ok(self.status().await)
    }

    pub async fn set_headup_angle(&self, angle: u8) -> Result<G1Status> {
        self.send_to_side(GlassSide::Right, &[HEADUP_ANGLE, angle.min(0x3C), 0x01])
            .await?;
        self.set_last_event(format!("G1 head-up angle set to {}", angle.min(0x3C)))
            .await;
        Ok(self.status().await)
    }

    pub async fn set_wear_detection(&self, enabled: bool) -> Result<G1Status> {
        self.send_to_both(&[WEAR_DETECTION, if enabled { 1 } else { 0 }])
            .await?;
        self.set_last_event(format!(
            "G1 wear detection {}",
            if enabled { "enabled" } else { "disabled" }
        ))
        .await;
        Ok(self.status().await)
    }

    pub async fn set_display_position(&self, input: G1DisplayPositionInput) -> Result<G1Status> {
        let height = input.height.min(8);
        let depth = input.depth.clamp(1, 9);
        let seq_preview = self.next_sequence().await;
        self.send_to_side(
            GlassSide::Right,
            &[
                DISPLAY_POSITION,
                0x08,
                0x00,
                seq_preview,
                0x02,
                0x01,
                height,
                depth,
            ],
        )
        .await?;
        tokio::time::sleep(Duration::from_secs(2)).await;
        let seq_apply = self.next_sequence().await;
        self.send_to_side(
            GlassSide::Right,
            &[
                DISPLAY_POSITION,
                0x08,
                0x00,
                seq_apply,
                0x02,
                0x00,
                height,
                depth,
            ],
        )
        .await?;
        self.set_last_event(format!(
            "G1 display position set to height {height}, depth {depth}"
        ))
        .await;
        Ok(self.status().await)
    }

    pub async fn set_microphone(&self, open: bool) -> Result<G1Status> {
        self.send_to_side(GlassSide::Right, &[OPEN_MIC, if open { 1 } else { 0 }])
            .await?;
        self.set_last_event(format!(
            "G1 microphone {}",
            if open { "opened" } else { "closed" }
        ))
        .await;
        Ok(self.status().await)
    }

    pub async fn start_mic_capture(&self) -> Result<G1Status> {
        {
            let mut rt = self.runtime.lock().await;
            rt.voice.reset();
            rt.voice.recording = true;
        }
        self.set_microphone(true).await
    }

    pub async fn stop_mic_capture(&self) -> Result<G1MicCapture> {
        let _ = self.set_microphone(false).await;
        let (data, chunk_count) = {
            let mut rt = self.runtime.lock().await;
            rt.voice.recording = false;
            rt.voice.take()
        };
        let wav =
            crate::g1_lc3::decode_lc3_to_wav(&data).context("decode G1 LC3 microphone audio")?;
        Ok(G1MicCapture {
            audio_base64: BASE64.encode(&wav),
            mime_type: "audio/wav".to_string(),
            size_bytes: wav.len(),
            chunk_count,
        })
    }

    pub async fn sync(&self, settings: &DesktopSettings) -> Result<G1Status> {
        let time_packet = self.build_time_weather_packet(settings).await?;
        self.send_to_both(&time_packet).await?;
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
        self.set_last_event("G1 dashboard synced".to_string()).await;
        Ok(self.status().await)
    }

    async fn set_dashboard_layout(&self, layout: &str) -> Result<()> {
        let option = match layout {
            "full" => [0x08, 0x06, 0x00, 0x00],
            "minimal" => [0x31, 0x06, 0x02, 0x00],
            _ => [0x1E, 0x06, 0x01, 0x00],
        };
        let mut packet = vec![0x06, 0x07, 0x00];
        packet.extend_from_slice(&option);
        self.send_to_both(&packet).await
    }

    async fn send_setup(&self, settings: &DesktopSettings) -> Result<()> {
        let apps = if settings.g1_notification_forwarding {
            vec![json!({"id": "systems.xt.agixt.desktop", "name": "AGiXT Desktop"})]
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
        for chunk in chunk_with_header(SETUP, &bytes, 176) {
            self.send_to_both(&chunk).await?;
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
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

    async fn handle_notification(&self, app: &AppHandle, side: GlassSide, data: Vec<u8>) {
        if data.is_empty() {
            return;
        }
        let command = data[0];
        match command {
            BUTTON_PRESS => {
                self.emit_event(
                    app,
                    G1Event {
                        event_type: "button".to_string(),
                        side: Some(side),
                        action: Some("button_press".to_string()),
                        subcommand: None,
                        message: Some("G1 side button pressed".to_string()),
                        battery: None,
                        status: None,
                    },
                );
            }
            GET_BATTERY => {
                if let Some(battery) = G1BatteryInfo::from_response(&data, side) {
                    {
                        let mut rt = self.runtime.lock().await;
                        match side {
                            GlassSide::Left => rt.battery.left = Some(battery.clone()),
                            GlassSide::Right => rt.battery.right = Some(battery.clone()),
                        }
                        rt.battery.last_updated = Some(Utc::now().to_rfc3339());
                        rt.last_event = Some(format!(
                            "{} G1 battery: {}%",
                            side.as_str(),
                            battery.percentage
                        ));
                    }
                    self.emit_event(
                        app,
                        G1Event {
                            event_type: "battery".to_string(),
                            side: Some(side),
                            action: None,
                            subcommand: None,
                            message: None,
                            battery: Some(battery),
                            status: Some(self.status().await),
                        },
                    );
                }
            }
            START_AI => {
                let subcommand = data.get(1).copied();
                let action = match (side, subcommand) {
                    (_, Some(0x00)) => {
                        let _ = self.set_microphone(false).await;
                        "exit_dashboard"
                    }
                    (GlassSide::Left, Some(0x17)) => "voice_start",
                    (GlassSide::Left, Some(0x18)) => "voice_stop",
                    (GlassSide::Right, Some(0x17)) => "conversation_toggle",
                    (GlassSide::Right, Some(0x18)) => "conversation_release",
                    (GlassSide::Left, Some(0x01)) => "page_up",
                    (GlassSide::Right, Some(0x01)) => "page_down",
                    _ => "state_change",
                };
                self.emit_event(
                    app,
                    G1Event {
                        event_type: "button".to_string(),
                        side: Some(side),
                        action: Some(action.to_string()),
                        subcommand,
                        message: Some(format!("G1 {} event {subcommand:?}", side.as_str())),
                        battery: None,
                        status: None,
                    },
                );
            }
            MIC_RESPONSE => {
                self.emit_event(
                    app,
                    G1Event {
                        event_type: "microphone".to_string(),
                        side: Some(side),
                        action: Some(
                            if data.get(2).copied() == Some(1) {
                                "opened"
                            } else {
                                "closed"
                            }
                            .to_string(),
                        ),
                        subcommand: data.get(1).copied(),
                        message: None,
                        battery: None,
                        status: None,
                    },
                );
            }
            RECEIVE_MIC_DATA => {
                if data.len() >= 2 {
                    let seq = data[1];
                    let mut rt = self.runtime.lock().await;
                    if rt.voice.recording {
                        rt.voice.add_chunk(seq, &data[2..]);
                    }
                }
            }
            QUICK_NOTE => {
                self.emit_event(
                    app,
                    G1Event {
                        event_type: "quick_note".to_string(),
                        side: Some(side),
                        action: Some("ignored".to_string()),
                        subcommand: data.get(4).copied(),
                        message: Some("G1 quick note event received".to_string()),
                        battery: None,
                        status: None,
                    },
                );
            }
            QUICK_NOTE_ADD => {
                self.emit_event(
                    app,
                    G1Event {
                        event_type: "quick_note_audio".to_string(),
                        side: Some(side),
                        action: Some("received".to_string()),
                        subcommand: data.get(4).copied(),
                        message: Some("G1 quick note audio data received".to_string()),
                        battery: None,
                        status: None,
                    },
                );
            }
            HEARTBEAT => {}
            other => {
                tracing::debug!("G1 {} unknown packet 0x{other:02x}", side.as_str());
            }
        }
    }

    async fn mark_disconnected(&self, app: &AppHandle, side: GlassSide) {
        {
            let mut rt = self.runtime.lock().await;
            match side {
                GlassSide::Left => {
                    if let Some(conn) = rt.left.as_mut() {
                        conn.connected = false;
                    }
                }
                GlassSide::Right => {
                    if let Some(conn) = rt.right.as_mut() {
                        conn.connected = false;
                    }
                }
            }
            rt.last_event = Some(format!("{} G1 disconnected", side.as_str()));
        }
        self.emit_status(app).await;
    }

    async fn next_sequence(&self) -> u8 {
        let mut rt = self.runtime.lock().await;
        rt.sequence = rt.sequence.wrapping_add(1);
        rt.sequence
    }

    async fn writers(&self, side: Option<GlassSide>) -> Vec<G1Writer> {
        let rt = self.runtime.lock().await;
        let mut writers = Vec::new();
        if side.map(|s| s == GlassSide::Left).unwrap_or(true) {
            if let Some(conn) = rt.left.as_ref().filter(|conn| conn.connected) {
                writers.push(conn.writer());
            }
        }
        if side.map(|s| s == GlassSide::Right).unwrap_or(true) {
            if let Some(conn) = rt.right.as_ref().filter(|conn| conn.connected) {
                writers.push(conn.writer());
            }
        }
        writers
    }

    async fn send_to_both(&self, data: &[u8]) -> Result<()> {
        self.send_to_writers(self.writers(None).await, data).await
    }

    async fn send_to_side(&self, side: GlassSide, data: &[u8]) -> Result<()> {
        self.send_to_writers(self.writers(Some(side)).await, data)
            .await
    }

    async fn send_to_writers(&self, writers: Vec<G1Writer>, data: &[u8]) -> Result<()> {
        if writers.is_empty() {
            return Err(anyhow!("G1 glasses are not connected"));
        }
        for writer in writers {
            writer
                .peripheral
                .write(&writer.tx, data, WriteType::WithResponse)
                .await
                .with_context(|| format!("write G1 packet to {} glass", writer.side.as_str()))?;
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
        Ok(())
    }

    async fn set_last_event(&self, message: String) {
        let mut rt = self.runtime.lock().await;
        rt.last_event = Some(message);
        rt.last_error = None;
    }

    async fn emit_status(&self, app: &AppHandle) {
        let status = self.status().await;
        self.emit_event(
            app,
            G1Event {
                event_type: "status".to_string(),
                side: None,
                action: None,
                subcommand: None,
                message: None,
                battery: None,
                status: Some(status),
            },
        );
    }

    fn emit_event(&self, app: &AppHandle, event: G1Event) {
        let _ = app.emit("g1-event", event);
    }
}

fn build_heartbeat(seq: u8) -> Vec<u8> {
    let s = seq % 0xFF;
    vec![HEARTBEAT, 0x06, 0x00, s, 0x04, s]
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_battery_response() {
        let left =
            G1BatteryInfo::from_response(&[0x2C, 0x66, 85, 0xE6, 0x01], GlassSide::Left).unwrap();
        assert_eq!(left.percentage, 85);
        assert_eq!(left.voltage, 0xE6);
        assert!(left.is_charging);

        let clamped =
            G1BatteryInfo::from_response(&[0x2C, 0x66, 255, 0, 0], GlassSide::Right).unwrap();
        assert_eq!(clamped.percentage, 100);
        assert!(G1BatteryInfo::from_response(&[0x25, 0x66, 85, 0, 0], GlassSide::Left).is_none());
    }

    #[test]
    fn builds_dashboard_text_packets() {
        let packets = build_text_packets("hello world");
        assert_eq!(packets.first().unwrap()[0], SEND_RESULT);
        assert_eq!(packets.last().unwrap()[4], 0x40);
        assert!(String::from_utf8_lossy(packets.last().unwrap()).contains("hello world"));
    }

    #[test]
    fn builds_streaming_packet_for_last_page() {
        let packet = build_streaming_text_packet(
            "one two three four five six seven eight nine ten eleven twelve",
        );
        assert_eq!(packet[0], SEND_RESULT);
        assert_eq!(packet[4], 0x30);
        assert!(packet.len() > 9);
    }

    #[test]
    fn maps_weather_icons_like_mobile() {
        assert_eq!(weather_icon_id(0, true), 0x10);
        assert_eq!(weather_icon_id(0, false), 0x01);
        assert_eq!(weather_icon_id(3, true), 0x02);
        assert_eq!(weather_icon_id(61, true), 0x05);
        assert_eq!(weather_icon_id(65, true), 0x06);
        assert_eq!(weather_icon_id(71, true), 0x09);
        assert_eq!(weather_icon_id(95, true), 0x07);
        assert_eq!(weather_icon_id(45, true), 0x0B);
        assert_eq!(weather_icon_id(56, true), 0x0F);
    }

    #[test]
    fn builds_notification_chunks() {
        let packets = build_notification_packets(&G1NotificationInput {
            title: "Hello".into(),
            subtitle: "Mention".into(),
            message: "A short message".into(),
            app_identifier: "systems.xt.agixt.desktop".into(),
            display_name: "AGiXT".into(),
            msg_id: Some(1),
        })
        .unwrap();
        assert_eq!(packets[0][0], NOTIFICATION);
        assert_eq!(packets[0][1], packets.len() as u8);
        assert_eq!(packets[0][2], 0);
    }

    #[test]
    fn builds_note_commands() {
        let add = build_note_add_packet(1, "AGiXT", "Remember this").unwrap();
        assert_eq!(add[0], QUICK_NOTE_ADD);
        assert_eq!(add[9], 1);
        let delete = build_note_delete_packet(4).unwrap();
        assert_eq!(delete[0], QUICK_NOTE_ADD);
        assert_eq!(delete[9], 4);
        assert!(build_note_add_packet(5, "bad", "bad").is_err());
    }
}
