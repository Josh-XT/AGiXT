use anyhow::{Context, Result};
use serde::{Deserialize, Serialize};
use sqlx::sqlite::SqlitePoolOptions;
use sqlx::SqlitePool;
use std::path::PathBuf;

#[cfg(mobile)]
const DEFAULT_SERVER_URL: &str = "https://api.agixt.com";
#[cfg(not(mobile))]
const DEFAULT_SERVER_URL: &str = "http://localhost:7437";
#[cfg(mobile)]
const DEFAULT_WEB_URL: &str = "https://agixt.com";
#[cfg(not(mobile))]
const DEFAULT_WEB_URL: &str = "http://localhost:3437";
const DEFAULT_AGENT_NAME: &str = "XT";
#[cfg(mobile)]
const DEFAULT_BRAND: &str = "agixt";
#[cfg(not(mobile))]
const DEFAULT_BRAND: &str = "local";

/// Slug for the dedicated "local AGiXT" mode. The login screen probes
/// `http://localhost:7437` when this brand is selected and offers a
/// one-click installer if nothing is listening.
pub const BRAND_LOCAL: &str = "local";
/// Slug for the free-form "point at any server" mode.
pub const BRAND_CUSTOM: &str = "custom";

/// Catalog of preset AGiXT brand backends. Tuple is
/// `(slug, label, default_server_url, default_web_url)`.
///
/// The `web_url` is the public URL of the AGiXT *web client*, which is
/// where OAuth providers redirect after the user authorizes. AGiXT
/// pre-registers `{web_url}/user/close/{provider}` with Microsoft, Google,
/// etc — we have to use exactly that URL or the provider rejects the
/// request with `redirect_uri_mismatch`.
///
/// The `custom` slug maps to whatever the user typed in. We default the
/// backend to `localhost:7437` and the web client to `localhost:3437`
/// (the standard AGiXT dev setup), but both are editable.
pub const SERVICE_BRANDS: &[(&str, &str, &str, &str)] = &[
    (
        "agixt",
        "AGiXT.com",
        "https://api.agixt.com",
        "https://agixt.com",
    ),
    (
        "nursext",
        "NurseXT.com",
        "https://api.nursext.com",
        "https://nursext.com",
    ),
    (
        "xtsystems",
        "XT.Systems",
        "https://api.xt.systems",
        "https://xt.systems",
    ),
    (
        "boltremote",
        "BoltRemote.com",
        "https://api.boltremote.com",
        "https://boltremote.com",
    ),
    // Local: dedicated entry for `http://localhost:7437` so the login
    // screen can probe the port and offer a one-click installer when
    // nothing is listening. URLs are non-editable in this mode — if the
    // user wants a different host, they pick "Custom" instead.
    ("local", "Local", DEFAULT_SERVER_URL, DEFAULT_WEB_URL),
    // Custom: free-form, user-editable server + web URLs for any
    // self-hosted AGiXT that isn't a known brand and isn't the local
    // dev install.
    ("custom", "Custom", DEFAULT_SERVER_URL, DEFAULT_WEB_URL),
];

pub fn brand_default_url(slug: &str) -> &'static str {
    for (s, _, url, _) in SERVICE_BRANDS {
        if *s == slug {
            return url;
        }
    }
    DEFAULT_SERVER_URL
}

pub fn brand_default_web_url(slug: &str) -> &'static str {
    for (s, _, _, web) in SERVICE_BRANDS {
        if *s == slug {
            return web;
        }
    }
    DEFAULT_WEB_URL
}

fn default_true() -> bool {
    true
}

fn default_g1_time_format() -> String {
    "12h".to_string()
}

fn default_g1_temperature_unit() -> String {
    "fahrenheit".to_string()
}

fn default_g1_dashboard_layout() -> String {
    "dual".to_string()
}

fn default_g1_brightness() -> u8 {
    28
}

fn default_g1_headup_angle() -> u8 {
    20
}

fn default_g1_display_height() -> u8 {
    0
}

fn default_g1_display_depth() -> u8 {
    5
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct DesktopSettings {
    pub server_url: String,
    /// Public URL of the AGiXT web client. Used as the OAuth redirect
    /// target — must exactly match what AGiXT pre-registered with each
    /// provider (Microsoft, Google, etc) or those providers reject the
    /// request with `redirect_uri_mismatch`.
    #[serde(default)]
    pub web_url: String,
    /// One of the slugs in `SERVICE_BRANDS`. `"custom"` means use
    /// `server_url` literally and let the user edit it freely.
    #[serde(default)]
    pub service_brand: String,
    pub jwt: Option<String>,
    pub user_email: Option<String>,
    pub agent_id: Option<String>,
    pub agent_name: Option<String>,
    pub company_id: Option<String>,
    pub company_name: Option<String>,
    pub conversation_id: Option<String>,
    pub conversation_name: Option<String>,
    pub voice_enabled: bool,
    pub desktop_auto_update: bool,
    pub sidebar_open: bool,
    pub allow_client_commands: bool,
    /// `"system"`, `"light"`, or `"dark"`. `"system"` defers to the
    /// current OS color scheme via `prefers-color-scheme` and reacts to
    /// changes live. The frontend reads/applies this on boot before
    /// any UI paint to avoid a light-mode user flashing dark.
    #[serde(default)]
    pub theme: String,
    /// Last user-positioned coordinates of the dock window (physical px).
    /// Saved when the user drags the bubble; restored on next launch so
    /// the WM (mutter etc) doesn't place us in a random tile slot.
    pub dock_pos_x: Option<i32>,
    pub dock_pos_y: Option<i32>,
    /// Even Realities G1 glasses integration. The values mirror the
    /// Flutter mobile app defaults: display on, Fahrenheit, and 12-hour
    /// time unless the user opts into different dashboard behavior.
    #[serde(default)]
    pub g1_enabled: bool,
    #[serde(default = "default_true")]
    pub g1_display_enabled: bool,
    #[serde(default = "default_true")]
    pub g1_show_ai_responses: bool,
    #[serde(default = "default_true")]
    pub g1_notification_forwarding: bool,
    #[serde(default = "default_true")]
    pub g1_auto_connect: bool,
    #[serde(default = "default_g1_time_format")]
    pub g1_time_format: String,
    #[serde(default = "default_g1_temperature_unit")]
    pub g1_temperature_unit: String,
    #[serde(default = "default_g1_dashboard_layout")]
    pub g1_dashboard_layout: String,
    #[serde(default)]
    pub g1_weather_latitude: Option<f64>,
    #[serde(default)]
    pub g1_weather_longitude: Option<f64>,
    #[serde(default)]
    pub g1_left_device_id: Option<String>,
    #[serde(default)]
    pub g1_left_device_name: Option<String>,
    #[serde(default)]
    pub g1_right_device_id: Option<String>,
    #[serde(default)]
    pub g1_right_device_name: Option<String>,
    #[serde(default = "default_g1_brightness")]
    pub g1_brightness: u8,
    #[serde(default = "default_true")]
    pub g1_auto_brightness: bool,
    #[serde(default = "default_g1_headup_angle")]
    pub g1_headup_angle: u8,
    #[serde(default = "default_true")]
    pub g1_wear_detection: bool,
    #[serde(default = "default_g1_display_height")]
    pub g1_display_height: u8,
    #[serde(default = "default_g1_display_depth")]
    pub g1_display_depth: u8,
}

impl DesktopSettings {
    pub fn defaults() -> Self {
        Self {
            server_url: DEFAULT_SERVER_URL.to_string(),
            web_url: DEFAULT_WEB_URL.to_string(),
            service_brand: DEFAULT_BRAND.to_string(),
            jwt: None,
            user_email: None,
            agent_id: None,
            agent_name: Some(DEFAULT_AGENT_NAME.to_string()),
            company_id: None,
            company_name: None,
            conversation_id: None,
            conversation_name: None,
            voice_enabled: false,
            desktop_auto_update: true,
            sidebar_open: false,
            allow_client_commands: true,
            theme: "system".to_string(),
            dock_pos_x: None,
            dock_pos_y: None,
            g1_enabled: false,
            g1_display_enabled: true,
            g1_show_ai_responses: true,
            g1_notification_forwarding: true,
            g1_auto_connect: true,
            g1_time_format: default_g1_time_format(),
            g1_temperature_unit: default_g1_temperature_unit(),
            g1_dashboard_layout: default_g1_dashboard_layout(),
            g1_weather_latitude: None,
            g1_weather_longitude: None,
            g1_left_device_id: None,
            g1_left_device_name: None,
            g1_right_device_id: None,
            g1_right_device_name: None,
            g1_brightness: default_g1_brightness(),
            g1_auto_brightness: true,
            g1_headup_angle: default_g1_headup_angle(),
            g1_wear_detection: true,
            g1_display_height: default_g1_display_height(),
            g1_display_depth: default_g1_display_depth(),
        }
    }
}

pub struct ConfigStore {
    pool: SqlitePool,
}

impl ConfigStore {
    pub async fn open() -> Result<Self> {
        let path = config_path()?;
        Self::open_at(path).await
    }

    /// Open the settings database at an explicit file path. Tauri mobile
    /// passes its app-config directory here because `dirs` can return
    /// `None` when Android/iOS do not expose a normal `$HOME`.
    pub async fn open_at(path: PathBuf) -> Result<Self> {
        if let Some(parent) = path.parent() {
            std::fs::create_dir_all(parent).context("create config dir")?;
        }
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let pool = SqlitePoolOptions::new()
            .max_connections(4)
            .connect(&url)
            .await
            .with_context(|| format!("open sqlite at {}", path.display()))?;

        sqlx::query(
            r#"CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )"#,
        )
        .execute(&pool)
        .await?;

        let store = Self { pool };
        // Seed defaults the first time we run.
        if store.load().await?.jwt.is_none() && store.get_raw("server_url").await?.is_none() {
            store.save(&DesktopSettings::defaults()).await?;
        }
        #[cfg(mobile)]
        {
            let mut settings = store.load().await?;
            if settings.jwt.is_none()
                && settings.service_brand == BRAND_LOCAL
                && settings.server_url.trim_end_matches('/') == "http://localhost:7437"
            {
                let defaults = DesktopSettings::defaults();
                settings.service_brand = defaults.service_brand;
                settings.server_url = defaults.server_url;
                settings.web_url = defaults.web_url;
                store.save(&settings).await?;
            }
        }
        Ok(store)
    }

    async fn get_raw(&self, key: &str) -> Result<Option<String>> {
        let row: Option<(String,)> = sqlx::query_as("SELECT value FROM settings WHERE key = ?")
            .bind(key)
            .fetch_optional(&self.pool)
            .await?;
        Ok(row.map(|r| r.0))
    }

    async fn put_raw(&self, key: &str, value: &str) -> Result<()> {
        sqlx::query(
            "INSERT INTO settings(key,value) VALUES(?,?)
             ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        )
        .bind(key)
        .bind(value)
        .execute(&self.pool)
        .await?;
        Ok(())
    }

    async fn delete_raw(&self, key: &str) -> Result<()> {
        sqlx::query("DELETE FROM settings WHERE key = ?")
            .bind(key)
            .execute(&self.pool)
            .await?;
        Ok(())
    }

    pub async fn load(&self) -> Result<DesktopSettings> {
        let mut s = DesktopSettings::defaults();
        if let Some(v) = self.get_raw("server_url").await? {
            s.server_url = v;
        }
        if let Some(v) = self.get_raw("web_url").await? {
            s.web_url = v;
        }
        if let Some(v) = self.get_raw("service_brand").await? {
            s.service_brand = v;
        }
        s.jwt = self.get_raw("jwt").await?;
        s.user_email = self.get_raw("user_email").await?;
        s.agent_id = self.get_raw("agent_id").await?;
        if let Some(v) = self.get_raw("agent_name").await? {
            s.agent_name = Some(v);
        }
        s.company_id = self.get_raw("company_id").await?;
        s.company_name = self.get_raw("company_name").await?;
        s.conversation_id = self.get_raw("conversation_id").await?;
        s.conversation_name = self.get_raw("conversation_name").await?;
        if let Some(v) = self.get_raw("voice_enabled").await? {
            s.voice_enabled = v == "1";
        }
        if let Some(v) = self.get_raw("desktop_auto_update").await? {
            s.desktop_auto_update = v == "1";
        }
        if let Some(v) = self.get_raw("sidebar_open").await? {
            s.sidebar_open = v == "1";
        }
        if let Some(v) = self.get_raw("allow_client_commands").await? {
            s.allow_client_commands = v == "1";
        }
        if let Some(v) = self.get_raw("theme").await? {
            s.theme = v;
        }
        if let Some(v) = self.get_raw("dock_pos_x").await? {
            s.dock_pos_x = v.parse().ok();
        }
        if let Some(v) = self.get_raw("dock_pos_y").await? {
            s.dock_pos_y = v.parse().ok();
        }
        if let Some(v) = self.get_raw("g1_enabled").await? {
            s.g1_enabled = v == "1";
        }
        if let Some(v) = self.get_raw("g1_display_enabled").await? {
            s.g1_display_enabled = v == "1";
        }
        if let Some(v) = self.get_raw("g1_show_ai_responses").await? {
            s.g1_show_ai_responses = v == "1";
        }
        if let Some(v) = self.get_raw("g1_notification_forwarding").await? {
            s.g1_notification_forwarding = v == "1";
        }
        if let Some(v) = self.get_raw("g1_auto_connect").await? {
            s.g1_auto_connect = v == "1";
        }
        if let Some(v) = self.get_raw("g1_time_format").await? {
            s.g1_time_format = v;
        }
        if let Some(v) = self.get_raw("g1_temperature_unit").await? {
            s.g1_temperature_unit = v;
        }
        if let Some(v) = self.get_raw("g1_dashboard_layout").await? {
            s.g1_dashboard_layout = v;
        }
        if let Some(v) = self.get_raw("g1_weather_latitude").await? {
            s.g1_weather_latitude = v.parse().ok();
        }
        if let Some(v) = self.get_raw("g1_weather_longitude").await? {
            s.g1_weather_longitude = v.parse().ok();
        }
        s.g1_left_device_id = self.get_raw("g1_left_device_id").await?;
        s.g1_left_device_name = self.get_raw("g1_left_device_name").await?;
        s.g1_right_device_id = self.get_raw("g1_right_device_id").await?;
        s.g1_right_device_name = self.get_raw("g1_right_device_name").await?;
        if let Some(v) = self.get_raw("g1_brightness").await? {
            s.g1_brightness = v.parse().unwrap_or_else(|_| default_g1_brightness());
        }
        if let Some(v) = self.get_raw("g1_auto_brightness").await? {
            s.g1_auto_brightness = v == "1";
        }
        if let Some(v) = self.get_raw("g1_headup_angle").await? {
            s.g1_headup_angle = v.parse().unwrap_or_else(|_| default_g1_headup_angle());
        }
        if let Some(v) = self.get_raw("g1_wear_detection").await? {
            s.g1_wear_detection = v == "1";
        }
        if let Some(v) = self.get_raw("g1_display_height").await? {
            s.g1_display_height = v.parse().unwrap_or_else(|_| default_g1_display_height());
        }
        if let Some(v) = self.get_raw("g1_display_depth").await? {
            s.g1_display_depth = v.parse().unwrap_or_else(|_| default_g1_display_depth());
        }
        Ok(s)
    }

    pub async fn save(&self, s: &DesktopSettings) -> Result<()> {
        self.put_raw("server_url", &s.server_url).await?;
        self.put_raw("web_url", &s.web_url).await?;
        self.put_raw("service_brand", &s.service_brand).await?;
        if let Some(v) = &s.jwt {
            self.put_raw("jwt", v).await?;
        }
        if let Some(v) = &s.user_email {
            self.put_raw("user_email", v).await?;
        }
        if let Some(v) = &s.agent_id {
            self.put_raw("agent_id", v).await?;
        }
        if let Some(v) = &s.agent_name {
            self.put_raw("agent_name", v).await?;
        }
        if let Some(v) = &s.company_id {
            self.put_raw("company_id", v).await?;
        }
        if let Some(v) = &s.company_name {
            self.put_raw("company_name", v).await?;
        }
        if let Some(v) = &s.conversation_id {
            self.put_raw("conversation_id", v).await?;
        } else {
            self.delete_raw("conversation_id").await?;
        }
        if let Some(v) = &s.conversation_name {
            self.put_raw("conversation_name", v).await?;
        } else {
            self.delete_raw("conversation_name").await?;
        }
        self.put_raw("voice_enabled", if s.voice_enabled { "1" } else { "0" })
            .await?;
        self.put_raw(
            "desktop_auto_update",
            if s.desktop_auto_update { "1" } else { "0" },
        )
        .await?;
        self.put_raw("sidebar_open", if s.sidebar_open { "1" } else { "0" })
            .await?;
        self.put_raw(
            "allow_client_commands",
            if s.allow_client_commands { "1" } else { "0" },
        )
        .await?;
        let theme = if s.theme.is_empty() {
            "system"
        } else {
            s.theme.as_str()
        };
        self.put_raw("theme", theme).await?;
        if let Some(v) = s.dock_pos_x {
            self.put_raw("dock_pos_x", &v.to_string()).await?;
        }
        if let Some(v) = s.dock_pos_y {
            self.put_raw("dock_pos_y", &v.to_string()).await?;
        }
        self.put_raw("g1_enabled", if s.g1_enabled { "1" } else { "0" })
            .await?;
        self.put_raw(
            "g1_display_enabled",
            if s.g1_display_enabled { "1" } else { "0" },
        )
        .await?;
        self.put_raw(
            "g1_show_ai_responses",
            if s.g1_show_ai_responses { "1" } else { "0" },
        )
        .await?;
        self.put_raw(
            "g1_notification_forwarding",
            if s.g1_notification_forwarding {
                "1"
            } else {
                "0"
            },
        )
        .await?;
        self.put_raw("g1_auto_connect", if s.g1_auto_connect { "1" } else { "0" })
            .await?;
        self.put_raw("g1_time_format", &s.g1_time_format).await?;
        self.put_raw("g1_temperature_unit", &s.g1_temperature_unit)
            .await?;
        self.put_raw("g1_dashboard_layout", &s.g1_dashboard_layout)
            .await?;
        if let Some(v) = s.g1_weather_latitude {
            self.put_raw("g1_weather_latitude", &v.to_string()).await?;
        } else {
            self.delete_raw("g1_weather_latitude").await?;
        }
        if let Some(v) = s.g1_weather_longitude {
            self.put_raw("g1_weather_longitude", &v.to_string()).await?;
        } else {
            self.delete_raw("g1_weather_longitude").await?;
        }
        if let Some(v) = &s.g1_left_device_id {
            self.put_raw("g1_left_device_id", v).await?;
        } else {
            self.delete_raw("g1_left_device_id").await?;
        }
        if let Some(v) = &s.g1_left_device_name {
            self.put_raw("g1_left_device_name", v).await?;
        } else {
            self.delete_raw("g1_left_device_name").await?;
        }
        if let Some(v) = &s.g1_right_device_id {
            self.put_raw("g1_right_device_id", v).await?;
        } else {
            self.delete_raw("g1_right_device_id").await?;
        }
        if let Some(v) = &s.g1_right_device_name {
            self.put_raw("g1_right_device_name", v).await?;
        } else {
            self.delete_raw("g1_right_device_name").await?;
        }
        self.put_raw("g1_brightness", &s.g1_brightness.to_string())
            .await?;
        self.put_raw(
            "g1_auto_brightness",
            if s.g1_auto_brightness { "1" } else { "0" },
        )
        .await?;
        self.put_raw("g1_headup_angle", &s.g1_headup_angle.to_string())
            .await?;
        self.put_raw(
            "g1_wear_detection",
            if s.g1_wear_detection { "1" } else { "0" },
        )
        .await?;
        self.put_raw("g1_display_height", &s.g1_display_height.to_string())
            .await?;
        self.put_raw("g1_display_depth", &s.g1_display_depth.to_string())
            .await?;
        Ok(())
    }

    pub async fn clear_jwt(&self) -> Result<()> {
        self.delete_raw("jwt").await?;
        Ok(())
    }
}

fn config_path() -> Result<PathBuf> {
    let base = if cfg!(target_os = "windows") {
        dirs::data_local_dir()
    } else if cfg!(target_os = "macos") {
        dirs::data_dir()
    } else {
        dirs::config_dir()
    }
    .context("resolve config dir")?;
    Ok(base.join("agixt-desktop").join("settings.db"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_db() -> (tempfile::TempDir, PathBuf) {
        let dir = tempfile::tempdir().unwrap();
        let p = dir.path().join("settings.db");
        (dir, p)
    }

    #[tokio::test]
    async fn defaults_round_trip() {
        let (_dir, p) = temp_db();
        let store = ConfigStore::open_at(p).await.unwrap();
        let s = store.load().await.unwrap();
        assert_eq!(s.server_url, DEFAULT_SERVER_URL);
        assert_eq!(s.agent_name.as_deref(), Some(DEFAULT_AGENT_NAME));
        assert!(s.jwt.is_none());
        assert!(s.allow_client_commands);
        // First-launch default is bubble mode so the user sees the
        // floating chat icon, not a maximized panel.
        assert!(!s.sidebar_open);
        assert!(!s.voice_enabled);
        assert!(s.desktop_auto_update);
        // Theme defaults to "system" so first-launch matches the OS
        // (light-mode users don't get force-flashed dark).
        assert_eq!(s.theme, "system");
        assert!(!s.g1_enabled);
        assert!(s.g1_display_enabled);
        assert!(s.g1_show_ai_responses);
        assert!(s.g1_notification_forwarding);
        assert!(s.g1_auto_connect);
        assert_eq!(s.g1_time_format, "12h");
        assert_eq!(s.g1_temperature_unit, "fahrenheit");
        assert_eq!(s.g1_dashboard_layout, "dual");
        assert_eq!(s.g1_brightness, 28);
        assert!(s.g1_auto_brightness);
        assert_eq!(s.g1_headup_angle, 20);
        assert!(s.g1_wear_detection);
        assert_eq!(s.g1_display_height, 0);
        assert_eq!(s.g1_display_depth, 5);
    }

    #[tokio::test]
    async fn theme_round_trip() {
        let (_dir, p) = temp_db();
        let store = ConfigStore::open_at(p).await.unwrap();
        let mut s = store.load().await.unwrap();
        s.theme = "light".into();
        store.save(&s).await.unwrap();
        assert_eq!(store.load().await.unwrap().theme, "light");
        s.theme = "dark".into();
        store.save(&s).await.unwrap();
        assert_eq!(store.load().await.unwrap().theme, "dark");
        // Empty incoming string normalizes back to "system" so we never
        // persist a value the frontend can't interpret.
        s.theme = "".into();
        store.save(&s).await.unwrap();
        assert_eq!(store.load().await.unwrap().theme, "system");
    }

    #[tokio::test]
    async fn save_then_load_preserves_values() {
        let (_dir, p) = temp_db();
        let store = ConfigStore::open_at(p).await.unwrap();
        let mut s = DesktopSettings::defaults();
        s.server_url = "https://example.com".into();
        s.jwt = Some("eyJfake".into());
        s.agent_id = Some("agent-uuid".into());
        s.agent_name = Some("Custom".into());
        s.company_id = Some("company-uuid".into());
        s.company_name = Some("Acme Inc".into());
        s.conversation_id = Some("convo-uuid".into());
        s.conversation_name = Some("Conversation Title".into());
        s.voice_enabled = true;
        s.desktop_auto_update = false;
        s.sidebar_open = false;
        s.allow_client_commands = false;
        s.g1_enabled = true;
        s.g1_display_enabled = false;
        s.g1_show_ai_responses = false;
        s.g1_notification_forwarding = false;
        s.g1_auto_connect = false;
        s.g1_time_format = "24h".into();
        s.g1_temperature_unit = "celsius".into();
        s.g1_dashboard_layout = "minimal".into();
        s.g1_weather_latitude = Some(40.7128);
        s.g1_weather_longitude = Some(-74.0060);
        s.g1_left_device_id = Some("left-id".into());
        s.g1_left_device_name = Some("G1_L".into());
        s.g1_right_device_id = Some("right-id".into());
        s.g1_right_device_name = Some("G1_R".into());
        s.g1_brightness = 12;
        s.g1_auto_brightness = false;
        s.g1_headup_angle = 30;
        s.g1_wear_detection = false;
        s.g1_display_height = 3;
        s.g1_display_depth = 7;
        store.save(&s).await.unwrap();

        let loaded = store.load().await.unwrap();
        assert_eq!(loaded.server_url, "https://example.com");
        assert_eq!(loaded.jwt.as_deref(), Some("eyJfake"));
        assert_eq!(loaded.agent_id.as_deref(), Some("agent-uuid"));
        assert_eq!(loaded.agent_name.as_deref(), Some("Custom"));
        assert_eq!(loaded.company_id.as_deref(), Some("company-uuid"));
        assert_eq!(loaded.company_name.as_deref(), Some("Acme Inc"));
        assert_eq!(loaded.conversation_id.as_deref(), Some("convo-uuid"));
        assert_eq!(
            loaded.conversation_name.as_deref(),
            Some("Conversation Title")
        );
        assert!(loaded.voice_enabled);
        assert!(!loaded.desktop_auto_update);
        assert!(!loaded.sidebar_open);
        assert!(!loaded.allow_client_commands);
        assert!(loaded.g1_enabled);
        assert!(!loaded.g1_display_enabled);
        assert!(!loaded.g1_show_ai_responses);
        assert!(!loaded.g1_notification_forwarding);
        assert!(!loaded.g1_auto_connect);
        assert_eq!(loaded.g1_time_format, "24h");
        assert_eq!(loaded.g1_temperature_unit, "celsius");
        assert_eq!(loaded.g1_dashboard_layout, "minimal");
        assert_eq!(loaded.g1_weather_latitude, Some(40.7128));
        assert_eq!(loaded.g1_weather_longitude, Some(-74.0060));
        assert_eq!(loaded.g1_left_device_id.as_deref(), Some("left-id"));
        assert_eq!(loaded.g1_left_device_name.as_deref(), Some("G1_L"));
        assert_eq!(loaded.g1_right_device_id.as_deref(), Some("right-id"));
        assert_eq!(loaded.g1_right_device_name.as_deref(), Some("G1_R"));
        assert_eq!(loaded.g1_brightness, 12);
        assert!(!loaded.g1_auto_brightness);
        assert_eq!(loaded.g1_headup_angle, 30);
        assert!(!loaded.g1_wear_detection);
        assert_eq!(loaded.g1_display_height, 3);
        assert_eq!(loaded.g1_display_depth, 7);
    }

    #[tokio::test]
    async fn clear_jwt_removes_only_jwt() {
        let (_dir, p) = temp_db();
        let store = ConfigStore::open_at(p).await.unwrap();
        let mut s = DesktopSettings::defaults();
        s.jwt = Some("token".into());
        s.agent_id = Some("agent".into());
        store.save(&s).await.unwrap();

        store.clear_jwt().await.unwrap();
        let loaded = store.load().await.unwrap();
        assert!(loaded.jwt.is_none());
        assert_eq!(loaded.agent_id.as_deref(), Some("agent"));
    }

    #[tokio::test]
    async fn save_clears_conversation_when_none() {
        let (_dir, p) = temp_db();
        let store = ConfigStore::open_at(p).await.unwrap();
        let mut s = DesktopSettings::defaults();
        s.conversation_id = Some("convo-uuid".into());
        s.conversation_name = Some("Old Name".into());
        store.save(&s).await.unwrap();

        s.conversation_id = None;
        s.conversation_name = None;
        store.save(&s).await.unwrap();

        let loaded = store.load().await.unwrap();
        assert!(loaded.conversation_id.is_none());
        assert!(loaded.conversation_name.is_none());
    }

    #[tokio::test]
    async fn upsert_overwrites_existing() {
        let (_dir, p) = temp_db();
        let store = ConfigStore::open_at(p).await.unwrap();
        let mut s = DesktopSettings::defaults();
        s.jwt = Some("first".into());
        store.save(&s).await.unwrap();
        s.jwt = Some("second".into());
        store.save(&s).await.unwrap();
        assert_eq!(store.load().await.unwrap().jwt.as_deref(), Some("second"));
    }
}
