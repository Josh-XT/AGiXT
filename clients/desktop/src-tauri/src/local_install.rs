//! "Install AGiXT Locally" orchestration.
//!
//! End-to-end: from a fresh user machine to AGiXT + ezLocalai
//! responding on `localhost:7437`. Steps:
//!   1. `git clone` (or `git pull`) Josh-XT/AGiXT
//!   2. `pip install -e .` inside the cloned tree
//!   3. `pip install ezlocalai` — the AGiXT CLI shells out to
//!      `ezlocalai start` and refuses to proceed without it
//!   4. Pre-write `.env` with the hardware-tier-chosen `DEFAULT_MODEL`,
//!      `EZLOCALAI_AI_MODEL`, `EZLOCALAI_MAX_TOKENS`,
//!      `AGIXT_AUTO_UPDATE=true`, and `WITH_EZLOCALAI=true`. This both
//!      plants our model/context choice and skips the auto-update prompt the
//!      AGiXT CLI fires when no `.env` exists yet
//!   5. `agixt restart` — which itself handles Docker install (Linux,
//!      with prompt) and triggers `ezlocalai start` which detects GPU
//!      vendor + offers to install NVIDIA Container Toolkit / build
//!      the right compose file (cuda / rocm / jetson / cpu)
//!
//! Each subprocess streams stdout+stderr line-by-line as
//! `local-install-progress` events so the login screen can render a
//! live log.
//!
//! Sudo on Linux: AGiXT's Docker install and ezLocalai's NVIDIA
//! Container Toolkit install both shell out to `sudo apt-get install`.
//! When the caller has authenticated via `sudo_auth` first, sudo's
//! cached credentials carry into the child processes — no TTY prompt
//! needed. Without that cache, the install will still proceed up to
//! the point sudo is required and then fail with a useful error in
//! the install log.

use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::process::Stdio;
use std::time::Duration;
use tauri::{AppHandle, Emitter};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::process::Command;

const REPO_URL: &str = "https://github.com/Josh-XT/AGiXT.git";
/// Cheap liveness probe — `{"status":"UP"}` from FastAPI when AGiXT is
/// up. Doesn't identify the app on its own, so we follow with the
/// OpenAPI title check to confirm we're looking at AGiXT specifically.
const HEALTH_URL: &str = "http://localhost:7437/health";
/// OpenAPI spec — title is "AGiXT" and `info.version` carries the
/// release we'll surface in the UI when the server is reachable.
const OPENAPI_URL: &str = "http://localhost:7437/openapi.json";
const LOCAL_BASE: &str = "http://localhost:7437";
/// Tauri event channel the frontend subscribes to for live install
/// progress. One event per stdout/stderr line plus phase markers.
pub const INSTALL_EVENT: &str = "local-install-progress";

#[derive(Debug, Clone, Deserialize)]
pub struct InstallArgs {
    /// Absolute path the AGiXT repo should live in. If the directory
    /// already exists and looks like an AGiXT checkout we `git pull`;
    /// otherwise we `git clone` into it.
    #[serde(default)]
    pub install_path: Option<String>,
    /// Path to the Python interpreter to use for `pip install -e .`
    /// and the `agixt` CLI shim. Defaults to `python3` from PATH.
    #[serde(default)]
    pub python: Option<String>,
    /// HuggingFace repo ID of the model ezLocalai should default to.
    /// Pre-written into `AGiXT/.env` as `DEFAULT_MODEL` so AGiXT's
    /// `set_environment` picks it up via `os.getenv()`. If `None`,
    /// the AGiXT CLI's own default is left in place.
    #[serde(default)]
    pub default_model: Option<String>,
    /// Pre-written into `.env` as `EZLOCALAI_MAX_TOKENS` when available.
    #[serde(default)]
    pub default_max_tokens: Option<u32>,
}

#[derive(Debug, Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum InstallEvent {
    /// Phase boundary — frontend uses this to update step indicators.
    Phase { phase: String, message: String },
    /// One line of subprocess output (stdout or stderr).
    Log { stream: String, line: String },
    /// Terminal success — agixt is up and reachable.
    Ok { message: String },
    /// Terminal failure with a human-readable reason. The frontend
    /// shows this and stops the spinner.
    Err { message: String },
}

#[derive(Debug, Clone, Serialize)]
pub struct InstallResult {
    pub success: bool,
    pub install_path: String,
    pub message: String,
}

/// Best-effort default install location: `$HOME/AGiXT`.
pub fn default_install_path() -> Result<PathBuf> {
    let home = dirs::home_dir().ok_or_else(|| anyhow!("could not resolve home directory"))?;
    Ok(home.join("AGiXT"))
}

/// Probe `http://localhost:7437` for an AGiXT instance. Two-step:
///   1. GET `/health` for a cheap UP/DOWN.
///   2. GET `/openapi.json` to confirm the app identifies as AGiXT and
///      grab `info.version` for the UI.
///
/// Step 1 alone isn't enough — a `{"status":"UP"}` response is
/// generic FastAPI boilerplate that any other server on port 7437
/// could be serving.
pub async fn check_local_agixt() -> LocalAgixtStatus {
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_millis(1_500))
        .build()
    {
        Ok(c) => c,
        Err(e) => {
            return LocalAgixtStatus {
                running: false,
                version: None,
                detail: Some(format!("client build failed: {e}")),
            };
        }
    };
    // Step 1: liveness.
    match client.get(HEALTH_URL).send().await {
        Ok(resp) if resp.status().is_success() => {}
        Ok(resp) => {
            return LocalAgixtStatus {
                running: false,
                version: None,
                detail: Some(format!("HTTP {} on /health", resp.status())),
            };
        }
        Err(e) if e.is_connect() || e.is_timeout() => {
            return LocalAgixtStatus {
                running: false,
                version: None,
                detail: None,
            };
        }
        Err(e) => {
            return LocalAgixtStatus {
                running: false,
                version: None,
                detail: Some(format!("{e}")),
            };
        }
    }
    // Step 2: identity. We treat any `info.title` containing "AGiXT"
    // (case-insensitive) as a match — covers brand variants the spec
    // is sometimes published under.
    match client.get(OPENAPI_URL).send().await {
        Ok(resp) if resp.status().is_success() => {
            let text = resp.text().await.unwrap_or_default();
            let info = parse_openapi_info(&text);
            let is_agixt = info
                .title
                .as_deref()
                .map(|t| t.to_ascii_lowercase().contains("agixt"))
                .unwrap_or(false);
            if is_agixt {
                LocalAgixtStatus {
                    running: true,
                    version: info.version,
                    detail: None,
                }
            } else {
                LocalAgixtStatus {
                    running: false,
                    version: None,
                    detail: Some(format!(
                        "{LOCAL_BASE} is up but isn't AGiXT (title: {})",
                        info.title.as_deref().unwrap_or("?")
                    )),
                }
            }
        }
        Ok(resp) => LocalAgixtStatus {
            running: false,
            version: None,
            detail: Some(format!("HTTP {} on /openapi.json", resp.status())),
        },
        Err(e) => LocalAgixtStatus {
            running: false,
            version: None,
            detail: Some(format!("openapi probe failed: {e}")),
        },
    }
}

#[derive(Default)]
struct OpenApiInfo {
    title: Option<String>,
    version: Option<String>,
}

fn parse_openapi_info(json_blob: &str) -> OpenApiInfo {
    let v: serde_json::Value = match serde_json::from_str(json_blob) {
        Ok(v) => v,
        Err(_) => return OpenApiInfo::default(),
    };
    let info = v.get("info");
    OpenApiInfo {
        title: info
            .and_then(|i| i.get("title"))
            .and_then(|x| x.as_str())
            .map(str::to_string),
        version: info
            .and_then(|i| i.get("version"))
            .and_then(|x| x.as_str())
            .map(str::to_string),
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct LocalAgixtStatus {
    pub running: bool,
    pub version: Option<String>,
    /// Diagnostic to surface in the UI when probing fails for a
    /// non-trivial reason (e.g. a non-AGiXT process is squatting on
    /// the port). `None` for the common "nothing listening" case.
    pub detail: Option<String>,
}

/// Run the full install. Errors are surfaced both as a `Result::Err`
/// and as an `InstallEvent::Err` event so the frontend doesn't have to
/// distinguish "command rejected" from "command ran, install failed".
pub async fn run_install(app: AppHandle, args: InstallArgs) -> Result<InstallResult> {
    let install_path = match args.install_path.as_deref() {
        Some(p) if !p.trim().is_empty() => PathBuf::from(p),
        _ => default_install_path()?,
    };
    let python = args.python.unwrap_or_else(|| "python3".to_string());

    emit(
        &app,
        InstallEvent::Phase {
            phase: "preflight".into(),
            message: format!("Installing AGiXT to {}", install_path.display()),
        },
    );

    if let Err(e) = preflight(&app, &python).await {
        emit(
            &app,
            InstallEvent::Err {
                message: format!("Preflight failed: {e:#}"),
            },
        );
        return Err(e);
    }

    if let Err(e) = clone_or_pull(&app, &install_path).await {
        emit(
            &app,
            InstallEvent::Err {
                message: format!("Git step failed: {e:#}"),
            },
        );
        return Err(e);
    }

    if let Err(e) = pip_install(&app, &install_path, &python).await {
        emit(
            &app,
            InstallEvent::Err {
                message: format!("pip install failed: {e:#}"),
            },
        );
        return Err(e);
    }

    if let Err(e) = pip_install_ezlocalai(&app, &python).await {
        emit(
            &app,
            InstallEvent::Err {
                message: format!("pip install ezlocalai failed: {e:#}"),
            },
        );
        return Err(e);
    }

    if let Err(e) = write_env_file(
        &app,
        &install_path,
        args.default_model.as_deref(),
        args.default_max_tokens,
    )
    .await
    {
        emit(
            &app,
            InstallEvent::Err {
                message: format!("Writing .env failed: {e:#}"),
            },
        );
        return Err(e);
    }

    if let Err(e) = agixt_restart(&app, &install_path, &python).await {
        emit(
            &app,
            InstallEvent::Err {
                message: format!("agixt restart failed: {e:#}"),
            },
        );
        return Err(e);
    }

    if let Err(e) = wait_for_health(&app).await {
        emit(
            &app,
            InstallEvent::Err {
                message: format!("Health check failed: {e:#}"),
            },
        );
        return Err(e);
    }

    let msg = format!("AGiXT is running at {LOCAL_BASE}");
    emit(
        &app,
        InstallEvent::Ok {
            message: msg.clone(),
        },
    );
    Ok(InstallResult {
        success: true,
        install_path: install_path.display().to_string(),
        message: msg,
    })
}

async fn preflight(app: &AppHandle, python: &str) -> Result<()> {
    emit(
        app,
        InstallEvent::Phase {
            phase: "preflight".into(),
            message: "Checking for git and python…".into(),
        },
    );
    require_on_path(app, "git").await?;
    // Python may be `python3` or `python`. We trust whatever the user
    // chose; `python --version` confirms it works at all.
    let mut cmd = Command::new(python);
    cmd.arg("--version");
    stream_command(app, cmd, "preflight", StdinMode::None)
        .await
        .with_context(|| format!("python interpreter `{python}` not runnable"))?;
    Ok(())
}

async fn require_on_path(app: &AppHandle, program: &str) -> Result<()> {
    let mut cmd = Command::new(program);
    cmd.arg("--version");
    stream_command(app, cmd, "preflight", StdinMode::None)
        .await
        .with_context(|| format!("`{program}` is required but not found on PATH"))?;
    Ok(())
}

async fn clone_or_pull(app: &AppHandle, install_path: &Path) -> Result<()> {
    let dot_git = install_path.join(".git");
    if dot_git.is_dir() {
        emit(
            app,
            InstallEvent::Phase {
                phase: "git".into(),
                message: format!("Pulling latest AGiXT into {}", install_path.display()),
            },
        );
        let mut cmd = Command::new("git");
        cmd.current_dir(install_path).args(["pull", "--ff-only"]);
        stream_command(app, cmd, "git", StdinMode::None).await?;
        return Ok(());
    }
    // Fresh clone. Make sure parent exists first.
    if let Some(parent) = install_path.parent() {
        tokio::fs::create_dir_all(parent)
            .await
            .with_context(|| format!("create {}", parent.display()))?;
    }
    if install_path.exists() {
        // Directory exists but isn't a git repo. Refuse rather than
        // clobber whatever is there.
        return Err(anyhow!(
            "{} exists but is not an AGiXT git checkout; remove or pick a different path",
            install_path.display()
        ));
    }
    emit(
        app,
        InstallEvent::Phase {
            phase: "git".into(),
            message: format!("Cloning {REPO_URL} into {}", install_path.display()),
        },
    );
    let mut cmd = Command::new("git");
    cmd.args(["clone", REPO_URL]).arg(install_path);
    stream_command(app, cmd, "git", StdinMode::None).await
}

async fn pip_install(app: &AppHandle, install_path: &Path, python: &str) -> Result<()> {
    emit(
        app,
        InstallEvent::Phase {
            phase: "pip".into(),
            message: "Installing AGiXT Python package (this can take a few minutes)…".into(),
        },
    );
    let mut cmd = Command::new(python);
    cmd.current_dir(install_path)
        .args(["-m", "pip", "install", "-e", "."]);
    stream_command(app, cmd, "pip", StdinMode::None).await
}

async fn pip_install_ezlocalai(app: &AppHandle, python: &str) -> Result<()> {
    emit(
        app,
        InstallEvent::Phase {
            phase: "ezlocalai".into(),
            message: "Installing ezLocalai (the AGiXT CLI shells out to `ezlocalai start`)…".into(),
        },
    );
    let mut cmd = Command::new(python);
    cmd.args(["-m", "pip", "install", "ezlocalai"]);
    stream_command(app, cmd, "ezlocalai", StdinMode::None).await
}

/// Pre-write `<install_path>/.env` with our hardware-tier-chosen
/// `DEFAULT_MODEL`, `EZLOCALAI_AI_MODEL`, `EZLOCALAI_MAX_TOKENS`,
/// `AGIXT_AUTO_UPDATE=true`, and `WITH_EZLOCALAI=true`.
///
/// Two reasons for writing this *before* invoking `agixt restart`:
///   * The AGiXT CLI prompts "Would you like AGiXT to auto update…?"
///     when no `.env` exists. A non-TTY subprocess would block forever
///     on that prompt.
///   * `set_environment()` calls `load_dotenv()` first, then reads
///     `os.getenv()` for each known key — so any value we plant here
///     wins over the in-CLI defaults.
async fn write_env_file(
    app: &AppHandle,
    install_path: &Path,
    default_model: Option<&str>,
    default_max_tokens: Option<u32>,
) -> Result<()> {
    emit(
        app,
        InstallEvent::Phase {
            phase: "env".into(),
            message: "Pre-configuring .env (model, auto-update, ezLocalai)…".into(),
        },
    );
    let env_path = install_path.join(".env");
    let mut desired: Vec<(&str, String)> = vec![
        ("AGIXT_AUTO_UPDATE", "true".into()),
        ("WITH_EZLOCALAI", "true".into()),
    ];
    if let Some(model) = default_model {
        let trimmed = model.trim();
        if !trimmed.is_empty() {
            desired.push(("DEFAULT_MODEL", trimmed.into()));
            desired.push(("EZLOCALAI_AI_MODEL", trimmed.into()));
        }
    }
    if let Some(max_tokens) = default_max_tokens.filter(|n| *n > 0) {
        desired.push(("EZLOCALAI_MAX_TOKENS", max_tokens.to_string()));
    }

    let mut existing = if env_path.exists() {
        tokio::fs::read_to_string(&env_path)
            .await
            .with_context(|| format!("read {}", env_path.display()))?
            .lines()
            .map(str::to_string)
            .collect::<Vec<_>>()
    } else {
        Vec::new()
    };
    let mut existing_keys = std::collections::HashSet::new();
    for line in &existing {
        let stripped = line.trim();
        if stripped.is_empty() || stripped.starts_with('#') {
            continue;
        }
        if let Some((key, _)) = stripped.split_once('=') {
            existing_keys.insert(key.trim().to_string());
        }
    }

    let mut added = Vec::new();
    for (key, value) in desired {
        if existing_keys.contains(key) {
            continue;
        }
        existing.push(format!("{key}=\"{}\"", escape_env_value(&value)));
        added.push(key.to_string());
    }

    if existing.is_empty() {
        existing.push(String::new());
    }
    let body = format!("{}\n", existing.join("\n"));
    tokio::fs::write(&env_path, body)
        .await
        .with_context(|| format!("write {}", env_path.display()))?;
    emit(
        app,
        InstallEvent::Log {
            stream: "env/stdout".into(),
            line: if added.is_empty() {
                format!(
                    "{} already had local model/ezLocalai settings",
                    env_path.display()
                )
            } else {
                format!("Updated {} with {}", env_path.display(), added.join(", "))
            },
        },
    );
    Ok(())
}

fn escape_env_value(value: &str) -> String {
    value.replace('\\', "\\\\").replace('"', "\\\"")
}

async fn agixt_restart(app: &AppHandle, install_path: &Path, python: &str) -> Result<()> {
    emit(
        app,
        InstallEvent::Phase {
            phase: "start".into(),
            message:
                "Starting AGiXT + ezLocalai via `agixt restart` (Docker pulls and model downloads can take 30+ minutes on first run)…"
                    .into(),
        },
    );
    let mut cmd = Command::new(python);
    cmd.current_dir(install_path)
        .args(["-m", "agixt.cli", "restart"]);
    // Both AGiXT and ezLocalai may emit interactive (y/n) prompts —
    // Docker install, NVIDIA Container Toolkit install. Defaults are
    // "y" on both, so a stream of newlines accepts every prompt.
    stream_command(app, cmd, "start", StdinMode::AcceptDefaults).await
}

async fn wait_for_health(app: &AppHandle) -> Result<()> {
    emit(
        app,
        InstallEvent::Phase {
            phase: "health".into(),
            message: "Waiting for AGiXT to come up at localhost:7437…".into(),
        },
    );
    // Docker and dependency startup can be slow after the CLI returns,
    // especially on first-run local installs.
    for attempt in 0..180 {
        let status = check_local_agixt().await;
        if status.running {
            emit(
                app,
                InstallEvent::Log {
                    stream: "stdout".into(),
                    line: format!("AGiXT responded after {}s", attempt),
                },
            );
            return Ok(());
        }
        tokio::time::sleep(Duration::from_secs(1)).await;
    }
    Err(anyhow!(
        "AGiXT did not come up within 180s — check the install log for errors"
    ))
}

/// How `stream_command` wires up stdin for the child process.
#[derive(Debug, Clone, Copy)]
enum StdinMode {
    /// Hand the child `/dev/null` (or the Windows equivalent). Use
    /// when the child cannot prompt — most commands.
    None,
    /// Pipe a steady stream of `y\n` lines so any `(y/n)` prompt with
    /// a default of "y" auto-accepts. Used for `agixt restart` because
    /// the AGiXT and ezLocalai CLIs may prompt to install Docker /
    /// the NVIDIA Container Toolkit during the run.
    AcceptDefaults,
}

/// Spawn a command, stream stdout+stderr line-by-line as InstallEvent::Log
/// events, and bubble a non-zero exit as an Err.
async fn stream_command(
    app: &AppHandle,
    mut cmd: Command,
    phase: &str,
    stdin_mode: StdinMode,
) -> Result<()> {
    match stdin_mode {
        StdinMode::None => {
            cmd.stdin(Stdio::null());
        }
        StdinMode::AcceptDefaults => {
            cmd.stdin(Stdio::piped());
        }
    }
    cmd.stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);
    let mut child = cmd.spawn().context("spawn subprocess")?;

    // Hand the child a chunk of `y\n` lines so any (y/n) prompts with
    // a default of "y" auto-accept. We send a finite buffer rather
    // than holding stdin open indefinitely so the child sees EOF if
    // it ever closes its end.
    if matches!(stdin_mode, StdinMode::AcceptDefaults) {
        if let Some(mut stdin) = child.stdin.take() {
            tokio::spawn(async move {
                use tokio::io::AsyncWriteExt;
                let payload = "y\n".repeat(64);
                let _ = stdin.write_all(payload.as_bytes()).await;
                let _ = stdin.shutdown().await;
            });
        }
    }

    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let app_out = app.clone();
    let app_err = app.clone();
    let phase_out = phase.to_string();
    let phase_err = phase.to_string();

    let stdout_task = tokio::spawn(async move {
        if let Some(out) = stdout {
            let mut reader = BufReader::new(out).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                let _ = app_out.emit(
                    INSTALL_EVENT,
                    InstallEvent::Log {
                        stream: format!("{phase_out}/stdout"),
                        line,
                    },
                );
            }
        }
    });
    let stderr_task = tokio::spawn(async move {
        if let Some(err) = stderr {
            let mut reader = BufReader::new(err).lines();
            while let Ok(Some(line)) = reader.next_line().await {
                let _ = app_err.emit(
                    INSTALL_EVENT,
                    InstallEvent::Log {
                        stream: format!("{phase_err}/stderr"),
                        line,
                    },
                );
            }
        }
    });

    let status = child.wait().await.context("wait for subprocess")?;
    let _ = stdout_task.await;
    let _ = stderr_task.await;

    if !status.success() {
        return Err(anyhow!(
            "command failed with {} (phase: {phase})",
            status
                .code()
                .map(|c| format!("exit code {c}"))
                .unwrap_or_else(|| "no exit code (signal)".into())
        ));
    }
    Ok(())
}

fn emit(app: &AppHandle, event: InstallEvent) {
    if let Err(e) = app.emit(INSTALL_EVENT, &event) {
        tracing::warn!("failed to emit install event: {e}");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_openapi_info_extracts_title_and_version() {
        let blob = r#"{"info":{"title":"AGiXT","version":"v1.9.4"},"openapi":"3.1.0"}"#;
        let info = parse_openapi_info(blob);
        assert_eq!(info.title.as_deref(), Some("AGiXT"));
        assert_eq!(info.version.as_deref(), Some("v1.9.4"));
    }

    #[test]
    fn parse_openapi_info_handles_missing_info_block() {
        let blob = r#"{"openapi":"3.1.0"}"#;
        let info = parse_openapi_info(blob);
        assert!(info.title.is_none());
        assert!(info.version.is_none());
    }

    #[test]
    fn parse_openapi_info_handles_invalid_json() {
        let info = parse_openapi_info("not json");
        assert!(info.title.is_none());
    }

    #[test]
    fn parse_openapi_info_treats_non_string_version_as_missing() {
        // FastAPI sometimes serializes int versions; we want None, not
        // a panic, in that case.
        let blob = r#"{"info":{"title":"AGiXT","version":42}}"#;
        let info = parse_openapi_info(blob);
        assert_eq!(info.title.as_deref(), Some("AGiXT"));
        assert!(info.version.is_none());
    }

    #[test]
    fn escape_env_value_escapes_quotes_and_backslashes() {
        assert_eq!(escape_env_value(r#"a\b"c"#), r#"a\\b\"c"#);
    }

    /// Live smoke test against a local AGiXT. Skipped by default
    /// because CI doesn't have an AGiXT running; opt in by setting
    /// `AGIXT_LIVE_PROBE=1` when AGiXT is up on `localhost:7437`.
    #[tokio::test]
    async fn live_probe_detects_running_agixt() {
        if std::env::var("AGIXT_LIVE_PROBE").ok().as_deref() != Some("1") {
            return;
        }
        let s = check_local_agixt().await;
        assert!(s.running, "expected running=true, got {:?}", s);
        assert!(
            s.version.is_some(),
            "expected version from /openapi.json, got {:?}",
            s
        );
    }
}
