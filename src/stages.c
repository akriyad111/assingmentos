#define _GNU_SOURCE
#include "stages.h"
#include <errno.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

/* ----------------------------------------------------- fault injection etc. */

static stage_id_t g_fault_stage = STAGE_NONE;
static long       g_fault_after = -1;
static long       g_work = 0;

void stages_set_fault(stage_id_t id, long after) { g_fault_stage = id; g_fault_after = after; }
void stages_clear_fault(void)                    { g_fault_stage = STAGE_NONE; }
void stages_set_work(long iterations)            { g_work = iterations; }

static void maybe_crash(stage_id_t me, long handled)
{
    if (g_fault_stage == me && handled == g_fault_after) {
        fprintf(stderr, "[fault] stage %d killing itself after %ld messages\n", (int)me, handled);
        fflush(stderr);
        raise(SIGKILL);            /* no cleanup, no flush: a realistic crash */
    }
}

static void burn(long n)
{
    volatile unsigned long x = 1;
    for (long i = 0; i < n; i++) x = x * 1664525UL + 1013904223UL;
}

#define MAX_WARNINGS 10

/* ------------------------------------------------------------ stage 1: reader */

int stage_reader(const char *path, FILE *out, long resume_seq)
{
    FILE *f = fopen(path, "r");
    if (!f) {
        fprintf(stderr, "reader: cannot open '%s': %s\n", path, strerror(errno));
        return RC_IO;
    }

    char  *line = NULL;
    size_t cap = 0;
    ssize_t len;
    long seq = 0, run_lines = 0, valid = 0, bad = 0;
    int  rc = RC_OK;

    while ((len = getline(&line, &cap, f)) != -1) {
        seq++;
        if (seq <= resume_seq) continue;            /* already accounted for */
        run_lines++;

        record_t r;
        /* A NUL byte inside a line would silently truncate it: call it malformed. */
        int ok = memchr(line, '\0', (size_t)len) == NULL && parse_log_line(line, seq, &r) == 0;
        int w;
        if (ok) { w = wire_write_record(out, &r); valid++; }
        else {
            if (++bad <= MAX_WARNINGS)
                fprintf(stderr, "reader: line %ld is malformed, skipping\n", seq);
            else if (bad == MAX_WARNINGS + 1)
                fprintf(stderr, "reader: further malformed-line warnings suppressed\n");
            w = wire_write_malformed(out, seq);
        }
        if (w < 0) { rc = RC_DOWNSTREAM; goto done; }
        maybe_crash(STAGE_READER, run_lines);
    }
    if (ferror(f)) {
        fprintf(stderr, "reader: read error on '%s': %s\n", path, strerror(errno));
        rc = RC_IO;
        goto done;
    }
    if (wire_write_end(out, run_lines, valid, bad, valid) < 0 || fflush(out) != 0)
        rc = RC_DOWNSTREAM;

done:
    if (rc == RC_DOWNSTREAM)
        fprintf(stderr, "reader: downstream closed the pipe (%s)\n", strerror(errno));
    free(line);
    fclose(f);
    return rc;
}

/* ------------------------------------------------------------ stage 2: filter */

int stage_filter(FILE *in, FILE *out, unsigned mask)
{
    char *buf = NULL;
    size_t cap = 0;
    wire_msg_t m;
    long in_r = 0, in_m = 0, out_r = 0, handled = 0;
    int rc;

    for (;;) {
        int r = wire_read(in, &buf, &cap, &m);
        if (r == 0) {
            fprintf(stderr, "filter: upstream closed the pipe without an END marker "
                            "(reader died?)\n");
            rc = RC_UPSTREAM; break;
        }
        if (r < 0) {
            fprintf(stderr, "filter: protocol error: unparseable message on the pipe\n");
            rc = RC_INTEGRITY; break;
        }

        if (m.type == W_RECORD) {
            in_r++;
            burn(g_work);
            if (mask & LEVEL_MASK(m.rec.level)) {
                if (wire_write_record(out, &m.rec) < 0) { rc = RC_DOWNSTREAM; break; }
                out_r++;
            }
        } else if (m.type == W_MALFORMED) {
            in_m++;
            if (wire_write_malformed(out, m.seq) < 0) { rc = RC_DOWNSTREAM; break; }
        } else { /* W_END: verify what we received against what the reader claims */
            if (m.lines != m.valid + m.malformed || in_r != m.valid || in_m != m.malformed) {
                fprintf(stderr, "filter: integrity check failed: reader says %ld valid/%ld "
                        "malformed, received %ld/%ld\n", m.valid, m.malformed, in_r, in_m);
                rc = RC_INTEGRITY; break;
            }
            if (wire_write_end(out, m.lines, m.valid, m.malformed, out_r) < 0 || fflush(out) != 0)
                rc = RC_DOWNSTREAM;
            else
                rc = RC_OK;
            break;
        }
        maybe_crash(STAGE_FILTER, ++handled);
    }
    if (rc == RC_DOWNSTREAM)
        fprintf(stderr, "filter: downstream closed the pipe (%s)\n", strerror(errno));
    free(buf);
    return rc;
}

/* ------------------------------------------------------- stage 3: summarizer */

int stage_summarizer(FILE *in, const summary_t *base, unsigned mask,
                     const char *ckpt_path, long ckpt_every)
{
    summary_t s = *base;
    char *buf = NULL;
    size_t cap = 0;
    wire_msg_t m;
    long run_r = 0, run_m = 0, dups = 0, since_ckpt = 0, handled = 0;
    int rc;

    for (;;) {
        int r = wire_read(in, &buf, &cap, &m);
        if (r == 0) {
            fprintf(stderr, "summarizer: upstream closed the pipe without an END marker "
                            "(an earlier stage died?) - no report produced\n");
            rc = RC_UPSTREAM; break;
        }
        if (r < 0) {
            fprintf(stderr, "summarizer: protocol error: unparseable message on the pipe\n");
            rc = RC_INTEGRITY; break;
        }

        if (m.type == W_END) {
            if (m.lines != m.valid + m.malformed || m.passed != run_r || m.malformed != run_m) {
                fprintf(stderr, "summarizer: integrity check failed: filter says %ld kept/%ld "
                        "malformed, received %ld/%ld\n", m.passed, m.malformed, run_r, run_m);
                rc = RC_INTEGRITY; break;
            }
            /* Lines up to base->last_seq were accounted for by an earlier run. */
            summary_print(stdout, &s, base->last_seq + m.lines, mask);
            if (dups) fprintf(stderr, "summarizer: ignored %ld duplicate message(s)\n", dups);
            rc = fflush(stdout) == 0 ? RC_OK : RC_IO;
            break;
        }

        long seq = (m.type == W_RECORD) ? m.rec.seq : m.seq;
        if (m.type == W_RECORD) run_r++; else run_m++;

        if (seq <= s.last_seq) {            /* defensive: never count a line twice */
            dups++;
        } else {
            if (m.type == W_RECORD) summary_add_record(&s, &m.rec);
            else                    s.malformed++;
            s.last_seq = seq;
            since_ckpt++;
        }

        if (ckpt_path && since_ckpt >= ckpt_every) {
            if (summary_save(ckpt_path, &s) < 0)
                fprintf(stderr, "summarizer: warning: could not write checkpoint: %s\n",
                        strerror(errno));
            since_ckpt = 0;
        }
        maybe_crash(STAGE_SUMMARIZER, ++handled);
    }
    free(buf);
    return rc;
}

/* --------------------------------------------------------- single-process run */

int run_single(const char *path, unsigned mask)
{
    FILE *f = fopen(path, "r");
    if (!f) {
        fprintf(stderr, "single: cannot open '%s': %s\n", path, strerror(errno));
        return RC_IO;
    }
    summary_t s;
    summary_init(&s);
    char *line = NULL;
    size_t cap = 0;
    ssize_t len;
    long seq = 0;

    while ((len = getline(&line, &cap, f)) != -1) {
        seq++;
        record_t r;
        if (memchr(line, '\0', (size_t)len) != NULL || parse_log_line(line, seq, &r) != 0) {
            s.malformed++;
            continue;
        }
        burn(g_work);
        if (mask & LEVEL_MASK(r.level)) summary_add_record(&s, &r);
    }
    int rc = ferror(f) ? RC_IO : RC_OK;
    free(line);
    fclose(f);
    if (rc == RC_OK) { summary_print(stdout, &s, seq, mask); fflush(stdout); }
    return rc;
}
