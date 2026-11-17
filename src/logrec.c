#define _GNU_SOURCE
#include "logrec.h"
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>

static const char *LEVEL_NAMES[LV_COUNT] = {"DEBUG", "INFO", "WARN", "ERROR", "FATAL"};

const char *level_name(level_t l)
{
    return (l >= 0 && l < LV_COUNT) ? LEVEL_NAMES[l] : "?";
}

int level_from_name(const char *s, size_t n, level_t *out)
{
    for (int i = 0; i < LV_COUNT; i++) {
        if (strlen(LEVEL_NAMES[i]) == n && memcmp(s, LEVEL_NAMES[i], n) == 0) {
            *out = (level_t)i;
            return 1;
        }
    }
    return 0;
}

static int is_digit(char c) { return c >= '0' && c <= '9'; }
static int num2(const char *p) { return (p[0] - '0') * 10 + (p[1] - '0'); }

/* p must point at >= 19 readable bytes. */
static int valid_timestamp(const char *p)
{
    static const char fmt[] = "dddd-dd-dd dd:dd:dd";
    for (int i = 0; i < TS_LEN; i++) {
        if (fmt[i] == 'd') { if (!is_digit(p[i])) return 0; }
        else if (p[i] != fmt[i]) return 0;
    }
    int mo = num2(p + 5), d = num2(p + 8);
    int h = num2(p + 11), mi = num2(p + 14), s = num2(p + 17);
    return mo >= 1 && mo <= 12 && d >= 1 && d <= 31 && h < 24 && mi < 60 && s < 61;
}

int parse_log_line(const char *line, long seq, record_t *r)
{
    size_t n = strlen(line);
    while (n > 0 && (line[n - 1] == '\n' || line[n - 1] == '\r')) n--;

    /* timestamp(19) + ' ' + shortest level(4) + ' ' + >=1 char of message */
    if (n < TS_LEN + 1 + 4 + 1 + 1) return -1;
    if (!valid_timestamp(line) || line[TS_LEN] != ' ') return -1;

    const char *lv = line + TS_LEN + 1;
    const char *sp = memchr(lv, ' ', n - (size_t)(lv - line));
    if (!sp) return -1;

    level_t level;
    if (!level_from_name(lv, (size_t)(sp - lv), &level)) return -1;

    const char *msg = sp + 1;
    size_t mlen = n - (size_t)(msg - line);
    if (mlen == 0 || mlen >= MSG_MAX) return -1;
    for (size_t i = 0; i < mlen; i++) {
        unsigned char c = (unsigned char)msg[i];
        if (c < 0x20 && c != '\t') return -1;       /* control characters */
    }

    r->seq = seq;
    memcpy(r->ts, line, TS_LEN);
    r->ts[TS_LEN] = '\0';
    r->level = level;
    memcpy(r->msg, msg, mlen);
    r->msg[mlen] = '\0';
    return 0;
}

/* ---------------------------------------------------------------- writers */

int wire_write_record(FILE *out, const record_t *r)
{
    return fprintf(out, "R\t%ld\t%s\t%s\t%s\n", r->seq, r->ts,
                   level_name(r->level), r->msg) < 0 ? -1 : 0;
}

int wire_write_malformed(FILE *out, long seq)
{
    return fprintf(out, "M\t%ld\n", seq) < 0 ? -1 : 0;
}

int wire_write_end(FILE *out, long lines, long valid, long malformed, long passed)
{
    return fprintf(out, "E\t%ld\t%ld\t%ld\t%ld\n", lines, valid, malformed, passed) < 0 ? -1 : 0;
}

/* ----------------------------------------------------------------- reader */

static int parse_wire(char *line, wire_msg_t *m)
{
    if (line[0] == '\0' || line[1] != '\t') return 0;
    char *p = line + 2, *e;

    switch (line[0]) {
    case 'R': {
        m->type = W_RECORD;
        m->rec.seq = strtol(p, &e, 10);
        if (e == p || *e != '\t') return 0;
        p = e + 1;
        if (strnlen(p, TS_LEN + 1) < TS_LEN + 1 || p[TS_LEN] != '\t') return 0;
        memcpy(m->rec.ts, p, TS_LEN);
        m->rec.ts[TS_LEN] = '\0';
        p += TS_LEN + 1;
        char *t = strchr(p, '\t');
        if (!t || !level_from_name(p, (size_t)(t - p), &m->rec.level)) return 0;
        p = t + 1;
        size_t mlen = strlen(p);
        if (mlen == 0 || mlen >= MSG_MAX) return 0;
        memcpy(m->rec.msg, p, mlen + 1);
        return 1;
    }
    case 'M':
        m->type = W_MALFORMED;
        m->seq = strtol(p, &e, 10);
        return e != p && *e == '\0';
    case 'E':
        m->type = W_END;
        return sscanf(p, "%ld %ld %ld %ld", &m->lines, &m->valid,
                      &m->malformed, &m->passed) == 4;
    default:
        return 0;
    }
}

int wire_read(FILE *in, char **buf, size_t *cap, wire_msg_t *m)
{
    ssize_t n = getline(buf, cap, in);
    if (n <= 0) return 0;                       /* EOF or read error */
    if ((*buf)[n - 1] != '\n') return 0;        /* cut off mid-message: writer died */
    (*buf)[n - 1] = '\0';
    return parse_wire(*buf, m) ? 1 : -1;
}
