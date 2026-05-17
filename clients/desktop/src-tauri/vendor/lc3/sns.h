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
 * LC3 - Spectral Noise Shaping
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 */

#ifndef __LC3_SNS_H
#define __LC3_SNS_H

#include "common.h"
#include "bits.h"


/**
 * Bitstream data
 */

typedef struct lc3_sns_data {
    int lfcb, hfcb;
    int shape, gain;
    int idx_a, idx_b;
    bool ls_a, ls_b;
} lc3_sns_data_t;


/* ----------------------------------------------------------------------------
 *  Encoding
 * -------------------------------------------------------------------------- */

/**
 * SNS analysis
 * dt, sr          Duration and samplerate of the frame
 * eb              Energy estimation per bands, and count of bands
 * att             1: Attack detected  0: Otherwise
 * data            Return bitstream data
 * x               Spectral coefficients
 * y               Return shapped coefficients
 *
 * `x` and `y` can be the same buffer
 */
void lc3_sns_analyze(enum lc3_dt dt, enum lc3_srate sr,
    const float *eb, bool att, lc3_sns_data_t *data,
    const float *x, float *y);

/**
 * Return number of bits coding the bitstream data
 * return          Bit consumption
 */
int lc3_sns_get_nbits(void);

/**
 * Put bitstream data
 * bits            Bitstream context
 * data            Bitstream data
 */
void lc3_sns_put_data(lc3_bits_t *bits, const lc3_sns_data_t *data);


/* ----------------------------------------------------------------------------
 *  Decoding
 * -------------------------------------------------------------------------- */

/**
 * Get bitstream data
 * bits            Bitstream context
 * data            Return SNS data
 * return          0: Ok  -1: Invalid SNS data
 */
int lc3_sns_get_data(lc3_bits_t *bits, lc3_sns_data_t *data);

/**
 * SNS synthesis
 * dt, sr          Duration and samplerate of the frame
 * data            Bitstream data
 * x               Spectral coefficients
 * y               Return shapped coefficients
 *
 * `x` and `y` can be the same buffer
 */
void lc3_sns_synthesize(enum lc3_dt dt, enum lc3_srate sr,
    const lc3_sns_data_t *data, const float *x, float *y);


#endif /* __LC3_SNS_H */
