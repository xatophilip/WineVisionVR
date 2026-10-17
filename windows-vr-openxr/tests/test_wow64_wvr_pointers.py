#!/usr/bin/env python3
"""Run production legacy WMT handlers with real shifted-window pointer records.

Only compositor/Metal plumbing is stubbed. Both WOW64 wrappers, both unchanged
native handlers and the production UInt32ToPtr implementation are extracted
from a scratch copy with the reproducible integration patch applied.
"""
from pathlib import Path
import argparse, hashlib, json, os, shutil, subprocess
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True,help='Prepared legacy DXMT tree before or after patch 0018');p.add_argument('--build',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[2];build=a.build.resolve();build.mkdir(parents=True,exist_ok=True)
relative=Path('src/winemetal/unix/winemetal_unix.c');input_source=(a.source/relative).read_text();scratch=build/'patched-source';target=scratch/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(input_source)
patch=root/'windows-vr-openxr/patches/0018-dxmt-legacy-wvr-wow64-pointers.patch'
subprocess.run(['git','init','--quiet'],cwd=scratch,check=True)
forward=subprocess.run(['git','apply','--check',str(patch)],cwd=scratch,capture_output=True,text=True)
if forward.returncode==0:
 source_state='before-0018'
 original=input_source
elif subprocess.run(['git','apply','--reverse','--check',str(patch)],cwd=scratch,capture_output=True,text=True).returncode==0:
 source_state='after-0018'
 # Derive the actual baseline only in the scratch copy, then verify that the
 # owned patch reconstructs the provided fully prepared source byte for byte.
 subprocess.run(['git','apply','--reverse',str(patch)],cwd=scratch,check=True)
 original=target.read_text()
else:
 raise SystemExit('Legacy DXMT source is neither an applicable pre-0018 tree nor an exactly reversible post-0018 tree; refusing unknown patch state.')
subprocess.run(['git','apply',str(patch)],cwd=scratch,check=True)
source=target.read_text()
if source_state=='after-0018':
 assert source==input_source,'Reverse/reapply did not reproduce the supplied prepared source'

def function(text,signature):
 start=text.index(signature);brace=text.index('{',start);end=brace+1;depth=1
 while depth:
  depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
v1='static NTSTATUS\n_WMTWindowsVRBridgeCallV1(';v2='static NTSTATUS\n_WMTWindowsVRBridgeCallV2('
assert function(source,v1)==function(original,v1) and function(source,v2)==function(original,v2)
def table(text,name):
 start=text.index('const void *'+name+'[] = {');return text[start:text.index('\n};',start)+3]
assert table(source,'__wine_unix_call_funcs')==table(original,'__wine_unix_call_funcs')
assert '&_WMTWindowsVRBridgeCallV1_wow64,' in table(source,'__wine_unix_call_wow64_funcs')
assert '&_WMTWindowsVRBridgeCallV2_wow64,' in table(source,'__wine_unix_call_wow64_funcs')
preamble=r'''
#include <cassert>
#include <cstdio>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <sys/mman.h>
#include "WindowsVRWMTBridge.h"
@protocol MTLCommandBuffer;
@protocol MTLTexture;
@protocol MTLSharedEvent;
#undef TARGET_OS_IOS
#define TARGET_OS_IOS 1
using NTSTATUS=int;
constexpr NTSTATUS STATUS_SUCCESS=0,STATUS_INVALID_ADDRESS=int(0xc0000141u);
struct WMTMemoryPointer {void*ptr;};
struct unixcall_windows_vr_bridge_v1 {WMTMemoryPointer request;};
unsigned long windowBase;
unsigned long ios_wow_base(){return windowBase;}
bool wmtr_enabled(){return false;}
constexpr uint64_t commandID=0x1122334455667700ULL,leftID=0x2233445566778800ULL,rightID=0x3344556677889900ULL,eventID=0x445566778899aa00ULL,consumerID=0x5566778899aabb00ULL;
unsigned targetCalls=0,submitCalls=0;
int32_t wvr_compositor_copy_targets_v1(WVRRenderTargetInfoV1*t){++targetCalls;t->generation=123;t->width[0]=1920;t->width[1]=1920;t->height[0]=1792;t->height[1]=1792;t->pixelFormat[0]=t->pixelFormat[1]=71;return 0;}
int32_t wvr_compositor_copy_readiness_v1(WVRCompositorReadinessV1*){return -1;}
int32_t wvr_compositor_copy_frame_tracking_v1(WVRFrameTrackingV1*){return -1;}
int32_t wvr_compositor_copy_controller_state_v1(uint32_t,WVRControllerStateV1*){return -1;}
int32_t wvr_compositor_submit_haptic_v1(uint32_t,float,float,float,uint64_t*){return -1;}
void*wvr_compositor_copy_consumer_event_v1(){return reinterpret_cast<void*>(consumerID);}
void wvr_compositor_release_object_v1(void*){assert(false);}
int32_t wvr_compositor_submit_stereo_frame_for_generation_v1(const WVRSubmitStereoFrameV1*f,uint64_t generation,uint64_t*ticket){
 assert(generation==123&&uint64_t(f->leftTexture)==leftID&&uint64_t(f->rightTexture)==rightID&&uint64_t(f->producerReadyEvent)==eventID);assert(f->producerFrameID==321&&f->producerReadyValue==777);*ticket=900;++submitCalls;return 0;}
int32_t wvr_compositor_submit_stereo_frame_v2(const WVRSubmitStereoFrameV2*f,uint64_t*ticket){
 assert(f->targetGeneration==123&&uint64_t(f->leftTexture)==leftID&&uint64_t(f->rightTexture)==rightID&&uint64_t(f->producerReadyEvent)==eventID);assert(f->producerFrameID==321&&f->producerReadyValue==777);assert(f->leftSlice==1&&f->leftX==2&&f->leftWidth==1920&&f->rightSlice==3&&f->rightY==4&&f->rightHeight==1792);*ticket=901;++submitCalls;return 0;}
'''
functions='\n'.join(function(source,x)for x in [v1,v2,'static inline void *\nUInt32ToPtr(','static NTSTATUS\n_WMTWindowsVRBridgeCallV1_wow64(','static NTSTATUS\n_WMTWindowsVRBridgeCallV2_wow64('])
# The production file is Objective-C, where void* converts implicitly. Add only
# the explicit pointer casts required by this Objective-C++ sanitizer harness.
functions=functions.replace('*params = obj;', '*params = static_cast<struct unixcall_windows_vr_bridge_v1 *>(obj);')
for version in [1,2]:
 functions=functions.replace(f'WMTWindowsVRRequestV{version} *request = params->request.ptr;',f'WMTWindowsVRRequestV{version} *request = static_cast<WMTWindowsVRRequestV{version} *>(params->request.ptr);')

tests=r'''
int main(int argc,char**argv){
 void*memory=mmap(nullptr,65536,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANON,-1,0);assert(memory!=MAP_FAILED);assert(uintptr_t(memory)>UINT32_MAX);
 constexpr uintptr_t guestOffset=0x10000;windowBase=uintptr_t(memory)-guestOffset;assert(windowBase>UINT32_MAX);
 auto*v1=static_cast<WMTWindowsVRRequestV1*>(memory);v1->abiVersion=1;v1->structSize=sizeof(*v1);v1->kind=WMTWindowsVRRequestTargets;v1->status=-99;
 unixcall_windows_vr_bridge_v1 outer{{reinterpret_cast<void*>(guestOffset)}};
 if(argc>1&&std::strcmp(argv[1],"--baseline-v1")==0){return _WMTWindowsVRBridgeCallV1(&outer);}
 if(argc>1&&std::strcmp(argv[1],"--baseline-v2")==0){return _WMTWindowsVRBridgeCallV2(&outer);}
 assert(_WMTWindowsVRBridgeCallV1_wow64(&outer)==STATUS_SUCCESS&&v1->status==0);assert(v1->targets.generation==123&&v1->targets.width[0]==1920&&v1->targets.height[1]==1792);assert(outer.request.ptr==reinterpret_cast<void*>(guestOffset));
 v1->kind=WMTWindowsVRRequestSubmitStereo;v1->targetGeneration=123;v1->commandBuffer=commandID;v1->leftTexture=leftID;v1->rightTexture=rightID;v1->producerEvent=eventID;v1->frameID=321;v1->producerValue=777;
 assert(_WMTWindowsVRBridgeCallV1_wow64(&outer)==0&&v1->status==0&&v1->compositorTicket==900&&v1->consumerEvent==consumerID);
 auto*v2=reinterpret_cast<WMTWindowsVRRequestV2*>(static_cast<char*>(memory)+8192);v2->abiVersion=2;v2->structSize=sizeof(*v2);v2->commandBuffer=commandID;v2->leftTexture=leftID;v2->rightTexture=rightID;v2->producerEvent=eventID;v2->frameID=321;v2->targetGeneration=123;v2->producerValue=777;v2->leftSlice=1;v2->leftX=2;v2->leftWidth=1920;v2->rightSlice=3;v2->rightY=4;v2->rightHeight=1792;
 outer.request.ptr=reinterpret_cast<void*>(guestOffset+8192);
 assert(_WMTWindowsVRBridgeCallV2_wow64(&outer)==0&&v2->status==0&&v2->compositorTicket==901&&v2->consumerEvent==consumerID);assert(outer.request.ptr==reinterpret_cast<void*>(guestOffset+8192));
 // Malformed pointer fields must not truncate into a live resource record.
 outer.request.ptr=reinterpret_cast<void*>(0x100010000ULL);assert(_WMTWindowsVRBridgeCallV1_wow64(&outer)==STATUS_INVALID_ADDRESS&&_WMTWindowsVRBridgeCallV2_wow64(&outer)==STATUS_INVALID_ADDRESS);
 outer.request.ptr=nullptr;assert(_WMTWindowsVRBridgeCallV1_wow64(&outer)==STATUS_INVALID_ADDRESS&&_WMTWindowsVRBridgeCallV2_wow64(&outer)==STATUS_INVALID_ADDRESS);assert(_WMTWindowsVRBridgeCallV1_wow64(nullptr)==STATUS_INVALID_ADDRESS&&_WMTWindowsVRBridgeCallV2_wow64(nullptr)==STATUS_INVALID_ADDRESS);
 // Native callers retain their original actual pointer even while a guest
 // window is active: only the WOW64 dispatch entries perform relocation.
 outer.request.ptr=v1;v1->kind=WMTWindowsVRRequestTargets;assert(_WMTWindowsVRBridgeCallV1(&outer)==0&&v1->status==0);
 outer.request.ptr=v2;assert(_WMTWindowsVRBridgeCallV2(&outer)==0&&v2->status==0);
 // Classic identity mapping still works with a zero guest-window base.
 windowBase=0;assert(UInt32ToPtr(0x1234)==reinterpret_cast<void*>(0x1234));assert(UInt32ToPtr(0)==nullptr);
 assert(targetCalls==3&&submitCalls==3);assert(munmap(memory,65536)==0);
 std::puts("PASS: actual V1/V2 WOW64 handlers relocate nested requests once; preserve native 64-bit object IDs, output records and dispatch; reject null/high bits (ASan/UBSan)");
}
'''
cpp=build/'test.mm';exe=build/'test';cpp.write_text(preamble+functions+tests)
subprocess.run(['xcrun','--sdk','macosx','clang++','-std=c++20','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root/'windows-vr-openxr/include'),'-I',str(root/'windows-vr-native/include'),str(cpp),'-o',str(exe)],check=True)
positive=subprocess.run([str(exe)],capture_output=True,text=True,timeout=30);(build/'positive.log').write_text(positive.stdout+positive.stderr);assert positive.returncode==0,positive.stdout+positive.stderr
negative={}
for variant in ['v1','v2']:
 result=subprocess.run([str(exe),'--baseline-'+variant],capture_output=True,text=True,timeout=30);(build/('negative-'+variant+'.log')).write_text(result.stdout+result.stderr);assert result.returncode!=0 and ('AddressSanitizer' in result.stderr or 'UndefinedBehaviorSanitizer' in result.stderr),result.stderr
 negative[variant]={'returncode':result.returncode,'scope':'Original shared 64-bit handler dereferences the unconverted low guest pointer and fails under sanitizer'}
result={'inputSourceState':source_state,'postPatchRoundtripExact':source_state=='after-0018','patchSha256':hashlib.sha256(patch.read_bytes()).hexdigest(),'native64HandlersUnchanged':True,'native64DispatchUnchanged':True,'actualProductionFunctions':True,'shiftedWindowV1V2':'passed ASan/UBSan','pointerNullAndHighBits':'rejected','nativeMetalIDs64Bit':'unchanged','negativeControls':negative,'headsetExecuted':False}
(build/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(positive.stdout.strip())
