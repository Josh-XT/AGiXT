use std::{collections::HashMap, path::PathBuf, time::Duration};

use anyhow::{anyhow, Context};
use futures_util::StreamExt;
use serde::{Deserialize, Serialize};
use tokio::io::AsyncWriteExt;

use crate::terminal;

const DEFAULT_UPDATE_BASE_URL: &str = "https://download.xt.systems";

#[derive(Debug, Clone, Serialize)]
pub struct DesktopUpdateStatus {
    pub current_build_id: String,
    pub current_commit: String,
    pub app_version: String,
    pub latest_build_id: Option<String>,
    pub update_available: bool,
    pub platform: String,
    pub ready: bool,
    pub download_url: String,
    pub artifact_name: Option<String>,
    pub message: String,
}

#[derive(Debug, Clone, Serialize)]
pub struct DesktopUpdateInstallResult {
    pub installed: bool,
    pub restart_required: bool,
    pub downloaded_path: Option<String>,
    pub command: Option<String>,
    pub message: String,
}

#[derive(Debug, Deserialize)]
struct VersionResponse {
    #[serde(default)]
    version: String,
    #[serde(default)]
    ready_targets: Vec<String>,
    #[serde(default)]
    builds: HashMap<String, BuildState>,
}

#[derive(Debug, Deserialize)]
struct BuildState {
    #[serde(default)]
    status: Option<String>,
    #[serde(default)]
    ready: Option<bool>,
    #[serde(default)]
    download: Option<String>,
    #[serde(default)]
    artifact: Option<String>,
}

pub fn current_build_id() -> String {
    option_env!("AGIXT_DESKTOP_BUILD_ID")
        .unwrap_or("dev")
        .to_string()
}

fn current_commit() -> String {
    option_env!("AGIXT_DESKTOP_COMMIT")
        .unwrap_or("unknown")
        .to_string()
}

fn update_base_url() -> String {
    std::env::var("AGIXT_DESKTOP_UPDATE_BASE_URL")
        .ok()
        .filter(|v| !v.trim().is_empty())
        .unwrap_or_else(|| DEFAULT_UPDATE_BASE_URL.into())
        .trim_end_matches('/')
        .to_string()
}

fn platform_slug() -> String {
    if cfg!(target_os = "linux") {
        if cfg!(target_arch = "aarch64") {
            "linux-arm64".into()
        } else {
            "linux".into()
        }
    } else if cfg!(target_os = "windows") {
        "windows".into()
    } else if cfg!(target_os = "macos") {
        if cfg!(target_arch = "x86_64") {
            "macos-x86".into()
        } else {
            "macos".into()
        }
    } else {
        std::env::consts::OS.into()
    }
}

pub async fn check() -> anyhow::Result<DesktopUpdateStatus> {
    let base_url = update_base_url();
    let platform = platform_slug();
    let current_build_id = current_build_id();
    let client = reqwest::Client::builder()
        .user_agent(concat!("agixt-desktop/", env!("CARGO_PKG_VERSION")))
        .timeout(Duration::from_secs(20))
        .build()
        .context("build desktop updater client")?;
    let version_url = format!("{base_url}/desktop/version");
    let resp = client
        .get(&version_url)
        .send()
        .await
        .with_context(|| format!("GET {version_url}"))?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "update check HTTP {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }
    let version: VersionResponse = resp.json().await.context("parse desktop version")?;
    let latest = version.version.trim();
    let build_state = version.builds.get(&platform);
    let ready = version.ready_targets.iter().any(|t| t == &platform)
        || build_state.and_then(|s| s.ready).unwrap_or(false)
        || build_state
            .and_then(|s| s.status.as_deref())
            .map(|s| s.eq_ignore_ascii_case("ready"))
            .unwrap_or(false);
    let update_available = !latest.is_empty()
        && latest != "unknown"
        && latest != current_build_id
        && current_build_id != "unknown";
    let download_path = build_state
        .and_then(|s| s.download.clone())
        .unwrap_or_else(|| format!("/desktop/{platform}"));
    let download_url = format!("{base_url}{download_path}");
    let artifact_name = build_state.and_then(|s| s.artifact.clone());
    let message = if !update_available {
        "AGiXT Desktop is up to date.".into()
    } else if ready {
        format!("AGiXT Desktop update {latest} is ready.")
    } else {
        format!("AGiXT Desktop update {latest} is building.")
    };

    Ok(DesktopUpdateStatus {
        current_build_id,
        current_commit: current_commit(),
        app_version: env!("CARGO_PKG_VERSION").to_string(),
        latest_build_id: if latest.is_empty() {
            None
        } else {
            Some(latest.to_string())
        },
        update_available,
        platform,
        ready,
        download_url,
        artifact_name,
        message,
    })
}

pub async fn install() -> anyhow::Result<DesktopUpdateInstallResult> {
    let status = check().await?;
    if !status.update_available {
        return Ok(DesktopUpdateInstallResult {
            installed: false,
            restart_required: false,
            downloaded_path: None,
            command: None,
            message: status.message,
        });
    }
    if !status.ready {
        return Err(anyhow!(
            "{} Try again once /desktop/version marks {} ready.",
            status.message,
            status.platform
        ));
    }
    ensure_linux_update_sudo_ready().await?;

    let path = download_update(&status).await?;
    install_downloaded_update(&status, path).await
}

async fn ensure_linux_update_sudo_ready() -> anyhow::Result<()> {
    if !cfg!(target_os = "linux") {
        return Ok(());
    }
    let result = terminal::sudo_refresh_or_restore()
        .await
        .context("check desktop update sudo session")?;
    if result.exit_code == 0 {
        return Ok(());
    }
    return Err(anyhow!(
        "SUDO_AUTH_REQUIRED: Authenticate Privileged Commands once so AGiXT Desktop can remember the sudo password, then retry installing the desktop update."
    ));
}

async fn download_update(status: &DesktopUpdateStatus) -> anyhow::Result<PathBuf> {
    let client = reqwest::Client::builder()
        .user_agent(concat!("agixt-desktop/", env!("CARGO_PKG_VERSION")))
        .timeout(Duration::from_secs(900))
        .build()
        .context("build desktop update downloader")?;

    let mut last_error = None;
    for attempt in 1..=3 {
        match download_update_once(&client, status).await {
            Ok(path) => return Ok(path),
            Err(err) => {
                last_error = Some(err);
                if attempt < 3 {
                    tokio::time::sleep(Duration::from_secs(2 * attempt)).await;
                }
            }
        }
    }
    Err(last_error
        .unwrap_or_else(|| anyhow!("download failed"))
        .context("download update failed after 3 attempts"))
}

async fn download_update_once(
    client: &reqwest::Client,
    status: &DesktopUpdateStatus,
) -> anyhow::Result<PathBuf> {
    let resp = client
        .get(&status.download_url)
        .send()
        .await
        .with_context(|| format!("download {}", status.download_url))?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "update download HTTP {}: {}",
            resp.status(),
            resp.text().await.unwrap_or_default()
        ));
    }

    let artifact_name = resp
        .headers()
        .get("x-artifact-name")
        .and_then(|v| v.to_str().ok())
        .map(sanitize_filename)
        .filter(|v| !v.is_empty())
        .or_else(|| {
            status
                .artifact_name
                .as_deref()
                .map(sanitize_filename)
                .filter(|v| !v.is_empty())
        })
        .unwrap_or_else(|| default_update_filename(status));
    let dir = std::env::temp_dir().join("agixt-desktop-updates");
    tokio::fs::create_dir_all(&dir)
        .await
        .with_context(|| format!("create {}", dir.display()))?;
    let path = dir.join(artifact_name);
    let expected_len = resp.content_length();
    if let Some(expected_len) = expected_len {
        if expected_len > 0 {
            if let Ok(metadata) = tokio::fs::metadata(&path).await {
                if metadata.len() == expected_len {
                    return Ok(path);
                }
            }
        }
    }

    let tmp_name = path
        .file_name()
        .and_then(|v| v.to_str())
        .map(|v| format!(".{v}.part-{}", std::process::id()))
        .unwrap_or_else(|| format!(".agixt-desktop-update.part-{}", std::process::id()));
    let tmp_path = path.with_file_name(tmp_name);
    let _ = tokio::fs::remove_file(&tmp_path).await;
    let mut file = tokio::fs::File::create(&tmp_path)
        .await
        .with_context(|| format!("create {}", tmp_path.display()))?;
    let mut downloaded = 0_u64;
    let mut stream = resp.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.context("read update body chunk")?;
        downloaded += chunk.len() as u64;
        file.write_all(&chunk)
            .await
            .with_context(|| format!("write {}", tmp_path.display()))?;
    }
    file.flush().await.ok();
    drop(file);
    if let Some(expected_len) = expected_len {
        if downloaded != expected_len {
            let _ = tokio::fs::remove_file(&tmp_path).await;
            return Err(anyhow!(
                "downloaded {downloaded} bytes but expected {expected_len} bytes"
            ));
        }
    }
    tokio::fs::rename(&tmp_path, &path)
        .await
        .with_context(|| format!("move {} to {}", tmp_path.display(), path.display()))?;
    Ok(path)
}

fn sanitize_filename(name: &str) -> String {
    name.chars()
        .filter(|c| c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_'))
        .collect()
}

fn default_update_filename(status: &DesktopUpdateStatus) -> String {
    let build = status.latest_build_id.as_deref().unwrap_or("latest");
    let ext = if cfg!(target_os = "linux") {
        ".deb"
    } else if cfg!(target_os = "windows") {
        ".exe"
    } else if cfg!(target_os = "macos") {
        ".dmg"
    } else {
        ""
    };
    format!(
        "agixt-desktop-{build}-{platform}{ext}",
        platform = status.platform
    )
}

async fn install_downloaded_update(
    status: &DesktopUpdateStatus,
    path: PathBuf,
) -> anyhow::Result<DesktopUpdateInstallResult> {
    if cfg!(target_os = "linux") {
        install_linux_update(path).await
    } else if cfg!(target_os = "macos") {
        open_installer(status, path).await
    } else if cfg!(target_os = "windows") {
        open_installer(status, path).await
    } else {
        Ok(DesktopUpdateInstallResult {
            installed: false,
            restart_required: false,
            downloaded_path: Some(path.display().to_string()),
            command: None,
            message: format!("Downloaded update to {}.", path.display()),
        })
    }
}

async fn install_linux_update(path: PathBuf) -> anyhow::Result<DesktopUpdateInstallResult> {
    #[cfg(unix)]
    if path.extension().and_then(|v| v.to_str()) != Some("deb") {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = tokio::fs::metadata(&path).await?.permissions();
        perms.set_mode(perms.mode() | 0o755);
        tokio::fs::set_permissions(&path, perms).await?;
        return Ok(DesktopUpdateInstallResult {
            installed: false,
            restart_required: false,
            downloaded_path: Some(path.display().to_string()),
            command: None,
            message: format!(
                "Downloaded update to {}. This build did not produce a .deb installer.",
                path.display()
            ),
        });
    }

    let command = format!(
        "DEBIAN_FRONTEND=noninteractive apt-get install -y {}",
        shell_quote(&path.display().to_string())
    );
    let result = terminal::sudo_run_with_stored_password(command.clone(), 1_800_000)
        .await
        .context("run desktop update installer")?;
    if terminal::sudo_auth_required(&result) {
        return Err(anyhow!(
            "SUDO_AUTH_REQUIRED: Authenticate Privileged Commands once so AGiXT Desktop can remember the sudo password, then retry installing the desktop update."
        ));
    }
    if result.exit_code != 0 {
        let detail = if !result.stderr.trim().is_empty() {
            result.stderr.trim()
        } else {
            result.stdout.trim()
        };
        return Err(anyhow!("desktop update installer failed: {detail}"));
    }

    Ok(DesktopUpdateInstallResult {
        installed: true,
        restart_required: true,
        downloaded_path: Some(path.display().to_string()),
        command: Some(command),
        message: "Update installed. Restart AGiXT Desktop to use the new version.".into(),
    })
}

async fn open_installer(
    _status: &DesktopUpdateStatus,
    path: PathBuf,
) -> anyhow::Result<DesktopUpdateInstallResult> {
    let command = if cfg!(target_os = "windows") {
        format!(
            "start \"\" {}",
            windows_cmd_quote(&path.display().to_string())
        )
    } else {
        format!("open {}", shell_quote(&path.display().to_string()))
    };
    let result = terminal::shell_run(command.clone(), 30_000).await?;
    if result.exit_code != 0 {
        let detail = if !result.stderr.trim().is_empty() {
            result.stderr.trim()
        } else {
            result.stdout.trim()
        };
        return Err(anyhow!("failed to open update installer: {detail}"));
    }
    Ok(DesktopUpdateInstallResult {
        installed: false,
        restart_required: false,
        downloaded_path: Some(path.display().to_string()),
        command: Some(command),
        message: format!(
            "Downloaded and opened update installer at {}.",
            path.display()
        ),
    })
}

fn shell_quote(value: &str) -> String {
    format!("'{}'", value.replace('\'', "'\"'\"'"))
}

fn windows_cmd_quote(value: &str) -> String {
    format!("\"{}\"", value.replace('"', "\"\""))
}
