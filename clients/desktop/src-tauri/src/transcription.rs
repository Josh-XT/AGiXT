//! Local audiobook transcription via whisper-rs.
//!
//! This is the Tauri-side replacement for the AGiXT server's
//! `_transcribe_audiobook` pipeline. The server route still exists as a
//! fallback for headless deploys, but on a desktop install we'd rather
//! keep a 60-300 MB audio file on the user's machine than ship every
//! audiobook to a remote voice server.
//!
//! Architecture:
//!
//!   1. `transcribe_audiobook` is a Tauri command. The audible page
//!      invokes it after a fresh download lands. We accept the audio
//!      path, the asin, and the AGiXT server credentials so we can
//!      POST the finished transcript back to the user's account.
//!   2. The model file (`ggml-base.en.bin` by default) lives in the
//!      app's cache directory under `whisper/`. It's downloaded once
//!      from Hugging Face on first use; subsequent runs hit disk.
//!   3. We decode the audio file in-process via symphonia → resample
//!      to 16 kHz mono f32 PCM (whisper's native format).
//!   4. The samples are fed to whisper-rs in 5-minute windows so
//!      progress events fire steadily and a long book doesn't sit
//!      silent for 20 minutes. Each window's segments are time-shifted
//!      by the chunk offset and accumulated.
//!   5. After transcription, we POST the whole transcript to
//!      `/v1/audible/book/{asin}/transcript/upload` so the rest of
//!      AGiXT (and other devices) can read it back.
//!
//! Progress is emitted on the `audible-transcription-progress` event
//! with `{ asin, state, percent, message }` payloads. The audible page
//! subscribes via `event.listen` and re-renders its status block.

use std::fs::File;
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};

use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use tauri::{AppHandle, Emitter, Manager, Runtime};
use tracing::{info, warn};

use crate::api::build_client;

const PROGRESS_EVENT: &str = "audible-transcription-progress";
const CHUNK_WINDOW_SECONDS: u32 = 300;
const TARGET_SAMPLE_RATE: u32 = 16_000;

/// Public input to the Tauri command. The frontend hands us everything
/// we need to do the work + report it back.
#[derive(Debug, Deserialize)]
pub struct TranscribeAudiobookRequest {
    pub asin: String,
    pub audio_path: String,
    pub server_url: String,
    pub jwt: String,
    /// Optional explicit agent id; the server uses it to namespace the
    /// upload. When omitted we let the server fall back to the default
    /// agent for the JWT.
    #[serde(default)]
    pub agent_id: Option<String>,
    /// `tiny`/`base`/`small`/`medium`/`large-v3`. Defaults to
    /// `base.en` which is small and very fast on CPU.
    #[serde(default)]
    pub model: Option<String>,
    /// IETF language tag (e.g. "en", "de"). Defaults to "en". Leave
    /// blank to let whisper auto-detect.
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

#[derive(Debug, Serialize, Clone)]
struct ProgressEvent<'a> {
    asin: &'a str,
    state: &'a str,
    /// 0.0 - 1.0
    progress: f32,
    message: &'a str,
}

#[derive(Debug, Serialize)]
struct TranscriptSegment {
    start: u64, // ms
    end: u64,   // ms
    text: String,
}

#[derive(Debug, Serialize)]
struct UploadedTranscript {
    language: String,
    source: &'static str,
    segments: Vec<TranscriptSegment>,
}

/// Tauri command entry point.
#[tauri::command]
pub async fn audible_transcribe<R: Runtime>(
    app: AppHandle<R>,
    req: TranscribeAudiobookRequest,
) -> Result<TranscribeAudiobookResponse, String> {
    run_transcription(app, req).await.map_err(|e| {
        warn!("audible_transcribe: {e:#}");
        format!("{e:#}")
    })
}

async fn run_transcription<R: Runtime>(
    app: AppHandle<R>,
    req: TranscribeAudiobookRequest,
) -> Result<TranscribeAudiobookResponse> {
    let asin = req.asin.clone();
    let model_choice = req.model.as_deref().unwrap_or("base.en").to_string();
    let language = req.language.as_deref().unwrap_or("en").to_string();
    let audio_path = PathBuf::from(&req.audio_path);
    if !audio_path.is_file() {
        return Err(anyhow!("audio file not found at {}", audio_path.display()));
    }

    let app_for_events = app.clone();
    let emit = move |state: &str, progress: f32, message: &str| {
        let _ = app_for_events.emit(
            PROGRESS_EVENT,
            ProgressEvent {
                asin: &asin,
                state,
                progress,
                message,
            },
        );
    };
    emit("preparing", 0.0, "Preparing local transcription…");

    // 1) Make sure we have the model on disk.
    let model_path = ensure_whisper_model(&app, &model_choice, &emit).await?;

    // 2) Decode the audio file to 16 kHz mono f32 PCM.
    emit("decoding", 0.05, "Decoding audio for transcription…");
    let samples = tokio::task::spawn_blocking({
        let audio_path = audio_path.clone();
        move || decode_to_mono_f32_16khz(&audio_path)
    })
    .await
    .context("decode audio task panicked")??;
    let total_seconds = (samples.len() as f32) / (TARGET_SAMPLE_RATE as f32);
    info!(
        "audible_transcribe: loaded {} samples ({:.1}s) from {}",
        samples.len(),
        total_seconds,
        audio_path.display()
    );

    // 3) Run whisper on consecutive windows so we can emit useful
    //    progress + each call stays bounded in memory/time.
    emit("transcribing", 0.1, "Loading whisper model…");
    let segments = tokio::task::spawn_blocking({
        let asin = req.asin.clone();
        let app = app.clone();
        let language = language.clone();
        let model_path = model_path.clone();
        move || transcribe_windows(&app, &asin, &model_path, &language, samples)
    })
    .await
    .context("whisper task panicked")??;

    // 4) Upload to AGiXT.
    emit("uploading", 0.97, "Uploading transcript to AGiXT…");
    let uploaded = upload_transcript(&req, &segments, &language)
        .await
        .map_err(|e| {
            warn!("audible_transcribe upload failed: {e:#}");
            e
        })
        .is_ok();

    let segment_count = segments.len();
    let final_msg = if uploaded {
        format!("Done — {segment_count} segments")
    } else {
        format!("Done — {segment_count} segments (upload failed; retry later)")
    };
    let _ = app.emit(
        PROGRESS_EVENT,
        ProgressEvent {
            asin: &req.asin,
            state: "ready",
            progress: 1.0,
            message: &final_msg,
        },
    );

    Ok(TranscribeAudiobookResponse {
        asin: req.asin,
        segment_count,
        duration_seconds: total_seconds,
        uploaded,
    })
}

// ---------- model management ------------------------------------------

/// Resolve `<app cache>/whisper/<filename>`. Downloads from
/// Hugging Face on first use.
async fn ensure_whisper_model<R: Runtime, F>(
    app: &AppHandle<R>,
    choice: &str,
    emit: &F,
) -> Result<PathBuf>
where
    F: Fn(&str, f32, &str),
{
    let filename = match choice {
        "tiny" | "tiny.en" | "base" | "base.en" | "small" | "small.en" | "medium"
        | "medium.en" | "large-v3" => format!("ggml-{}.bin", choice),
        other => return Err(anyhow!("unsupported whisper model: {other}")),
    };
    let cache_root = app
        .path()
        .app_cache_dir()
        .context("resolve app cache dir")?;
    let dir = cache_root.join("whisper");
    std::fs::create_dir_all(&dir).context("create whisper cache dir")?;
    let target = dir.join(&filename);
    if target.is_file() {
        return Ok(target);
    }

    // Hugging Face hosts pre-converted GGML models on `ggerganov/whisper.cpp`.
    let url = format!(
        "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/{}",
        filename
    );
    emit(
        "downloading_model",
        0.0,
        &format!("Downloading {filename} (one-time)…"),
    );
    let client = build_client()?;
    let mut resp = client
        .get(&url)
        .send()
        .await
        .with_context(|| format!("download whisper model from {url}"))?;
    if !resp.status().is_success() {
        return Err(anyhow!(
            "model download {} returned http {}",
            url,
            resp.status()
        ));
    }
    let total = resp.content_length();
    let tmp = target.with_extension("partial");
    let mut file = BufWriter::new(File::create(&tmp).context("create whisper model tmp")?);
    let mut downloaded: u64 = 0;
    while let Some(chunk) = resp.chunk().await.context("download chunk")? {
        file.write_all(&chunk).context("write whisper model chunk")?;
        downloaded += chunk.len() as u64;
        if let Some(total) = total {
            let pct = (downloaded as f32 / total as f32).clamp(0.0, 1.0);
            emit(
                "downloading_model",
                pct,
                &format!(
                    "Downloading whisper model… {:.0}%",
                    pct * 100.0
                ),
            );
        }
    }
    file.flush().ok();
    drop(file);
    std::fs::rename(&tmp, &target).context("finalize whisper model file")?;
    info!("whisper model written to {}", target.display());
    Ok(target)
}

// ---------- audio decoding -------------------------------------------

fn decode_to_mono_f32_16khz(path: &Path) -> Result<Vec<f32>> {
    use symphonia::core::audio::SampleBuffer;
    use symphonia::core::codecs::{DecoderOptions, CODEC_TYPE_NULL};
    use symphonia::core::errors::Error as SymError;
    use symphonia::core::formats::FormatOptions;
    use symphonia::core::io::MediaSourceStream;
    use symphonia::core::meta::MetadataOptions;
    use symphonia::core::probe::Hint;

    let file = File::open(path).with_context(|| format!("open {}", path.display()))?;
    let mss = MediaSourceStream::new(Box::new(file), Default::default());

    let mut hint = Hint::new();
    if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
        hint.with_extension(ext);
    }

    let probed = symphonia::default::get_probe()
        .format(
            &hint,
            mss,
            &FormatOptions::default(),
            &MetadataOptions::default(),
        )
        .context("probe audio container")?;
    let mut format = probed.format;

    let track = format
        .tracks()
        .iter()
        .find(|t| t.codec_params.codec != CODEC_TYPE_NULL)
        .ok_or_else(|| anyhow!("no decodable audio track in {}", path.display()))?
        .clone();
    let track_id = track.id;
    let src_rate = track
        .codec_params
        .sample_rate
        .ok_or_else(|| anyhow!("source sample rate unknown"))?;
    let src_channels = track
        .codec_params
        .channels
        .ok_or_else(|| anyhow!("source channel layout unknown"))?
        .count();

    let mut decoder = symphonia::default::get_codecs()
        .make(&track.codec_params, &DecoderOptions::default())
        .context("build audio decoder")?;

    let mut mono = Vec::<f32>::with_capacity(1 << 20);
    loop {
        let packet = match format.next_packet() {
            Ok(p) => p,
            Err(SymError::IoError(e)) if e.kind() == std::io::ErrorKind::UnexpectedEof => break,
            Err(SymError::ResetRequired) => break,
            Err(e) => return Err(anyhow!("read audio packet: {e}")),
        };
        if packet.track_id() != track_id {
            continue;
        }
        match decoder.decode(&packet) {
            Ok(decoded) => {
                let spec = *decoded.spec();
                let mut sample_buf = SampleBuffer::<f32>::new(decoded.capacity() as u64, spec);
                sample_buf.copy_interleaved_ref(decoded);
                let samples = sample_buf.samples();
                if src_channels <= 1 {
                    mono.extend_from_slice(samples);
                } else {
                    // Average all channels per frame to mono.
                    let chans = src_channels;
                    for frame in samples.chunks_exact(chans) {
                        let s: f32 = frame.iter().sum::<f32>() / (chans as f32);
                        mono.push(s);
                    }
                }
            }
            Err(SymError::DecodeError(e)) => {
                // Skip a corrupt packet — continue reading.
                warn!("decode packet: {e}");
                continue;
            }
            Err(e) => return Err(anyhow!("decode audio: {e}")),
        }
    }

    if src_rate == TARGET_SAMPLE_RATE {
        return Ok(mono);
    }
    Ok(linear_resample(&mono, src_rate, TARGET_SAMPLE_RATE))
}

/// Cheap linear-interpolation resampler. Whisper is not picky about
/// resample fidelity for transcription accuracy — anti-aliased
/// resampling would add a heavy dependency for negligible gain.
fn linear_resample(input: &[f32], src_rate: u32, dst_rate: u32) -> Vec<f32> {
    if input.is_empty() || src_rate == 0 || dst_rate == 0 {
        return Vec::new();
    }
    let ratio = (dst_rate as f64) / (src_rate as f64);
    let out_len = ((input.len() as f64) * ratio).round() as usize;
    let mut out = Vec::with_capacity(out_len);
    for i in 0..out_len {
        let src_pos = (i as f64) / ratio;
        let src_idx = src_pos.floor() as usize;
        let frac = (src_pos - src_idx as f64) as f32;
        if src_idx + 1 < input.len() {
            let a = input[src_idx];
            let b = input[src_idx + 1];
            out.push(a + (b - a) * frac);
        } else if src_idx < input.len() {
            out.push(input[src_idx]);
        } else {
            break;
        }
    }
    out
}

// ---------- whisper inference ----------------------------------------

fn transcribe_windows<R: Runtime>(
    app: &AppHandle<R>,
    asin: &str,
    model_path: &Path,
    language: &str,
    samples: Vec<f32>,
) -> Result<Vec<TranscriptSegment>> {
    use whisper_rs::{FullParams, SamplingStrategy, WhisperContext, WhisperContextParameters};

    let ctx_params = WhisperContextParameters::default();
    let ctx = WhisperContext::new_with_params(
        model_path
            .to_str()
            .ok_or_else(|| anyhow!("non-utf8 whisper model path"))?,
        ctx_params,
    )
    .context("load whisper model")?;
    let mut state = ctx.create_state().context("create whisper state")?;

    let total_seconds = samples.len() as f32 / TARGET_SAMPLE_RATE as f32;
    let cancelled = AtomicBool::new(false);
    let _cancel = &cancelled; // reserved for future cancel command

    let chunk_samples = (CHUNK_WINDOW_SECONDS as usize) * (TARGET_SAMPLE_RATE as usize);
    // 30-second overlap between consecutive windows. Whisper has poor
    // right-context at the very end of each window — the last token or
    // two often hallucinate badly (we've seen e.g. "League of Legends"
    // inserted into the Art of War). Re-processing the last 30s of
    // each window as the first 30s of the next window gives the model
    // full forward context for those edge segments. Segments whose
    // start falls inside the previous window's accepted range are
    // dropped at concat time.
    let overlap_samples = 30usize * (TARGET_SAMPLE_RATE as usize);
    let advance_samples = chunk_samples.saturating_sub(overlap_samples).max(1);
    let mut all = Vec::<TranscriptSegment>::new();
    // Boundary used to discard overlap segments: any segment whose
    // start (ms) is below this and that has a similar text to a
    // segment we already accepted ending nearby is a duplicate.
    let mut last_accepted_end_ms: u64 = 0;
    let mut offset = 0usize;
    let mut window_idx: u32 = 0;
    let total_windows = ((samples.len() + advance_samples - 1) / advance_samples).max(1) as u32;

    while offset < samples.len() && !cancelled.load(Ordering::Relaxed) {
        let end = (offset + chunk_samples).min(samples.len());
        let window = &samples[offset..end];
        let window_start_ms = ((offset as u64) * 1000) / TARGET_SAMPLE_RATE as u64;

        let pct = ((window_idx as f32) / (total_windows as f32) * 0.85) + 0.10;
        let _ = app.emit(
            PROGRESS_EVENT,
            ProgressEvent {
                asin,
                state: "transcribing",
                progress: pct,
                message: &format!(
                    "Transcribing window {} of {} (offset {:.0}s / {:.0}s)…",
                    window_idx + 1,
                    total_windows,
                    window_start_ms as f32 / 1000.0,
                    total_seconds
                ),
            },
        );

        // Beam search instead of greedy — costs ~2x CPU but cuts
        // boundary hallucinations (the model commits less aggressively
        // to a single token sequence). beam_size=5 + best_of=5 matches
        // the openai-whisper Python library's default.
        let mut params = FullParams::new(SamplingStrategy::BeamSearch {
            beam_size: 5,
            patience: 1.0,
        });
        params.set_print_special(false);
        params.set_print_progress(false);
        params.set_print_realtime(false);
        params.set_print_timestamps(false);
        params.set_translate(false);
        // Higher no_speech threshold makes whisper bail on near-silent
        // tokens rather than inventing words for them. 0.6 is the
        // openai-whisper default; whisper-rs ships 0.6 too but we set
        // it explicitly so downstream behaviour is stable across
        // whisper-rs versions.
        params.set_no_speech_thold(0.6);
        // Suppress the entropy collapse that produces "thanks for
        // watching" / "subscribe" / repeated phrases. 2.4 is openai
        // whisper's default for `compression_ratio_threshold` analog.
        params.set_entropy_thold(2.4);
        if !language.is_empty() {
            params.set_language(Some(language));
        }
        // Single-threaded by default — whisper-rs sets a safe value
        // based on the available CPU count, which we leave alone.

        state.full(params, window).context("whisper full inference")?;

        let n = state.full_n_segments().context("count segments")?;
        for i in 0..n {
            let text = state
                .full_get_segment_text(i)
                .context("read segment text")?
                .trim()
                .to_string();
            if text.is_empty() {
                continue;
            }
            // whisper.cpp emits markers like `[BLANK_AUDIO]`, `[MUSIC]`,
            // `(silence)` when no speech is found in the window. They
            // aren't narration — drop them so they don't pollute the
            // read-along.
            if is_whisper_special_token(&text) {
                continue;
            }
            // whisper returns timestamps in centiseconds (10 ms units).
            let t0 = state
                .full_get_segment_t0(i)
                .context("read segment t0")? as u64;
            let t1 = state
                .full_get_segment_t1(i)
                .context("read segment t1")? as u64;
            let abs_start = window_start_ms + t0 * 10;
            let abs_end = window_start_ms + t1 * 10;
            // For all windows after the first, drop segments inside the
            // overlap region (their absolute start is earlier than the
            // last accepted segment's end). They were already covered
            // with better right-context in the previous window.
            if window_idx > 0 && abs_start + 200 < last_accepted_end_ms {
                continue;
            }
            last_accepted_end_ms = abs_end.max(last_accepted_end_ms);
            all.push(TranscriptSegment {
                start: abs_start,
                end: abs_end,
                text,
            });
        }
        offset = if end >= samples.len() {
            end
        } else {
            offset + advance_samples
        };
        window_idx += 1;
    }

    Ok(all)
}

/// True when `text` looks like a whisper.cpp non-speech marker: a string
/// fully wrapped in `[]` or `()` whose interior is just letters,
/// underscores, and spaces (`[BLANK_AUDIO]`, `[MUSIC]`, `(silence)`,
/// etc.). Real narration ends in punctuation or words, never matches.
fn is_whisper_special_token(text: &str) -> bool {
    let t = text.trim();
    let inner = if t.starts_with('[') && t.ends_with(']') && t.len() >= 2 {
        Some(&t[1..t.len() - 1])
    } else if t.starts_with('(') && t.ends_with(')') && t.len() >= 2 {
        Some(&t[1..t.len() - 1])
    } else {
        None
    };
    match inner {
        Some(inner) if !inner.is_empty() => inner
            .chars()
            .all(|c| c.is_ascii_alphabetic() || c == '_' || c == ' '),
        _ => false,
    }
}

// ---------- upload back to AGiXT -------------------------------------

async fn upload_transcript(
    req: &TranscribeAudiobookRequest,
    segments: &[TranscriptSegment],
    language: &str,
) -> Result<()> {
    let payload = UploadedTranscript {
        language: language.to_string(),
        source: "agixt-desktop",
        // The endpoint clones the data, so a serialized borrow is fine.
        segments: segments
            .iter()
            .map(|s| TranscriptSegment {
                start: s.start,
                end: s.end,
                text: s.text.clone(),
            })
            .collect(),
    };
    let mut url = format!(
        "{}/v1/audible/book/{}/transcript/upload",
        req.server_url.trim_end_matches('/'),
        req.asin
    );
    if let Some(agent_id) = &req.agent_id {
        url.push_str(&format!("?agent_id={}", agent_id));
    }
    let client = build_client()?;
    let resp = client
        .post(&url)
        .bearer_auth(&req.jwt)
        .json(&payload)
        .send()
        .await
        .with_context(|| format!("POST {url}"))?;
    if !resp.status().is_success() {
        let status = resp.status();
        let body = resp.text().await.unwrap_or_default();
        return Err(anyhow!("transcript upload http {}: {}", status, body));
    }
    Ok(())
}

