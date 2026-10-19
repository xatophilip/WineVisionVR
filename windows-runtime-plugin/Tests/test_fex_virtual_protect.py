#!/usr/bin/env python3
"""Execute the actual FEX Win32 protection wrapper against a validating provider."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[2]
PATCH=ROOT/"windows-runtime-plugin/patches/0021-fex-win32-virtual-protect.patch"

def helper(text):
    start=text.index("inline bool VirtualProtect(void* Ptr, size_t Size, ProtectOptions options)")
    end=text.index("\n}",start)+2
    return text[start:end]

PREAMBLE=r"""
#include <cstdint>
#include <cstdio>
#include <cerrno>
using DWORD=uint32_t;
using BOOL=int;
constexpr DWORD PAGE_NOACCESS=1,PAGE_READONLY=2,PAGE_READWRITE=4,
 PAGE_EXECUTE_READ=0x20,PAGE_EXECUTE_READWRITE=0x40;
enum class ProtectOptions:uint32_t {None=0,Read=1,Write=2,Exec=4};
constexpr ProtectOptions operator|(ProtectOptions a,ProtectOptions b) {
 return static_cast<ProtectOptions>(static_cast<uint32_t>(a)|static_cast<uint32_t>(b));
}
#define LOGMAN_MSG_A_FMT(...) do {} while(0)
static int calls,bad_argument,expected_result;
static unsigned last_error;
static void *expected_pointer;
static size_t expected_size;
static DWORD expected_protection;
static BOOL VirtualProtect(void *ptr,size_t size,DWORD prot,DWORD *previous) {
 ++calls;
 if (ptr!=expected_pointer || size!=expected_size || prot!=expected_protection || !previous) {
  ++bad_argument;last_error=87;return 0;
 }
 *previous=PAGE_READWRITE;
 last_error=expected_result ? 0x12345678u : 0x87654321u;
 return expected_result;
}
namespace FEXCore { namespace Allocator {
"""
POSTAMBLE=r"""
}}
int main() {
 struct Mapping { ProtectOptions options; DWORD protection; };
 const Mapping mappings[]={
  {ProtectOptions::None,PAGE_NOACCESS},
  {ProtectOptions::Read,PAGE_READONLY},
  {ProtectOptions::Read|ProtectOptions::Write,PAGE_READWRITE},
  {ProtectOptions::Read|ProtectOptions::Exec,PAGE_EXECUTE_READ},
  {ProtectOptions::Read|ProtectOptions::Write|ProtectOptions::Exec,PAGE_EXECUTE_READWRITE}
 };
 unsigned failed=0;
 for (const auto &mapping:mappings) for (int success:{0,1}) {
  char allocation[8192];
  expected_pointer=allocation+17;expected_size=4097;
  expected_protection=mapping.protection;expected_result=success;
  calls=bad_argument=0;last_error=0;errno=EDOM;
  bool got=FEXCore::Allocator::VirtualProtect(expected_pointer,expected_size,mapping.options);
  if (got!=(success!=0) || calls!=1 || bad_argument ||
      last_error!=(success ? 0x12345678u : 0x87654321u) || errno!=EDOM) {
   ++failed;
   fprintf(stderr,"mapping=%x success=%d got=%d calls=%d badarg=%d lastError=%x\n",
           mapping.protection,success,got,calls,bad_argument,last_error);
  }
 }
 return failed ? 1 : 0;
}
"""

def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument("--runtime-source",required=True,type=Path)
 ap.add_argument("--output-dir",type=Path)
 args=ap.parse_args()
 source=args.runtime_source/"FEX/FEXCore/include/FEXCore/Utils/AllocatorHooks.h"
 original=source.read_text()
 with tempfile.TemporaryDirectory(prefix="wvr-virtual-protect-") as td:
  work=Path(td);dest=work/"FEX/FEXCore/include/FEXCore/Utils/AllocatorHooks.h"
  dest.parent.mkdir(parents=True);dest.write_text(original)
  installed="DWORD previous_protection;" in helper(original)
  subprocess.run(["git","apply",*(["--reverse"] if installed else []),str(PATCH)],
                 cwd=work,check=True,capture_output=True)
  counterpart=dest.read_text()
  old,new=(counterpart,original) if installed else (original,counterpart)
  results=[]
  for name,text,expected in [("old-negative-control",old,1),("patched",new,0)]:
   code=PREAMBLE+helper(text)+POSTAMBLE
   c=work/(name+".cpp");exe=work/name;c.write_text(code)
   subprocess.run(["xcrun","clang++","-std=c++17","-include","initializer_list",
                   "-fsanitize=address,undefined","-fno-omit-frame-pointer",str(c),"-o",str(exe)],check=True)
   run=subprocess.run([str(exe)],capture_output=True,text=True)
   assert run.returncode==expected,(name,run.returncode,run.stderr)
   results.append({"name":name,"exitCode":run.returncode,"expectedExitCode":expected,
                   "stderr":run.stderr})
  receipt={"source":str(source),"sourceSha256":hashlib.sha256(source.read_bytes()).hexdigest(),
           "patchSha256":hashlib.sha256(PATCH.read_bytes()).hexdigest(),
           "patchedSourceSha256":hashlib.sha256(new.encode()).hexdigest(),
           "casesPerVariant":10,"tests":results,"deviceTested":False,"nativeRuntimeBuilt":False}
  if args.output_dir:
   args.output_dir.mkdir(parents=True,exist_ok=True)
   (args.output_dir/"result.json").write_text(json.dumps(receipt,indent=2)+"\n")
  print(json.dumps(receipt,indent=2))
if __name__=="__main__":main()
