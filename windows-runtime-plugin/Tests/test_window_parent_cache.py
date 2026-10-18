#!/usr/bin/env python3
"""Compile actual Wine parent traversal before/after the cache-fallback patch.

Mock only object-cache and server boundaries. Exercise the complete production
get_win_ptr, list_window_parents, and NtUserGetAncestor functions with sanitizers.
Never modify the supplied runtime or execute Windows code.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-source', required=True, type=Path)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
args.build.mkdir(parents=True, exist_ok=True)
scratch = Path(tempfile.mkdtemp(prefix='parent-cache-', dir=args.build.resolve()))
relative = Path('wine/dlls/win32u/window.c')
original = args.runtime_source / relative
target = scratch / relative
target.parent.mkdir(parents=True)
shutil.copyfile(original, target)
patch = ROOT / 'windows-runtime-plugin/patches/0014-wine-parent-cache-fallback.patch'
def apply(*flags):
    return subprocess.run(['git', 'apply', *flags, str(patch)], cwd=scratch,
                          capture_output=True, text=True)
# A freshly prepared runtime already contains the patch; recover only the test
# copy's baseline so the same real regression is exercised in either case.
if apply('--check').returncode:
    result = apply('--reverse', '--check')
    assert result.returncode == 0, result.stderr
    result = apply('--reverse')
    assert result.returncode == 0, result.stderr
before = target.read_text()
result = apply()
assert result.returncode == 0, result.stderr
after = target.read_text()
def function(source, signature):
    start = source.index(signature)
    opening = source.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]

prefix = r"""
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef void *HWND, *HANDLE;
typedef unsigned UINT;
typedef int BOOL;
typedef uint32_t user_handle_t;
typedef struct { HWND parent; } WND;
#define TRUE 1
#define FALSE 0
#define GA_PARENT 1
#define GA_ROOT 2
#define GA_ROOTOWNER 3
#define ERROR_INVALID_WINDOW_HANDLE 1400
#define NTUSER_OBJ_WINDOW 1
#define WND_OTHER_PROCESS ((WND *)(uintptr_t)1)
#define WND_DESKTOP ((WND *)(uintptr_t)2)
#define H(n) ((HWND)(uintptr_t)(n))
static const HWND desktop = H(0x10022), root = H(0x10028), child = H(0x2003a);
struct node { HWND handle, server_parent; WND local; int cache; };
static struct node nodes[96];
static unsigned node_count, server_calls, locks, live_allocations, last_error;
static int fail_server, allocation_budget = -1;
static HWND last_query;
static struct node *node(HWND handle) {
    for (unsigned i=0; i<node_count; ++i) if (nodes[i].handle==handle) return nodes+i;
    return NULL;
}
static void add(HWND handle, HWND parent, int cache) {
    assert(node_count<96); nodes[node_count++]=(struct node){handle,parent,{parent},cache};
}
static void reset(void) {
    assert(!locks && !live_allocations);
    node_count=server_calls=last_error=0; fail_server=0; last_query=0; allocation_budget=-1;
    add(desktop,0,2); add(root,desktop,0); add(child,root,0);
}
static void *test_malloc(size_t size) {
    if (!allocation_budget) return NULL;
    if (allocation_budget>0) --allocation_budget;
    void *p=malloc(size); if(p) ++live_allocations; return p;
}
static void *test_realloc(void *p,size_t size) {
    if (!allocation_budget) return NULL;
    if (allocation_budget>0) --allocation_budget;
    return realloc(p,size);
}
static void test_free(void *p) { if(p) { assert(live_allocations); --live_allocations; } free(p); }
#define malloc test_malloc
#define realloc test_realloc
#define free test_free
static void *get_user_handle_ptr(HWND handle,unsigned type) {
    assert(type==NTUSER_OBJ_WINDOW);
    struct node *n=node(handle);
    if(!n || n->cache==1) return NULL;
    if(n->cache==2) return WND_OTHER_PROCESS;
    ++locks; return &n->local;
}
static BOOL is_desktop_window(HWND handle) { return handle==desktop; }
static void release_win_ptr(WND *win) { assert(win && locks); --locks; }
static void RtlSetLastWin32Error(unsigned value) { last_error=value; }
static HWND get_full_window_handle(HWND handle) { return node(handle) ? handle : NULL; }
static HWND get_parent(HWND handle) {
    struct node *n=node(handle); return n && handle!=root && handle!=desktop ? n->server_parent : NULL;
}
struct reply { int count; uint32_t parent; };
struct request { const char *kind; uint32_t handle; void *output; size_t bytes; struct reply *reply; };
#define SERVER_START_REQ(kind) do { struct reply response={0}; \
    struct request request={#kind,0,NULL,0,&response}, *req=&request; struct reply *reply=&response;
#define SERVER_END_REQ } while(0)
static uint32_t wine_server_user_handle(HWND handle) { return (uint32_t)(uintptr_t)handle; }
static HWND wine_server_ptr_handle(uint32_t handle) { return H(handle); }
static void wine_server_set_reply(struct request *r,void *output,size_t bytes) { r->output=output;r->bytes=bytes; }
static int wine_server_call(struct request *r) {
    ++server_calls; last_query=H(r->handle);
    struct node *n=node(last_query);
    if(fail_server || !n) return 1;
    if(!strcmp(r->kind,"get_window_tree")) { r->reply->parent=(uint32_t)(uintptr_t)n->server_parent; return 0; }
    assert(!strcmp(r->kind,"get_window_parents"));
    HWND current=n->server_parent;
    while(current) {
        unsigned i=(unsigned)r->reply->count++;
        assert(i<96); n=node(current); if(!n) return 1;
        if((i+1)*sizeof(uint32_t)<=r->bytes) ((uint32_t *)r->output)[i]=(uint32_t)(uintptr_t)current;
        current=n->server_parent;
    }
    return 0;
}
#define wine_server_call_err wine_server_call
"""
tests = r"""
static void clean(void) { assert(!live_allocations && !locks); }
int main(void) {
    reset();
    assert(NtUserGetAncestor(child,GA_PARENT)==root);
    assert(NtUserGetAncestor(root,GA_PARENT)==desktop);
    assert(NtUserGetAncestor(child,GA_ROOT)==root);
    assert(NtUserGetAncestor(root,GA_ROOT)==root);
    assert(NtUserGetAncestor(child,GA_ROOTOWNER)==root);
    assert(!server_calls); clean();
    node(desktop)->cache=1;
#ifdef EXPECT_BASELINE
    assert(!NtUserGetAncestor(child,GA_ROOT));
    assert(!NtUserGetAncestor(root,GA_ROOT));
    assert(!server_calls); clean();
    puts("PASS: unpatched production traversal reproduces valid-parent/zero-root failure with absent desktop WND");
    return 0;
#else
    assert(NtUserGetAncestor(child,GA_ROOT)==root && last_query==child);
    assert(NtUserGetAncestor(root,GA_ROOT)==root && last_query==root);
    assert(NtUserGetAncestor(child,GA_ROOTOWNER)==root); clean();
    puts("PASS: server chain recovers root/child when desktop cache entry is absent");
    reset(); node(child)->cache=1;
    assert(NtUserGetAncestor(child,GA_ROOT)==root && last_query==child); clean();
    reset(); node(child)->cache=2;
    assert(NtUserGetAncestor(child,GA_ROOT)==root && last_query==child); clean();
    reset(); node(child)->local.parent=H(0xfeed);
    assert(NtUserGetAncestor(child,GA_ROOT)==root && last_query==child); clean();
    puts("PASS: missing child, cross-process and stale partial-cache chains query original HWND");
    reset();
    assert(!NtUserGetAncestor(H(0x9999),GA_ROOT));
    assert(!NtUserGetAncestor(H(0x3003a),GA_ROOT)); /* stale generation */
    assert(!last_error); clean();
    node(child)->cache=1; fail_server=1;
    assert(!NtUserGetAncestor(child,GA_ROOT)); clean();
    reset(); node(desktop)->cache=1;
    assert(!NtUserGetAncestor(desktop,GA_ROOT)); clean();
    assert(!NtUserGetAncestor(NULL,GA_ROOT)); clean();
    puts("PASS: invalid/stale handles, server failure and empty desktop chain remain empty");
    reset(); allocation_budget=0;
    assert(!NtUserGetAncestor(child,GA_ROOT) && !server_calls); clean();
    reset();
    HWND deep=root;
    for(unsigned i=0;i<24;++i) { HWND next=H(0x40000+i*2); add(next,deep,0);deep=next; }
    assert(NtUserGetAncestor(deep,GA_ROOT)==root && !server_calls); clean();
    allocation_budget=1;
    assert(!NtUserGetAncestor(deep,GA_ROOT)); clean(); /* realloc failure */
    allocation_budget=-1; node(deep)->cache=1;
    assert(NtUserGetAncestor(deep,GA_ROOT)==root && server_calls==2 && last_query==deep); clean();
    puts("PASS: local growth, packed server-handle expansion, terminator and allocation-failure cleanup");
#endif
}
"""
commands=[]
for label, source in [('before',before),('after',after)]:
    functions='\n'.join(function(source,s) for s in [
        'WND *get_win_ptr(', 'static HWND *list_window_parents(', 'HWND WINAPI NtUserGetAncestor('])
    unit=scratch/(label+'.c')
    unit.write_text(prefix+'\n#define WINAPI\n'+functions+'\n'+tests)
    binary=scratch/label
    command=['xcrun','clang','-std=c11','-O1','-g','-fsanitize=address,undefined',
             '-fno-omit-frame-pointer',str(unit),'-o',str(binary)]
    if label=='before': command.insert(2,'-DEXPECT_BASELINE')
    subprocess.run(command,check=True)
    result=subprocess.run([str(binary)],capture_output=True,text=True)
    print(result.stdout,end='');print(result.stderr,end='')
    result.check_returncode()
    commands.append(command)
(args.build/'result.json').write_text(json.dumps({
    'passed':True,'commands':commands,
    'runtimeSourceFileSHA256':hashlib.sha256(original.read_bytes()).hexdigest(),
    'patchSHA256':hashlib.sha256(patch.read_bytes()).hexdigest(),
    'patchedSourceSHA256':hashlib.sha256(after.encode()).hexdigest(),
    'scope':'Actual production functions; mocked local object-cache and authoritative server boundary; no device execution'
},indent=2)+'\n')
