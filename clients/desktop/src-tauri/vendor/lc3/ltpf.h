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
 * LC3 - Long Term Postfilter
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 */

#ifndef __LC3_LTPF_H
#define __LC3_LTPF_H

#include "common.h"
#include "bits.h"


/**
 * LTPF data
 */

typedef struct lc3_ltpf_data {
    bool active;
    int pitch_index;
} lc3_ltpf_data_t;


/* ----------------------------------------------------------------------------
 *  Encoding
 * -------------------------------------------------------------------------- */

/**
 * LTPF analysis
 * dt, sr          Duration and samplerate of the frame
 * ltpf            Context of analysis
 * allowed         True when activation of LTPF is allowed
 * x               [-d..-1] Previous, [0..ns-1] Current samples
 * data            Return bitstream data
 * return          True when pitch present, False otherwise
 *
 * The `x` vector is aligned on 32 bits
 * The number of previous samples `d` accessed on `x` is :
 *   d: { 10, 20, 30, 40, 60 } - 1 for samplerates from 8KHz to 48KHz
 */
bool lc3_ltpf_analyse(enum lc3_dt dt, enum lc3_srate sr,
    lc3_ltpf_analysis_t *ltpf, const int16_t *x, lc3_ltpf_data_t *data);

/**
 * LTPF disable
 * data            LTPF data, disabled activation on return
 */
void lc3_ltpf_disable(lc3_ltpf_data_t *data);

/**
 * Return number of bits coding the bitstream data
 * pitch           True when pitch present, False otherwise
 * return          Bit consumption, including the pitch present flag
 */
int lc3_ltpf_get_nbits(bool pitch);

/**
 * Put bitstream data
 * bits            Bitstream context
 * data            LTPF data
 */
void lc3_ltpf_put_data(lc3_bits_t *bits, const lc3_ltpf_data_t *data);


/* ----------------------------------------------------------------------------
 *  Decoding
 * -------------------------------------------------------------------------- */
/**
 * Get bitstream data
 * bits            Bitstream context
 * data            Return bitstream data
 */
void lc3_ltpf_get_data(lc3_bits_t *bits, lc3_ltpf_data_t *data);

/**
 * LTPF synthesis
 * dt, sr          Duration and samplerate of the frame
 * nbytes          Size in bytes of the frame
 * ltpf            Context of synthesis
 * data            Bitstream data, NULL when pitch not present
 * xr              Base address of ring buffer of decoded samples
 * x               Samples to proceed in the ring buffer, filtered as output
 *
 * The size of the ring buffer is `nh + ns`.
 * The filtering needs an history of at least 18 ms.
 */
void lc3_ltpf_synthesize(enum lc3_dt dt, enum lc3_srate sr, int nbytes,
    lc3_ltpf_synthesis_t *ltpf, const lc3_ltpf_data_t *data,
    const float *xr, float *x);


#endif /* __LC3_LTPF_H */
