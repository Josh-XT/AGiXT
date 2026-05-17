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
 * FFT 5 Points
 * The number of interleaved transform `n` assumed to be even
 */
#ifndef fft_5

LC3_HOT static inline void neon_fft_5(
    const struct lc3_complex *x, struct lc3_complex *y, int n)
{
    static const union { float f[2]; uint64_t u64; }
        __cos1 = { {  0.3090169944,  0.3090169944 } },
        __cos2 = { { -0.8090169944, -0.8090169944 } },
        __sin1 = { {  0.9510565163, -0.9510565163 } },
        __sin2 = { {  0.5877852523, -0.5877852523 } };

    float32x2_t sin1 = vcreate_f32(__sin1.u64);
    float32x2_t sin2 = vcreate_f32(__sin2.u64);
    float32x2_t cos1 = vcreate_f32(__cos1.u64);
    float32x2_t cos2 = vcreate_f32(__cos2.u64);

    float32x4_t sin1q = vcombine_f32(sin1, sin1);
    float32x4_t sin2q = vcombine_f32(sin2, sin2);
    float32x4_t cos1q = vcombine_f32(cos1, cos1);
    float32x4_t cos2q = vcombine_f32(cos2, cos2);

    for (int i = 0; i < n; i += 2, x += 2, y += 10) {

        float32x4_t y0, y1, y2, y3, y4;

        float32x4_t x0 = vld1q_f32( (float *)(x + 0*n) );
        float32x4_t x1 = vld1q_f32( (float *)(x + 1*n) );
        float32x4_t x2 = vld1q_f32( (float *)(x + 2*n) );
        float32x4_t x3 = vld1q_f32( (float *)(x + 3*n) );
        float32x4_t x4 = vld1q_f32( (float *)(x + 4*n) );

        float32x4_t s14 = vaddq_f32(x1, x4);
        float32x4_t s23 = vaddq_f32(x2, x3);

        float32x4_t d14 = vrev64q_f32( vsubq_f32(x1, x4) );
        float32x4_t d23 = vrev64q_f32( vsubq_f32(x2, x3) );

        y0 = vaddq_f32( x0, vaddq_f32(s14, s23) );

        y4 = vfmaq_f32( x0, s14, cos1q );
        y4 = vfmaq_f32( y4, s23, cos2q );

        y1 = vfmaq_f32( y4, d14, sin1q );
        y1 = vfmaq_f32( y1, d23, sin2q );

        y4 = vfmsq_f32( y4, d14, sin1q );
        y4 = vfmsq_f32( y4, d23, sin2q );

        y3 = vfmaq_f32( x0, s14, cos2q );
        y3 = vfmaq_f32( y3, s23, cos1q );

        y2 = vfmaq_f32( y3, d14, sin2q );
        y2 = vfmsq_f32( y2, d23, sin1q );

        y3 = vfmsq_f32( y3, d14, sin2q );
        y3 = vfmaq_f32( y3, d23, sin1q );

        vst1_f32( (float *)(y + 0), vget_low_f32(y0) );
        vst1_f32( (float *)(y + 1), vget_low_f32(y1) );
        vst1_f32( (float *)(y + 2), vget_low_f32(y2) );
        vst1_f32( (float *)(y + 3), vget_low_f32(y3) );
        vst1_f32( (float *)(y + 4), vget_low_f32(y4) );

        vst1_f32( (float *)(y + 5), vget_high_f32(y0) );
        vst1_f32( (float *)(y + 6), vget_high_f32(y1) );
        vst1_f32( (float *)(y + 7), vget_high_f32(y2) );
        vst1_f32( (float *)(y + 8), vget_high_f32(y3) );
        vst1_f32( (float *)(y + 9), vget_high_f32(y4) );
    }
}

#ifndef TEST_NEON
#define fft_5 neon_fft_5
#endif

#endif /* fft_5 */

/**
 * FFT Butterfly 3 Points
 */
#ifndef fft_bf3

LC3_HOT static inline void neon_fft_bf3(
    const struct lc3_fft_bf3_twiddles *twiddles,
    const struct lc3_complex *x, struct lc3_complex *y, int n)
{
    int n3 = twiddles->n3;
    const struct lc3_complex (*w0_ptr)[2] = twiddles->t;
    const struct lc3_complex (*w1_ptr)[2] = w0_ptr + n3;
    const struct lc3_complex (*w2_ptr)[2] = w1_ptr + n3;

    const struct lc3_complex *x0_ptr = x;
    const struct lc3_complex *x1_ptr = x0_ptr + n*n3;
    const struct lc3_complex *x2_ptr = x1_ptr + n*n3;

    struct lc3_complex *y0_ptr = y;
    struct lc3_complex *y1_ptr = y0_ptr + n3;
    struct lc3_complex *y2_ptr = y1_ptr + n3;

    for (int j, i = 0; i < n; i++,
            y0_ptr += 3*n3, y1_ptr += 3*n3, y2_ptr += 3*n3) {

        /* --- Process by pair --- */

        for (j = 0; j < (n3 >> 1); j++,
                x0_ptr += 2, x1_ptr += 2, x2_ptr += 2) {

            float32x4_t x0 = vld1q_f32( (float *)x0_ptr );
            float32x4_t x1 = vld1q_f32( (float *)x1_ptr );
            float32x4_t x2 = vld1q_f32( (float *)x2_ptr );

            float32x4_t x1r = vtrn1q_f32( vrev64q_f32(vnegq_f32(x1)), x1 );
            float32x4_t x2r = vtrn1q_f32( vrev64q_f32(vnegq_f32(x2)), x2 );

            float32x4x2_t wn;
            float32x4_t yn;

            wn = vld2q_f32( (float *)(w0_ptr + 2*j) );

            yn = vfmaq_f32( x0, x1 , vtrn1q_f32(wn.val[0], wn.val[0]) );
            yn = vfmaq_f32( yn, x1r, vtrn1q_f32(wn.val[1], wn.val[1]) );
            yn = vfmaq_f32( yn, x2 , vtrn2q_f32(wn.val[0], wn.val[0]) );
            yn = vfmaq_f32( yn, x2r, vtrn2q_f32(wn.val[1], wn.val[1]) );
            vst1q_f32( (float *)(y0_ptr + 2*j), yn );

            wn = vld2q_f32( (float *)(w1_ptr + 2*j) );

            yn = vfmaq_f32( x0, x1 , vtrn1q_f32(wn.val[0], wn.val[0]) );
            yn = vfmaq_f32( yn, x1r, vtrn1q_f32(wn.val[1], wn.val[1]) );
            yn = vfmaq_f32( yn, x2 , vtrn2q_f32(wn.val[0], wn.val[0]) );
            yn = vfmaq_f32( yn, x2r, vtrn2q_f32(wn.val[1], wn.val[1]) );
            vst1q_f32( (float *)(y1_ptr + 2*j), yn );

            wn = vld2q_f32( (float *)(w2_ptr + 2*j) );

            yn = vfmaq_f32( x0, x1 , vtrn1q_f32(wn.val[0], wn.val[0]) );
            yn = vfmaq_f32( yn, x1r, vtrn1q_f32(wn.val[1], wn.val[1]) );
            yn = vfmaq_f32( yn, x2 , vtrn2q_f32(wn.val[0], wn.val[0]) );
            yn = vfmaq_f32( yn, x2r, vtrn2q_f32(wn.val[1], wn.val[1]) );
            vst1q_f32( (float *)(y2_ptr + 2*j), yn );

        }

        /* --- Last iteration --- */

        if (n3 & 1) {

            float32x2x2_t wn;
            float32x2_t yn;

            float32x2_t x0 = vld1_f32( (float *)(x0_ptr++) );
            float32x2_t x1 = vld1_f32( (float *)(x1_ptr++) );
            float32x2_t x2 = vld1_f32( (float *)(x2_ptr++) );

            float32x2_t x1r = vtrn1_f32( vrev64_f32(vneg_f32(x1)), x1 );
            float32x2_t x2r = vtrn1_f32( vrev64_f32(vneg_f32(x2)), x2 );

            wn = vld2_f32( (float *)(w0_ptr + 2*j) );

            yn = vfma_f32( x0, x1 , vtrn1_f32(wn.val[0], wn.val[0]) );
            yn = vfma_f32( yn, x1r, vtrn1_f32(wn.val[1], wn.val[1]) );
            yn = vfma_f32( yn, x2 , vtrn2_f32(wn.val[0], wn.val[0]) );
            yn = vfma_f32( yn, x2r, vtrn2_f32(wn.val[1], wn.val[1]) );
            vst1_f32( (float *)(y0_ptr + 2*j), yn );

            wn = vld2_f32( (float *)(w1_ptr + 2*j) );

            yn = vfma_f32( x0, x1 , vtrn1_f32(wn.val[0], wn.val[0]) );
            yn = vfma_f32( yn, x1r, vtrn1_f32(wn.val[1], wn.val[1]) );
            yn = vfma_f32( yn, x2 , vtrn2_f32(wn.val[0], wn.val[0]) );
            yn = vfma_f32( yn, x2r, vtrn2_f32(wn.val[1], wn.val[1]) );
            vst1_f32( (float *)(y1_ptr + 2*j), yn );

            wn = vld2_f32( (float *)(w2_ptr + 2*j) );

            yn = vfma_f32( x0, x1 , vtrn1_f32(wn.val[0], wn.val[0]) );
            yn = vfma_f32( yn, x1r, vtrn1_f32(wn.val[1], wn.val[1]) );
            yn = vfma_f32( yn, x2 , vtrn2_f32(wn.val[0], wn.val[0]) );
            yn = vfma_f32( yn, x2r, vtrn2_f32(wn.val[1], wn.val[1]) );
            vst1_f32( (float *)(y2_ptr + 2*j), yn );
        }

    }
}

#ifndef TEST_NEON
#define fft_bf3 neon_fft_bf3
#endif

#endif /* fft_bf3 */

/**
 * FFT Butterfly 2 Points
 */
#ifndef fft_bf2

LC3_HOT static inline void neon_fft_bf2(
    const struct lc3_fft_bf2_twiddles *twiddles,
    const struct lc3_complex *x, struct lc3_complex *y, int n)
{
    int n2 = twiddles->n2;
    const struct lc3_complex *w_ptr = twiddles->t;

    const struct lc3_complex *x0_ptr = x;
    const struct lc3_complex *x1_ptr = x0_ptr + n*n2;

    struct lc3_complex *y0_ptr = y;
    struct lc3_complex *y1_ptr = y0_ptr + n2;

    for (int j, i = 0; i < n; i++, y0_ptr += 2*n2, y1_ptr += 2*n2) {

        /* --- Process by pair --- */

        for (j = 0; j < (n2 >> 1); j++, x0_ptr += 2, x1_ptr += 2) {

            float32x4_t x0 = vld1q_f32( (float *)x0_ptr );
            float32x4_t x1 = vld1q_f32( (float *)x1_ptr );
            float32x4_t y0, y1;

            float32x4_t x1r = vtrn1q_f32( vrev64q_f32(vnegq_f32(x1)), x1 );

            float32x4_t w = vld1q_f32( (float *)(w_ptr + 2*j) );
            float32x4_t w_re = vtrn1q_f32(w, w);
            float32x4_t w_im = vtrn2q_f32(w, w);

            y0 = vfmaq_f32( x0, x1 , w_re );
            y0 = vfmaq_f32( y0, x1r, w_im );
            vst1q_f32( (float *)(y0_ptr + 2*j), y0 );

            y1 = vfmsq_f32( x0, x1 , w_re );
            y1 = vfmsq_f32( y1, x1r, w_im );
            vst1q_f32( (float *)(y1_ptr + 2*j), y1 );
        }

        /* --- Last iteration --- */

        if (n2 & 1) {

            float32x2_t x0 = vld1_f32( (float *)(x0_ptr++) );
            float32x2_t x1 = vld1_f32( (float *)(x1_ptr++) );
            float32x2_t y0, y1;

            float32x2_t x1r = vtrn1_f32( vrev64_f32(vneg_f32(x1)), x1 );

            float32x2_t w = vld1_f32( (float *)(w_ptr + 2*j) );
            float32x2_t w_re = vtrn1_f32(w, w);
            float32x2_t w_im = vtrn2_f32(w, w);

            y0 = vfma_f32( x0, x1 , w_re );
            y0 = vfma_f32( y0, x1r, w_im );
            vst1_f32( (float *)(y0_ptr + 2*j), y0 );

            y1 = vfms_f32( x0, x1 , w_re );
            y1 = vfms_f32( y1, x1r, w_im );
            vst1_f32( (float *)(y1_ptr + 2*j), y1 );
        }
    }
}

#ifndef TEST_NEON
#define fft_bf2 neon_fft_bf2
#endif

#endif /* fft_bf2 */

#endif /* __ARM_NEON && __ARM_ARCH_ISA_A64 */
