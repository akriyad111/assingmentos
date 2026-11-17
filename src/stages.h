/*
 * stages.h - the three pipeline stages (reader -> filter -> summarizer), the
 *            single-process baseline, and fault injection for testing.
 */
#ifndef STAGES_H
#define STAGES_H

#include "summary.h"
#include <stdio.h>

/* Stage / process exit codes (also used as the child's exit status). */
enum {
    RC_OK         = 0,
    RC_IO         = 13,   /* cannot open/read the input file                    */
    RC_UPSTREAM   = 10,   /* upstream closed the pipe without an END marker     */
    RC_DOWNSTREAM = 11,   /* write failed (EPIPE: the next stage is gone)       */
    RC_INTEGRITY  = 12    /* protocol error or record counts do not add up      */
};

typedef enum { STAGE_NONE, STAGE_READER, STAGE_FILTER, STAGE_SUMMARIZER } stage_id_t;

/* Fault injection: stage <id> kills itself with SIGKILL after handling
 * <after> messages. Used to simulate a crashing process. */
void stages_set_fault(stage_id_t id, long after);
void stages_clear_fault(void);

/* Artificial per-record CPU cost (loop iterations) in the filter step. Used by
 * the benchmark to model an expensive stage. Default 0. */
void stages_set_work(long iterations);

/* Stage 1: read the log file, validate each line, emit records downstream.
 * Lines with seq <= resume_seq are skipped (already accounted for). */
int stage_reader(const char *path, FILE *out, long resume_seq);

/* Stage 2: forward only records whose level is in mask. */
int stage_filter(FILE *in, FILE *out, unsigned mask);

/* Stage 3: count records and print the report to stdout. If ckpt_path is not
 * NULL, a checkpoint is written every ckpt_every messages. */
int stage_summarizer(FILE *in, const summary_t *base, unsigned mask,
                     const char *ckpt_path, long ckpt_every);

/* Baseline: the same three steps in one process, no IPC. */
int run_single(const char *path, unsigned mask);

#endif
