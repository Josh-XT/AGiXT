use std::{
    io::Cursor,
    sync::{mpsc, Arc, Mutex},
    thread::{self, JoinHandle},
    time::{Duration, Instant},
};

use anyhow::{anyhow, Context};
use base64::engine::general_purpose::STANDARD as BASE64;
use base64::Engine as _;
use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use serde::Serialize;

const MAX_RECORDING_SECONDS: usize = 300;
const MIN_RECORDING_MS: u64 = 150;
const START_TIMEOUT: Duration = Duration::from_secs(8);
const STOP_TIMEOUT: Duration = Duration::from_secs(15);

#[derive(Debug, Serialize)]
pub struct VoiceStartResponse {
    pub device_name: String,
    pub sample_rate: u32,
    pub channels: u16,
}

#[derive(Debug, Serialize)]
pub struct VoiceStopResponse {
    pub audio_base64: String,
    pub mime_type: String,
    pub size_bytes: usize,
    pub duration_ms: u64,
    pub sample_count: usize,
    pub sample_rate: u32,
    pub channels: u16,
}

struct RecordedAudio {
    wav: Vec<u8>,
    duration_ms: u64,
    sample_count: usize,
    sample_rate: u32,
    channels: u16,
}

enum RecorderCommand {
    Stop,
    Cancel,
}

enum StartMessage {
    Ready(VoiceStartResponse),
    Failed(String),
}

struct RecordingSession {
    command_tx: mpsc::Sender<RecorderCommand>,
    done_rx: mpsc::Receiver<Result<RecordedAudio, String>>,
    thread: Option<JoinHandle<()>>,
}

pub struct VoiceRecorder {
    session: Mutex<Option<RecordingSession>>,
}

impl VoiceRecorder {
    pub fn new() -> Self {
        Self {
            session: Mutex::new(None),
        }
    }

    pub fn start(&self) -> anyhow::Result<VoiceStartResponse> {
        let mut active = self
            .session
            .lock()
            .map_err(|_| anyhow!("voice recorder lock poisoned"))?;
        if active.is_some() {
            return Err(anyhow!("voice recording already in progress"));
        }

        let (command_tx, command_rx) = mpsc::channel();
        let (start_tx, start_rx) = mpsc::channel();
        let (done_tx, done_rx) = mpsc::channel();
        let thread = thread::Builder::new()
            .name("agixt-desktop-voice".into())
            .spawn(move || record_on_thread(start_tx, command_rx, done_tx))
            .context("start native voice recorder thread")?;

        let info = match start_rx.recv_timeout(START_TIMEOUT) {
            Ok(StartMessage::Ready(info)) => info,
            Ok(StartMessage::Failed(error)) => {
                join_recorder_thread(thread);
                return Err(anyhow!(error));
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                let _ = command_tx.send(RecorderCommand::Cancel);
                return Err(anyhow!("Timed out starting microphone recorder"));
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                join_recorder_thread(thread);
                return Err(anyhow!("Microphone recorder stopped before starting"));
            }
        };

        tracing::info!(
            "voice recording started: device={}, sample_rate={}, channels={}",
            info.device_name,
            info.sample_rate,
            info.channels
        );
        *active = Some(RecordingSession {
            command_tx,
            done_rx,
            thread: Some(thread),
        });
        Ok(info)
    }

    pub fn stop(&self) -> anyhow::Result<VoiceStopResponse> {
        let mut session = self
            .session
            .lock()
            .map_err(|_| anyhow!("voice recorder lock poisoned"))?
            .take()
            .ok_or_else(|| anyhow!("voice recording is not active"))?;
        if session.command_tx.send(RecorderCommand::Stop).is_err() {
            if let Some(thread) = session.thread.take() {
                join_recorder_thread(thread);
            }
            return Err(anyhow!("voice recorder stopped unexpectedly"));
        }

        let audio = match session.done_rx.recv_timeout(STOP_TIMEOUT) {
            Ok(Ok(audio)) => audio,
            Ok(Err(error)) => {
                if let Some(thread) = session.thread.take() {
                    join_recorder_thread(thread);
                }
                return Err(anyhow!(error));
            }
            Err(mpsc::RecvTimeoutError::Timeout) => {
                return Err(anyhow!("Timed out stopping microphone recorder"));
            }
            Err(mpsc::RecvTimeoutError::Disconnected) => {
                if let Some(thread) = session.thread.take() {
                    join_recorder_thread(thread);
                }
                return Err(anyhow!("Microphone recorder stopped without audio"));
            }
        };
        if let Some(thread) = session.thread.take() {
            join_recorder_thread(thread);
        }

        tracing::info!(
            "voice recording stopped: duration_ms={duration_ms}, samples={}, wav_bytes={}",
            audio.sample_count,
            audio.wav.len(),
            duration_ms = audio.duration_ms
        );
        Ok(VoiceStopResponse {
            audio_base64: BASE64.encode(&audio.wav),
            mime_type: "audio/wav".into(),
            size_bytes: audio.wav.len(),
            duration_ms: audio.duration_ms,
            sample_count: audio.sample_count,
            sample_rate: audio.sample_rate,
            channels: audio.channels,
        })
    }

    pub fn cancel(&self) -> anyhow::Result<()> {
        if let Some(session) = self
            .session
            .lock()
            .map_err(|_| anyhow!("voice recorder lock poisoned"))?
            .take()
        {
            let _ = session.command_tx.send(RecorderCommand::Cancel);
        }
        tracing::info!("voice recording cancelled");
        Ok(())
    }
}

fn record_on_thread(
    start_tx: mpsc::Sender<StartMessage>,
    command_rx: mpsc::Receiver<RecorderCommand>,
    done_tx: mpsc::Sender<Result<RecordedAudio, String>>,
) {
    let setup = match setup_recording_stream() {
        Ok(setup) => setup,
        Err(error) => {
            let _ = start_tx.send(StartMessage::Failed(format!("{error:#}")));
            return;
        }
    };
    let (stream, samples, info) = setup;
    if let Err(error) = stream.play().context("start microphone input stream") {
        let _ = start_tx.send(StartMessage::Failed(format!("{error:#}")));
        return;
    }

    let started_at = Instant::now();
    let sample_rate = info.sample_rate;
    let channels = info.channels;
    let _ = start_tx.send(StartMessage::Ready(info));

    match command_rx.recv() {
        Ok(RecorderCommand::Stop) => {
            drop(stream);
            let duration_ms = started_at.elapsed().as_millis() as u64;
            let result = finish_recording(samples, sample_rate, channels, duration_ms)
                .map_err(|error| format!("{error:#}"));
            let _ = done_tx.send(result);
        }
        Ok(RecorderCommand::Cancel) | Err(_) => {
            drop(stream);
        }
    }
}

fn setup_recording_stream(
) -> anyhow::Result<(cpal::Stream, Arc<Mutex<Vec<i16>>>, VoiceStartResponse)> {
    let host = cpal::default_host();
    let device = host
        .default_input_device()
        .ok_or_else(|| anyhow!("No microphone input device found"))?;
    let device_name = device
        .name()
        .unwrap_or_else(|_| "Default microphone".into());
    let supported_config = device
        .default_input_config()
        .context("read default microphone input config")?;
    let sample_rate = supported_config.sample_rate().0;
    let channels = supported_config.channels();
    let max_samples = sample_rate as usize * channels as usize * MAX_RECORDING_SECONDS;
    let samples = Arc::new(Mutex::new(Vec::<i16>::new()));
    let stream_samples = Arc::clone(&samples);
    let err_fn = move |err| {
        tracing::warn!("voice recorder input stream error: {err}");
    };
    let config = supported_config.config();

    let stream = match supported_config.sample_format() {
        cpal::SampleFormat::I8 => device.build_input_stream(
            &config,
            move |data: &[i8], _| push_samples(data, &stream_samples, max_samples, i8_to_i16),
            err_fn,
            None,
        )?,
        cpal::SampleFormat::I16 => device.build_input_stream(
            &config,
            move |data: &[i16], _| {
                push_samples(data, &stream_samples, max_samples, |sample| sample)
            },
            err_fn,
            None,
        )?,
        cpal::SampleFormat::I32 => device.build_input_stream(
            &config,
            move |data: &[i32], _| push_samples(data, &stream_samples, max_samples, i32_to_i16),
            err_fn,
            None,
        )?,
        cpal::SampleFormat::I64 => device.build_input_stream(
            &config,
            move |data: &[i64], _| push_samples(data, &stream_samples, max_samples, i64_to_i16),
            err_fn,
            None,
        )?,
        cpal::SampleFormat::U8 => device.build_input_stream(
            &config,
            move |data: &[u8], _| push_samples(data, &stream_samples, max_samples, u8_to_i16),
            err_fn,
            None,
        )?,
        cpal::SampleFormat::U16 => device.build_input_stream(
            &config,
            move |data: &[u16], _| push_samples(data, &stream_samples, max_samples, u16_to_i16),
            err_fn,
            None,
        )?,
        cpal::SampleFormat::U32 => device.build_input_stream(
            &config,
            move |data: &[u32], _| push_samples(data, &stream_samples, max_samples, u32_to_i16),
            err_fn,
            None,
        )?,
        cpal::SampleFormat::U64 => device.build_input_stream(
            &config,
            move |data: &[u64], _| push_samples(data, &stream_samples, max_samples, u64_to_i16),
            err_fn,
            None,
        )?,
        cpal::SampleFormat::F32 => device.build_input_stream(
            &config,
            move |data: &[f32], _| push_samples(data, &stream_samples, max_samples, f32_to_i16),
            err_fn,
            None,
        )?,
        cpal::SampleFormat::F64 => device.build_input_stream(
            &config,
            move |data: &[f64], _| push_samples(data, &stream_samples, max_samples, f64_to_i16),
            err_fn,
            None,
        )?,
        other => return Err(anyhow!("Unsupported microphone sample format: {other:?}")),
    };

    Ok((
        stream,
        samples,
        VoiceStartResponse {
            device_name,
            sample_rate,
            channels,
        },
    ))
}

fn finish_recording(
    samples: Arc<Mutex<Vec<i16>>>,
    sample_rate: u32,
    channels: u16,
    duration_ms: u64,
) -> anyhow::Result<RecordedAudio> {
    let samples = samples
        .lock()
        .map_err(|_| anyhow!("voice sample buffer lock poisoned"))?
        .clone();
    if duration_ms < MIN_RECORDING_MS || samples.is_empty() {
        return Err(anyhow!("No audio captured"));
    }

    let wav =
        encode_wav(&samples, sample_rate, channels).context("encode recorded microphone audio")?;
    Ok(RecordedAudio {
        wav,
        duration_ms,
        sample_count: samples.len(),
        sample_rate,
        channels,
    })
}

fn join_recorder_thread(thread: JoinHandle<()>) {
    if thread.join().is_err() {
        tracing::warn!("voice recorder thread panicked");
    }
}

fn push_samples<T: Copy>(
    input: &[T],
    samples: &Arc<Mutex<Vec<i16>>>,
    max_samples: usize,
    convert: fn(T) -> i16,
) {
    if input.is_empty() {
        return;
    }
    if let Ok(mut guard) = samples.try_lock() {
        let remaining = max_samples.saturating_sub(guard.len());
        if remaining == 0 {
            return;
        }
        guard.extend(input.iter().take(remaining).copied().map(convert));
    }
}

fn i8_to_i16(sample: i8) -> i16 {
    (sample as i16) << 8
}

fn i32_to_i16(sample: i32) -> i16 {
    (sample >> 16) as i16
}

fn i64_to_i16(sample: i64) -> i16 {
    (sample >> 48) as i16
}

fn u8_to_i16(sample: u8) -> i16 {
    ((sample as i16) - 128) << 8
}

fn u16_to_i16(sample: u16) -> i16 {
    (sample as i32 - 32_768) as i16
}

fn u32_to_i16(sample: u32) -> i16 {
    ((sample as i64 - 2_147_483_648) >> 16) as i16
}

fn u64_to_i16(sample: u64) -> i16 {
    ((sample as i128 - 9_223_372_036_854_775_808_i128) >> 48) as i16
}

fn f32_to_i16(sample: f32) -> i16 {
    (sample.clamp(-1.0, 1.0) * i16::MAX as f32) as i16
}

fn f64_to_i16(sample: f64) -> i16 {
    (sample.clamp(-1.0, 1.0) * i16::MAX as f64) as i16
}

fn encode_wav(samples: &[i16], sample_rate: u32, channels: u16) -> anyhow::Result<Vec<u8>> {
    let mut cursor = Cursor::new(Vec::new());
    {
        let spec = hound::WavSpec {
            channels,
            sample_rate,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        let mut writer = hound::WavWriter::new(&mut cursor, spec)?;
        for sample in samples {
            writer.write_sample(*sample)?;
        }
        writer.finalize()?;
    }
    Ok(cursor.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn encode_wav_writes_header_and_samples() {
        let wav = encode_wav(&[0, i16::MAX, i16::MIN, 42], 44_100, 1).unwrap();
        assert!(wav.starts_with(b"RIFF"));
        assert!(wav.len() > 44);
    }

    #[test]
    fn unsigned_samples_center_on_zero() {
        assert_eq!(u8_to_i16(128), 0);
        assert_eq!(u16_to_i16(32_768), 0);
    }
}
