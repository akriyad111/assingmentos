#define _GNU_SOURCE
#include "summary.h"
#include <string.h>
#include <unistd.h>

void summary_init(summary_t *s) { memset(s, 0, sizeof *s); }

void summary_add_record(summary_t *s, const record_t *r)
{
    s->passed++;
    s->by_level[r->level]++;
    if (!s->first_ts[0] || strcmp(r->ts, s->first_ts) < 0) strcpy(s->first_ts, r->ts);
    if (!s->last_ts[0]  || strcmp(r->ts, s->last_ts)  > 0) strcpy(s->last_ts,  r->ts);
}

/* Timestamps contain a space, so store them with 'T' to keep fscanf simple. */
static void ts_to_token(const char *ts, char *tok)
{
    if (!ts[0]) { strcpy(tok, "-"); return; }
    strcpy(tok, ts);
    tok[10] = 'T';
}

static void token_to_ts(const char *tok, char *ts)
{
    if (strcmp(tok, "-") == 0) { ts[0] = '\0'; return; }
    strcpy(ts, tok);
    ts[10] = ' ';
}

int summary_save(const char *path, const summary_t *s)
{
    char tmp[4096], a[TS_LEN + 2], b[TS_LEN + 2];
    if (snprintf(tmp, sizeof tmp, "%s.tmp", path) >= (int)sizeof tmp) return -1;

    FILE *f = fopen(tmp, "w");
    if (!f) return -1;
    ts_to_token(s->first_ts, a);
    ts_to_token(s->last_ts, b);
    fprintf(f, "CKPT1 %ld %ld %ld", s->last_seq, s->malformed, s->passed);
    for (int i = 0; i < LV_COUNT; i++) fprintf(f, " %ld", s->by_level[i]);
    fprintf(f, " %s %s\n", a, b);

    int ok = (fflush(f) == 0) && (fsync(fileno(f)) == 0);
    ok = (fclose(f) == 0) && ok;
    if (!ok) { unlink(tmp); return -1; }
    return rename(tmp, path) == 0 ? 0 : -1;      /* rename() is atomic on POSIX */
}

int summary_load(const char *path, summary_t *s)
{
    summary_init(s);
    FILE *f = fopen(path, "r");
    if (!f) return 0;

    char magic[8], a[32], b[32];
    summary_t t;
    summary_init(&t);
    int n = fscanf(f, "%7s %ld %ld %ld %ld %ld %ld %ld %ld %31s %31s", magic,
                   &t.last_seq, &t.malformed, &t.passed,
                   &t.by_level[0], &t.by_level[1], &t.by_level[2],
                   &t.by_level[3], &t.by_level[4], a, b);
    fclose(f);
    if (n != 11 || strcmp(magic, "CKPT1") != 0) return 0;   /* corrupt: start over */
    token_to_ts(a, t.first_ts);
    token_to_ts(b, t.last_ts);
    *s = t;
    return 1;
}

void summary_print(FILE *out, const summary_t *s, long total_lines, unsigned mask)
{
    long valid = total_lines - s->malformed;
    fprintf(out, "=== Log Summary ===\n");
    fprintf(out, "Lines read             : %ld\n", total_lines);
    fprintf(out, "  Valid records        : %ld\n", valid);
    fprintf(out, "  Malformed (skipped)  : %ld\n", s->malformed);
    fprintf(out, "Records kept by filter : %ld\n", s->passed);
    fprintf(out, "Records filtered out   : %ld\n", valid - s->passed);
    fprintf(out, "Counts by level (kept records):\n");
    for (int i = 0; i < LV_COUNT; i++)
        if (mask & LEVEL_MASK(i))
            fprintf(out, "  %-6s : %ld\n", level_name((level_t)i), s->by_level[i]);
    fprintf(out, "Earliest timestamp     : %s\n", s->first_ts[0] ? s->first_ts : "(none)");
    fprintf(out, "Latest timestamp       : %s\n", s->last_ts[0]  ? s->last_ts  : "(none)");
}
