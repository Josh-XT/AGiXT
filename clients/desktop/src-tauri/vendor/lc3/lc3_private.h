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

#ifndef __LC3_PRIVATE_H
#define __LC3_PRIVATE_H

#include <stdint.h>
#include <stdbool.h>


/**
 * Return number of samples, delayed samples and
 * encoded spectrum coefficients within a frame
 * - For encoding, keep 1.25 ms of temporal winodw
 * - For decoding, keep 18 ms of history, aligned on frames, and a frame
 */

#define __LC3_NS(dt_us, sr_hz) \
    ( (dt_us * sr_hz) / 1000 / 1000 )

#define __LC3_ND(dt_us, sr_hz) \
    ( (dt_us) == 7500 ? 23 * __LC3_NS(dt_us, sr_hz) / 30 \
                      :  5 * __LC3_NS(dt_us, sr_hz) /  8 )

#define __LC3_NT(sr_hz) \
    ( (5 * sr_hz) / 4000 )

#define __LC3_NH(dt_us, sr_hz) \
    ( ((3 - ((dt_us) >= 10000)) + 1) * __LC3_NS(dt_us, sr_hz) )


/**
 * Frame duration 7.5ms or 10ms
 */

enum lc3_dt {
    LC3_DT_7M5,
    LC3_DT_10M,

    LC3_NUM_DT
};

/**
 * Sampling frequency
 */

enum lc3_srate {
    LC3_SRATE_8K,
    LC3_SRATE_16K,
    LC3_SRATE_24K,
    LC3_SRATE_32K,
    LC3_SRATE_48K,

    LC3_NUM_SRATE,
};


/**
 * Encoder state and memory
 */

typedef struct lc3_attdet_analysis {
    int32_t en1, an1;
    int p_att;
} lc3_attdet_analysis_t;

struct lc3_ltpf_hp50_state {
    int64_t s1, s2;
};

typedef struct lc3_ltpf_analysis {
    bool active;
    int pitch;
    float nc[2];

    struct lc3_ltpf_hp50_state hp50;
    int16_t x_12k8[384];
    int16_t x_6k4[178];
    int tc;
} lc3_ltpf_analysis_t;

typedef struct lc3_spec_analysis {
    float nbits_off;
    int nbits_spare;
} lc3_spec_analysis_t;

struct lc3_encoder {
    enum lc3_dt dt;
    enum lc3_srate sr, sr_pcm;

    lc3_attdet_analysis_t attdet;
    lc3_ltpf_analysis_t ltpf;
    lc3_spec_analysis_t spec;

    int xt_off, xs_off, xd_off;
    float x[1];
};

#define LC3_ENCODER_BUFFER_COUNT(dt_us, sr_hz) \
    ( ( __LC3_NS(dt_us, sr_hz) + __LC3_NT(sr_hz) ) / 2 + \
        __LC3_NS(dt_us, sr_hz) + __LC3_ND(dt_us, sr_hz) )

#define LC3_ENCODER_MEM_T(dt_us, sr_hz) \
    struct { \
        struct lc3_encoder __e; \
        float __x[LC3_ENCODER_BUFFER_COUNT(dt_us, sr_hz)-1]; \
    }


/**
 * Decoder state and memory
 */

typedef struct lc3_ltpf_synthesis {
    bool active;
    int pitch;
    float c[2*12], x[12];
} lc3_ltpf_synthesis_t;

typedef struct lc3_plc_state {
    uint16_t seed;
    int count;
    float alpha;
} lc3_plc_state_t;

struct lc3_decoder {
    enum lc3_dt dt;
    enum lc3_srate sr, sr_pcm;

    lc3_ltpf_synthesis_t ltpf;
    lc3_plc_state_t plc;

    int xh_off, xs_off, xd_off, xg_off;
    float x[1];
};

#define LC3_DECODER_BUFFER_COUNT(dt_us, sr_hz) \
    ( __LC3_NH(dt_us, sr_hz) + __LC3_ND(dt_us, sr_hz) + \
      __LC3_NS(dt_us, sr_hz) )

#define LC3_DECODER_MEM_T(dt_us, sr_hz) \
    struct { \
        struct lc3_decoder __d; \
        float __x[LC3_DECODER_BUFFER_COUNT(dt_us, sr_hz)-1]; \
    }


#endif /* __LC3_PRIVATE_H */
