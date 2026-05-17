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

/**
 * LC3 - Common constants and types
 */

#ifndef __LC3_COMMON_H
#define __LC3_COMMON_H

#include "lc3.h"
#include "fastmath.h"

#include <stdalign.h>
#include <limits.h>
#include <string.h>

#ifdef __ARM_ARCH
#include <arm_acle.h>
#endif


/**
 * Hot Function attribute
 * Selectively disable sanitizer
 */

#ifdef __clang__

#define LC3_HOT \
    __attribute__((no_sanitize("bounds"))) \
    __attribute__((no_sanitize("integer")))

#else /* __clang__ */

#define LC3_HOT

#endif /* __clang__ */


/**
 * Macros
 * MIN/MAX  Minimum and maximum between 2 values
 * CLIP     Clip a value between low and high limits
 * SATXX    Signed saturation on 'xx' bits
 * ABS      Return absolute value
 */

#define LC3_MIN(a, b)  ( (a) < (b) ?  (a) : (b) )
#define LC3_MAX(a, b)  ( (a) > (b) ?  (a) : (b) )

#define LC3_CLIP(v, min, max)  LC3_MIN(LC3_MAX(v, min), max)
#define LC3_SAT16(v)  LC3_CLIP(v, -(1 << 15), (1 << 15) - 1)
#define LC3_SAT24(v)  LC3_CLIP(v, -(1 << 23), (1 << 23) - 1)

#define LC3_ABS(v)  ( (v) < 0 ? -(v) : (v) )


#if defined(__ARM_FEATURE_SAT) && !(__GNUC__ < 10)

#undef  LC3_SAT16
#define LC3_SAT16(v) __ssat(v, 16)

#undef  LC3_SAT24
#define LC3_SAT24(v) __ssat(v, 24)

#endif /* __ARM_FEATURE_SAT */


/**
 * Convert `dt` in us and `sr` in KHz
 */

#define LC3_DT_US(dt) \
    ( (3 + (dt)) * 2500 )

#define LC3_SRATE_KHZ(sr) \
    ( (1 + (sr) + ((sr) == LC3_SRATE_48K)) * 8 )


/**
 * Return number of samples, delayed samples and
 * encoded spectrum coefficients within a frame
 * - For encoding, keep 1.25 ms for temporal window
 * - For decoding, keep 18 ms of history, aligned on frames, and a frame
 */

#define LC3_NS(dt, sr) \
    ( 20 * (3 + (dt)) * (1 + (sr) + ((sr) == LC3_SRATE_48K)) )

#define LC3_ND(dt, sr) \
    ( (dt) == LC3_DT_7M5 ? 23 * LC3_NS(dt, sr) / 30 \
                         :  5 * LC3_NS(dt, sr) /  8 )

#define LC3_NE(dt, sr) \
    ( 20 * (3 + (dt)) * (1 + (sr)) )

#define LC3_MAX_NS \
    LC3_NS(LC3_DT_10M, LC3_SRATE_48K)

#define LC3_MAX_NE \
    LC3_NE(LC3_DT_10M, LC3_SRATE_48K)

#define LC3_NT(sr_hz) \
    ( (5 * LC3_SRATE_KHZ(sr)) / 4 )

#define LC3_NH(dt, sr) \
    ( ((3 - dt) + 1) * LC3_NS(dt, sr) )


/**
 * Bandwidth, mapped to Nyquist frequency of samplerates
 */

enum lc3_bandwidth {
    LC3_BANDWIDTH_NB = LC3_SRATE_8K,
    LC3_BANDWIDTH_WB = LC3_SRATE_16K,
    LC3_BANDWIDTH_SSWB = LC3_SRATE_24K,
    LC3_BANDWIDTH_SWB = LC3_SRATE_32K,
    LC3_BANDWIDTH_FB = LC3_SRATE_48K,

    LC3_NUM_BANDWIDTH,
};


/**
 * Complex floating point number
 */

struct lc3_complex
{
    float re, im;
};


#endif /* __LC3_COMMON_H */
