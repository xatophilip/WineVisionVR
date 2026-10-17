#!/usr/bin/env python3
"""Compile production mouse-activation routing; keep explicit eat decisions.

Platform calls are mocked, but the complete mouse-activation block is extracted
unchanged from both compiled native and Wine source paths of a prepared runtime.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import tempfile


def block(source):
    signature = 'if (msg->hwnd != info.hwndActive)'
    start = source.index(signature)
    opening = source.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-source', required=True, type=Path)
    parser.add_argument('--build', type=Path)
    args = parser.parse_args()
    native = args.runtime_source / 'build/win32u-unix/message_ios.c'
    wine = args.runtime_source / 'wine/dlls/win32u/message.c'
    actual = block(native.read_text())
    assert actual == block(wine.read_text()), 'Native and Wine routing must agree'
    code = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uintptr_t HWND, WPARAM;
typedef unsigned UINT, DWORD;
typedef int BOOL;
#define TRUE 1
#define FALSE 0
#define GA_ROOT 2
#define GWL_STYLE (-16)
#define WS_POPUP 0x80000000u
#define WS_CHILD 0x40000000u
#define WM_MOUSEACTIVATE 0x21
#define WM_LBUTTONDOWN 0x201
#define HTCLIENT 1
#define MA_ACTIVATE 1
#define MA_ACTIVATEANDEAT 2
#define MA_NOACTIVATE 3
#define MA_NOACTIVATEANDEAT 4
#define MAKELONG(lo, hi) ((uint32_t)(uint16_t)(lo) | ((uint32_t)(uint16_t)(hi) << 16))
#define WARN(...) ((void)0)
static HWND root_window = 0x10028, current_active;
static UINT activate_result;
static BOOL foreground_result;
static unsigned foreground_calls, activate_calls;
static DWORD root_style;
static HWND NtUserGetAncestor(HWND hwnd, UINT kind) {
 assert(hwnd && kind == GA_ROOT); return root_window;
}
static DWORD get_window_long(HWND hwnd, int field) {
 assert(hwnd == root_window && field == GWL_STYLE); return root_style;
}
static UINT send_message(HWND hwnd, UINT msg, WPARAM wp, uint32_t lp) {
 assert(hwnd && msg == WM_MOUSEACTIVATE && wp == root_window);
 assert(lp == MAKELONG(HTCLIENT, WM_LBUTTONDOWN));
 ++activate_calls; return activate_result;
}
static BOOL set_foreground_window(HWND hwnd, BOOL mouse, BOOL internal) {
 assert(hwnd == root_window && mouse && !internal);
 ++foreground_calls; if (foreground_result) current_active = hwnd;
 return foreground_result;
}
static HWND get_active_window(void) { return current_active; }
static BOOL route(HWND target, HWND active) {
 struct { HWND hwnd; UINT message; } message = {target, WM_LBUTTONDOWN}, *msg = &message;
 struct { HWND hwndActive; } info = {active};
 BOOL eat_msg = FALSE;
 int hittest = HTCLIENT;
'''+actual+r'''
 return !eat_msg;
}
static void check(UINT result, BOOL fg, HWND before, BOOL delivered, unsigned calls) {
 activate_result = result; foreground_result = fg; current_active = before;
 foreground_calls = activate_calls = 0; root_style = 0;
 assert(route(0x2003a, before) == delivered);
 assert(foreground_calls == calls && activate_calls == 1);
}
int main(void) {
 // Captured failure: active/foreground root is already0x10028, MA_ACTIVATE,
 // redundant activation reports failure. The button-down must reach control.
 check(MA_ACTIVATE, FALSE, root_window, TRUE, 1);
 check(0, FALSE, root_window, TRUE, 1);
 // Real activation failure while another root remains active still eats.
 check(MA_ACTIVATE, FALSE, 0x9999, FALSE, 1);
 check(0, FALSE, 0x9999, FALSE, 1);
 check(MA_ACTIVATE, TRUE, 0x9999, TRUE, 1);
 check(0, TRUE, 0x9999, TRUE, 1);
 // An application explicitly asking to eat keeps that decision, even when
 // activation succeeds or its requested root was already active.
 check(MA_ACTIVATEANDEAT, FALSE, root_window, FALSE, 1);
 check(MA_ACTIVATEANDEAT, FALSE, 0x9999, FALSE, 1);
 check(MA_ACTIVATEANDEAT, TRUE, 0x9999, FALSE, 1);
 check(MA_NOACTIVATEANDEAT, FALSE, root_window, FALSE, 0);
 check(MA_NOACTIVATEANDEAT, TRUE, 0x9999, FALSE, 0);
 check(MA_NOACTIVATE, FALSE, root_window, TRUE, 0);
 check(MA_NOACTIVATE, FALSE, 0x9999, TRUE, 0);
 // Already-active target and child-only roots bypass activation as before.
 activate_calls = foreground_calls = 0; current_active = root_window;
 assert(route(root_window, root_window));
 assert(!activate_calls && !foreground_calls);
 root_style = WS_CHILD;
 assert(route(0x2003a, root_window));
 assert(!activate_calls && !foreground_calls);
 puts("PASS: captured active-root click, inactive failure, successful activation, explicit eat/noactivate and activation bypasses");
}
'''
    output = args.build or Path(tempfile.mkdtemp(prefix='wvr-mouse-activation-'))
    output.mkdir(parents=True, exist_ok=True)
    unit = output / 'mouse-activation.c'
    unit.write_text(code)
    command = ['xcrun', 'clang', '-std=c11', '-O1', '-g', '-fsanitize=address,undefined',
               '-fno-omit-frame-pointer', str(unit), '-o', str(output / 'mouse-activation')]
    print(shlex.join(command), flush=True)
    subprocess.run(command, check=True)
    result = subprocess.run([str(output / 'mouse-activation')], capture_output=True, text=True)
    print(result.stdout, end='')
    print(result.stderr, end='')
    result.check_returncode()
    (output / 'result.json').write_text(json.dumps({
        'passed': True, 'command': command, 'result': result.stdout.strip(),
        'sourceSHA256': {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in (native, wine)},
    }, indent=2)+'\n')


if __name__ == '__main__':
    main()
