CC      ?= gcc
CFLAGS  ?= -O2 -Wall -Wextra -std=gnu11
SRC     := src/main.c src/stages.c src/summary.c src/logrec.c

all: logpipe

logpipe: $(SRC) src/*.h
	$(CC) $(CFLAGS) -o $@ $(SRC)

test: logpipe
	bash tests/run_tests.sh

bench: logpipe
	python3 tools/bench.py

clean:
	rm -f logpipe data/*.ckpt data/*.ckpt.tmp

.PHONY: all test bench clean
