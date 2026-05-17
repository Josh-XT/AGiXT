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
 * LC3 - Bandwidth detector
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 */

#ifndef __LC3_BWDET_H
#define __LC3_BWDET_H

#include "common.h"
#include "bits.h"


/**
 * Bandwidth detector (cf. 3.3.5)
 * dt, sr          Duration and samplerate of the frame
 * e               Energy estimation per bands
 * return          Return detected bandwitdth
 */
enum lc3_bandwidth lc3_bwdet_run(
    enum lc3_dt dt, enum lc3_srate sr, const float *e);

/**
 * Return number of bits coding the bandwidth value
 * sr              Samplerate of the frame
 * return          Number of bits coding the bandwidth value
 */
int lc3_bwdet_get_nbits(enum lc3_srate sr);

/**
 * Put bandwidth indication
 * bits            Bitstream context
 * sr              Samplerate of the frame
 * bw              Bandwidth detected
 */
void lc3_bwdet_put_bw(lc3_bits_t *bits,
    enum lc3_srate sr, enum lc3_bandwidth bw);

/**
 * Get bandwidth indication
 * bits            Bitstream context
 * sr              Samplerate of the frame
 * bw              Return bandwidth indication
 * return          0: Ok  -1: Invalid bandwidth indication
 */
int lc3_bwdet_get_bw(lc3_bits_t *bits,
    enum lc3_srate sr, enum lc3_bandwidth *bw);


#endif /* __LC3_BWDET_H */
