/******************************************************************************
 *
 *  Copyright 2022 Google LLC
 *
 *  Licensed under the Apache License, Version 2.0 (the "License");
 *  you may not use this file except in compliance with the License.
 *  You may obtain a copy of the License at:
 *
 *  http://www.apache.org/licenses/LICENSE-2.0
 *
 *  Unless required by applicable law or agreed to in writing, software
 *  distributed under the License is distributed on an "AS IS" BASIS,
 *  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 *  See the License for the specific language governing permissions and
 *  limitations under the License.
 *
 ******************************************************************************/

/**
 * Low Complexity Communication Codec (LC3) - C++ interface
 */

#ifndef __LC3_CPP_H
#define __LC3_CPP_H

#include <cassert>
#include <memory>
#include <vector>
#include <stdlib.h>

#include "lc3.h"

namespace lc3 {

// PCM Sample Format
// - Signed 16 bits, in 16 bits words (int16_t)
// - Signed 24 bits, using low three bytes of 32 bits words (int32_t)
//   The high byte sign extends (bits 31..24 set to b23)
// - Signed 24 bits packed in 3 bytes little endian
// - Floating point 32 bits (float type), in range -1 to 1

enum class PcmFormat {
  kS16 = LC3_PCM_FORMAT_S16,
  kS24 = LC3_PCM_FORMAT_S24,
  kS24In3Le = LC3_PCM_FORMAT_S24_3LE,
  kF32 = LC3_PCM_FORMAT_FLOAT
};

// Base Encoder/Decoder Class
template <typename T>
class Base {
 protected:
  Base(int dt_us, int sr_hz, int sr_pcm_hz, size_t nchannels)
      : dt_us_(dt_us),
        sr_hz_(sr_hz),
        sr_pcm_hz_(sr_pcm_hz == 0 ? sr_hz : sr_pcm_hz),
        nchannels_(nchannels) {
    states.reserve(nchannels_);
  }

  virtual ~Base() = default;

  int dt_us_, sr_hz_;
  int sr_pcm_hz_;
  size_t nchannels_;

  using state_ptr = std::unique_ptr<T, decltype(&free)>;
  std::vector<state_ptr> states;

 public:
  // Return the number of PCM samples in a frame
  int GetFrameSamples() { return lc3_frame_samples(dt_us_, sr_pcm_hz_); }

  // Return the size of frames, from bitrate
  int GetFrameBytes(int bitrate) { return lc3_frame_bytes(dt_us_, bitrate); }

  // Resolve the bitrate, from the size of frames
  int ResolveBitrate(int nbytes) { return lc3_resolve_bitrate(dt_us_, nbytes); }

  // Return algorithmic delay, as a number of samples
  int GetDelaySamples() { return lc3_delay_samples(dt_us_, sr_pcm_hz_); }

};  // class Base

// Encoder Class
class Encoder : public Base<struct lc3_encoder> {
  template <typename T>
  int EncodeImpl(PcmFormat fmt, const T *pcm, int frame_size, uint8_t *out) {
    if (states.size() != nchannels_) return -1;

    enum lc3_pcm_format cfmt = static_cast<lc3_pcm_format>(fmt);
    int ret = 0;

    for (size_t ich = 0; ich < nchannels_; ich++)
      ret |= lc3_encode(states[ich].get(), cfmt, pcm + ich, nchannels_,
                        frame_size, out + ich * frame_size);

    return ret;
  }

 public:
  // Encoder construction / destruction
  //
  // The frame duration `dt_us` is 7500 or 10000 us.
  // The samplerate `sr_hz` is 8000, 16000, 24000, 32000 or 48000 Hz.
  //
  // The `sr_pcm_hz` parameter is a downsampling option of PCM input,
  // the value 0 fallback to the samplerate of the encoded stream `sr_hz`.
  // When used, `sr_pcm_hz` is intended to be higher or equal to the encoder
  // samplerate `sr_hz`.

  Encoder(int dt_us, int sr_hz, int sr_pcm_hz = 0, size_t nchannels = 1)
      : Base(dt_us, sr_hz, sr_pcm_hz, nchannels) {
    for (size_t ich = 0; ich < nchannels_; ich++) {
      auto s = state_ptr(
          (lc3_encoder_t)malloc(lc3_encoder_size(dt_us_, sr_pcm_hz_)), free);

      if (lc3_setup_encoder(dt_us_, sr_hz_, sr_pcm_hz_, s.get()))
        states.push_back(std::move(s));
    }
  }

  ~Encoder() override = default;

  // Reset encoder state

  void Reset() {
    for (auto &s : states)
      lc3_setup_encoder(dt_us_, sr_hz_, sr_pcm_hz_, s.get());
  }

  // Encode
  //
  // The input PCM samples are given in signed 16 bits, 24 bits, float,
  // according the type of `pcm` input buffer, or by selecting a format.
  //
  // The PCM samples are read in interleaved way, and consecutive
  // `nchannels` frames of size `frame_size` are output in `out` buffer.
  //
  // The value returned is 0 on successs, -1 otherwise.

  int Encode(const int16_t *pcm, int frame_size, uint8_t *out) {
    return EncodeImpl(PcmFormat::kS16, pcm, frame_size, out);
  }

  int Encode(const int32_t *pcm, int frame_size, uint8_t *out) {
    return EncodeImpl(PcmFormat::kS24, pcm, frame_size, out);
  }

  int Encode(const float *pcm, int frame_size, uint8_t *out) {
    return EncodeImpl(PcmFormat::kF32, pcm, frame_size, out);
  }

  int Encode(PcmFormat fmt, const void *pcm, int frame_size, uint8_t *out) {
    uintptr_t pcm_ptr = reinterpret_cast<uintptr_t>(pcm);

    switch (fmt) {
      case PcmFormat::kS16:
        assert(pcm_ptr % alignof(int16_t) == 0);
        return EncodeImpl(fmt, reinterpret_cast<const int16_t *>(pcm),
                          frame_size, out);

      case PcmFormat::kS24:
        assert(pcm_ptr % alignof(int32_t) == 0);
        return EncodeImpl(fmt, reinterpret_cast<const int32_t *>(pcm),
                          frame_size, out);

      case PcmFormat::kS24In3Le:
        return EncodeImpl(fmt, reinterpret_cast<const int8_t(*)[3]>(pcm),
                          frame_size, out);

      case PcmFormat::kF32:
        assert(pcm_ptr % alignof(float) == 0);
        return EncodeImpl(fmt, reinterpret_cast<const float *>(pcm), frame_size,
                          out);
    }

    return -1;
  }

};  // class Encoder

// Decoder Class
class Decoder : public Base<struct lc3_decoder> {
  template <typename T>
  int DecodeImpl(const uint8_t *in, int frame_size, PcmFormat fmt, T *pcm) {
    if (states.size() != nchannels_) return -1;

    enum lc3_pcm_format cfmt = static_cast<enum lc3_pcm_format>(fmt);
    int ret = 0;

    for (size_t ich = 0; ich < nchannels_; ich++)
      ret |= lc3_decode(states[ich].get(), in + ich * frame_size, frame_size,
                        cfmt, pcm + ich, nchannels_);

    return ret;
  }

 public:
  // Decoder construction / destruction
  //
  // The frame duration `dt_us` is 7500 or 10000 us.
  // The samplerate `sr_hz` is 8000, 16000, 24000, 32000 or 48000 Hz.
  //
  // The `sr_pcm_hz` parameter is an downsampling option of PCM output,
  // the value 0 fallback to the samplerate of the decoded stream `sr_hz`.
  // When used, `sr_pcm_hz` is intended to be higher or equal to the decoder
  // samplerate `sr_hz`.

  Decoder(int dt_us, int sr_hz, int sr_pcm_hz = 0, size_t nchannels = 1)
      : Base(dt_us, sr_hz, sr_pcm_hz, nchannels) {
    for (size_t i = 0; i < nchannels_; i++) {
      auto s = state_ptr(
          (lc3_decoder_t)malloc(lc3_decoder_size(dt_us_, sr_pcm_hz_)), free);

      if (lc3_setup_decoder(dt_us_, sr_hz_, sr_pcm_hz_, s.get()))
        states.push_back(std::move(s));
    }
  }

  ~Decoder() override = default;

  // Reset decoder state

  void Reset() {
    for (auto &s : states)
      lc3_setup_decoder(dt_us_, sr_hz_, sr_pcm_hz_, s.get());
  }

  // Decode
  //
  // Consecutive `nchannels` frames of size `frame_size` are decoded
  // in the `pcm` buffer in interleaved way.
  //
  // The PCM samples are output in signed 16 bits, 24 bits, float,
  // according the type of `pcm` output buffer, or by selecting a format.
  //
  // The value returned is 0 on successs, 1 when PLC has been performed,
  // and -1 otherwise.

  int Decode(const uint8_t *in, int frame_size, int16_t *pcm) {
    return DecodeImpl(in, frame_size, PcmFormat::kS16, pcm);
  }

  int Decode(const uint8_t *in, int frame_size, int32_t *pcm) {
    return DecodeImpl(in, frame_size, PcmFormat::kS24In3Le, pcm);
  }

  int Decode(const uint8_t *in, int frame_size, float *pcm) {
    return DecodeImpl(in, frame_size, PcmFormat::kF32, pcm);
  }

  int Decode(const uint8_t *in, int frame_size, PcmFormat fmt, void *pcm) {
    uintptr_t pcm_ptr = reinterpret_cast<uintptr_t>(pcm);

    switch (fmt) {
      case PcmFormat::kS16:
        assert(pcm_ptr % alignof(int16_t) == 0);
        return DecodeImpl(in, frame_size, fmt,
                          reinterpret_cast<int16_t *>(pcm));

      case PcmFormat::kS24:
        assert(pcm_ptr % alignof(int32_t) == 0);
        return DecodeImpl(in, frame_size, fmt,
                          reinterpret_cast<int32_t *>(pcm));

      case PcmFormat::kS24In3Le:
        return DecodeImpl(in, frame_size, fmt,
                          reinterpret_cast<int8_t(*)[3]>(pcm));

      case PcmFormat::kF32:
        assert(pcm_ptr % alignof(float) == 0);
        return DecodeImpl(in, frame_size, fmt, reinterpret_cast<float *>(pcm));
    }

    return -1;
  }

};  // class Decoder

}  // namespace lc3

#endif /* __LC3_CPP_H */
