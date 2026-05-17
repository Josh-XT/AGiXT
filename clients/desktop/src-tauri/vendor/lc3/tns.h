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
 * LC3 - Temporal Noise Shaping
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 */

#ifndef __LC3_TNS_H
#define __LC3_TNS_H

#include "common.h"
#include "bits.h"


/**
 * Bitstream data
 */

typedef struct lc3_tns_data {
    int nfilters;
    bool lpc_weighting;
    int rc_order[2];
    int rc[2][8];
} lc3_tns_data_t;


/* ----------------------------------------------------------------------------
 *  Encoding
 * -------------------------------------------------------------------------- */

/**
 * TNS analysis
 * dt, bw          Duration and bandwidth of the frame
 * nn_flag         True when high energy detected near Nyquist frequency
 * nbytes          Size in bytes of the frame
 * data            Return bitstream data
 * x               Spectral coefficients, filtered as output
 */
void lc3_tns_analyze(enum lc3_dt dt, enum lc3_bandwidth bw,
    bool nn_flag, int nbytes, lc3_tns_data_t *data, float *x);

/**
 * Return number of bits coding the data
 * data            Bitstream data
 * return          Bit consumption
 */
int lc3_tns_get_nbits(const lc3_tns_data_t *data);

/**
 * Put bitstream data
 * bits            Bitstream context
 * data            Bitstream data
 */
void lc3_tns_put_data(lc3_bits_t *bits, const lc3_tns_data_t *data);


/* ----------------------------------------------------------------------------
 *  Decoding
 * -------------------------------------------------------------------------- */

/**
 * Get bitstream data
 * bits            Bitstream context
 * dt, bw          Duration and bandwidth of the frame
 * nbytes          Size in bytes of the frame
 * data            Bitstream data
 */
void lc3_tns_get_data(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_bandwidth bw, int nbytes, lc3_tns_data_t *data);

/**
 * TNS synthesis
 * dt, bw          Duration and bandwidth of the frame
 * data            Bitstream data
 * x               Spectral coefficients, filtered as output
 */
void lc3_tns_synthesize(enum lc3_dt dt, enum lc3_bandwidth bw,
    const lc3_tns_data_t *data, float *x);


#endif /* __LC3_TNS_H */
