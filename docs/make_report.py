#!/usr/bin/env python3
"""Build docs/report.pdf from the REAL files in results/ (benchmark.csv,
test_output.txt, machine.txt, sample outputs). Re-run after `make test` and
`make bench` on your own machine so the report shows your measurements.

Needs: reportlab, matplotlib.
"""
import csv, os, re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (Image, PageBreak, Paragraph, Preformatted,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
R = lambda *p: os.path.join(ROOT, "results", *p)

def read(path):
    with open(path) as f:
        return f.read()

# ------------------------------------------------------------------ data
machine = dict(l.strip().split("=", 1) for l in read(R("machine.txt")).splitlines() if "=" in l)
cores = int(machine["cores"])
rows = [dict(lines=int(r["lines"]), work=int(r["work"]), single=float(r["single_ms"]),
             pipe=float(r["pipeline_ms"]), ratio=float(r["ratio"]))
        for r in csv.DictReader(open(R("benchmark.csv")))]
test_text = read(R("test_output.txt"))
n_pass = len(re.findall(r"^\s+PASS", test_text, re.M))
n_fail = len(re.findall(r"^\s+FAIL", test_text, re.M))

# ---------------------------------------------------------------- figures
def fig_architecture(path):
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.set_xlim(0, 100); ax.set_ylim(0, 46); ax.axis("off")

    def box(x, y, w, h, text, fc, ec="#333", ls="-", fs=9):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2",
                                    fc=fc, ec=ec, lw=1.4, ls=ls))
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs)

    def arrow(x1, y1, x2, y2, label=None, ls="-", color="#222", off=(0, 1.6), fs=8):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", lw=1.6, ls=ls, color=color))
        if label:
            ax.text((x1 + x2) / 2 + off[0], (y1 + y2) / 2 + off[1], label, ha="center",
                    va="bottom", fontsize=fs, color=color)

    box(37, 36, 26, 7, "Supervisor (parent process)\npipe()  fork()  wait()  restart loop", "#fff3cd")
    box(1, 14, 12, 8, "log file\n(input)", "#e8e8e8")
    box(19, 12, 16, 12, "Process 1\nREADER\nparse + validate\nline -> R / M msg", "#d6eaf8")
    box(46, 12, 16, 12, "Process 2\nFILTER\nkeep selected\nlevels", "#d5f5e3")
    box(73, 12, 16, 12, "Process 3\nSUMMARIZER\ncount per level\nprint report", "#fadbd8")
    box(73, 0, 16, 5.5, "checkpoint file\n(atomic rename)", "#e8e8e8", ls="--", fs=8)
    box(93, 14, 6.5, 8, "stdout\nreport", "#e8e8e8", fs=8)

    arrow(13.6, 18, 18.6, 18)
    arrow(35.6, 18, 45.6, 18, "pipe 1", off=(0, 0.8))
    ax.text(40.6, 15.6, "64 KiB", ha="center", fontsize=7, color="#222")
    arrow(62.6, 18, 72.6, 18, "pipe 2", off=(0, 0.8))
    ax.text(67.6, 15.6, "64 KiB", ha="center", fontsize=7, color="#222")
    arrow(89.6, 18, 92.6, 18)
    arrow(81, 11.4, 81, 6.2, "every N msgs", ls="--", off=(5.5, -0.8), fs=7)
    for x in (27, 54, 81):
        arrow(50 if x == 54 else (45 if x == 27 else 55), 35.5, x, 25, ls="--", color="#b9770e")
    ax.text(31, 31, "fork()", fontsize=8, color="#b9770e")
    ax.text(73, 31, "wait() -> exit status", fontsize=8, color="#b9770e")
    ax.text(50, 8, "Wire format: R seq ts LEVEL msg  |  M seq  |  E lines valid malformed passed",
            ha="center", fontsize=8, style="italic")
    fig.savefig(path, dpi=170, bbox_inches="tight"); plt.close(fig)

def fig_bench(path):
    works = sorted({r["work"] for r in rows})
    fig, axes = plt.subplots(1, len(works), figsize=(10, 3.3), sharey=False)
    for ax, w in zip(axes, works):
        sel = sorted([r for r in rows if r["work"] == w], key=lambda r: r["lines"])
        xs = range(len(sel)); bw = 0.38
        ax.bar([x - bw / 2 for x in xs], [r["single"] for r in sel], bw, label="single process", color="#5dade2")
        ax.bar([x + bw / 2 for x in xs], [r["pipe"] for r in sel], bw, label="3-process pipeline", color="#e67e22")
        ax.set_xticks(list(xs)); ax.set_xticklabels([f"{r['lines']:,}" for r in sel], fontsize=7, rotation=20)
        ax.set_yscale("log"); ax.set_ylabel("median time (ms, log)", fontsize=8)
        ax.set_title(f"extra work = {w} iter/record", fontsize=9); ax.tick_params(labelsize=7)
        ax.grid(axis="y", alpha=.3)
    axes[0].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(path, dpi=170); plt.close(fig)

arch_png, bench_png = os.path.join(HERE, "architecture.png"), os.path.join(HERE, "benchmark.png")
fig_architecture(arch_png); fig_bench(bench_png)

# ----------------------------------------------------------------- styles
ss = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=10, leading=13.6, spaceAfter=6)
H1 = ParagraphStyle("h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=14.5, spaceBefore=12, spaceAfter=6, keepWithNext=1)
H2 = ParagraphStyle("h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=11.5, spaceBefore=8, spaceAfter=4, keepWithNext=1)
CAP = ParagraphStyle("cap", parent=BODY, fontSize=8.5, leading=11, textColor=colors.HexColor("#444"), alignment=1)
CODE = ParagraphStyle("code", fontName="Courier", fontSize=7.4, leading=9)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.6, leading=11, spaceAfter=0)
TITLE = ParagraphStyle("title", parent=ss["Title"], fontName="Helvetica-Bold", fontSize=21, leading=26)

def P(t, s=BODY): return Paragraph(t, s)
def code(t): return Preformatted(t, CODE)
def table(data, widths, header=True):
    data = [[Paragraph(str(c), CELL) for c in row] for row in data]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header: st.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e6e6e6")))
    t.setStyle(TableStyle(st)); return t
def image(path, width):
    from PIL import Image as PI
    w, h = PI.open(path).size
    return Image(path, width=width, height=width * h / w)

def footer(c, d):
    c.saveState(); c.setFont("Helvetica", 8); c.setFillColor(colors.grey)
    c.drawString(2 * cm, 1.2 * cm, "Operating Systems - Topic 2: IPC through a log-processing pipeline")
    c.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {d.page}"); c.restoreState()

# ------------------------------------------------------------ report text
S = []
S += [Spacer(1, 2.5 * cm), P("Interprocess Communication Through a Log-Processing Pipeline", TITLE),
      P("Operating Systems Assignment - Topic 2: IPC, pipes and process coordination",
        ParagraphStyle("sub", parent=BODY, fontSize=12, leading=16)),
      Spacer(1, 0.6 * cm),
      P("<b>Name:</b> Ahsanul Karim Riyad &nbsp;&nbsp;&nbsp; <b>Student ID:</b> 2403012"),
      P("Course / Section: ______________________"),
      P("Source code repository: ______________________________ (GitHub URL)"),
      Spacer(1, 0.8 * cm),
      P("<b>Summary.</b> This report describes <i>logpipe</i>, a log-processing system written in C in which three "
        "separate processes (reader, filter, summarizer) cooperate through anonymous pipes under the control of a "
        "supervisor process. It explains the operating-system mechanisms involved (<font name='Courier'>fork</font>, "
        "<font name='Courier'>pipe</font>, blocking I/O, EOF and SIGPIPE semantics, <font name='Courier'>wait</font>), the "
        "design and wire format, how end-of-file, broken pipes, malformed input and process crashes are handled, a "
        "checkpoint-based restart mechanism that neither loses nor duplicates records (the assignment's challenge), the test "
        "suite, and a measured comparison with a single-process implementation."),
      PageBreak()]

# 1
S += [P("1. Problem and goals", H1),
      P("A log file contains lines of the form <font name='Courier'>YYYY-MM-DD HH:MM:SS LEVEL message</font>. The system must "
        "read the file, discard unwanted events, and report how many events of each severity remain, using at least three "
        "cooperating <i>processes</i> that exchange data through real interprocess communication (not shared function calls). "
        "It must define a clear data format, survive end-of-file conditions, broken pipes and unexpected process exit "
        "<i>without hanging</i>, produce a report that correctly represents the input, tolerate malformed lines, and be "
        "compared experimentally with a single-process version. The challenge extension asks that a failed stage can be "
        "restarted without silently losing or duplicating records."),
      P("The deliverables map to the repository as follows: source code (<font name='Courier'>src/</font>), process-communication "
        "diagram (Figure 1), sample input/output (Section 6.2), error-handling tests (Section 6), and the performance "
        "comparison (Section 7).")]

# 2
S += [P("2. Operating-system concepts used", H1),
      P("<b>Processes and fork().</b> Each stage is a separate process with its own address space. The supervisor calls "
        "<font name='Courier'>fork()</font> three times; every child inherits a <i>copy of the parent's file-descriptor table</i>, "
        "which is what makes pipes usable between related processes, and also what makes descriptor hygiene critical (below). "
        "Because stdio buffers are also duplicated by <font name='Courier'>fork()</font>, the supervisor flushes stdout/stderr "
        "before forking and the children leave with <font name='Courier'>_exit()</font> so buffered text is never emitted twice."),
      P("<b>Pipes.</b> <font name='Courier'>pipe()</font> returns two descriptors referring to a kernel-managed bounded buffer "
        "(65,536 bytes by default on Linux; measured on the test machine with <font name='Courier'>F_GETPIPE_SZ</font>). "
        "A <font name='Courier'>read()</font> on an empty pipe blocks; a <font name='Courier'>write()</font> on a full pipe blocks. "
        "This bounded buffer gives the classic producer-consumer behaviour: a fast reader is automatically throttled "
        "(back-pressure) by a slower filter, and memory use stays constant regardless of input size."),
      P("<b>EOF and broken pipes.</b> <font name='Courier'>read()</font> returns 0 (EOF) only when <i>every</i> write-end descriptor "
        "of the pipe has been closed. Conversely, writing to a pipe whose read ends are all closed raises SIGPIPE, whose default "
        "action kills the writer. The supervisor sets SIGPIPE to be ignored, so the write instead fails with "
        "<font name='Courier'>EPIPE</font> and the stage can log the problem and exit with a meaningful status."),
      P("<b>Why closing unused descriptors prevents hangs.</b> If the parent (or a sibling) kept a copy of pipe 1's write end, the "
        "filter would never see EOF even after the reader exited, because the pipe would still have a writer: the pipeline "
        "would hang forever. Therefore the supervisor closes all four pipe descriptors immediately after forking, and each "
        "child closes the ends it does not use (reader keeps only pipe 1 write; filter keeps pipe 1 read and pipe 2 write; "
        "summarizer keeps only pipe 2 read). With this discipline the death of any process closes its descriptors, and its "
        "neighbours are guaranteed to observe EOF or EPIPE."),
      P("<b>wait() and exit status.</b> The supervisor reaps all children with <font name='Courier'>wait()</font> (no zombies) and "
        "uses <font name='Courier'>WIFEXITED/WEXITSTATUS/WIFSIGNALED</font> to tell a clean exit, an error code, and death by signal "
        "(e.g. SIGKILL = 9) apart. <b>Atomic file replacement.</b> Checkpoints are written to a temporary file, "
        "<font name='Courier'>fsync()</font>ed, then installed with <font name='Courier'>rename()</font>, which POSIX guarantees to be atomic, "
        "so a crash can never leave a half-written checkpoint.")]

# 3
S += [P("3. Design", H1),
      image(arch_png, 16.2 * cm),
      P("Figure 1 - Process communication diagram. Solid arrows are data flow through pipes (each backed by a 64 KiB kernel buffer); "
        "dashed arrows show process control (fork/wait) and the checkpoint written by the last stage.", CAP),
      P("3.1 Stages", H2),
      table([["Process", "Responsibility", "Reads", "Writes"],
             ["Reader", "Reads the log with getline(), validates each line (timestamp ranges, level name, non-empty message, "
                        "no control characters, length &lt; 1024, no NUL byte). Emits R for valid lines and M for malformed ones, then E.",
              "log file", "pipe 1"],
             ["Filter", "Forwards only records whose level is selected (default WARN, ERROR, FATAL). Passes M through. "
                        "Verifies the reader's counts at E, then sends its own E.", "pipe 1", "pipe 2"],
             ["Summarizer", "Counts surviving records per level, tracks earliest/latest timestamp and the malformed count, "
                            "verifies the filter's counts at E, prints the report, optionally checkpoints.", "pipe 2", "stdout, checkpoint"],
             ["Supervisor", "Creates pipes, forks, closes unused descriptors, waits, reports each child's fate, restarts on failure.",
              "-", "-"]],
            [2.2 * cm, 9.6 * cm, 2.0 * cm, 2.6 * cm]),
      P("3.2 Data format", H2),
      P("Messages are single text lines with TAB-separated fields: <font name='Courier'>R seq timestamp LEVEL message</font> (a valid "
        "record), <font name='Courier'>M seq</font> (line number of a malformed line) and <font name='Courier'>E lines valid malformed "
        "passed</font> (end-of-stream marker with counts). The message is the last field, so it may itself contain TABs; newlines cannot "
        "occur because lines are the framing unit. <i>seq</i> is the line number in the input file: it is deterministic, which is what makes "
        "restart possible. A text format was chosen over a binary one because it is easy to inspect and debug (a stage can be tested by "
        "hand with <font name='Courier'>cat</font>); its cost is measured in Section 7."),
      P("3.3 Integrity checks", H2),
      P("The E marker carries counts. The filter checks that the number of R and M messages it received equals what the reader says it sent, "
        "and the summarizer does the same for the filter. A mismatch (for example from a corrupted stream) makes the stage exit with a distinct "
        "status (12) and print an explanation instead of reporting wrong numbers. This directly supports the requirement that the final report "
        "correctly represents the input: the report's <i>Lines read = Valid + Malformed</i> identity is enforced, and "
        "<i>Kept + Filtered out = Valid</i> holds by construction.")]

# 4
S += [P("4. Error handling", H1),
      table([["Situation", "Who detects it and how", "Result"],
             ["End of input file", "Reader: getline() returns -1 and ferror() is false", "Sends E, flushes, closes pipe; downstream sees E then EOF; exit 0"],
             ["Malformed log line", "Reader's parser rejects it", "Counted, first 10 reported on stderr, M message sent; processing continues"],
             ["Input file missing/unreadable", "Reader: fopen()/ferror()", "Message on stderr, exit 13; downstream sees EOF without E and exits 10; supervisor returns 1"],
             ["Reader dies mid-run", "Filter: EOF before E (also detects a half-written last line)", "Filter exits 10, summarizer exits 10, <b>no partial report</b>, no hang"],
             ["Filter dies", "Reader: write() fails with EPIPE; summarizer: EOF before E", "Reader exits 11, summarizer exits 10"],
             ["Summarizer dies", "Filter: EPIPE, then reader: EPIPE (cascade)", "Both exit 11; supervisor reports SIGKILL"],
             ["Garbage on a pipe", "wire_read() cannot parse the message", "Exit 12 (protocol error)"],
             ["Counts do not add up", "Filter/summarizer compare E counts", "Exit 12 with a diagnostic"]],
            [3.4 * cm, 6.3 * cm, 6.7 * cm]),
      Spacer(1, 4),
      P("No stage ever blocks forever, because for every blocking call there is a guaranteed wake-up: a reader blocked in "
        "<font name='Courier'>read()</font> is woken by EOF when the writer's descriptors close (including when the writer is killed); a writer blocked in "
        "<font name='Courier'>write()</font> on a full pipe is woken with EPIPE when the reader dies. The test suite verifies this "
        "by killing every stage at the very first message and in the middle of the run under a 20-second watchdog "
        "(<font name='Courier'>timeout</font>), and checks that no report is printed and the exit status is non-zero.")]

# 5
S += [P("5. Challenge: restart without losing or duplicating records", H1),
      P("<b>Approach.</b> The pipeline is restartable because (a) every message carries the stable line number <i>seq</i>, (b) the summarizer "
        "periodically writes a <i>checkpoint</i> containing its entire state (counts per level, malformed count, timestamps) together with "
        "<i>last_seq</i>, the highest line number whose effect is included, and (c) the checkpoint is replaced atomically. When any stage fails, the "
        "supervisor (<font name='Courier'>--restart</font>) relaunches the three stages; the supervisor loads the checkpoint <i>before</i> forking and "
        "hands the same state to the new summarizer and the value <i>last_seq</i> to the new reader, which skips lines up to it."),
      P("<b>Why nothing is lost.</b> Everything after <i>last_seq</i> is re-read and re-sent, including messages that were in the pipe buffers or in "
        "stdio buffers when the crash happened. <b>Why nothing is counted twice.</b> The checkpoint state corresponds exactly to messages "
        "<i>&lt;= last_seq</i>; messages the crashed summarizer had counted after its last checkpoint died with its memory, so after restart they "
        "are counted once, from the checkpoint. As a defence in depth the summarizer also ignores any message with <i>seq &lt;= last_seq</i> "
        "and prints a notice. Messages are processed in order because there is one writer per pipe, so <i>last_seq</i> is a valid high-water mark."),
      P("<b>Evidence.</b> For each stage, the test suite kills the process at the first message, in the middle and near the end (9 cases) with "
        "a checkpoint every 100 messages, and requires the final report to be <i>byte-identical</i> to a clean single-process run. "
        "Example run (<font name='Courier'>results/sample_stderr_restart.txt</font>): the summarizer is killed after 30 messages; the supervisor "
        "reports the SIGKILL, restarts, and resumes after line 65 (checkpoint: 2 malformed, 18 kept); the final report is complete.")]

# 6
S += [P("6. Testing", H1),
      P(f"The suite (<font name='Courier'>tests/run_tests.sh</font>) contains {n_pass + n_fail} checks; the captured run passed {n_pass} and failed {n_fail}. "
        "It covers normal cases (hand-computed expected report, 100,000-line generated inputs compared with the single-process version), malformed "
        "entries, boundary cases (empty file, no trailing newline, CRLF line endings, everything filtered out, only malformed lines, over-long message, "
        "embedded NUL byte, TAB inside a message) and failure scenarios (each stage killed, missing file, bad option, and the restart matrix)."),
      P("6.1 Test output (results/test_output.txt)", H2),
      code("\n".join(l[:118] for l in test_text.strip().splitlines())),
      PageBreak()]
sm_in = read(os.path.join(ROOT, "data", "sample_malformed.log")).rstrip("\n")
sm_out = read(R("sample_output_malformed.txt")).rstrip("\n")
S += [P("6.2 Sample input and output with malformed entries", H2),
      P("Input <font name='Courier'>data/sample_malformed.log</font> (line 5 is blank). Lines 2, 4, 5, 7 and 9 are malformed for these "
        "reasons: not a log line, month 13/day 40, blank, unknown level CRITICAL, missing message."),
      code(sm_in), Spacer(1, 4),
      P("Output of <font name='Courier'>./logpipe data/sample_malformed.log</font>:"), code(sm_out)]

# 7
rows_sorted = sorted(rows, key=lambda r: (r["work"], r["lines"]))
tab = [["Input lines", "Extra work\n(iter/record)", "Single (ms)", "Pipeline (ms)", "Pipeline / single"]]
for r in rows_sorted:
    tab.append([f"{r['lines']:,}", r["work"], f"{r['single']:.1f}", f"{r['pipe']:.1f}", f"{r['ratio']:.2f}x"])
big0 = [r for r in rows if r["work"] == 0 and r["lines"] == max(x["lines"] for x in rows)][0]
ovh_us = (big0["pipe"] - big0["single"]) / big0["lines"] * 1000
r_hi = [r for r in rows if r["work"] == max(x["work"] for x in rows)]
best = min(rows, key=lambda r: r["ratio"])
faster = best["ratio"] < 1.0
_sz = sorted({r["lines"] for r in rows if r["work"] == 0})
_a = [r for r in rows if r["work"] == 0 and r["lines"] == 100_000][0]
scaling_text = ("<b>Scaling.</b> Run time grows roughly in proportion to the input size for both versions "
                f"({_sz[-1] // _a['lines']}x more lines ({_a['lines']:,} to {_sz[-1]:,}) cost {big0['single'] / _a['single']:.1f}x more time single-process and "
                f"{big0['pipe'] / _a['pipe']:.1f}x more time in the pipeline; the sub-linear part is fixed start-up cost being amortised). "
                "This is the expected behaviour of a streaming design whose memory use is constant: the 64 KiB pipe buffers bound the data in flight.")
S += [P("7. Experimental investigation", H1),
      P("<b>Method.</b> Logs of 10,000 to 1,000,000 lines (1 percent malformed, fixed seed) were generated with "
        "<font name='Courier'>tools/gen_logs.py</font>. For each size and each per-record workload, the program was run once as warm-up and then "
        "5 times per mode; the table reports the <i>median wall-clock time</i> measured inside the program "
        "(<font name='Courier'>--time</font>, <font name='Courier'>CLOCK_MONOTONIC</font>), covering the whole run including fork and wait. "
        "The workload parameter adds a fixed CPU loop per valid record in the filter step to model a more expensive stage "
        "(0 = the real, very cheap filter). The same total work is done by both versions. "
        f"<b>Machine:</b> {machine['cpu']}, <b>{cores} logical CPU core{'s' if cores != 1 else ''}</b>, {machine['os']}."),
      table(tab, [3.0 * cm, 3.2 * cm, 3.0 * cm, 3.4 * cm, 3.6 * cm]),
      Spacer(1, 6), image(bench_png, 16.4 * cm),
      P("Figure 2 - Median run time, single process vs 3-process pipeline (log scale).", CAP),
      P("7.1 Analysis", H2),
      P(f"<b>IPC overhead.</b> With the real (cheap) filter the pipeline is {big0['ratio']:.1f}x slower than one process at "
        f"{big0['lines']:,} lines. The extra time is {ovh_us:.2f} microseconds per record, which is the price of formatting each record to text, "
        "<font name='Courier'>write()</font>ing it into the kernel pipe buffer, waking the next process, <font name='Courier'>read()</font>ing and "
        "re-parsing it - twice (two pipes) - plus context switches when a buffer fills or empties, plus the one-off cost of three "
        "<font name='Courier'>fork()</font>s. The whole single-process run (reading, parsing, filtering and counting) costs only "
        f"{big0['single'] / big0['lines'] * 1000:.2f} microseconds per line, so the communication is more expensive than the computation it distributes."),
      P("<b>Do additional processes improve performance?</b> " +
        (f"Yes, in the heavy-work runs: the best ratio observed was {best['ratio']:.2f}x. Pipeline parallelism lets the three stages work on "
         "different records at the same time on different cores; the speed-up is bounded by the slowest stage, because all stages advance at the "
         f"speed of the slowest one (pipe back-pressure). This machine has {cores} cores." if faster else
         f"Not on this machine: with only {cores} logical CPU core{'s' if cores != 1 else ''} the three processes cannot run in parallel, so they only "
         "<i>interleave</i> on the same core. The same total work is executed, plus IPC overhead and extra context switches, so the pipeline can never "
         f"win here. The overhead shrinks as the per-record work grows (ratio {r_hi[0]['ratio']:.2f}x to {r_hi[-1]['ratio']:.2f}x at the heaviest "
         "workload), because it is a roughly fixed cost per record that is amortised over more computation. On a multi-core machine the heavy-work "
         "case is where the pipeline is expected to start paying off, up to a bound set by the slowest stage (Amdahl's law applied to a pipeline); "
         "the benchmark should be re-run on such a machine, which is why the report is generated from the measured files.")),
      P(scaling_text),
      P("<b>Why use a pipeline at all, then?</b> The measurements show that for this workload the benefit is not speed but structure: stages are isolated "
        "(a crash in one cannot corrupt another's memory), they can be replaced, restarted and supervised independently, and the design "
        "scales to genuinely expensive stages or to different machines if the pipes were replaced by sockets. The single-process version is simpler "
        "and faster for cheap per-record work.")]

# 8-10
S += [P("8. Comparison with the single-process version", H1),
      table([["Aspect", "Single process (--mode single)", "Pipeline (3 processes)"],
             ["Result", "Identical report (verified by diff on 100k-line inputs, with and without malformed lines)", "Identical"],
             ["Speed (cheap filter)", "Fastest: no IPC", f"{big0['ratio']:.1f}x slower at {big0['lines']:,} lines"],
             ["Speed (expensive stage, multi-core)", "Sequential: total = sum of stages", "Potentially faster: total ~ slowest stage"],
             ["Fault isolation", "A crash loses everything", "A crash is contained; neighbours detect it; can restart from checkpoint"],
             ["Complexity", "About 40 lines", "Supervisor, wire format, descriptor management, integrity checks"],
             ["Memory", "One process", "Three address spaces + 2 x 64 KiB pipe buffers"]],
            [3.7 * cm, 6.4 * cm, 6.3 * cm]),
      P("9. Reflection", H1),
      P("<b>Limitation.</b> Recovery restarts the <i>whole</i> pipeline and the reader re-scans the file from the beginning to skip already-counted lines; "
        "also, a stage that hangs without dying (for example an infinite loop) is not detected, since detection relies on descriptors being closed "
        "when a process exits. <b>Improvement.</b> Add a heartbeat/timeout in the supervisor that kills a silent stage, and let the reader "
        "<font name='Courier'>fseek()</font> to a byte offset stored in the checkpoint (alongside <i>last_seq</i>) so restart cost no longer grows with file size. "
        "A further step would be per-stage restart using sequence-number acknowledgements, so only the failed stage is relaunched."),
      P("10. Conclusion", H1),
      P("The implementation uses real interprocess communication (anonymous pipes between forked processes) with a defined wire format, "
        "survives end-of-file, broken pipes and process crashes without hanging, validates its own counts, handles malformed input, and "
        "can recover from a crash with an exact, duplicate-free result. The experiments show that for cheap per-record work the cost of IPC "
        "dominates, and that the real value of the multi-process design lies in isolation and recoverability, with performance benefits only "
        "when stages are expensive and cores are available."),
      P("Appendix: build and run", H2),
      code("make                # build ./logpipe\nmake test           # run the test suite\nmake bench          # run the benchmark (results/benchmark.csv)\n"
           "./logpipe data/sample_normal.log\n./logpipe --restart --ckpt-every 20 --crash summarizer:30 data/sample_generated.log")]

doc = SimpleDocTemplate(os.path.join(HERE, "report.pdf"), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm,
                        topMargin=1.8 * cm, bottomMargin=2 * cm, title="Interprocess Communication Through a Log-Processing Pipeline")
doc.build(S, onFirstPage=lambda c, d: None, onLaterPages=footer)
print("wrote docs/report.pdf")
