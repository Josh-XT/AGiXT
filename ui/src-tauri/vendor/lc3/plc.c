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

#include "plc.h"


/**
 * Reset Packet Loss Concealment state
 */
void lc3_plc_reset(struct lc3_plc_state *plc)
{
    plc->seed = 24607;
    lc3_plc_suspend(plc);
}

/**
 * Suspend PLC execution (Good frame received)
 */
void lc3_plc_suspend(struct lc3_plc_state *plc)
{
    plc->count = 1;
    plc->alpha = 1.0f;
}

/**
 * Synthesis of a PLC frame
 */
void lc3_plc_synthesize(enum lc3_dt dt, enum lc3_srate sr,
    struct lc3_plc_state *plc, const float *x, float *y)
{
    uint16_t seed = plc->seed;
    float alpha = plc->alpha;
    int ne = LC3_NE(dt, sr);

    alpha *= (plc->count < 4 ? 1.0f :
              plc->count < 8 ? 0.9f : 0.85f);

    for (int i = 0; i < ne; i++) {
        seed = (16831 + seed * 12821) & 0xffff;
        y[i] = alpha * (seed & 0x8000 ? -x[i] : x[i]);
    }

    plc->seed = seed;
    plc->alpha = alpha;
    plc->count++;
}
