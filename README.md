# logpipe - Interprocess Communication Through a Log-Processing Pipeline

A log-processing system built from three cooperating **processes** that talk
through **anonymous pipes**:

```
 log file --> [ reader ] --pipe 1--> [ filter ] --pipe 2--> [ summarizer ] --> report (stdout)
              parse + validate       keep selected levels    count by level
```

A parent **supervisor** process creates the pipes, `fork()`s the stages, closes
every unused pipe end, reaps the children with `wait()` and (optionally)
restarts the pipeline after a failure without losing or duplicating records.
A single-process version (`--mode single`) is included for comparison.

## Requirements

* A POSIX system: **Linux or macOS** (uses `fork`, `pipe`, `wait`, `fsync`).
  On Windows use **WSL** (Ubuntu); native Windows has no `fork()`.
* `gcc` or `clang`, and `make`
* `python3` (log generator, benchmark; the report script also needs `reportlab` and `matplotlib`)

## Build

```
make            # produces ./logpipe
```

## Usage

```
./logpipe [options] <logfile>

  --mode pipeline|single   multi-process pipeline (default) or one process
  --levels A,B,...         levels to keep (default WARN,ERROR,FATAL)
  --restart                restart the pipeline after a stage failure, resuming
                           from the last checkpoint (max 3 retries)
  --ckpt FILE              checkpoint file (default <logfile>.ckpt)
  --ckpt-every N           checkpoint every N messages (default 1000)
  --crash STAGE:N          fault injection: STAGE (reader|filter|summarizer)
                           kills itself with SIGKILL after N messages
  --work N                 extra CPU loop iterations per record in the filter step
  --time                   print wall-clock milliseconds to stderr
```

Log line format: `YYYY-MM-DD HH:MM:SS LEVEL message`, LEVEL one of
`DEBUG INFO WARN ERROR FATAL`. Anything else (bad date, unknown level, empty
message, blank line, control characters, message >= 1024 bytes, NUL byte) is
**malformed**: it is counted, reported on stderr, and skipped.

### Examples

```
./logpipe data/sample_normal.log                       # pipeline
./logpipe --mode single data/sample_normal.log         # same report, one process
./logpipe data/sample_malformed.log                    # malformed entries
./logpipe --levels ERROR,FATAL data/sample_generated.log
./logpipe --crash filter:50 data/sample_generated.log  # a stage dies: clean error, no hang
./logpipe --restart --ckpt-every 20 --crash summarizer:30 data/sample_generated.log   # recovers
```

Exit status: `0` success, `1` pipeline failed, `2` bad command line. Individual
stage codes: 10 upstream closed without END marker, 11 downstream pipe broken
(EPIPE), 12 protocol/integrity error, 13 input file I/O error.

## Wire format (between processes)

One text message per line, TAB-separated:

| Message | Meaning |
|---|---|
| `R seq timestamp LEVEL message` | a valid record (`seq` = line number in the input file) |
| `M seq` | line `seq` was malformed |
| `E lines valid malformed passed` | end-of-stream marker with counts, used for integrity checks |

A stream that ends **without** an `E` message means the upstream process died.

## Tests and experiments

```
make test       # 34 checks: normal, malformed, boundary, failure and restart cases
make bench      # single vs pipeline timings -> results/benchmark.csv
python3 docs/make_report.py   # rebuilds docs/report.pdf from the real results/ files
```

`results/test_output.txt` and `results/benchmark_output.txt` are the captured
outputs of one run. **Re-run both on your own machine** and regenerate the
report so that the numbers are yours.

## Layout

```
src/logrec.[ch]    record type, line parser, wire protocol
src/summary.[ch]   running summary, atomic checkpoint file, report printer
src/stages.[ch]    reader / filter / summarizer stages, single-process baseline, fault injection
src/main.c         command line, supervisor (pipe(), fork(), wait(), restart loop)
tools/             gen_logs.py (synthetic logs), bench.py (benchmark)
tests/run_tests.sh test suite
data/              sample inputs
results/           captured test and benchmark output, sample runs
docs/              diagram + report generator
```

## Limitations

* Whole-pipeline restart: a failed stage causes all three stages to be relaunched
  from the last checkpoint (stages are stateless except the summarizer, so this is
  simple and correct, but the reader re-scans the file from the start).
* Text wire format costs formatting/parsing time; a binary format would be faster.
* Stages run to completion on one input file; there is no streaming of a growing log.
* A stage that hangs (rather than dies) is not detected; there is no watchdog timeout.
