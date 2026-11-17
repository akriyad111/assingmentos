#!/usr/bin/env python3
"""Benchmark: single-process vs 3-process pipeline.

For every (input size, per-record work) pair, run each mode REPEATS times and
report the median wall-clock time measured inside logpipe (TIME_MS).
Writes results/benchmark.csv and prints a table.
"""
import csv, os, platform, statistics, subprocess, sys, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "logpipe")
SIZES = [10_000, 100_000, 500_000, 1_000_000]
WORKS = [0, 200, 2000]          # extra CPU loop iterations per record in the filter step
REPEATS = 5

def run(mode, path, work):
    args = [BIN, "--mode", mode, "--time", "--work", str(work), path]
    p = subprocess.run(args, capture_output=True, text=True, check=True)
    for line in p.stderr.splitlines():
        if line.startswith("TIME_MS"):
            return float(line.split()[1])
    raise RuntimeError("no timing line")

def write_machine_info():
    """Record the hardware the numbers were measured on (used by the report)."""
    cpu = platform.processor() or platform.machine()
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name"):
                    cpu = line.split(":", 1)[1].strip(); break
    except OSError:
        try:
            cpu = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                 capture_output=True, text=True).stdout.strip() or cpu
        except OSError:
            pass
    with open(os.path.join(ROOT, "results", "machine.txt"), "w") as f:
        f.write(f"cores={os.cpu_count()}\nos={platform.system()} {platform.release()}\ncpu={cpu}\n")

def main():
    write_machine_info()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for n in SIZES:
            path = os.path.join(tmp, f"log_{n}.log")
            subprocess.run([sys.executable, os.path.join(ROOT, "tools", "gen_logs.py"),
                            "--lines", str(n), "--seed", "1", "--malformed-rate", "0.01",
                            "--out", path], check=True)
            for work in WORKS:
                if n >= 500_000 and work == 2000:
                    continue                      # keeps total benchmark time reasonable
                run("single", path, work)         # warm-up (page cache)
                s = [run("single", path, work) for _ in range(REPEATS)]
                p = [run("pipeline", path, work) for _ in range(REPEATS)]
                ms, mp = statistics.median(s), statistics.median(p)
                rows.append(dict(lines=n, work=work, single_ms=round(ms, 1),
                                 pipeline_ms=round(mp, 1), ratio=round(mp / ms, 2)))
                print(f"lines={n:>9,} work={work:>5}  single={ms:9.1f} ms  "
                      f"pipeline={mp:9.1f} ms  pipeline/single={mp/ms:5.2f}x", flush=True)
    out = os.path.join(ROOT, "results", "benchmark.csv")
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["lines", "work", "single_ms", "pipeline_ms", "ratio"])
        w.writeheader(); w.writerows(rows)
    print("wrote", out)

if __name__ == "__main__":
    main()
