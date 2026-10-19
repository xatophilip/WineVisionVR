#!/usr/bin/env python3
"""Apply the canonical patch to pinned OC and execute its actual haptic method."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--source',type=Path,required=True,help='Genuine OpenComposite git checkout (read only)')
p.add_argument('--build',type=Path,required=True)
a=p.parse_args()
root=Path(__file__).resolve().parents[2]
lock=json.loads((root/'windows-vr-openvr/opencomposite.lock.json').read_text())
rel='OpenOVR/Reimpl/BaseInput.cpp'
original=subprocess.check_output(['git','-C',str(a.source),'show',lock['commit']+':'+rel],text=True)
base=a.build.resolve();base.mkdir(parents=True,exist_ok=True)
# Each invocation preserves its own source, sanitizer logs and result receipt.
build=Path(tempfile.mkdtemp(prefix="run-",dir=base))
overlay=build/'overlay';file=overlay/rel;file.parent.mkdir(parents=True);file.write_text(original)
# Patch 0003 is the only earlier normal-recipe patch touching this file.
compat=root/'windows-vr-openvr/patches/0003-llvm-mingw-direct3d-compat.patch'
subprocess.run(['git','apply','--include='+rel,str(compat)],check=True,cwd=overlay)
baseline=file.read_text()
patch=root/'windows-vr-openvr/patches/0013-haptic-duration-width.patch'
subprocess.run(['git','apply',str(patch)],check=True,cwd=overlay)
patched=file.read_text()
signature='EVRInputError BaseInput::TriggerHapticVibrationAction('
def function(text):
 start=text.index(signature);brace=text.index('{',start);end=brace+1;depth=1
 while depth:
  depth+=(text[end]=='{')-(text[end]=='}');end+=1
 return text[start:end]
# Take the real existing handle-validation macro too; only platform dispatch is stubbed.
macro=original[original.index('#define GET_ACTION_FROM_HANDLE('):original.index('/**',original.index('#define GET_ACTION_FROM_HANDLE('))]
preamble=r'''
#include <openxr/openxr.h>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
namespace vr {using VRActionHandle_t=uint64_t;using VRInputValueHandle_t=uint64_t;
enum EVRInputError {VRInputError_None,VRInputError_InvalidHandle,VRInputError_InvalidParam};
constexpr auto k_ulInvalidInputValueHandle=0ull;}
using namespace vr;
enum class ActionType {Vibration,Other};
struct Action {ActionType type=ActionType::Vibration;std::string fullName="test";XrAction xr=(XrAction)1;} currentAction;
Action* cast_AH(VRActionHandle_t h){return h==1?&currentAction:nullptr;}
#define OOVR_LOG_ONCE(...) ((void)0)
struct HardAbort:std::runtime_error{using std::runtime_error::runtime_error;};
#define OOVR_ABORTF(...) throw HardAbort("action-type")
#define OOVR_FAILED_XR_ABORT(call) do {if(XR_FAILED(call))throw HardAbort("xr-error");}while(0)
struct ITrackedDevice {enum {HAND_NONE=-1};int hand;int GetHand(){return hand;}};
std::shared_ptr<ITrackedDevice> ivhToDev(VRInputValueHandle_t h){if(h!=10&&h!=11)return {};return std::make_shared<ITrackedDevice>(ITrackedDevice{int(h-10)});}
struct LegacyControllerActions{XrPath handPathXr;};
struct {XrSession get(){return (XrSession)1;}} xr_session;
unsigned calls=0;XrHapticVibration captured{};XrHapticActionInfo capturedInfo{};XrResult transport=XR_SUCCESS;
XrResult xrApplyHapticFeedback(XrSession,const XrHapticActionInfo* info,const XrHapticBaseHeader* feedback){++calls;captured=*reinterpret_cast<const XrHapticVibration*>(feedback);capturedInfo=*info;return transport;}
struct BaseInput {LegacyControllerActions legacyControllers[2]{{100},{101}};
 EVRInputError TriggerHapticVibrationAction(VRActionHandle_t,float,float,float,float,VRInputValueHandle_t);};
'''
tests=r'''
int main(){BaseInput input;
 auto run=[&](float duration,float delay=0.f,VRInputValueHandle_t hand=0){return input.TriggerHapticVibrationAction(1,delay,duration,120,.7f,hand);};
 assert(run(3.f)==VRInputError_None);assert(captured.duration==3000000000LL);
 assert(run(5.f)==VRInputError_None&&captured.duration==5000000000LL);
 assert(run(0.f)==VRInputError_None&&captured.duration==0);
 assert(run(.5f,2.f,10)==VRInputError_None&&captured.duration==500000000LL&&capturedInfo.subactionPath==100);
 assert(run(.5f,0.f,11)==VRInputError_None&&capturedInfo.subactionPath==101);
 assert(run(.5f)==VRInputError_None&&capturedInfo.subactionPath==XR_NULL_PATH);
 assert(captured.amplitude==.7f&&captured.frequency==120);
 for(float bad:{-1.f,std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity(),std::numeric_limits<float>::max(),1.0e10f}){
  unsigned before=calls;assert(run(bad)==VRInputError_InvalidParam&&calls==before);
 }
 // Float seconds on both sides of the int64 boundary, computed in the exact
 // double arithmetic used by the production conversion. No cast on invalids.
 float boundary=static_cast<float>(std::ldexp(1.0,63)/1.0e9);
 for(float value:{std::nextafter(boundary,0.f),boundary,std::nextafter(boundary,std::numeric_limits<float>::infinity())}){
  double ns=static_cast<double>(value)*1.0e9;unsigned before=calls;
  if(ns<std::ldexp(1.0,63)){assert(run(value)==VRInputError_None&&captured.duration==static_cast<int64_t>(ns));}
  else assert(run(value)==VRInputError_InvalidParam&&calls==before);
 }
 unsigned before=calls;assert(input.TriggerHapticVibrationAction(0,0,3,0,1,0)==VRInputError_InvalidHandle&&calls==before);
 currentAction.type=ActionType::Other;bool aborted=false;try{run(3);}catch(const HardAbort&){aborted=true;}assert(aborted);currentAction.type=ActionType::Vibration;
 transport=XR_ERROR_RUNTIME_FAILURE;aborted=false;try{run(3);}catch(const HardAbort&){aborted=true;}assert(aborted);
 transport=XR_SESSION_NOT_FOCUSED;assert(run(3)==VRInputError_None);
 puts("PASS: actual patched OC method, 3s/5s, zero/start-delay/hand routing, finite/int64 boundary validation, unchanged handle/type/XR abort paths");
}
'''
receipts={}
for name,text in [('before',baseline),('after',patched)]:
 cpp=build/(name+'.cpp');cpp.write_text(preamble+macro+function(text)+tests);exe=build/name
 subprocess.run(['clang++','-std=c++20','-fsanitize=address,undefined,float-cast-overflow','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-I',str(root/'third-party/openxr/include'),str(cpp),'-o',str(exe)],check=True)
 result=subprocess.run([str(exe)],capture_output=True,text=True);(build/(name+'.log')).write_text(result.stdout+result.stderr)
 receipts[name]={'returncode':result.returncode,'sourceSHA256':hashlib.sha256(cpp.read_bytes()).hexdigest()}
 if name=='before':assert result.returncode!=0 and 'outside the range of representable values' in result.stderr,result.stderr
 else:assert result.returncode==0,result.stderr
cmake=(root/'windows-vr-openvr/CMakeLists.txt').read_text();assert cmake.index('patches/0013-haptic-duration-width.patch')>cmake.index('patches/0012-d3d11-base-mip-swapchain.patch')
receipt={'passed':True,'pinnedCommit':lock['commit'],'originalSourceSHA256':hashlib.sha256(original.encode()).hexdigest(),'patchSHA256':hashlib.sha256(patch.read_bytes()).hexdigest(),'patchedSourceSHA256':hashlib.sha256(file.read_bytes()).hexdigest(),'results':receipts,'limits':'Actual production method and handle macro executed locally with XR transport/platform types stubbed; no guest rebuild/device proof.'}
(build/'result.json').write_text(json.dumps(receipt,indent=2)+'\n');print((build/'after.log').read_text(),end='');print('Evidence:',build/'result.json')
