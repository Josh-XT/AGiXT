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

#include "ltpf.h"
#include "tables.h"

#include "ltpf_neon.h"
#include "ltpf_arm.h"


/* ----------------------------------------------------------------------------
 *  Resampling
 * -------------------------------------------------------------------------- */

/**
 * Resampling coefficients
 * The coefficients, in fixed Q15, are reordered by phase for each source
 * samplerate (coefficient matrix transposed)
 */

#ifndef resample_8k_12k8
static const int16_t h_8k_12k8_q15[8*10] = {
      214,   417, -1052, -4529, 26233, -4529, -1052,   417,   214,     0,
      180,     0, -1522, -2427, 24506, -5289,     0,   763,   156,   -28,
       92,  -323, -1361,     0, 19741, -3885,  1317,   861,     0,   -61,
        0,  -457,  -752,  1873, 13068,     0,  2389,   598,  -213,   -79,
      -61,  -398,     0,  2686,  5997,  5997,  2686,     0,  -398,   -61,
      -79,  -213,   598,  2389,     0, 13068,  1873,  -752,  -457,     0,
      -61,     0,   861,  1317, -3885, 19741,     0, -1361,  -323,    92,
      -28,   156,   763,     0, -5289, 24506, -2427, -1522,     0,   180,
};
#endif /* resample_8k_12k8 */

#ifndef resample_16k_12k8
static const int16_t h_16k_12k8_q15[4*20] = {
      -61,   214,  -398,   417,     0, -1052,  2686, -4529,  5997, 26233,
     5997, -4529,  2686, -1052,     0,   417,  -398,   214,   -61,     0,

      -79,   180,  -213,     0,   598, -1522,  2389, -2427,     0, 24506,
    13068, -5289,  1873,     0,  -752,   763,  -457,   156,     0,   -28,

      -61,    92,     0,  -323,   861, -1361,  1317,     0, -3885, 19741,
    19741, -3885,     0,  1317, -1361,   861,  -323,     0,    92,   -61,

      -28,     0,   156,  -457,   763,  -752,     0,  1873, -5289, 13068,
    24506,     0, -2427,  2389, -1522,   598,     0,  -213,   180,   -79,
};
#endif /* resample_16k_12k8 */

#ifndef resample_32k_12k8
static const int16_t h_32k_12k8_q15[2*40] = {
      -30,   -31,    46,   107,     0,  -199,  -162,   209,   430,     0,
     -681,  -526,   658,  1343,     0, -2264, -1943,  2999,  9871, 13116,
     9871,  2999, -1943, -2264,     0,  1343,   658,  -526,  -681,     0,
      430,   209,  -162,  -199,     0,   107,    46,   -31,   -30,     0,

      -14,   -39,     0,    90,    78,  -106,  -229,     0,   382,   299,
     -376,  -761,     0,  1194,   937, -1214, -2644,     0,  6534, 12253,
    12253,  6534,     0, -2644, -1214,   937,  1194,     0,  -761,  -376,
      299,   382,     0,  -229,  -106,    78,    90,     0,   -39,   -14,
};
#endif /* resample_32k_12k8 */

#ifndef resample_24k_12k8
static const int16_t h_24k_12k8_q15[8*30] = {
      -50,    19,   143,   -93,  -290,   278,   485,  -658,  -701,  1396,
      901, -3019, -1042, 10276, 17488, 10276, -1042, -3019,   901,  1396,
     -701,  -658,   485,   278,  -290,   -93,   143,    19,   -50,     0,

      -46,     0,   141,   -45,  -305,   185,   543,  -501,  -854,  1153,
     1249, -2619, -1908,  8712, 17358, 11772,     0, -3319,   480,  1593,
     -504,  -796,   399,   367,  -261,  -142,   138,    40,   -52,    -5,

      -41,   -17,   133,     0,  -304,    91,   574,  -334,  -959,   878,
     1516, -2143, -2590,  7118, 16971, 13161,  1202, -3495,     0,  1731,
     -267,  -908,   287,   445,  -215,  -188,   125,    62,   -52,   -12,

      -34,   -30,   120,    41,  -291,     0,   577,  -164, -1015,   585,
     1697, -1618, -3084,  5534, 16337, 14406,  2544, -3526,  -523,  1800,
        0,  -985,   152,   509,  -156,  -230,   104,    83,   -48,   -19,

      -26,   -41,   103,    76,  -265,   -83,   554,     0, -1023,   288,
     1791, -1070, -3393,  3998, 15474, 15474,  3998, -3393, -1070,  1791,
      288, -1023,     0,   554,   -83,  -265,    76,   103,   -41,   -26,

      -19,   -48,    83,   104,  -230,  -156,   509,   152,  -985,     0,
     1800,  -523, -3526,  2544, 14406, 16337,  5534, -3084, -1618,  1697,
      585, -1015,  -164,   577,     0,  -291,    41,   120,   -30,   -34,

      -12,   -52,    62,   125,  -188,  -215,   445,   287,  -908,  -267,
     1731,     0, -3495,  1202, 13161, 16971,  7118, -2590, -2143,  1516,
      878,  -959,  -334,   574,    91,  -304,     0,   133,   -17,   -41,

       -5,   -52,    40,   138,  -142,  -261,   367,   399,  -796,  -504,
     1593,   480, -3319,     0, 11772, 17358,  8712, -1908, -2619,  1249,
     1153,  -854,  -501,   543,   185,  -305,   -45,   141,     0,   -46,
};
#endif /* resample_24k_12k8 */

#ifndef resample_48k_12k8
static const int16_t h_48k_12k8_q15[4*60] = {
      -13,   -25,   -20,    10,    51,    71,    38,   -47,  -133,  -145,
      -42,   139,   277,   242,     0,  -329,  -511,  -351,   144,   698,
      895,   450,  -535, -1510, -1697,  -521,  1999,  5138,  7737,  8744,
     7737,  5138,  1999,  -521, -1697, -1510,  -535,   450,   895,   698,
      144,  -351,  -511,  -329,     0,   242,   277,   139,   -42,  -145,
     -133,   -47,    38,    71,    51,    10,   -20,   -25,   -13,     0,

       -9,   -23,   -24,     0,    41,    71,    52,   -23,  -115,  -152,
      -78,    92,   254,   272,    76,  -251,  -493,  -427,     0,   576,
      900,   624,  -262, -1309, -1763,  -954,  1272,  4356,  7203,  8679,
     8169,  5886,  2767,     0, -1542, -1660,  -809,   240,   848,   796,
      292,  -252,  -507,  -398,   -82,   199,   288,   183,     0,  -130,
     -145,   -71,    20,    69,    60,    20,   -15,   -26,   -17,    -3,

       -6,   -20,   -26,    -8,    31,    67,    62,     0,   -94,  -152,
     -108,    45,   223,   287,   143,  -167,  -454,  -480,  -134,   439,
      866,   758,     0, -1071, -1748, -1295,   601,  3559,  6580,  8485,
     8485,  6580,  3559,   601, -1295, -1748, -1071,     0,   758,   866,
      439,  -134,  -480,  -454,  -167,   143,   287,   223,    45,  -108,
     -152,   -94,     0,    62,    67,    31,    -8,   -26,   -20,    -6,

       -3,   -17,   -26,   -15,    20,    60,    69,    20,   -71,  -145,
     -130,     0,   183,   288,   199,   -82,  -398,  -507,  -252,   292,
      796,   848,   240,  -809, -1660, -1542,     0,  2767,  5886,  8169,
     8679,  7203,  4356,  1272,  -954, -1763, -1309,  -262,   624,   900,
      576,     0,  -427,  -493,  -251,    76,   272,   254,    92,   -78,
     -152,  -115,   -23,    52,    71,    41,     0,   -24,   -23,    -9,
};
#endif /* resample_48k_12k8 */


/**
 * High-pass 50Hz filtering, at 12.8 KHz samplerate
 * hp50            Biquad filter state
 * xn              Input sample, in fixed Q30
 * return          Filtered sample, in fixed Q30
 */
LC3_HOT static inline int32_t filter_hp50(
    struct lc3_ltpf_hp50_state *hp50, int32_t xn)
{
    int32_t yn;

    const int32_t a1 = -2110217691, a2 = 1037111617;
    const int32_t b1 = -2110535566, b2 = 1055267782;

    yn       = (hp50->s1 + (int64_t)xn * b2) >> 30;
    hp50->s1 = (hp50->s2 + (int64_t)xn * b1 - (int64_t)yn * a1);
    hp50->s2 = (           (int64_t)xn * b2 - (int64_t)yn * a2);

    return yn;
}

/**
 * Resample from 8 / 16 / 32 KHz to 12.8 KHz Template
 * p               Resampling factor with compared to 192 KHz (8, 4 or 2)
 * h               Arrange by phase coefficients table
 * hp50            High-Pass biquad filter state
 * x               [-d..-1] Previous, [0..ns-1] Current samples, Q15
 * y, n            [0..n-1] Output `n` processed samples, Q14
 *
 * The `x` vector is aligned on 32 bits
 * The number of previous samples `d` accessed on `x` is :
 *   d: { 10, 20, 40 } - 1 for resampling factors 8, 4 and 2.
 */
#if !defined(resample_8k_12k8) || !defined(resample_16k_12k8) \
    || !defined(resample_32k_12k8)
LC3_HOT static inline void resample_x64k_12k8(const int p, const int16_t *h,
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    const int w = 2*(40 / p);

    x -= w - 1;

    for (int i = 0; i < 5*n; i += 5) {
        const int16_t *hn = h + (i % p) * w;
        const int16_t *xn = x + (i / p);
        int32_t un = 0;

        for (int k = 0; k < w; k += 10) {
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
        }

        int32_t yn = filter_hp50(hp50, un);
        *(y++) = (yn + (1 << 15)) >> 16;
    }
}
#endif

/**
 * Resample from 24 / 48 KHz to 12.8 KHz Template
 * p               Resampling factor with compared to 192 KHz (8 or 4)
 * h               Arrange by phase coefficients table
 * hp50            High-Pass biquad filter state
 * x               [-d..-1] Previous, [0..ns-1] Current samples, Q15
 * y, n            [0..n-1] Output `n` processed samples, Q14
 *
 * The `x` vector is aligned on 32 bits
 * The number of previous samples `d` accessed on `x` is :
 *   d: { 30, 60 } - 1 for resampling factors 8 and 4.
 */
#if !defined(resample_24k_12k8) || !defined(resample_48k_12k8)
LC3_HOT static inline void resample_x192k_12k8(const int p, const int16_t *h,
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    const int w = 2*(120 / p);

    x -= w - 1;

    for (int i = 0; i < 15*n; i += 15) {
        const int16_t *hn = h + (i % p) * w;
        const int16_t *xn = x + (i / p);
        int32_t un = 0;

        for (int k = 0; k < w; k += 15) {
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
            un += *(xn++) * *(hn++);
        }

        int32_t yn = filter_hp50(hp50, un);
        *(y++) = (yn + (1 << 15)) >> 16;
    }
}
#endif

/**
 * Resample from 8 Khz to 12.8 KHz
 * hp50            High-Pass biquad filter state
 * x               [-10..-1] Previous, [0..ns-1] Current samples, Q15
 * y, n            [0..n-1] Output `n` processed samples, Q14
 *
 * The `x` vector is aligned on 32 bits
 */
#ifndef resample_8k_12k8
LC3_HOT static void resample_8k_12k8(
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    resample_x64k_12k8(8, h_8k_12k8_q15, hp50, x, y, n);
}
#endif /* resample_8k_12k8 */

/**
 * Resample from 16 Khz to 12.8 KHz
 * hp50            High-Pass biquad filter state
 * x               [-20..-1] Previous, [0..ns-1] Current samples, in fixed Q15
 * y, n            [0..n-1] Output `n` processed samples, in fixed Q14
 *
 * The `x` vector is aligned on 32 bits
 */
#ifndef resample_16k_12k8
LC3_HOT static void resample_16k_12k8(
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    resample_x64k_12k8(4, h_16k_12k8_q15, hp50, x, y, n);
}
#endif /* resample_16k_12k8 */

/**
 * Resample from 32 Khz to 12.8 KHz
 * hp50            High-Pass biquad filter state
 * x               [-30..-1] Previous, [0..ns-1] Current samples, in fixed Q15
 * y, n            [0..n-1] Output `n` processed samples, in fixed Q14
 *
 * The `x` vector is aligned on 32 bits
 */
#ifndef resample_32k_12k8
LC3_HOT static void resample_32k_12k8(
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    resample_x64k_12k8(2, h_32k_12k8_q15, hp50, x, y, n);
}
#endif /* resample_32k_12k8 */

/**
 * Resample from 24 Khz to 12.8 KHz
 * hp50            High-Pass biquad filter state
 * x               [-30..-1] Previous, [0..ns-1] Current samples, in fixed Q15
 * y, n            [0..n-1] Output `n` processed samples, in fixed Q14
 *
 * The `x` vector is aligned on 32 bits
 */
#ifndef resample_24k_12k8
LC3_HOT static void resample_24k_12k8(
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    resample_x192k_12k8(8, h_24k_12k8_q15, hp50, x, y, n);
}
#endif /* resample_24k_12k8 */

/**
 * Resample from 48 Khz to 12.8 KHz
 * hp50            High-Pass biquad filter state
 * x               [-60..-1] Previous, [0..ns-1] Current samples, in fixed Q15
 * y, n            [0..n-1] Output `n` processed samples, in fixed Q14
 *
* The `x` vector is aligned on 32 bits
*/
#ifndef resample_48k_12k8
LC3_HOT static void resample_48k_12k8(
    struct lc3_ltpf_hp50_state *hp50, const int16_t *x, int16_t *y, int n)
{
    resample_x192k_12k8(4, h_48k_12k8_q15, hp50, x, y, n);
}
#endif /* resample_48k_12k8 */

/**
* Resample to 6.4 KHz
* x               [-3..-1] Previous, [0..n-1] Current samples
* y, n            [0..n-1] Output `n` processed samples
*
* The `x` vector is aligned on 32 bits
 */
#ifndef resample_6k4
LC3_HOT static void resample_6k4(const int16_t *x, int16_t *y, int n)
{
    static const int16_t h[] = { 18477, 15424, 8105 };
    const int16_t *ye = y + n;

    for (x--; y < ye; x += 2)
        *(y++) = (x[0] * h[0] + (x[-1] + x[1]) * h[1]
                              + (x[-2] + x[2]) * h[2]) >> 16;
}
#endif /* resample_6k4 */

/**
 * LTPF Resample to 12.8 KHz implementations for each samplerates
 */

static void (* const resample_12k8[])
    (struct lc3_ltpf_hp50_state *, const int16_t *, int16_t *, int ) =
{
    [LC3_SRATE_8K ] = resample_8k_12k8,
    [LC3_SRATE_16K] = resample_16k_12k8,
    [LC3_SRATE_24K] = resample_24k_12k8,
    [LC3_SRATE_32K] = resample_32k_12k8,
    [LC3_SRATE_48K] = resample_48k_12k8,
};


/* ----------------------------------------------------------------------------
 *  Analysis
 * -------------------------------------------------------------------------- */

/**
 * Return dot product of 2 vectors
 * a, b, n         The 2 vectors of size `n` (> 0 and <= 128)
 * return          sum( a[i] * b[i] ), i = [0..n-1]
 *
 * The size `n` of vectors must be multiple of 16, and less or equal to 128
*/
#ifndef dot
LC3_HOT static inline float dot(const int16_t *a, const int16_t *b, int n)
{
    int64_t v = 0;

    for (int i = 0; i < (n >> 4); i++)
        for (int j = 0; j < 16; j++)
            v += *(a++) * *(b++);

    int32_t v32 = (v + (1 << 5)) >> 6;
    return (float)v32;
}
#endif /* dot */

/**
 * Return vector of correlations
 * a, b, n         The 2 vector of size `n` (> 0 and <= 128)
 * y, nc           Output the correlation vector of size `nc`
 *
 * The first vector `a` is aligned of 32 bits
 * The size `n` of vectors is multiple of 16, and less or equal to 128
 */
#ifndef correlate
LC3_HOT static void correlate(
    const int16_t *a, const int16_t *b, int n, float *y, int nc)
{
    for (const float *ye = y + nc; y < ye; )
        *(y++) = dot(a, b--, n);
}
#endif /* correlate */

/**
 * Search the maximum value and returns its argument
 * x, n            The input vector of size `n`
 * x_max           Return the maximum value
 * return          Return the argument of the maximum
 */
LC3_HOT static int argmax(const float *x, int n, float *x_max)
{
    int arg = 0;

    *x_max = x[arg = 0];
    for (int i = 1; i < n; i++)
        if (*x_max < x[i])
            *x_max = x[arg = i];

    return arg;
}

/**
 * Search the maximum weithed value and returns its argument
 * x, n            The input vector of size `n`
 * w_incr          Increment of the weight
 * x_max, xw_max   Return the maximum not weighted value
 * return          Return the argument of the weigthed maximum
 */
LC3_HOT static int argmax_weighted(
    const float *x, int n, float w_incr, float *x_max)
{
    int arg;

    float xw_max = (*x_max = x[arg = 0]);
    float w = 1 + w_incr;

    for (int i = 1; i < n; i++, w += w_incr)
        if (xw_max < x[i] * w)
            xw_max = (*x_max = x[arg = i]) * w;

    return arg;
}

/**
 * Interpolate from pitch detected value (3.3.9.8)
 * x, n            [-2..-1] Previous, [0..n] Current input
 * d               The phase of interpolation (0 to 3)
 * return          The interpolated vector
 *
 * The size `n` of vectors must be multiple of 4
 */
LC3_HOT static void interpolate(const int16_t *x, int n, int d, int16_t *y)
{
    static const int16_t h4_q15[][4] = {
        { 6877, 19121,  6877,     0 }, { 3506, 18025, 11000,   220 },
        { 1300, 15048, 15048,  1300 }, {  220, 11000, 18025,  3506 } };

    const int16_t *h = h4_q15[d];
    int16_t x3 = x[-2], x2 = x[-1], x1, x0;

    x1 = (*x++);
    for (const int16_t *ye = y + n; y < ye; ) {
        int32_t yn;

        yn = (x0 = *(x++)) * h[0] + x1 * h[1] + x2 * h[2] + x3 * h[3];
        *(y++) = yn >> 15;

        yn = (x3 = *(x++)) * h[0] + x0 * h[1] + x1 * h[2] + x2 * h[3];
        *(y++) = yn >> 15;

        yn = (x2 = *(x++)) * h[0] + x3 * h[1] + x0 * h[2] + x1 * h[3];
        *(y++) = yn >> 15;

        yn = (x1 = *(x++)) * h[0] + x2 * h[1] + x3 * h[2] + x0 * h[3];
        *(y++) = yn >> 15;
    }
}

/**
 * Interpolate autocorrelation (3.3.9.7)
 * x               [-4..-1] Previous, [0..4] Current input
 * d               The phase of interpolation (-3 to 3)
 * return          The interpolated value
 */
LC3_HOT static float interpolate_corr(const float *x, int d)
{
    static const float h4[][8] = {
        {  1.53572770e-02, -4.72963246e-02,  8.35788573e-02,  8.98638285e-01,
           8.35788573e-02, -4.72963246e-02,  1.53572770e-02,                 },
        {  2.74547165e-03,  4.59833449e-03, -7.54404636e-02,  8.17488686e-01,
           3.30182571e-01, -1.05835916e-01,  2.86823405e-02, -2.87456116e-03 },
        { -3.00125103e-03,  2.95038503e-02, -1.30305021e-01,  6.03297008e-01,
           6.03297008e-01, -1.30305021e-01,  2.95038503e-02, -3.00125103e-03 },
        { -2.87456116e-03,  2.86823405e-02, -1.05835916e-01,  3.30182571e-01,
           8.17488686e-01, -7.54404636e-02,  4.59833449e-03,  2.74547165e-03 },
    };

    const float *h = h4[(4+d) % 4];

    float y = d < 0 ? x[-4] * *(h++) :
              d > 0 ? x[ 4] * *(h+7) : 0;

    y += x[-3] * h[0] + x[-2] * h[1] + x[-1] * h[2] + x[0] * h[3] +
         x[ 1] * h[4] + x[ 2] * h[5] + x[ 3] * h[6];

    return y;
}

/**
 * Pitch detection algorithm (3.3.9.5-6)
 * ltpf            Context of analysis
 * x, n            [-114..-17] Previous, [0..n-1] Current 6.4KHz samples
 * tc              Return the pitch-lag estimation
 * return          True when pitch present
 *
 * The `x` vector is aligned on 32 bits
 */
static bool detect_pitch(
    struct lc3_ltpf_analysis *ltpf, const int16_t *x, int n, int *tc)
{
    float rm1, rm2;
    float r[98];

    const int r0 = 17, nr = 98;
    int k0 = LC3_MAX(   0, ltpf->tc-4);
    int nk = LC3_MIN(nr-1, ltpf->tc+4) - k0 + 1;

    correlate(x, x - r0, n, r, nr);

    int t1 = argmax_weighted(r, nr, -.5f/(nr-1), &rm1);
    int t2 = k0 + argmax(r + k0, nk, &rm2);

    const int16_t *x1 = x - (r0 + t1);
    const int16_t *x2 = x - (r0 + t2);

    float nc1 = rm1 <= 0 ? 0 :
        rm1 / sqrtf(dot(x, x, n) * dot(x1, x1, n));

    float nc2 = rm2 <= 0 ? 0 :
        rm2 / sqrtf(dot(x, x, n) * dot(x2, x2, n));

    int t1sel = nc2 <= 0.85f * nc1;
    ltpf->tc = (t1sel ? t1 : t2);

    *tc = r0 + ltpf->tc;
    return (t1sel ? nc1 : nc2) > 0.6f;
}

/**
 * Pitch-lag parameter (3.3.9.7)
 * x, n            [-232..-28] Previous, [0..n-1] Current 12.8KHz samples, Q14
 * tc              Pitch-lag estimation
 * pitch           The pitch value, in fixed .4
 * return          The bitstream pitch index value
 *
 * The `x` vector is aligned on 32 bits
 */
static int refine_pitch(const int16_t *x, int n, int tc, int *pitch)
{
    float r[17], rm;
    int e, f;

    int r0 = LC3_MAX( 32, 2*tc - 4);
    int nr = LC3_MIN(228, 2*tc + 4) - r0 + 1;

    correlate(x, x - (r0 - 4), n, r, nr + 8);

    e = r0 + argmax(r + 4, nr, &rm);
    const float *re = r + (e - (r0 - 4));

    float dm = interpolate_corr(re, f = 0);
    for (int i = 1; i <= 3; i++) {
        float d;

        if (e >= 127 && ((i & 1) | (e >= 157)))
            continue;

        if ((d = interpolate_corr(re, i)) > dm)
            dm = d, f = i;

        if (e > 32 && (d = interpolate_corr(re, -i)) > dm)
            dm = d, f = -i;
    }

    e -=   (f < 0);
    f += 4*(f < 0);

    *pitch = 4*e + f;
    return e < 127 ? 4*e +  f       - 128 :
           e < 157 ? 2*e + (f >> 1) + 126 : e + 283;
}

/**
 * LTPF Analysis
 */
bool lc3_ltpf_analyse(
    enum lc3_dt dt, enum lc3_srate sr, struct lc3_ltpf_analysis *ltpf,
    const int16_t *x, struct lc3_ltpf_data *data)
{
    /* --- Resampling to 12.8 KHz --- */

    int z_12k8 = sizeof(ltpf->x_12k8) / sizeof(*ltpf->x_12k8);
    int n_12k8 = dt == LC3_DT_7M5 ? 96 : 128;

    memmove(ltpf->x_12k8, ltpf->x_12k8 + n_12k8,
        (z_12k8 - n_12k8) * sizeof(*ltpf->x_12k8));

    int16_t *x_12k8 = ltpf->x_12k8 + (z_12k8 - n_12k8);

    resample_12k8[sr](&ltpf->hp50, x, x_12k8, n_12k8);

    x_12k8 -= (dt == LC3_DT_7M5 ? 44 :  24);

    /* --- Resampling to 6.4 KHz --- */

    int z_6k4 = sizeof(ltpf->x_6k4) / sizeof(*ltpf->x_6k4);
    int n_6k4 = n_12k8 >> 1;

    memmove(ltpf->x_6k4, ltpf->x_6k4 + n_6k4,
        (z_6k4 - n_6k4) * sizeof(*ltpf->x_6k4));

    int16_t *x_6k4 = ltpf->x_6k4 + (z_6k4 - n_6k4);

    resample_6k4(x_12k8, x_6k4, n_6k4);

    /* --- Pitch detection --- */

    int tc, pitch = 0;
    float nc = 0;

    bool pitch_present = detect_pitch(ltpf, x_6k4, n_6k4, &tc);

    if (pitch_present) {
        int16_t u[128], v[128];

        data->pitch_index = refine_pitch(x_12k8, n_12k8, tc, &pitch);

        interpolate(x_12k8, n_12k8, 0, u);
        interpolate(x_12k8 - (pitch >> 2), n_12k8, pitch & 3, v);

        nc = dot(u, v, n_12k8) / sqrtf(dot(u, u, n_12k8) * dot(v, v, n_12k8));
    }

    /* --- Activation --- */

     if (ltpf->active) {
        int pitch_diff =
            LC3_MAX(pitch, ltpf->pitch) - LC3_MIN(pitch, ltpf->pitch);
        float nc_diff = nc - ltpf->nc[0];

        data->active = pitch_present &&
            ((nc > 0.9f) || (nc > 0.84f && pitch_diff < 8 && nc_diff > -0.1f));

     } else {
         data->active = pitch_present &&
            ( (dt == LC3_DT_10M || ltpf->nc[1] > 0.94f) &&
              (ltpf->nc[0] > 0.94f && nc > 0.94f) );
     }

     ltpf->active = data->active;
     ltpf->pitch = pitch;
     ltpf->nc[1] = ltpf->nc[0];
     ltpf->nc[0] = nc;

     return pitch_present;
}


/* ----------------------------------------------------------------------------
 *  Synthesis
 * -------------------------------------------------------------------------- */

/**
 * Width of synthesis filter
 */

#define FILTER_WIDTH(sr) \
  LC3_MAX(4, LC3_SRATE_KHZ(sr) / 4)

#define MAX_FILTER_WIDTH \
  FILTER_WIDTH(LC3_NUM_SRATE)


/**
 * Synthesis filter template
 * xh, nh          History ring buffer of filtered samples
 * lag             Lag parameter in the ring buffer
 * x0              w-1 previous input samples
 * x, n            Current samples as input, filtered as output
 * c, w            Coefficients `den` then `num`, and width of filter
 * fade            Fading mode of filter  -1: Out  1: In  0: None
 */
LC3_HOT static inline void synthesize_template(
    const float *xh, int nh, int lag,
    const float *x0, float *x, int n,
    const float *c, const int w, int fade)
{
    float g = (float)(fade <= 0);
    float g_incr = (float)((fade > 0) - (fade < 0)) / n;
    float u[MAX_FILTER_WIDTH];

    /* --- Load previous samples --- */

    lag += (w >> 1);

    const float *y = x - xh < lag ? x + (nh - lag) : x - lag;
    const float *y_end = xh + nh - 1;

    for (int j = 0; j < w-1; j++) {

        u[j] = 0;

        float yi = *y, xi = *(x0++);
        y = y < y_end ? y + 1 : xh;

        for (int k = 0; k <= j; k++)
            u[j-k] -= yi * c[k];

        for (int k = 0; k <= j; k++)
            u[j-k] += xi * c[w+k];
    }

    u[w-1] = 0;

    /* --- Process by filter length --- */

    for (int i = 0; i < n; i += w)
        for (int j = 0; j < w; j++, g += g_incr) {

            float yi = *y, xi = *x;
            y = y < y_end ? y + 1 : xh;

            for (int k = 0; k < w; k++)
                u[(j+(w-1)-k)%w] -= yi * c[k];

            for (int k = 0; k < w; k++)
                u[(j+(w-1)-k)%w] += xi * c[w+k];

            *(x++) = xi - g * u[j];
            u[j] = 0;
        }
}

/**
 * Synthesis filter for each samplerates (width of filter)
 */


LC3_HOT static void synthesize_4(const float *xh, int nh, int lag,
    const float *x0, float *x, int n, const float *c, int fade)
{
    synthesize_template(xh, nh, lag, x0, x, n, c, 4, fade);
}

LC3_HOT static void synthesize_6(const float *xh, int nh, int lag,
    const float *x0, float *x, int n, const float *c, int fade)
{
    synthesize_template(xh, nh, lag, x0, x, n, c, 6, fade);
}

LC3_HOT static void synthesize_8(const float *xh, int nh, int lag,
    const float *x0, float *x, int n, const float *c, int fade)
{
    synthesize_template(xh, nh, lag, x0, x, n, c, 8, fade);
}

LC3_HOT static void synthesize_12(const float *xh, int nh, int lag,
    const float *x0, float *x, int n, const float *c, int fade)
{
    synthesize_template(xh, nh, lag, x0, x, n, c, 12, fade);
}

static void (* const synthesize[])(const float *, int, int,
    const float *, float *, int, const float *, int) =
{
    [LC3_SRATE_8K ] = synthesize_4,
    [LC3_SRATE_16K] = synthesize_4,
    [LC3_SRATE_24K] = synthesize_6,
    [LC3_SRATE_32K] = synthesize_8,
    [LC3_SRATE_48K] = synthesize_12,
};


/**
 * LTPF Synthesis
 */
void lc3_ltpf_synthesize(enum lc3_dt dt, enum lc3_srate sr, int nbytes,
    lc3_ltpf_synthesis_t *ltpf, const lc3_ltpf_data_t *data,
    const float *xh, float *x)
{
    int nh = LC3_NH(dt, sr);
    int dt_us = LC3_DT_US(dt);

    /* --- Filter parameters --- */

    int p_idx = data ? data->pitch_index : 0;
    int pitch =
        p_idx >= 440 ? (((p_idx     ) - 283) << 2)  :
        p_idx >= 380 ? (((p_idx >> 1) -  63) << 2) + (((p_idx & 1)) << 1) :
                       (((p_idx >> 2) +  32) << 2) + (((p_idx & 3)) << 0)  ;

    pitch = (pitch * LC3_SRATE_KHZ(sr) * 10 + 64) / 128;

    int nbits = (nbytes*8 * 10000 + (dt_us/2)) / dt_us;
    int g_idx = LC3_MAX(nbits / 80, 3 + (int)sr) - (3 + sr);
    bool active = data && data->active && g_idx < 4;

    int w = FILTER_WIDTH(sr);
    float c[2 * MAX_FILTER_WIDTH];

    for (int i = 0; i < w; i++) {
        float g = active ? 0.4f - 0.05f * g_idx : 0;
        c[  i] = g * lc3_ltpf_cden[sr][pitch & 3][(w-1)-i];
        c[w+i] = 0.85f * g * lc3_ltpf_cnum[sr][LC3_MIN(g_idx, 3)][(w-1)-i];
    }

    /* --- Transition handling --- */

    int ns = LC3_NS(dt, sr);
    int nt = ns / (3 + dt);
    float x0[MAX_FILTER_WIDTH];

    if (active)
        memcpy(x0, x + nt-(w-1), (w-1) * sizeof(float));

    if (!ltpf->active && active)
        synthesize[sr](xh, nh, pitch/4, ltpf->x, x, nt, c, 1);
    else if (ltpf->active && !active)
        synthesize[sr](xh, nh, ltpf->pitch/4, ltpf->x, x, nt, ltpf->c, -1);
    else if (ltpf->active && active && ltpf->pitch == pitch)
        synthesize[sr](xh, nh, pitch/4, ltpf->x, x, nt, c, 0);
    else if (ltpf->active && active) {
        synthesize[sr](xh, nh, ltpf->pitch/4, ltpf->x, x, nt, ltpf->c, -1);
        synthesize[sr](xh, nh, pitch/4,
            (x <= xh ? x + nh : x) - (w-1), x, nt, c, 1);
    }

    /* --- Remainder --- */

    memcpy(ltpf->x, x + ns - (w-1), (w-1) * sizeof(float));

    if (active)
        synthesize[sr](xh, nh, pitch/4, x0, x + nt, ns-nt, c, 0);

    /* --- Update state --- */

    ltpf->active = active;
    ltpf->pitch = pitch;
    memcpy(ltpf->c, c, 2*w * sizeof(*ltpf->c));
}


/* ----------------------------------------------------------------------------
 *  Bitstream data
 * -------------------------------------------------------------------------- */

/**
 * LTPF disable
 */
void lc3_ltpf_disable(struct lc3_ltpf_data *data)
{
    data->active = false;
}

/**
 * Return number of bits coding the bitstream data
 */
int lc3_ltpf_get_nbits(bool pitch)
{
    return 1 + 10 * pitch;
}

/**
 * Put bitstream data
 */
void lc3_ltpf_put_data(lc3_bits_t *bits,
    const struct lc3_ltpf_data *data)
{
    lc3_put_bit(bits, data->active);
    lc3_put_bits(bits, data->pitch_index, 9);
}

/**
 * Get bitstream data
 */
void lc3_ltpf_get_data(lc3_bits_t *bits, struct lc3_ltpf_data *data)
{
    data->active = lc3_get_bit(bits);
    data->pitch_index = lc3_get_bits(bits, 9);
}
