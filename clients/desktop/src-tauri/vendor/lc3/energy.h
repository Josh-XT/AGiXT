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
 * LC3 - Energy estimation per band
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 */

#ifndef __LC3_ENERGY_H
#define __LC3_ENERGY_H

#include "common.h"


/**
 * Energy estimation per band
 * dt, sr          Duration and samplerate of the frame
 * x               Input MDCT coefficient
 * e               Energy estimation per bands
 * return          True when high energy detected near Nyquist frequency
 */
bool lc3_energy_compute(
    enum lc3_dt dt, enum lc3_srate sr, const float *x, float *e);


#endif /* __LC3_ENERGY_H */
