//! Local hardware probe + ezLocalai default-model selection.
//!
//! Used by the "Local" login mode to decide which Qwen GGUF the
//! one-click installer should pre-configure. We *do not* download the
//! model here — we just inspect the machine and recommend a tier.
//!
//! Detection strategy is platform-aware but stays out of new heavy
//! dependencies (no `sysinfo` crate) so the installer flow can run on
//! whatever target the desktop app builds for. We shell out to
//! standard tools that ship with each OS:
//!   * NVIDIA VRAM:   `nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits`
//!   * Linux RAM:     parse `/proc/meminfo`
//!   * macOS RAM:     `sysctl -n hw.memsize` + `vm_stat`
//!   * Windows RAM:   `wmic ComputerSystem get TotalPhysicalMemory` (fallback to PowerShell CIM)
//!
//! All shells are best-effort: failure to detect any single signal
//! degrades gracefully to the CPU-only / unknown-VRAM path rather than
//! erroring out. The user can still proceed; we just won't be able to
//! pre-fill the model recommendation.

use serde::{Deserialize, Serialize};
use std::process::Stdio;
use std::time::Duration;

/// HuggingFace repo IDs Josh chose for ezLocalai's defaults. These are
/// product decisions — do not substitute.
pub const MODEL_LOW: &str = "unsloth/Qwen3.5-4B-GGUF";
pub const MODEL_MID: &str = "unsloth/Qwen3.5-9B-GGUF";
pub const MODEL_HIGH: &str = "unsloth/Qwen3.6-35B-A3B-GGUF";

pub const MAX_TOKENS_CONSTRAINED: u32 = 8_192;
pub const MAX_TOKENS_LOW: u32 = 32_000;
pub const MAX_TOKENS_MID: u32 = 128_000;
pub const MAX_TOKENS_HIGH: u32 = 250_000;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GpuInfo {
    pub name: String,
    /// Total VRAM in MiB. `None` when we can't read it (e.g. AMD/Intel
    /// without a tool we know how to query).
    pub vram_mib: Option<u64>,
    pub vendor: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HardwareInfo {
    pub os: String,
    pub arch: String,
    pub cpu_cores: u32,
    /// Total system RAM in MiB.
    pub total_ram_mib: u64,
    /// Available RAM in MiB (may equal `total_ram_mib` if the OS
    /// doesn't expose a separate "available" figure cheaply).
    pub available_ram_mib: u64,
    pub gpus: Vec<GpuInfo>,
    /// Largest VRAM across detected GPUs, in MiB. `None` when no GPU
    /// is detected or VRAM is unknown.
    pub max_vram_mib: Option<u64>,
    /// One of `"low_gpu"`, `"mid_gpu"`, `"high_gpu"`, `"cpu"`,
    /// `"constrained"`. Drives the default-model selection.
    pub tier: String,
    /// HuggingFace repo ID of the recommended ezLocalai model.
    pub recommended_model: String,
    /// Default ezLocalai max-token/context setting to pair with the
    /// hardware-tiered model.
    pub recommended_max_tokens: u32,
    /// Human-readable explanation for the UI.
    pub recommendation_note: String,
}

pub async fn probe() -> HardwareInfo {
    let os = std::env::consts::OS.to_string();
    let arch = std::env::consts::ARCH.to_string();
    let cpu_cores = std::thread::available_parallelism()
        .map(|n| n.get() as u32)
        .unwrap_or(1);

    let (total_ram_mib, available_ram_mib) = ram_mib().await;
    let gpus = detect_gpus().await;
    let max_vram_mib = gpus.iter().filter_map(|g| g.vram_mib).max();

    let (tier, recommended_model, recommended_max_tokens, recommendation_note) =
        choose_tier(max_vram_mib, total_ram_mib, available_ram_mib);

    HardwareInfo {
        os,
        arch,
        cpu_cores,
        total_ram_mib,
        available_ram_mib,
        gpus,
        max_vram_mib,
        tier,
        recommended_model,
        recommended_max_tokens,
        recommendation_note,
    }
}

/// Pick the ezLocalai default-model tier from VRAM/RAM. Mirrors the
/// product spec: <12GB VRAM → 4B, 13–17 → 9B, 24+ → 35B-A3B; CPU-only
/// with ≥12GB RAM → 4B; <16GB total RAM → 4B with a slow-path warning.
fn choose_tier(
    max_vram_mib: Option<u64>,
    total_ram_mib: u64,
    available_ram_mib: u64,
) -> (String, String, u32, String) {
    const GIB: u64 = 1024;

    // GPU path first — VRAM is the primary signal.
    if let Some(vram) = max_vram_mib {
        if vram >= 24 * GIB {
            return (
                "high_gpu".into(),
                MODEL_HIGH.into(),
                MAX_TOKENS_HIGH,
                "24GB+ VRAM detected — using the 35B A3B mixture-of-experts model for best quality."
                    .into(),
            );
        }
        if vram >= 13 * GIB {
            return (
                "mid_gpu".into(),
                MODEL_MID.into(),
                MAX_TOKENS_MID,
                "13GB+ VRAM detected below the 24GB high tier — using the 9B model.".into(),
            );
        }
        // <12GB GPU still beats CPU; route to 4B.
        return (
            "low_gpu".into(),
            MODEL_LOW.into(),
            MAX_TOKENS_LOW,
            "12GB or less VRAM detected — using the 4B model.".into(),
        );
    }

    // No GPU detected. Use RAM to decide between "ok" and "slow".
    if total_ram_mib < 16 * GIB {
        return (
            "constrained".into(),
            MODEL_LOW.into(),
            MAX_TOKENS_CONSTRAINED,
            "No GPU detected and under 16GB RAM. The 4B model will run, but responses may be slow. \
             For best performance, an NVIDIA GPU with 24GB+ VRAM is recommended (3090, 4090, or 5090)."
                .into(),
        );
    }
    if available_ram_mib < 12 * GIB {
        return (
            "constrained".into(),
            MODEL_LOW.into(),
            MAX_TOKENS_CONSTRAINED,
            "No GPU detected and less than 12GB RAM is currently available. The 4B model will run, \
             but closing other apps first is recommended. For best performance, use an NVIDIA GPU \
             with 24GB+ VRAM (3090, 4090, or 5090)."
                .into(),
        );
    }
    (
        "cpu".into(),
        MODEL_LOW.into(),
        MAX_TOKENS_LOW,
        "No GPU detected. The 4B model will run on CPU. For better performance, an NVIDIA GPU \
         with 24GB+ VRAM is recommended (3090, 4090, or 5090)."
            .into(),
    )
}

async fn detect_gpus() -> Vec<GpuInfo> {
    let mut gpus = Vec::new();
    if let Some(nv) = nvidia_smi().await {
        gpus.extend(nv);
    }
    // No AMD/Intel VRAM probe yet — those users still get a working
    // installer, just without pre-filled VRAM. The UI surfaces this.
    gpus
}

async fn nvidia_smi() -> Option<Vec<GpuInfo>> {
    let out = run_short(
        "nvidia-smi",
        &[
            "--query-gpu=name,memory.total",
            "--format=csv,noheader,nounits",
        ],
        2_500,
    )
    .await?;
    if out.trim().is_empty() {
        return None;
    }
    let mut gpus = Vec::new();
    for line in out.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        // Format: "NVIDIA GeForce RTX 4090, 24564"
        let mut parts = line.splitn(2, ',');
        let name = parts.next()?.trim().to_string();
        let mib = parts.next().and_then(|s| s.trim().parse::<u64>().ok());
        gpus.push(GpuInfo {
            name,
            vram_mib: mib,
            vendor: "nvidia".into(),
        });
    }
    if gpus.is_empty() {
        None
    } else {
        Some(gpus)
    }
}

#[cfg(target_os = "linux")]
async fn ram_mib() -> (u64, u64) {
    // /proc/meminfo: lines like "MemTotal:       16384000 kB"
    let raw = match tokio::fs::read_to_string("/proc/meminfo").await {
        Ok(s) => s,
        Err(_) => return (0, 0),
    };
    let mut total_kib: u64 = 0;
    let mut avail_kib: u64 = 0;
    for line in raw.lines() {
        if let Some(rest) = line.strip_prefix("MemTotal:") {
            total_kib = parse_kib(rest);
        } else if let Some(rest) = line.strip_prefix("MemAvailable:") {
            avail_kib = parse_kib(rest);
        }
    }
    if avail_kib == 0 {
        avail_kib = total_kib;
    }
    (total_kib / 1024, avail_kib / 1024)
}

#[cfg(target_os = "macos")]
async fn ram_mib() -> (u64, u64) {
    let total_bytes = run_short("sysctl", &["-n", "hw.memsize"], 1_500)
        .await
        .and_then(|s| s.trim().parse::<u64>().ok())
        .unwrap_or(0);
    let total = total_bytes / 1024 / 1024;

    // vm_stat reports "Pages free", "Pages inactive" etc in 4KiB pages.
    // We approximate "available" as free + inactive + speculative.
    let mut avail_pages: u64 = 0;
    if let Some(out) = run_short("vm_stat", &[], 1_500).await {
        for line in out.lines() {
            let lower = line.to_ascii_lowercase();
            if lower.starts_with("pages free")
                || lower.starts_with("pages inactive")
                || lower.starts_with("pages speculative")
            {
                if let Some(num) = line.split(':').nth(1) {
                    let cleaned: String = num.chars().filter(|c| c.is_ascii_digit()).collect();
                    avail_pages += cleaned.parse::<u64>().unwrap_or(0);
                }
            }
        }
    }
    let avail = if avail_pages > 0 {
        (avail_pages * 4) / 1024
    } else {
        total
    };
    (total, avail)
}

#[cfg(target_os = "windows")]
async fn ram_mib() -> (u64, u64) {
    // wmic is deprecated but still present on Win10/11. Falls back to
    // PowerShell CIM for newer machines that have removed wmic.
    let total_bytes = match run_short(
        "wmic",
        &["ComputerSystem", "get", "TotalPhysicalMemory", "/value"],
        2_500,
    )
    .await
    {
        Some(s) => parse_wmic_value(&s),
        None => 0,
    };
    let total_bytes = if total_bytes == 0 {
        run_short(
            "powershell",
            &[
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory",
            ],
            3_500,
        )
        .await
        .and_then(|s| s.trim().parse::<u64>().ok())
        .unwrap_or(0)
    } else {
        total_bytes
    };
    let total = total_bytes / 1024 / 1024;

    // Available physical memory via PowerShell CIM (kilobytes).
    let avail_kib = run_short(
        "powershell",
        &[
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory",
        ],
        3_500,
    )
    .await
    .and_then(|s| s.trim().parse::<u64>().ok())
    .unwrap_or(0);
    let avail = if avail_kib > 0 {
        avail_kib / 1024
    } else {
        total
    };
    (total, avail)
}

#[cfg(target_os = "linux")]
fn parse_kib(s: &str) -> u64 {
    s.trim()
        .split_whitespace()
        .next()
        .and_then(|n| n.parse::<u64>().ok())
        .unwrap_or(0)
}

#[cfg(target_os = "windows")]
fn parse_wmic_value(s: &str) -> u64 {
    // wmic /value output: "TotalPhysicalMemory=17179869184"
    for line in s.lines() {
        if let Some(rest) = line.split_once('=') {
            if let Ok(n) = rest.1.trim().parse::<u64>() {
                return n;
            }
        }
    }
    0
}

/// Run a small command with a tight timeout, returning stdout as a
/// trimmed `String`. Any failure (missing binary, non-zero exit,
/// timeout) returns `None` — detection is best-effort.
async fn run_short(program: &str, args: &[&str], timeout_ms: u64) -> Option<String> {
    let mut cmd = tokio::process::Command::new(program);
    cmd.args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .kill_on_drop(true);
    let child = match cmd.spawn() {
        Ok(c) => c,
        Err(_) => return None,
    };
    let out =
        match tokio::time::timeout(Duration::from_millis(timeout_ms), child.wait_with_output())
            .await
        {
            Ok(Ok(o)) if o.status.success() => o,
            _ => return None,
        };
    Some(String::from_utf8_lossy(&out.stdout).to_string())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn high_gpu_picks_35b() {
        let (tier, model, max_tokens, _) = choose_tier(Some(24 * 1024), 32 * 1024, 16 * 1024);
        assert_eq!(tier, "high_gpu");
        assert_eq!(model, MODEL_HIGH);
        assert_eq!(max_tokens, MAX_TOKENS_HIGH);
    }

    #[test]
    fn mid_gpu_picks_9b() {
        let (tier, model, max_tokens, _) = choose_tier(Some(16 * 1024), 32 * 1024, 16 * 1024);
        assert_eq!(tier, "mid_gpu");
        assert_eq!(model, MODEL_MID);
        assert_eq!(max_tokens, MAX_TOKENS_MID);
    }

    #[test]
    fn low_gpu_picks_4b() {
        let (tier, model, max_tokens, _) = choose_tier(Some(8 * 1024), 16 * 1024, 8 * 1024);
        assert_eq!(tier, "low_gpu");
        assert_eq!(model, MODEL_LOW);
        assert_eq!(max_tokens, MAX_TOKENS_LOW);
    }

    #[test]
    fn cpu_only_with_enough_ram_picks_4b() {
        let (tier, model, max_tokens, _) = choose_tier(None, 32 * 1024, 16 * 1024);
        assert_eq!(tier, "cpu");
        assert_eq!(model, MODEL_LOW);
        assert_eq!(max_tokens, MAX_TOKENS_LOW);
    }

    #[test]
    fn cpu_only_constrained_warns_about_speed() {
        let (tier, model, max_tokens, note) = choose_tier(None, 12 * 1024, 6 * 1024);
        assert_eq!(tier, "constrained");
        assert_eq!(model, MODEL_LOW);
        assert_eq!(max_tokens, MAX_TOKENS_CONSTRAINED);
        assert!(note.to_ascii_lowercase().contains("slow"));
    }

    #[test]
    fn cpu_only_with_low_available_ram_uses_constrained_context() {
        let (tier, model, max_tokens, note) = choose_tier(None, 32 * 1024, 8 * 1024);
        assert_eq!(tier, "constrained");
        assert_eq!(model, MODEL_LOW);
        assert_eq!(max_tokens, MAX_TOKENS_CONSTRAINED);
        assert!(note.to_ascii_lowercase().contains("available"));
    }

    #[test]
    fn boundary_24gib_exactly_picks_high() {
        // Exact 24GiB should land in the high tier (≥24GB).
        let (tier, _, _, _) = choose_tier(Some(24 * 1024), 32 * 1024, 16 * 1024);
        assert_eq!(tier, "high_gpu");
    }

    #[test]
    fn boundary_12gib_falls_to_low() {
        // Spec says <12GB → 4B, 13–17 → 9B. 12GiB sits in low_gpu.
        let (tier, _, _, _) = choose_tier(Some(12 * 1024), 32 * 1024, 16 * 1024);
        assert_eq!(tier, "low_gpu");
    }
}
