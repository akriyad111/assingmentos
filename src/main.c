/*
 * logpipe - log-processing pipeline built from cooperating processes.
 *
 *   reader --pipe1--> filter --pipe2--> summarizer --> stdout
 *
 * The parent process is a supervisor: it creates the pipes, forks the three
 * stages, closes every unused pipe end, and waits for all of them. With
 * --restart it relaunches the pipeline after a failure, resuming from the
 * summarizer's last checkpoint so no record is lost or counted twice.
 */
#define _GNU_SOURCE
#include "stages.h"
#include <errno.h>
#include <signal.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

typedef struct {
    const char *path;
    int         single;
    unsigned    mask;
    int         restart;
    int         max_retries;
    const char *ckpt_path;
    long        ckpt_every;
    stage_id_t  fault_stage;
    long        fault_after;
    long        work;
    int         timing;
} options_t;

static const char *STAGE_NAMES[] = {"?", "reader", "filter", "summarizer"};

static void usage(const char *argv0)
{
    fprintf(stderr,
        "Usage: %s [options] <logfile>\n"
        "  --mode pipeline|single   multi-process pipeline (default) or one process\n"
        "  --levels A,B,...         levels to keep (default WARN,ERROR,FATAL)\n"
        "  --restart                restart the pipeline after a stage failure,\n"
        "                           resuming from the last checkpoint (max 3 retries)\n"
        "  --ckpt FILE              checkpoint file (default <logfile>.ckpt)\n"
        "  --ckpt-every N           checkpoint every N messages (default 1000)\n"
        "  --crash STAGE:N          fault injection: STAGE (reader|filter|summarizer)\n"
        "                           kills itself after N messages (first attempt only)\n"
        "  --work N                 extra CPU loop iterations per record in the filter step\n"
        "  --time                   print wall-clock time to stderr\n", argv0);
}

static int parse_levels(const char *s, unsigned *mask)
{
    char *copy = strdup(s), *save = NULL;
    unsigned m = 0;
    if (!copy) return -1;
    for (char *tok = strtok_r(copy, ",", &save); tok; tok = strtok_r(NULL, ",", &save)) {
        level_t l;
        if (!level_from_name(tok, strlen(tok), &l)) { free(copy); return -1; }
        m |= LEVEL_MASK(l);
    }
    free(copy);
    if (!m) return -1;
    *mask = m;
    return 0;
}

static int parse_args(int argc, char **argv, options_t *o)
{
    memset(o, 0, sizeof *o);
    o->mask = DEFAULT_MASK;
    o->max_retries = 3;
    o->ckpt_every = 1000;

    for (int i = 1; i < argc; i++) {
        const char *a = argv[i];
        const char *v = (i + 1 < argc) ? argv[i + 1] : NULL;
        if      (!strcmp(a, "--mode") && v) {
            if (!strcmp(v, "single")) o->single = 1;
            else if (strcmp(v, "pipeline")) return -1;
            i++;
        }
        else if (!strcmp(a, "--levels") && v)     { if (parse_levels(v, &o->mask)) return -1; i++; }
        else if (!strcmp(a, "--restart"))         o->restart = 1;
        else if (!strcmp(a, "--ckpt") && v)       { o->ckpt_path = v; i++; }
        else if (!strcmp(a, "--ckpt-every") && v) { o->ckpt_every = atol(v); i++; if (o->ckpt_every < 1) return -1; }
        else if (!strcmp(a, "--work") && v)       { o->work = atol(v); i++; }
        else if (!strcmp(a, "--time"))            o->timing = 1;
        else if (!strcmp(a, "--crash") && v) {
            char *colon = strchr(v, ':');
            if (!colon) return -1;
            size_t n = (size_t)(colon - v);
            if      (n == 6  && !strncmp(v, "reader", n))     o->fault_stage = STAGE_READER;
            else if (n == 6  && !strncmp(v, "filter", n))     o->fault_stage = STAGE_FILTER;
            else if (n == 10 && !strncmp(v, "summarizer", n)) o->fault_stage = STAGE_SUMMARIZER;
            else return -1;
            o->fault_after = atol(colon + 1);
            if (o->fault_after < 1) return -1;
            i++;
        }
        else if (a[0] == '-' && a[1] == '-') return -1;
        else if (!o->path) o->path = a;
        else return -1;
    }
    if (!o->path) return -1;
    if (o->restart && o->single) return -1;
    return 0;
}

static double now_ms(void)
{
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000.0 + t.tv_nsec / 1e6;
}

static void report_status(stage_id_t id, pid_t pid, int status)
{
    if (WIFEXITED(status))
        fprintf(stderr, "[supervisor] %-10s (pid %d) exited with code %d\n",
                STAGE_NAMES[id], (int)pid, WEXITSTATUS(status));
    else if (WIFSIGNALED(status))
        fprintf(stderr, "[supervisor] %-10s (pid %d) killed by signal %d\n",
                STAGE_NAMES[id], (int)pid, WTERMSIG(status));
}

/* Close both ends of a pipe in the parent / unused ends in a child. */
static void close_fd(int fd) { if (fd >= 0) close(fd); }

/* Run the three stages once. Returns 0 if every stage exited with status 0. */
static int run_pipeline_once(const options_t *o, const summary_t *base, int inject_fault)
{
    int p1[2], p2[2];
    if (pipe(p1) < 0 || pipe(p2) < 0) { perror("pipe"); return -1; }

    fflush(stdout);                         /* children must not inherit buffered output */
    fflush(stderr);

    pid_t pids[4] = {0};
    int started = 0;

    for (stage_id_t id = STAGE_READER; id <= STAGE_SUMMARIZER; id++) {
        pid_t pid = fork();
        if (pid < 0) { perror("fork"); break; }
        if (pid > 0) { pids[id] = pid; started++; continue; }

        /* ---- child: keep only the pipe ends this stage needs ---- */
        FILE *in = NULL, *out = NULL;
        if (id == STAGE_READER) {
            close_fd(p1[0]); close_fd(p2[0]); close_fd(p2[1]);
            out = fdopen(p1[1], "w");
        } else if (id == STAGE_FILTER) {
            close_fd(p1[1]); close_fd(p2[0]);
            in  = fdopen(p1[0], "r");
            out = fdopen(p2[1], "w");
        } else {
            close_fd(p1[0]); close_fd(p1[1]); close_fd(p2[1]);
            in  = fdopen(p2[0], "r");
        }
        if ((id != STAGE_SUMMARIZER && !out) || (id != STAGE_READER && !in)) _exit(RC_IO);   /* fdopen failed */
        if (in)  setvbuf(in,  NULL, _IOFBF, 1 << 16);
        if (out) setvbuf(out, NULL, _IOFBF, 1 << 16);

        if (inject_fault && o->fault_stage == id) stages_set_fault(id, o->fault_after);

        int rc;
        if      (id == STAGE_READER)  rc = stage_reader(o->path, out, base->last_seq);
        else if (id == STAGE_FILTER)  rc = stage_filter(in, out, o->mask);
        else rc = stage_summarizer(in, base, o->mask,
                                   o->restart ? o->ckpt_path : NULL, o->ckpt_every);
        if (out) fclose(out);               /* closing the write end delivers EOF downstream */
        if (in)  fclose(in);
        fflush(stdout);
        fflush(stderr);
        _exit(rc);
    }

    /* Parent closes all pipe ends: otherwise a child would never see EOF. */
    close(p1[0]); close(p1[1]); close(p2[0]); close(p2[1]);

    int ok = (started == 3);
    for (int n = 0; n < started; n++) {
        int status;
        pid_t pid = wait(&status);
        if (pid < 0) { if (errno == EINTR) { n--; continue; } break; }
        stage_id_t id = STAGE_READER;
        for (stage_id_t k = STAGE_READER; k <= STAGE_SUMMARIZER; k++) if (pids[k] == pid) id = k;
        if (!(WIFEXITED(status) && WEXITSTATUS(status) == 0)) {
            report_status(id, pid, status);
            ok = 0;
        }
    }
    return ok ? 0 : -1;
}

static int run_supervised(const options_t *o)
{
    char default_ckpt[4096];
    options_t opt = *o;
    if (opt.restart && !opt.ckpt_path) {
        snprintf(default_ckpt, sizeof default_ckpt, "%s.ckpt", opt.path);
        opt.ckpt_path = default_ckpt;
    }

    summary_t base;
    summary_init(&base);
    if (opt.restart) { unlink(opt.ckpt_path); }          /* always start a fresh run */

    int attempts = opt.restart ? opt.max_retries + 1 : 1;
    for (int attempt = 0; attempt < attempts; attempt++) {
        if (attempt > 0) {
            summary_load(opt.ckpt_path, &base);
            fprintf(stderr, "[supervisor] restart %d/%d: resuming after line %ld "
                            "(checkpoint: %ld malformed, %ld kept)\n",
                    attempt, opt.max_retries, base.last_seq, base.malformed, base.passed);
        }
        if (run_pipeline_once(&opt, &base, attempt == 0) == 0) {
            if (opt.restart) { unlink(opt.ckpt_path); }
            return 0;
        }
        fprintf(stderr, "[supervisor] pipeline attempt %d failed\n", attempt + 1);
    }
    if (opt.restart) fprintf(stderr, "[supervisor] giving up after %d restarts\n", opt.max_retries);
    return 1;
}

int main(int argc, char **argv)
{
    options_t o;
    if (parse_args(argc, argv, &o) < 0) { usage(argv[0]); return 2; }

    /* A write to a pipe whose reader died must return EPIPE, not kill us. */
    signal(SIGPIPE, SIG_IGN);

    stages_set_work(o.work);
    double t0 = now_ms();
    int rc;
    if (o.single) rc = run_single(o.path, o.mask) == RC_OK ? 0 : 1;
    else          rc = run_supervised(&o);
    if (o.timing) fprintf(stderr, "TIME_MS %.3f\n", now_ms() - t0);
    return rc;
}
