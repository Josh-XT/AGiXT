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

#include "sns.h"
#include "tables.h"


/* ----------------------------------------------------------------------------
 *  DCT-16
 * -------------------------------------------------------------------------- */

/**
 * Matrix of DCT-16 coefficients
 *
 * M[n][k] = 2f cos( Pi k (2n + 1) / 2N )
 *
 *   k = [0..N-1], n = [0..N-1], N = 16
 *   f = sqrt(1/4N) for k=0, sqrt(1/2N) otherwise
 */
static const float dct16_m[16][16] = {

    {  2.50000000e-01,  3.51850934e-01,  3.46759961e-01,  3.38329500e-01,
       3.26640741e-01,  3.11806253e-01,  2.93968901e-01,  2.73300467e-01,
       2.50000000e-01,  2.24291897e-01,  1.96423740e-01,  1.66663915e-01,
       1.35299025e-01,  1.02631132e-01,  6.89748448e-02,  3.46542923e-02 },

    {  2.50000000e-01,  3.38329500e-01,  2.93968901e-01,  2.24291897e-01,
       1.35299025e-01,  3.46542923e-02, -6.89748448e-02, -1.66663915e-01,
      -2.50000000e-01, -3.11806253e-01, -3.46759961e-01, -3.51850934e-01,
      -3.26640741e-01, -2.73300467e-01, -1.96423740e-01, -1.02631132e-01 },

     { 2.50000000e-01,  3.11806253e-01,  1.96423740e-01,  3.46542923e-02,
      -1.35299025e-01, -2.73300467e-01, -3.46759961e-01, -3.38329500e-01,
      -2.50000000e-01, -1.02631132e-01,  6.89748448e-02,  2.24291897e-01,
       3.26640741e-01,  3.51850934e-01,  2.93968901e-01,  1.66663915e-01 },

     { 2.50000000e-01,  2.73300467e-01,  6.89748448e-02, -1.66663915e-01,
      -3.26640741e-01, -3.38329500e-01, -1.96423740e-01,  3.46542923e-02,
       2.50000000e-01,  3.51850934e-01,  2.93968901e-01,  1.02631132e-01,
      -1.35299025e-01, -3.11806253e-01, -3.46759961e-01, -2.24291897e-01 },

    {  2.50000000e-01,  2.24291897e-01, -6.89748448e-02, -3.11806253e-01,
      -3.26640741e-01, -1.02631132e-01,  1.96423740e-01,  3.51850934e-01,
       2.50000000e-01, -3.46542923e-02, -2.93968901e-01, -3.38329500e-01,
      -1.35299025e-01,  1.66663915e-01,  3.46759961e-01,  2.73300467e-01 },

    {  2.50000000e-01,  1.66663915e-01, -1.96423740e-01, -3.51850934e-01,
      -1.35299025e-01,  2.24291897e-01,  3.46759961e-01,  1.02631132e-01,
      -2.50000000e-01, -3.38329500e-01, -6.89748448e-02,  2.73300467e-01,
       3.26640741e-01,  3.46542923e-02, -2.93968901e-01, -3.11806253e-01 },

    {  2.50000000e-01,  1.02631132e-01, -2.93968901e-01, -2.73300467e-01,
       1.35299025e-01,  3.51850934e-01,  6.89748448e-02, -3.11806253e-01,
      -2.50000000e-01,  1.66663915e-01,  3.46759961e-01,  3.46542923e-02,
      -3.26640741e-01, -2.24291897e-01,  1.96423740e-01,  3.38329500e-01 },

    {  2.50000000e-01,  3.46542923e-02, -3.46759961e-01, -1.02631132e-01,
       3.26640741e-01,  1.66663915e-01, -2.93968901e-01, -2.24291897e-01,
       2.50000000e-01,  2.73300467e-01, -1.96423740e-01, -3.11806253e-01,
       1.35299025e-01,  3.38329500e-01, -6.89748448e-02, -3.51850934e-01 },

    {  2.50000000e-01, -3.46542923e-02, -3.46759961e-01,  1.02631132e-01,
       3.26640741e-01, -1.66663915e-01, -2.93968901e-01,  2.24291897e-01,
       2.50000000e-01, -2.73300467e-01, -1.96423740e-01,  3.11806253e-01,
       1.35299025e-01, -3.38329500e-01, -6.89748448e-02,  3.51850934e-01 },

    {  2.50000000e-01, -1.02631132e-01, -2.93968901e-01,  2.73300467e-01,
       1.35299025e-01, -3.51850934e-01,  6.89748448e-02,  3.11806253e-01,
      -2.50000000e-01, -1.66663915e-01,  3.46759961e-01, -3.46542923e-02,
      -3.26640741e-01,  2.24291897e-01,  1.96423740e-01, -3.38329500e-01 },

    {  2.50000000e-01, -1.66663915e-01, -1.96423740e-01,  3.51850934e-01,
      -1.35299025e-01, -2.24291897e-01,  3.46759961e-01, -1.02631132e-01,
      -2.50000000e-01,  3.38329500e-01, -6.89748448e-02, -2.73300467e-01,
       3.26640741e-01, -3.46542923e-02, -2.93968901e-01,  3.11806253e-01 },

    {  2.50000000e-01, -2.24291897e-01, -6.89748448e-02,  3.11806253e-01,
      -3.26640741e-01,  1.02631132e-01,  1.96423740e-01, -3.51850934e-01,
       2.50000000e-01,  3.46542923e-02, -2.93968901e-01,  3.38329500e-01,
      -1.35299025e-01, -1.66663915e-01,  3.46759961e-01, -2.73300467e-01 },

    {  2.50000000e-01, -2.73300467e-01,  6.89748448e-02,  1.66663915e-01,
      -3.26640741e-01,  3.38329500e-01, -1.96423740e-01, -3.46542923e-02,
       2.50000000e-01, -3.51850934e-01,  2.93968901e-01, -1.02631132e-01,
      -1.35299025e-01,  3.11806253e-01, -3.46759961e-01,  2.24291897e-01 },

    {  2.50000000e-01, -3.11806253e-01,  1.96423740e-01, -3.46542923e-02,
      -1.35299025e-01,  2.73300467e-01, -3.46759961e-01,  3.38329500e-01,
      -2.50000000e-01,  1.02631132e-01,  6.89748448e-02, -2.24291897e-01,
       3.26640741e-01, -3.51850934e-01,  2.93968901e-01, -1.66663915e-01 },

    {  2.50000000e-01, -3.38329500e-01,  2.93968901e-01, -2.24291897e-01,
       1.35299025e-01, -3.46542923e-02, -6.89748448e-02,  1.66663915e-01,
      -2.50000000e-01,  3.11806253e-01, -3.46759961e-01,  3.51850934e-01,
      -3.26640741e-01,  2.73300467e-01, -1.96423740e-01,  1.02631132e-01 },

    {  2.50000000e-01, -3.51850934e-01,  3.46759961e-01, -3.38329500e-01,
       3.26640741e-01, -3.11806253e-01,  2.93968901e-01, -2.73300467e-01,
       2.50000000e-01, -2.24291897e-01,  1.96423740e-01, -1.66663915e-01,
       1.35299025e-01, -1.02631132e-01,  6.89748448e-02, -3.46542923e-02 },

};

/**
 * Forward DCT-16 transformation
 * x, y            Input and output 16 values
 */
LC3_HOT static void dct16_forward(const float *x, float *y)
{
    for (int i = 0, j; i < 16; i++)
        for (y[i] = 0, j = 0; j < 16; j++)
            y[i] += x[j] * dct16_m[j][i];
}

/**
 * Inverse DCT-16 transformation
 * x, y            Input and output 16 values
 */
LC3_HOT static void dct16_inverse(const float *x, float *y)
{
    for (int i = 0, j; i < 16; i++)
        for (y[i] = 0, j = 0; j < 16; j++)
            y[i] += x[j] * dct16_m[i][j];
}


/* ----------------------------------------------------------------------------
 *  Scale factors
 * -------------------------------------------------------------------------- */

/**
 * Scale factors
 * dt, sr          Duration and samplerate of the frame
 * eb              Energy estimation per bands
 * att             1: Attack detected  0: Otherwise
 * scf             Output 16 scale factors
 */
LC3_HOT static void compute_scale_factors(
    enum lc3_dt dt, enum lc3_srate sr,
    const float *eb, bool att, float *scf)
{
    /* Pre-emphasis gain table :
     * Ge[b] = 10 ^ (b * g_tilt) / 630 , b = [0..63] */

    static const float ge_table[LC3_NUM_SRATE][LC3_NUM_BANDS] = {

        [LC3_SRATE_8K] = { /* g_tilt = 14 */
            1.00000000e+00, 1.05250029e+00, 1.10775685e+00, 1.16591440e+00,
            1.22712524e+00, 1.29154967e+00, 1.35935639e+00, 1.43072299e+00,
            1.50583635e+00, 1.58489319e+00, 1.66810054e+00, 1.75567629e+00,
            1.84784980e+00, 1.94486244e+00, 2.04696827e+00, 2.15443469e+00,
            2.26754313e+00, 2.38658979e+00, 2.51188643e+00, 2.64376119e+00,
            2.78255940e+00, 2.92864456e+00, 3.08239924e+00, 3.24422608e+00,
            3.41454887e+00, 3.59381366e+00, 3.78248991e+00, 3.98107171e+00,
            4.19007911e+00, 4.41005945e+00, 4.64158883e+00, 4.88527357e+00,
            5.14175183e+00, 5.41169527e+00, 5.69581081e+00, 5.99484250e+00,
            6.30957344e+00, 6.64082785e+00, 6.98947321e+00, 7.35642254e+00,
            7.74263683e+00, 8.14912747e+00, 8.57695899e+00, 9.02725178e+00,
            9.50118507e+00, 1.00000000e+01, 1.05250029e+01, 1.10775685e+01,
            1.16591440e+01, 1.22712524e+01, 1.29154967e+01, 1.35935639e+01,
            1.43072299e+01, 1.50583635e+01, 1.58489319e+01, 1.66810054e+01,
            1.75567629e+01, 1.84784980e+01, 1.94486244e+01, 2.04696827e+01,
            2.15443469e+01, 2.26754313e+01, 2.38658979e+01, 2.51188643e+01 },

        [LC3_SRATE_16K] = { /* g_tilt = 18 */
            1.00000000e+00, 1.06800043e+00, 1.14062492e+00, 1.21818791e+00,
            1.30102522e+00, 1.38949549e+00, 1.48398179e+00, 1.58489319e+00,
            1.69266662e+00, 1.80776868e+00, 1.93069773e+00, 2.06198601e+00,
            2.20220195e+00, 2.35195264e+00, 2.51188643e+00, 2.68269580e+00,
            2.86512027e+00, 3.05994969e+00, 3.26802759e+00, 3.49025488e+00,
            3.72759372e+00, 3.98107171e+00, 4.25178630e+00, 4.54090961e+00,
            4.84969343e+00, 5.17947468e+00, 5.53168120e+00, 5.90783791e+00,
            6.30957344e+00, 6.73862717e+00, 7.19685673e+00, 7.68624610e+00,
            8.20891416e+00, 8.76712387e+00, 9.36329209e+00, 1.00000000e+01,
            1.06800043e+01, 1.14062492e+01, 1.21818791e+01, 1.30102522e+01,
            1.38949549e+01, 1.48398179e+01, 1.58489319e+01, 1.69266662e+01,
            1.80776868e+01, 1.93069773e+01, 2.06198601e+01, 2.20220195e+01,
            2.35195264e+01, 2.51188643e+01, 2.68269580e+01, 2.86512027e+01,
            3.05994969e+01, 3.26802759e+01, 3.49025488e+01, 3.72759372e+01,
            3.98107171e+01, 4.25178630e+01, 4.54090961e+01, 4.84969343e+01,
            5.17947468e+01, 5.53168120e+01, 5.90783791e+01, 6.30957344e+01 },

        [LC3_SRATE_24K] = { /* g_tilt = 22 */
            1.00000000e+00, 1.08372885e+00, 1.17446822e+00, 1.27280509e+00,
            1.37937560e+00, 1.49486913e+00, 1.62003281e+00, 1.75567629e+00,
            1.90267705e+00, 2.06198601e+00, 2.23463373e+00, 2.42173704e+00,
            2.62450630e+00, 2.84425319e+00, 3.08239924e+00, 3.34048498e+00,
            3.62017995e+00, 3.92329345e+00, 4.25178630e+00, 4.60778348e+00,
            4.99358789e+00, 5.41169527e+00, 5.86481029e+00, 6.35586411e+00,
            6.88803330e+00, 7.46476041e+00, 8.08977621e+00, 8.76712387e+00,
            9.50118507e+00, 1.02967084e+01, 1.11588399e+01, 1.20931568e+01,
            1.31057029e+01, 1.42030283e+01, 1.53922315e+01, 1.66810054e+01,
            1.80776868e+01, 1.95913107e+01, 2.12316686e+01, 2.30093718e+01,
            2.49359200e+01, 2.70237760e+01, 2.92864456e+01, 3.17385661e+01,
            3.43959997e+01, 3.72759372e+01, 4.03970086e+01, 4.37794036e+01,
            4.74450028e+01, 5.14175183e+01, 5.57226480e+01, 6.03882412e+01,
            6.54444792e+01, 7.09240702e+01, 7.68624610e+01, 8.32980665e+01,
            9.02725178e+01, 9.78309319e+01, 1.06022203e+02, 1.14899320e+02,
            1.24519708e+02, 1.34945600e+02, 1.46244440e+02, 1.58489319e+02 },

        [LC3_SRATE_32K] = { /* g_tilt = 26 */
            1.00000000e+00, 1.09968890e+00, 1.20931568e+00, 1.32987103e+00,
            1.46244440e+00, 1.60823388e+00, 1.76855694e+00, 1.94486244e+00,
            2.13874364e+00, 2.35195264e+00, 2.58641621e+00, 2.84425319e+00,
            3.12779366e+00, 3.43959997e+00, 3.78248991e+00, 4.15956216e+00,
            4.57422434e+00, 5.03022373e+00, 5.53168120e+00, 6.08312841e+00,
            6.68954879e+00, 7.35642254e+00, 8.08977621e+00, 8.89623710e+00,
            9.78309319e+00, 1.07583590e+01, 1.18308480e+01, 1.30102522e+01,
            1.43072299e+01, 1.57335019e+01, 1.73019574e+01, 1.90267705e+01,
            2.09235283e+01, 2.30093718e+01, 2.53031508e+01, 2.78255940e+01,
            3.05994969e+01, 3.36499270e+01, 3.70044512e+01, 4.06933843e+01,
            4.47500630e+01, 4.92111475e+01, 5.41169527e+01, 5.95118121e+01,
            6.54444792e+01, 7.19685673e+01, 7.91430346e+01, 8.70327166e+01,
            9.57089124e+01, 1.05250029e+02, 1.15742288e+02, 1.27280509e+02,
            1.39968963e+02, 1.53922315e+02, 1.69266662e+02, 1.86140669e+02,
            2.04696827e+02, 2.25102829e+02, 2.47543082e+02, 2.72220379e+02,
            2.99357729e+02, 3.29200372e+02, 3.62017995e+02, 3.98107171e+02 },

        [LC3_SRATE_48K] = { /* g_tilt = 30 */
            1.00000000e+00, 1.11588399e+00, 1.24519708e+00, 1.38949549e+00,
            1.55051578e+00, 1.73019574e+00, 1.93069773e+00, 2.15443469e+00,
            2.40409918e+00, 2.68269580e+00, 2.99357729e+00, 3.34048498e+00,
            3.72759372e+00, 4.15956216e+00, 4.64158883e+00, 5.17947468e+00,
            5.77969288e+00, 6.44946677e+00, 7.19685673e+00, 8.03085722e+00,
            8.96150502e+00, 1.00000000e+01, 1.11588399e+01, 1.24519708e+01,
            1.38949549e+01, 1.55051578e+01, 1.73019574e+01, 1.93069773e+01,
            2.15443469e+01, 2.40409918e+01, 2.68269580e+01, 2.99357729e+01,
            3.34048498e+01, 3.72759372e+01, 4.15956216e+01, 4.64158883e+01,
            5.17947468e+01, 5.77969288e+01, 6.44946677e+01, 7.19685673e+01,
            8.03085722e+01, 8.96150502e+01, 1.00000000e+02, 1.11588399e+02,
            1.24519708e+02, 1.38949549e+02, 1.55051578e+02, 1.73019574e+02,
            1.93069773e+02, 2.15443469e+02, 2.40409918e+02, 2.68269580e+02,
            2.99357729e+02, 3.34048498e+02, 3.72759372e+02, 4.15956216e+02,
            4.64158883e+02, 5.17947468e+02, 5.77969288e+02, 6.44946677e+02,
            7.19685673e+02, 8.03085722e+02, 8.96150502e+02, 1.00000000e+03 },
    };

    float e[LC3_NUM_BANDS];

    /* --- Copy and padding --- */

    int nb = LC3_MIN(lc3_band_lim[dt][sr][LC3_NUM_BANDS], LC3_NUM_BANDS);
    int n2 = LC3_NUM_BANDS - nb;

    for (int i2 = 0; i2 < n2; i2++)
        e[2*i2 + 0] = e[2*i2 + 1] = eb[i2];

    memcpy(e + 2*n2, eb + n2, (nb - n2) * sizeof(float));

    /* --- Smoothing, pre-emphasis and logarithm --- */

    const float *ge = ge_table[sr];

    float e0 = e[0], e1 = e[0], e2;
    float e_sum = 0;

    for (int i = 0; i < LC3_NUM_BANDS-1; ) {
        e[i] = (e0 * 0.25f + e1 * 0.5f + (e2 = e[i+1]) * 0.25f) * ge[i];
        e_sum += e[i++];

        e[i] = (e1 * 0.25f + e2 * 0.5f + (e0 = e[i+1]) * 0.25f) * ge[i];
        e_sum += e[i++];

        e[i] = (e2 * 0.25f + e0 * 0.5f + (e1 = e[i+1]) * 0.25f) * ge[i];
        e_sum += e[i++];
    }

    e[LC3_NUM_BANDS-1] = (e0 * 0.25f + e1 * 0.75f) * ge[LC3_NUM_BANDS-1];
    e_sum += e[LC3_NUM_BANDS-1];

    float noise_floor = fmaxf(e_sum * (1e-4f / 64), 0x1p-32f);

    for (int i = 0; i < LC3_NUM_BANDS; i++)
        e[i] = fast_log2f(fmaxf(e[i], noise_floor)) * 0.5f;

    /* --- Grouping & scaling --- */

    float scf_sum;

    scf[0] = (e[0] + e[4]) * 1.f/12 +
             (e[0] + e[3]) * 2.f/12 +
             (e[1] + e[2]) * 3.f/12  ;
    scf_sum = scf[0];

    for (int i = 1; i < 15; i++) {
        scf[i] = (e[4*i-1] + e[4*i+4]) * 1.f/12 +
                 (e[4*i  ] + e[4*i+3]) * 2.f/12 +
                 (e[4*i+1] + e[4*i+2]) * 3.f/12  ;
        scf_sum += scf[i];
    }

    scf[15] = (e[59] + e[63]) * 1.f/12 +
              (e[60] + e[63]) * 2.f/12 +
              (e[61] + e[62]) * 3.f/12  ;
    scf_sum += scf[15];

    for (int i = 0; i < 16; i++)
        scf[i] = 0.85f * (scf[i] - scf_sum * 1.f/16);

    /* --- Attack handling --- */

    if (!att)
        return;

    float s0, s1 = scf[0], s2 = scf[1], s3 = scf[2], s4 = scf[3];
    float sn = s1 + s2;

    scf[0] = (sn += s3) * 1.f/3;
    scf[1] = (sn += s4) * 1.f/4;
    scf_sum = scf[0] + scf[1];

    for (int i = 2; i < 14; i++, sn -= s0) {
        s0 = s1, s1 = s2, s2 = s3, s3 = s4, s4 = scf[i+2];
        scf[i] = (sn += s4) * 1.f/5;
        scf_sum += scf[i];
    }

    scf[14] = (sn      ) * 1.f/4;
    scf[15] = (sn -= s1) * 1.f/3;
    scf_sum += scf[14] + scf[15];

    for (int i = 0; i < 16; i++)
        scf[i] = (dt == LC3_DT_7M5 ? 0.3f : 0.5f) *
                 (scf[i] - scf_sum * 1.f/16);
}

/**
 * Codebooks
 * scf             Input 16 scale factors
 * lf/hfcb_idx     Output the low and high frequency codebooks index
 */
LC3_HOT static void resolve_codebooks(
    const float *scf, int *lfcb_idx, int *hfcb_idx)
{
    float dlfcb_max = 0, dhfcb_max = 0;
    *lfcb_idx = *hfcb_idx = 0;

    for (int icb = 0; icb < 32; icb++) {
        const float *lfcb = lc3_sns_lfcb[icb];
        const float *hfcb = lc3_sns_hfcb[icb];
        float dlfcb = 0, dhfcb = 0;

        for (int i = 0; i < 8; i++) {
            dlfcb += (scf[  i] - lfcb[i]) * (scf[  i] - lfcb[i]);
            dhfcb += (scf[8+i] - hfcb[i]) * (scf[8+i] - hfcb[i]);
        }

        if (icb == 0 || dlfcb < dlfcb_max)
            *lfcb_idx = icb, dlfcb_max = dlfcb;

        if (icb == 0 || dhfcb < dhfcb_max)
            *hfcb_idx = icb, dhfcb_max = dhfcb;
    }
}

/**
 * Unit energy normalize pulse configuration
 * c               Pulse configuration
 * cn              Normalized pulse configuration
 */
LC3_HOT static void normalize(const int *c, float *cn)
{
    int c2_sum = 0;
    for (int i = 0; i < 16; i++)
        c2_sum += c[i] * c[i];

    float c_norm = 1.f / sqrtf(c2_sum);

    for (int i = 0; i < 16; i++)
        cn[i] = c[i] * c_norm;
}

/**
 * Sub-procedure of `quantize()`, add unit pulse
 * x, y, n         Transformed residual, and vector of pulses with length
 * start, end      Current number of pulses, limit to reach
 * corr, energy    Correlation (x,y) and y energy, updated at output
 */
LC3_HOT static void add_pulse(const float *x, int *y, int n,
    int start, int end, float *corr, float *energy)
{
    for (int k = start; k < end; k++) {
        float best_c2 = (*corr + x[0]) * (*corr + x[0]);
        float best_e = *energy + 2*y[0] + 1;
        int nbest = 0;

        for (int i = 1; i < n; i++) {
            float c2 = (*corr + x[i]) * (*corr + x[i]);
            float e  = *energy + 2*y[i] + 1;

            if (c2 * best_e > e * best_c2)
                best_c2 = c2, best_e = e, nbest = i;
        }

        *corr += x[nbest];
        *energy += 2*y[nbest] + 1;
        y[nbest]++;
    }
}

/**
 * Quantization of codebooks residual
 * scf             Input 16 scale factors, output quantized version
 * lf/hfcb_idx     Codebooks index
 * c, cn           Output 4 pulse configurations candidates, normalized
 * shape/gain_idx  Output selected shape/gain indexes
 */
LC3_HOT static void quantize(const float *scf, int lfcb_idx, int hfcb_idx,
    int (*c)[16], float (*cn)[16], int *shape_idx, int *gain_idx)
{
    /* --- Residual --- */

    const float *lfcb = lc3_sns_lfcb[lfcb_idx];
    const float *hfcb = lc3_sns_hfcb[hfcb_idx];
    float r[16], x[16];

    for (int i = 0; i < 8; i++) {
        r[  i] = scf[  i] - lfcb[i];
        r[8+i] = scf[8+i] - hfcb[i];
    }

    dct16_forward(r, x);

    /* --- Shape 3 candidate ---
     * Project to or below pyramid N = 16, K = 6,
     * then add unit pulses until you reach K = 6, over N = 16 */

    float xm[16];
    float xm_sum = 0;

    for (int i = 0; i < 16; i++) {
        xm[i] = fabsf(x[i]);
        xm_sum += xm[i];
    }

    float proj_factor = (6 - 1) / fmaxf(xm_sum, 1e-31f);
    float corr = 0, energy = 0;
    int npulses = 0;

    for (int i = 0; i < 16; i++) {
        c[3][i] = floorf(xm[i] * proj_factor);
        npulses += c[3][i];
        corr    += c[3][i] * xm[i];
        energy  += c[3][i] * c[3][i];
    }

    add_pulse(xm, c[3], 16, npulses, 6, &corr, &energy);
    npulses = 6;

    /* --- Shape 2 candidate ---
     * Add unit pulses until you reach K = 8 on shape 3 */

    memcpy(c[2], c[3], sizeof(c[2]));

    add_pulse(xm, c[2], 16, npulses, 8, &corr, &energy);
    npulses = 8;

    /* --- Shape 1 candidate ---
     * Remove any unit pulses from shape 2 that are not part of 0 to 9
     * Update energy and correlation terms accordingly
     * Add unit pulses until you reach K = 10, over N = 10 */

    memcpy(c[1], c[2], sizeof(c[1]));

    for (int i = 10; i < 16; i++) {
        c[1][i] = 0;
        npulses -= c[2][i];
        corr    -= c[2][i] * xm[i];
        energy  -= c[2][i] * c[2][i];
    }

    add_pulse(xm, c[1], 10, npulses, 10, &corr, &energy);
    npulses = 10;

    /* --- Shape 0 candidate ---
     * Add unit pulses until you reach K = 1, on shape 1 */

    memcpy(c[0], c[1], sizeof(c[0]));

    add_pulse(xm + 10, c[0] + 10, 6, 0, 1, &corr, &energy);

    /* --- Add sign and unit energy normalize --- */

    for (int j = 0; j < 16; j++)
        for (int i = 0; i < 4; i++)
            c[i][j] = x[j] < 0 ? -c[i][j] : c[i][j];

    for (int i = 0; i < 4; i++)
        normalize(c[i], cn[i]);

    /* --- Determe shape & gain index ---
     * Search the Mean Square Error, within (shape, gain) combinations */

    float mse_min = INFINITY;
    *shape_idx = *gain_idx = 0;

    for (int ic = 0; ic < 4; ic++) {
        const struct lc3_sns_vq_gains *cgains = lc3_sns_vq_gains + ic;
        float cmse_min = INFINITY;
        int cgain_idx = 0;

        for (int ig = 0; ig < cgains->count; ig++) {
            float g = cgains->v[ig];

            float mse = 0;
            for (int i = 0; i < 16; i++)
                mse += (x[i] - g * cn[ic][i]) * (x[i] - g * cn[ic][i]);

            if (mse < cmse_min) {
                cgain_idx = ig,
                cmse_min = mse;
            }
        }

        if (cmse_min < mse_min) {
            *shape_idx = ic, *gain_idx = cgain_idx;
            mse_min = cmse_min;
        }
    }
}

/**
 * Unquantization of codebooks residual
 * lf/hfcb_idx     Low and high frequency codebooks index
 * c               Table of normalized pulse configuration
 * shape/gain      Selected shape/gain indexes
 * scf             Return unquantized scale factors
 */
LC3_HOT static void unquantize(int lfcb_idx, int hfcb_idx,
    const float *c, int shape, int gain, float *scf)
{
    const float *lfcb = lc3_sns_lfcb[lfcb_idx];
    const float *hfcb = lc3_sns_hfcb[hfcb_idx];
    float g = lc3_sns_vq_gains[shape].v[gain];

    dct16_inverse(c, scf);

    for (int i = 0; i < 8; i++)
        scf[i] = lfcb[i] + g * scf[i];

    for (int i = 8; i < 16; i++)
        scf[i] = hfcb[i-8] + g * scf[i];
}

/**
 * Sub-procedure of `sns_enumerate()`, enumeration of a vector
 * c, n            Table of pulse configuration, and length
 * idx, ls         Return enumeration set
 */
static void enum_mvpq(const int *c, int n, int *idx, bool *ls)
{
    int ci, i, j;

    /* --- Scan for 1st significant coeff --- */

    for (i = 0, c += n; (ci = *(--c)) == 0 ; i++);

    *idx = 0;
    *ls = ci < 0;

    /* --- Scan remaining coefficients --- */

    for (i++, j = LC3_ABS(ci); i < n; i++, j += LC3_ABS(ci)) {

        if ((ci = *(--c)) != 0) {
            *idx = (*idx << 1) | *ls;
            *ls = ci < 0;
        }

        *idx += lc3_sns_mpvq_offsets[i][j];
    }
}

/**
 * Sub-procedure of `sns_deenumerate()`, deenumeration of a vector
 * idx, ls         Enumeration set
 * npulses         Number of pulses in the set
 * c, n            Table of pulses configuration, and length
 */
static void deenum_mvpq(int idx, bool ls, int npulses, int *c, int n)
{
    int i;

    /* --- Scan for coefficients --- */

    for (i = n-1; i >= 0 && idx; i--) {

        int ci = 0;

        for (ci = 0; idx < lc3_sns_mpvq_offsets[i][npulses - ci]; ci++);
        idx -= lc3_sns_mpvq_offsets[i][npulses - ci];

        *(c++) = ls ? -ci : ci;
        npulses -= ci;
        if (ci > 0) {
            ls = idx & 1;
            idx >>= 1;
        }
    }

    /* --- Set last significant --- */

    int ci = npulses;

    if (i-- >= 0)
        *(c++) = ls ? -ci : ci;

    while (i-- >= 0)
        *(c++) = 0;
}

/**
 * SNS Enumeration of PVQ configuration
 * shape           Selected shape index
 * c               Selected pulse configuration
 * idx_a, ls_a     Return enumeration set A
 * idx_b, ls_b     Return enumeration set B (shape = 0)
 */
static void enumerate(int shape, const int *c,
    int *idx_a, bool *ls_a, int *idx_b, bool *ls_b)
{
    enum_mvpq(c, shape < 2 ? 10 : 16, idx_a, ls_a);

    if (shape == 0)
        enum_mvpq(c + 10, 6, idx_b, ls_b);
}

/**
 * SNS Deenumeration of PVQ configuration
 * shape           Selected shape index
 * idx_a, ls_a     enumeration set A
 * idx_b, ls_b     enumeration set B (shape = 0)
 * c               Return pulse configuration
 */
static void deenumerate(int shape,
    int idx_a, bool ls_a, int idx_b, bool ls_b, int *c)
{
    int npulses_a = (const int []){ 10, 10, 8, 6 }[shape];

    deenum_mvpq(idx_a, ls_a, npulses_a, c, shape < 2 ? 10 : 16);

    if (shape == 0)
        deenum_mvpq(idx_b, ls_b, 1, c + 10, 6);
    else if (shape == 1)
        memset(c + 10, 0, 6 * sizeof(*c));
}


/* ----------------------------------------------------------------------------
 *  Filtering
 * -------------------------------------------------------------------------- */

/**
 * Spectral shaping
 * dt, sr          Duration and samplerate of the frame
 * scf_q           Quantized scale factors
 * inv             True on inverse shaping, False otherwise
 * x               Spectral coefficients
 * y               Return shapped coefficients
 *
 * `x` and `y` can be the same buffer
 */
LC3_HOT static void spectral_shaping(enum lc3_dt dt, enum lc3_srate sr,
    const float *scf_q, bool inv, const float *x, float *y)
{
    /* --- Interpolate scale factors --- */

    float scf[LC3_NUM_BANDS];
    float s0, s1 = inv ? -scf_q[0] : scf_q[0];

    scf[0] = scf[1] = s1;
    for (int i = 0; i < 15; i++) {
        s0 = s1, s1 = inv ? -scf_q[i+1] : scf_q[i+1];
        scf[4*i+2] = s0 + 0.125f * (s1 - s0);
        scf[4*i+3] = s0 + 0.375f * (s1 - s0);
        scf[4*i+4] = s0 + 0.625f * (s1 - s0);
        scf[4*i+5] = s0 + 0.875f * (s1 - s0);
    }
    scf[62] = s1 + 0.125f * (s1 - s0);
    scf[63] = s1 + 0.375f * (s1 - s0);

    int nb = LC3_MIN(lc3_band_lim[dt][sr][LC3_NUM_BANDS], LC3_NUM_BANDS);
    int n2 = LC3_NUM_BANDS - nb;

    for (int i2 = 0; i2 < n2; i2++)
        scf[i2] = 0.5f * (scf[2*i2] + scf[2*i2+1]);

    if (n2 > 0)
        memmove(scf + n2, scf + 2*n2, (nb - n2) * sizeof(float));

    /* --- Spectral shaping --- */

    const int *lim = lc3_band_lim[dt][sr];

    for (int i = 0, ib = 0; ib < nb; ib++) {
        float g_sns = fast_exp2f(-scf[ib]);

        for ( ; i < lim[ib+1]; i++)
            y[i] = x[i] * g_sns;
    }
}


/* ----------------------------------------------------------------------------
 *  Interface
 * -------------------------------------------------------------------------- */

/**
 * SNS analysis
 */
void lc3_sns_analyze(enum lc3_dt dt, enum lc3_srate sr,
    const float *eb, bool att, struct lc3_sns_data *data,
    const float *x, float *y)
{
    /* Processing steps :
     * - Determine 16 scale factors from bands energy estimation
     * - Get codebooks indexes that match thoses scale factors
     * - Quantize the residual with the selected codebook
     * - The pulse configuration `c[]` is enumerated
     * - Finally shape the spectrum coefficients accordingly */

    float scf[16], cn[4][16];
    int c[4][16];

    compute_scale_factors(dt, sr, eb, att, scf);

    resolve_codebooks(scf, &data->lfcb, &data->hfcb);

    quantize(scf, data->lfcb, data->hfcb,
        c, cn, &data->shape, &data->gain);

    unquantize(data->lfcb, data->hfcb,
        cn[data->shape], data->shape, data->gain, scf);

    enumerate(data->shape, c[data->shape],
        &data->idx_a, &data->ls_a, &data->idx_b, &data->ls_b);

    spectral_shaping(dt, sr, scf, false, x, y);
}

/**
 * SNS synthesis
 */
void lc3_sns_synthesize(enum lc3_dt dt, enum lc3_srate sr,
    const lc3_sns_data_t *data, const float *x, float *y)
{
    float scf[16], cn[16];
    int c[16];

    deenumerate(data->shape,
        data->idx_a, data->ls_a, data->idx_b, data->ls_b, c);

    normalize(c, cn);

    unquantize(data->lfcb, data->hfcb, cn, data->shape, data->gain, scf);

    spectral_shaping(dt, sr, scf, true, x, y);
}

/**
 * Return number of bits coding the bitstream data
 */
int lc3_sns_get_nbits(void)
{
    return 38;
}

/**
 * Put bitstream data
 */
void lc3_sns_put_data(lc3_bits_t *bits, const struct lc3_sns_data *data)
{
    /* --- Codebooks --- */

    lc3_put_bits(bits, data->lfcb, 5);
    lc3_put_bits(bits, data->hfcb, 5);

    /* --- Shape, gain and vectors --- *
     * Write MSB bit of shape index, next LSB bits of shape and gain,
     * and MVPQ vectors indexes are muxed */

    int shape_msb = data->shape >> 1;
    lc3_put_bit(bits, shape_msb);

    if (shape_msb == 0) {
        const int size_a = 2390004;
        int submode = data->shape & 1;

        int mux_high = submode == 0 ?
            2 * (data->idx_b + 1) + data->ls_b : data->gain & 1;
        int mux_code = mux_high * size_a + data->idx_a;

        lc3_put_bits(bits, data->gain >> submode, 1);
        lc3_put_bits(bits, data->ls_a, 1);
        lc3_put_bits(bits, mux_code, 25);

    } else {
        const int size_a = 15158272;
        int submode = data->shape & 1;

        int mux_code = submode == 0 ?
            data->idx_a : size_a + 2 * data->idx_a + (data->gain & 1);

        lc3_put_bits(bits, data->gain >> submode, 2);
        lc3_put_bits(bits, data->ls_a, 1);
        lc3_put_bits(bits, mux_code, 24);
    }
}

/**
 * Get bitstream data
 */
int lc3_sns_get_data(lc3_bits_t *bits, struct lc3_sns_data *data)
{
    /* --- Codebooks --- */

    *data = (struct lc3_sns_data){
        .lfcb = lc3_get_bits(bits, 5),
        .hfcb = lc3_get_bits(bits, 5)
    };

    /* --- Shape, gain and vectors --- */

    int shape_msb = lc3_get_bit(bits);
    data->gain = lc3_get_bits(bits, 1 + shape_msb);
    data->ls_a = lc3_get_bit(bits);

    int mux_code = lc3_get_bits(bits, 25 - shape_msb);

    if (shape_msb == 0) {
        const int size_a = 2390004;

        if (mux_code >= size_a * 14)
            return -1;

        data->idx_a = mux_code % size_a;
        mux_code = mux_code / size_a;

        data->shape = (mux_code < 2);

        if (data->shape == 0) {
            data->idx_b = (mux_code - 2) / 2;
            data->ls_b  = (mux_code - 2) % 2;
        } else {
            data->gain = (data->gain << 1) + (mux_code % 2);
        }

    } else {
        const int size_a = 15158272;

        if (mux_code >= size_a + 1549824)
            return -1;

        data->shape = 2 + (mux_code >= size_a);
        if (data->shape == 2) {
            data->idx_a = mux_code;
        } else {
            mux_code -= size_a;
            data->idx_a = mux_code / 2;
            data->gain = (data->gain << 1) + (mux_code % 2);
        }
    }

    return 0;
}
