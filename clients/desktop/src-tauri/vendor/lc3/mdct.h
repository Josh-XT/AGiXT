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
 * LC3 - Compute LD-MDCT (Low Delay Modified Discret Cosinus Transform)
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 */

#ifndef __LC3_MDCT_H
#define __LC3_MDCT_H

#include "common.h"


/**
 * Forward MDCT transformation
 * dt, sr          Duration and samplerate (size of the transform)
 * sr_dst          Samplerate destination, scale transforam accordingly
 * x, d            Temporal samples and delayed buffer
 * y, d            Output `ns` coefficients and `nd` delayed samples
 *
 * `x` and `y` can be the same buffer
 */
void lc3_mdct_forward(enum lc3_dt dt, enum lc3_srate sr,
    enum lc3_srate sr_dst, const float *x, float *d, float *y);

/**
 * Inverse MDCT transformation
 * dt, sr          Duration and samplerate (size of the transform)
 * sr_src          Samplerate source, scale transforam accordingly
 * x, d            Frequency coefficients and delayed buffer
 * y, d            Output `ns` samples and `nd` delayed ones
 *
 * `x` and `y` can be the same buffer
 */
void lc3_mdct_inverse(enum lc3_dt dt, enum lc3_srate sr,
    enum lc3_srate sr_src, const float *x, float *d, float *y);


#endif /* __LC3_MDCT_H */
