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
 * LC3 - Bitstream management
 *
 * The bitstream is written by the 2 ends of the buffer :
 *
 * - Arthmetic coder put bits while increasing memory addresses
 *   in the buffer (forward)
 *
 * - Plain bits are puts starting the end of the buffer, with memeory
 *   addresses decreasing (backward)
 *
 *       .---------------------------------------------------.
 *       | > > > > > > > > > > :         : < < < < < < < < < |
 *       '---------------------------------------------------'
 *       |---------------------> - - - - - - - - - - - - - ->|
 *                              |< - - - <-------------------|
 *          Arithmetic coding                  Plain bits
 *          `lc3_put_symbol()`               `lc3_put_bits()`
 *
 * - The forward writing is protected against buffer overflow, it cannot
 *   write after the buffer, but can overwrite plain bits previously
 *   written in the buffer.
 *
 * - The backward writing is protected against overwrite of the arithmetic
 *   coder bitstream. In such way, the backward bitstream is always limited
 *   by the aritmetic coder bitstream, and can be overwritten by him.
 *
 *       .---------------------------------------------------.
 *       | > > > > > > > > > > :         : < < < < < < < < < |
 *       '---------------------------------------------------'
 *       |---------------------> - - - - - - - - - - - - - ->|
 *       |< - - - - - - - - - - -  - - - <-------------------|
 *          Arithmetic coding                  Plain bits
 *          `lc3_get_symbol()`               `lc3_get_bits()`
 *
 * - Reading is limited to read of the complementary end of the buffer.
 *
 * - The procedure `lc3_check_bits()` returns indication that read has been
 *   made crossing the other bit plane.
 *
 *
 * Reference : Low Complexity Communication Codec (LC3)
 *             Bluetooth Specification v1.0
 *
 */

#ifndef __LC3_BITS_H
#define __LC3_BITS_H

#include "common.h"


/**
 * Bitstream mode
 */

enum lc3_bits_mode {
    LC3_BITS_MODE_READ,
    LC3_BITS_MODE_WRITE,
};

/**
 * Arithmetic coder symbol interval
 * The model split the interval in 17 symbols
 */

struct lc3_ac_symbol {
    uint16_t low   : 16;
    uint16_t range : 16;
};

struct lc3_ac_model {
    struct lc3_ac_symbol s[17];
};

/**
 * Bitstream context
 */

#define LC3_ACCU_BITS (int)(8 * sizeof(unsigned))

struct lc3_bits_accu {
    unsigned v;
    int n, nover;
};

#define LC3_AC_BITS (int)(24)

struct lc3_bits_ac {
    unsigned low, range;
    int cache, carry, carry_count;
    bool error;
};

struct lc3_bits_buffer {
    const uint8_t *start, *end;
    uint8_t *p_fw, *p_bw;
};

typedef struct lc3_bits {
    enum lc3_bits_mode mode;
    struct lc3_bits_ac ac;
    struct lc3_bits_accu accu;
    struct lc3_bits_buffer buffer;
} lc3_bits_t;


/**
 * Setup bitstream reading/writing
 * bits            Bitstream context
 * mode            Either READ or WRITE mode
 * buffer, len     Output buffer and length (in bytes)
 */
void lc3_setup_bits(lc3_bits_t *bits,
    enum lc3_bits_mode mode, void *buffer, int len);

/**
 * Return number of bits left in the bitstream
 * bits            Bitstream context
 * return          Number of bits left
 */
int lc3_get_bits_left(const lc3_bits_t *bits);

/**
 * Check if error occured on bitstream reading/writing
 * bits            Bitstream context
 * return          0: Ok  -1: Bitstream overflow or AC reading error
 */
int lc3_check_bits(const lc3_bits_t *bits);

/**
 * Put a bit
 * bits            Bitstream context
 * v               Bit value, 0 or 1
 */
static inline void lc3_put_bit(lc3_bits_t *bits, int v);

/**
 * Put from 1 to 32 bits
 * bits            Bitstream context
 * v, n            Value, in range 0 to 2^n - 1, and bits count (1 to 32)
 */
static inline void lc3_put_bits(lc3_bits_t *bits, unsigned v, int n);

/**
 * Put arithmetic coder symbol
 * bits            Bitstream context
 * model, s        Model distribution and symbol value
 */
static inline void lc3_put_symbol(lc3_bits_t *bits,
    const struct lc3_ac_model *model, unsigned s);

/**
 * Flush and terminate bitstream writing
 * bits            Bitstream context
 */
void lc3_flush_bits(lc3_bits_t *bits);

/**
 * Get a bit
 * bits            Bitstream context
 */
static inline int lc3_get_bit(lc3_bits_t *bits);

/**
 * Get from 1 to 32 bits
 * bits            Bitstream context
 * n               Number of bits to read (1 to 32)
 * return          The value read
 */
static inline unsigned lc3_get_bits(lc3_bits_t *bits,  int n);

/**
 * Get arithmetic coder symbol
 * bits            Bitstream context
 * model           Model distribution
 * return          The value read
 */
static inline unsigned lc3_get_symbol(lc3_bits_t *bits,
    const struct lc3_ac_model *model);



/* ----------------------------------------------------------------------------
 *  Inline implementations
 * -------------------------------------------------------------------------- */

void lc3_put_bits_generic(lc3_bits_t *bits, unsigned v, int n);
unsigned lc3_get_bits_generic(struct lc3_bits *bits, int n);

void lc3_ac_read_renorm(lc3_bits_t *bits);
void lc3_ac_write_renorm(lc3_bits_t *bits);


/**
 * Put a bit
 */
LC3_HOT static inline void lc3_put_bit(lc3_bits_t *bits, int v)
{
    lc3_put_bits(bits, v, 1);
}

/**
 * Put from 1 to 32 bits
 */
LC3_HOT static inline void lc3_put_bits(
    struct lc3_bits *bits, unsigned v, int n)
{
    struct lc3_bits_accu *accu = &bits->accu;

    if (accu->n + n <= LC3_ACCU_BITS) {
        accu->v |= v << accu->n;
        accu->n += n;
    } else {
        lc3_put_bits_generic(bits, v, n);
    }
}

/**
 * Get a bit
 */
LC3_HOT static inline int lc3_get_bit(lc3_bits_t *bits)
{
    return lc3_get_bits(bits, 1);
}

/**
 * Get from 1 to 32 bits
 */
LC3_HOT static inline unsigned lc3_get_bits(struct lc3_bits *bits, int n)
{
    struct lc3_bits_accu *accu = &bits->accu;

    if (accu->n + n <= LC3_ACCU_BITS) {
        int v = (accu->v >> accu->n) & ((1u << n) - 1);
        return (accu->n += n), v;
    }
    else {
        return lc3_get_bits_generic(bits, n);
    }
}

/**
 * Put arithmetic coder symbol
 */
LC3_HOT static inline void lc3_put_symbol(
    struct lc3_bits *bits, const struct lc3_ac_model *model, unsigned s)
{
    const struct lc3_ac_symbol *symbols = model->s;
    struct lc3_bits_ac *ac = &bits->ac;
    unsigned range = ac->range >> 10;

    ac->low += range * symbols[s].low;
    ac->range = range * symbols[s].range;

    ac->carry |= ac->low >> 24;
    ac->low &= 0xffffff;

    if (ac->range < 0x10000)
        lc3_ac_write_renorm(bits);
}

/**
 * Get arithmetic coder symbol
 */
LC3_HOT static inline unsigned lc3_get_symbol(
    lc3_bits_t *bits, const struct lc3_ac_model *model)
{
    const struct lc3_ac_symbol *symbols = model->s;
    struct lc3_bits_ac *ac = &bits->ac;

    unsigned range = (ac->range >> 10) & 0xffff;

    ac->error |= (ac->low >= (range << 10));
    if (ac->error)
        ac->low = 0;

    int s = 16;

    if (ac->low < range * symbols[s].low) {
        s >>= 1;
        s -= ac->low < range * symbols[s].low ? 4 : -4;
        s -= ac->low < range * symbols[s].low ? 2 : -2;
        s -= ac->low < range * symbols[s].low ? 1 : -1;
        s -= ac->low < range * symbols[s].low;
    }

    ac->low -= range * symbols[s].low;
    ac->range = range * symbols[s].range;

    if (ac->range < 0x10000)
        lc3_ac_read_renorm(bits);

    return s;
}

#endif /* __LC3_BITS_H */
