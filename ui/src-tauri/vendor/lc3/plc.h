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
 * LC3 - Packet Loss Concealment
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 */

#ifndef __LC3_PLC_H
#define __LC3_PLC_H

#include "common.h"


/**
 * Reset PLC state
 * plc             PLC State to reset
 */
void lc3_plc_reset(lc3_plc_state_t *plc);

/**
 * Suspend PLC synthesis (Error-free frame decoded)
 * plc             PLC State
 */
void lc3_plc_suspend(lc3_plc_state_t *plc);

/**
 * Synthesis of a PLC frame
 * dt, sr          Duration and samplerate of the frame
 * plc             PLC State
 * x               Last good spectral coefficients
 * y               Return emulated ones
 *
 * `x` and `y` can be the same buffer
 */
void lc3_plc_synthesize(enum lc3_dt dt, enum lc3_srate sr,
    lc3_plc_state_t *plc, const float *x, float *y);


#endif /* __LC3_PLC_H */
