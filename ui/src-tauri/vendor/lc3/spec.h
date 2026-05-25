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
 * LC3 - Spectral coefficients encoding/decoding
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 */

#ifndef __LC3_SPEC_H
#define __LC3_SPEC_H

#include "common.h"
#include "tables.h"
#include "bwdet.h"
#include "ltpf.h"
#include "tns.h"
#include "sns.h"


/**
 * Spectral quantization side data
 */
typedef struct lc3_spec_side {
    int g_idx, nq;
    bool lsb_mode;
} lc3_spec_side_t;


/* ----------------------------------------------------------------------------
 *  Encoding
 * -------------------------------------------------------------------------- */

/**
 * Spectrum analysis
 * dt, sr, nbytes  Duration, samplerate and size of the frame
 * pitch, tns      Pitch present indication and TNS bistream data
 * spec            Context of analysis
 * x               Spectral coefficients, scaled as output
 * xq, side        Return quantization data
 *
 * The spectral coefficients `xq` storage is :
 *   b0       0:positive or zero  1:negative
 *   b15..b1  Absolute value
 */
void lc3_spec_analyze(enum lc3_dt dt, enum lc3_srate sr,
    int nbytes, bool pitch, const lc3_tns_data_t *tns,
    lc3_spec_analysis_t *spec, float *x, uint16_t *xq, lc3_spec_side_t *side);

/**
 * Put spectral quantization side data
 * bits            Bitstream context
 * dt, sr          Duration and samplerate of the frame
 * side            Spectral quantization side data
 */
void lc3_spec_put_side(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_srate sr, const lc3_spec_side_t *side);

/**
 * Encode spectral coefficients
 * bits            Bitstream context
 * dt, sr, bw      Duration, samplerate, bandwidth
 * nbytes          and size of the frame
 * xq, side        Quantization data
 * x               Scaled spectral coefficients
 *
 * The spectral coefficients `xq` storage is :
 *   b0       0:positive or zero  1:negative
 *   b15..b1  Absolute value
 */
void lc3_spec_encode(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_srate sr, enum lc3_bandwidth bw, int nbytes,
    const uint16_t *xq, const lc3_spec_side_t *side, const float *x);


/* ----------------------------------------------------------------------------
 *  Decoding
 * -------------------------------------------------------------------------- */

/**
 * Get spectral quantization side data
 * bits            Bitstream context
 * dt, sr          Duration and samplerate of the frame
 * side            Return quantization side data
 * return          0: Ok  -1: Invalid bandwidth indication
 */
int lc3_spec_get_side(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_srate sr, lc3_spec_side_t *side);

/**
 * Decode spectral coefficients
 * bits            Bitstream context
 * dt, sr, bw      Duration, samplerate, bandwidth
 * nbytes          and size of the frame
 * side            Quantization side data
 * x               Spectral coefficients
 * return          0: Ok  -1: Invalid bitstream data
 */
int lc3_spec_decode(lc3_bits_t *bits, enum lc3_dt dt, enum lc3_srate sr,
    enum lc3_bandwidth bw, int nbytes, const lc3_spec_side_t *side, float *x);


#endif /* __LC3_SPEC_H */
