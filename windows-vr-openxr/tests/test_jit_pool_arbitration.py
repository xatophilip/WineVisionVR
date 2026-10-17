#!/usr/bin/env python3
"""ASan/UBSan tests for production head/tail reservation helpers.

Accepts a prepared Madeira source containing patch 0012. Exercises the captured
Fantastic Contraption exhaustion, failed-reservation accounting, stale head
limits and concurrent allocator arbitration without creating executable memory.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def extract(source, name):
    match = re.search(r"static\s+(?:size_t|int)\s+" + name + r"\([^)]*\)\s*\{", source)
    if not match:
        raise RuntimeError("Missing production helper " + name)
    level, end = 1, match.end()
    while level:
        level += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-source", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    source = args.runtime_source / "build/ntdll-unix/virtual_ios.c"
    text = source.read_text()
    helpers = extract(text, "ios_pool_head_limit_locked") + "\n" + extract(text, "ios_pool_reserve_tail_locked")
    assert "pool_limit = ios_pool_head_limit_locked( pool_limit );" in text
    allocation = text[text.index("size_t reserve_offset, pool_tail_off = 0;"):]
    allocation = allocation[:allocation.index("if (!reserved)")]
    assert allocation.index("pthread_mutex_lock( &ios_pool_lock )") < allocation.index("ios_pool_reserve_tail_locked")
    assert allocation.index("ios_pool_reserve_tail_locked") < allocation.index("pthread_mutex_unlock( &ios_pool_lock )")
    assert "__sync_fetch_and_add(&ios_jit_tail_reserved" not in text
    assert "__sync_fetch_and_sub(&ios_jit_tail_reserved" not in text
    code = r'''
#include <assert.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#define MB ((size_t)1024 * 1024)
static size_t ios_jit_pool_size_global, jit_pool_offset;
static volatile size_t ios_jit_tail_reserved;
static pthread_mutex_t ios_pool_lock = PTHREAD_MUTEX_INITIALIZER;
'''+helpers+r'''
static struct { size_t offset, size; } committed[8192];
static unsigned committed_count;
static void record(size_t offset, size_t size) {
    assert(offset <= ios_jit_pool_size_global && size <= ios_jit_pool_size_global - offset);
    for (unsigned i = 0; i < committed_count; ++i)
        assert(offset + size <= committed[i].offset || offset >= committed[i].offset + committed[i].size);
    assert(committed_count < 8192);
    committed[committed_count].offset = offset; committed[committed_count++].size = size;
}
static void *worker(void *argument) {
    uintptr_t id = (uintptr_t)argument;
    for (unsigned i = 0; i < 1000; ++i) {
        size_t size = (1 + ((i + id) % 4)) * 0x10000;
        if ((i + id) % 2) {
            /* Capture a deliberately stale caller limit before taking the
             * production allocator's commit lock, as real callers can. */
            pthread_mutex_lock(&ios_pool_lock);
            size_t caller_limit = ios_jit_pool_size_global - ios_jit_tail_reserved;
            pthread_mutex_unlock(&ios_pool_lock);
            sched_yield();
            pthread_mutex_lock(&ios_pool_lock);
            size_t limit = ios_pool_head_limit_locked(caller_limit);
            if (jit_pool_offset <= limit && size <= limit - jit_pool_offset) {
                size_t offset = jit_pool_offset; jit_pool_offset += size; record(offset, size);
            }
            pthread_mutex_unlock(&ios_pool_lock);
        } else {
            size_t offset;
            pthread_mutex_lock(&ios_pool_lock);
            if (ios_pool_reserve_tail_locked(size, &offset)) record(offset, size);
            pthread_mutex_unlock(&ios_pool_lock);
        }
    }
    return NULL;
}
int main(void) {
    size_t offset = SIZE_MAX;
    ios_jit_pool_size_global = 0x28000000;
    /* Exact captured 17:18 state before Fantastic Contraption's code buffer. */
    jit_pool_offset = 0x8bb8000; ios_jit_tail_reserved = 0x18010000;
    assert(!ios_pool_reserve_tail_locked(128 * MB, &offset));
    assert(!ios_pool_reserve_tail_locked(64 * MB, &offset));
    assert(ios_jit_tail_reserved == 0x18010000 && offset == SIZE_MAX);
    assert(ios_pool_reserve_tail_locked(32 * MB, &offset));
    assert(offset == 0x0dff0000);
    /* A later DLL that failed at captured head0xbf74000 now fits, without
     * expanding the arena or writing over a live tail carve. */
    jit_pool_offset = 0xbf74000;
    size_t limit = ios_pool_head_limit_locked(ios_jit_pool_size_global);
    assert(jit_pool_offset + 0x1c4000 <= limit);
    /* A stale head limit cannot cross a newer tail reservation. */
    assert(ios_pool_head_limit_locked(0x28000000) == offset);
    assert(ios_pool_head_limit_locked(0) == 0); /* freelist-only remains so */
    assert(ios_pool_head_limit_locked(0x10000) == 0x10000);
    ios_jit_tail_reserved = 0; jit_pool_offset = 575 * MB;
    assert(!ios_pool_reserve_tail_locked(16 * MB, &offset));
    assert(ios_pool_reserve_tail_locked(1 * MB, &offset));
    assert(!ios_pool_reserve_tail_locked(0x4000, &offset));
    assert(ios_jit_tail_reserved == 1 * MB);
    ios_jit_tail_reserved = SIZE_MAX;
    assert(!ios_pool_reserve_tail_locked(0x4000, &offset));
    assert(ios_pool_head_limit_locked(SIZE_MAX) == 0);
    ios_jit_tail_reserved = 0; jit_pool_offset = SIZE_MAX;
    assert(!ios_pool_reserve_tail_locked(0x4000, &offset));
    jit_pool_offset = 0;
    assert(!ios_pool_reserve_tail_locked(0, &offset));
    assert(!ios_pool_reserve_tail_locked(SIZE_MAX, &offset));
    /* Competing head/tail committers never overlap or corrupt rollback
     * accounting. Thread scheduling varies their allocation order. */
    pthread_t threads[8];
    for (uintptr_t i = 0; i < 8; ++i) assert(!pthread_create(&threads[i], NULL, worker, (void *)i));
    for (unsigned i = 0; i < 8; ++i) assert(!pthread_join(threads[i], NULL));
    assert(committed_count && jit_pool_offset + ios_jit_tail_reserved <= ios_jit_pool_size_global);
    assert(ios_jit_tail_reserved <= (ios_jit_pool_size_global / 4) * 3);
    printf("PASS: captured exhaustion replay, refusal accounting, stale limits, overflow and 8000 concurrent requests (%u committed)\n", committed_count);
}
'''
    output = args.output_dir or Path(tempfile.mkdtemp(prefix="wvr-jit-pool-"))
    output.mkdir(parents=True, exist_ok=True)
    test = output / "jit-pool-arbitration.c"
    test.write_text(code)
    command = ["xcrun", "clang", "-std=c11", "-g", "-O1", "-fsanitize=address,undefined",
               "-fno-omit-frame-pointer", "-pthread", str(test), "-o", str(output / "jit-pool-arbitration")]
    print(shlex.join(command), flush=True)
    subprocess.run(command, check=True)
    run = subprocess.run([str(output / "jit-pool-arbitration")], check=True, text=True, capture_output=True)
    print(run.stdout, end="")
    (output / "result.json").write_text(json.dumps({"status": "PASS", "sanitizers": ["ASan", "UBSan"],
        "productionSourceSha256": hashlib.sha256(source.read_bytes()).hexdigest(), "arenaMiB": 640,
        "headReserveMiB": 64, "concurrentRequests": 8000,
        "cases": ["captured-exhaustion", "no-cursor-change-on-refusal", "small-buffer-degradation",
                  "stale-head-limit", "freelist-only", "overflow", "concurrent-nonoverlap"]}, indent=2) + "\n")


if __name__ == "__main__":
    main()
