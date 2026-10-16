#!/usr/bin/env python3
"""Checks actual production-generated thunks using mixed Windows C++ ABIs.

The failing control must report an incorrect this pointer; the bridge must preserve
both matrix returns, the receiver canary and a qualified internal call.
This executes under host Wine and does not establish FEX/headset compatibility.
"""
from pathlib import Path
import sys,io,subprocess,os,json
import argparse, shutil
parser=argparse.ArgumentParser(description="Run the production OpenComposite matrix-return bridge across actual MSVC and MinGW Windows objects.")
parser.add_argument('--source',type=Path,required=True,help='Pinned clean OpenComposite source with scripts/stubs dependencies')
parser.add_argument('--build',type=Path,required=True)
parser.add_argument('--llvm-mingw',type=Path,required=True)
parser.add_argument('--wine',type=Path,required=True,help='Host Windows x64 Wine executable, not WineIOS')
parser.add_argument('--wine-prefix',type=Path,required=True,help='Existing isolated host test prefix')
args=parser.parse_args()
r=args.build.resolve();r.mkdir(parents=True,exist_ok=True)
up=args.source.resolve()
patched=r/'patched-source';patched.mkdir(exist_ok=False)
for rel in ['scripts/stubs/codegen.py','OpenOVR/BaseCommon.h','OCOVR/openvr_api.cpp']:
 p=patched/rel;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(up/rel,p)
patch=Path(__file__).resolve().parents[1]/'patches/0007-mingw-msvc-aggregate-return.patch'
subprocess.run(['git','apply',str(patch)],cwd=patched,check=True)
sys.path.insert(0,str(up/'scripts'))
ns={};exec((patched/'scripts/stubs/codegen.py').read_text(),ns)
class F:
 def __init__(self,name,ret):self.name=name;self.return_type=ret
 def args_str(self):return 'int eye, float nearZ, float farZ'
 def args_names(self):return 'eye, nearZ, farZ'
class V:
 functions=[F('matrix44','HmdMatrix44_t'),F('matrix34','HmdMatrix34_t')]
 def proxy_class_name(self):return 'Probe'
fi=io.StringIO();ns['_write_msabi_thunks'](fi,V()); ns['_write_deleter'](fi,V())
pre='''#include <windows.h>
extern "C" { int _fltused = 0; }
struct HmdMatrix44_t { float m[16]; };
struct HmdMatrix34_t { float m[12]; };
struct Probe;
Probe *expected;
bool wrongThis;
int deleted;
struct NativeAPI {
 virtual HmdMatrix44_t matrix44(int,float,float)=0;
 virtual HmdMatrix34_t matrix34(int,float,float)=0;
};
struct Common {
 virtual ~Common() {}
 virtual void Delete()=0;
 virtual void _PrepareMSABI() {}
};
struct Probe : NativeAPI, Common {
 ~Probe() override { ++deleted; }
 void Delete() override;
 virtual HmdMatrix44_t matrix44(int eye,float n,float f) {
   HmdMatrix44_t result{};
   if (this!=expected) {wrongThis=true; return result;}
   for(int i=0;i<16;++i)result.m[i]=float(i)+eye+n+f;
   return result;
 }
 virtual HmdMatrix34_t matrix34(int eye,float n,float f) {
   HmdMatrix34_t result{};
   if (this!=expected) {wrongThis=true; return result;}
   for(int i=0;i<12;++i)result.m[i]=float(i)+eye+n+f;
   return result;
 }
 void _PrepareMSABI() override;
 void **_nativeVTable = nullptr;
 void *_msVTable[2];
 unsigned long long guard=0x123456789abcdef0ULL;
 char padding[128]{};
};
extern "C" int msvcCaller(void *p);
'''
post='''
int main() {
 Probe &p=*new Probe;expected=&p;
#if PREPARE
 p._PrepareMSABI();
#endif
 int result=msvcCaller(&p);
 if(wrongThis)ExitProcess(41);
 if(p.guard!=0x123456789abcdef0ULL)ExitProcess(42);
 if(result)ExitProcess(result);
 // Native internal/FnTable calls must bypass the outward vtable.
 auto m=p.Probe::matrix44(2,3,4);
 if(m.m[15]!=24)ExitProcess(43);
 Common *common=&p;
 common->Delete();
 if(deleted!=1)ExitProcess(44);
 ExitProcess(0);
}
'''
(r/'bridge.cpp').write_text(pre+fi.getvalue()+post)
(r/'msvc-caller.cpp').write_text('''struct HmdMatrix44_t {float m[16];}; struct HmdMatrix34_t{float m[12];};
struct API {virtual HmdMatrix44_t matrix44(int,float,float)=0;virtual HmdMatrix34_t matrix34(int,float,float)=0;};
extern "C" int msvcCaller(void *p) {
 auto *api=(API*)p;
 auto a=api->matrix44(2,3,4);
 if(a.m[0]!=9 || a.m[15]!=24)return 51;
 auto b=api->matrix34(5,6,7);
 if(b.m[0]!=18 || b.m[11]!=29)return 52;
 return 0;
}
''')
cc=str(args.llvm_mingw.resolve()/'bin/clang++')
subprocess.run([cc,'--target=x86_64-pc-windows-msvc','-c','-O1','-fno-exceptions','-fno-rtti',str(r/'msvc-caller.cpp'),'-o',str(r/'msvc-caller.obj')],check=True)
wine=str(args.wine.resolve())
env=os.environ.copy();env['WINEPREFIX']=str(args.wine_prefix.resolve());env['WINEDEBUG']='-all'
results={}
for prepare in [0,1]:
 exe=r/f'probe-{prepare}.exe'
 subprocess.run([cc,'--target=x86_64-w64-mingw32','-O1','-static',f'-DPREPARE={prepare}',str(r/'bridge.cpp'),str(r/'msvc-caller.obj'),'-o',str(exe)],check=True)
 result=subprocess.run([wine,str(exe)],env=env,capture_output=True,text=True,timeout=30)
 results[str(prepare)]={'returncode':result.returncode,'stderr':result.stderr[-1500:]}
 assert result.returncode==(41 if prepare==0 else 0),results
(r/'bridge-result.json').write_text(json.dumps({'scope':'Production generator thunks called by actual MSVC-ABI object linked with MinGW implementation; host macOS Wine/Rosetta, not headset FEX','results':results},indent=2)+'\n')
print('PASS: unbridged MSVC call uses wrong this (41); production generated bridge preserves both matrices, object canary, native qualified call and complete destruction (0)')
