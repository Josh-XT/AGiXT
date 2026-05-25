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

#include "spec.h"
#include "bits.h"
#include "tables.h"


/* ----------------------------------------------------------------------------
 *  Global Gain / Quantization
 * -------------------------------------------------------------------------- */

/**
 * Resolve quantized gain index offset
 * sr, nbytes      Samplerate and size of the frame
 * return          Gain index offset
 */
static int resolve_gain_offset(enum lc3_srate sr, int nbytes)
{
    int g_off = (nbytes * 8) / (10 * (1 + sr));
    return 105 + 5*(1 + sr) + LC3_MIN(g_off, 115);
}

/**
 * Global Gain Estimation
 * dt, sr          Duration and samplerate of the frame
 * x               Spectral coefficients
 * nbits_budget    Number of bits available coding the spectrum
 * nbits_off       Offset on the available bits, temporarily smoothed
 * g_off           Gain index offset
 * reset_off       Return True when the nbits_off must be reset
 * g_min           Return lower bound of quantized gain value
 * return          The quantized gain value
 */
LC3_HOT static int estimate_gain(
    enum lc3_dt dt, enum lc3_srate sr, const float *x,
    int nbits_budget, float nbits_off, int g_off, bool *reset_off, int *g_min)
{
    int ne = LC3_NE(dt, sr) >> 2;
    int e[LC3_MAX_NE];

    /* --- Energy (dB) by 4 MDCT blocks --- */

    float x2_max = 0;

    for (int i = 0; i < ne; i++, x += 4) {
        float x0 = x[0] * x[0];
        float x1 = x[1] * x[1];
        float x2 = x[2] * x[2];
        float x3 = x[3] * x[3];

        x2_max = fmaxf(x2_max, x0);
        x2_max = fmaxf(x2_max, x1);
        x2_max = fmaxf(x2_max, x2);
        x2_max = fmaxf(x2_max, x3);

        e[i] = fast_db_q16(fmaxf(x0 + x1 + x2 + x3, 1e-10f));
    }

    /* --- Determine gain index --- */

    int nbits = nbits_budget + nbits_off + 0.5f;
    int g_int = 255 - g_off;

    const int k_20_28 = 20.f/28 * 0x1p16f + 0.5f;
    const int k_2u7 = 2.7f * 0x1p16f + 0.5f;
    const int k_1u4 = 1.4f * 0x1p16f + 0.5f;

    for (int i = 128, j, j0 = ne-1, j1 ; i > 0; i >>= 1) {
        int gn = (g_int - i) * k_20_28;
        int v = 0;

        for (j = j0; j >= 0 && e[j] < gn; j--);

        for (j1 = j; j >= 0; j--) {
            int e_diff = e[j] - gn;

            v += e_diff < 0 ? k_2u7 :
                 e_diff < 43 << 16 ?   e_diff + ( 7 << 16)
                                   : 2*e_diff - (36 << 16);
        }

        if (v > nbits * k_1u4)
            j0 = j1;
        else
            g_int = g_int - i;
    }

    /* --- Limit gain index --- */

    *g_min = x2_max == 0 ? -g_off :
        ceilf(28 * log10f(sqrtf(x2_max) / (32768 - 0.375f)));

    *reset_off = g_int < *g_min || x2_max == 0;
    if (*reset_off)
        g_int = *g_min;

    return g_int;
}

/**
 * Global Gain Adjustment
 * sr              Samplerate of the frame
 * g_idx           The estimated quantized gain index
 * nbits           Computed number of bits coding the spectrum
 * nbits_budget    Number of bits available for coding the spectrum
 * g_idx_min       Minimum gain index value
 * return          Gain adjust value (-1 to 2)
 */
LC3_HOT static int adjust_gain(enum lc3_srate sr, int g_idx,
    int nbits, int nbits_budget, int g_idx_min)
{
    /* --- Compute delta threshold --- */

    const int *t = (const int [LC3_NUM_SRATE][3]){
        {  80,  500,  850 }, { 230, 1025, 1700 }, { 380, 1550, 2550 },
        { 530, 2075, 3400 }, { 680, 2600, 4250 }
    }[sr];

    int delta, den = 48;

    if (nbits < t[0]) {
        delta = 3*(nbits + 48);

    } else if (nbits < t[1]) {
        int n0 = 3*(t[0] + 48), range = t[1] - t[0];
        delta = n0 * range + (nbits - t[0]) * (t[1] - n0);
        den *= range;

    } else {
        delta = LC3_MIN(nbits, t[2]);
    }

    delta = (delta + den/2) / den;

    /* --- Adjust gain --- */

    if (nbits < nbits_budget - (delta + 2))
        return -(g_idx > g_idx_min);

    if (nbits > nbits_budget)
        return (g_idx < 255) + (g_idx < 254 && nbits >= nbits_budget + delta);

    return 0;
}

/**
 * Unquantize gain
 * g_int           Quantization gain value
 * return          Unquantized gain value
 */
static float unquantize_gain(int g_int)
{
    /* Unquantization gain table :
     * G[i] = 10 ^ (i / 28) , i = [0..64] */

    static const float iq_table[] = {
        1.00000000e+00, 1.08571112e+00, 1.17876863e+00, 1.27980221e+00,
        1.38949549e+00, 1.50859071e+00, 1.63789371e+00, 1.77827941e+00,
        1.93069773e+00, 2.09617999e+00, 2.27584593e+00, 2.47091123e+00,
        2.68269580e+00, 2.91263265e+00, 3.16227766e+00, 3.43332002e+00,
        3.72759372e+00, 4.04708995e+00, 4.39397056e+00, 4.77058270e+00,
        5.17947468e+00, 5.62341325e+00, 6.10540230e+00, 6.62870316e+00,
        7.19685673e+00, 7.81370738e+00, 8.48342898e+00, 9.21055318e+00,
        1.00000000e+01, 1.08571112e+01, 1.17876863e+01, 1.27980221e+01,
        1.38949549e+01, 1.50859071e+01, 1.63789371e+01, 1.77827941e+01,
        1.93069773e+01, 2.09617999e+01, 2.27584593e+01, 2.47091123e+01,
        2.68269580e+01, 2.91263265e+01, 3.16227766e+01, 3.43332002e+01,
        3.72759372e+01, 4.04708995e+01, 4.39397056e+01, 4.77058270e+01,
        5.17947468e+01, 5.62341325e+01, 6.10540230e+01, 6.62870316e+01,
        7.19685673e+01, 7.81370738e+01, 8.48342898e+01, 9.21055318e+01,
        1.00000000e+02, 1.08571112e+02, 1.17876863e+02, 1.27980221e+02,
        1.38949549e+02, 1.50859071e+02, 1.63789371e+02, 1.77827941e+02,
        1.93069773e+02
    };

    float g = iq_table[LC3_ABS(g_int) & 0x3f];
    for(int n64 = LC3_ABS(g_int) >> 6; n64--; )
        g *= iq_table[64];

    return g_int >= 0 ? g : 1 / g;
}

/**
 * Spectrum quantization
 * dt, sr          Duration and samplerate of the frame
 * g_int           Quantization gain value
 * x               Spectral coefficients, scaled as output
 * xq, nq          Output spectral quantized coefficients, and count
 *
 * The spectral coefficients `xq` are stored as :
 *   b0       0:positive or zero  1:negative
 *   b15..b1  Absolute value
 */
LC3_HOT static void quantize(enum lc3_dt dt, enum lc3_srate sr,
    int g_int, float *x, uint16_t *xq, int *nq)
{
    float g_inv = 1 / unquantize_gain(g_int);
    int ne = LC3_NE(dt, sr);

    *nq = ne;

    for (int i = 0; i < ne; i += 2) {
        uint16_t x0, x1;

        x[i+0] *= g_inv;
        x[i+1] *= g_inv;

        x0 = fminf(fabsf(x[i+0]) + 6.f/16, INT16_MAX);
        x1 = fminf(fabsf(x[i+1]) + 6.f/16, INT16_MAX);

        xq[i+0] = (x0 << 1) + ((x0 > 0) & (x[i+0] < 0));
        xq[i+1] = (x1 << 1) + ((x1 > 0) & (x[i+1] < 0));

        *nq = x0 || x1 ? ne : *nq - 2;
    }
}

/**
 * Spectrum quantization inverse
 * dt, sr          Duration and samplerate of the frame
 * g_int           Quantization gain value
 * x, nq           Spectral quantized, and count of significants
 * return          Unquantized gain value
 */
LC3_HOT static float unquantize(enum lc3_dt dt, enum lc3_srate sr,
    int g_int, float *x, int nq)
{
    float g = unquantize_gain(g_int);
    int i, ne = LC3_NE(dt, sr);

    for (i = 0; i < nq; i++)
        x[i] = x[i] * g;

    for ( ; i < ne; i++)
        x[i] = 0;

    return g;
}


/* ----------------------------------------------------------------------------
 *  Spectrum coding
 * -------------------------------------------------------------------------- */

/**
 * Resolve High-bitrate mode according size of the frame
 * sr, nbytes      Samplerate and size of the frame
 * return          True when High-Rate mode enabled
 */
static int resolve_high_rate(enum lc3_srate sr, int nbytes)
{
    return nbytes > 20 * (1 + (int)sr);
}

/**
 * Bit consumption
 * dt, sr, nbytes  Duration, samplerate and size of the frame
 * x               Spectral quantized coefficients
 * n               Count of significant coefficients, updated on truncation
 * nbits_budget    Truncate to stay in budget, when not zero
 * p_lsb_mode      Return True when LSB's are not AC coded, or NULL
 * return          The number of bits coding the spectrum
 *
 * The spectral coefficients `x` storage is :
 *   b0       0:positive or zero  1:negative
 *   b15..b1  Absolute value
 */
LC3_HOT static int compute_nbits(
    enum lc3_dt dt, enum lc3_srate sr, int nbytes,
    const uint16_t *x, int *n, int nbits_budget, bool *p_lsb_mode)
{
    int ne = LC3_NE(dt, sr);

    /* --- Mode and rate --- */

    bool lsb_mode  = nbytes >= 20 * (3 + (int)sr);
    bool high_rate = resolve_high_rate(sr, nbytes);

    /* --- Loop on quantized coefficients --- */

    int nbits = 0, nbits_lsb = 0;
    uint8_t state = 0;

    int nbits_end = 0;
    int n_end = 0;

    nbits_budget = nbits_budget ? nbits_budget * 2048 : INT_MAX;

    for (int i = 0, h = 0; h < 2; h++) {
        const uint8_t (*lut_coeff)[4] = lc3_spectrum_lookup[high_rate][h];

        for ( ; i < LC3_MIN(*n, (ne + 2) >> (1 - h))
                && nbits <= nbits_budget; i += 2) {

            const uint8_t *lut = lut_coeff[state];
            uint16_t a = x[i] >> 1, b = x[i+1] >> 1;

            /* --- Sign values --- */

            int s = (a > 0) + (b > 0);
            nbits += s * 2048;

            /* --- LSB values Reduce to 2*2 bits MSB values ---
             * Reduce to 2x2 bits MSB values. The LSB's pair are arithmetic
             * coded with an escape code followed by 1 bit for each values.
             * The LSB mode does not arthmetic code the first LSB,
             * add the sign of the LSB when one of pair was at value 1 */

            int k = 0;
            int m = (a | b) >> 2;

            if (m) {

                if (lsb_mode) {
                    nbits += lc3_spectrum_bits[lut[k++]][16] - 2*2048;
                    nbits_lsb += 2 + (a == 1) + (b == 1);
                }

                for (m >>= lsb_mode; m; m >>= 1, k++)
                    nbits += lc3_spectrum_bits[lut[LC3_MIN(k, 3)]][16];

                nbits += k * 2*2048;
                a >>= k;
                b >>= k;

                k = LC3_MIN(k, 3);
            }

            /* --- MSB values --- */

            nbits += lc3_spectrum_bits[lut[k]][a + 4*b];

            /* --- Update state --- */

            if (s && nbits <= nbits_budget) {
                n_end = i + 2;
                nbits_end = nbits;
            }

            state = (state << 4) + (k > 1 ? 12 + k : 1 + (a + b) * (k + 1));
        }
    }

    /* --- Return --- */

    *n = n_end;

    if (p_lsb_mode)
        *p_lsb_mode = lsb_mode &&
            nbits_end + nbits_lsb * 2048 > nbits_budget;

    if (nbits_budget >= INT_MAX)
        nbits_end += nbits_lsb * 2048;

    return (nbits_end + 2047) / 2048;
}

/**
 * Put quantized spectrum
 * bits            Bitstream context
 * dt, sr, nbytes  Duration, samplerate and size of the frame
 * x               Spectral quantized
 * nq, lsb_mode    Count of significants, and LSB discard indication
 *
 * The spectral coefficients `x` storage is :
 *   b0       0:positive or zero  1:negative
 *   b15..b1  Absolute value
 */
LC3_HOT static void put_quantized(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_srate sr, int nbytes,
    const uint16_t *x, int nq, bool lsb_mode)
{
    int ne = LC3_NE(dt, sr);
    bool high_rate = resolve_high_rate(sr, nbytes);

    /* --- Loop on quantized coefficients --- */

    uint8_t state = 0;

    for (int i = 0, h = 0; h < 2; h++) {
        const uint8_t (*lut_coeff)[4] = lc3_spectrum_lookup[high_rate][h];

        for ( ; i < LC3_MIN(nq, (ne + 2) >> (1 - h)); i += 2) {

            const uint8_t *lut = lut_coeff[state];
            uint16_t a = x[i] >> 1, b = x[i+1] >> 1;

            /* --- LSB values Reduce to 2*2 bits MSB values ---
             * Reduce to 2x2 bits MSB values. The LSB's pair are arithmetic
             * coded with an escape code and 1 bits for each values.
             * The LSB mode discard the first LSB (at this step) */

            int m = (a | b) >> 2;
            int k = 0, shr = 0;

            if (m) {

                if (lsb_mode)
                    lc3_put_symbol(bits,
                        lc3_spectrum_models + lut[k++], 16);

                for (m >>= lsb_mode; m; m >>= 1, k++) {
                    lc3_put_bit(bits, (a >> k) & 1);
                    lc3_put_bit(bits, (b >> k) & 1);
                    lc3_put_symbol(bits,
                        lc3_spectrum_models + lut[LC3_MIN(k, 3)], 16);
                }

                a >>= lsb_mode;
                b >>= lsb_mode;

                shr = k - lsb_mode;
                k = LC3_MIN(k, 3);
            }

            /* --- Sign values --- */

            if (a) lc3_put_bit(bits, x[i+0] & 1);
            if (b) lc3_put_bit(bits, x[i+1] & 1);

            /* --- MSB values --- */

            a >>= shr;
            b >>= shr;

            lc3_put_symbol(bits, lc3_spectrum_models + lut[k], a + 4*b);

            /* --- Update state --- */

            state = (state << 4) + (k > 1 ? 12 + k : 1 + (a + b) * (k + 1));
        }
    }
}

/**
 * Get quantized spectrum
 * bits            Bitstream context
 * dt, sr, nbytes  Duration, samplerate and size of the frame
 * nq, lsb_mode    Count of significants, and LSB discard indication
 * xq              Return `nq` spectral quantized coefficients
 * nf_seed         Return the noise factor seed associated
 * return          0: Ok  -1: Invalid bitstream data
 */
LC3_HOT static int get_quantized(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_srate sr, int nbytes,
    int nq, bool lsb_mode, float *xq, uint16_t *nf_seed)
{
    int ne = LC3_NE(dt, sr);
    bool high_rate = resolve_high_rate(sr, nbytes);

     *nf_seed = 0;

    /* --- Loop on quantized coefficients --- */

    uint8_t state = 0;

    for (int i = 0, h = 0; h < 2; h++) {
        const uint8_t (*lut_coeff)[4] = lc3_spectrum_lookup[high_rate][h];

        for ( ; i < LC3_MIN(nq, (ne + 2) >> (1 - h)); i += 2) {

            const uint8_t *lut = lut_coeff[state];

            /* --- LSB values ---
             * Until the symbol read indicates the escape value 16,
             * read an LSB bit for each values.
             * The LSB mode discard the first LSB (at this step) */

            int u = 0, v = 0;
            int k = 0, shl = 0;

            unsigned s = lc3_get_symbol(bits, lc3_spectrum_models + lut[k]);

            if (lsb_mode && s >= 16) {
                s = lc3_get_symbol(bits, lc3_spectrum_models + lut[++k]);
                shl++;
            }

            for ( ; s >= 16 && shl < 14; shl++) {
                u |= lc3_get_bit(bits) << shl;
                v |= lc3_get_bit(bits) << shl;

                k += (k < 3);
                s  = lc3_get_symbol(bits, lc3_spectrum_models + lut[k]);
            }

            if (s >= 16)
                return -1;

            /* --- MSB & sign values --- */

            int a = s % 4;
            int b = s / 4;

            u |= a << shl;
            v |= b << shl;

            xq[i  ] = u && lc3_get_bit(bits) ? -u : u;
            xq[i+1] = v && lc3_get_bit(bits) ? -v : v;

            *nf_seed = (*nf_seed + u * i + v * (i+1)) & 0xffff;

            /* --- Update state --- */

            state = (state << 4) + (k > 1 ? 12 + k : 1 + (a + b) * (k + 1));
        }
    }

    return 0;
}

/**
 * Put residual bits of quantization
 * bits            Bitstream context
 * nbits           Maximum number of bits to output
 * x, n            Spectral quantized, and count of significants
 * xf              Scaled spectral coefficients
 *
 * The spectral coefficients `x` storage is :
 *   b0       0:positive or zero  1:negative
 *   b15..b1  Absolute value
 */
LC3_HOT static void put_residual(
    lc3_bits_t *bits, int nbits, const uint16_t *x, int n, const float *xf)
{
    for (int i = 0; i < n && nbits > 0; i++) {

        if (x[i] == 0)
            continue;

        float xq = x[i] & 1 ? -(x[i] >> 1) : (x[i] >> 1);

        lc3_put_bit(bits, xf[i] >= xq);
        nbits--;
    }
}

/**
 * Get residual bits of quantization
 * bits            Bitstream context
 * nbits           Maximum number of bits to output
 * x, nq           Spectral quantized, and count of significants
 */
LC3_HOT static void get_residual(
    lc3_bits_t *bits, int nbits, float *x, int nq)
{
    for (int i = 0; i < nq && nbits > 0; i++) {

        if (x[i] == 0)
            continue;

        if (lc3_get_bit(bits) == 0)
            x[i] -= x[i] < 0 ? 5.f/16 : 3.f/16;
        else
            x[i] += x[i] > 0 ? 5.f/16 : 3.f/16;

        nbits--;
    }
}

/**
 * Put LSB values of quantized spectrum values
 * bits            Bitstream context
 * nbits           Maximum number of bits to output
 * x, n            Spectral quantized, and count of significants
 *
 * The spectral coefficients `x` storage is :
 *   b0       0:positive or zero  1:negative
 *   b15..b1  Absolute value
 */
LC3_HOT static void put_lsb(
    lc3_bits_t *bits, int nbits, const uint16_t *x, int n)
{
    for (int i = 0; i < n && nbits > 0; i += 2) {
        uint16_t a = x[i] >> 1, b = x[i+1] >> 1;
        int a_neg = x[i] & 1, b_neg = x[i+1] & 1;

        if ((a | b) >> 2 == 0)
            continue;

        if (nbits-- > 0)
            lc3_put_bit(bits, a & 1);

        if (a == 1 && nbits-- > 0)
            lc3_put_bit(bits, a_neg);

        if (nbits-- > 0)
            lc3_put_bit(bits, b & 1);

        if (b == 1 && nbits-- > 0)
            lc3_put_bit(bits, b_neg);
    }
}

/**
 * Get LSB values of quantized spectrum values
 * bits            Bitstream context
 * nbits           Maximum number of bits to output
 * x, nq           Spectral quantized, and count of significants
 * nf_seed         Update the noise factor seed according
 */
LC3_HOT static void get_lsb(lc3_bits_t *bits,
    int nbits, float *x, int nq, uint16_t *nf_seed)
{
    for (int i = 0; i < nq && nbits > 0; i += 2) {

        float a = fabsf(x[i]), b = fabsf(x[i+1]);

        if (fmaxf(a, b) < 4)
            continue;

        if (nbits-- > 0 && lc3_get_bit(bits)) {
            if (a) {
                x[i] += x[i] < 0 ? -1 : 1;
                *nf_seed = (*nf_seed + i) & 0xffff;
            } else if (nbits-- > 0) {
                x[i] = lc3_get_bit(bits) ? -1 : 1;
                *nf_seed = (*nf_seed + i) & 0xffff;
            }
        }

        if (nbits-- > 0 && lc3_get_bit(bits)) {
            if (b) {
                x[i+1] += x[i+1] < 0 ? -1 : 1;
                *nf_seed = (*nf_seed + i+1) & 0xffff;
            } else if (nbits-- > 0) {
                x[i+1] = lc3_get_bit(bits) ? -1 : 1;
                *nf_seed = (*nf_seed + i+1) & 0xffff;
            }
        }
    }
}


/* ----------------------------------------------------------------------------
 *  Noise coding
 * -------------------------------------------------------------------------- */

/**
 * Estimate noise level
 * dt, bw          Duration and bandwidth of the frame
 * xq, nq          Quantized spectral coefficients
 * x               Quantization scaled spectrum coefficients
 * return          Noise factor (0 to 7)
 *
 * The spectral coefficients `x` storage is :
 *   b0       0:positive or zero  1:negative
 *   b15..b1  Absolute value
 */
LC3_HOT static int estimate_noise(enum lc3_dt dt, enum lc3_bandwidth bw,
    const uint16_t *xq, int nq, const float *x)
{
    int bw_stop = (dt == LC3_DT_7M5 ? 60 : 80) * (1 + bw);
    int w = 2 + dt;

    float sum = 0;
    int i, n = 0, z = 0;

    for (i = 6*(3 + dt) - w; i < LC3_MIN(nq, bw_stop); i++) {
        z = xq[i] ? 0 : z + 1;
        if (z > 2*w)
            sum += fabsf(x[i - w]), n++;
    }

    for ( ; i < bw_stop + w; i++)
        if (++z > 2*w)
            sum += fabsf(x[i - w]), n++;

    int nf = n ? 8 - (int)((16 * sum) / n + 0.5f) : 0;

    return LC3_CLIP(nf, 0, 7);
}

/**
 * Noise filling
 * dt, bw          Duration and bandwidth of the frame
 * nf, nf_seed     The noise factor and pseudo-random seed
 * g               Quantization gain
 * x, nq           Spectral quantized, and count of significants
 */
LC3_HOT static void fill_noise(enum lc3_dt dt, enum lc3_bandwidth bw,
    int nf, uint16_t nf_seed, float g, float *x, int nq)
{
    int bw_stop = (dt == LC3_DT_7M5 ? 60 : 80) * (1 + bw);
    int w = 2 + dt;

    float s = g * (float)(8 - nf) / 16;
    int i, z = 0;

    for (i = 6*(3 + dt) - w; i < LC3_MIN(nq, bw_stop); i++) {
        z = x[i] ? 0 : z + 1;
        if (z > 2*w) {
            nf_seed = (13849 + nf_seed*31821) & 0xffff;
            x[i - w] = nf_seed & 0x8000 ? -s : s;
        }
    }

    for ( ; i < bw_stop + w; i++)
        if (++z > 2*w) {
            nf_seed = (13849 + nf_seed*31821) & 0xffff;
            x[i - w] = nf_seed & 0x8000 ? -s : s;
        }
}

/**
 * Put noise factor
 * bits            Bitstream context
 * nf              Noise factor (0 to 7)
 */
static void put_noise_factor(lc3_bits_t *bits, int nf)
{
    lc3_put_bits(bits, nf, 3);
}

/**
 * Get noise factor
 * bits            Bitstream context
 * return          Noise factor (0 to 7)
 */
static int get_noise_factor(lc3_bits_t *bits)
{
    return lc3_get_bits(bits, 3);
}


/* ----------------------------------------------------------------------------
 *  Encoding
 * -------------------------------------------------------------------------- */

/**
 * Bit consumption of the number of coded coefficients
 * dt, sr          Duration, samplerate of the frame
 * return          Bit consumpution of the number of coded coefficients
 */
static int get_nbits_nq(enum lc3_dt dt, enum lc3_srate sr)
{
    int ne = LC3_NE(dt, sr);
    return 4 + (ne > 32) + (ne > 64) + (ne > 128) + (ne > 256);
}

/**
 * Bit consumption of the arithmetic coder
 * dt, sr, nbytes  Duration, samplerate and size of the frame
 * return          Bit consumption of bitstream data
 */
static int get_nbits_ac(enum lc3_dt dt, enum lc3_srate sr, int nbytes)
{
    return get_nbits_nq(dt, sr) + 3 + LC3_MIN((nbytes-1) / 160, 2);
}

/**
 * Spectrum analysis
 */
void lc3_spec_analyze(enum lc3_dt dt, enum lc3_srate sr,
    int nbytes, bool pitch, const lc3_tns_data_t *tns,
    struct lc3_spec_analysis *spec, float *x,
    uint16_t *xq, struct lc3_spec_side *side)
{
    bool reset_off;

    /* --- Bit budget --- */

    const int nbits_gain = 8;
    const int nbits_nf = 3;

    int nbits_budget = 8*nbytes - get_nbits_ac(dt, sr, nbytes) -
        lc3_bwdet_get_nbits(sr) - lc3_ltpf_get_nbits(pitch) -
        lc3_sns_get_nbits() - lc3_tns_get_nbits(tns) - nbits_gain - nbits_nf;

    /* --- Global gain --- */

    float nbits_off = spec->nbits_off + spec->nbits_spare;
    nbits_off = fminf(fmaxf(nbits_off, -40), 40);
    nbits_off = 0.8f * spec->nbits_off + 0.2f * nbits_off;

    int g_off = resolve_gain_offset(sr, nbytes);

    int g_min, g_int = estimate_gain(dt, sr,
        x, nbits_budget, nbits_off, g_off, &reset_off, &g_min);

    /* --- Quantization --- */

    quantize(dt, sr, g_int, x, xq, &side->nq);

    int nbits = compute_nbits(dt, sr, nbytes, xq, &side->nq, 0, NULL);

    spec->nbits_off = reset_off ? 0 : nbits_off;
    spec->nbits_spare = reset_off ? 0 : nbits_budget - nbits;

    /* --- Adjust gain and requantize --- */

    int g_adj = adjust_gain(sr, g_off + g_int,
        nbits, nbits_budget, g_off + g_min);

    if (g_adj)
        quantize(dt, sr, g_adj, x, xq, &side->nq);

    side->g_idx = g_int + g_adj + g_off;
    nbits = compute_nbits(dt, sr, nbytes,
        xq, &side->nq, nbits_budget, &side->lsb_mode);
}

/**
 * Put spectral quantization side data
 */
void lc3_spec_put_side(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_srate sr, const struct lc3_spec_side *side)
{
    int nbits_nq = get_nbits_nq(dt, sr);

    lc3_put_bits(bits, LC3_MAX(side->nq >> 1, 1) - 1, nbits_nq);
    lc3_put_bits(bits, side->lsb_mode, 1);
    lc3_put_bits(bits, side->g_idx, 8);
}

/**
 * Encode spectral coefficients
 */
void lc3_spec_encode(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_srate sr, enum lc3_bandwidth bw, int nbytes,
    const uint16_t *xq, const lc3_spec_side_t *side, const float *x)
{
    bool lsb_mode = side->lsb_mode;
    int nq = side->nq;

    put_noise_factor(bits, estimate_noise(dt, bw, xq, nq, x));

    put_quantized(bits, dt, sr, nbytes, xq, nq, lsb_mode);

    int nbits_left = lc3_get_bits_left(bits);

    if (lsb_mode)
        put_lsb(bits, nbits_left, xq, nq);
    else
        put_residual(bits, nbits_left, xq, nq, x);
}


/* ----------------------------------------------------------------------------
 *  Decoding
 * -------------------------------------------------------------------------- */

/**
 * Get spectral quantization side data
 */
int lc3_spec_get_side(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_srate sr, struct lc3_spec_side *side)
{
    int nbits_nq = get_nbits_nq(dt, sr);
    int ne = LC3_NE(dt, sr);

    side->nq = (lc3_get_bits(bits, nbits_nq) + 1) << 1;
    side->lsb_mode = lc3_get_bit(bits);
    side->g_idx = lc3_get_bits(bits, 8);

    return side->nq > ne ? (side->nq = ne), -1 : 0;
}

/**
 * Decode spectral coefficients
 */
int lc3_spec_decode(lc3_bits_t *bits,
    enum lc3_dt dt, enum lc3_srate sr, enum lc3_bandwidth bw,
    int nbytes, const lc3_spec_side_t *side, float *x)
{
    bool lsb_mode = side->lsb_mode;
    int nq = side->nq;
    int ret = 0;

    int nf = get_noise_factor(bits);
    uint16_t nf_seed;

    if ((ret = get_quantized(bits, dt, sr, nbytes,
                    nq, lsb_mode, x, &nf_seed)) < 0)
        return ret;

    int nbits_left = lc3_get_bits_left(bits);

    if (lsb_mode)
        get_lsb(bits, nbits_left, x, nq, &nf_seed);
    else
        get_residual(bits, nbits_left, x, nq);

    int g_int = side->g_idx - resolve_gain_offset(sr, nbytes);
    float g = unquantize(dt, sr, g_int, x, nq);

    if (nq > 2 || x[0] || x[1] || side->g_idx > 0 || nf < 7)
        fill_noise(dt, bw, nf, nf_seed, g, x, nq);

    return 0;
}
