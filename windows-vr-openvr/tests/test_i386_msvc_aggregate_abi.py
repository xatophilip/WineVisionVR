#!/usr/bin/env python3
"""Build actual MSVC-i386 callers against production-generated MinGW adapters.

Compiler IR checks cover all five OpenVR POD returns, including the 8-byte mesh.
Pass --wine and --wine-prefix to execute the positive and failing-control EXEs.
A compile-only result is explicitly recorded as not runtime-tested.
"""
from pathlib import Path
import argparse, io, json, os, re, shutil, subprocess, sys
p=argparse.ArgumentParser()
p.add_argument('--source',type=Path,required=True)
p.add_argument('--build',type=Path,required=True)
p.add_argument('--llvm-mingw',type=Path,required=True)
p.add_argument('--wine',type=Path)
p.add_argument('--wine-prefix',type=Path)
a=p.parse_args()
if bool(a.wine)!=bool(a.wine_prefix):p.error('--wine and --wine-prefix must be supplied together')
r=a.build.resolve();r.mkdir(parents=True,exist_ok=True)
up=a.source.resolve();patched=r/'patched-source';patched.mkdir(exist_ok=False)
for rel in ['scripts/stubs/codegen.py','OpenOVR/BaseCommon.h','OCOVR/openvr_api.cpp']:
 d=patched/rel;d.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(up/rel,d)
root=Path(__file__).resolve().parents[1]
for name in ['0007-mingw-msvc-aggregate-return.patch','0009-i386-msvc-aggregate-return.patch']:
 subprocess.run(['git','apply',str(root/'patches'/name)],cwd=patched,check=True)
sys.path.insert(0,str(up/'scripts'));ns={};exec((patched/'scripts/stubs/codegen.py').read_text(),ns)
types=['HmdMatrix44_t','HmdMatrix34_t','DistortionCoordinates_t','HiddenAreaMesh_t','HmdColor_t']
class F:
 def __init__(self,n,t):self.name='method'+str(n);self.return_type=t
 def args_str(self):return 'int eye, float nearZ, float farZ'
 def args_names(self):return 'eye, nearZ, farZ'
class V:
 functions=[F(n,t) for n,t in enumerate(types)]
 def proxy_class_name(self):return 'Probe'
f=io.StringIO();ns['_write_msabi_thunks'](f,V());ns['_write_deleter'](f,V())
shared='''struct HmdMatrix44_t {float v[16];}; struct HmdMatrix34_t {float v[12];};
struct DistortionCoordinates_t {float v[6];};struct HiddenAreaMesh_t {void *ptr;unsigned count;};struct HmdColor_t {float v[4];};
struct API {'''+''.join('virtual '+t+' method'+str(n)+'(int,float,float)=0;' for n,t in enumerate(types))+'''};
'''
methods=[]
for n,t in enumerate(types):
 body=('result.ptr=this;result.count=unsigned(eye+nearZ+farZ);' if t=='HiddenAreaMesh_t' else 'for(unsigned i=0;i<sizeof(result)/sizeof(float);++i)result.v[i]=i+eye+nearZ+farZ;')
 methods.append(t+' method'+str(n)+'(int eye,float nearZ,float farZ) override {'+t+' result{};if(this!=expected){wrongThis=true;return result;}'+body+'return result;}')
bridge='''#include <windows.h>
extern "C" {int _fltused=0;}
'''+shared+'''struct Probe;Probe*expected;bool wrongThis;int deleted;
struct Common {virtual ~Common(){}virtual void Delete()=0;virtual void _PrepareMSABI(){}};
struct Probe:API,Common {~Probe()override{++deleted;}void Delete()override;
'''+''.join(methods)+'''void _PrepareMSABI()override;void**_nativeVTable=nullptr;void*_msVTable[5];unsigned long long guard=0x123456789abcdef0ULL;};
extern "C" int msvcCaller(void*);
'''+f.getvalue()+'''int main(){
const wchar_t *resultPath=L"C:\\\\wvr-abi32-result.txt";
if(!DeleteFileW(resultPath)&&GetLastError()!=ERROR_FILE_NOT_FOUND&&GetLastError()!=ERROR_PATH_NOT_FOUND)ExitProcess(46);
Probe&p=*new Probe;expected=&p;
#if PREPARE
p._PrepareMSABI();
#endif
int result=msvcCaller(&p);if(wrongThis)ExitProcess(41);if(p.guard!=0x123456789abcdef0ULL)ExitProcess(42);if(result)ExitProcess(result);
if(p.Probe::method0(2,3,4).v[15]!=24)ExitProcess(43);Common*c=&p;c->Delete();if(deleted!=1)ExitProcess(44);
const char sentinel[]="PASS i386 MSVC OpenVR ABI: 5 POD returns; canary; native call; complete deletion\\n";
HANDLE file=CreateFileW(resultPath,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);
if(file==INVALID_HANDLE_VALUE)ExitProcess(45);
DWORD written=0;BOOL saved=WriteFile(file,sentinel,sizeof(sentinel)-1,&written,NULL);
BOOL flushed=FlushFileBuffers(file);BOOL closed=CloseHandle(file);
if(!saved||written!=sizeof(sentinel)-1||!flushed||!closed)ExitProcess(45);
ExitProcess(0);}
'''
caller=shared+'''extern "C" int msvcCaller(void*p){API*api=(API*)p;
'''
for n,t in enumerate(types):
 caller+='auto r'+str(n)+'=api->method'+str(n)+'(2,3,4);'
 caller+=('if(r3.ptr!=p||r3.count!=9)return 54;' if t=='HiddenAreaMesh_t' else 'if(r'+str(n)+'.v[0]!=9||r'+str(n)+'.v[sizeof(r'+str(n)+')/sizeof(float)-1]!=8+sizeof(r'+str(n)+')/sizeof(float))return '+str(51+n)+';')
caller+='return 0;}\n'
(r/'bridge.cpp').write_text(bridge);(r/'msvc-caller.cpp').write_text(caller)
cc=str(a.llvm_mingw.resolve()/'bin/clang++')
subprocess.run([cc,'--target=i686-pc-windows-msvc','-c','-O1','-fno-exceptions','-fno-rtti',str(r/'msvc-caller.cpp'),'-o',str(r/'msvc-caller.obj')],check=True)
subprocess.run([cc,'--target=i686-pc-windows-msvc','-S','-emit-llvm','-O0',str(r/'msvc-caller.cpp'),'-o',str(r/'msvc-caller.ll')],check=True)
ir=(r/'msvc-caller.ll').read_text()
calls=[x for x in ir.splitlines() if 'call x86_thiscallcc' in x]
assert len(calls)==5 and all('sret(' in x and x.index('sret(')>x.index('dereferenceable(') for x in calls),calls
results={}
for prepare in [0,1]:
 exe=r/f'probe-{prepare}.exe'
 subprocess.run([cc,'--target=i686-w64-mingw32','-O1','-static',f'-DPREPARE={prepare}',str(r/'bridge.cpp'),str(r/'msvc-caller.obj'),'-o',str(exe)],check=True)
 if a.wine:
  env=os.environ.copy();env['WINEPREFIX']=str(a.wine_prefix.resolve());env['WINEDEBUG']='-all'
  result=subprocess.run([str(a.wine.resolve()),str(exe)],env=env,capture_output=True,text=True,timeout=30)
  results[str(prepare)]={'returncode':result.returncode,'stderr':result.stderr[-1500:]}
  assert result.returncode==(41 if prepare==0 else 0),results
subprocess.run([cc,'--target=i686-w64-mingw32','-DPREPARE=1','-S','-emit-llvm','-O0',str(r/'bridge.cpp'),'-o',str(r/'bridge.ll')],check=True)
ir=(r/'bridge.ll').read_text()
defs=[x for x in ir.splitlines() if 'define internal x86_thiscallcc ' in x and 'msabi32_' in x]
assert len(defs)==5 and all('sret(' not in x for x in defs),defs
(r/'bridge-result.json').write_text(json.dumps({'architecture':'i386','productionGenerator':True,'msvcCallerIRReceiverBeforeResult':True,'explicitThiscallAdapterCount':len(defs),'linked':True,'executed':bool(a.wine),'results':results,'scope':'Compiler ABI lowering and real mixed-target PE link; runtime execution only when executed is true.'},indent=2)+'\n')
print('PASS: five production i386 adapters match MSVC thiscall lowering; mixed MSVC/MinGW objects link'+('; positive and negative control executed' if a.wine else '; NOT runtime-executed'))
