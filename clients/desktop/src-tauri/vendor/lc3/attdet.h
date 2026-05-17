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
 * LC3 - Time domain attack detector
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 */

#ifndef __LC3_ATTDET_H
#define __LC3_ATTDET_H

#include "common.h"


/**
 * Time domain attack detector
 * dt, sr          Duration and samplerate of the frame
 * nbytes          Size in bytes of the frame
 * attdet          Context of the Attack Detector
 * x               [-6..-1] Previous, [0..ns-1] Current samples
 * return          1: Attack detected  0: Otherwise
 */
bool lc3_attdet_run(enum lc3_dt dt, enum lc3_srate sr,
    int nbytes, lc3_attdet_analysis_t *attdet, const int16_t *x);


#endif /* __LC3_ATTDET_H */
