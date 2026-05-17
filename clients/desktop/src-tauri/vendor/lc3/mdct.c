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

#include "mdct.h"
#include "tables.h"

#include "mdct_neon.h"


/* ----------------------------------------------------------------------------
 *  FFT processing
 * -------------------------------------------------------------------------- */

/**
 * FFT 5 Points
 * x, y            Input and output coefficients, of size 5xn
 * n               Number of interleaved transform to perform (n % 2 = 0)
 */
#ifndef fft_5
LC3_HOT static inline void fft_5(
    const struct lc3_complex *x, struct lc3_complex *y, int n)
{
    static const float cos1 =  0.3090169944;  /* cos(-2Pi 1/5) */
    static const float cos2 = -0.8090169944;  /* cos(-2Pi 2/5) */

    static const float sin1 = -0.9510565163;  /* sin(-2Pi 1/5) */
    static const float sin2 = -0.5877852523;  /* sin(-2Pi 2/5) */

    for (int i = 0; i < n; i++, x++, y+= 5) {

        struct lc3_complex s14 =
            { x[1*n].re + x[4*n].re, x[1*n].im + x[4*n].im };
        struct lc3_complex d14 =
            { x[1*n].re - x[4*n].re, x[1*n].im - x[4*n].im };

        struct lc3_complex s23 =
            { x[2*n].re + x[3*n].re, x[2*n].im + x[3*n].im };
        struct lc3_complex d23 =
            { x[2*n].re - x[3*n].re, x[2*n].im - x[3*n].im };

        y[0].re = x[0].re + s14.re + s23.re;

        y[0].im = x[0].im + s14.im + s23.im;

        y[1].re = x[0].re + s14.re * cos1 - d14.im * sin1
                          + s23.re * cos2 - d23.im * sin2;

        y[1].im = x[0].im + s14.im * cos1 + d14.re * sin1
                          + s23.im * cos2 + d23.re * sin2;

        y[2].re = x[0].re + s14.re * cos2 - d14.im * sin2
                          + s23.re * cos1 + d23.im * sin1;

        y[2].im = x[0].im + s14.im * cos2 + d14.re * sin2
                          + s23.im * cos1 - d23.re * sin1;

        y[3].re = x[0].re + s14.re * cos2 + d14.im * sin2
                          + s23.re * cos1 - d23.im * sin1;

        y[3].im = x[0].im + s14.im * cos2 - d14.re * sin2
                          + s23.im * cos1 + d23.re * sin1;

        y[4].re = x[0].re + s14.re * cos1 + d14.im * sin1
                          + s23.re * cos2 + d23.im * sin2;

        y[4].im = x[0].im + s14.im * cos1 - d14.re * sin1
                          + s23.im * cos2 - d23.re * sin2;
    }
}
#endif /* fft_5 */

/**
 * FFT Butterfly 3 Points
 * x, y            Input and output coefficients
 * twiddles        Twiddles factors, determine size of transform
 * n               Number of interleaved transforms
 */
#ifndef fft_bf3
LC3_HOT static inline void fft_bf3(
    const struct lc3_fft_bf3_twiddles *twiddles,
    const struct lc3_complex *x, struct lc3_complex *y, int n)
{
    int n3 = twiddles->n3;
    const struct lc3_complex (*w0)[2] = twiddles->t;
    const struct lc3_complex (*w1)[2] = w0 + n3, (*w2)[2] = w1 + n3;

    const struct lc3_complex *x0 = x, *x1 = x0 + n*n3, *x2 = x1 + n*n3;
    struct lc3_complex *y0 = y, *y1 = y0 + n3, *y2 = y1 + n3;

    for (int i = 0; i < n; i++, y0 += 3*n3, y1 += 3*n3, y2 += 3*n3)
        for (int j = 0; j < n3; j++, x0++, x1++, x2++) {

            y0[j].re = x0->re + x1->re * w0[j][0].re - x1->im * w0[j][0].im
                              + x2->re * w0[j][1].re - x2->im * w0[j][1].im;

            y0[j].im = x0->im + x1->im * w0[j][0].re + x1->re * w0[j][0].im
                              + x2->im * w0[j][1].re + x2->re * w0[j][1].im;

            y1[j].re = x0->re + x1->re * w1[j][0].re - x1->im * w1[j][0].im
                              + x2->re * w1[j][1].re - x2->im * w1[j][1].im;

            y1[j].im = x0->im + x1->im * w1[j][0].re + x1->re * w1[j][0].im
                              + x2->im * w1[j][1].re + x2->re * w1[j][1].im;

            y2[j].re = x0->re + x1->re * w2[j][0].re - x1->im * w2[j][0].im
                              + x2->re * w2[j][1].re - x2->im * w2[j][1].im;

            y2[j].im = x0->im + x1->im * w2[j][0].re + x1->re * w2[j][0].im
                              + x2->im * w2[j][1].re + x2->re * w2[j][1].im;
        }
}
#endif /* fft_bf3 */

/**
 * FFT Butterfly 2 Points
 * twiddles        Twiddles factors, determine size of transform
 * x, y            Input and output coefficients
 * n               Number of interleaved transforms
 */
#ifndef fft_bf2
LC3_HOT static inline void fft_bf2(
    const struct lc3_fft_bf2_twiddles *twiddles,
    const struct lc3_complex *x, struct lc3_complex *y, int n)
{
    int n2 = twiddles->n2;
    const struct lc3_complex *w = twiddles->t;

    const struct lc3_complex *x0 = x, *x1 = x0 + n*n2;
    struct lc3_complex *y0 = y, *y1 = y0 + n2;

    for (int i = 0; i < n; i++, y0 += 2*n2, y1 += 2*n2) {

        for (int j = 0; j < n2; j++, x0++, x1++) {

            y0[j].re = x0->re + x1->re * w[j].re - x1->im * w[j].im;
            y0[j].im = x0->im + x1->im * w[j].re + x1->re * w[j].im;

            y1[j].re = x0->re - x1->re * w[j].re + x1->im * w[j].im;
            y1[j].im = x0->im - x1->im * w[j].re - x1->re * w[j].im;
        }
    }
}
#endif /* fft_bf2 */

/**
 * Perform FFT
 * x, y0, y1       Input, and 2 scratch buffers of size `n`
 * n               Number of points 30, 40, 60, 80, 90, 120, 160, 180, 240
 * return          The buffer `y0` or `y1` that hold the result
 *
 * Input `x` can be the same as the `y0` second scratch buffer
 */
static struct lc3_complex *fft(const struct lc3_complex *x, int n,
    struct lc3_complex *y0, struct lc3_complex *y1)
{
    struct lc3_complex *y[2] = { y1, y0 };
    int i2, i3, is = 0;

    /* The number of points `n` can be decomposed as :
     *
     *   n = 5^1 * 3^n3 * 2^n2
     *
     *   for n = 40, 80, 160        n3 = 0, n2 = [3..5]
     *       n = 30, 60, 120, 240   n3 = 1, n2 = [1..4]
     *       n = 90, 180            n3 = 2, n2 = [1..2]
     *
     * Note that the expression `n & (n-1) == 0` is equivalent
     * to the check that `n` is a power of 2. */

    fft_5(x, y[is], n /= 5);

    for (i3 = 0; n & (n-1); i3++, is ^= 1)
        fft_bf3(lc3_fft_twiddles_bf3[i3], y[is], y[is ^ 1], n /= 3);

    for (i2 = 0; n > 1; i2++, is ^= 1)
        fft_bf2(lc3_fft_twiddles_bf2[i2][i3], y[is], y[is ^ 1], n >>= 1);

    return y[is];
}


/* ----------------------------------------------------------------------------
 *  MDCT processing
 * -------------------------------------------------------------------------- */

/**
 * Windowing of samples before MDCT
 * dt, sr          Duration and samplerate (size of the transform)
 * x, y            Input current and delayed samples
 * y, d            Output windowed samples, and delayed ones
 */
LC3_HOT static void mdct_window(enum lc3_dt dt, enum lc3_srate sr,
    const float *x, float *d, float *y)
{
    int ns = LC3_NS(dt, sr), nd = LC3_ND(dt, sr);

    const float *w0 = lc3_mdct_win[dt][sr], *w1 = w0 + ns;
    const float *w2 = w1, *w3 = w2 + nd;

    const float *x0 = x + ns-nd, *x1 = x0;
    float *y0 = y + ns/2, *y1 = y0;
    float *d0 = d, *d1 = d + nd;

    while (x1 > x) {
        *(--y0) = *d0 * *(w0++) - *(--x1) * *(--w1);
        *(y1++) = (*(d0++) = *(x0++)) * *(w2++);

        *(--y0) = *d0 * *(w0++) - *(--x1) * *(--w1);
        *(y1++) = (*(d0++) = *(x0++)) * *(w2++);
    }

    for (x1 += ns; x0 < x1; ) {
        *(--y0) = *d0 * *(w0++) - *(--d1) * *(--w1);
        *(y1++) = (*(d0++) = *(x0++)) * *(w2++) + (*d1 = *(--x1)) * *(--w3);

        *(--y0) = *d0 * *(w0++) - *(--d1) * *(--w1);
        *(y1++) = (*(d0++) = *(x0++)) * *(w2++) + (*d1 = *(--x1)) * *(--w3);
    }
}

/**
 * Pre-rotate MDCT coefficients of N/2 points, before FFT N/4 points FFT
 * def             Size and twiddles factors
 * x, y            Input and output coefficients
 *
 * `x` and y` can be the same buffer
 */
LC3_HOT static void mdct_pre_fft(const struct lc3_mdct_rot_def *def,
    const float *x, struct lc3_complex *y)
{
    int n4 = def->n4;

    const float *x0 = x, *x1 = x0 + 2*n4;
    const struct lc3_complex *w0 = def->w, *w1 = w0 + n4;
    struct lc3_complex *y0 = y, *y1 = y0 + n4;

    while (x0 < x1) {
        struct lc3_complex u, uw = *(w0++);
        u.re = - *(--x1) * uw.re + *x0 * uw.im;
        u.im =   *(x0++) * uw.re + *x1 * uw.im;

        struct lc3_complex v, vw = *(--w1);
        v.re = - *(--x1) * vw.im + *x0 * vw.re;
        v.im = - *(x0++) * vw.im - *x1 * vw.re;

        *(y0++) = u;
        *(--y1) = v;
    }
}

/**
 * Post-rotate FFT N/4 points coefficients, resulting MDCT N points
 * def             Size and twiddles factors
 * x, y            Input and output coefficients
 *
 * `x` and y` can be the same buffer
 */
LC3_HOT static void mdct_post_fft(const struct lc3_mdct_rot_def *def,
    const struct lc3_complex *x, float *y)
{
    int n4 = def->n4, n8 = n4 >> 1;

    const struct lc3_complex *w0 = def->w + n8, *w1 = w0 - 1;
    const struct lc3_complex *x0 = x + n8, *x1 = x0 - 1;

    float *y0 = y + n4, *y1 = y0;

    for ( ; y1 > y; x0++, x1--, w0++, w1--) {

        float u0 = x0->im * w0->im + x0->re * w0->re;
        float u1 = x1->re * w1->im - x1->im * w1->re;

        float v0 = x0->re * w0->im - x0->im * w0->re;
        float v1 = x1->im * w1->im + x1->re * w1->re;

        *(y0++) = u0;  *(y0++) = u1;
        *(--y1) = v0;  *(--y1) = v1;
    }
}

/**
 * Pre-rotate IMDCT coefficients of N points, before FFT N/4 points FFT
 * def             Size and twiddles factors
 * x, y            Input and output coefficients
 *
 * `x` and `y` can be the same buffer
 * The real and imaginary parts of `y` are swapped,
 * to operate on FFT instead of IFFT
 */
LC3_HOT static void imdct_pre_fft(const struct lc3_mdct_rot_def *def,
    const float *x, struct lc3_complex *y)
{
    int n4 = def->n4;

    const float *x0 = x, *x1 = x0 + 2*n4;

    const struct lc3_complex *w0 = def->w, *w1 = w0 + n4;
    struct lc3_complex *y0 = y, *y1 = y0 + n4;

    while (x0 < x1) {
        float u0 = *(x0++), u1 = *(--x1);
        float v0 = *(x0++), v1 = *(--x1);
        struct lc3_complex uw = *(w0++), vw = *(--w1);

        (y0  )->re = - u0 * uw.re - u1 * uw.im;
        (y0++)->im = - u1 * uw.re + u0 * uw.im;

        (--y1)->re = - v1 * vw.re - v0 * vw.im;
        (  y1)->im = - v0 * vw.re + v1 * vw.im;
    }
}

/**
 * Post-rotate FFT N/4 points coefficients, resulting IMDCT N points
 * def             Size and twiddles factors
 * x, y            Input and output coefficients
 *
 * `x` and y` can be the same buffer
 * The real and imaginary parts of `x` are swapped,
 * to operate on FFT instead of IFFT
 */
LC3_HOT static void imdct_post_fft(const struct lc3_mdct_rot_def *def,
    const struct lc3_complex *x, float *y)
{
    int n4 = def->n4;

    const struct lc3_complex *w0 = def->w, *w1 = w0 + n4;
    const struct lc3_complex *x0 = x, *x1 = x0 + n4;

    float *y0 = y, *y1 = y0 + 2*n4;

    while (x0 < x1) {
        struct lc3_complex uz = *(x0++), vz = *(--x1);
        struct lc3_complex uw = *(w0++), vw = *(--w1);

        *(y0++) = uz.re * uw.im - uz.im * uw.re;
        *(--y1) = uz.re * uw.re + uz.im * uw.im;

        *(--y1) = vz.re * vw.im - vz.im * vw.re;
        *(y0++) = vz.re * vw.re + vz.im * vw.im;
    }
}

/**
 * Apply windowing of samples
 * dt, sr          Duration and samplerate
 * x, d            Middle half of IMDCT coefficients and delayed samples
 * y, d            Output samples and delayed ones
 */
LC3_HOT static void imdct_window(enum lc3_dt dt, enum lc3_srate sr,
    const float *x, float *d, float *y)
{
    /* The full MDCT coefficients is given by symmetry :
     *   T[   0 ..  n/4-1] = -half[n/4-1 .. 0    ]
     *   T[ n/4 ..  n/2-1] =  half[0     .. n/4-1]
     *   T[ n/2 .. 3n/4-1] =  half[n/4   .. n/2-1]
     *   T[3n/4 ..    n-1] =  half[n/2-1 .. n/4  ]  */

    int n4 = LC3_NS(dt, sr) >> 1, nd = LC3_ND(dt, sr);
    const float *w2 = lc3_mdct_win[dt][sr], *w0 = w2 + 3*n4, *w1 = w0;

    const float *x0 = d + nd-n4, *x1 = x0;
    float *y0 = y + nd-n4, *y1 = y0, *y2 = d + nd, *y3 = d;

    while (y0 > y) {
        *(--y0) = *(--x0) - *(x  ) * *(w1++);
        *(y1++) = *(x1++) + *(x++) * *(--w0);

        *(--y0) = *(--x0) - *(x  ) * *(w1++);
        *(y1++) = *(x1++) + *(x++) * *(--w0);
    }

    while (y1 < y + nd) {
        *(y1++) = *(x1++) + *(x++) * *(--w0);
        *(y1++) = *(x1++) + *(x++) * *(--w0);
    }

    while (y1 < y + 2*n4) {
        *(y1++) = *(x  ) * *(--w0);
        *(--y2) = *(x++) * *(w2++);

        *(y1++) = *(x  ) * *(--w0);
        *(--y2) = *(x++) * *(w2++);
    }

    while (y2 > y3) {
        *(y3++) = *(x  ) * *(--w0);
        *(--y2) = *(x++) * *(w2++);

        *(y3++) = *(x  ) * *(--w0);
        *(--y2) = *(x++) * *(w2++);
    }
}

/**
 * Rescale samples
 * x, n            Input and count of samples, scaled as output
 * scale           Scale factor
 */
LC3_HOT static void rescale(float *x, int n, float f)
{
    for (int i = 0; i < (n >> 2); i++) {
        *(x++) *= f; *(x++) *= f;
        *(x++) *= f; *(x++) *= f;
    }
}

/**
 * Forward MDCT transformation
 */
void lc3_mdct_forward(enum lc3_dt dt, enum lc3_srate sr,
    enum lc3_srate sr_dst, const float *x, float *d, float *y)
{
    const struct lc3_mdct_rot_def *rot = lc3_mdct_rot[dt][sr];
    int ns_dst = LC3_NS(dt, sr_dst);
    int ns = LC3_NS(dt, sr);

    struct lc3_complex buffer[LC3_MAX_NS / 2];
    struct lc3_complex *z = (struct lc3_complex *)y;
    union { float *f; struct lc3_complex *z; } u = { .z = buffer };

    mdct_window(dt, sr, x, d, u.f);

    mdct_pre_fft(rot, u.f, u.z);
    u.z = fft(u.z, ns/2, u.z, z);
    mdct_post_fft(rot, u.z, y);

    if (ns != ns_dst)
        rescale(y, ns_dst, sqrtf((float)ns_dst / ns));
}

/**
 * Inverse MDCT transformation
 */
void lc3_mdct_inverse(enum lc3_dt dt, enum lc3_srate sr,
    enum lc3_srate sr_src, const float *x, float *d, float *y)
{
    const struct lc3_mdct_rot_def *rot = lc3_mdct_rot[dt][sr];
    int ns_src = LC3_NS(dt, sr_src);
    int ns = LC3_NS(dt, sr);

    struct lc3_complex buffer[LC3_MAX_NS / 2];
    struct lc3_complex *z = (struct lc3_complex *)y;
    union { float *f; struct lc3_complex *z; } u = { .z = buffer };

    imdct_pre_fft(rot, x, z);
    z = fft(z, ns/2, z, u.z);
    imdct_post_fft(rot, z, u.f);

    if (ns != ns_src)
        rescale(u.f, ns, sqrtf((float)ns / ns_src));

    imdct_window(dt, sr, u.f, d, y);
}
