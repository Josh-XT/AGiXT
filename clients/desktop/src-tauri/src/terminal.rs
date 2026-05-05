//! Background PTY terminal sessions.
//!
//! Mirrors the local terminal-control surface area of
//! `xtsystems_extensions/machines.py` — the agent can:
//!   * `terminal_open`         — spawn a shell in a PTY
//!   * `terminal_exec`         — write a command + read output until idle
//!   * `terminal_send_input`   — write raw bytes (no newline added)
//!   * `terminal_read`         — pull buffered output since `offset`
//!   * `terminal_resize`       — tell the PTY about a new window size
//!   * `terminal_signal`       — send Ctrl+C / Ctrl+D
//!   * `terminal_close`        — kill the child + drop the session
//!   * `terminal_list`         — enumerate active sessions
//!
//! Multiple sessions can be open in parallel. Output from each PTY is
//! drained on a dedicated OS thread into a per-session `Vec<u8>` ring
//! buffer; readers see a monotonic byte offset so they can poll
//! incrementally without loss or duplication.

use anyhow::{anyhow, Context, Result};
use portable_pty::{native_pty_system, CommandBuilder, MasterPty, PtySize};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::env;
use std::ffi::OsString;
use std::io::{Read, Write};
use std::path::PathBuf;
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};
use tokio::io::AsyncWriteExt;

const MAX_BUFFER_BYTES: usize = 1_048_576; // 1 MiB per session
const READ_CHUNK: usize = 4096;

/// One PTY-backed shell session.
struct Session {
    id: String,
    shell: String,
    cwd: String,
    cols: u16,
    rows: u16,
    created: Instant,
    last_activity: Arc<Mutex<Instant>>,
    /// Accumulated raw output. The reader thread appends; readers consume
    /// using `total_bytes` as a monotonic offset so they can resume.
    buffer: Arc<Mutex<Vec<u8>>>,
    /// How many bytes have ever been written to this session's stream
    /// (including any that were trimmed off the head of `buffer`).
    total_bytes: Arc<Mutex<u64>>,
    /// `true` once the child exits or the session is closed.
    closed: Arc<AtomicBool>,
    /// Wrapped writer to the PTY master. Cloned out of the master so we
    /// can keep the master around for `resize`.
    writer: Arc<Mutex<Box<dyn Write + Send>>>,
    /// Master PTY handle, kept alive so the slave stays open.
    master: Arc<Mutex<Box<dyn MasterPty + Send>>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    pub id: String,
    pub shell: String,
    pub cwd: String,
    pub cols: u16,
    pub rows: u16,
    pub closed: bool,
    /// Total bytes written by the PTY since session start.
    pub total_bytes: u64,
    /// Seconds since the session was created.
    pub uptime_secs: u64,
    /// Seconds since the last byte of output (or input).
    pub idle_secs: u64,
}

#[derive(Debug, Clone, Serialize)]
pub struct ReadResult {
    pub data: String,
    /// Byte offset of the *next* unread byte. Pass this back as `offset` on
    /// the following call to resume.
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

fn desktop_path() -> OsString {
    let mut parts: Vec<PathBuf> = env::var_os("PATH")
        .map(|v| env::split_paths(&v).collect())
        .unwrap_or_default();

    let mut add = |path: PathBuf| {
        if !path.as_os_str().is_empty() && !parts.iter().any(|p| p == &path) {
            parts.push(path);
        }
    };

    if let Ok(home) = env::var("HOME") {
        add(PathBuf::from(format!("{home}/.local/bin")));
        add(PathBuf::from(format!(
            "{home}/.local/share/flatpak/exports/bin"
        )));
    }

    for path in [
        "/usr/local/sbin",
        "/usr/local/bin",
        "/usr/sbin",
        "/usr/bin",
        "/sbin",
        "/bin",
        "/snap/bin",
        "/var/lib/flatpak/exports/bin",
        "/opt/homebrew/bin",
    ] {
        add(PathBuf::from(path));
    }

    env::join_paths(parts).unwrap_or_else(|_| env::var_os("PATH").unwrap_or_default())
}

fn normalized_exit_code(
    status_code: Option<i32>,
    success: bool,
    stdout: &str,
    stderr: &str,
) -> i32 {
    let mut code = status_code.unwrap_or_else(|| if success { 0 } else { 1 });
    if code == 0 && stdout.trim().is_empty() {
        let stderr_lower = stderr.to_lowercase();
        if stderr_lower.contains("not found")
            || stderr_lower.contains("command not found")
            || stderr_lower.contains("no such file or directory")
        {
            code = 127;
        } else if stderr_lower.contains("permission denied") {
            code = 126;
        }
    }
    code
}

#[cfg(not(target_os = "windows"))]
fn background_inner_command(command: &str) -> Option<String> {
    let trimmed = command.trim_end();
    let inner = trimmed.strip_suffix('&')?.trim();
    if inner.is_empty() {
        None
    } else {
        Some(inner.to_string())
    }
}

#[cfg(not(target_os = "windows"))]
fn background_shell_wrapper(command: &str) -> Option<(String, String)> {
    let inner = background_inner_command(command)?;
    let log_path = format!("/tmp/agixt-desktop-shell-run-{}.log", uuid::Uuid::new_v4());
    let script = format!(
        r#"log={log_path:?}
(
{inner}
) >"$log" 2>&1 &
pid=$!
sleep 0.3
if kill -0 "$pid" 2>/dev/null; then
  echo "started background command pid $pid; output log: $log"
  exit 0
fi
wait "$pid"
code=$?
if [ -s "$log" ]; then
  if [ "$code" -eq 0 ]; then
    cat "$log"
  else
    cat "$log" >&2
  fi
fi
exit "$code"
"#
    );
    Some((script, log_path))
}

/// Run a single shell command and collect stdout/stderr. This is the
/// one-shot command surface used by the `shell_run` client tool; persistent
/// interactive shells still go through `TerminalManager`.
pub async fn shell_run(command: String, timeout_ms: u64) -> Result<ShellRunResult> {
    let timeout_ms = timeout_ms.clamp(100, 300_000);
    #[cfg(not(target_os = "windows"))]
    let shell_command = background_shell_wrapper(&command)
        .map(|(script, _log_path)| script)
        .unwrap_or_else(|| command.clone());
    #[cfg(target_os = "windows")]
    let shell_command = command.clone();

    let cmd = if cfg!(target_os = "windows") {
        let mut c = tokio::process::Command::new("cmd");
        c.arg("/C").arg(&shell_command);
        c
    } else {
        let mut c = tokio::process::Command::new("sh");
        c.arg("-c").arg(&shell_command);
        c
    };

    run_process(command, cmd, timeout_ms, None).await
}

async fn run_process(
    display_command: String,
    mut cmd: tokio::process::Command,
    timeout_ms: u64,
    stdin_input: Option<Vec<u8>>,
) -> Result<ShellRunResult> {
    if stdin_input.is_some() {
        cmd.stdin(Stdio::piped());
    } else {
        cmd.stdin(Stdio::null());
    }
    cmd.stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .env("PATH", desktop_path())
        .kill_on_drop(true);

    let mut child = cmd
        .spawn()
        .with_context(|| format!("spawn shell command: {display_command}"))?;
    if let Some(input) = stdin_input {
        if let Some(mut stdin) = child.stdin.take() {
            tokio::spawn(async move {
                let _ = stdin.write_all(&input).await;
            });
        }
    }
    let result =
        tokio::time::timeout(Duration::from_millis(timeout_ms), child.wait_with_output()).await;

    match result {
        Ok(Ok(output)) => {
            let stdout = String::from_utf8_lossy(&output.stdout).to_string();
            let stderr = String::from_utf8_lossy(&output.stderr).to_string();
            let exit_code = normalized_exit_code(
                output.status.code(),
                output.status.success(),
                &stdout,
                &stderr,
            );
            Ok(ShellRunResult {
                command: display_command,
                stdout,
                stderr,
                exit_code,
                timed_out: false,
            })
        }
        Ok(Err(e)) => Err(e).context("wait for shell command"),
        Err(_) => Ok(ShellRunResult {
            command: display_command,
            stdout: String::new(),
            stderr: format!("command timed out after {timeout_ms}ms"),
            exit_code: 124,
            timed_out: true,
        }),
    }
}

#[cfg(not(target_os = "windows"))]
pub async fn sudo_validate(password: String) -> Result<ShellRunResult> {
    let mut cmd = tokio::process::Command::new("sudo");
    cmd.arg("-S").arg("-p").arg("").arg("-v");
    run_process(
        "sudo -v".to_string(),
        cmd,
        30_000,
        Some(format!("{password}\n").into_bytes()),
    )
    .await
}

#[cfg(target_os = "windows")]
pub async fn sudo_validate(_password: String) -> Result<ShellRunResult> {
    Ok(ShellRunResult {
        command: "sudo -v".to_string(),
        stdout: String::new(),
        stderr: "sudo is not available on Windows".to_string(),
        exit_code: 1,
        timed_out: false,
    })
}

#[cfg(not(target_os = "windows"))]
pub async fn sudo_refresh() -> Result<ShellRunResult> {
    let mut cmd = tokio::process::Command::new("sudo");
    cmd.arg("-n").arg("-v");
    run_process("sudo -n -v".to_string(), cmd, 15_000, None).await
}

#[cfg(target_os = "windows")]
pub async fn sudo_refresh() -> Result<ShellRunResult> {
    Ok(ShellRunResult {
        command: "sudo -n -v".to_string(),
        stdout: String::new(),
        stderr: "sudo is not available on Windows".to_string(),
        exit_code: 1,
        timed_out: false,
    })
}

#[cfg(not(target_os = "windows"))]
pub async fn sudo_clear() -> Result<ShellRunResult> {
    let mut cmd = tokio::process::Command::new("sudo");
    cmd.arg("-k");
    run_process("sudo -k".to_string(), cmd, 15_000, None).await
}

#[cfg(target_os = "windows")]
pub async fn sudo_clear() -> Result<ShellRunResult> {
    Ok(ShellRunResult {
        command: "sudo -k".to_string(),
        stdout: String::new(),
        stderr: "sudo is not available on Windows".to_string(),
        exit_code: 1,
        timed_out: false,
    })
}

pub async fn sudo_run(command: String, timeout_ms: u64) -> Result<ShellRunResult> {
    let timeout_ms = timeout_ms.clamp(100, 1_800_000);

    #[cfg(not(target_os = "windows"))]
    {
        let mut cmd = tokio::process::Command::new("sudo");
        cmd.arg("-n").arg("sh").arg("-c").arg(&command);
        run_process(format!("sudo {command}"), cmd, timeout_ms, None).await
    }

    #[cfg(target_os = "windows")]
    {
        Ok(ShellRunResult {
            command: format!("sudo {command}"),
            stdout: String::new(),
            stderr: "sudo is not available on Windows".to_string(),
            exit_code: 1,
            timed_out: false,
        })
    }
}

pub fn sudo_auth_required(result: &ShellRunResult) -> bool {
    if result.exit_code == 0 || result.timed_out {
        return false;
    }
    let combined = format!("{}\n{}", result.stdout, result.stderr).to_lowercase();
    combined.contains("a password is required")
        || combined.contains("password is required")
        || combined.contains("no tty present")
        || combined.contains("a terminal is required to read the password")
        || combined.contains("must be run from a terminal")
}

#[derive(Default)]
pub struct TerminalManager {
    sessions: Mutex<HashMap<String, Arc<Session>>>,
}

impl TerminalManager {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn open(
        &self,
        shell: Option<String>,
        cwd: Option<String>,
        cols: Option<u16>,
        rows: Option<u16>,
    ) -> Result<SessionInfo> {
        let cols = cols.unwrap_or(120);
        let rows = rows.unwrap_or(30);

        let pty_system = native_pty_system();
        let pair = pty_system
            .openpty(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| anyhow!("openpty: {e}"))?;

        let shell_path = shell
            .clone()
            .or_else(default_shell)
            .ok_or_else(|| anyhow!("no shell available"))?;
        let mut cmd = CommandBuilder::new(&shell_path);
        let resolved_cwd = match cwd {
            Some(c) => std::path::PathBuf::from(c),
            None => std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from(".")),
        };
        cmd.cwd(&resolved_cwd);
        if cfg!(target_os = "windows") {
            cmd.env("TERM", "dumb");
        } else {
            cmd.env("TERM", "xterm-256color");
        }
        // Inherit PATH/HOME so the shell behaves naturally.
        for key in ["PATH", "HOME", "USER", "LOGNAME", "LANG", "LC_ALL"] {
            if let Ok(v) = std::env::var(key) {
                cmd.env(key, v);
            }
        }

        let mut child = pair
            .slave
            .spawn_command(cmd)
            .map_err(|e| anyhow!("spawn shell: {e}"))?;

        let writer = pair
            .master
            .take_writer()
            .map_err(|e| anyhow!("take_writer: {e}"))?;
        let mut reader = pair
            .master
            .try_clone_reader()
            .map_err(|e| anyhow!("clone_reader: {e}"))?;

        let id = uuid::Uuid::new_v4().to_string();
        let buffer = Arc::new(Mutex::new(Vec::<u8>::new()));
        let total = Arc::new(Mutex::new(0u64));
        let closed = Arc::new(AtomicBool::new(false));
        let last_activity = Arc::new(Mutex::new(Instant::now()));

        let session = Arc::new(Session {
            id: id.clone(),
            shell: shell_path.clone(),
            cwd: resolved_cwd.display().to_string(),
            cols,
            rows,
            created: Instant::now(),
            last_activity: last_activity.clone(),
            buffer: buffer.clone(),
            total_bytes: total.clone(),
            closed: closed.clone(),
            writer: Arc::new(Mutex::new(writer)),
            master: Arc::new(Mutex::new(pair.master)),
        });

        // Reader thread: drain PTY into ring buffer.
        {
            let buffer = buffer.clone();
            let total = total.clone();
            let closed = closed.clone();
            let last_activity = last_activity.clone();
            thread::Builder::new()
                .name(format!("pty-reader-{}", id))
                .spawn(move || {
                    let mut chunk = [0u8; READ_CHUNK];
                    loop {
                        match reader.read(&mut chunk) {
                            Ok(0) => break,
                            Ok(n) => {
                                {
                                    let mut buf = buffer.lock().unwrap();
                                    buf.extend_from_slice(&chunk[..n]);
                                    if buf.len() > MAX_BUFFER_BYTES {
                                        let drop_n = buf.len() - MAX_BUFFER_BYTES;
                                        buf.drain(..drop_n);
                                    }
                                }
                                *total.lock().unwrap() += n as u64;
                                *last_activity.lock().unwrap() = Instant::now();
                            }
                            Err(_) => break,
                        }
                    }
                    closed.store(true, Ordering::SeqCst);
                })
                .ok();
        }

        // Reaper thread: keep the child handle alive and mark closed when it exits.
        {
            let closed = closed.clone();
            thread::Builder::new()
                .name(format!("pty-reaper-{}", id))
                .spawn(move || {
                    let _ = child.wait();
                    closed.store(true, Ordering::SeqCst);
                })
                .ok();
        }

        let info = info_for(&session);
        self.sessions.lock().unwrap().insert(id, session);
        Ok(info)
    }

    fn get(&self, id: &str) -> Result<Arc<Session>> {
        self.sessions
            .lock()
            .unwrap()
            .get(id)
            .cloned()
            .ok_or_else(|| anyhow!("unknown session: {id}"))
    }

    pub fn list(&self) -> Vec<SessionInfo> {
        self.sessions
            .lock()
            .unwrap()
            .values()
            .map(|s| info_for(s))
            .collect()
    }

    pub fn close(&self, id: &str) -> Result<()> {
        let session = self
            .sessions
            .lock()
            .unwrap()
            .remove(id)
            .ok_or_else(|| anyhow!("unknown session: {id}"))?;
        session.closed.store(true, Ordering::SeqCst);
        // Dropping the master + writer will close the slave end and the
        // child shell will receive SIGHUP / EOF.
        drop(session);
        Ok(())
    }

    pub fn write(&self, id: &str, data: &[u8]) -> Result<()> {
        let session = self.get(id)?;
        let mut w = session.writer.lock().unwrap();
        w.write_all(data).context("write to pty")?;
        w.flush().ok();
        *session.last_activity.lock().unwrap() = Instant::now();
        Ok(())
    }

    pub fn signal(&self, id: &str, signal: &str) -> Result<()> {
        let byte: u8 = match signal.to_ascii_lowercase().as_str() {
            "sigint" | "ctrl-c" | "ctrl+c" | "interrupt" => 0x03,
            "sigquit" | "ctrl-\\" => 0x1c,
            "eof" | "ctrl-d" | "ctrl+d" => 0x04,
            "ctrl-z" | "ctrl+z" | "suspend" => 0x1a,
            other => return Err(anyhow!("unknown signal: {other}")),
        };
        self.write(id, &[byte])
    }

    pub fn resize(&self, id: &str, cols: u16, rows: u16) -> Result<()> {
        let session = self.get(id)?;
        session
            .master
            .lock()
            .unwrap()
            .resize(PtySize {
                rows,
                cols,
                pixel_width: 0,
                pixel_height: 0,
            })
            .map_err(|e| anyhow!("resize: {e}"))?;
        Ok(())
    }

    /// Return all output produced after `offset`. If no new output exists,
    /// returns an empty string with the same offset.
    pub fn read(&self, id: &str, offset: u64) -> Result<ReadResult> {
        let session = self.get(id)?;
        let buf = session.buffer.lock().unwrap();
        let total = *session.total_bytes.lock().unwrap();
        let head = total.saturating_sub(buf.len() as u64);
        let start = if offset < head {
            0
        } else {
            (offset - head) as usize
        };
        let slice = if start >= buf.len() {
            &[][..]
        } else {
            &buf[start..]
        };
        Ok(ReadResult {
            data: String::from_utf8_lossy(slice).to_string(),
            next_offset: total,
            closed: session.closed.load(Ordering::SeqCst),
        })
    }

    /// High-level convenience: write `command + "\n"`, then drain output
    /// until the stream goes quiet for `idle_ms` (or `timeout_ms` elapses).
    pub fn exec(
        &self,
        id: &str,
        command: &str,
        idle_ms: u64,
        timeout_ms: u64,
    ) -> Result<ExecResult> {
        let session = self.get(id)?;
        let start_offset = *session.total_bytes.lock().unwrap();

        // Write command + newline. Use \r\n on Windows.
        let line = if cfg!(target_os = "windows") {
            format!("{}\r\n", command)
        } else {
            format!("{}\n", command)
        };
        {
            let mut w = session.writer.lock().unwrap();
            w.write_all(line.as_bytes()).context("write command")?;
            w.flush().ok();
        }
        *session.last_activity.lock().unwrap() = Instant::now();

        let started = Instant::now();
        let idle = Duration::from_millis(idle_ms.max(50));
        let deadline = started + Duration::from_millis(timeout_ms.max(idle_ms + 100));

        let mut last_seen = *session.total_bytes.lock().unwrap();
        let mut last_change = Instant::now();
        loop {
            if session.closed.load(Ordering::SeqCst) {
                break;
            }
            let total = *session.total_bytes.lock().unwrap();
            if total != last_seen {
                last_seen = total;
                last_change = Instant::now();
            }
            if total > start_offset && last_change.elapsed() >= idle {
                break;
            }
            if Instant::now() >= deadline {
                let buf = session.buffer.lock().unwrap();
                let total = *session.total_bytes.lock().unwrap();
                let head = total.saturating_sub(buf.len() as u64);
                let s = if start_offset < head {
                    0
                } else {
                    (start_offset - head) as usize
                };
                let slice = if s >= buf.len() { &[][..] } else { &buf[s..] };
                return Ok(ExecResult {
                    data: String::from_utf8_lossy(slice).to_string(),
                    next_offset: total,
                    closed: session.closed.load(Ordering::SeqCst),
                    timed_out: true,
                });
            }
            thread::sleep(Duration::from_millis(25));
        }

        let buf = session.buffer.lock().unwrap();
        let total = *session.total_bytes.lock().unwrap();
        let head = total.saturating_sub(buf.len() as u64);
        let s = if start_offset < head {
            0
        } else {
            (start_offset - head) as usize
        };
        let slice = if s >= buf.len() { &[][..] } else { &buf[s..] };
        Ok(ExecResult {
            data: String::from_utf8_lossy(slice).to_string(),
            next_offset: total,
            closed: session.closed.load(Ordering::SeqCst),
            timed_out: false,
        })
    }
}

fn info_for(s: &Session) -> SessionInfo {
    let now = Instant::now();
    SessionInfo {
        id: s.id.clone(),
        shell: s.shell.clone(),
        cwd: s.cwd.clone(),
        cols: s.cols,
        rows: s.rows,
        closed: s.closed.load(Ordering::SeqCst),
        total_bytes: *s.total_bytes.lock().unwrap(),
        uptime_secs: now.duration_since(s.created).as_secs(),
        idle_secs: now
            .duration_since(*s.last_activity.lock().unwrap())
            .as_secs(),
    }
}

fn default_shell() -> Option<String> {
    if cfg!(target_os = "windows") {
        Some(std::env::var("COMSPEC").unwrap_or_else(|_| "cmd.exe".into()))
    } else {
        std::env::var("SHELL").ok().or_else(|| {
            for candidate in ["/bin/bash", "/bin/zsh", "/bin/sh"] {
                if std::path::Path::new(candidate).exists() {
                    return Some(candidate.to_string());
                }
            }
            None
        })
    }
}

// ----- Tests -----

#[cfg(test)]
mod tests {
    use super::*;

    fn pause(ms: u64) {
        std::thread::sleep(Duration::from_millis(ms));
    }

    #[test]
    fn open_lists_and_closes_session() {
        let mgr = TerminalManager::new();
        let info = mgr.open(None, None, Some(80), Some(24)).expect("open");
        assert_eq!(info.cols, 80);
        assert_eq!(info.rows, 24);
        assert!(!info.closed);
        let listed = mgr.list();
        assert_eq!(listed.len(), 1);
        assert_eq!(listed[0].id, info.id);
        mgr.close(&info.id).expect("close");
        assert!(mgr.list().is_empty());
    }

    #[test]
    fn exec_returns_command_output() {
        let mgr = TerminalManager::new();
        let info = mgr.open(None, None, Some(80), Some(24)).expect("open");
        // Drain the shell prompt first.
        pause(150);
        let _ = mgr.read(&info.id, 0);

        let result = mgr
            .exec(&info.id, "echo hello-from-pty-test", 200, 5_000)
            .expect("exec");
        assert!(!result.timed_out, "exec should not time out");
        assert!(
            result.data.contains("hello-from-pty-test"),
            "expected echo output, got: {:?}",
            result.data
        );

        mgr.close(&info.id).ok();
    }

    #[test]
    fn read_resumes_from_offset() {
        let mgr = TerminalManager::new();
        let info = mgr.open(None, None, Some(80), Some(24)).expect("open");
        pause(150);

        let first = mgr
            .exec(&info.id, "printf abc", 200, 3_000)
            .expect("first exec");
        let second_offset = first.next_offset;
        let second = mgr
            .exec(&info.id, "printf xyz", 200, 3_000)
            .expect("second exec");
        // The data we got from the second exec should not contain "abc"
        // because we passed in the offset *after* the first exec finished.
        assert!(!second.data.contains("abc"), "got: {:?}", second.data);
        assert!(second.data.contains("xyz"), "got: {:?}", second.data);
        // Re-reading from the earlier offset should still return both.
        let replay = mgr
            .read(&info.id, second_offset.saturating_sub(20))
            .expect("read");
        assert!(replay.next_offset >= second_offset);
        mgr.close(&info.id).ok();
    }

    #[test]
    fn signal_writes_ctrl_c_byte() {
        let mgr = TerminalManager::new();
        let info = mgr.open(None, None, Some(80), Some(24)).expect("open");
        pause(150);
        // Should not error even with no foreground process; the byte is
        // delivered to the shell which interprets it as a line discard.
        mgr.signal(&info.id, "ctrl-c").expect("signal");
        mgr.close(&info.id).ok();
    }

    #[test]
    fn unknown_session_returns_error() {
        let mgr = TerminalManager::new();
        assert!(mgr.read("does-not-exist", 0).is_err());
        assert!(mgr.write("does-not-exist", b"hi").is_err());
        assert!(mgr.signal("does-not-exist", "ctrl-c").is_err());
        assert!(mgr.resize("does-not-exist", 80, 24).is_err());
        assert!(mgr.close("does-not-exist").is_err());
    }

    #[tokio::test]
    async fn shell_run_returns_stdout_and_exit_code() {
        let result = shell_run("printf shell-run-ok".to_string(), 5_000)
            .await
            .expect("shell_run");
        assert!(!result.timed_out);
        assert_eq!(result.exit_code, 0);
        assert_eq!(result.stdout, "shell-run-ok");
    }

    #[tokio::test]
    async fn shell_run_marks_background_command_not_found_as_failure() {
        let result = shell_run(
            "definitely_missing_agixt_desktop_command &".to_string(),
            5_000,
        )
        .await
        .expect("shell_run");
        assert!(!result.timed_out);
        assert_ne!(result.exit_code, 0);
        assert!(result.stderr.to_lowercase().contains("not found"));
    }

    #[tokio::test]
    async fn shell_run_detaches_background_command_pipes() {
        let result = shell_run("sh -c 'printf started; sleep 5' &".to_string(), 1_500)
            .await
            .expect("shell_run");
        assert!(!result.timed_out);
        assert_eq!(result.exit_code, 0);
        assert!(result.stdout.contains("started background command pid"));
    }

    #[test]
    fn sudo_auth_required_detects_noninteractive_sudo_prompt() {
        let result = ShellRunResult {
            command: "sudo apt update".to_string(),
            stdout: String::new(),
            stderr: "sudo: a password is required".to_string(),
            exit_code: 1,
            timed_out: false,
        };
        assert!(sudo_auth_required(&result));

        let result = ShellRunResult {
            command: "sudo apt update".to_string(),
            stdout: String::new(),
            stderr: "E: Unable to locate package nope".to_string(),
            exit_code: 100,
            timed_out: false,
        };
        assert!(!sudo_auth_required(&result));
    }

    #[test]
    fn desktop_path_includes_common_app_locations() {
        let path = desktop_path().to_string_lossy().to_string();
        assert!(path.contains("/snap/bin"));
        assert!(path.contains("/var/lib/flatpak/exports/bin"));
    }
}
