#!/usr/bin/env python3
"""Run native handle regressions and compile real i386 overflow guards to IR."""
from pathlib import Path
import argparse, json, subprocess
p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--llvm-mingw',type=Path,required=True);a=p.parse_args()
r=a.build.resolve();r.mkdir(parents=True,exist_ok=True);root=Path(__file__).resolve().parents[2]
includes=['-I',str(root/'third-party/openxr/include'),'-I',str(root/'windows-vr-openxr/include')]
source=r/'handles.cpp'
source.write_text('''#include "WindowsVRHandles.h"
#include <cassert>
struct Resource {int marker;};
extern "C" Resource* roundtrip(Resource*p){return WVRPointerFromHandle<Resource>(WVRHandleFromPointer<XrInstance>(p));}
#if XR_PTR_SIZE == 4
static_assert(sizeof(XrInstance)==8);
extern "C" Resource* rejectHighBits(){return WVRPointerFromHandle<Resource>(XrInstance{0x100001234ULL});}
extern "C" Resource* rejectMax(){return WVRPointerFromHandle<Resource>(XrInstance{0xffffffffffffffffULL});}
#endif
int main(){Resource value{42};assert(roundtrip(&value)==&value);assert(roundtrip(nullptr)==nullptr);
#if XR_PTR_SIZE == 4
assert(!rejectHighBits()&&!rejectMax());
#endif
return 0;}
''')
exe=r/'handles-native';subprocess.run(['clang++','-std=c++20','-fsanitize=address,undefined',*includes,str(source),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
cc=str(a.llvm_mingw.resolve()/'bin/i686-w64-mingw32-clang++')
subprocess.run([cc,'-std=c++20','-O2','-S','-emit-llvm',*includes,str(source),'-o',str(r/'handles-i386.ll')],check=True)
ir=(r/'handles-i386.ll').read_text()
for name in ['rejectHighBits','rejectMax']:
 body=ir.split('@'+name+'(',1)[1].split('}',1)[0]
 assert 'ret ptr null' in body,body
body=ir.split('@roundtrip(',1)[1].split('}',1)[0];assert 'ret ptr %0' in body,body
subprocess.run([cc,'-std=c++20','-O2','-static',*includes,str(source),'-o',str(r/'handles-i386.exe')],check=True)
(r/'handle-result.json').write_text(json.dumps({'nativeASanUBSan':'passed','i386Compiler':'i686-w64-mingw32','i386PointerSize':4,'openxrHandleSize':8,'i386RoundtripIR':'identity','i386HighBitsIR':'returns null','i386MaxIR':'returns null','i386ExecutableLinked':True,'i386Executed':False},indent=2)+'\n')
print('PASS: native handle roundtrip/null ASan+UBSan; actual i386 IR rejects upper bits without truncation; i386 PE linked, not executed')
