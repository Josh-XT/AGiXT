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
 * Low Complexity Communication Codec (LC3)
 *
 * This implementation conforms to :
 *   Low Complexity Communication Codec (LC3)
 *   Bluetooth Specification v1.0
 *
 *
 * The LC3 is an efficient low latency audio codec.
 *
 * - Unlike most other codecs, the LC3 codec is focused on audio streaming
 *   in constrained (on packet sizes and interval) tranport layer.
 *   In this way, the LC3 does not handle :
 *   VBR (Variable Bitrate), based on input signal complexity
 *   ABR (Adaptative Bitrate). It does not rely on any bit reservoir,
 *       a frame will be strictly encoded in the bytes budget given by
 *       the user (or transport layer).
 *
 *   However, the bitrate (bytes budget for encoding a frame) can be
 *   freely changed at any time. But will not rely on signal complexity,
 *   it can follow a temporary bandwidth increase or reduction.
 *
 * - Unlike classic codecs, the LC3 codecs does not run on fixed amount
 *   of samples as input. It operates only on fixed frame duration, for
 *   any supported samplerates (8 to 48 KHz). Two frames duration are
 *   available 7.5ms and 10ms.
 *
 *
 * --- About 44.1 KHz samplerate ---
 *
 * The Bluetooth specification reference the 44.1 KHz samplerate, although
 * there is no support in the core algorithm of the codec of 44.1 KHz.
 * We can summarize the 44.1 KHz support by "you can put any samplerate
 * around the defined base samplerates". Please mind the following items :
 *
 *   1. The frame size will not be 7.5 ms or 10 ms, but is scaled
 *      by 'supported samplerate' / 'input samplerate'
 *
 *   2. The bandwidth will be hard limited (to 20 KHz) if you select 48 KHz.
 *      The encoded bandwidth will also be affected by the above inverse
 *      factor of 20 KHz.
 *
 * Applied to 44.1 KHz, we get :
 *
 *   1. About  8.16 ms frame duration, instead of 7.5 ms
 *      About 10.88 ms frame duration, instead of  10 ms
 *
 *   2. The bandwidth becomes limited to 18.375 KHz
 *
 *
 * --- How to encode / decode ---
 *
 * An encoder / decoder context needs to be setup. This context keeps states
 * on the current stream to proceed, and samples that overlapped across
 * frames.
 *
 * You have two ways to setup the encoder / decoder :
 *
 * - Using static memory allocation (this module does not rely on
 *   any dynamic memory allocation). The types `lc3_xxcoder_mem_16k_t`,
 *   and `lc3_xxcoder_mem_48k_t` have size of the memory needed for
 *   encoding up to 16 KHz or 48 KHz.
 *
 * - Using dynamic memory allocation. The `lc3_xxcoder_size()` procedure
 *   returns the needed memory size, for a given configuration. The memory
 *   space must be aligned to a pointer size. As an example, you can setup
 *   encoder like this :
 *
 *   | enc = lc3_setup_encoder(frame_us, samplerate,
 *   |      malloc(lc3_encoder_size(frame_us, samplerate)));
 *   | ...
 *   | free(enc);
 *
 *   Note :
 *   - A NULL memory adress as input, will return a NULL encoder context.
 *   - The returned encoder handle is set at the address of the allocated
 *     memory space, you can directly free the handle.
 *
 * Next, call the `lc3_encode()` encoding procedure, for each frames.
 * To handle multichannel streams (Stereo or more), you can proceed with
 * interleaved channels PCM stream like this :
 *
 *   | for(int ich = 0; ich < nch: ich++)
 *   |     lc3_encode(encoder[ich], pcm + ich, nch, ...);
 *
 *   with `nch` as the number of channels in the PCM stream
 *
 * ---
 *
 * Antoine SOULIER, Tempow / Google LLC
 *
 */

#ifndef __LC3_H
#define __LC3_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stdint.h>
#include <stdbool.h>

#include "lc3_private.h"


/**
 * Limitations
 * - On the bitrate, in bps, of a stream
 * - On the size of the frames in bytes
 * - On the number of samples by frames
 */

#define LC3_MIN_BITRATE         16000
#define LC3_MAX_BITRATE        320000

#define LC3_MIN_FRAME_BYTES        20
#define LC3_MAX_FRAME_BYTES       400

#define LC3_MIN_FRAME_SAMPLES  __LC3_NS( 7500,  8000)
#define LC3_MAX_FRAME_SAMPLES  __LC3_NS(10000, 48000)


/**
 * Parameters check
 *   LC3_CHECK_DT_US(us)  True when frame duration in us is suitable
 *   LC3_CHECK_SR_HZ(sr)  True when samplerate in Hz is suitable
 */

#define LC3_CHECK_DT_US(us) \
    ( ((us) == 7500) || ((us) == 10000) )

#define LC3_CHECK_SR_HZ(sr) \
    ( ((sr) ==  8000) || ((sr) == 16000) || ((sr) == 24000) || \
      ((sr) == 32000) || ((sr) == 48000)                       )


/**
 * PCM Sample Format
 *   S16      Signed 16 bits, in 16 bits words (int16_t)
 *   S24      Signed 24 bits, using low three bytes of 32 bits words (int32_t).
 *            The high byte sign extends (bits 31..24 set to b23).
 *   S24_3LE  Signed 24 bits packed in 3 bytes little endian
 *   FLOAT    Floating point 32 bits (float type), in range -1 to 1
 */

enum lc3_pcm_format {
    LC3_PCM_FORMAT_S16,
    LC3_PCM_FORMAT_S24,
    LC3_PCM_FORMAT_S24_3LE,
    LC3_PCM_FORMAT_FLOAT,
};


/**
 * Handle
 */

typedef struct lc3_encoder *lc3_encoder_t;
typedef struct lc3_decoder *lc3_decoder_t;


/**
 * Static memory of encoder context
 *
 * Propose types suitable for static memory allocation, supporting
 * any frame duration, and maximum samplerates 16k and 48k respectively
 * You can customize your type using the `LC3_ENCODER_MEM_T` or
 * `LC3_DECODER_MEM_T` macro.
 */

typedef LC3_ENCODER_MEM_T(10000, 16000) lc3_encoder_mem_16k_t;
typedef LC3_ENCODER_MEM_T(10000, 48000) lc3_encoder_mem_48k_t;

typedef LC3_DECODER_MEM_T(10000, 16000) lc3_decoder_mem_16k_t;
typedef LC3_DECODER_MEM_T(10000, 48000) lc3_decoder_mem_48k_t;


/**
 * Return the number of PCM samples in a frame
 * dt_us           Frame duration in us, 7500 or 10000
 * sr_hz           Samplerate in Hz, 8000, 16000, 24000, 32000 or 48000
 * return          Number of PCM samples, -1 on bad parameters
 */
int lc3_frame_samples(int dt_us, int sr_hz);

/**
 * Return the size of frames, from bitrate
 * dt_us           Frame duration in us, 7500 or 10000
 * bitrate         Target bitrate in bit per second
 * return          The floor size in bytes of the frames, -1 on bad parameters
 */
int lc3_frame_bytes(int dt_us, int bitrate);

/**
 * Resolve the bitrate, from the size of frames
 * dt_us           Frame duration in us, 7500 or 10000
 * nbytes          Size in bytes of the frames
 * return          The according bitrate in bps, -1 on bad parameters
 */
int lc3_resolve_bitrate(int dt_us, int nbytes);

/**
 * Return algorithmic delay, as a number of samples
 * dt_us           Frame duration in us, 7500 or 10000
 * sr_hz           Samplerate in Hz, 8000, 16000, 24000, 32000 or 48000
 * return          Number of algorithmic delay samples, -1 on bad parameters
 */
int lc3_delay_samples(int dt_us, int sr_hz);

/**
 * Return size needed for an encoder
 * dt_us           Frame duration in us, 7500 or 10000
 * sr_hz           Samplerate in Hz, 8000, 16000, 24000, 32000 or 48000
 * return          Size of then encoder in bytes, 0 on bad parameters
 *
 * The `sr_hz` parameter is the samplerate of the PCM input stream,
 * and will match `sr_pcm_hz` of `lc3_setup_encoder()`.
 */
unsigned lc3_encoder_size(int dt_us, int sr_hz);

/**
 * Setup encoder
 * dt_us           Frame duration in us, 7500 or 10000
 * sr_hz           Samplerate in Hz, 8000, 16000, 24000, 32000 or 48000
 * sr_pcm_hz       Input samplerate, downsampling option of input, or 0
 * mem             Encoder memory space, aligned to pointer type
 * return          Encoder as an handle, NULL on bad parameters
 *
 * The `sr_pcm_hz` parameter is a downsampling option of PCM input,
 * the value `0` fallback to the samplerate of the encoded stream `sr_hz`.
 * When used, `sr_pcm_hz` is intended to be higher or equal to the encoder
 * samplerate `sr_hz`. The size of the context needed, given by
 * `lc3_encoder_size()` will be set accordingly to `sr_pcm_hz`.
 */
lc3_encoder_t lc3_setup_encoder(
    int dt_us, int sr_hz, int sr_pcm_hz, void *mem);

/**
 * Encode a frame
 * encoder         Handle of the encoder
 * fmt             PCM input format
 * pcm, stride     Input PCM samples, and count between two consecutives
 * nbytes          Target size, in bytes, of the frame (20 to 400)
 * out             Output buffer of `nbytes` size
 * return          0: On success  -1: Wrong parameters
 */
int lc3_encode(lc3_encoder_t encoder, enum lc3_pcm_format fmt,
    const void *pcm, int stride, int nbytes, void *out);

/**
 * Return size needed for an decoder
 * dt_us           Frame duration in us, 7500 or 10000
 * sr_hz           Samplerate in Hz, 8000, 16000, 24000, 32000 or 48000
 * return          Size of then decoder in bytes, 0 on bad parameters
 *
 * The `sr_hz` parameter is the samplerate of the PCM output stream,
 * and will match `sr_pcm_hz` of `lc3_setup_decoder()`.
 */
unsigned lc3_decoder_size(int dt_us, int sr_hz);

/**
 * Setup decoder
 * dt_us           Frame duration in us, 7500 or 10000
 * sr_hz           Samplerate in Hz, 8000, 16000, 24000, 32000 or 48000
 * sr_pcm_hz       Output samplerate, upsampling option of output (or 0)
 * mem             Decoder memory space, aligned to pointer type
 * return          Decoder as an handle, NULL on bad parameters
 *
 * The `sr_pcm_hz` parameter is an upsampling option of PCM output,
 * the value `0` fallback to the samplerate of the decoded stream `sr_hz`.
 * When used, `sr_pcm_hz` is intended to be higher or equal to the decoder
 * samplerate `sr_hz`. The size of the context needed, given by
 * `lc3_decoder_size()` will be set accordingly to `sr_pcm_hz`.
 */
lc3_decoder_t lc3_setup_decoder(
    int dt_us, int sr_hz, int sr_pcm_hz, void *mem);

/**
 * Decode a frame
 * decoder         Handle of the decoder
 * in, nbytes      Input bitstream, and size in bytes, NULL performs PLC
 * fmt             PCM output format
 * pcm, stride     Output PCM samples, and count between two consecutives
 * return          0: On success  1: PLC operated  -1: Wrong parameters
 */
int lc3_decode(lc3_decoder_t decoder, const void *in, int nbytes,
    enum lc3_pcm_format fmt, void *pcm, int stride);


#ifdef __cplusplus
}
#endif

#endif /* __LC3_H */
