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

#include "bwdet.h"


/**
 * Bandwidth detector
 */
enum lc3_bandwidth lc3_bwdet_run(
    enum lc3_dt dt, enum lc3_srate sr, const float *e)
{
    /* Bandwidth regions (Table 3.6)  */

    struct region { int is : 8; int ie : 8; };

    static const struct region bws_table[LC3_NUM_DT]
            [LC3_NUM_BANDWIDTH-1][LC3_NUM_BANDWIDTH-1] = {

        [LC3_DT_7M5] = {
            { { 51, 63+1 } },
            { { 45, 55+1 }, { 58, 63+1 } },
            { { 42, 51+1 }, { 53, 58+1 }, { 60, 63+1 } },
            { { 40, 48+1 }, { 51, 55+1 }, { 57, 60+1 }, { 61, 63+1 } },
        },

        [LC3_DT_10M] = {
            { { 53, 63+1 } },
            { { 47, 56+1 }, { 59, 63+1 } },
            { { 44, 52+1 }, { 54, 59+1 }, { 60, 63+1 } },
            { { 41, 49+1 }, { 51, 55+1 }, { 57, 60+1 }, { 61, 63+1 } },
        },
    };

    static const int l_table[LC3_NUM_DT][LC3_NUM_BANDWIDTH-1] = {
        [LC3_DT_7M5] = { 4, 4, 3, 2 },
        [LC3_DT_10M] = { 4, 4, 3, 1 },
    };

    /* --- Stage 1 ---
     * Determine bw0 candidate */

    enum lc3_bandwidth bw0 = LC3_BANDWIDTH_NB;
    enum lc3_bandwidth bwn = (enum lc3_bandwidth)sr;

    if (bwn <= bw0)
        return bwn;

    const struct region *bwr = bws_table[dt][bwn-1];

    for (enum lc3_bandwidth bw = bw0; bw < bwn; bw++) {
        int i = bwr[bw].is, ie = bwr[bw].ie;
        int n = ie - i;

        float se = e[i];
        for (i++; i < ie; i++)
            se += e[i];

        if (se >= (10 << (bw == LC3_BANDWIDTH_NB)) * n)
            bw0 = bw + 1;
    }

    /* --- Stage 2 ---
     * Detect drop above cut-off frequency.
     * The Tc condition (13) is precalculated, as
     * Tc[] = 10 ^ (n / 10) , n = { 15, 23, 20, 20 } */

    int hold = bw0 >= bwn;

    if (!hold) {
        int i0 = bwr[bw0].is, l = l_table[dt][bw0];
        float tc = (const float []){
             31.62277660, 199.52623150, 100, 100 }[bw0];

        for (int i = i0 - l + 1; !hold && i <= i0 + 1; i++) {
            hold = e[i-l] > tc * e[i];
        }

    }

    return hold ? bw0 : bwn;
}

/**
 * Return number of bits coding the bandwidth value
 */
int lc3_bwdet_get_nbits(enum lc3_srate sr)
{
    return (sr > 0) + (sr > 1) + (sr > 3);
}

/**
 * Put bandwidth indication
 */
void lc3_bwdet_put_bw(lc3_bits_t *bits,
    enum lc3_srate sr, enum lc3_bandwidth bw)
{
    int nbits_bw = lc3_bwdet_get_nbits(sr);
    if (nbits_bw > 0)
        lc3_put_bits(bits, bw, nbits_bw);
}

/**
 * Get bandwidth indication
 */
int lc3_bwdet_get_bw(lc3_bits_t *bits,
    enum lc3_srate sr, enum lc3_bandwidth *bw)
{
    enum lc3_bandwidth max_bw = (enum lc3_bandwidth)sr;
    int nbits_bw = lc3_bwdet_get_nbits(sr);

    *bw = nbits_bw > 0 ? lc3_get_bits(bits, nbits_bw) : LC3_BANDWIDTH_NB;
    return *bw > max_bw ? (*bw = max_bw), -1 : 0;
}
