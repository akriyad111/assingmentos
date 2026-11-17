/*
 * logrec.h - log record type, line parser and the wire format used between
 *            pipeline stages.
 *
 * Wire format (one message per line, fields separated by TAB):
 *
 *   R <seq> <timestamp> <LEVEL> <message>   a valid log record
 *   M <seq>                                 a malformed input line (skipped)
 *   E <lines> <valid> <malformed> <passed>  end-of-stream marker + counts
 *
 * <seq> is the 1-based line number in the original log file, so it is stable
 * across restarts. The final "E" message lets a downstream stage tell a clean
 * end of stream apart from an upstream process that died mid-stream.
 */
#ifndef LOGREC_H
#define LOGREC_H

#include <stddef.h>
#include <stdio.h>

#define MSG_MAX 1024
#define TS_LEN  19              /* "YYYY-MM-DD HH:MM:SS" */

typedef enum { LV_DEBUG, LV_INFO, LV_WARN, LV_ERROR, LV_FATAL, LV_COUNT } level_t;

typedef struct {
    long    seq;
    char    ts[TS_LEN + 1];
    level_t level;
    char    msg[MSG_MAX];
} record_t;

typedef enum { W_RECORD, W_MALFORMED, W_END } wire_type_t;

typedef struct {
    wire_type_t type;
    record_t    rec;                 /* W_RECORD */
    long        seq;                 /* W_MALFORMED */
    long        lines, valid, malformed, passed;   /* W_END */
} wire_msg_t;

const char *level_name(level_t l);
int         level_from_name(const char *s, size_t n, level_t *out);

/* Parse "YYYY-MM-DD HH:MM:SS LEVEL message". Returns 0 on success, -1 if the
 * line is malformed. */
int parse_log_line(const char *line, long seq, record_t *r);

/* Writers return 0 on success, -1 on I/O error (e.g. EPIPE). */
int wire_write_record(FILE *out, const record_t *r);
int wire_write_malformed(FILE *out, long seq);
int wire_write_end(FILE *out, long lines, long valid, long malformed, long passed);

/* Reader returns: 1 = message read, 0 = EOF / truncated stream (no complete
 * message), -1 = protocol error (garbage on the pipe). buf/cap are a
 * getline() scratch buffer owned by the caller. */
int wire_read(FILE *in, char **buf, size_t *cap, wire_msg_t *m);

#endif
