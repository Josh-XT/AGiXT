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

#if __ARM_NEON && __ARM_ARCH_ISA_A64 && \
        !defined(TEST_ARM) || defined(TEST_NEON)

#ifndef TEST_NEON
#include <arm_neon.h>
#endif /* TEST_NEON */


/**
 * Import
 */

static inline int32_t filter_hp50(struct lc3_ltpf_hp50_state *, int32_t);


/**
 * Resample from 16 Khz to 12.8 KHz
 */
#ifndef resample_16k_12k8

LC3_HOT static void neon_resample_16k_12k8(
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    static const int16_t h[4][20] = {

    {   -61,   214,  -398,   417,     0, -1052,  2686, -4529,  5997, 26233,
       5997, -4529,  2686, -1052,     0,   417,  -398,   214,   -61,     0 },

    {   -79,   180,  -213,     0,   598, -1522,  2389, -2427,     0, 24506,
      13068, -5289,  1873,     0,  -752,   763,  -457,   156,     0,   -28 },

    {   -61,    92,     0,  -323,   861, -1361,  1317,     0, -3885, 19741,
      19741, -3885,     0,  1317, -1361,   861,  -323,     0,    92,   -61 },

    {   -28,     0,   156,  -457,   763,  -752,     0,  1873, -5289, 13068,
      24506,     0, -2427,  2389, -1522,   598,     0,  -213,   180,   -79 },

    };

    x -= 20 - 1;

    for (int i = 0; i < 5*n; i += 5) {
        const int16_t *hn = h[i & 3];
        const int16_t *xn = x + (i >> 2);
        int32x4_t un;

        un = vmull_s16(    vld1_s16(xn), vld1_s16(hn)), xn += 4, hn += 4;
        un = vmlal_s16(un, vld1_s16(xn), vld1_s16(hn)), xn += 4, hn += 4;
        un = vmlal_s16(un, vld1_s16(xn), vld1_s16(hn)), xn += 4, hn += 4;
        un = vmlal_s16(un, vld1_s16(xn), vld1_s16(hn)), xn += 4, hn += 4;
        un = vmlal_s16(un, vld1_s16(xn), vld1_s16(hn)), xn += 4, hn += 4;

        int32_t yn = filter_hp50(hp50, vaddvq_s32(un));
        *(y++) = (yn + (1 << 15)) >> 16;
    }
}

#ifndef TEST_NEON
#define resample_16k_12k8 neon_resample_16k_12k8
#endif

#endif /* resample_16k_12k8 */

/**
 * Resample from 32 Khz to 12.8 KHz
 */
#ifndef resample_32k_12k8

LC3_HOT static void neon_resample_32k_12k8(
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    x -= 40 - 1;

    static const int16_t h[2][40] = {

    {   -30,   -31,    46,   107,     0,  -199,  -162,   209,   430,     0,
       -681,  -526,   658,  1343,     0, -2264, -1943,  2999,  9871, 13116,
       9871,  2999, -1943, -2264,     0,  1343,   658,  -526,  -681,     0,
        430,   209,  -162,  -199,     0,   107,    46,   -31,   -30,     0 },

    {   -14,   -39,     0,    90,    78,  -106,  -229,     0,   382,   299,
       -376,  -761,     0,  1194,   937, -1214, -2644,     0,  6534, 12253,
      12253,  6534,     0, -2644, -1214,   937,  1194,     0,  -761,  -376,
        299,   382,     0,  -229,  -106,    78,    90,     0,   -39,   -14 },

    };

    for (int i = 0; i < 5*n; i += 5) {
        const int16_t *hn = h[i & 1];
        const int16_t *xn = x + (i >> 1);

        int32x4_t un = vmull_s16(vld1_s16(xn), vld1_s16(hn));
        xn += 4, hn += 4;

        for (int i = 1; i < 10; i++)
            un = vmlal_s16(un, vld1_s16(xn), vld1_s16(hn)), xn += 4, hn += 4;

        int32_t yn = filter_hp50(hp50, vaddvq_s32(un));
        *(y++) = (yn + (1 << 15)) >> 16;
    }
}

#ifndef TEST_NEON
#define resample_32k_12k8 neon_resample_32k_12k8
#endif

#endif /* resample_32k_12k8 */

/**
 * Resample from 48 Khz to 12.8 KHz
 */
#ifndef resample_48k_12k8

LC3_HOT static void neon_resample_48k_12k8(
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    static const int16_t alignas(16) h[4][64] = {

    {  -13,   -25,   -20,    10,    51,    71,    38,   -47,  -133,  -145,
       -42,   139,   277,   242,     0,  -329,  -511,  -351,   144,   698,
       895,   450,  -535, -1510, -1697,  -521,  1999,  5138,  7737,  8744,
      7737,  5138,  1999,  -521, -1697, -1510,  -535,   450,   895,   698,
       144,  -351,  -511,  -329,     0,   242,   277,   139,   -42,  -145,
      -133,   -47,    38,    71,    51,    10,   -20,   -25,   -13,     0 },

    {   -9,   -23,   -24,     0,    41,    71,    52,   -23,  -115,  -152,
       -78,    92,   254,   272,    76,  -251,  -493,  -427,     0,   576,
       900,   624,  -262, -1309, -1763,  -954,  1272,  4356,  7203,  8679,
      8169,  5886,  2767,     0, -1542, -1660,  -809,   240,   848,   796,
       292,  -252,  -507,  -398,   -82,   199,   288,   183,     0,  -130,
      -145,   -71,    20,    69,    60,    20,   -15,   -26,   -17,    -3 },

    {   -6,   -20,   -26,    -8,    31,    67,    62,     0,   -94,  -152,
      -108,    45,   223,   287,   143,  -167,  -454,  -480,  -134,   439,
       866,   758,     0, -1071, -1748, -1295,   601,  3559,  6580,  8485,
      8485,  6580,  3559,   601, -1295, -1748, -1071,     0,   758,   866,
       439,  -134,  -480,  -454,  -167,   143,   287,   223,    45,  -108,
      -152,   -94,     0,    62,    67,    31,    -8,   -26,   -20,    -6 },

    {   -3,   -17,   -26,   -15,    20,    60,    69,    20,   -71,  -145,
      -130,     0,   183,   288,   199,   -82,  -398,  -507,  -252,   292,
       796,   848,   240,  -809, -1660, -1542,     0,  2767,  5886,  8169,
      8679,  7203,  4356,  1272,  -954, -1763, -1309,  -262,   624,   900,
       576,     0,  -427,  -493,  -251,    76,   272,   254,    92,   -78,
      -152,  -115,   -23,    52,    71,    41,     0,   -24,   -23,    -9 },

    };

    x -= 60 - 1;

    for (int i = 0; i < 15*n; i += 15) {
        const int16_t *hn = h[i & 3];
        const int16_t *xn = x + (i >> 2);

        int32x4_t un = vmull_s16(vld1_s16(xn), vld1_s16(hn));
        xn += 4, hn += 4;

        for (int i = 1; i < 15; i++)
            un = vmlal_s16(un, vld1_s16(xn), vld1_s16(hn)), xn += 4, hn += 4;

        int32_t yn = filter_hp50(hp50, vaddvq_s32(un));
        *(y++) = (yn + (1 << 15)) >> 16;
    }
}

#ifndef TEST_NEON
#define resample_48k_12k8 neon_resample_48k_12k8
#endif

#endif /* resample_48k_12k8 */

/**
 * Return dot product of 2 vectors
 */
#ifndef dot

LC3_HOT static inline float neon_dot(const int16_t *a, const int16_t *b, int n)
{
    int64x2_t v = vmovq_n_s64(0);

    for (int i = 0; i < (n >> 4); i++) {
        int32x4_t u;

        u = vmull_s16(   vld1_s16(a), vld1_s16(b)), a += 4, b += 4;
        u = vmlal_s16(u, vld1_s16(a), vld1_s16(b)), a += 4, b += 4;
        v = vpadalq_s32(v, u);

        u = vmull_s16(   vld1_s16(a), vld1_s16(b)), a += 4, b += 4;
        u = vmlal_s16(u, vld1_s16(a), vld1_s16(b)), a += 4, b += 4;
        v = vpadalq_s32(v, u);
    }

    int32_t v32 = (vaddvq_s64(v) + (1 << 5)) >> 6;
    return (float)v32;
}

#ifndef TEST_NEON
#define dot neon_dot
#endif

#endif /* dot */

/**
 * Return vector of correlations
 */
#ifndef correlate

LC3_HOT static void neon_correlate(
    const int16_t *a, const int16_t *b, int n, float *y, int nc)
{
    for ( ; nc >= 4; nc -= 4, b -= 4) {
        const int16_t *an = (const int16_t *)a;
        const int16_t *bn = (const int16_t *)b;

        int64x2_t v0 = vmovq_n_s64(0), v1 = v0, v2 = v0, v3 = v0;
        int16x4_t ax, b0, b1;

        b0 = vld1_s16(bn-4);

        for (int i=0; i < (n >> 4); i++ )
            for (int j = 0; j < 2; j++) {
                int32x4_t u0, u1, u2, u3;

                b1 = b0;
                b0 = vld1_s16(bn), bn += 4;
                ax = vld1_s16(an), an += 4;

                u0 = vmull_s16(ax, b0);
                u1 = vmull_s16(ax, vext_s16(b1, b0, 3));
                u2 = vmull_s16(ax, vext_s16(b1, b0, 2));
                u3 = vmull_s16(ax, vext_s16(b1, b0, 1));

                b1 = b0;
                b0 = vld1_s16(bn), bn += 4;
                ax = vld1_s16(an), an += 4;

                u0 = vmlal_s16(u0, ax, b0);
                u1 = vmlal_s16(u1, ax, vext_s16(b1, b0, 3));
                u2 = vmlal_s16(u2, ax, vext_s16(b1, b0, 2));
                u3 = vmlal_s16(u3, ax, vext_s16(b1, b0, 1));

                v0 = vpadalq_s32(v0, u0);
                v1 = vpadalq_s32(v1, u1);
                v2 = vpadalq_s32(v2, u2);
                v3 = vpadalq_s32(v3, u3);
            }

        *(y++) = (float)((int32_t)((vaddvq_s64(v0) + (1 << 5)) >> 6));
        *(y++) = (float)((int32_t)((vaddvq_s64(v1) + (1 << 5)) >> 6));
        *(y++) = (float)((int32_t)((vaddvq_s64(v2) + (1 << 5)) >> 6));
        *(y++) = (float)((int32_t)((vaddvq_s64(v3) + (1 << 5)) >> 6));
    }

    for ( ; nc > 0; nc--)
        *(y++) = neon_dot(a, b--, n);
}
#endif /* correlate */

#ifndef TEST_NEON
#define correlate neon_correlate
#endif

#endif /* __ARM_NEON && __ARM_ARCH_ISA_A64 */
