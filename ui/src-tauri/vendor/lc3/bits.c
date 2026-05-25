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

#include "bits.h"
#include "common.h"


/* ----------------------------------------------------------------------------
 *  Common
 * -------------------------------------------------------------------------- */

static inline int ac_get(struct lc3_bits_buffer *);
static inline void accu_load(struct lc3_bits_accu *, struct lc3_bits_buffer *);

/**
 * Arithmetic coder return range bits
 * ac              Arithmetic coder
 * return          1 + log2(ac->range)
 */
static int ac_get_range_bits(const struct lc3_bits_ac *ac)
{
    int nbits = 0;

    for (unsigned r = ac->range; r; r >>= 1, nbits++);

    return nbits;
}

/**
 * Arithmetic coder return pending bits
 * ac              Arithmetic coder
 * return          Pending bits
 */
static int ac_get_pending_bits(const struct lc3_bits_ac *ac)
{
    return 26 - ac_get_range_bits(ac) +
        ((ac->cache >= 0) + ac->carry_count) * 8;
}

/**
 * Return number of bits left in the bitstream
 * bits            Bitstream context
 * return          >= 0: Number of bits left  < 0: Overflow
 */
static int get_bits_left(const struct lc3_bits *bits)
{
    const struct lc3_bits_buffer *buffer = &bits->buffer;
    const struct lc3_bits_accu *accu = &bits->accu;
    const struct lc3_bits_ac *ac = &bits->ac;

    uintptr_t end = (uintptr_t)buffer->p_bw +
        (bits->mode == LC3_BITS_MODE_READ ? LC3_ACCU_BITS/8 : 0);

    uintptr_t start = (uintptr_t)buffer->p_fw -
        (bits->mode == LC3_BITS_MODE_READ ? LC3_AC_BITS/8 : 0);

    int n = end > start ? (int)(end - start) : -(int)(start - end);

    return 8 * n - (accu->n + accu->nover + ac_get_pending_bits(ac));
}

/**
 * Setup bitstream writing
 */
void lc3_setup_bits(struct lc3_bits *bits,
    enum lc3_bits_mode mode, void *buffer, int len)
{
    *bits = (struct lc3_bits){
        .mode = mode,
        .accu = {
            .n = mode == LC3_BITS_MODE_READ ? LC3_ACCU_BITS : 0,
        },
        .ac = {
            .range = 0xffffff,
            .cache = -1
        },
        .buffer = {
            .start = (uint8_t *)buffer, .end  = (uint8_t *)buffer + len,
            .p_fw  = (uint8_t *)buffer, .p_bw = (uint8_t *)buffer + len,
        }
    };

    if (mode == LC3_BITS_MODE_READ) {
        struct lc3_bits_ac *ac = &bits->ac;
        struct lc3_bits_accu *accu = &bits->accu;
        struct lc3_bits_buffer *buffer = &bits->buffer;

        ac->low  = ac_get(buffer) << 16;
        ac->low |= ac_get(buffer) <<  8;
        ac->low |= ac_get(buffer);

        accu_load(accu, buffer);
    }
}

/**
 * Return number of bits left in the bitstream
 */
int lc3_get_bits_left(const struct lc3_bits *bits)
{
    return LC3_MAX(get_bits_left(bits), 0);
}

/**
 * Return number of bits left in the bitstream
 */
int lc3_check_bits(const struct lc3_bits *bits)
{
    const struct lc3_bits_ac *ac = &bits->ac;

    return -(get_bits_left(bits) < 0 || ac->error);
}


/* ----------------------------------------------------------------------------
 *  Writing
 * -------------------------------------------------------------------------- */

/**
 * Flush the bits accumulator
 * accu            Bitstream accumulator
 * buffer          Bitstream buffer
 */
static inline void accu_flush(
    struct lc3_bits_accu *accu, struct lc3_bits_buffer *buffer)
{
    int nbytes = LC3_MIN(accu->n >> 3,
        LC3_MAX(buffer->p_bw - buffer->p_fw, 0));

    accu->n -= 8 * nbytes;

    for ( ; nbytes; accu->v >>= 8, nbytes--)
        *(--buffer->p_bw) = accu->v & 0xff;

    if (accu->n >= 8)
        accu->n = 0;
}

/**
 * Arithmetic coder put byte
 * buffer          Bitstream buffer
 * byte            Byte to output
 */
static inline void ac_put(struct lc3_bits_buffer *buffer, int byte)
{
    if (buffer->p_fw < buffer->end)
        *(buffer->p_fw++) = byte;
}

/**
 * Arithmetic coder range shift
 * ac              Arithmetic coder
 * buffer          Bitstream buffer
 */
LC3_HOT static inline void ac_shift(
    struct lc3_bits_ac *ac, struct lc3_bits_buffer *buffer)
{
    if (ac->low < 0xff0000 || ac->carry)
    {
        if (ac->cache >= 0)
            ac_put(buffer, ac->cache + ac->carry);

        for ( ; ac->carry_count > 0; ac->carry_count--)
            ac_put(buffer, ac->carry ? 0x00 : 0xff);

         ac->cache = ac->low >> 16;
         ac->carry = 0;
    }
    else
         ac->carry_count++;

    ac->low = (ac->low << 8) & 0xffffff;
}

/**
 * Arithmetic coder termination
 * ac              Arithmetic coder
 * buffer          Bitstream buffer
 * end_val/nbits   End value and count of bits to terminate (1 to 8)
 */
static void ac_terminate(struct lc3_bits_ac *ac,
    struct lc3_bits_buffer *buffer)
{
    int nbits = 25 - ac_get_range_bits(ac);
    unsigned mask = 0xffffff >> nbits;
    unsigned val  = ac->low + mask;
    unsigned high = ac->low + ac->range;

    bool over_val  = val  >> 24;
    bool over_high = high >> 24;

    val  = (val  & 0xffffff) & ~mask;
    high = (high & 0xffffff);

    if (over_val == over_high) {

        if (val + mask >= high) {
            nbits++;
            mask >>= 1;
            val = ((ac->low + mask) & 0xffffff) & ~mask;
        }

        ac->carry |= val < ac->low;
    }

    ac->low = val;

    for (; nbits > 8; nbits -= 8)
        ac_shift(ac, buffer);
    ac_shift(ac, buffer);

    int end_val = ac->cache >> (8 - nbits);

    if (ac->carry_count) {
        ac_put(buffer, ac->cache);
        for ( ; ac->carry_count > 1; ac->carry_count--)
            ac_put(buffer, 0xff);

        end_val = nbits < 8 ? 0 : 0xff;
    }

    if (buffer->p_fw < buffer->end) {
        *buffer->p_fw &= 0xff >> nbits;
        *buffer->p_fw |= end_val << (8 - nbits);
    }
}

/**
 * Flush and terminate bitstream
 */
void lc3_flush_bits(struct lc3_bits *bits)
{
    struct lc3_bits_ac *ac = &bits->ac;
    struct lc3_bits_accu *accu = &bits->accu;
    struct lc3_bits_buffer *buffer = &bits->buffer;

    int nleft = buffer->p_bw - buffer->p_fw;
    for (int n = 8 * nleft - accu->n; n > 0; n -= 32)
        lc3_put_bits(bits, 0, LC3_MIN(n, 32));

    accu_flush(accu, buffer);

    ac_terminate(ac, buffer);
}

/**
 * Write from 1 to 32 bits,
 * exceeding the capacity of the accumulator
 */
LC3_HOT void lc3_put_bits_generic(struct lc3_bits *bits, unsigned v, int n)
{
    struct lc3_bits_accu *accu = &bits->accu;

    /* --- Fulfill accumulator and flush -- */

    int n1 = LC3_MIN(LC3_ACCU_BITS - accu->n, n);
    if (n1) {
        accu->v |= v << accu->n;
        accu->n = LC3_ACCU_BITS;
    }

    accu_flush(accu, &bits->buffer);

    /* --- Accumulate remaining bits -- */

    accu->v = v >> n1;
    accu->n = n - n1;
}

/**
 * Arithmetic coder renormalization
 */
LC3_HOT void lc3_ac_write_renorm(struct lc3_bits *bits)
{
    struct lc3_bits_ac *ac = &bits->ac;

    for ( ; ac->range < 0x10000; ac->range <<= 8)
        ac_shift(ac, &bits->buffer);
}


/* ----------------------------------------------------------------------------
 *  Reading
 * -------------------------------------------------------------------------- */

/**
 * Arithmetic coder get byte
 * buffer          Bitstream buffer
 * return          Byte read, 0 on overflow
 */
static inline int ac_get(struct lc3_bits_buffer *buffer)
{
    return buffer->p_fw < buffer->end ? *(buffer->p_fw++) : 0;
}

/**
 * Load the accumulator
 * accu            Bitstream accumulator
 * buffer          Bitstream buffer
 */
static inline void accu_load(struct lc3_bits_accu *accu,
    struct lc3_bits_buffer *buffer)
{
    int nbytes = LC3_MIN(accu->n >> 3, buffer->p_bw - buffer->start);

    accu->n -= 8 * nbytes;

    for ( ; nbytes; nbytes--) {
        accu->v >>= 8;
        accu->v |= (unsigned)*(--buffer->p_bw) << (LC3_ACCU_BITS - 8);
    }

    if (accu->n >= 8) {
        accu->nover = LC3_MIN(accu->nover + accu->n, LC3_ACCU_BITS);
        accu->v >>= accu->n;
        accu->n = 0;
    }
}

/**
 * Read from 1 to 32 bits,
 * exceeding the capacity of the accumulator
 */
LC3_HOT unsigned lc3_get_bits_generic(struct lc3_bits *bits, int n)
{
    struct lc3_bits_accu *accu = &bits->accu;
    struct lc3_bits_buffer *buffer = &bits->buffer;

    /* --- Fulfill accumulator and read -- */

    accu_load(accu, buffer);

    int n1 = LC3_MIN(LC3_ACCU_BITS - accu->n, n);
    unsigned v = (accu->v >> accu->n) & ((1u << n1) - 1);
    accu->n += n1;

    /* --- Second round --- */

    int n2 = n - n1;

    if (n2) {
        accu_load(accu, buffer);

        v |= ((accu->v >> accu->n) & ((1u << n2) - 1)) << n1;
        accu->n += n2;
    }

    return v;
}

/**
 * Arithmetic coder renormalization
 */
LC3_HOT void lc3_ac_read_renorm(struct lc3_bits *bits)
{
    struct lc3_bits_ac *ac = &bits->ac;

    for ( ; ac->range < 0x10000; ac->range <<= 8)
        ac->low = ((ac->low << 8) | ac_get(&bits->buffer)) & 0xffffff;
}
