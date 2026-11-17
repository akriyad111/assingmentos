#!/usr/bin/env bash
# Test suite for logpipe: normal, boundary and failure scenarios.
# Usage: bash tests/run_tests.sh      (from the project root, after `make`)
set -u
cd "$(dirname "$0")/.."
BIN=./logpipe

# macOS has no `timeout` command. Use gtimeout (brew coreutils) if present,
# otherwise a tiny perl fallback that also exits with 124 on timeout.
if ! command -v timeout >/dev/null 2>&1; then
    if command -v gtimeout >/dev/null 2>&1; then
        timeout() { gtimeout "$@"; }
    else
        timeout() {
            perl -e 'my $t = shift; my $pid = fork();
                     if ($pid == 0) { exec @ARGV; exit 127; }
                     $SIG{ALRM} = sub { kill 9, $pid; waitpid($pid, 0); exit 124; };
                     alarm $t; waitpid($pid, 0); alarm 0;
                     exit(($? & 127) ? 128 + ($? & 127) : ($? >> 8));' "$@"
        }
    fi
fi
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
PASS=0; FAIL=0

ok()   { PASS=$((PASS+1)); printf '  PASS  %s\n' "$1"; }
bad()  { FAIL=$((FAIL+1)); printf '  FAIL  %s\n' "$1"; }
check(){ if [ "$1" = 0 ]; then ok "$2"; else bad "$2"; fi; }

# run_ok <name> <expected-file> <args...>: stdout must equal expected file, rc 0
run_expect() {
    local name=$1 exp=$2; shift 2
    timeout 30 $BIN "$@" >"$TMP/out" 2>"$TMP/err"; local rc=$?
    if [ $rc -eq 0 ] && diff -q "$TMP/out" "$exp" >/dev/null; then ok "$name"
    else bad "$name (rc=$rc)"; diff "$TMP/out" "$exp" | head -5; fi
}
# same_as_single <name> <file> [extra args]: pipeline output == single-process output
same_as_single() {
    local name=$1 file=$2; shift 2
    timeout 60 $BIN --mode single "$@" "$file" >"$TMP/s.out" 2>/dev/null
    timeout 60 $BIN "$@" "$file" >"$TMP/p.out" 2>/dev/null
    if [ $? -eq 0 ] && diff -q "$TMP/s.out" "$TMP/p.out" >/dev/null; then ok "$name"
    else bad "$name"; fi
}

[ -x $BIN ] || { echo "build first: make"; exit 1; }

echo "== 1. Normal cases =="
cat >"$TMP/exp_normal" <<'X'
=== Log Summary ===
Lines read             : 7
  Valid records        : 7
  Malformed (skipped)  : 0
Records kept by filter : 4
Records filtered out   : 3
Counts by level (kept records):
  WARN   : 1
  ERROR  : 2
  FATAL  : 1
Earliest timestamp     : 2025-03-01 10:01:00
Latest timestamp       : 2025-03-01 10:03:00
X
run_expect "pipeline: hand-checked report (7 lines)" "$TMP/exp_normal" data/sample_normal.log
run_expect "single:   hand-checked report (7 lines)" "$TMP/exp_normal" --mode single data/sample_normal.log

cat >"$TMP/exp_err" <<'X'
=== Log Summary ===
Lines read             : 7
  Valid records        : 7
  Malformed (skipped)  : 0
Records kept by filter : 2
Records filtered out   : 5
Counts by level (kept records):
  ERROR  : 2
Earliest timestamp     : 2025-03-01 10:02:00
Latest timestamp       : 2025-03-01 10:02:30
X
run_expect "--levels ERROR keeps only ERROR" "$TMP/exp_err" --levels ERROR data/sample_normal.log
python3 tools/gen_logs.py --lines 100000 --seed 11 --malformed-rate 0.02 --out "$TMP/big.log"
same_as_single "100k generated lines: pipeline == single-process" "$TMP/big.log"
same_as_single "100k lines, --levels DEBUG,INFO" "$TMP/big.log" --levels DEBUG,INFO

echo "== 2. Malformed log entries =="
cat >"$TMP/exp_mal" <<'X'
=== Log Summary ===
Lines read             : 9
  Valid records        : 4
  Malformed (skipped)  : 5
Records kept by filter : 3
Records filtered out   : 1
Counts by level (kept records):
  WARN   : 1
  ERROR  : 1
  FATAL  : 1
Earliest timestamp     : 2025-03-01 10:01:00
Latest timestamp       : 2025-03-01 10:03:10
X
run_expect "pipeline: 5 malformed of 9 lines (garbage, bad date, blank, bad level, empty msg)" "$TMP/exp_mal" data/sample_malformed.log
run_expect "single:   5 malformed of 9 lines" "$TMP/exp_mal" --mode single data/sample_malformed.log
same_as_single "generated sample with 3% malformed lines" data/sample_generated.log

echo "== 3. Boundary cases =="
: >"$TMP/empty.log"
timeout 20 $BIN "$TMP/empty.log" >"$TMP/out" 2>&1; rc=$?
{ [ $rc -eq 0 ] && grep -q "Lines read             : 0" "$TMP/out"; }; check $? "empty file -> report with 0 lines, no hang"
printf '2025-03-01 10:00:00 ERROR no trailing newline' >"$TMP/nonl.log"
timeout 20 $BIN "$TMP/nonl.log" >"$TMP/out" 2>&1
grep -q "ERROR  : 1" "$TMP/out"; check $? "last line without trailing newline is processed"
printf '2025-03-01 10:00:00 WARN crlf line\r\n2025-03-01 10:00:01 ERROR crlf line 2\r\n' >"$TMP/crlf.log"
timeout 20 $BIN "$TMP/crlf.log" >"$TMP/out" 2>&1
{ grep -q "Valid records        : 2" "$TMP/out"; }; check $? "Windows (CRLF) line endings accepted"
printf '2025-03-01 10:00:00 INFO a\n2025-03-01 10:00:01 DEBUG b\n' >"$TMP/nokeep.log"
timeout 20 $BIN "$TMP/nokeep.log" >"$TMP/out" 2>&1
{ grep -q "Records kept by filter : 0" "$TMP/out" && grep -q "Earliest timestamp     : (none)" "$TMP/out"; }; check $? "everything filtered out -> zero counts, (none) timestamps"
printf 'junk\nmore junk\n\n' >"$TMP/alljunk.log"
timeout 20 $BIN "$TMP/alljunk.log" >"$TMP/out" 2>/dev/null
{ grep -q "Malformed (skipped)  : 3" "$TMP/out"; }; check $? "file with only malformed lines"
{ printf '2025-03-01 10:00:00 ERROR '; head -c 5000 /dev/zero | tr '\0' 'x'; printf '\n2025-03-01 10:00:01 ERROR ok\n'; } >"$TMP/long.log"
timeout 20 $BIN "$TMP/long.log" >"$TMP/out" 2>/dev/null
{ grep -q "Malformed (skipped)  : 1" "$TMP/out" && grep -q "ERROR  : 1" "$TMP/out"; }; check $? "5000-char message rejected as malformed, next line still processed"
printf '2025-03-01 10:00:00 ERROR has a nul \000 byte\n2025-03-01 10:00:01 ERROR ok\n' >"$TMP/nul.log"
timeout 20 $BIN "$TMP/nul.log" >"$TMP/out" 2>/dev/null
{ grep -q "Malformed (skipped)  : 1" "$TMP/out"; }; check $? "embedded NUL byte -> malformed (not silently truncated)"
printf '2025-03-01 10:00:00 ERROR a\ttab\tinside message\n' >"$TMP/tab.log"
timeout 20 $BIN "$TMP/tab.log" >"$TMP/out" 2>/dev/null
{ grep -q "ERROR  : 1" "$TMP/out"; }; check $? "TAB characters inside a message do not break the wire format"

echo "== 4. Failure scenarios (no restart): must exit non-zero, must not hang, no partial report =="
python3 tools/gen_logs.py --lines 20000 --seed 5 --malformed-rate 0.02 --out "$TMP/f.log"
for spec in reader:1 reader:10000 filter:1 filter:10000 summarizer:1 summarizer:1000; do
    timeout 20 $BIN --crash $spec "$TMP/f.log" >"$TMP/out" 2>"$TMP/err"; rc=$?
    if [ $rc -ne 0 ] && [ $rc -ne 124 ] && [ ! -s "$TMP/out" ]; then ok "stage killed ($spec): rc=$rc, no hang, no report"
    else bad "stage killed ($spec): rc=$rc stdout_bytes=$(wc -c <"$TMP/out")"; fi
done
timeout 20 $BIN "$TMP/does-not-exist.log" >"$TMP/out" 2>"$TMP/err"; rc=$?
{ [ $rc -ne 0 ] && [ $rc -ne 124 ] && grep -q "cannot open" "$TMP/err"; }; check $? "missing input file -> clear error, rc=$rc"
timeout 20 $BIN --levels BOGUS "$TMP/f.log" >/dev/null 2>&1; rc=$?
{ [ $rc -eq 2 ]; }; check $? "invalid --levels -> usage error (rc 2)"

echo "== 5. Restart: crash each stage at several points, result must equal a clean run =="
python3 tools/gen_logs.py --lines 10000 --seed 9 --malformed-rate 0.02 --out "$TMP/r.log"
$BIN --mode single "$TMP/r.log" >"$TMP/ref" 2>/dev/null
for spec in reader:1 reader:5000 reader:9999 filter:1 filter:5000 filter:9999 summarizer:1 summarizer:700 summarizer:1500; do
    timeout 30 $BIN --restart --ckpt-every 100 --crash $spec "$TMP/r.log" >"$TMP/out" 2>"$TMP/err"; rc=$?
    if [ $rc -eq 0 ] && diff -q "$TMP/out" "$TMP/ref" >/dev/null && [ ! -e "$TMP/r.log.ckpt" ]; then
        ok "crash $spec -> restarted, report identical to clean run (no loss, no duplicates)"
    else bad "crash $spec (rc=$rc)"; diff "$TMP/out" "$TMP/ref" | head -4; fi
done
timeout 30 $BIN --restart "$TMP/r.log" >"$TMP/out" 2>/dev/null
{ diff -q "$TMP/out" "$TMP/ref" >/dev/null; }; check $? "--restart without a failure behaves like a normal run"

echo
echo "Result: $PASS passed, $FAIL failed"
[ $FAIL -eq 0 ]
