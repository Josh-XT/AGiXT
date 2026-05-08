//! AGiXT Desktop — Tauri 2 application entry.
//!
//! Two windows:
//!   * "sidebar"  — the chat panel docked to the right edge of the primary
//!                  monitor. Borderless, transparent, always-on-top.
//!   * "toggle"   — a tiny floating chat icon that lives over other windows
//!                  and shows/hides the sidebar when clicked.
//!
//! Rust IPC commands expose: settings, agent/company list, conversation
//! creation, prompt send (REST fallback), local automation (screenshot,
//! click, key, type, drag), and window control.

pub mod api;
pub mod automation;
pub mod chat_stream;
pub mod client_tool_specs;
pub mod client_tools_prompt;
pub mod config;
pub mod filesystem;
pub mod hardware;
pub mod local_install;
#[cfg(not(mobile))]
pub mod terminal;
#[cfg(mobile)]
#[path = "terminal_mobile.rs"]
pub mod terminal;
pub mod updater;
#[cfg(not(mobile))]
pub mod voice;
#[cfg(mobile)]
#[path = "voice_mobile.rs"]
pub mod voice;

use std::sync::atomic::AtomicBool;
use std::sync::Arc;
use std::time::Duration;

use serde::{Deserialize, Serialize};
#[cfg(not(mobile))]
use tauri::{
    image::Image,
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    LogicalSize, PhysicalPosition,
};
use tauri::{AppHandle, Emitter, Manager, State, WebviewWindow};
use tauri_plugin_opener::OpenerExt;
use tokio::sync::Mutex;

use config::{ConfigStore, DesktopSettings};

const MAIN_LABEL: &str = "main";

/// Margin (logical px) between the popover window and the tray icon /
/// screen edge.
const POPOVER_MARGIN: f64 = 6.0;
/// Popover size in logical pixels.
const PANEL_WIDTH: f64 = 400.0;
const PANEL_HEIGHT: f64 = 800.0;

pub struct AppState {
    pub store: Arc<ConfigStore>,
    pub settings: Mutex<DesktopSettings>,
    pub terminals: Arc<terminal::TerminalManager>,
    pub voice: Arc<voice::VoiceRecorder>,
    pub sudo_keepalive: Mutex<Option<tokio::task::JoinHandle<()>>>,
    /// Set to `true` for ~400ms after a programmatic show to keep the
    /// blur handler from immediately re-hiding the popover when the
    /// triggering tray-click steals focus back to the panel area.
    pub suppress_blur_hide: Arc<AtomicBool>,
}

/// Wrapper around the registered TrayIcon so we can park it in
/// `app.manage` and keep it alive for the duration of the app process.
/// Without this, the icon has been observed to disappear after the
/// first interaction on Ubuntu's AppIndicator extension.
#[allow(dead_code)]
#[cfg(not(mobile))]
struct TrayHolder(pub std::sync::Mutex<Option<tauri::tray::TrayIcon>>);

#[derive(Debug, Serialize, Deserialize)]
pub struct ToolError {
    pub error: String,
}

impl From<anyhow::Error> for ToolError {
    fn from(e: anyhow::Error) -> Self {
        Self {
            error: format!("{e:#}"),
        }
    }
}

type ToolResult<T> = Result<T, ToolError>;

#[tauri::command]
fn frontend_log(level: String, message: String) {
    let text: String = message.chars().take(4_000).collect();
    match level.to_ascii_lowercase().as_str() {
        "error" => tracing::error!(target: "frontend", "{text}"),
        "warn" | "warning" => tracing::warn!(target: "frontend", "{text}"),
        "debug" => tracing::debug!(target: "frontend", "{text}"),
        "trace" => tracing::trace!(target: "frontend", "{text}"),
        _ => tracing::info!(target: "frontend", "{text}"),
    }
}

// --------------------------------------------------------------------------
// Settings IPC
// --------------------------------------------------------------------------

#[tauri::command]
async fn get_settings(state: State<'_, AppState>) -> ToolResult<DesktopSettings> {
    let s = state.settings.lock().await.clone();
    tracing::info!(
        "get_settings -> sidebar_open={}, has_jwt={}",
        s.sidebar_open,
        s.jwt.is_some()
    );
    Ok(s)
}

#[tauri::command]
async fn save_settings(
    state: State<'_, AppState>,
    settings: DesktopSettings,
) -> ToolResult<DesktopSettings> {
    state.store.save(&settings).await.map_err(ToolError::from)?;
    let mut current = state.settings.lock().await;
    *current = settings.clone();
    Ok(settings)
}

#[tauri::command]
async fn logout(state: State<'_, AppState>) -> ToolResult<()> {
    state.store.clear_jwt().await.map_err(ToolError::from)?;
    let mut current = state.settings.lock().await;
    current.jwt = None;
    current.user_email = None;
    current.agent_id = None;
    current.agent_name = None;
    current.company_id = None;
    current.company_name = None;
    current.conversation_id = None;
    current.conversation_name = None;
    state.store.save(&current).await.map_err(ToolError::from)?;
    Ok(())
}

// --------------------------------------------------------------------------
// Desktop app updates
// --------------------------------------------------------------------------

#[tauri::command]
async fn desktop_update_check() -> ToolResult<updater::DesktopUpdateStatus> {
    updater::check().await.map_err(ToolError::from)
}

#[tauri::command]
async fn desktop_update_install() -> ToolResult<updater::DesktopUpdateInstallResult> {
    updater::install().await.map_err(ToolError::from)
}

// --------------------------------------------------------------------------
// Native voice recording
// --------------------------------------------------------------------------

#[tauri::command]
async fn voice_start_recording(
    state: State<'_, AppState>,
) -> ToolResult<voice::VoiceStartResponse> {
    state.voice.start().map_err(ToolError::from)
}

#[tauri::command]
async fn voice_stop_recording(state: State<'_, AppState>) -> ToolResult<voice::VoiceStopResponse> {
    state.voice.stop().map_err(ToolError::from)
}

#[tauri::command]
async fn voice_cancel_recording(state: State<'_, AppState>) -> ToolResult<()> {
    state.voice.cancel().map_err(ToolError::from)
}

// --------------------------------------------------------------------------
// Auth
// --------------------------------------------------------------------------

#[derive(Debug, Serialize)]
pub struct ServiceBrand {
    pub slug: String,
    pub label: String,
    pub default_url: String,
    /// Public URL of the brand's web client — also the OAuth redirect
    /// host. Each AGiXT brand pre-registers `{web}/user/close/{provider}`
    /// with Microsoft, Google, etc., so we must match exactly.
    pub default_web_url: String,
}

#[tauri::command]
fn list_service_brands() -> Vec<ServiceBrand> {
    config::SERVICE_BRANDS
        .iter()
        .filter(|(slug, _, _, _)| {
            // The "local" brand probes localhost:7437 and offers a
            // one-click installer. Neither makes sense on Android/iOS
            // where the user can't run an AGiXT backend on-device, so
            // it's hidden on mobile builds.
            #[cfg(mobile)]
            {
                *slug != config::BRAND_LOCAL
            }
            #[cfg(not(mobile))]
            {
                let _ = slug;
                true
            }
        })
        .map(|(slug, label, url, web)| ServiceBrand {
            slug: (*slug).into(),
            label: (*label).into(),
            default_url: (*url).into(),
            default_web_url: (*web).into(),
        })
        .collect()
}

#[tauri::command]
async fn list_oauth_providers(server_url: String) -> ToolResult<Vec<api::OAuthProvider>> {
    let providers = api::list_oauth_providers(&server_url)
        .await
        .map_err(ToolError::from)?;
    // Filter to login-capable, then dedupe by authorize host. AGiXT
    // exposes both `microsoft_sso` (dedicated SSO login) and `teams`
    // (extension provider that's also login-capable). Both go to
    // login.microsoftonline.com — showing both as separate buttons is
    // confusing UX, so we keep just the canonical SSO entry per host.
    let login_capable: Vec<_> = providers.into_iter().filter(|p| p.login_capable).collect();
    Ok(api::dedupe_login_providers(login_capable))
}

#[derive(Debug, Deserialize)]
pub struct LoginArgs {
    pub server_url: String,
    pub email: String,
    #[serde(default)]
    pub password: String,
    #[serde(default)]
    pub mfa_token: Option<String>,
}

#[tauri::command]
async fn login_password(
    state: State<'_, AppState>,
    args: LoginArgs,
) -> ToolResult<api::LoginResponse> {
    let resp = api::login_password(
        &args.server_url,
        &args.email,
        &args.password,
        args.mfa_token.as_deref(),
    )
    .await
    .map_err(ToolError::from)?;
    if let Some(token) = &resp.token {
        let mut s = state.settings.lock().await;
        s.server_url = args.server_url.clone();
        s.jwt = Some(token.clone());
        s.user_email = Some(args.email.clone());
        state.store.save(&s).await.map_err(ToolError::from)?;
    }
    Ok(resp)
}

#[derive(Debug, Deserialize)]
pub struct MagicLinkArgs {
    pub server_url: String,
    pub email: String,
}

#[tauri::command]
async fn request_magic_link(args: MagicLinkArgs) -> ToolResult<()> {
    api::request_magic_link(&args.server_url, &args.email)
        .await
        .map_err(ToolError::from)
}

#[derive(Debug, Deserialize)]
pub struct RegisterArgs {
    pub server_url: String,
    pub email: String,
    pub first_name: String,
    pub last_name: String,
    pub password: String,
    #[serde(default)]
    pub invitation_id: Option<String>,
}

#[tauri::command]
async fn register_account(
    state: State<'_, AppState>,
    args: RegisterArgs,
) -> ToolResult<api::LoginResponse> {
    let resp = api::register_user(
        &args.server_url,
        &args.email,
        &args.first_name,
        &args.last_name,
        &args.password,
        args.invitation_id.as_deref(),
    )
    .await
    .map_err(ToolError::from)?;
    if let Some(token) = &resp.token {
        let mut s = state.settings.lock().await;
        s.server_url = args.server_url.clone();
        s.jwt = Some(token.clone());
        s.user_email = Some(args.email.clone());
        state.store.save(&s).await.map_err(ToolError::from)?;
    }
    Ok(resp)
}

/// Accept a JWT pasted from a magic-link URL or from the user's web
/// session. Validates by hitting `/v1/user`; on success persists.
#[tauri::command]
async fn login_with_jwt(
    state: State<'_, AppState>,
    server_url: String,
    raw: String,
) -> ToolResult<()> {
    let token = extract_jwt(&raw).ok_or_else(|| ToolError {
        error: "couldn't find a JWT in that input".into(),
    })?;
    // Verify by calling /v1/user.
    let client = api::build_client().map_err(ToolError::from)?;
    let url = format!("{}/v1/user", server_url.trim_end_matches('/'));
    let resp = client
        .get(&url)
        .bearer_auth(&token)
        .send()
        .await
        .map_err(|e| ToolError {
            error: format!("verify jwt: {e}"),
        })?;
    if !resp.status().is_success() {
        return Err(ToolError {
            error: format!("server rejected token: HTTP {}", resp.status()),
        });
    }
    let user: serde_json::Value = resp.json().await.unwrap_or_default();
    let email = user
        .get("email")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    let mut s = state.settings.lock().await;
    s.server_url = server_url;
    s.jwt = Some(token);
    if email.is_some() {
        s.user_email = email;
    }
    state.store.save(&s).await.map_err(ToolError::from)?;
    Ok(())
}

#[derive(Debug, Deserialize)]
pub struct OAuthUrlArgs {
    pub server_url: String,
    /// Public URL of the AGiXT web client — *not* the backend. AGiXT
    /// pre-registered `{web_url}/user/close/{provider}` with each OAuth
    /// provider, so the redirect URI we send must match this exactly,
    /// not the backend URL.
    pub web_url: String,
    pub provider: api::OAuthProvider,
    /// Override for the default `{web_url}/user/close/{provider}`. Only
    /// useful if an embedder wants to handle OAuth callbacks themselves.
    #[serde(default)]
    pub redirect_uri: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct OAuthUrlResult {
    pub url: String,
    pub redirect_uri: String,
    pub pkce: Option<api::PkceChallenge>,
}

#[tauri::command]
async fn build_oauth_login_url(args: OAuthUrlArgs) -> ToolResult<OAuthUrlResult> {
    // Default to `{web_url}/user/close/{slug}` — that's the URL the
    // AGiXT web client uses and what each OAuth app config has
    // pre-registered. The slug is *not* the raw provider name —
    // `microsoft_sso` becomes `microsoft`, `_`/`.`/` ` become `-`.
    // See `api::redirect_slug_for` for the exact rules (kept in sync
    // with web/components/auth/OAuth.tsx).
    //
    // We can't put any extra query params on the redirect_uri itself
    // (most OAuth providers reject mismatches), but the desktop-app
    // hint is carried separately as `state` so the close page can
    // detect it and redirect to `agixt://login?token=...` instead of
    // landing the user in the web UI.
    let redirect_uri = args.redirect_uri.unwrap_or_else(|| {
        format!(
            "{}/user/close/{}",
            args.web_url.trim_end_matches('/'),
            api::redirect_slug_for(&args.provider.name),
        )
    });
    let pkce = if args.provider.pkce_required {
        Some(
            api::pkce_challenge(&args.server_url)
                .await
                .map_err(ToolError::from)?,
        )
    } else {
        None
    };
    // The web close page reads `state` to decide whether to redirect
    // to `agixt://login?token=...` (desktop) vs. landing in /chat (web).
    // Tag every desktop-launched flow with `desktop=1`.
    let url = api::build_oauth_url_with_state(
        &args.provider,
        &redirect_uri,
        pkce.as_ref(),
        Some("desktop=1"),
    );
    Ok(OAuthUrlResult {
        url,
        redirect_uri,
        pkce,
    })
}

/// Sibling of `build_oauth_login_url` for *extension* OAuth flows. Same
/// redirect URI shape (`{web_url}/user/close/{slug}`) so we don't need new
/// app-config registrations on the OAuth provider side, but tags the state
/// param with `desktop_connect=1` so the web close page knows to hand the
/// authorization `code` back to the desktop via `agixt://oauth-connect`
/// instead of POSTing it itself (the browser doesn't have the desktop's
/// JWT and couldn't authenticate the POST anyway).
#[tauri::command]
async fn build_oauth_connect_url(args: OAuthUrlArgs) -> ToolResult<OAuthUrlResult> {
    let redirect_uri = args.redirect_uri.unwrap_or_else(|| {
        format!(
            "{}/user/close/{}",
            args.web_url.trim_end_matches('/'),
            api::redirect_slug_for(&args.provider.name),
        )
    });
    let pkce = if args.provider.pkce_required {
        Some(
            api::pkce_challenge(&args.server_url)
                .await
                .map_err(ToolError::from)?,
        )
    } else {
        None
    };
    // Carry the canonical provider name in the state so the deep-link
    // handler doesn't have to reverse-engineer it from the slug. Format
    // matches the close page's regex: `desktop_connect=1|provider=<name>`.
    let state_payload = format!(
        "desktop_connect=1|provider={}",
        urlencode_state(&args.provider.name)
    );
    let url = api::build_oauth_url_with_state(
        &args.provider,
        &redirect_uri,
        pkce.as_ref(),
        Some(&state_payload),
    );
    Ok(OAuthUrlResult {
        url,
        redirect_uri,
        pkce,
    })
}

/// Bare percent-encode for state values. We can't pull `urlencode` out of
/// `api.rs` (it's private), and OAuth state allowed-chars are conservative
/// across providers, so we encode anything that isn't unreserved.
fn urlencode_state(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{:02X}", b)),
        }
    }
    out
}

/// Show the dedicated Agent Settings window. The window is declared in
/// tauri.conf.json with `visible: false`; this command just promotes it,
/// focuses it, and centers it (the user might've moved/hidden it earlier).
#[tauri::command]
async fn open_agent_settings(app: AppHandle, state: State<'_, AppState>) -> ToolResult<()> {
    let signed_in = {
        let settings = state.settings.lock().await;
        settings
            .jwt
            .as_deref()
            .map(|jwt| !jwt.trim().is_empty())
            .unwrap_or(false)
    };
    if !signed_in {
        if let Some(win) = app.get_webview_window(MAIN_LABEL) {
            let _ = win.show();
            let _ = win.set_focus();
        }
        if let Some(win) = app.get_webview_window("agent-settings") {
            let _ = win.hide();
        }
        return Err(ToolError {
            error: "Sign in before opening agent settings.".into(),
        });
    }

    if let Some(win) = app.get_webview_window("agent-settings") {
        let _ = win.show();
        #[cfg(not(mobile))]
        let _ = win.unminimize();
        let _ = win.set_focus();
        Ok(())
    } else {
        Err(ToolError {
            error: "agent-settings window not found".into(),
        })
    }
}

/// Called when a `agixt://oauth-connect?provider=<name>&code=<code>` deep
/// link arrives. The web close page hands us the authorization code; we
/// POST it to `/v1/oauth2/{slug}` server-side using the desktop's JWT (the
/// browser has no JWT for the desktop session) and emit
/// `agixt-extension-connected` so the agent-settings window can refresh.
async fn handle_deep_link_oauth_connect(
    app: &AppHandle,
    provider: Option<String>,
    code: Option<String>,
) {
    let provider = match provider.filter(|p| !p.is_empty()) {
        Some(p) => p,
        None => {
            tracing::warn!("agixt://oauth-connect missing provider");
            let _ = app.emit(
                "agixt-extension-connect-failed",
                serde_json::json!({ "detail": "missing provider" }),
            );
            return;
        }
    };
    let code = match code.filter(|c| !c.is_empty()) {
        Some(c) => c,
        None => {
            tracing::warn!("agixt://oauth-connect missing code");
            let _ = app.emit(
                "agixt-extension-connect-failed",
                serde_json::json!({ "provider": provider, "detail": "missing code" }),
            );
            return;
        }
    };
    let state = match app.try_state::<AppState>() {
        Some(s) => s,
        None => {
            tracing::warn!("oauth-connect deep link: no AppState");
            return;
        }
    };
    let (server_url, web_url, jwt) = {
        let s = state.settings.lock().await;
        (s.server_url.clone(), s.web_url.clone(), s.jwt.clone())
    };
    let jwt = match jwt {
        Some(j) => j,
        None => {
            tracing::warn!("oauth-connect: no JWT — user not signed in");
            let _ = app.emit(
                "agixt-extension-connect-failed",
                serde_json::json!({
                    "provider": provider,
                    "detail": "not signed in",
                }),
            );
            return;
        }
    };
    let slug = api::redirect_slug_for(&provider);
    let referrer = format!("{}/user/close/{}", web_url.trim_end_matches('/'), slug);
    let url = format!("{}/v1/oauth2/{}", server_url.trim_end_matches('/'), slug,);
    let client = match api::build_client() {
        Ok(c) => c,
        Err(e) => {
            tracing::warn!("oauth-connect build_client: {e}");
            let _ = app.emit(
                "agixt-extension-connect-failed",
                serde_json::json!({ "provider": provider, "detail": format!("client build: {e}") }),
            );
            return;
        }
    };
    let body = serde_json::json!({ "code": code, "referrer": referrer });
    let resp = client.post(&url).bearer_auth(&jwt).json(&body).send().await;
    let resp = match resp {
        Ok(r) => r,
        Err(e) => {
            tracing::warn!("oauth-connect POST failed: {e}");
            let _ = app.emit(
                "agixt-extension-connect-failed",
                serde_json::json!({ "provider": provider, "detail": format!("network: {e}") }),
            );
            return;
        }
    };
    let status = resp.status();
    let text = resp.text().await.unwrap_or_default();
    if !status.is_success() {
        // The close page treats `invalid_grant` as a benign duplicate (the
        // code was already redeemed), and so do we — emit a success event
        // so the UI doesn't strand the user.
        let benign = text.contains("invalid_grant") || text.contains("Invalid");
        if benign {
            tracing::info!(
                "oauth-connect: provider={} treated as success despite {status} (likely duplicate code)",
                provider
            );
            let _ = app.emit(
                "agixt-extension-connected",
                serde_json::json!({ "provider": provider }),
            );
            return;
        }
        tracing::warn!("oauth-connect: provider={} http {status}: {text}", provider);
        let _ = app.emit(
            "agixt-extension-connect-failed",
            serde_json::json!({
                "provider": provider,
                "detail": format!("HTTP {status}: {text}"),
            }),
        );
        return;
    }
    tracing::info!("oauth-connect: provider={} success", provider);
    let _ = app.emit(
        "agixt-extension-connected",
        serde_json::json!({ "provider": provider }),
    );
}

/// Called when a `agixt://login?token=<jwt>` deep link arrives. Validates
/// the token against the configured server's `/v1/user`, persists it to
/// settings, and notifies the front-end that auth completed so the chat
/// UI can swap in.
async fn handle_deep_link_login(app: &AppHandle, token: String) {
    tracing::info!("handle_deep_link_login: token len={}", token.len());
    let state = match app.try_state::<AppState>() {
        Some(s) => s,
        None => {
            tracing::warn!("deep link login: no AppState");
            return;
        }
    };
    let jwt = match extract_jwt(&token) {
        Some(j) => j,
        None => {
            tracing::warn!("deep link login: token didn't look like a JWT");
            return;
        }
    };
    let server_url = state.settings.lock().await.server_url.clone();
    // Verify by hitting /v1/user.
    let client = match api::build_client() {
        Ok(c) => c,
        Err(e) => {
            tracing::warn!("build_client: {e}");
            return;
        }
    };
    let url = format!("{}/v1/user", server_url.trim_end_matches('/'));
    let resp = client.get(&url).bearer_auth(&jwt).send().await;
    let resp = match resp {
        Ok(r) => r,
        Err(e) => {
            tracing::warn!("deep link login verify failed: {e}");
            return;
        }
    };
    if !resp.status().is_success() {
        tracing::warn!("deep link login: server rejected token: {}", resp.status());
        return;
    }
    let user: serde_json::Value = resp.json().await.unwrap_or_default();
    let email = user
        .get("email")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    {
        let mut s = state.settings.lock().await;
        s.jwt = Some(jwt);
        if email.is_some() {
            s.user_email = email;
        }
        let _ = state.store.save(&s).await;
    }
    let _ = app.emit("agixt-authenticated", ());
    tracing::info!("deep link login: success");
}

/// Try to pull a JWT out of a string that might be:
///   * the raw JWT (`eyJhbGci…`)
///   * a magic-link URL with `?token=…` or `?jwt=…`
///   * the URL-encoded `detail` field returned by `/v1/login`
fn extract_jwt(raw: &str) -> Option<String> {
    let trimmed = raw.trim();
    if trimmed.starts_with("eyJ") && trimmed.split('.').count() == 3 {
        return Some(trimmed.to_string());
    }
    // Try parse as URL with token param.
    let candidate = if trimmed.starts_with("http://") || trimmed.starts_with("https://") {
        trimmed.to_string()
    } else if trimmed.starts_with("?") {
        format!("http://x{trimmed}")
    } else {
        format!("http://x?{trimmed}")
    };
    if let Ok(url) = url::Url::parse(&candidate) {
        for (k, v) in url.query_pairs() {
            if k == "token" || k == "jwt" || k == "authorization" {
                let v = v.to_string();
                if v.starts_with("eyJ") {
                    return Some(v);
                }
            }
        }
        // fragment too
        if let Some(frag) = url.fragment() {
            for part in frag.split('&') {
                let mut it = part.splitn(2, '=');
                let k = it.next().unwrap_or("");
                let v = it.next().unwrap_or("");
                if (k == "token" || k == "jwt") && v.starts_with("eyJ") {
                    return Some(v.to_string());
                }
            }
        }
    }
    None
}

// --------------------------------------------------------------------------
// "Local" mode: localhost:7437 probe + one-click installer
// --------------------------------------------------------------------------

/// Probe `http://localhost:7437` and report whether an AGiXT instance
/// is already running. Used by the auth screen when the user picks the
/// "Local" service brand: a green check + Connect button if running,
/// otherwise the installer flow.
#[tauri::command]
async fn check_local_agixt() -> ToolResult<local_install::LocalAgixtStatus> {
    Ok(local_install::check_local_agixt().await)
}

/// Probe local hardware (CPU cores, RAM, GPUs/VRAM) and return both
/// the raw figures *and* the ezLocalai default-model recommendation.
/// Best-effort: missing signals degrade gracefully rather than erroring.
#[tauri::command]
async fn detect_hardware() -> ToolResult<hardware::HardwareInfo> {
    Ok(hardware::probe().await)
}

/// Default AGiXT install location (`$HOME/AGiXT`) so the frontend can
/// pre-fill the "install to" field without hardcoding paths in JS.
#[tauri::command]
fn default_install_path() -> ToolResult<String> {
    local_install::default_install_path()
        .map(|p| p.display().to_string())
        .map_err(ToolError::from)
}

/// Run the full local AGiXT install flow. Streams progress to the
/// frontend via the `local-install-progress` event channel; the
/// `Result` resolves only after the install finishes (success or
/// failure). The frontend should subscribe to the event channel
/// *before* invoking this command to avoid missing early lines.
#[tauri::command]
async fn install_agixt_local(
    app: AppHandle,
    args: local_install::InstallArgs,
) -> ToolResult<local_install::InstallResult> {
    local_install::run_install(app, args)
        .await
        .map_err(ToolError::from)
}

// --------------------------------------------------------------------------
// AGiXT REST helpers (proxied through Rust to keep JWT off the JS console)
// --------------------------------------------------------------------------

#[tauri::command]
async fn list_companies(state: State<'_, AppState>) -> ToolResult<Vec<api::CompanyInfo>> {
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    api::list_companies(&s.server_url, &jwt)
        .await
        .map_err(ToolError::from)
}

#[tauri::command]
async fn list_agents(state: State<'_, AppState>) -> ToolResult<Vec<api::AgentInfo>> {
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    api::list_agents(&s.server_url, &jwt)
        .await
        .map_err(ToolError::from)
}

#[tauri::command]
async fn list_conversations(
    state: State<'_, AppState>,
) -> ToolResult<Vec<api::ConversationSummary>> {
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    api::list_conversations(&s.server_url, &jwt)
        .await
        .map_err(ToolError::from)
}

#[tauri::command]
async fn select_conversation(
    state: State<'_, AppState>,
    id: String,
    name: String,
) -> ToolResult<()> {
    let mut s = state.settings.lock().await;
    s.conversation_id = Some(id);
    s.conversation_name = Some(name);
    state.store.save(&s).await.map_err(ToolError::from)?;
    Ok(())
}

/// Pull the message history for a conversation. Returns a flat list of
/// `{ id, role, message, timestamp }` records the JS chat renderer
/// can replay through its existing `ingest()` path.
#[tauri::command]
async fn get_conversation_history(
    state: State<'_, AppState>,
    conversation_id: String,
    limit: Option<u32>,
    page: Option<u32>,
) -> ToolResult<Vec<serde_json::Value>> {
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    api::get_conversation_history(
        &s.server_url,
        &jwt,
        &conversation_id,
        limit.unwrap_or(200),
        page.unwrap_or(1),
    )
    .await
    .map_err(ToolError::from)
}

#[tauri::command]
async fn new_conversation(
    state: State<'_, AppState>,
    name: String,
    force_new: Option<bool>,
) -> ToolResult<api::NewConversationResponse> {
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    let agent_name = s.agent_name.clone().unwrap_or_else(|| "XT".to_string());
    let conversation_name = if name.trim().is_empty() || name.trim() == "-" {
        agent_name.clone()
    } else {
        name.clone()
    };
    let force = force_new.unwrap_or(false);
    let company_id = s.company_id.clone().unwrap_or_default();
    let resp = match api::new_agent_dm_conversation(
        &s.server_url,
        &jwt,
        &agent_name,
        &company_id,
        &conversation_name,
        force,
    )
    .await
    {
        Ok(resp) => resp,
        Err(err) => {
            tracing::warn!(
                "new_conversation: agent DM create failed ({err:#}); falling back to legacy private conversation"
            );
            api::new_conversation(&s.server_url, &jwt, &agent_name, &conversation_name)
                .await
                .map_err(ToolError::from)?
        }
    };
    let mut cur = state.settings.lock().await;
    cur.conversation_id = Some(resp.id.clone());
    cur.conversation_name = resp
        .display_name
        .clone()
        .or_else(|| resp.name.clone())
        .or_else(|| Some(conversation_name));
    state.store.save(&cur).await.map_err(ToolError::from)?;
    Ok(resp)
}

#[derive(Debug, Deserialize)]
pub struct ChatStreamArgs {
    /// Client-generated stream id. JS attaches its Tauri listener before
    /// invoking `chat_send`, then passes the id here so early deltas cannot
    /// race ahead of the listener.
    #[serde(default)]
    pub stream_id: Option<String>,
    /// The new messages for this turn. For normal user prompts this is one
    /// user message. For OpenAI-shaped tool continuations this is only the
    /// new role:tool result messages.
    pub messages: Vec<chat_stream::ChatMessage>,
    pub conversation_name: String,
}

/// Streams a chat completion. Emits `chat-stream` Tauri events keyed by
/// `stream_id` that the JS layer subscribes to. Returns the stream id
/// the caller should listen on. When a client tool is requested, the JS
/// layer executes it locally and calls this command again with matching
/// `role: tool` results.
#[tauri::command]
async fn chat_send(
    app: AppHandle,
    state: State<'_, AppState>,
    args: ChatStreamArgs,
) -> ToolResult<String> {
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    let agent_name = s.agent_name.clone().unwrap_or_else(|| "XT".to_string());
    let server_url = s.server_url.clone();
    let voice = s.voice_enabled;
    let conversation_name = s
        .conversation_id
        .clone()
        .filter(|id| !id.trim().is_empty())
        .unwrap_or_else(|| args.conversation_name.clone());
    tracing::info!(
        "chat_send: convo='{}' messages={}",
        conversation_name,
        args.messages.len()
    );
    let tools = if s.allow_client_commands {
        client_tool_specs::for_current_platform()
    } else {
        Vec::new()
    };
    tracing::info!(
        "chat_send: agent='{}' server='{}' tools={} voice={}",
        agent_name,
        server_url,
        tools.len(),
        voice
    );
    let stream_id = args
        .stream_id
        .clone()
        .filter(|s| !s.trim().is_empty())
        .unwrap_or_else(|| uuid::Uuid::new_v4().to_string());
    let stream_id_for_thread = stream_id.clone();
    let app_for_thread = app.clone();

    tauri::async_runtime::spawn(async move {
        let app2 = app_for_thread.clone();
        let sid = stream_id_for_thread.clone();
        let result = chat_stream::stream_chat(
            &server_url,
            &jwt,
            &agent_name,
            &conversation_name,
            &args.messages,
            &tools,
            voice,
            move |ev| {
                let _ = app2.emit(
                    &format!("chat-stream:{}", sid),
                    serde_json::json!({ "stream_id": sid, "event": ev }),
                );
            },
        )
        .await;
        if let Err(e) = result {
            tracing::warn!("chat_send stream error: {e:#}");
            let _ = app_for_thread.emit(
                &format!("chat-stream:{}", stream_id_for_thread),
                serde_json::json!({
                    "stream_id": stream_id_for_thread,
                    "event": { "kind": "error", "data": { "message": format!("{e:#}") } }
                }),
            );
        }
    });

    Ok(stream_id)
}

#[derive(Debug, Deserialize)]
pub struct AgentVisionArgs {
    pub prompt: String,
    #[serde(default)]
    pub images: Vec<String>,
    #[serde(default)]
    pub use_smartest: bool,
}

/// Runs the configured agent's vision provider directly. This is used by
/// the local desktop vision-control loop so screenshot interpretation stays
/// a client-side tool concern instead of a special case in the main chat
/// pipeline.
#[tauri::command]
async fn agent_vision(
    state: State<'_, AppState>,
    args: AgentVisionArgs,
) -> ToolResult<api::VisionResponse> {
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    let agent_id = s.agent_id.clone().ok_or_else(|| ToolError {
        error: "no agent selected".into(),
    })?;
    api::agent_vision(
        &s.server_url,
        &jwt,
        &agent_id,
        &args.prompt,
        &args.images,
        args.use_smartest,
    )
    .await
    .map_err(ToolError::from)
}

#[derive(Debug, Serialize)]
pub struct ClientPlatformInfo {
    pub os: String,
    pub family: String,
    pub mobile: bool,
    pub desktop: bool,
    pub tools: Vec<String>,
}

#[tauri::command]
fn client_platform() -> ClientPlatformInfo {
    let platform = client_tool_specs::current_platform();
    let tools = client_tool_specs::for_platform(platform)
        .iter()
        .filter_map(|tool| tool["function"]["name"].as_str().map(str::to_string))
        .collect::<Vec<_>>();
    let mobile = client_tool_specs::is_mobile_platform(platform);
    ClientPlatformInfo {
        os: client_tool_specs::platform_id(platform).to_string(),
        family: if mobile { "mobile" } else { "desktop" }.to_string(),
        mobile,
        desktop: !mobile,
        tools,
    }
}

#[derive(Debug, Deserialize)]
pub struct DeviceOpenUrlArgs {
    pub url: String,
    #[serde(default)]
    pub with: Option<String>,
}

#[derive(Debug, Deserialize, Default)]
pub struct DeviceOpenAppArgs {
    #[serde(default)]
    pub name: Option<String>,
    #[serde(default)]
    pub url: Option<String>,
    #[serde(default, alias = "packageName", alias = "app_package")]
    pub package: Option<String>,
    #[serde(default)]
    pub package_name: Option<String>,
    #[serde(default, alias = "bundleId")]
    pub bundle_id: Option<String>,
}

#[derive(Debug, Deserialize, Default)]
pub struct DeviceOpenSettingsArgs {
    #[serde(default)]
    pub section: Option<String>,
    #[serde(default, alias = "package")]
    pub app_package: Option<String>,
    #[serde(default, alias = "bundleId")]
    pub bundle_id: Option<String>,
}

#[derive(Debug, Serialize)]
pub struct DeviceActionResult {
    pub success: bool,
    pub action: String,
    pub platform: String,
    pub url: Option<String>,
    pub message: String,
}

fn trimmed_arg(value: &Option<String>) -> Option<String> {
    value
        .as_deref()
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(str::to_string)
}

fn clean_device_url(raw: &str) -> ToolResult<String> {
    let url = raw.trim();
    if url.is_empty() {
        return Err(ToolError {
            error: "device URL is required".into(),
        });
    }
    if url.contains(['\n', '\r', '\0']) {
        return Err(ToolError {
            error: "device URL must be a single line".into(),
        });
    }
    if !url.contains(':') {
        return Err(ToolError {
            error: "device URL must include a scheme such as https:, spotify:, maps:, geo:, tel:, sms:, or mailto:".into(),
        });
    }
    Ok(url.to_string())
}

fn current_platform_name() -> String {
    client_tool_specs::platform_id(client_tool_specs::current_platform()).to_string()
}

fn open_device_url_with(
    app: &AppHandle,
    url: String,
    with: Option<String>,
    action: &str,
    detail: &str,
) -> ToolResult<DeviceActionResult> {
    app.opener()
        .open_url(url.clone(), with.filter(|value| !value.trim().is_empty()))
        .map_err(|e| ToolError {
            error: format!("open device URL {url}: {e}"),
        })?;
    Ok(DeviceActionResult {
        success: true,
        action: action.to_string(),
        platform: current_platform_name(),
        url: Some(url),
        message: detail.to_string(),
    })
}

fn compact_app_name(name: &str) -> String {
    name.trim()
        .to_ascii_lowercase()
        .chars()
        .filter(|ch| ch.is_ascii_alphanumeric())
        .collect::<String>()
}

fn known_mobile_app_url(
    name: &str,
    platform: client_tool_specs::ClientPlatform,
) -> Option<&'static str> {
    let normalized = compact_app_name(name);
    match normalized.as_str() {
        "spotify" => Some("spotify://"),
        "youtube" => Some("youtube://"),
        "maps" | "map" | "googlemaps" => {
            if platform == client_tool_specs::ClientPlatform::Ios {
                Some("maps://")
            } else {
                Some("geo:0,0")
            }
        }
        "mail" | "email" | "gmail" => Some("mailto:"),
        "phone" | "dialer" | "call" => Some("tel:"),
        "messages" | "message" | "sms" | "text" => Some("sms:"),
        "browser" | "web" | "chrome" | "safari" => Some("https://www.google.com"),
        "settings" | "preferences" => {
            if platform == client_tool_specs::ClientPlatform::Ios {
                Some("app-settings:")
            } else {
                None
            }
        }
        _ => None,
    }
}

fn known_android_package(name: &str) -> Option<&'static str> {
    match compact_app_name(name).as_str() {
        "spotify" => Some("com.spotify.music"),
        "youtube" => Some("com.google.android.youtube"),
        "maps" | "map" | "googlemaps" => Some("com.google.android.apps.maps"),
        "gmail" | "mail" | "email" => Some("com.google.android.gm"),
        "chrome" | "browser" | "web" => Some("com.android.chrome"),
        "messages" | "message" | "sms" | "text" => Some("com.google.android.apps.messaging"),
        "phone" | "dialer" | "call" => Some("com.google.android.dialer"),
        _ => None,
    }
}

fn explicit_android_package(args: &DeviceOpenAppArgs) -> Option<String> {
    trimmed_arg(&args.package).or_else(|| trimmed_arg(&args.package_name))
}

fn named_android_package(args: &DeviceOpenAppArgs) -> Option<String> {
    trimmed_arg(&args.name).and_then(|name| known_android_package(&name).map(str::to_string))
}

#[cfg(target_os = "android")]
fn recv_android_intent_result(
    rx: std::sync::mpsc::Receiver<Result<(), String>>,
    action: &str,
) -> ToolResult<()> {
    match rx.recv_timeout(Duration::from_secs(5)) {
        Ok(Ok(())) => Ok(()),
        Ok(Err(error)) => Err(ToolError { error }),
        Err(error) => Err(ToolError {
            error: format!("{action}: Android intent did not complete: {error}"),
        }),
    }
}

#[cfg(target_os = "android")]
fn android_launch_package(app: &AppHandle, package: &str) -> ToolResult<()> {
    use jni::objects::{JObject, JValue};

    let window = app
        .get_webview_window(MAIN_LABEL)
        .ok_or_else(|| ToolError {
            error: "main Android webview is not available".into(),
        })?;
    let package = package.to_string();
    let (tx, rx) = std::sync::mpsc::channel();
    window
        .with_webview(move |webview| {
            webview.jni_handle().exec(
                move |env: &mut jni::JNIEnv,
                      activity: &jni::objects::JObject,
                      _webview: &jni::objects::JObject| {
                    let result = (|| -> Result<(), String> {
                        let package_name = env
                            .new_string(&package)
                            .map_err(|e| format!("create Android package string: {e}"))?;
                        let package_obj = JObject::from(package_name);
                        let package_manager = env
                            .call_method(
                                activity,
                                "getPackageManager",
                                "()Landroid/content/pm/PackageManager;",
                                &[],
                            )
                            .map_err(|e| format!("getPackageManager: {e}"))?
                            .l()
                            .map_err(|e| format!("getPackageManager object: {e}"))?;
                        let intent = env
                            .call_method(
                                &package_manager,
                                "getLaunchIntentForPackage",
                                "(Ljava/lang/String;)Landroid/content/Intent;",
                                &[JValue::Object(&package_obj)],
                            )
                            .map_err(|e| format!("getLaunchIntentForPackage({package}): {e}"))?
                            .l()
                            .map_err(|e| format!("launch intent object: {e}"))?;
                        if intent.is_null() {
                            return Err(format!(
                                "Android package '{package}' is not installed or has no launch intent"
                            ));
                        }
                        env.call_method(
                            activity,
                            "startActivity",
                            "(Landroid/content/Intent;)V",
                            &[JValue::Object(&intent)],
                        )
                        .map_err(|e| format!("startActivity for package '{package}': {e}"))?;
                        Ok(())
                    })();
                    let _ = tx.send(result);
                },
            );
        })
        .map_err(|e| ToolError {
            error: format!("access Android webview for package launch: {e}"),
        })?;
    recv_android_intent_result(rx, "android_launch_package")
}

#[cfg(target_os = "android")]
fn android_start_intent(app: &AppHandle, action: &str, data_uri: Option<String>) -> ToolResult<()> {
    use jni::objects::{JObject, JValue};

    let window = app
        .get_webview_window(MAIN_LABEL)
        .ok_or_else(|| ToolError {
            error: "main Android webview is not available".into(),
        })?;
    let action = action.to_string();
    let (tx, rx) = std::sync::mpsc::channel();
    window
        .with_webview(move |webview| {
            webview.jni_handle().exec(
                move |env: &mut jni::JNIEnv,
                      activity: &jni::objects::JObject,
                      _webview: &jni::objects::JObject| {
                    let result = (|| -> Result<(), String> {
                        let action_string = env
                            .new_string(&action)
                            .map_err(|e| format!("create Android intent action string: {e}"))?;
                        let action_obj = JObject::from(action_string);
                        let intent = env
                            .new_object(
                                "android/content/Intent",
                                "(Ljava/lang/String;)V",
                                &[JValue::Object(&action_obj)],
                            )
                            .map_err(|e| format!("create Android intent '{action}': {e}"))?;
                        env.call_method(
                            &intent,
                            "addFlags",
                            "(I)Landroid/content/Intent;",
                            &[JValue::Int(0x10000000)],
                        )
                        .map_err(|e| format!("add Android intent flags: {e}"))?;

                        if let Some(data_uri) = data_uri {
                            let data_string = env
                                .new_string(&data_uri)
                                .map_err(|e| format!("create Android data URI string: {e}"))?;
                            let data_obj = JObject::from(data_string);
                            let uri_class = env
                                .find_class("android/net/Uri")
                                .map_err(|e| format!("find android.net.Uri: {e}"))?;
                            let uri = env
                                .call_static_method(
                                    uri_class,
                                    "parse",
                                    "(Ljava/lang/String;)Landroid/net/Uri;",
                                    &[JValue::Object(&data_obj)],
                                )
                                .map_err(|e| format!("parse Android data URI '{data_uri}': {e}"))?
                                .l()
                                .map_err(|e| format!("Android URI object: {e}"))?;
                            env.call_method(
                                &intent,
                                "setData",
                                "(Landroid/net/Uri;)Landroid/content/Intent;",
                                &[JValue::Object(&uri)],
                            )
                            .map_err(|e| format!("set Android intent data '{data_uri}': {e}"))?;
                        }

                        env.call_method(
                            activity,
                            "startActivity",
                            "(Landroid/content/Intent;)V",
                            &[JValue::Object(&intent)],
                        )
                        .map_err(|e| format!("start Android settings intent '{action}': {e}"))?;
                        Ok(())
                    })();
                    let _ = tx.send(result);
                },
            );
        })
        .map_err(|e| ToolError {
            error: format!("access Android webview for settings intent: {e}"),
        })?;
    recv_android_intent_result(rx, "android_start_intent")
}

#[cfg(target_os = "android")]
fn android_settings_action(section: Option<&str>) -> &'static str {
    match section.map(compact_app_name).as_deref() {
        Some("wifi") | Some("wireless") => "android.settings.WIFI_SETTINGS",
        Some("bluetooth") => "android.settings.BLUETOOTH_SETTINGS",
        Some("notifications") | Some("notification") => "android.settings.NOTIFICATION_SETTINGS",
        Some("privacy") => "android.settings.PRIVACY_SETTINGS",
        Some("location") | Some("gps") => "android.settings.LOCATION_SOURCE_SETTINGS",
        Some("accessibility") => "android.settings.ACCESSIBILITY_SETTINGS",
        Some("network") | Some("internet") => "android.settings.WIRELESS_SETTINGS",
        Some("battery") => "android.settings.BATTERY_SAVER_SETTINGS",
        Some("apps") | Some("applications") => "android.settings.APPLICATION_SETTINGS",
        _ => "android.settings.SETTINGS",
    }
}

fn resolve_device_app_url(args: &DeviceOpenAppArgs) -> ToolResult<String> {
    if let Some(url) = trimmed_arg(&args.url) {
        return clean_device_url(&url);
    }

    let platform = client_tool_specs::current_platform();
    if let Some(name) = trimmed_arg(&args.name) {
        if let Some(url) = known_mobile_app_url(&name, platform) {
            return clean_device_url(url);
        }
    }

    let package = trimmed_arg(&args.package).or_else(|| trimmed_arg(&args.package_name));
    if platform == client_tool_specs::ClientPlatform::Android {
        if let Some(package) = package {
            return Err(ToolError {
                error: format!(
                    "No deep link fallback is available for Android package '{package}'. Pass a deep link URL/app link to device_open_url, or use a known app name with device_open_app."
                ),
            });
        }
    }

    if platform == client_tool_specs::ClientPlatform::Ios {
        if let Some(bundle_id) = trimmed_arg(&args.bundle_id) {
            return Err(ToolError {
                error: format!(
                    "Opening iOS bundle id '{bundle_id}' directly is not allowed by iOS. Pass that app's URL scheme or universal link to device_open_url."
                ),
            });
        }
    }

    Err(ToolError {
        error: "device_open_app needs either a URL/deep link or a known app name such as Spotify, YouTube, Maps, Mail, Phone, Messages, Settings, or Browser.".into(),
    })
}

#[tauri::command]
async fn device_open_url(
    app: AppHandle,
    state: State<'_, AppState>,
    args: DeviceOpenUrlArgs,
) -> ToolResult<DeviceActionResult> {
    require_client_commands(&state).await?;
    let url = clean_device_url(&args.url)?;
    open_device_url_with(
        &app,
        url,
        args.with,
        "device_open_url",
        "Opened the URL on the user's device.",
    )
}

#[tauri::command]
async fn device_open_app(
    app: AppHandle,
    state: State<'_, AppState>,
    args: DeviceOpenAppArgs,
) -> ToolResult<DeviceActionResult> {
    require_client_commands(&state).await?;
    if client_tool_specs::current_platform() == client_tool_specs::ClientPlatform::Android {
        let package = explicit_android_package(&args).or_else(|| named_android_package(&args));
        if let Some(package) = package {
            #[cfg(not(target_os = "android"))]
            let _ = &package;
            #[cfg(target_os = "android")]
            match android_launch_package(&app, &package) {
                Ok(()) => {
                    let detail = trimmed_arg(&args.name)
                        .map(|name| {
                            format!("Requested the {name} app through Android package '{package}'.")
                        })
                        .unwrap_or_else(|| {
                            format!("Requested Android package '{package}' on the user's device.")
                        });
                    return Ok(DeviceActionResult {
                        success: true,
                        action: "device_open_app".to_string(),
                        platform: current_platform_name(),
                        url: None,
                        message: detail,
                    });
                }
                Err(error) => {
                    tracing::warn!(
                        "device_open_app: Android package launch failed for {package}: {}",
                        error.error
                    );
                }
            }
        }

        if matches!(
            trimmed_arg(&args.name)
                .as_deref()
                .map(compact_app_name)
                .as_deref(),
            Some("settings") | Some("preferences")
        ) {
            #[cfg(target_os = "android")]
            {
                android_start_intent(&app, android_settings_action(None), None)?;
                return Ok(DeviceActionResult {
                    success: true,
                    action: "device_open_app".to_string(),
                    platform: current_platform_name(),
                    url: None,
                    message: "Requested Android system settings on the user's device.".into(),
                });
            }
        }
    }

    let url = resolve_device_app_url(&args)?;
    let detail = trimmed_arg(&args.name)
        .map(|name| format!("Requested the {name} app on the user's device."))
        .unwrap_or_else(|| "Opened the requested app link on the user's device.".to_string());
    open_device_url_with(&app, url, None, "device_open_app", &detail)
}

fn resolve_device_settings_url(
    _app: &AppHandle,
    args: &DeviceOpenSettingsArgs,
) -> ToolResult<String> {
    let platform = client_tool_specs::current_platform();
    match platform {
        client_tool_specs::ClientPlatform::Ios => clean_device_url("app-settings:"),
        client_tool_specs::ClientPlatform::Android => {
            if let Some(package) = trimmed_arg(&args.app_package) {
                #[cfg(target_os = "android")]
                {
                    android_start_intent(
                        _app,
                        "android.settings.APPLICATION_DETAILS_SETTINGS",
                        Some(format!("package:{package}")),
                    )?;
                    return Ok(String::new());
                }
                #[cfg(not(target_os = "android"))]
                {
                    return clean_device_url(&format!("package:{package}"));
                }
            }
            #[cfg(target_os = "android")]
            {
                android_start_intent(_app, android_settings_action(args.section.as_deref()), None)?;
                Ok(String::new())
            }
            #[cfg(not(target_os = "android"))]
            {
                let section = trimmed_arg(&args.section).unwrap_or_else(|| "system".to_string());
                Err(ToolError {
                    error: format!(
                        "Opening Android settings section '{section}' needs native intent support on this build. Pass app_package for app-specific settings, or pass a device-supported settings deep link to device_open_url."
                    ),
                })
            }
        }
        client_tool_specs::ClientPlatform::Desktop => Err(ToolError {
            error: "device_open_settings is for mobile builds; use desktop_vision_control or shell_run on desktop.".into(),
        }),
    }
}

#[tauri::command]
async fn device_open_settings(
    app: AppHandle,
    state: State<'_, AppState>,
    args: DeviceOpenSettingsArgs,
) -> ToolResult<DeviceActionResult> {
    require_client_commands(&state).await?;
    let url = resolve_device_settings_url(&app, &args)?;
    if url.is_empty() {
        Ok(DeviceActionResult {
            success: true,
            action: "device_open_settings".to_string(),
            platform: current_platform_name(),
            url: None,
            message: "Requested device settings on the user's device.".into(),
        })
    } else {
        open_device_url_with(
            &app,
            url,
            None,
            "device_open_settings",
            "Requested device settings on the user's device.",
        )
    }
}

#[cfg(test)]
mod auth_tests {
    use super::extract_jwt;

    const JWT: &str = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature";

    #[test]
    fn raw_jwt_passes_through() {
        assert_eq!(extract_jwt(JWT), Some(JWT.to_string()));
        // Whitespace tolerated.
        assert_eq!(extract_jwt(&format!("  {JWT}\n")), Some(JWT.to_string()));
    }

    #[test]
    fn three_part_check_rejects_random_strings() {
        assert!(extract_jwt("hello world").is_none());
        assert!(
            extract_jwt("eyJfoo").is_none(),
            "two-part token must not match"
        );
    }

    #[test]
    fn extracts_from_magic_link_url() {
        let url = format!("https://app.example.com/user/close?token={JWT}");
        assert_eq!(extract_jwt(&url), Some(JWT.to_string()));
    }

    #[test]
    fn extracts_from_jwt_query_param_alias() {
        let url = format!("http://localhost:3437/?jwt={JWT}");
        assert_eq!(extract_jwt(&url), Some(JWT.to_string()));
    }

    #[test]
    fn extracts_from_url_fragment() {
        let url = format!("https://example.com/x#token={JWT}&foo=bar");
        assert_eq!(extract_jwt(&url), Some(JWT.to_string()));
    }

    #[test]
    fn extracts_from_bare_query_string() {
        let raw = format!("?token={JWT}");
        assert_eq!(extract_jwt(&raw), Some(JWT.to_string()));
        let raw = format!("token={JWT}&extra=1");
        assert_eq!(extract_jwt(&raw), Some(JWT.to_string()));
    }

    #[test]
    fn ignores_non_jwt_tokens() {
        let url = "https://example.com/?token=plaintext-not-a-jwt";
        assert!(extract_jwt(url).is_none());
    }
}

// --------------------------------------------------------------------------
// Local desktop automation
// --------------------------------------------------------------------------

#[derive(Debug, Deserialize, Default)]
pub struct VisionArgs {
    #[serde(default)]
    pub normalized: bool,
    #[serde(default)]
    pub coordinate_space: Option<String>,
    #[serde(default)]
    pub image_coordinates: bool,
    #[serde(default)]
    pub target_width: Option<u32>,
    #[serde(default)]
    pub target_height: Option<u32>,
    #[serde(default)]
    pub screen_width: Option<u32>,
    #[serde(default)]
    pub screen_height: Option<u32>,
    #[serde(default)]
    pub monitor_offset_x: Option<i32>,
    #[serde(default)]
    pub monitor_offset_y: Option<i32>,
}

impl From<VisionArgs> for automation::VisionContext {
    fn from(v: VisionArgs) -> Self {
        Self {
            normalized: v.normalized,
            coordinate_space: v.coordinate_space,
            image_coordinates: v.image_coordinates,
            target_width: v.target_width,
            target_height: v.target_height,
            screen_width: v.screen_width,
            screen_height: v.screen_height,
            monitor_offset_x: v.monitor_offset_x,
            monitor_offset_y: v.monitor_offset_y,
        }
    }
}

#[derive(Debug, Deserialize)]
pub struct ClickArgs {
    pub x: i32,
    pub y: i32,
    #[serde(default = "default_button")]
    pub button: String,
    #[serde(default = "default_click_type")]
    pub click_type: String,
    #[serde(default, flatten)]
    pub vision: VisionArgs,
}
fn default_button() -> String {
    "left".into()
}
fn default_click_type() -> String {
    "single".into()
}

#[derive(Debug, Serialize)]
pub struct ClickResult {
    pub x: i32,
    pub y: i32,
}

#[tauri::command]
async fn desktop_screenshot(
    state: State<'_, AppState>,
    monitor_index: Option<usize>,
    target_width: Option<u32>,
    target_height: Option<u32>,
) -> ToolResult<automation::ScreenshotResult> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || {
        automation::screenshot(monitor_index, target_width, target_height)
    })
    .await
    .map_err(|e| ToolError {
        error: format!("join: {e}"),
    })?
    .map_err(ToolError::from)
}

#[tauri::command]
async fn desktop_click(state: State<'_, AppState>, args: ClickArgs) -> ToolResult<ClickResult> {
    require_client_commands(&state).await?;
    let ClickArgs {
        x,
        y,
        button,
        click_type,
        vision,
    } = args;
    let ctx = automation::VisionContext::from(vision);
    let log_ctx = ctx.clone();
    let log_button = button.clone();
    let log_click_type = click_type.clone();
    let (rx, ry) =
        tokio::task::spawn_blocking(move || automation::click(x, y, &button, &click_type, &ctx))
            .await
            .map_err(|e| ToolError {
                error: format!("join: {e}"),
            })?
            .map_err(ToolError::from)?;
    tracing::info!(
        "desktop_click: raw=({}, {}) resolved=({}, {}) button={} click_type={} vision={:?}",
        x,
        y,
        rx,
        ry,
        log_button,
        log_click_type,
        log_ctx
    );
    Ok(ClickResult { x: rx, y: ry })
}

#[derive(Debug, Deserialize)]
pub struct MoveArgs {
    pub x: i32,
    pub y: i32,
    #[serde(default, flatten)]
    pub vision: VisionArgs,
}

#[tauri::command]
async fn desktop_move(state: State<'_, AppState>, args: MoveArgs) -> ToolResult<ClickResult> {
    require_client_commands(&state).await?;
    let ctx = automation::VisionContext::from(args.vision);
    let (rx, ry) =
        tokio::task::spawn_blocking(move || automation::move_mouse(args.x, args.y, &ctx))
            .await
            .map_err(|e| ToolError {
                error: format!("join: {e}"),
            })?
            .map_err(ToolError::from)?;
    Ok(ClickResult { x: rx, y: ry })
}

#[derive(Debug, Deserialize)]
pub struct DragArgs {
    pub from_x: i32,
    pub from_y: i32,
    pub to_x: i32,
    pub to_y: i32,
    #[serde(default = "default_button")]
    pub button: String,
    #[serde(default, flatten)]
    pub vision: VisionArgs,
}

#[derive(Debug, Serialize)]
pub struct DragResult {
    pub from_x: i32,
    pub from_y: i32,
    pub to_x: i32,
    pub to_y: i32,
}

#[tauri::command]
async fn desktop_drag(state: State<'_, AppState>, args: DragArgs) -> ToolResult<DragResult> {
    require_client_commands(&state).await?;
    let DragArgs {
        from_x,
        from_y,
        to_x,
        to_y,
        button,
        vision,
    } = args;
    let ctx = automation::VisionContext::from(vision);
    let ((fx, fy), (tx, ty)) = tokio::task::spawn_blocking(move || {
        automation::drag(from_x, from_y, to_x, to_y, &button, &ctx)
    })
    .await
    .map_err(|e| ToolError {
        error: format!("join: {e}"),
    })?
    .map_err(ToolError::from)?;
    Ok(DragResult {
        from_x: fx,
        from_y: fy,
        to_x: tx,
        to_y: ty,
    })
}

#[tauri::command]
async fn desktop_scroll(
    state: State<'_, AppState>,
    amount: i32,
    axis: Option<String>,
) -> ToolResult<()> {
    require_client_commands(&state).await?;
    let ax = axis.unwrap_or_else(|| "vertical".into());
    tokio::task::spawn_blocking(move || automation::scroll(amount, &ax))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

#[tauri::command]
async fn desktop_type(
    state: State<'_, AppState>,
    text: Option<String>,
    keys: Option<Vec<String>>,
) -> ToolResult<()> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || automation::keyboard(text, keys))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

async fn require_client_commands(state: &State<'_, AppState>) -> ToolResult<()> {
    let s = state.settings.lock().await;
    if !s.allow_client_commands {
        return Err(ToolError {
            error: "client commands are disabled in settings".into(),
        });
    }
    Ok(())
}

// --------------------------------------------------------------------------
// Local filesystem ops on the user's machine
// --------------------------------------------------------------------------

#[tauri::command]
async fn fs_read(state: State<'_, AppState>, path: String) -> ToolResult<filesystem::ReadResult> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || filesystem::read(&path))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

#[derive(Debug, Deserialize)]
pub struct WriteFileArgs {
    pub path: String,
    pub content: String,
    #[serde(default)]
    pub encoding: Option<String>,
    #[serde(default)]
    pub create_dirs: bool,
}

#[tauri::command]
async fn fs_write(
    state: State<'_, AppState>,
    args: WriteFileArgs,
) -> ToolResult<filesystem::WriteResult> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || {
        filesystem::write(
            &args.path,
            &args.content,
            args.encoding.as_deref(),
            args.create_dirs,
        )
    })
    .await
    .map_err(|e| ToolError {
        error: format!("join: {e}"),
    })?
    .map_err(ToolError::from)
}

#[tauri::command]
async fn fs_append(
    state: State<'_, AppState>,
    args: WriteFileArgs,
) -> ToolResult<filesystem::WriteResult> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || {
        filesystem::append(&args.path, &args.content, args.encoding.as_deref())
    })
    .await
    .map_err(|e| ToolError {
        error: format!("join: {e}"),
    })?
    .map_err(ToolError::from)
}

#[derive(Debug, Deserialize)]
pub struct EditFileArgs {
    pub path: String,
    pub edits: Vec<filesystem::EditOp>,
}

#[tauri::command]
async fn fs_edit(
    state: State<'_, AppState>,
    args: EditFileArgs,
) -> ToolResult<filesystem::WriteResult> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || filesystem::edit(&args.path, &args.edits))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

#[tauri::command]
async fn fs_list(state: State<'_, AppState>, path: String) -> ToolResult<Vec<filesystem::FsEntry>> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || filesystem::list(&path))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

#[tauri::command]
async fn fs_stat(state: State<'_, AppState>, path: String) -> ToolResult<filesystem::FsStat> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || filesystem::stat(&path))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

#[derive(Debug, Deserialize)]
pub struct MkdirArgs {
    pub path: String,
    #[serde(default = "default_true")]
    pub parents: bool,
}
fn default_true() -> bool {
    true
}

#[tauri::command]
async fn fs_mkdir(state: State<'_, AppState>, args: MkdirArgs) -> ToolResult<()> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || filesystem::mkdir(&args.path, args.parents))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

#[derive(Debug, Deserialize)]
pub struct DeleteArgs {
    pub path: String,
    #[serde(default)]
    pub recursive: bool,
}

#[tauri::command]
async fn fs_delete(state: State<'_, AppState>, args: DeleteArgs) -> ToolResult<()> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || filesystem::delete(&args.path, args.recursive))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

#[derive(Debug, Deserialize)]
pub struct RenameArgs {
    pub from: String,
    pub to: String,
    #[serde(default)]
    pub overwrite: bool,
}

#[tauri::command]
async fn fs_rename(state: State<'_, AppState>, args: RenameArgs) -> ToolResult<()> {
    require_client_commands(&state).await?;
    tokio::task::spawn_blocking(move || filesystem::rename(&args.from, &args.to, args.overwrite))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

// --------------------------------------------------------------------------
// Workspace bridge: user disk ↔ AGiXT conversation workspace
// --------------------------------------------------------------------------

#[derive(Debug, Serialize)]
pub struct UploadResult {
    pub local_path: String,
    pub workspace_path: Option<String>,
    pub bytes: u64,
    pub server_response: serde_json::Value,
}

#[tauri::command]
async fn workspace_upload_local(
    state: State<'_, AppState>,
    local_path: String,
    workspace_path: Option<String>,
) -> ToolResult<UploadResult> {
    require_client_commands(&state).await?;
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    let convo = s.conversation_id.clone().ok_or_else(|| ToolError {
        error: "no active conversation".into(),
    })?;

    let path_clone = local_path.clone();
    let bytes = tokio::task::spawn_blocking(move || std::fs::read(&path_clone))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(|e| ToolError {
            error: format!("read {local_path}: {e}"),
        })?;
    let size = bytes.len() as u64;

    let file_name = std::path::Path::new(&local_path)
        .file_name()
        .map(|n| n.to_string_lossy().to_string())
        .unwrap_or_else(|| "upload.bin".to_string());

    let server_response = api::workspace_upload(
        &s.server_url,
        &jwt,
        &convo,
        &file_name,
        bytes,
        workspace_path.as_deref(),
    )
    .await
    .map_err(ToolError::from)?;

    Ok(UploadResult {
        local_path,
        workspace_path,
        bytes: size,
        server_response,
    })
}

#[derive(Debug, Serialize)]
pub struct DownloadResult {
    pub workspace_path: String,
    pub local_path: String,
    pub bytes: u64,
}

#[tauri::command]
async fn workspace_download_to_local(
    state: State<'_, AppState>,
    workspace_path: String,
    local_path: String,
    overwrite: Option<bool>,
) -> ToolResult<DownloadResult> {
    require_client_commands(&state).await?;
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    let convo = s.conversation_id.clone().ok_or_else(|| ToolError {
        error: "no active conversation".into(),
    })?;

    let bytes = api::workspace_download(&s.server_url, &jwt, &convo, &workspace_path)
        .await
        .map_err(ToolError::from)?;
    let len = bytes.len() as u64;

    let local_p = filesystem::resolve(&local_path, None).map_err(ToolError::from)?;
    if local_p.exists() && !overwrite.unwrap_or(false) {
        return Err(ToolError {
            error: format!(
                "local path exists and overwrite=false: {}",
                local_p.display()
            ),
        });
    }
    let local_p_str = local_p.display().to_string();
    let bytes_clone = bytes.clone();
    let local_clone = local_p_str.clone();
    tokio::task::spawn_blocking(move || std::fs::write(&local_clone, &bytes_clone))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(|e| ToolError {
            error: format!("write {local_p_str}: {e}"),
        })?;

    Ok(DownloadResult {
        workspace_path,
        local_path: local_p.display().to_string(),
        bytes: len,
    })
}

#[tauri::command]
async fn workspace_list(
    state: State<'_, AppState>,
    sub_path: Option<String>,
) -> ToolResult<Vec<api::WorkspaceItem>> {
    let s = state.settings.lock().await.clone();
    let jwt = s.jwt.clone().ok_or_else(|| ToolError {
        error: "not logged in".into(),
    })?;
    let convo = s.conversation_id.clone().ok_or_else(|| ToolError {
        error: "no active conversation".into(),
    })?;
    api::workspace_list(&s.server_url, &jwt, &convo, sub_path.as_deref())
        .await
        .map_err(ToolError::from)
}

// --------------------------------------------------------------------------
// Background terminal sessions (PTY-backed shells the agent can drive)
// --------------------------------------------------------------------------

#[derive(Debug, Deserialize, Default)]
pub struct OpenTerminalArgs {
    #[serde(default)]
    pub shell: Option<String>,
    #[serde(default)]
    pub cwd: Option<String>,
    #[serde(default)]
    pub cols: Option<u16>,
    #[serde(default)]
    pub rows: Option<u16>,
}

#[tauri::command]
async fn shell_run(
    state: State<'_, AppState>,
    command: String,
    timeout_ms: Option<u64>,
) -> ToolResult<terminal::ShellRunResult> {
    require_client_commands(&state).await?;
    terminal::shell_run(command, timeout_ms.unwrap_or(8_000))
        .await
        .map_err(ToolError::from)
}

#[derive(Debug, Serialize)]
pub struct SudoStatus {
    pub authenticated: bool,
    pub remembered: bool,
}

fn sudo_error_from_result(result: &terminal::ShellRunResult) -> String {
    let detail = if !result.stderr.trim().is_empty() {
        result.stderr.trim()
    } else if !result.stdout.trim().is_empty() {
        result.stdout.trim()
    } else {
        "sudo did not return a diagnostic"
    };
    format!("{detail}")
}

async fn restart_sudo_keepalive(state: &State<'_, AppState>) {
    let mut keepalive = state.sudo_keepalive.lock().await;
    if let Some(handle) = keepalive.take() {
        handle.abort();
    }
    *keepalive = Some(tokio::spawn(async {
        loop {
            tokio::time::sleep(Duration::from_secs(60)).await;
            match terminal::sudo_refresh_or_restore().await {
                Ok(result) if result.exit_code == 0 => {}
                Ok(result) => {
                    tracing::warn!(
                        "sudo keepalive failed with exit_code={}: {}",
                        result.exit_code,
                        sudo_error_from_result(&result)
                    );
                    break;
                }
                Err(e) => {
                    tracing::warn!("sudo keepalive failed: {e:#}");
                    break;
                }
            }
        }
    }));
}

#[tauri::command]
async fn sudo_status(state: State<'_, AppState>) -> ToolResult<SudoStatus> {
    require_client_commands(&state).await?;
    let result = terminal::sudo_refresh_or_restore()
        .await
        .map_err(ToolError::from)?;
    let remembered = terminal::sudo_password_is_stored()
        .await
        .map_err(ToolError::from)?;
    if result.exit_code == 0 {
        restart_sudo_keepalive(&state).await;
    }
    Ok(SudoStatus {
        authenticated: result.exit_code == 0,
        remembered,
    })
}

#[tauri::command]
async fn sudo_auth(state: State<'_, AppState>, password: String) -> ToolResult<SudoStatus> {
    require_client_commands(&state).await?;
    if password.is_empty() {
        return Err(ToolError {
            error: "sudo password is required".into(),
        });
    }

    let result = terminal::sudo_validate(password.clone())
        .await
        .map_err(ToolError::from)?;
    if result.exit_code != 0 {
        return Err(ToolError {
            error: format!(
                "sudo authentication failed: {}",
                sudo_error_from_result(&result)
            ),
        });
    }

    terminal::sudo_store_password(password)
        .await
        .map_err(ToolError::from)?;
    restart_sudo_keepalive(&state).await;

    Ok(SudoStatus {
        authenticated: true,
        remembered: true,
    })
}

#[tauri::command]
async fn sudo_clear(state: State<'_, AppState>) -> ToolResult<SudoStatus> {
    require_client_commands(&state).await?;
    let mut keepalive = state.sudo_keepalive.lock().await;
    if let Some(handle) = keepalive.take() {
        handle.abort();
    }
    drop(keepalive);
    terminal::sudo_delete_stored_password()
        .await
        .map_err(ToolError::from)?;
    terminal::sudo_clear().await.map_err(ToolError::from)?;
    Ok(SudoStatus {
        authenticated: false,
        remembered: false,
    })
}

#[tauri::command]
async fn sudo_run(
    state: State<'_, AppState>,
    command: String,
    timeout_ms: Option<u64>,
) -> ToolResult<terminal::ShellRunResult> {
    require_client_commands(&state).await?;
    let result = terminal::sudo_run_with_stored_password(command, timeout_ms.unwrap_or(600_000))
        .await
        .map_err(ToolError::from)?;
    if terminal::sudo_auth_required(&result) {
        return Err(ToolError {
            error: "SUDO_AUTH_REQUIRED: Open AGiXT Desktop settings, authenticate Privileged Commands once so AGiXT Desktop can remember the sudo password, then retry the sudo_run tool."
                .into(),
        });
    }
    Ok(result)
}

#[tauri::command]
async fn terminal_open(
    state: State<'_, AppState>,
    args: Option<OpenTerminalArgs>,
) -> ToolResult<terminal::SessionInfo> {
    require_client_commands(&state).await?;
    let mgr = state.terminals.clone();
    let a = args.unwrap_or_default();
    tokio::task::spawn_blocking(move || mgr.open(a.shell, a.cwd, a.cols, a.rows))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

#[tauri::command]
async fn terminal_list(state: State<'_, AppState>) -> ToolResult<Vec<terminal::SessionInfo>> {
    Ok(state.terminals.list())
}

#[tauri::command]
async fn terminal_close(state: State<'_, AppState>, session_id: String) -> ToolResult<()> {
    state.terminals.close(&session_id).map_err(ToolError::from)
}

#[tauri::command]
async fn terminal_exec(
    state: State<'_, AppState>,
    session_id: String,
    command: String,
    idle_ms: Option<u64>,
    timeout_ms: Option<u64>,
) -> ToolResult<terminal::ExecResult> {
    require_client_commands(&state).await?;
    let mgr = state.terminals.clone();
    let idle = idle_ms.unwrap_or(250);
    let timeout = timeout_ms.unwrap_or(15_000);
    tokio::task::spawn_blocking(move || mgr.exec(&session_id, &command, idle, timeout))
        .await
        .map_err(|e| ToolError {
            error: format!("join: {e}"),
        })?
        .map_err(ToolError::from)
}

#[tauri::command]
async fn terminal_send_input(
    state: State<'_, AppState>,
    session_id: String,
    data: String,
) -> ToolResult<()> {
    require_client_commands(&state).await?;
    state
        .terminals
        .write(&session_id, data.as_bytes())
        .map_err(ToolError::from)
}

#[tauri::command]
async fn terminal_read(
    state: State<'_, AppState>,
    session_id: String,
    offset: Option<u64>,
) -> ToolResult<terminal::ReadResult> {
    state
        .terminals
        .read(&session_id, offset.unwrap_or(0))
        .map_err(ToolError::from)
}

#[tauri::command]
async fn terminal_resize(
    state: State<'_, AppState>,
    session_id: String,
    cols: u16,
    rows: u16,
) -> ToolResult<()> {
    state
        .terminals
        .resize(&session_id, cols, rows)
        .map_err(ToolError::from)
}

#[tauri::command]
async fn terminal_signal(
    state: State<'_, AppState>,
    session_id: String,
    signal: String,
) -> ToolResult<()> {
    require_client_commands(&state).await?;
    state
        .terminals
        .signal(&session_id, &signal)
        .map_err(ToolError::from)
}

// --------------------------------------------------------------------------
// Window management — sidebar dock + floating toggle
// --------------------------------------------------------------------------

/// Stamp `_GTK_APPLICATION_ID` on the X11 window. GNOME Shell's window
/// tracker uses this property as the most reliable signal for window-to-
/// `.desktop`-file association — when present, mutter looks up
/// `<id>.desktop` directly instead of falling back to the much fuzzier
/// `WM_CLASS` / `Exec=` heuristics. Without it (Tauri's GTK backend never
/// sets one), Ubuntu Dock cannot reliably attach the running window to
/// the dash entry, so the app appears to be missing from the taskbar.
///
/// Match value `agixt` to the `agixt.desktop` filename installed by
/// `install_linux_launcher()`.
#[cfg(target_os = "linux")]
fn set_gtk_application_id(win: &WebviewWindow) {
    use gtk::prelude::*;
    let Ok(gw) = win.gtk_window() else {
        tracing::warn!("set_gtk_application_id: gtk_window() failed");
        return;
    };
    // Force realization so the underlying X11 window exists, then we
    // can stamp `_GTK_APPLICATION_ID` on it.
    gw.realize();
    let Some(gdk_win) = gw.window() else {
        tracing::warn!("set_gtk_application_id: gtk_window has no gdk::Window after realize()");
        return;
    };
    let prop = gdk::Atom::intern("_GTK_APPLICATION_ID");
    let utf8 = gdk::Atom::intern("UTF8_STRING");
    let id = b"agixt";
    gdk::property_change(
        &gdk_win,
        &prop,
        &utf8,
        8,
        gdk::PropMode::Replace,
        gdk::ChangeData::UChars(id),
    );
    tracing::info!("set_gtk_application_id: stamped _GTK_APPLICATION_ID=agixt");
}

#[cfg(all(not(mobile), not(target_os = "linux")))]
fn set_gtk_application_id(_: &WebviewWindow) {}

/// On Linux/X11 with mutter (GNOME), normal `_NET_WM_WINDOW_TYPE_NORMAL`
/// windows still participate in tile-snap and edge-tiling. We need to
/// promote our popover to a non-tilable window type. `Utility` is the
/// closest match — Slack and Discord use the same hint for their popups.
#[cfg(target_os = "linux")]
fn promote_to_utility(win: &WebviewWindow) {
    use gdk::WindowTypeHint;
    use gtk::prelude::*;
    if let Ok(gw) = win.gtk_window() {
        gw.set_type_hint(WindowTypeHint::Utility);
        gw.set_skip_taskbar_hint(true);
        gw.set_skip_pager_hint(true);
        gw.set_keep_above(true);
        gw.set_decorated(false);
    }
}

#[cfg(all(not(mobile), not(target_os = "linux")))]
fn promote_to_utility(_: &WebviewWindow) {}

/// Inverse of `promote_to_utility`: turn the popover back into a normal
/// X11 window so mutter includes it in the taskbar/alt-tab list and lets
/// the user tile it like any other app. We use this when entering the
/// workspace editor (set_workspace_window_mode(true)).
#[cfg(target_os = "linux")]
fn demote_to_normal(win: &WebviewWindow) {
    use gdk::WindowTypeHint;
    use gtk::prelude::*;
    if let Ok(gw) = win.gtk_window() {
        gw.set_type_hint(WindowTypeHint::Normal);
        gw.set_skip_taskbar_hint(false);
        gw.set_skip_pager_hint(false);
        gw.set_keep_above(false);
        gw.set_decorated(true);
        // Without an explicit icon list, GNOME's overview / dash-to-dock
        // / taskbar shows a generic placeholder for the window. Load the
        // bundled 128px PNG and attach it so the window picks up the
        // AGiXT logo in switcher / alt-tab / taskbar.
        if let Some(pixbuf) = load_app_pixbuf() {
            gw.set_icon(Some(&pixbuf));
        }
    }
    // We deliberately *don't* re-stamp `_GTK_APPLICATION_ID` here:
    // `demote_to_normal` is invoked from `set_workspace_window_mode`,
    // which runs on a tokio worker thread, and GDK panics if touched
    // off the main thread. The property is set once at startup (in the
    // Tauri `.setup` callback, which is on the main thread) and X11
    // preserves it across hide → show cycles since the underlying
    // X11 window isn't re-created.
    // Tauri's own icon hook also writes _NET_WM_ICON via the wry
    // backend; call it too so any non-GTK consumers (eg. Window
    // List in some panels) pick it up.
    if let Ok(image) = Image::from_bytes(APP_ICON_BYTES) {
        let _ = win.set_icon(image);
    }
}

#[cfg(all(not(mobile), not(target_os = "linux")))]
fn demote_to_normal(win: &WebviewWindow) {
    if let Ok(image) = Image::from_bytes(APP_ICON_BYTES) {
        let _ = win.set_icon(image);
    }
}

/// 128px AGiXT logo, embedded at compile time so we don't need a
/// runtime file lookup. Used as the window icon in decorated mode.
#[cfg(not(mobile))]
const APP_ICON_BYTES: &[u8] = include_bytes!("../icons/128x128.png");

#[cfg(target_os = "linux")]
fn load_app_pixbuf() -> Option<gtk::gdk_pixbuf::Pixbuf> {
    use gtk::gdk_pixbuf::PixbufLoader;
    use gtk::prelude::*;
    let loader = PixbufLoader::new();
    loader.write(APP_ICON_BYTES).ok()?;
    loader.close().ok()?;
    loader.pixbuf()
}

/// WebKitGTK does not show a browser-style permission prompt for
/// getUserMedia in this app shell, so approve microphone/camera capture
/// requests from our bundled UI explicitly.
#[cfg(target_os = "linux")]
fn configure_media_capture(win: &WebviewWindow) {
    let label = win.label().to_string();
    if let Err(e) = win.with_webview(move |webview| {
        use webkit2gtk::glib::prelude::*;
        use webkit2gtk::{
            PermissionRequestExt, SettingsExt, UserMediaPermissionRequestExt, WebViewExt,
        };

        let inner = webview.inner();
        if let Some(settings) = inner.settings() {
            settings.set_enable_media(true);
            settings.set_enable_media_stream(true);
            settings.set_enable_webrtc(true);
        }

        inner.connect_permission_request(move |_webview, request| {
            let Some(media_request) =
                request.dynamic_cast_ref::<webkit2gtk::UserMediaPermissionRequest>()
            else {
                return false;
            };

            let wants_audio = media_request.is_for_audio_device();
            let wants_video = media_request.is_for_video_device();
            if wants_audio || wants_video {
                tracing::info!(
                    "allowing WebKit user-media request for {label}: audio={wants_audio}, video={wants_video}"
                );
                request.allow();
                true
            } else {
                false
            }
        });
    }) {
        tracing::warn!("configure_media_capture with_webview err: {e}");
    }
}

#[cfg(all(not(mobile), not(target_os = "linux")))]
fn configure_media_capture(_: &WebviewWindow) {}

/// Linux-specific hide via gtk_widget_hide on the underlying GtkWindow.
/// Tauri 2's `WebviewWindow::hide` and `minimize` have both proven
/// unreliable on this Ubuntu+mutter+AppIndicator stack — the former no-ops
/// re-show on UTILITY windows, the latter doesn't actually unmap. Going
/// straight to GTK gives us the canonical path that always works.
#[cfg(target_os = "linux")]
fn linux_hide(win: &WebviewWindow) -> bool {
    use gtk::prelude::*;
    match win.gtk_window() {
        Ok(gw) => {
            gw.hide();
            true
        }
        Err(e) => {
            tracing::warn!("linux_hide gtk_window err: {e}");
            false
        }
    }
}

#[cfg(target_os = "linux")]
fn linux_show(win: &WebviewWindow) -> bool {
    use gtk::prelude::*;
    match win.gtk_window() {
        Ok(gw) => {
            gw.show_all();
            gw.present();
            true
        }
        Err(e) => {
            tracing::warn!("linux_show gtk_window err: {e}");
            false
        }
    }
}

#[cfg(not(target_os = "linux"))]
#[allow(dead_code)]
fn linux_hide(_: &WebviewWindow) -> bool {
    false
}
#[cfg(not(target_os = "linux"))]
#[allow(dead_code)]
fn linux_show(_: &WebviewWindow) -> bool {
    false
}

/// `WebviewWindow::is_visible` reports the *requested* state, which
/// disagrees with reality after our gtk-direct hide on Linux. Check the
/// gtk visibility AND the X11 mapping state instead.
#[cfg(target_os = "linux")]
fn is_actually_visible(win: &WebviewWindow) -> bool {
    use gtk::prelude::*;
    let tauri_says = win.is_visible().unwrap_or(false);
    let gtk_says = win
        .gtk_window()
        .ok()
        .map(|gw| gw.is_visible())
        .unwrap_or(false);
    let mapped = win
        .gtk_window()
        .ok()
        .and_then(|gw| gw.window())
        .map(|w| w.is_visible())
        .unwrap_or(false);
    tracing::info!(
        "is_actually_visible: tauri={tauri_says} gtk_widget={gtk_says} gdk_mapped={mapped}"
    );
    // Trust the GDK window mapping state — that's the X11 reality.
    mapped
}

#[cfg(not(target_os = "linux"))]
fn is_actually_visible(win: &WebviewWindow) -> bool {
    win.is_visible().unwrap_or(false)
}

/// Position the popover window so it sits next to the tray icon, like
/// Discord / Slack / most tray-driven chat apps.
///
/// `tray_rect` is the physical-pixel rectangle of the tray icon, supplied
/// by `TrayIconEvent::Click`. We pick the screen edge nearest the tray,
/// then offset the panel by `POPOVER_MARGIN` so it doesn't overlap the
/// icon itself. If the tray rect is unavailable (some Linux DEs don't
/// report it) we fall back to the right edge of the primary monitor —
/// the same place a top-right tray would put us.
#[cfg(not(mobile))]
fn position_popover(
    app: &AppHandle,
    win: &WebviewWindow,
    tray_rect: Option<(i32, i32, i32, i32)>,
) -> ToolResult<()> {
    let monitor = win
        .current_monitor()
        .ok()
        .flatten()
        .or_else(|| app.primary_monitor().ok().flatten())
        .ok_or_else(|| ToolError {
            error: "no monitor".into(),
        })?;

    let scale = monitor.scale_factor();
    let mon_pos = monitor.position();
    let mon_size = monitor.size();
    let mon_right = mon_pos.x + mon_size.width as i32;
    let mon_bottom = mon_pos.y + mon_size.height as i32;

    // Honor whatever size the user has dragged the window to, capped
    // to sensible min/max. We only set the size when it's outside the
    // bounds. set_resizable(true) is left on so the user can keep
    // resizing freely once the window is shown.
    let _ = win.set_resizable(true);
    let min_w = 320.0_f64;
    let min_h = 420.0_f64;
    let _ = win.set_min_size(Some(LogicalSize::new(min_w, min_h)));
    let _ = win.set_max_size::<LogicalSize<f64>>(None);
    let current = win
        .inner_size()
        .ok()
        .map(|sz| (sz.width as f64 / scale, sz.height as f64 / scale));
    let (logical_w, logical_h) = match current {
        Some((w, h)) if w >= min_w && h >= min_h => (w, h),
        _ => (PANEL_WIDTH, PANEL_HEIGHT),
    };
    if current.is_none()
        || current
            .map(|(w, h)| (w - logical_w).abs() > 0.5 || (h - logical_h).abs() > 0.5)
            .unwrap_or(true)
    {
        let _ = win.set_size(LogicalSize::new(logical_w, logical_h));
    }

    let phys_w = (logical_w * scale).round() as i32;
    let phys_h = (logical_h * scale).round() as i32;
    let margin = (POPOVER_MARGIN * scale).round() as i32;

    let (phys_x, phys_y) = match tray_rect {
        Some((tx, ty, tw, th)) => {
            // Heuristic: stand the panel on whichever edge of the tray is
            // closer to the inside of the monitor. Tray on top → panel
            // drops down; tray on bottom → panel rises up; tray on right →
            // panel slides left; tray on left → panel slides right.
            let tray_cx = tx + tw / 2;
            let tray_cy = ty + th / 2;
            let mon_cx = mon_pos.x + mon_size.width as i32 / 2;
            let mon_cy = mon_pos.y + mon_size.height as i32 / 2;

            let dist_top = (ty - mon_pos.y).abs();
            let dist_bottom = (mon_bottom - (ty + th)).abs();
            let dist_left = (tx - mon_pos.x).abs();
            let dist_right = (mon_right - (tx + tw)).abs();

            // Edge with the smallest distance is the one the tray hugs.
            let nearest = [
                ("top", dist_top),
                ("bottom", dist_bottom),
                ("left", dist_left),
                ("right", dist_right),
            ]
            .into_iter()
            .min_by_key(|&(_, d)| d)
            .map(|(name, _)| name)
            .unwrap_or("top");

            let (mut x, mut y) = match nearest {
                "top" => (tray_cx - phys_w / 2, ty + th + margin),
                "bottom" => (tray_cx - phys_w / 2, ty - phys_h - margin),
                "left" => (tx + tw + margin, tray_cy - phys_h / 2),
                "right" => (tx - phys_w - margin, tray_cy - phys_h / 2),
                _ => (mon_cx - phys_w / 2, mon_cy - phys_h / 2),
            };
            // Clamp to the monitor so a partial tray rect (or weird DE
            // panel layout) doesn't shove the window off-screen.
            x = x.clamp(mon_pos.x + margin, mon_right - phys_w - margin);
            y = y.clamp(mon_pos.y + margin, mon_bottom - phys_h - margin);
            (x, y)
        }
        None => {
            // No tray rect → assume top-right tray (Windows/GNOME default)
            // and pin the panel to the top-right corner of the monitor.
            let x = mon_right - phys_w - margin;
            let y = mon_pos.y + margin + (28.0 * scale).round() as i32; // leave room for a typical top panel
            (x, y)
        }
    };

    let _ = win.set_position(PhysicalPosition::new(phys_x, phys_y));
    let _ = win.set_always_on_top(true);
    let _ = win.set_skip_taskbar(true);
    // Leave `resizable(true)` set so the user can drag corners.
    tracing::info!(
        "position_popover tray={:?} -> pos=({}, {}) size=({}, {}) scale={}",
        tray_rect,
        phys_x,
        phys_y,
        phys_w,
        phys_h,
        scale
    );
    Ok(())
}

/// Show the popover window anchored to a tray-icon rectangle (or the
/// monitor corner if `tray_rect` is None).
///
/// On Linux/X11 with mutter we fight a known issue: position requests on
/// already-mapped windows are coalesced with the WM's auto-placement.
/// Mitigation: hide the window first (if it's visible), set position, then
/// show — unmapped windows accept geometry hints reliably.
#[cfg(not(mobile))]
fn show_popover(
    app: &AppHandle,
    win: &WebviewWindow,
    tray_rect: Option<(i32, i32, i32, i32)>,
) -> ToolResult<()> {
    tracing::info!("show_popover ENTER tray_rect={:?}", tray_rect);
    // Show via gtk directly on Linux. We also call Tauri's `show` so
    // its internal "is_visible" tracking gets updated.
    #[cfg(target_os = "linux")]
    {
        let _ = win.show();
        if !linux_show(win) {
            let _ = win.unminimize();
        }
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = win.show();
        let _ = win.unminimize();
    }
    promote_to_utility(win);
    if let Err(e) = position_popover(app, win, tray_rect) {
        tracing::warn!("show_popover: position_popover err: {:?}", e);
    }
    let _ = win.set_focus();
    let _ = win.set_always_on_top(true);
    tracing::info!("show_popover EXIT");
    // Re-apply position once on a small delay in case mutter coalesced
    // the configure-request through the show transition. Use Tauri's
    // async runtime so this works whether we were called from the
    // tokio-bound IPC thread or from the GTK main thread (tray menu /
    // global shortcut handlers).
    let app_clone = app.clone();
    let win_clone = win.clone();
    let tray_clone = tray_rect;
    tauri::async_runtime::spawn(async move {
        for delay_ms in [60u64, 200, 500] {
            tokio::time::sleep(std::time::Duration::from_millis(delay_ms)).await;
            let _ = position_popover(&app_clone, &win_clone, tray_clone);
        }
    });
    let _ = app.emit("popover-visible", true);
    Ok(())
}

#[cfg(not(mobile))]
fn hide_popover(app: &AppHandle, win: &WebviewWindow) {
    tracing::info!("hide_popover called");
    // Hide first via gtk directly on Linux — Tauri's wrapper has proven
    // unreliable here. Cross-platform fallback uses Tauri's hide.
    #[cfg(target_os = "linux")]
    {
        if !linux_hide(win) {
            let _ = win.hide();
        }
    }
    #[cfg(not(target_os = "linux"))]
    {
        let _ = win.hide();
    }
    // The user might have hidden the window while the workspace editor
    // was open (decorated, in-taskbar). Always revert to popover chrome
    // before the next show, otherwise the tray click would bring back a
    // decorated window with the workspace pane still rendered. The
    // `popover-visible:false` emit below is the JS cue to drop the
    // workspace state class and close the active file. Doing this
    // after hide() means the user doesn't see the chrome flicker.
    let _ = win.set_decorations(false);
    let _ = win.set_skip_taskbar(true);
    let _ = win.set_always_on_top(true);
    promote_to_utility(win);
    let _ = app.emit("popover-visible", false);
}

/// IPC: imperative show. Front-end calls this after a global-shortcut hit
/// or a settings/menu action. Tray clicks bypass IPC and call
/// `show_popover` directly so they can pass the tray rect through.
#[tauri::command]
#[cfg(not(mobile))]
async fn show_chat(app: AppHandle, state: State<'_, AppState>) -> ToolResult<()> {
    let win = app
        .get_webview_window(MAIN_LABEL)
        .ok_or_else(|| ToolError {
            error: "main window missing".into(),
        })?;
    show_popover(&app, &win, None)?;
    let mut s = state.settings.lock().await;
    s.sidebar_open = true;
    state.store.save(&s).await.map_err(ToolError::from)?;
    Ok(())
}

#[tauri::command]
#[cfg(not(mobile))]
async fn hide_chat(app: AppHandle, state: State<'_, AppState>) -> ToolResult<()> {
    if let Some(win) = app.get_webview_window(MAIN_LABEL) {
        hide_popover(&app, &win);
    }
    let mut s = state.settings.lock().await;
    s.sidebar_open = false;
    state.store.save(&s).await.map_err(ToolError::from)?;
    Ok(())
}

#[tauri::command]
#[cfg(not(mobile))]
async fn toggle_chat(app: AppHandle, state: State<'_, AppState>) -> ToolResult<bool> {
    let win = app
        .get_webview_window(MAIN_LABEL)
        .ok_or_else(|| ToolError {
            error: "main window missing".into(),
        })?;
    let visible = win.is_visible().unwrap_or(false);
    if visible {
        hide_chat(app, state).await?;
        Ok(false)
    } else {
        show_chat(app, state).await?;
        Ok(true)
    }
}

// Legacy aliases — older IPC callers still reference these names.
#[tauri::command]
#[cfg(not(mobile))]
async fn toggle_sidebar(app: AppHandle, state: State<'_, AppState>) -> ToolResult<bool> {
    toggle_chat(app, state).await
}

#[tauri::command]
#[cfg(not(mobile))]
async fn set_sidebar_visible(
    app: AppHandle,
    state: State<'_, AppState>,
    visible: bool,
) -> ToolResult<()> {
    if visible {
        show_chat(app, state).await
    } else {
        hide_chat(app, state).await
    }
}

/// Flip the main window between "popover" mode (borderless, always-on-top,
/// hidden from the taskbar) and "workspace" mode (a regular decorated
/// window the user can drag/resize like any other app). The workspace
/// editor calls this on open/close so the popover doesn't feel cramped
/// when the editor is up but stays out of the way for chat-only use.
#[tauri::command]
#[cfg(not(mobile))]
async fn set_workspace_window_mode(app: AppHandle, enabled: bool) -> ToolResult<()> {
    let win = app
        .get_webview_window(MAIN_LABEL)
        .ok_or_else(|| ToolError {
            error: "main window missing".into(),
        })?;
    if enabled {
        // Workspace open → regular window. Tauri's `set_decorations` /
        // `set_skip_taskbar` aren't enough on X11 because the popover's
        // GTK type hint is `Utility`, which mutter excludes from the
        // taskbar and from tile-snap. Demote the GTK window to `Normal`
        // and clear the keep-above / skip-taskbar / skip-pager hints
        // before flipping the Tauri-level attributes.
        //
        // On Linux, mutter only re-reads `_NET_WM_WINDOW_TYPE` when the
        // window is unmapped, so we hide → demote → show. Brief flicker,
        // but it's the only way to actually make the window tilable and
        // taskbar-visible. macOS/Windows pick up the live changes fine.
        #[cfg(target_os = "linux")]
        {
            let _ = win.hide();
        }
        demote_to_normal(&win);
        let _ = win.set_always_on_top(false);
        let _ = win.set_skip_taskbar(false);
        let _ = win.set_decorations(true);
        // The popover anchors to a tray corner; that position is wrong
        // for a larger decorated window. Resize to a workable default
        // and center on the current monitor.
        let _ = win.set_size(LogicalSize::new(1300.0_f64, 800.0_f64));
        if let Some(monitor) = win.current_monitor().ok().flatten() {
            let mon_pos = monitor.position();
            let mon_size = monitor.size();
            if let Ok(sz) = win.outer_size() {
                let x = mon_pos.x + ((mon_size.width as i32 - sz.width as i32) / 2);
                let y = mon_pos.y + ((mon_size.height as i32 - sz.height as i32) / 2);
                let _ = win.set_position(PhysicalPosition::new(x, y));
            }
        }
        #[cfg(target_os = "linux")]
        {
            let _ = win.show();
            let _ = win.set_focus();
        }
    } else {
        // Workspace closed → revert to popover. Same hide → re-promote
        // → show dance so the type hint flip lands on Linux.
        #[cfg(target_os = "linux")]
        {
            let _ = win.hide();
        }
        let _ = win.set_decorations(false);
        let _ = win.set_skip_taskbar(true);
        let _ = win.set_always_on_top(true);
        promote_to_utility(&win);
        #[cfg(target_os = "linux")]
        {
            let _ = win.show();
            let _ = win.set_focus();
        }
        // The JS caller restores the previous geometry it captured
        // before opening so the window snaps back to its tray corner.
    }
    Ok(())
}

#[tauri::command]
#[cfg(not(mobile))]
async fn set_dock_mode(
    app: AppHandle,
    state: State<'_, AppState>,
    mode: String,
) -> ToolResult<String> {
    match mode.as_str() {
        "panel" | "expanded" | "open" => {
            show_chat(app, state).await?;
            Ok("panel".into())
        }
        "bubble" | "collapsed" | "closed" => {
            hide_chat(app, state).await?;
            Ok("bubble".into())
        }
        other => Err(ToolError {
            error: format!("unknown dock mode: {other}"),
        }),
    }
}

#[tauri::command]
#[cfg(not(mobile))]
async fn toggle_dock_mode(app: AppHandle, state: State<'_, AppState>) -> ToolResult<String> {
    let opened = toggle_chat(app, state).await?;
    Ok(if opened {
        "panel".into()
    } else {
        "bubble".into()
    })
}

#[tauri::command]
#[cfg(not(mobile))]
async fn save_dock_position(app: AppHandle, state: State<'_, AppState>) -> ToolResult<()> {
    // Kept for back-compat with the older drag-the-bubble flow; the
    // tray-anchored popover doesn't need to remember position.
    let _ = (app, state);
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn show_chat(_app: AppHandle, state: State<'_, AppState>) -> ToolResult<()> {
    let mut s = state.settings.lock().await;
    s.sidebar_open = true;
    state.store.save(&s).await.map_err(ToolError::from)
}

#[tauri::command]
#[cfg(mobile)]
async fn hide_chat(_app: AppHandle, state: State<'_, AppState>) -> ToolResult<()> {
    let mut s = state.settings.lock().await;
    s.sidebar_open = false;
    state.store.save(&s).await.map_err(ToolError::from)
}

#[tauri::command]
#[cfg(mobile)]
async fn toggle_chat(_app: AppHandle, state: State<'_, AppState>) -> ToolResult<bool> {
    let mut s = state.settings.lock().await;
    s.sidebar_open = !s.sidebar_open;
    let visible = s.sidebar_open;
    state.store.save(&s).await.map_err(ToolError::from)?;
    Ok(visible)
}

#[tauri::command]
#[cfg(mobile)]
async fn toggle_sidebar(app: AppHandle, state: State<'_, AppState>) -> ToolResult<bool> {
    toggle_chat(app, state).await
}

#[tauri::command]
#[cfg(mobile)]
async fn set_sidebar_visible(
    app: AppHandle,
    state: State<'_, AppState>,
    visible: bool,
) -> ToolResult<()> {
    if visible {
        show_chat(app, state).await
    } else {
        hide_chat(app, state).await
    }
}

#[tauri::command]
#[cfg(mobile)]
async fn set_workspace_window_mode(_app: AppHandle, _enabled: bool) -> ToolResult<()> {
    Ok(())
}

#[tauri::command]
#[cfg(mobile)]
async fn set_dock_mode(
    app: AppHandle,
    state: State<'_, AppState>,
    mode: String,
) -> ToolResult<String> {
    match mode.as_str() {
        "panel" | "expanded" | "open" => {
            show_chat(app, state).await?;
            Ok("panel".into())
        }
        "bubble" | "collapsed" | "closed" => {
            hide_chat(app, state).await?;
            Ok("bubble".into())
        }
        other => Err(ToolError {
            error: format!("unknown dock mode: {other}"),
        }),
    }
}

#[tauri::command]
#[cfg(mobile)]
async fn toggle_dock_mode(app: AppHandle, state: State<'_, AppState>) -> ToolResult<String> {
    let opened = toggle_chat(app, state).await?;
    Ok(if opened {
        "panel".into()
    } else {
        "bubble".into()
    })
}

#[tauri::command]
#[cfg(mobile)]
async fn save_dock_position(_app: AppHandle, _state: State<'_, AppState>) -> ToolResult<()> {
    Ok(())
}

// --------------------------------------------------------------------------
// Tauri setup
// --------------------------------------------------------------------------

#[cfg(target_os = "linux")]
fn cleanup_legacy_linux_launchers() {
    let home = match std::env::var_os("HOME") {
        Some(home) => std::path::PathBuf::from(home),
        None => return,
    };
    let current_exe = std::env::current_exe().ok();
    let legacy_bin = home.join(".local/bin/agixt-desktop");
    let current_is_legacy_bin = current_exe.as_ref().is_some_and(|path| path == &legacy_bin);

    let apps_dir = home.join(".local/share/applications");
    // Old launcher and URL-scheme handler from when the binary was named
    // `agixt-desktop` and the deb package was `a-gi-xt-desktop`. The
    // unified `agixt.desktop` we ship now supersedes both.
    for name in [
        "agixt-desktop.desktop",
        "agixt-desktop-handler.desktop",
        "agixt-handler.desktop",
    ] {
        let path = apps_dir.join(name);
        if path.exists() {
            match std::fs::remove_file(&path) {
                Ok(_) => tracing::info!("removed legacy desktop launcher {}", path.display()),
                Err(e) => {
                    tracing::warn!("failed to remove legacy launcher {}: {e}", path.display())
                }
            }
        }
    }

    // Legacy hicolor icon written under the old name.
    let legacy_icon = home.join(".local/share/icons/hicolor/128x128/apps/agixt-desktop.png");
    if legacy_icon.exists() {
        let _ = std::fs::remove_file(&legacy_icon);
    }

    if !current_is_legacy_bin && legacy_bin.exists() {
        match std::fs::remove_file(&legacy_bin) {
            Ok(_) => tracing::info!("removed legacy desktop binary {}", legacy_bin.display()),
            Err(e) => tracing::warn!(
                "failed to remove legacy desktop binary {}: {e}",
                legacy_bin.display()
            ),
        }
    }

    let _ = std::process::Command::new("update-desktop-database")
        .arg(apps_dir)
        .status();
}

#[cfg(not(target_os = "linux"))]
fn cleanup_legacy_linux_launchers() {}

/// Install a freedesktop `.desktop` launcher and hicolor icon so GNOME Shell
/// (and other taskbars) can associate the running window with a dash entry.
///
/// Why: the running window's `WM_CLASS` is `"agixt"`, but without a
/// `.desktop` file containing a matching `StartupWMClass=agixt`, GNOME
/// treats it as "Window not associated with a window list" and the app
/// is easy to lose behind other windows.
#[cfg(target_os = "linux")]
fn install_linux_launcher() {
    let home = match std::env::var_os("HOME") {
        Some(h) => std::path::PathBuf::from(h),
        None => return,
    };
    let current_exe = match std::env::current_exe() {
        Ok(p) => p,
        Err(e) => {
            tracing::warn!("install_linux_launcher: current_exe failed: {e}");
            return;
        }
    };
    let exe_str = current_exe.display().to_string();

    // Install icon under the user's hicolor theme so `Icon=agixt`
    // resolves to a real PNG.
    let icons_dir = home.join(".local/share/icons/hicolor/128x128/apps");
    if let Err(e) = std::fs::create_dir_all(&icons_dir) {
        tracing::warn!(
            "install_linux_launcher: mkdir {} failed: {e}",
            icons_dir.display()
        );
        return;
    }
    let icon_path = icons_dir.join("agixt.png");
    if let Err(e) = std::fs::write(&icon_path, APP_ICON_BYTES) {
        tracing::warn!(
            "install_linux_launcher: write icon {} failed: {e}",
            icon_path.display()
        );
    }

    let apps_dir = home.join(".local/share/applications");
    if let Err(e) = std::fs::create_dir_all(&apps_dir) {
        tracing::warn!(
            "install_linux_launcher: mkdir {} failed: {e}",
            apps_dir.display()
        );
        return;
    }
    let desktop_path = apps_dir.join("agixt.desktop");
    let contents = format!(
        "[Desktop Entry]\n\
        Type=Application\n\
        Name=AGiXT Desktop\n\
        Comment=AGiXT chat, workspace, and machine console\n\
        Exec=\"{exe}\" %u\n\
        Icon=agixt\n\
        Terminal=false\n\
        StartupNotify=true\n\
        StartupWMClass=agixt\n\
        Categories=Network;\n\
        MimeType=x-scheme-handler/agixt;\n",
        exe = exe_str
    );

    let needs_write = match std::fs::read_to_string(&desktop_path) {
        Ok(existing) => existing != contents,
        Err(_) => true,
    };
    if needs_write {
        if let Err(e) = std::fs::write(&desktop_path, &contents) {
            tracing::warn!(
                "install_linux_launcher: write {} failed: {e}",
                desktop_path.display()
            );
            return;
        }
        tracing::info!("installed desktop launcher {}", desktop_path.display());
        let _ = std::process::Command::new("update-desktop-database")
            .arg(&apps_dir)
            .status();
        let _ = std::process::Command::new("gtk-update-icon-cache")
            .arg(home.join(".local/share/icons/hicolor"))
            .status();
    }

    // Mask any leftover deb-installed system launcher
    // (`/usr/share/applications/AGiXT Desktop.desktop` from older
    // `a-gi-xt-desktop` package installs). Per the freedesktop spec, a
    // user-local `.desktop` with the same basename and `Hidden=true`
    // causes GIO to skip the system file entirely.
    let mask_path = apps_dir.join("AGiXT Desktop.desktop");
    let system_target = std::path::Path::new("/usr/share/applications/AGiXT Desktop.desktop");
    if system_target.exists() {
        let mask = "[Desktop Entry]\n\
            Type=Application\n\
            Name=AGiXT Desktop (legacy)\n\
            NoDisplay=true\n\
            Hidden=true\n\
            Exec=true\n";
        let needs_mask_write = match std::fs::read_to_string(&mask_path) {
            Ok(existing) => existing != mask,
            Err(_) => true,
        };
        if needs_mask_write {
            if let Err(e) = std::fs::write(&mask_path, mask) {
                tracing::warn!(
                    "install_linux_launcher: write mask {} failed: {e}",
                    mask_path.display()
                );
            } else {
                tracing::info!("masked legacy system launcher via {}", mask_path.display());
                let _ = std::process::Command::new("update-desktop-database")
                    .arg(&apps_dir)
                    .status();
            }
        }
    } else if mask_path.exists() {
        // System file is gone; the mask is no longer needed and would
        // just clutter the user's app dir.
        let _ = std::fs::remove_file(&mask_path);
    }

    // Re-point the agixt:// URL scheme to the unified launcher. xdg-mime
    // caches the previous default in `~/.config/mimeapps.list` and might
    // still reference an old/removed file.
    let mime_default = std::process::Command::new("xdg-mime")
        .args(["query", "default", "x-scheme-handler/agixt"])
        .output();
    let needs_mime_update = match mime_default {
        Ok(out) => {
            let s = String::from_utf8_lossy(&out.stdout);
            s.trim() != "agixt.desktop"
        }
        Err(_) => true,
    };
    if needs_mime_update {
        let _ = std::process::Command::new("xdg-mime")
            .args(["default", "agixt.desktop", "x-scheme-handler/agixt"])
            .status();
    }
}

#[cfg(not(target_os = "linux"))]
fn install_linux_launcher() {}

#[cfg(not(mobile))]
pub fn run() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info,agixt_desktop_lib=debug".into()),
        )
        .init();

    tauri::Builder::default()
        // single-instance must run before any other plugin so that a
        // second `agixt-desktop` invocation (e.g. from a deep-link
        // dispatcher) is forwarded to the first instance instead of
        // booting a parallel app.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            // When a deep-link comes in while we're already running,
            // single-instance hands us the args. We don't need to do
            // anything with `argv` directly — `deep-link`'s `on_open_url`
            // listener (registered in setup) handles the URL.
            tracing::info!("single_instance: another invocation received, raising");
            if let Some(w) = app.get_webview_window(MAIN_LABEL) {
                let _ = show_popover(app, &w, None);
            }
        }))
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(|app, _shortcut, event| {
                    use tauri_plugin_global_shortcut::ShortcutState;
                    tracing::info!("global shortcut fired, state={:?}", event.state());
                    if event.state() != ShortcutState::Pressed {
                        return;
                    }
                    if let Some(w) = app.get_webview_window(MAIN_LABEL) {
                        let shown = is_actually_visible(&w);
                        tracing::info!("global shortcut: shown={shown}");
                        if shown {
                            hide_popover(app, &w);
                        } else {
                            let _ = show_popover(app, &w, None);
                        }
                    } else {
                        tracing::warn!("global shortcut: no main window");
                    }
                })
                .build(),
        )
        .setup(|app| {
            cleanup_legacy_linux_launchers();
            install_linux_launcher();

            // Load settings synchronously up-front so the front-end can render
            // immediately with the cached state.
            let store = tauri::async_runtime::block_on(async {
                ConfigStore::open().await.expect("open settings db")
            });
            let settings =
                tauri::async_runtime::block_on(async { store.load().await.unwrap_or_default() });

            let initial_visible = settings.sidebar_open;
            app.manage(AppState {
                store: Arc::new(store),
                settings: Mutex::new(settings),
                terminals: Arc::new(terminal::TerminalManager::new()),
                voice: Arc::new(voice::VoiceRecorder::new()),
                sudo_keepalive: Mutex::new(None),
                suppress_blur_hide: Arc::new(AtomicBool::new(false)),
            });

            // Show the popover on launch — Linux AppIndicator has been
            // unreliable enough on this dev box (icon disappears mid-
            // interaction) that we can't depend on the tray as the
            // *only* path to the window. Visible-by-default fixes the
            // "I clicked something and nothing happened" problem.
            //
            // We deliberately skip `hide-on-blur`: it races every other
            // focus event on GTK and is the source of the
            // "click-tray-it-doesn't-come-back" reports. Users dismiss
            // explicitly via the X button, Esc, the tray menu, or
            // Ctrl+Shift+Space.
            let _ = initial_visible;
            let handle = app.handle().clone();
            if let Some(win) = app.get_webview_window(MAIN_LABEL) {
                configure_media_capture(&win);
                promote_to_utility(&win);
                let _ = position_popover(&handle, &win, None);
                let _ = win.show();
                let _ = win.set_focus();
                // After show() the X11 window is realized, so we can
                // stamp `_GTK_APPLICATION_ID` for GNOME's window tracker.
                set_gtk_application_id(&win);
                // Re-apply position once after the WM has placed it —
                // mutter sometimes coalesces the first set_position
                // through the show transition.
                let win_clone = win.clone();
                let handle_clone = handle.clone();
                tauri::async_runtime::spawn(async move {
                    for delay_ms in [80u64, 250, 600] {
                        tokio::time::sleep(std::time::Duration::from_millis(delay_ms)).await;
                        let _ = position_popover(&handle_clone, &win_clone, None);
                    }
                });
            }

            // Listen for `agixt://` deep links. These come in three flavors:
            //
            //   agixt://login?token=<JWT>                   — auto-sign-in after OAuth
            //   agixt://oauth-connect?provider=&code=       — extension OAuth callback
            //   agixt://open                                — just raise the popover
            //
            // The web client's `/user/close/{provider}` page redirects to
            // these URLs once it has the authorization code, so the user
            // never has to copy-paste.
            use tauri_plugin_deep_link::DeepLinkExt;
            let dl_handle = handle.clone();
            handle.deep_link().on_open_url(move |event| {
                for url in event.urls() {
                    tracing::info!("deep link received: {}", url);
                    let scheme = url.scheme();
                    if scheme != "agixt" {
                        continue;
                    }
                    // url::Url treats `agixt://login?token=X` so that
                    // `host_str()` is "login" and the token is in
                    // query_pairs().
                    let action = url.host_str().unwrap_or(url.path()).to_string();
                    let token = url.query_pairs().find_map(|(k, v)| {
                        if k == "token" || k == "jwt" {
                            Some(v.into_owned())
                        } else {
                            None
                        }
                    });
                    let provider = url.query_pairs().find_map(|(k, v)| {
                        if k == "provider" {
                            Some(v.into_owned())
                        } else {
                            None
                        }
                    });
                    let code = url.query_pairs().find_map(|(k, v)| {
                        if k == "code" {
                            Some(v.into_owned())
                        } else {
                            None
                        }
                    });
                    let app = dl_handle.clone();
                    tauri::async_runtime::spawn(async move {
                        if let Some(w) = app.get_webview_window(MAIN_LABEL) {
                            let _ = show_popover(&app, &w, None);
                        }
                        match action.as_str() {
                            "login" => {
                                if let Some(tok) = token {
                                    handle_deep_link_login(&app, tok).await;
                                } else {
                                    tracing::warn!("agixt://login received with no token");
                                }
                            }
                            "oauth-connect" => {
                                handle_deep_link_oauth_connect(&app, provider, code).await;
                                if let Some(w) = app.get_webview_window("agent-settings") {
                                    let _ = w.show();
                                    let _ = w.set_focus();
                                }
                            }
                            _ => {}
                        }
                    });
                }
            });
            // On Linux we may be invoked via xdg-open before the runtime
            // is ready; the plugin queues those URLs and replays them
            // once we've subscribed.
            #[cfg(any(not(target_os = "linux"), debug_assertions))]
            if let Err(e) = handle.deep_link().register("agixt") {
                tracing::warn!("could not register agixt:// scheme: {e}");
            }

            // Register Ctrl+Shift+Space as a global "open AGiXT" shortcut
            // so the user always has a way in even if their DE hides the
            // tray (e.g. stock GNOME without an extension).
            use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut};
            let shortcut = Shortcut::new(Some(Modifiers::CONTROL | Modifiers::SHIFT), Code::Space);
            if let Err(e) = handle.global_shortcut().register(shortcut) {
                tracing::warn!("global shortcut unavailable: {e}");
            }

            // System tray menu — on Linux AppIndicator (GNOME), the
            // canonical interaction is to open a menu when the icon is
            // clicked. Bare "click without menu" events are unreliable
            // there, so we use the menu as the primary entry point —
            // exactly like Slack and Discord.
            //
            // We also still listen to `on_tray_icon_event` so that on
            // platforms that DO give us bare click events (Windows,
            // macOS) we get the snappier toggle behavior.
            let tray_handle = handle.clone();
            let menu = Menu::with_items(
                &handle,
                &[
                    &MenuItem::with_id(&handle, "open", "Open AGiXT", true, None::<&str>)
                        .map_err(|e| Box::<dyn std::error::Error>::from(e.to_string()))?,
                    &MenuItem::with_id(&handle, "hide", "Hide AGiXT", true, None::<&str>)
                        .map_err(|e| Box::<dyn std::error::Error>::from(e.to_string()))?,
                    &MenuItem::with_id(&handle, "quit", "Quit AGiXT", true, None::<&str>)
                        .map_err(|e| Box::<dyn std::error::Error>::from(e.to_string()))?,
                ],
            )
            .map_err(|e| Box::<dyn std::error::Error>::from(e.to_string()))?;

            let icon_bytes = include_bytes!("../icons/32x32.png");
            let tray_icon = Image::from_bytes(icon_bytes).ok();
            let mut builder = TrayIconBuilder::with_id("agixt")
                .tooltip("AGiXT")
                .menu(&menu)
                .on_menu_event(move |app, event| {
                    let id = event.id().as_ref().to_string();
                    tracing::info!("tray menu event: id={id}");
                    match id.as_str() {
                        "open" => {
                            if let Some(w) = app.get_webview_window(MAIN_LABEL) {
                                tracing::info!("menu open -> show_popover");
                                let _ = show_popover(app, &w, None);
                            } else {
                                tracing::warn!("menu open: no main window");
                            }
                        }
                        "hide" => {
                            if let Some(w) = app.get_webview_window(MAIN_LABEL) {
                                tracing::info!("menu hide -> hide_popover");
                                hide_popover(app, &w);
                            }
                        }
                        "quit" => {
                            tracing::info!("menu quit");
                            app.exit(0);
                        }
                        other => tracing::warn!("unknown menu id: {other}"),
                    }
                })
                .on_tray_icon_event(move |tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        rect,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(w) = app.get_webview_window(MAIN_LABEL) {
                            let shown = is_actually_visible(&w);
                            tracing::info!("tray click: shown={shown}");
                            if shown {
                                hide_popover(&app, &w);
                            } else {
                                let scale = w.scale_factor().unwrap_or(1.0);
                                let pos = rect.position.to_physical::<i32>(scale);
                                let size = rect.size.to_physical::<u32>(scale);
                                let tray_rect =
                                    Some((pos.x, pos.y, size.width as i32, size.height as i32));
                                let _ = show_popover(&app, &w, tray_rect);
                            }
                        } else {
                            tracing::warn!("tray click but no main window");
                        }
                    }
                });
            if let Some(img) = tray_icon {
                builder = builder.icon(img);
            }
            // IMPORTANT: hold on to the TrayIcon handle. Even though
            // Tauri's app manager keeps a reference internally, dropping
            // the local binding has been observed to free GTK
            // AppIndicator handles on some Ubuntu setups, which is what
            // makes the icon vanish after the first menu interaction.
            // We stash it in `app.manage` so it lives for the app's
            // entire lifetime.
            match builder.build(&tray_handle) {
                Ok(tray) => {
                    app.manage(TrayHolder(std::sync::Mutex::new(Some(tray))));
                }
                Err(e) => tracing::warn!("system tray unavailable: {e}"),
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            frontend_log,
            get_settings,
            save_settings,
            logout,
            desktop_update_check,
            desktop_update_install,
            voice_start_recording,
            voice_stop_recording,
            voice_cancel_recording,
            list_service_brands,
            check_local_agixt,
            detect_hardware,
            default_install_path,
            install_agixt_local,
            list_oauth_providers,
            login_password,
            request_magic_link,
            register_account,
            login_with_jwt,
            build_oauth_login_url,
            build_oauth_connect_url,
            open_agent_settings,
            list_companies,
            list_agents,
            list_conversations,
            select_conversation,
            get_conversation_history,
            new_conversation,
            chat_send,
            agent_vision,
            client_platform,
            device_open_url,
            device_open_app,
            device_open_settings,
            desktop_screenshot,
            desktop_click,
            desktop_move,
            desktop_drag,
            desktop_scroll,
            desktop_type,
            shell_run,
            sudo_status,
            sudo_auth,
            sudo_clear,
            sudo_run,
            terminal_open,
            terminal_list,
            terminal_close,
            terminal_exec,
            terminal_send_input,
            terminal_read,
            terminal_resize,
            terminal_signal,
            fs_read,
            fs_write,
            fs_append,
            fs_edit,
            fs_list,
            fs_stat,
            fs_mkdir,
            fs_delete,
            fs_rename,
            workspace_upload_local,
            workspace_download_to_local,
            workspace_list,
            show_chat,
            hide_chat,
            toggle_chat,
            set_dock_mode,
            toggle_dock_mode,
            save_dock_position,
            toggle_sidebar,
            set_sidebar_visible,
            set_workspace_window_mode,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| match event {
            tauri::RunEvent::ExitRequested { code, api, .. } => {
                tracing::warn!("run event: exit requested code={code:?}");
                if code.is_none() {
                    if let Some(win) = app.get_webview_window(MAIN_LABEL) {
                        tracing::warn!(
                            "run event: preventing user/window requested exit; hiding popover"
                        );
                        hide_popover(app, &win);
                    }
                    api.prevent_exit();
                }
            }
            tauri::RunEvent::Exit => {
                tracing::warn!("run event: exit");
            }
            tauri::RunEvent::WindowEvent { label, event, .. } => match event {
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    tracing::warn!("window event: close requested label={label}");
                    api.prevent_close();
                    if let Some(win) = app.get_webview_window(&label) {
                        hide_popover(app, &win);
                    }
                }
                tauri::WindowEvent::Destroyed => {
                    tracing::warn!("window event: destroyed label={label}");
                }
                tauri::WindowEvent::Focused(focused) => {
                    tracing::debug!("window event: focused label={label} focused={focused}");
                }
                _ => {}
            },
            _ => {}
        });
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
#[cfg(mobile)]
pub fn run() {
    tracing_subscriber::fmt()
        .with_env_filter(
            tracing_subscriber::EnvFilter::try_from_default_env()
                .unwrap_or_else(|_| "info,agixt_desktop_lib=debug".into()),
        )
        .init();

    tauri::Builder::default()
        .plugin(tauri_plugin_deep_link::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let settings_db = app
                .path()
                .app_config_dir()
                .expect("resolve app config dir")
                .join("settings.db");
            let store = tauri::async_runtime::block_on(async {
                ConfigStore::open_at(settings_db)
                    .await
                    .expect("open settings db")
            });
            let settings =
                tauri::async_runtime::block_on(async { store.load().await.unwrap_or_default() });

            app.manage(AppState {
                store: Arc::new(store),
                settings: Mutex::new(settings),
                terminals: Arc::new(terminal::TerminalManager::new()),
                voice: Arc::new(voice::VoiceRecorder::new()),
                sudo_keepalive: Mutex::new(None),
                suppress_blur_hide: Arc::new(AtomicBool::new(false)),
            });

            // Mobile deep links must be declared in config and handled
            // here. OAuth login lands as `agixt://login?token=<jwt>`;
            // without this listener Android opens the app but the JWT is
            // never persisted.
            use tauri_plugin_deep_link::DeepLinkExt;
            let handle = app.handle().clone();
            let dl_handle = handle.clone();
            handle.deep_link().on_open_url(move |event| {
                for url in event.urls() {
                    tracing::info!("deep link received: {}", url);
                    if url.scheme() != "agixt" {
                        continue;
                    }
                    let action = url.host_str().unwrap_or(url.path()).to_string();
                    let token = url.query_pairs().find_map(|(k, v)| {
                        if k == "token" || k == "jwt" {
                            Some(v.into_owned())
                        } else {
                            None
                        }
                    });
                    let provider = url.query_pairs().find_map(|(k, v)| {
                        if k == "provider" {
                            Some(v.into_owned())
                        } else {
                            None
                        }
                    });
                    let code = url.query_pairs().find_map(|(k, v)| {
                        if k == "code" {
                            Some(v.into_owned())
                        } else {
                            None
                        }
                    });
                    let app = dl_handle.clone();
                    tauri::async_runtime::spawn(async move {
                        match action.as_str() {
                            "login" => {
                                if let Some(tok) = token {
                                    handle_deep_link_login(&app, tok).await;
                                } else {
                                    tracing::warn!("agixt://login received with no token");
                                }
                            }
                            "oauth-connect" => {
                                handle_deep_link_oauth_connect(&app, provider, code).await;
                            }
                            _ => {}
                        }
                    });
                }
            });

            // Mobile is a single-surface app. Desktop-only secondary
            // windows, especially agent-settings, can otherwise win the
            // initial WebView focus on Android and strand signed-out users
            // away from the login screen.
            if let Some(win) = app.get_webview_window("agent-settings") {
                let _ = win.hide();
                let _ = win.destroy();
            }

            if let Some(win) = app.get_webview_window(MAIN_LABEL) {
                let _ = win.show();
                let _ = win.set_focus();
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            frontend_log,
            get_settings,
            save_settings,
            logout,
            desktop_update_check,
            desktop_update_install,
            voice_start_recording,
            voice_stop_recording,
            voice_cancel_recording,
            list_service_brands,
            check_local_agixt,
            detect_hardware,
            default_install_path,
            install_agixt_local,
            list_oauth_providers,
            login_password,
            request_magic_link,
            register_account,
            login_with_jwt,
            build_oauth_login_url,
            build_oauth_connect_url,
            open_agent_settings,
            list_companies,
            list_agents,
            list_conversations,
            select_conversation,
            get_conversation_history,
            new_conversation,
            chat_send,
            agent_vision,
            client_platform,
            device_open_url,
            device_open_app,
            device_open_settings,
            desktop_screenshot,
            desktop_click,
            desktop_move,
            desktop_drag,
            desktop_scroll,
            desktop_type,
            shell_run,
            sudo_status,
            sudo_auth,
            sudo_clear,
            sudo_run,
            terminal_open,
            terminal_list,
            terminal_close,
            terminal_exec,
            terminal_send_input,
            terminal_read,
            terminal_resize,
            terminal_signal,
            fs_read,
            fs_write,
            fs_append,
            fs_edit,
            fs_list,
            fs_stat,
            fs_mkdir,
            fs_delete,
            fs_rename,
            workspace_upload_local,
            workspace_download_to_local,
            workspace_list,
            show_chat,
            hide_chat,
            toggle_chat,
            set_dock_mode,
            toggle_dock_mode,
            save_dock_position,
            toggle_sidebar,
            set_sidebar_visible,
            set_workspace_window_mode,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
