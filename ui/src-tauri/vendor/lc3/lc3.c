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

#include "lc3.h"

#include "common.h"
#include "bits.h"

#include "attdet.h"
#include "bwdet.h"
#include "ltpf.h"
#include "mdct.h"
#include "energy.h"
#include "sns.h"
#include "tns.h"
#include "spec.h"
#include "plc.h"


/**
 * Frame side data
 */

struct side_data {
    enum lc3_bandwidth bw;
    bool pitch_present;
    lc3_ltpf_data_t ltpf;
    lc3_sns_data_t sns;
    lc3_tns_data_t tns;
    lc3_spec_side_t spec;
};


/* ----------------------------------------------------------------------------
 *  General
 * -------------------------------------------------------------------------- */

/**
 * Resolve frame duration in us
 * us              Frame duration in us
 * return          Frame duration identifier, or LC3_NUM_DT
 */
static enum lc3_dt resolve_dt(int us)
{
    return us ==  7500 ? LC3_DT_7M5 :
           us == 10000 ? LC3_DT_10M : LC3_NUM_DT;
}

/**
 * Resolve samplerate in Hz
 * hz              Samplerate in Hz
 * return          Sample rate identifier, or LC3_NUM_SRATE
 */
static enum lc3_srate resolve_sr(int hz)
{
    return hz ==  8000 ? LC3_SRATE_8K  : hz == 16000 ? LC3_SRATE_16K :
           hz == 24000 ? LC3_SRATE_24K : hz == 32000 ? LC3_SRATE_32K :
           hz == 48000 ? LC3_SRATE_48K : LC3_NUM_SRATE;
}

/**
 * Return the number of PCM samples in a frame
 */
int lc3_frame_samples(int dt_us, int sr_hz)
{
    enum lc3_dt dt = resolve_dt(dt_us);
    enum lc3_srate sr = resolve_sr(sr_hz);

    if (dt >= LC3_NUM_DT || sr >= LC3_NUM_SRATE)
        return -1;

    return LC3_NS(dt, sr);
}

/**
 * Return the size of frames, from bitrate
 */
int lc3_frame_bytes(int dt_us, int bitrate)
{
    if (resolve_dt(dt_us) >= LC3_NUM_DT)
        return -1;

    if (bitrate < LC3_MIN_BITRATE)
        return LC3_MIN_FRAME_BYTES;

    if (bitrate > LC3_MAX_BITRATE)
        return LC3_MAX_FRAME_BYTES;

    int nbytes = ((unsigned)bitrate * dt_us) / (1000*1000*8);

    return LC3_CLIP(nbytes, LC3_MIN_FRAME_BYTES, LC3_MAX_FRAME_BYTES);
}

/**
 * Resolve the bitrate, from the size of frames
 */
int lc3_resolve_bitrate(int dt_us, int nbytes)
{
    if (resolve_dt(dt_us) >= LC3_NUM_DT)
        return -1;

    if (nbytes < LC3_MIN_FRAME_BYTES)
        return LC3_MIN_BITRATE;

    if (nbytes > LC3_MAX_FRAME_BYTES)
        return LC3_MAX_BITRATE;

    int bitrate = ((unsigned)nbytes * (1000*1000*8) + dt_us/2) / dt_us;

    return LC3_CLIP(bitrate, LC3_MIN_BITRATE, LC3_MAX_BITRATE);
}

/**
 * Return algorithmic delay, as a number of samples
 */
int lc3_delay_samples(int dt_us, int sr_hz)
{
    enum lc3_dt dt = resolve_dt(dt_us);
    enum lc3_srate sr = resolve_sr(sr_hz);

    if (dt >= LC3_NUM_DT || sr >= LC3_NUM_SRATE)
        return -1;

    return (dt == LC3_DT_7M5 ? 8 : 5) * (LC3_SRATE_KHZ(sr) / 2);
}


/* ----------------------------------------------------------------------------
 *  Encoder
 * -------------------------------------------------------------------------- */

/**
 * Input PCM Samples from signed 16 bits
 * encoder         Encoder state
 * pcm, stride     Input PCM samples, and count between two consecutives
 */
static void load_s16(
    struct lc3_encoder *encoder, const void *_pcm, int stride)
{
    const int16_t *pcm = _pcm;

    enum lc3_dt dt = encoder->dt;
    enum lc3_srate sr = encoder->sr_pcm;

    int16_t *xt = (int16_t *)encoder->x + encoder->xt_off;
    float *xs = encoder->x + encoder->xs_off;
    int ns = LC3_NS(dt, sr);

    for (int i = 0; i < ns; i++, pcm += stride)
        xt[i] = *pcm, xs[i] = *pcm;
}

/**
 * Input PCM Samples from signed 24 bits
 * encoder         Encoder state
 * pcm, stride     Input PCM samples, and count between two consecutives
 */
static void load_s24(
    struct lc3_encoder *encoder, const void *_pcm, int stride)
{
    const int32_t *pcm = _pcm;

    enum lc3_dt dt = encoder->dt;
    enum lc3_srate sr = encoder->sr_pcm;

    int16_t *xt = (int16_t *)encoder->x + encoder->xt_off;
    float *xs = encoder->x + encoder->xs_off;
    int ns = LC3_NS(dt, sr);

    for (int i = 0; i < ns; i++, pcm += stride) {
        xt[i] = *pcm >> 8;
        xs[i] = ldexpf(*pcm, -8);
    }
}

/**
 * Input PCM Samples from signed 24 bits packed
 * encoder         Encoder state
 * pcm, stride     Input PCM samples, and count between two consecutives
 */
static void load_s24_3le(
    struct lc3_encoder *encoder, const void *_pcm, int stride)
{
    const uint8_t *pcm = _pcm;

    enum lc3_dt dt = encoder->dt;
    enum lc3_srate sr = encoder->sr_pcm;

    int16_t *xt = (int16_t *)encoder->x + encoder->xt_off;
    float *xs = encoder->x + encoder->xs_off;
    int ns = LC3_NS(dt, sr);

    for (int i = 0; i < ns; i++, pcm += 3*stride) {
        int32_t in = ((uint32_t)pcm[0] <<  8) |
                     ((uint32_t)pcm[1] << 16) |
                     ((uint32_t)pcm[2] << 24)  ;

        xt[i] = in >> 16;
        xs[i] = ldexpf(in, -16);
    }
}

/**
 * Input PCM Samples from float 32 bits
 * encoder         Encoder state
 * pcm, stride     Input PCM samples, and count between two consecutives
 */
static void load_float(
    struct lc3_encoder *encoder, const void *_pcm, int stride)
{
    const float *pcm = _pcm;

    enum lc3_dt dt = encoder->dt;
    enum lc3_srate sr = encoder->sr_pcm;

    int16_t *xt = (int16_t *)encoder->x + encoder->xt_off;
    float *xs = encoder->x + encoder->xs_off;
    int ns = LC3_NS(dt, sr);

    for (int i = 0; i < ns; i++, pcm += stride) {
        xs[i] = ldexpf(*pcm, 15);
        xt[i] = LC3_SAT16((int32_t)xs[i]);
    }
}

/**
 * Frame Analysis
 * encoder         Encoder state
 * nbytes          Size in bytes of the frame
 * side, xq        Return frame data
 */
static void analyze(struct lc3_encoder *encoder,
    int nbytes, struct side_data *side, uint16_t *xq)
{
    enum lc3_dt dt = encoder->dt;
    enum lc3_srate sr = encoder->sr;
    enum lc3_srate sr_pcm = encoder->sr_pcm;
    int ns = LC3_NS(dt, sr_pcm);
    int nt = LC3_NT(sr_pcm);

    int16_t *xt = (int16_t *)encoder->x + encoder->xt_off;
    float *xs = encoder->x + encoder->xs_off;
    float *xd = encoder->x + encoder->xd_off;
    float *xf = xs;

    /* --- Temporal --- */

    bool att = lc3_attdet_run(dt, sr_pcm, nbytes, &encoder->attdet, xt);

    side->pitch_present =
        lc3_ltpf_analyse(dt, sr_pcm, &encoder->ltpf, xt, &side->ltpf);

    memmove(xt - nt, xt + (ns-nt), nt * sizeof(*xt));

    /* --- Spectral --- */

    float e[LC3_NUM_BANDS];

    lc3_mdct_forward(dt, sr_pcm, sr, xs, xd, xf);

    bool nn_flag = lc3_energy_compute(dt, sr, xf, e);
    if (nn_flag)
        lc3_ltpf_disable(&side->ltpf);

    side->bw = lc3_bwdet_run(dt, sr, e);

    lc3_sns_analyze(dt, sr, e, att, &side->sns, xf, xf);

    lc3_tns_analyze(dt, side->bw, nn_flag, nbytes, &side->tns, xf);

    lc3_spec_analyze(dt, sr,
        nbytes, side->pitch_present, &side->tns,
        &encoder->spec, xf, xq, &side->spec);
}

/**
 * Encode bitstream
 * encoder         Encoder state
 * side, xq        The frame data
 * nbytes          Target size of the frame (20 to 400)
 * buffer          Output bitstream buffer of `nbytes` size
 */
static void encode(struct lc3_encoder *encoder,
    const struct side_data *side, uint16_t *xq, int nbytes, void *buffer)
{
    enum lc3_dt dt = encoder->dt;
    enum lc3_srate sr = encoder->sr;
    enum lc3_bandwidth bw = side->bw;
    float *xf = encoder->x + encoder->xs_off;

    lc3_bits_t bits;

    lc3_setup_bits(&bits, LC3_BITS_MODE_WRITE, buffer, nbytes);

    lc3_bwdet_put_bw(&bits, sr, bw);

    lc3_spec_put_side(&bits, dt, sr, &side->spec);

    lc3_tns_put_data(&bits, &side->tns);

    lc3_put_bit(&bits, side->pitch_present);

    lc3_sns_put_data(&bits, &side->sns);

    if (side->pitch_present)
        lc3_ltpf_put_data(&bits, &side->ltpf);

    lc3_spec_encode(&bits,
        dt, sr, bw, nbytes, xq, &side->spec, xf);

    lc3_flush_bits(&bits);
}

/**
 * Return size needed for an encoder
 */
unsigned lc3_encoder_size(int dt_us, int sr_hz)
{
    if (resolve_dt(dt_us) >= LC3_NUM_DT ||
        resolve_sr(sr_hz) >= LC3_NUM_SRATE)
        return 0;

    return sizeof(struct lc3_encoder) +
        (LC3_ENCODER_BUFFER_COUNT(dt_us, sr_hz)-1) * sizeof(float);
}

/**
 * Setup encoder
 */
struct lc3_encoder *lc3_setup_encoder(
    int dt_us, int sr_hz, int sr_pcm_hz, void *mem)
{
    if (sr_pcm_hz <= 0)
        sr_pcm_hz = sr_hz;

    enum lc3_dt dt = resolve_dt(dt_us);
    enum lc3_srate sr = resolve_sr(sr_hz);
    enum lc3_srate sr_pcm = resolve_sr(sr_pcm_hz);

    if (dt >= LC3_NUM_DT || sr_pcm >= LC3_NUM_SRATE || sr > sr_pcm || !mem)
        return NULL;

    struct lc3_encoder *encoder = mem;
    int ns = LC3_NS(dt, sr_pcm);
    int nt = LC3_NT(sr_pcm);

    *encoder = (struct lc3_encoder){
        .dt = dt, .sr = sr,
        .sr_pcm = sr_pcm,

        .xt_off = nt,
        .xs_off = (nt + ns) / 2,
        .xd_off = (nt + ns) / 2 + ns,
    };

    memset(encoder->x, 0,
        LC3_ENCODER_BUFFER_COUNT(dt_us, sr_pcm_hz) * sizeof(float));

    return encoder;
}

/**
 * Encode a frame
 */
int lc3_encode(struct lc3_encoder *encoder, enum lc3_pcm_format fmt,
    const void *pcm, int stride, int nbytes, void *out)
{
    static void (* const load[])(struct lc3_encoder *, const void *, int) = {
        [LC3_PCM_FORMAT_S16    ] = load_s16,
        [LC3_PCM_FORMAT_S24    ] = load_s24,
        [LC3_PCM_FORMAT_S24_3LE] = load_s24_3le,
        [LC3_PCM_FORMAT_FLOAT  ] = load_float,
    };

    /* --- Check parameters --- */

    if (!encoder || nbytes < LC3_MIN_FRAME_BYTES
                 || nbytes > LC3_MAX_FRAME_BYTES)
        return -1;

    /* --- Processing --- */

    struct side_data side;
    uint16_t xq[LC3_MAX_NE];

    load[fmt](encoder, pcm, stride);

    analyze(encoder, nbytes, &side, xq);

    encode(encoder, &side, xq, nbytes, out);

    return 0;
}


/* ----------------------------------------------------------------------------
 *  Decoder
 * -------------------------------------------------------------------------- */

/**
 * Output PCM Samples to signed 16 bits
 * decoder         Decoder state
 * pcm, stride     Output PCM samples, and count between two consecutives
 */
static void store_s16(
    struct lc3_decoder *decoder, void *_pcm, int stride)
{
    int16_t *pcm = _pcm;

    enum lc3_dt dt = decoder->dt;
    enum lc3_srate sr = decoder->sr_pcm;

    float *xs = decoder->x + decoder->xs_off;
    int ns = LC3_NS(dt, sr);

    for ( ; ns > 0; ns--, xs++, pcm += stride) {
        int32_t s = *xs >= 0 ? (int)(*xs + 0.5f) : (int)(*xs - 0.5f);
        *pcm = LC3_SAT16(s);
    }
}

/**
 * Output PCM Samples to signed 24 bits
 * decoder         Decoder state
 * pcm, stride     Output PCM samples, and count between two consecutives
 */
static void store_s24(
    struct lc3_decoder *decoder, void *_pcm, int stride)
{
    int32_t *pcm = _pcm;

    enum lc3_dt dt = decoder->dt;
    enum lc3_srate sr = decoder->sr_pcm;

    float *xs = decoder->x + decoder->xs_off;
    int ns = LC3_NS(dt, sr);

    for ( ; ns > 0; ns--, xs++, pcm += stride) {
        int32_t s = *xs >= 0 ? (int32_t)(ldexpf(*xs, 8) + 0.5f)
                             : (int32_t)(ldexpf(*xs, 8) - 0.5f);
        *pcm = LC3_SAT24(s);
    }
}

/**
 * Output PCM Samples to signed 24 bits packed
 * decoder         Decoder state
 * pcm, stride     Output PCM samples, and count between two consecutives
 */
static void store_s24_3le(
    struct lc3_decoder *decoder, void *_pcm, int stride)
{
    uint8_t *pcm = _pcm;

    enum lc3_dt dt = decoder->dt;
    enum lc3_srate sr = decoder->sr_pcm;

    float *xs = decoder->x + decoder->xs_off;
    int ns = LC3_NS(dt, sr);

    for ( ; ns > 0; ns--, xs++, pcm += 3*stride) {
        int32_t s = *xs >= 0 ? (int32_t)(ldexpf(*xs, 8) + 0.5f)
                             : (int32_t)(ldexpf(*xs, 8) - 0.5f);

        s = LC3_SAT24(s);
        pcm[0] = (s >>  0) & 0xff;
        pcm[1] = (s >>  8) & 0xff;
        pcm[2] = (s >> 16) & 0xff;
    }
}

/**
 * Output PCM Samples to float 32 bits
 * decoder         Decoder state
 * pcm, stride     Output PCM samples, and count between two consecutives
 */
static void store_float(
    struct lc3_decoder *decoder, void *_pcm, int stride)
{
    float *pcm = _pcm;

    enum lc3_dt dt = decoder->dt;
    enum lc3_srate sr = decoder->sr_pcm;

    float *xs = decoder->x + decoder->xs_off;
    int ns = LC3_NS(dt, sr);

    for ( ; ns > 0; ns--, xs++, pcm += stride) {
        float s = ldexpf(*xs, -15);
        *pcm = fminf(fmaxf(s, -1.f), 1.f);
    }
}

/**
 * Decode bitstream
 * decoder         Decoder state
 * data, nbytes    Input bitstream buffer
 * side            Return the side data
 * return          0: Ok  < 0: Bitsream error detected
 */
static int decode(struct lc3_decoder *decoder,
    const void *data, int nbytes, struct side_data *side)
{
    enum lc3_dt dt = decoder->dt;
    enum lc3_srate sr = decoder->sr;

    float *xf = decoder->x + decoder->xs_off;
    int ns = LC3_NS(dt, sr);
    int ne = LC3_NE(dt, sr);

    lc3_bits_t bits;
    int ret = 0;

    lc3_setup_bits(&bits, LC3_BITS_MODE_READ, (void *)data, nbytes);

    if ((ret = lc3_bwdet_get_bw(&bits, sr, &side->bw)) < 0)
        return ret;

    if ((ret = lc3_spec_get_side(&bits, dt, sr, &side->spec)) < 0)
        return ret;

    lc3_tns_get_data(&bits, dt, side->bw, nbytes, &side->tns);

    side->pitch_present = lc3_get_bit(&bits);

    if ((ret = lc3_sns_get_data(&bits, &side->sns)) < 0)
        return ret;

    if (side->pitch_present)
        lc3_ltpf_get_data(&bits, &side->ltpf);

    if ((ret = lc3_spec_decode(&bits, dt, sr,
                    side->bw, nbytes, &side->spec, xf)) < 0)
        return ret;

    memset(xf + ne, 0, (ns - ne) * sizeof(float));

    return lc3_check_bits(&bits);
}

/**
 * Frame synthesis
 * decoder         Decoder state
 * side            Frame data, NULL performs PLC
 * nbytes          Size in bytes of the frame
 */
static void synthesize(struct lc3_decoder *decoder,
    const struct side_data *side, int nbytes)
{
    enum lc3_dt dt = decoder->dt;
    enum lc3_srate sr = decoder->sr;
    enum lc3_srate sr_pcm = decoder->sr_pcm;

    float *xf = decoder->x + decoder->xs_off;
    int ns = LC3_NS(dt, sr_pcm);
    int ne = LC3_NE(dt, sr);

    float *xg = decoder->x + decoder->xg_off;
    float *xs = xf;

    float *xd = decoder->x + decoder->xd_off;
    float *xh = decoder->x + decoder->xh_off;

    if (side) {
        enum lc3_bandwidth bw = side->bw;

        lc3_plc_suspend(&decoder->plc);

        lc3_tns_synthesize(dt, bw, &side->tns, xf);

        lc3_sns_synthesize(dt, sr, &side->sns, xf, xg);

        lc3_mdct_inverse(dt, sr_pcm, sr, xg, xd, xs);

    } else {
        lc3_plc_synthesize(dt, sr, &decoder->plc, xg, xf);

        memset(xf + ne, 0, (ns - ne) * sizeof(float));

        lc3_mdct_inverse(dt, sr_pcm, sr, xf, xd, xs);
    }

    lc3_ltpf_synthesize(dt, sr_pcm, nbytes, &decoder->ltpf,
        side && side->pitch_present ? &side->ltpf : NULL, xh, xs);
}

/**
 * Update decoder state on decoding completion
 * decoder         Decoder state
 */
static void complete(struct lc3_decoder *decoder)
{
    enum lc3_dt dt = decoder->dt;
    enum lc3_srate sr_pcm = decoder->sr_pcm;
    int nh = LC3_NH(dt, sr_pcm);
    int ns = LC3_NS(dt, sr_pcm);

    decoder->xs_off = decoder->xs_off - decoder->xh_off < nh - ns ?
        decoder->xs_off + ns : decoder->xh_off;
}

/**
 * Return size needed for a decoder
 */
unsigned lc3_decoder_size(int dt_us, int sr_hz)
{
    if (resolve_dt(dt_us) >= LC3_NUM_DT ||
        resolve_sr(sr_hz) >= LC3_NUM_SRATE)
        return 0;

    return sizeof(struct lc3_decoder) +
        (LC3_DECODER_BUFFER_COUNT(dt_us, sr_hz)-1) * sizeof(float);
}

/**
 * Setup decoder
 */
struct lc3_decoder *lc3_setup_decoder(
    int dt_us, int sr_hz, int sr_pcm_hz, void *mem)
{
    if (sr_pcm_hz <= 0)
        sr_pcm_hz = sr_hz;

    enum lc3_dt dt = resolve_dt(dt_us);
    enum lc3_srate sr = resolve_sr(sr_hz);
    enum lc3_srate sr_pcm = resolve_sr(sr_pcm_hz);

    if (dt >= LC3_NUM_DT || sr_pcm >= LC3_NUM_SRATE || sr > sr_pcm || !mem)
        return NULL;

    struct lc3_decoder *decoder = mem;
    int nh = LC3_NH(dt, sr_pcm);
    int ns = LC3_NS(dt, sr_pcm);
    int nd = LC3_ND(dt, sr_pcm);

    *decoder = (struct lc3_decoder){
        .dt = dt, .sr = sr,
        .sr_pcm = sr_pcm,

        .xh_off = 0,
        .xs_off = nh - ns,
        .xd_off = nh,
        .xg_off = nh + nd,
    };

    lc3_plc_reset(&decoder->plc);

    memset(decoder->x, 0,
        LC3_DECODER_BUFFER_COUNT(dt_us, sr_pcm_hz) * sizeof(float));

    return decoder;
}

/**
 * Decode a frame
 */
int lc3_decode(struct lc3_decoder *decoder, const void *in, int nbytes,
    enum lc3_pcm_format fmt, void *pcm, int stride)
{
    static void (* const store[])(struct lc3_decoder *, void *, int) = {
        [LC3_PCM_FORMAT_S16    ] = store_s16,
        [LC3_PCM_FORMAT_S24    ] = store_s24,
        [LC3_PCM_FORMAT_S24_3LE] = store_s24_3le,
        [LC3_PCM_FORMAT_FLOAT  ] = store_float,
    };

    /* --- Check parameters --- */

    if (!decoder)
        return -1;

    if (in && (nbytes < LC3_MIN_FRAME_BYTES ||
               nbytes > LC3_MAX_FRAME_BYTES   ))
        return -1;

    /* --- Processing --- */

    struct side_data side;

    int ret = !in || (decode(decoder, in, nbytes, &side) < 0);

    synthesize(decoder, ret ? NULL : &side, nbytes);

    store[fmt](decoder, pcm, stride);

    complete(decoder);

    return ret;
}
