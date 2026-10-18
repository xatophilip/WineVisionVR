#!/usr/bin/env python3
"""Compile exact Wine cache-topology APIs under controlled NT/machine boundaries.

ASan/UBSan cover translated x86/AMD64/ARM64EC and native ARM profiles. Production
WinNT record declarations and RtlWow64GetProcessMachines are included unchanged.
No Wine process, headset, game or shared topology is modified.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime-source',required=True,type=Path)
p.add_argument('--build',required=True,type=Path)
a=p.parse_args();a.build.mkdir(parents=True,exist_ok=True)
work=Path(tempfile.mkdtemp(prefix='cache-topology-',dir=a.build.resolve()))
source=a.runtime_source.resolve()
rel='wine/dlls/kernelbase/memory.c';copy=work/'source'/rel
copy.parent.mkdir(parents=True);shutil.copyfile(source/rel,copy)
patch=ROOT/'windows-runtime-plugin/patches/0018-wine-translated-x86-cache-topology.patch'
def apply(*flags):
 return subprocess.run(['git','apply',*flags,str(patch)],cwd=work/'source',capture_output=True,text=True)
if apply('--check').returncode:
 r=apply('--reverse');assert r.returncode==0,r.stderr
before=copy.read_text();r=apply();assert r.returncode==0,r.stderr
after=copy.read_text()
def body(text,signature):
 start=text.index(signature);opening=text.index('{',start);end=opening+1;depth=1
 while depth:depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
def declaration(text,signature):
 code=body(text,signature);end=text.index(';',text.index(code)+len(code))
 return text[text.index(code):end+1]
winnt=(source/'wine/include/winnt.h').read_text()
types='\n'.join(declaration(winnt,'typedef '+kind+' _'+name) for kind,name in [
 ('enum','LOGICAL_PROCESSOR_RELATIONSHIP'),('enum','PROCESSOR_CACHE_TYPE'),
 ('struct','PROCESSOR_GROUP_INFO'),('struct','CACHE_DESCRIPTOR'),('struct','GROUP_AFFINITY'),
 ('struct','PROCESSOR_RELATIONSHIP'),('struct','NUMA_NODE_RELATIONSHIP'),
 ('struct','CACHE_RELATIONSHIP'),('struct','GROUP_RELATIONSHIP'),
 ('struct','SYSTEM_LOGICAL_PROCESSOR_INFORMATION'),('struct','SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX')])
machines=body((source/'wine/dlls/ntdll/process.c').read_text(),'NTSTATUS WINAPI RtlWow64GetProcessMachines(')
status=body((source/'wine/dlls/kernelbase/kernelbase.h').read_text(),'static inline BOOL set_ntstatus(')
def apis(text):
 return '\n'.join(body(text,signature) for signature in [
  'BOOL WINAPI DECLSPEC_HOTPATCH GetLogicalProcessorInformation(',
  'BOOL WINAPI DECLSPEC_HOTPATCH GetLogicalProcessorInformationEx('])
shell=r"""
#include <algorithm>
#include <array>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <vector>
#define WINAPI
#define DECLSPEC_HOTPATCH
#define DUMMYUNIONNAME
#define ANYSIZE_ARRAY 1
#define FIELD_OFFSET(type,field) offsetof(type,field)
using BOOL=int;using BYTE=uint8_t;using WORD=uint16_t;using USHORT=uint16_t;
using DWORD=uint32_t;using ULONG=uint32_t;using ULONGLONG=uint64_t;using NTSTATUS=int32_t;
using ULONG_PTR=uintptr_t;using KAFFINITY=uintptr_t;using HANDLE=void*;
constexpr BOOL TRUE=1,FALSE=0;
constexpr DWORD ERROR_INVALID_PARAMETER=87,ERROR_INSUFFICIENT_BUFFER=122;
constexpr NTSTATUS STATUS_INFO_LENGTH_MISMATCH=-1,STATUS_BUFFER_TOO_SMALL=-2,STATUS_ACCESS_VIOLATION=-3;
constexpr int SystemLogicalProcessorInformation=73,SystemLogicalProcessorInformationEx=107,SystemSupportedProcessorArchitectures=181;
constexpr USHORT IMAGE_FILE_MACHINE_ARM64=0xaa64,IMAGE_FILE_MACHINE_AMD64=0x8664;
struct SYSTEM_SUPPORTED_PROCESSOR_ARCHITECTURES_INFORMATION { USHORT Machine;bool Native,Process; };
""" + types + r"""
DWORD lastError=0;void SetLastError(DWORD error){lastError=error;}
DWORD RtlNtStatusToDosError(NTSTATUS s){return s==STATUS_BUFFER_TOO_SMALL?122:998;}
USHORT hostMachine=IMAGE_FILE_MACHINE_ARM64;
NTSTATUS machineStatus=0,queryStatus=0;
unsigned machineQueries=0,legacyQueries=0,extendedQueries=0;
std::array<SYSTEM_LOGICAL_PROCESSOR_INFORMATION,3> nativeInfo{};
std::vector<uint8_t> nativeEx;
NTSTATUS NtQuerySystemInformation(int cls,void*out,DWORD size,DWORD*len) {
 assert(cls==SystemLogicalProcessorInformation);legacyQueries++;
 if(queryStatus)return queryStatus;
 *len=sizeof(nativeInfo);
 if(size<*len)return STATUS_INFO_LENGTH_MISMATCH;
 assert(out);memcpy(out,nativeInfo.data(),*len);return 0;
}
NTSTATUS NtQuerySystemInformationEx(int cls,const void*query,DWORD querySize,void*out,DWORD size,DWORD*len) {
 if(cls==SystemSupportedProcessorArchitectures) {
  machineQueries++;if(machineStatus)return machineStatus;
  assert(query && querySize==sizeof(HANDLE) && size>=2*sizeof(SYSTEM_SUPPORTED_PROCESSOR_ARCHITECTURES_INFORMATION));
  auto*p=(SYSTEM_SUPPORTED_PROCESSOR_ARCHITECTURES_INFORMATION*)out;
  p[0]={hostMachine,true,false};p[1]={0,false,false};return 0;
 }
 assert(cls==SystemLogicalProcessorInformationEx && querySize==sizeof(LOGICAL_PROCESSOR_RELATIONSHIP));extendedQueries++;
 if(queryStatus)return queryStatus;
 auto relationship=*(const LOGICAL_PROCESSOR_RELATIONSHIP*)query;
 std::vector<uint8_t> result;
 size_t pos=0;
 while(pos<nativeEx.size()) {
  auto*entry=(const SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX*)(nativeEx.data()+pos);
  if(entry->Size<8 || entry->Size>nativeEx.size()-pos) {result=nativeEx;break;}
  if(relationship==RelationAll || entry->Relationship==relationship)
   result.insert(result.end(),nativeEx.begin()+pos,nativeEx.begin()+pos+entry->Size);
  pos+=entry->Size;
 }
 *len=result.size();if(size<*len)return STATUS_INFO_LENGTH_MISMATCH;
 if(*len){assert(out);memcpy(out,result.data(),*len);}return 0;
}
""" + machines + '\n' + status + '\n'
driver=r"""
int main() {
 for(auto&i:nativeInfo){i.ProcessorMask=0x55;i.Relationship=RelationCache;i.Cache={1,8,128,32768,CacheData};}
 nativeInfo[1].Relationship=RelationProcessorCore;nativeInfo[1].Reserved[0]=0x123456789;
 SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX ex{};ex.Relationship=RelationCache;ex.Size=sizeof(ex);ex.Cache.Level=1;ex.Cache.LineSize=128;ex.Cache.CacheSize=32768;
 nativeEx.resize(sizeof(ex)*3);memcpy(nativeEx.data(),&ex,sizeof(ex));
 ex.Relationship=RelationProcessorCore;ex.Processor.Flags=0x5a;memcpy(nativeEx.data()+sizeof(ex),&ex,sizeof(ex));
 ex.Relationship=RelationCache;ex.Cache.Level=2;ex.Cache.LineSize=128;memcpy(nativeEx.data()+2*sizeof(ex),&ex,sizeof(ex));
 const auto original=nativeInfo;const auto originalEx=nativeEx;
 auto legacy=[&](unsigned expected) {
  std::array<SYSTEM_LOGICAL_PROCESSOR_INFORMATION,4> out{};
  memset(out.data(),0xa5,sizeof(out));DWORD size=sizeof(out);
  assert(GetLogicalProcessorInformation(out.data(),&size)&&size==sizeof(nativeInfo));
  assert(out[0].Cache.LineSize==expected&&out[2].Cache.LineSize==expected);
  assert(out[0].Cache.Size==32768&&out[0].ProcessorMask==0x55&&out[1].Reserved[0]==0x123456789);
  auto*b=(const uint8_t*)&out[3];for(size_t i=0;i<sizeof(out[3]);i++)assert(b[i]==0xa5);
 };
 auto extended=[&](LOGICAL_PROCESSOR_RELATIONSHIP rel,unsigned expected) {
  alignas(16) std::array<uint8_t,1024> out{};out.fill(0xa5);DWORD size=out.size();
  assert(GetLogicalProcessorInformationEx(rel,(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX*)out.data(),&size));
  for(DWORD pos=0;pos<size;) {
   auto*entry=(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX*)(out.data()+pos);
   if(entry->Relationship==RelationCache){assert(entry->Cache.LineSize==expected);assert(entry->Cache.CacheSize==32768);}
   else assert(entry->Processor.Flags==0x5a);
   pos+=entry->Size;
  }
  for(size_t i=size;i<out.size();i++)assert(out[i]==0xa5);
 };
 legacy(EXPECTED_ARM);extended(RelationAll,EXPECTED_ARM);extended(RelationCache,EXPECTED_ARM);extended(RelationProcessorCore,EXPECTED_ARM);
 // Shared native data remains byte-identical after warm translated queries.
 assert(!memcmp(nativeInfo.data(),original.data(),sizeof(nativeInfo))&&nativeEx==originalEx);
 hostMachine=IMAGE_FILE_MACHINE_AMD64;legacy(128);extended(RelationAll,128);
 hostMachine=0x1c4;legacy(128);extended(RelationAll,128);
 hostMachine=IMAGE_FILE_MACHINE_ARM64;machineStatus=STATUS_ACCESS_VIOLATION;legacy(128);extended(RelationAll,128);machineStatus=0;
 const auto calls=machineQueries;
 DWORD size=0;assert(!GetLogicalProcessorInformation(nullptr,&size)&&size==sizeof(nativeInfo)&&lastError==122);
 assert(!GetLogicalProcessorInformationEx(RelationAll,nullptr,&size)&&size==nativeEx.size()&&lastError==122);
 assert(!GetLogicalProcessorInformation(nullptr,nullptr)&&lastError==87);
 assert(!GetLogicalProcessorInformationEx(RelationAll,nullptr,nullptr)&&lastError==87);
 assert(machineQueries==calls); // Failed/size-only API calls must not normalize.
 queryStatus=STATUS_ACCESS_VIOLATION;
 alignas(16) std::array<uint8_t,1024> untouched{};untouched.fill(0xa5);size=untouched.size();
 assert(!GetLogicalProcessorInformation((SYSTEM_LOGICAL_PROCESSOR_INFORMATION*)untouched.data(),&size));
 assert(!GetLogicalProcessorInformationEx(RelationAll,(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX*)untouched.data(),&size));
 for(auto byte:untouched)assert(byte==0xa5);queryStatus=0;
 // Successful but malformed fake NT records must not overrun or hot-loop.
 for(DWORD badSize:{0u,4u,1024u}) {
  nativeEx=originalEx;((SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX*)nativeEx.data())->Size=badSize;
  alignas(16) std::array<uint8_t,1024> out{};size=out.size();
  assert(GetLogicalProcessorInformationEx(RelationAll,(SYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX*)out.data(),&size));
 }
 printf("PASS production topology APIs profile=%s ARM-result=%u; native/Intel/ARMNT/failure preserve128; All/Cache/Core, buffer errors, canaries, shared-source invariance\n",PROFILE,EXPECTED_ARM);
}
"""
report=dict(passed=False,scope=__doc__,patchSha256=hashlib.sha256(patch.read_bytes()).hexdigest(),
 preparedSourceSha256=hashlib.sha256(before.encode()).hexdigest(),patchedSourceSha256=hashlib.sha256(after.encode()).hexdigest(),profiles={})
env=dict(os.environ,TMPDIR=str(work));compiler=['xcrun','--sdk','macosx','clang++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer']
for profile,macro,expected in [('baseline',None,128),('i386','__i386__',64),('amd64','__x86_64__',64),('arm64ec','__arm64ec__',64),('arm64',None,128)]:
 defines='\n#undef __i386__\n#undef __x86_64__\n#undef __arm64ec__\n'
 if macro:defines+='#define '+macro+' 1\n'
 funcs=apis(before) if profile=='baseline' else body(after,'static BOOL use_translated_x86_cache_lines(')+'\n'+apis(after)
 unit=work/(profile+'.cpp');unit.write_text(shell+defines+funcs+'\n#define EXPECTED_ARM '+str(expected)+'\n#define PROFILE "'+profile+'"\n'+driver)
 exe=work/profile;command=compiler+[str(unit),'-o',str(exe)]
 subprocess.run(command,env=env,check=True,timeout=60)
 run=subprocess.run([str(exe)],env=env,capture_output=True,text=True,timeout=15)
 (work/(profile+'.stdout')).write_text(run.stdout);(work/(profile+'.stderr')).write_text(run.stderr)
 assert run.returncode==0,run.stdout+run.stderr
 print(run.stdout,end='');report['profiles'][profile]=dict(command=command,exitCode=run.returncode,stdout=run.stdout)
report['passed']=True
report['limitations']=['Controlled NT query/machine boundary; production API/Rtl helper/WinNT declarations execute, not a full Wine guest or headset.','i386 macro coverage is host ABI simulation; full PE target compile/packaged probe establishes actual ABI separately.']
(work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print('Receipt:',work/'result.json')
