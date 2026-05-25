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

#ifndef __LC3_TABLES_H
#define __LC3_TABLES_H

#include "common.h"
#include "bits.h"


/**
 * MDCT Twiddles and window coefficients
 */

struct lc3_fft_bf3_twiddles { int n3; const struct lc3_complex (*t)[2]; };
struct lc3_fft_bf2_twiddles { int n2; const struct lc3_complex *t; };
struct lc3_mdct_rot_def { int n4; const struct lc3_complex *w; };

extern const struct lc3_fft_bf3_twiddles *lc3_fft_twiddles_bf3[];
extern const struct lc3_fft_bf2_twiddles *lc3_fft_twiddles_bf2[][3];
extern const struct lc3_mdct_rot_def *lc3_mdct_rot[LC3_NUM_DT][LC3_NUM_SRATE];

extern const float *lc3_mdct_win[LC3_NUM_DT][LC3_NUM_SRATE];


/**
 * Limits of bands
 */

#define LC3_NUM_BANDS  64

extern const int lc3_band_lim[LC3_NUM_DT][LC3_NUM_SRATE][LC3_NUM_BANDS+1];


/**
 * SNS Quantization
 */

extern const float lc3_sns_lfcb[32][8];
extern const float lc3_sns_hfcb[32][8];

struct lc3_sns_vq_gains {
    int count; const float *v;
};

extern const struct lc3_sns_vq_gains lc3_sns_vq_gains[4];

extern const int32_t lc3_sns_mpvq_offsets[][11];


/**
 * TNS Arithmetic Coding
 */

extern const struct lc3_ac_model lc3_tns_order_models[];
extern const uint16_t lc3_tns_order_bits[][8];

extern const struct lc3_ac_model lc3_tns_coeffs_models[];
extern const uint16_t lc3_tns_coeffs_bits[][17];


/**
 * Long Term Postfilter
 */

extern const float *lc3_ltpf_cnum[LC3_NUM_SRATE][4];
extern const float *lc3_ltpf_cden[LC3_NUM_SRATE][4];


/**
 * Spectral Data Arithmetic Coding
 */

extern const uint8_t lc3_spectrum_lookup[2][2][256][4];
extern const struct lc3_ac_model lc3_spectrum_models[];
extern const uint16_t lc3_spectrum_bits[][17];


#endif /* __LC3_TABLES_H */
