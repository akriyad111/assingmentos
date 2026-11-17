/*
 * summary.h - the running summary (the final stage's state), its checkpoint
 *             file, and the report printer.
 */
#ifndef SUMMARY_H
#define SUMMARY_H

#include "logrec.h"
#include <stdio.h>

typedef struct {
    long last_seq;              /* highest line number fully accounted for      */
    long malformed;             /* malformed lines seen up to last_seq          */
    long passed;                /* valid records that survived the filter       */
    long by_level[LV_COUNT];    /* per-level counts of surviving records        */
    char first_ts[TS_LEN + 1];  /* earliest timestamp among surviving records   */
    char last_ts[TS_LEN + 1];   /* latest timestamp among surviving records     */
} summary_t;

#define LEVEL_MASK(l) (1u << (l))
#define DEFAULT_MASK  (LEVEL_MASK(LV_WARN) | LEVEL_MASK(LV_ERROR) | LEVEL_MASK(LV_FATAL))

void summary_init(summary_t *s);
void summary_add_record(summary_t *s, const record_t *r);

/* Atomic checkpoint: write temp file, fsync, rename over the real one.
 * Returns 0 on success, -1 on error. */
int  summary_save(const char *path, const summary_t *s);
/* Returns 1 if a valid checkpoint was loaded, 0 otherwise (s is reset). */
int  summary_load(const char *path, summary_t *s);

/* total_lines = number of lines in the whole input file. */
void summary_print(FILE *out, const summary_t *s, long total_lines, unsigned mask);

#endif
