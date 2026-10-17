#!/usr/bin/env python3
"""Compile applied Wine GDI publication and client-init code with mock host I/O.

Only the TEB/PEB, section mapping and client-procedure registry dependencies are
mocked. The applied publication function, patched inline check and native
NtUserInitializeClientPfnArrays body are compiled from the prepared source.
No Wine runtime, guest executable, device or graphics API is executed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-source', required=True, type=Path)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
paths = {
    'inline': args.runtime_source / 'wine/dlls/win32u/win32u_private.h',
    'publish': args.runtime_source / 'wine/dlls/win32u/gdiobj.c',
    'init': args.runtime_source / 'build/win32u-unix/class_ios.c',
}
texts = {key: path.read_text() for key, path in paths.items()}
def function(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    end, depth = brace + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]
inline = function(texts['inline'], 'static inline void win32u_gdi_check_publish(void)')
publish = function(texts['publish'], 'void win32u_gdi_publish_shared(void)')
initialize = function(texts['init'], 'NTSTATUS WINAPI NtUserInitializeClientPfnArrays(')
# Evidence must come from the actually applied prepared tree, not the patch file.
assert 'TEB *teb = NtCurrentTeb();' in inline, 'The child-GDI patch was not applied'
assert '!teb->Peb->GdiSharedHandleTable' in inline, 'Uninitialized GDI tables must remain retryable'
assert initialize.index('pthread_once( &init_once, init_user );') < initialize.index('win32u_gdi_check_publish();'), 'Per-process publication must follow native-global initialization'

prelude = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <pthread.h>
#include <string.h>
typedef int BOOL;
typedef unsigned int DWORD;
typedef unsigned int UINT;
typedef uintptr_t HANDLE;
typedef uintptr_t ULONG_PTR;
typedef size_t SIZE_T;
typedef int NTSTATUS;
typedef void *HINSTANCE;
typedef struct { long long QuadPart; } LARGE_INTEGER;
typedef struct { void *GdiSharedHandleTable; } PEB;
typedef struct { PEB *Peb; int WowTebOffset; struct { void *UniqueProcess; } ClientId; } TEB;
#define WINAPI
#define ViewShare 1
#define PAGE_READWRITE 4
#define STATUS_SUCCESS 0
#define HandleToULong(h) ((DWORD)(uintptr_t)(h))
#define ERR(...) do { ++mapping_errors; } while (0)
static TEB *current_teb;
static TEB *NtCurrentTeb(void) { return current_teb; }
static int master_storage;
static void *gdi_shared;
static BOOL win32u_wow_session;
static _Thread_local void *win32u_gdi_published_peb;
static HANDLE gdi_shared_section = 1;
static void *win32u_gdi_creator_peb;
#define GDI_SHARED_MAX_VIEWS 8
static struct { DWORD pid; void *peb; void *view; } gdi_shared_views[GDI_SHARED_MAX_VIEWS];
static int gdi_shared_view_count, gdi_shared_view_next;
static pthread_mutex_t gdi_shared_view_lock = PTHREAD_MUTEX_INITIALIZER;
static unsigned publish_calls, map_calls, close_calls, mapping_errors;
static uintptr_t mock_guest_base;
static HANDLE open_gdi_shared_section(void) { return 100 + (HANDLE)NtCurrentTeb()->ClientId.UniqueProcess; }
static HANDLE GetCurrentProcess(void) { return 1; }
static ULONG_PTR caller_zero_bits(void) { return 0x7fffffff; }
static NTSTATUS NtMapViewOfSection(HANDLE section, HANDLE process, void **view, ULONG_PTR zero_bits,
                                   SIZE_T commit, LARGE_INTEGER *offset, SIZE_T *size,
                                   int inherit, int allocation, int protection) {
    assert(section != 0 && process == 1 && zero_bits == 0x7fffffff);
    ++map_calls;
    *view = (void *)(mock_guest_base + 0x12340000);
    return 0;
}
static void NtClose(HANDLE section) { assert(section >= 100); ++close_calls; }
#define win32u_gdi_publish_shared production_win32u_gdi_publish_shared
'''
wrapper = r'''
#undef win32u_gdi_publish_shared
static void win32u_gdi_publish_shared(void) {
    ++publish_calls;
    production_win32u_gdi_publish_shared();
}
'''
registry = r'''
#define NTUSER_NB_PROCS 2
#define IOS_MAX_CLIENT_PROCS 8
typedef uintptr_t ntuser_client_func_ptr[1];
static struct { uintptr_t procA, procW; } winproc_array[NTUSER_NB_PROCS];
struct ios_client_procs {
    void *peb;
    HINSTANCE user32_module;
    struct { uintptr_t procA, procW; } procs[NTUSER_NB_PROCS];
};
static struct ios_client_procs ios_client_procs_reg[IOS_MAX_CLIENT_PROCS];
static int ios_client_procs_count;
static pthread_mutex_t winproc_lock = PTHREAD_MUTEX_INITIALIZER;
static HINSTANCE user32_module;
static unsigned init_user_calls;
static void init_user(void) {
    ++init_user_calls;
    gdi_shared = &master_storage;
    win32u_gdi_publish_shared();
}
'''
probe = r'''
int main(void) {
    PEB parent = {0}, child = {0}, wow = {0}, later_wow = {0};
    TEB parent_teb = {&parent, 0, {(void *)1}};
    TEB child_teb = {&child, 0, {(void *)2}};
    TEB wow_teb = {&wow, 0x1000, {(void *)3}};
    TEB later_wow_teb = {&later_wow, 0x1000, {(void *)4}};
    current_teb = &parent_teb;
    // Calling before table allocation must not poison the per-thread marker.
    win32u_gdi_check_publish();
    assert(publish_calls == 1 && parent.GdiSharedHandleTable == NULL && win32u_gdi_published_peb == NULL);
    win32u_gdi_check_publish();
    assert(publish_calls == 2 && win32u_gdi_published_peb == NULL);
    gdi_shared = &master_storage;
    win32u_gdi_check_publish();
    assert(publish_calls == 3 && parent.GdiSharedHandleTable == gdi_shared);
    unsigned before = publish_calls;
    win32u_gdi_check_publish();
    assert(publish_calls == before && map_calls == 0);
    // A 64-bit child gets its own PEB populated despite native-global init.
    current_teb = &child_teb;
    win32u_gdi_check_publish();
    assert(publish_calls == before + 1 && child.GdiSharedHandleTable == gdi_shared && map_calls == 0);
    before = publish_calls;
    win32u_gdi_check_publish();
    assert(publish_calls == before);
    child.GdiSharedHandleTable = NULL;
    win32u_gdi_check_publish();
    assert(publish_calls == before + 1 && child.GdiSharedHandleTable == gdi_shared);
    // A 32-bit process cannot publish a host-only pointer before the session
    // is section-backed; once armed it receives its own guest-window view.
    current_teb = &wow_teb;
    win32u_wow_session = 0;
    before = publish_calls;
    win32u_gdi_check_publish();
    assert(publish_calls == before && wow.GdiSharedHandleTable == NULL && map_calls == 0);
    win32u_wow_session = 1;
    mock_guest_base = 0x7100000000ULL;
    win32u_gdi_check_publish();
    assert(publish_calls == before + 1 && wow.GdiSharedHandleTable == (void *)(mock_guest_base + 0x12340000));
    assert(map_calls == 1 && close_calls == 1 && mapping_errors == 0);
    before = publish_calls;
    win32u_gdi_check_publish();
    assert(publish_calls == before && map_calls == 1);
    wow.GdiSharedHandleTable = NULL;
    win32u_gdi_check_publish();
    assert(publish_calls == before + 1 && map_calls == 1 && wow.GdiSharedHandleTable != NULL);
    current_teb = &later_wow_teb;
    mock_guest_base = 0x7200000000ULL;
    win32u_gdi_check_publish();
    assert(later_wow.GdiSharedHandleTable == (void *)(mock_guest_base + 0x12340000) && map_calls == 2);

    // Compile and execute the actual native initialization entry point. Its
    // pthread_once callback runs once, but its publication hook runs per PEB.
    PEB init_parent = {0}, init_child = {0};
    TEB init_parent_teb = {&init_parent, 0, {(void *)5}};
    TEB init_child_teb = {&init_child, 0, {(void *)6}};
    ntuser_client_func_ptr a[NTUSER_NB_PROCS] = {{11}, {12}}, w[NTUSER_NB_PROCS] = {{21}, {22}};
    current_teb = &init_parent_teb;
    assert(NtUserInitializeClientPfnArrays(a, w, a, (void *)101) == STATUS_SUCCESS);
    assert(init_user_calls == 1 && init_parent.GdiSharedHandleTable == gdi_shared);
    current_teb = &init_child_teb;
    before = publish_calls;
    assert(NtUserInitializeClientPfnArrays(a, w, a, (void *)102) == STATUS_SUCCESS);
    assert(init_user_calls == 1 && publish_calls == before + 1 && init_child.GdiSharedHandleTable == gdi_shared);
    before = publish_calls;
    assert(NtUserInitializeClientPfnArrays(a, w, a, (void *)102) == STATUS_SUCCESS);
    assert(init_user_calls == 1 && publish_calls == before);
    assert(ios_client_procs_count == 2 && ios_client_procs_reg[0].peb == &init_parent && ios_client_procs_reg[1].peb == &init_child);
    puts("PASS: applied Wine GDI publication across 64-bit children, null-table retry, 32-bit section/window gating and native pthread_once client initialization");
    return 0;
}
'''
unit = args.build / 'child-gdi-publication.c'
unit.write_text(prelude + publish + wrapper + inline + registry + initialize + probe)
binary = args.build / 'child-gdi-publication'
command = ['xcrun', '--sdk', 'macosx', 'clang', '-std=c11', '-D_DARWIN_C_SOURCE',
           '-O1', '-g', '-fsanitize=address,undefined', '-pthread', str(unit), '-o', str(binary)]
subprocess.run(command, check=True)
subprocess.run([str(binary)], check=True)
(args.build / 'result.json').write_text(json.dumps({
    'status': 'pass', 'scope': __doc__,
    'appliedSourceSha256': {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in paths.items()},
    'extractedProbeSha256': hashlib.sha256(unit.read_bytes()).hexdigest(), 'command': command,
}, indent=2) + '\n')
