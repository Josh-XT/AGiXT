//! LC3 decoding for the Even Realities G1 microphone stream.
//!
//! This uses the same Google LC3 C implementation and parameters as the
//! Flutter mobile app: 10 ms frames, 16 kHz mono, 20 encoded bytes per frame,
//! decoded to signed 16-bit PCM.

use std::ffi::c_void;
use std::io::Cursor;
use std::mem;
use std::os::raw::{c_int, c_uint};

use anyhow::{anyhow, bail, Context, Result};

const DT_US: c_int = 10_000;
const SAMPLE_RATE_HZ: c_int = 16_000;
const ENCODED_FRAME_BYTES: usize = 20;
const LC3_PCM_FORMAT_S16: c_int = 0;

extern "C" {
    fn lc3_decoder_size(dt_us: c_int, sr_hz: c_int) -> c_uint;
    fn lc3_setup_decoder(
        dt_us: c_int,
        sr_hz: c_int,
        sr_pcm_hz: c_int,
        mem: *mut c_void,
    ) -> *mut c_void;
    fn lc3_frame_samples(dt_us: c_int, sr_hz: c_int) -> c_int;
    fn lc3_decode(
        decoder: *mut c_void,
        input: *const c_void,
        nbytes: c_int,
        fmt: c_int,
        pcm: *mut c_void,
        stride: c_int,
    ) -> c_int;
}

pub fn decode_lc3_to_wav(lc3: &[u8]) -> Result<Vec<u8>> {
    let pcm = decode_lc3_to_pcm_i16(lc3)?;
    pcm_i16_to_wav(&pcm, SAMPLE_RATE_HZ as u32)
}

fn decode_lc3_to_pcm_i16(lc3: &[u8]) -> Result<Vec<i16>> {
    let frame_samples = unsafe { lc3_frame_samples(DT_US, SAMPLE_RATE_HZ) };
    if frame_samples <= 0 {
        bail!("LC3 decoder rejected frame parameters");
    }
    let decoder_size = unsafe { lc3_decoder_size(DT_US, SAMPLE_RATE_HZ) } as usize;
    if decoder_size == 0 {
        bail!("LC3 decoder returned zero context size");
    }

    let decoder_words = decoder_size.div_ceil(mem::size_of::<usize>());
    let mut decoder_mem = vec![0usize; decoder_words];
    let decoder =
        unsafe { lc3_setup_decoder(DT_US, SAMPLE_RATE_HZ, 0, decoder_mem.as_mut_ptr().cast()) };
    if decoder.is_null() {
        bail!("LC3 decoder setup failed");
    }

    let frame_count = lc3.len() / ENCODED_FRAME_BYTES;
    let mut pcm = Vec::with_capacity(frame_count * frame_samples as usize);
    for (index, frame) in lc3.chunks_exact(ENCODED_FRAME_BYTES).enumerate() {
        let mut out = vec![0i16; frame_samples as usize];
        let rc = unsafe {
            lc3_decode(
                decoder,
                frame.as_ptr().cast(),
                ENCODED_FRAME_BYTES as c_int,
                LC3_PCM_FORMAT_S16,
                out.as_mut_ptr().cast(),
                1,
            )
        };
        if rc < 0 {
            return Err(anyhow!("LC3 decode failed at frame {index}"));
        }
        pcm.extend_from_slice(&out);
    }
    Ok(pcm)
}

fn pcm_i16_to_wav(samples: &[i16], sample_rate: u32) -> Result<Vec<u8>> {
    let mut cursor = Cursor::new(Vec::new());
    {
        let spec = hound::WavSpec {
            channels: 1,
            sample_rate,
            bits_per_sample: 16,
            sample_format: hound::SampleFormat::Int,
        };
        let mut writer = hound::WavWriter::new(&mut cursor, spec).context("create WAV writer")?;
        for sample in samples {
            writer.write_sample(*sample).context("write WAV sample")?;
        }
        writer.finalize().context("finalize WAV")?;
    }
    Ok(cursor.into_inner())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_lc3_decodes_to_valid_empty_wav() {
        let wav = decode_lc3_to_wav(&[]).unwrap();
        assert!(wav.starts_with(b"RIFF"));
        assert!(wav.windows(4).any(|w| w == b"WAVE"));
    }

    #[test]
    fn ignores_partial_lc3_tail() {
        let wav = decode_lc3_to_wav(&[0u8; ENCODED_FRAME_BYTES - 1]).unwrap();
        assert!(wav.starts_with(b"RIFF"));
    }
}
