#!/usr/bin/env python3
"""Generate a synthetic application log.

Format of a valid line:  YYYY-MM-DD HH:MM:SS LEVEL message
Usage: gen_logs.py --lines N [--seed S] [--malformed-rate R] --out FILE
"""
import argparse, random, datetime

LEVELS = [("DEBUG", 30), ("INFO", 50), ("WARN", 12), ("ERROR", 7), ("FATAL", 1)]
MSGS = {
    "DEBUG": ["cache lookup key=%d", "entering handler id=%d", "query plan cached (%d rows)"],
    "INFO":  ["user %d logged in", "request %d completed in %dms", "job %d scheduled"],
    "WARN":  ["slow query took %dms (id=%d)", "retrying connection attempt %d", "disk usage at %d%%"],
    "ERROR": ["failed to open file /var/data/%d.dat", "timeout calling payment service (id=%d)",
              "unhandled exception in worker %d"],
    "FATAL": ["out of memory in worker %d", "database connection lost (node %d)"],
}
BAD = [
    "this line is not a log entry at all",
    "2025-13-45 99:99:99 ERROR impossible date",
    "2025-03-01 12:00:00 SEVERE unknown level name",
    "2025-03-01 12:00:00 ERROR",                      # empty message
    "2025-03-01T12:00:00 ERROR wrong timestamp separator",
    "",                                               # blank line
    "ERROR 2025-03-01 12:00:00 fields in the wrong order",
    "2025-03-01 12:00:00 error lowercase level",
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lines", type=int, required=True)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--malformed-rate", type=float, default=0.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    rnd = random.Random(a.seed)
    names, weights = zip(*LEVELS)
    t = datetime.datetime(2025, 3, 1, 0, 0, 0)
    with open(a.out, "w") as f:
        for _ in range(a.lines):
            if a.malformed_rate and rnd.random() < a.malformed_rate:
                f.write(rnd.choice(BAD) + "\n")
                continue
            t += datetime.timedelta(seconds=rnd.randint(0, 2))
            lv = rnd.choices(names, weights)[0]
            tpl = rnd.choice(MSGS[lv])
            n = tpl.count("%d")
            msg = tpl % tuple(rnd.randint(1, 9999) for _ in range(n)) if n else tpl
            f.write(f"{t:%Y-%m-%d %H:%M:%S} {lv} {msg}\n")

if __name__ == "__main__":
    main()
