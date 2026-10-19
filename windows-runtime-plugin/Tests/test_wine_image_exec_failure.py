#!/usr/bin/env python3
"""Compile the actual image-protection tail with injected allocation/protection failures.

No Wine, executable mappings, or device are used. Also executes the pre-patch tail
to prove the captured failure was incorrectly reported as success.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
PATCH = ROOT / "windows-runtime-plugin/patches/0020-wine-image-exec-failure.patch"

def block(text):
    start = text.index("    set_vprot( view, ptr, ROUND_SIZE( 0, header_size, align_mask )",
                       text.index("static NTSTATUS map_image_into_view("))
    end = text.index("\n}\n", start)
    return text[start:end]

PREAMBLE = r"""
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
typedef uint32_t NTSTATUS;
typedef size_t SIZE_T;
typedef unsigned char BYTE;
#define STATUS_SUCCESS 0u
#define STATUS_NO_MEMORY 0xc0000017u
#define STATUS_ACCESS_DENIED 0xc0000022u
#define VPROT_COMMITTED 1
#define VPROT_READ 2
#define VPROT_WRITECOPY 4
#define VPROT_EXEC 8
#define IMAGE_SCN_MEM_READ 0x40000000u
#define IMAGE_SCN_MEM_WRITE 0x80000000u
#define IMAGE_SCN_MEM_EXECUTE 0x20000000u
#define PROT_READ 1
#define PROT_WRITE 2
#define PROT_EXEC 4
#define ROUND_SIZE(addr,size,mask) (((addr)+(size)+(mask)) & ~(mask))
#define ERR(...) do { errno = EIO; } while (0) /* logging must not alter mapped status */
static int set_calls, exec_calls, fail_set, fail_exec, injected_errno;
static int section_free_count, simulated_tls_count, simulated_view_delete_count;
static void tracked_free(void *p) { section_free_count++; free(p); }
#define free tracked_free
static int set_vprot(void *v, void *p, size_t s, unsigned prot) {
    (void)v;(void)p;(void)s;(void)prot;
    if (++set_calls == fail_set) { errno=injected_errno; return 0; }
    return 1;
}
static int mprotect_exec(void *p, size_t s, int prot) {
    (void)p;(void)s;(void)prot;
    if (++exec_calls == fail_exec) { errno=injected_errno; return -1; }
    return 0;
}
struct section { unsigned VirtualAddress; struct { unsigned VirtualSize; } Misc;
    unsigned SizeOfRawData, Characteristics; char Name[8]; };
struct headers { struct { unsigned NumberOfSections; } FileHeader; };
static NTSTATUS image_tail(void) {
    struct headers h = {{2}}, *nt=&h;
    struct section *sections=calloc(2,sizeof(*sections)), *sec=sections;
    char memory[16384], *ptr=memory;
    void *view=0;
    SIZE_T header_size=128, align_mask=4095;
    NTSTATUS status=0xdeadbeefu;
    int i;
    sec[0].VirtualAddress=4096; sec[0].Misc.VirtualSize=4096;
    sec[0].Characteristics=IMAGE_SCN_MEM_READ|IMAGE_SCN_MEM_EXECUTE;
    sec[1].VirtualAddress=8192; sec[1].SizeOfRawData=4096;
    sec[1].Characteristics=IMAGE_SCN_MEM_READ|IMAGE_SCN_MEM_EXECUTE|IMAGE_SCN_MEM_WRITE;
"""
POSTAMBLE = r"""
}
static int run_case(int fs,int fe,int error,NTSTATUS expected,int expected_exec) {
    set_calls=exec_calls=section_free_count=simulated_tls_count=simulated_view_delete_count=0;
    fail_set=fs; fail_exec=fe; injected_errno=error; errno=0;
    NTSTATUS got=image_tail();
    /* Mirrors the existing caller's success-only registration and delete_view
       failure branch, without pretending to execute Wine's real TLS machinery. */
    if (!got) simulated_tls_count++; else simulated_view_delete_count++;
    if (got!=expected || section_free_count!=1 || exec_calls!=expected_exec ||
        simulated_tls_count!=(expected==0) || simulated_view_delete_count!=(expected!=0)) {
        fprintf(stderr,"case set=%d eager=%d errno=%d got=%08x expected=%08x free=%d exec=%d\n",
                fs,fe,error,got,expected,section_free_count,exec_calls);
        return 1;
    }
    return 0;
}
int main(void) {
    int failed=0;
#ifdef WINE_IOS
    failed+=run_case(0,0,0,STATUS_SUCCESS,2);
    failed+=run_case(2,0,ENOMEM,STATUS_NO_MEMORY,0);
    failed+=run_case(3,0,EACCES,STATUS_ACCESS_DENIED,0);
    failed+=run_case(2,0,0,STATUS_ACCESS_DENIED,0);
    failed+=run_case(0,1,ENOMEM,STATUS_NO_MEMORY,1);
    failed+=run_case(0,2,EPERM,STATUS_ACCESS_DENIED,2);
#else
    failed+=run_case(0,0,0,STATUS_SUCCESS,0);
    failed+=run_case(2,0,ENOMEM,STATUS_SUCCESS,0);
#endif
    return failed ? 1 : 0;
}
"""

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--runtime-source",type=Path,required=True)
    ap.add_argument("--output-dir",type=Path)
    args=ap.parse_args()
    source=args.runtime_source/"build/ntdll-unix/virtual_ios.c"
    original=source.read_text()
    assert "else delete_view( view );" in original
    fn=original[original.index("static NTSTATUS virtual_map_image("):]
    assert fn.index("status = map_image_into_view(")<fn.index("SERVER_START_REQ( map_image_view )")
    with tempfile.TemporaryDirectory(prefix="wvr-image-failure-") as td:
        work=Path(td); dest=work/"build/ntdll-unix/virtual_ios.c"
        dest.parent.mkdir(parents=True);dest.write_text(original)
        installed="iOS: refusing image %s: executable section" in original
        subprocess.run(["git","apply",*(["--reverse"] if installed else []),str(PATCH)],
                       cwd=work,check=True,capture_output=True)
        counterpart=dest.read_text()
        old,new=(counterpart,original) if installed else (original,counterpart)
        results=[]
        for name,body,ios,expected in [
            ("old-ios-negative-control",old,True,1),
            ("patched-ios",new,True,0),
            ("patched-other-platform",new,False,0)]:
            c=work/(name+".c");exe=work/name
            c.write_text(PREAMBLE+block(body)+POSTAMBLE)
            command=["xcrun","clang","-std=c11","-Werror=implicit-function-declaration",
                     "-fsanitize=address,undefined","-fno-omit-frame-pointer",
                     *(["-DWINE_IOS"] if ios else []),str(c),"-o",str(exe)]
            subprocess.run(command,check=True)
            run=subprocess.run([str(exe)],capture_output=True,text=True)
            assert run.returncode==expected,(name,run.returncode,run.stderr)
            results.append({"name":name,"exitCode":run.returncode,
                            "expectedExitCode":expected,"stderr":run.stderr})
        receipt={"source":str(source),"sourceSha256":hashlib.sha256(source.read_bytes()).hexdigest(),
                 "patchSha256":hashlib.sha256(PATCH.read_bytes()).hexdigest(),
                 "patchedSourceSha256":hashlib.sha256(new.encode()).hexdigest(),
                 "tests":results,"deviceTested":False,"nativeRuntimeBuilt":False}
        if args.output_dir:
            args.output_dir.mkdir(parents=True,exist_ok=True)
            (args.output_dir/"result.json").write_text(json.dumps(receipt,indent=2)+"\n")
        print(json.dumps(receipt,indent=2))
if __name__=="__main__": main()
