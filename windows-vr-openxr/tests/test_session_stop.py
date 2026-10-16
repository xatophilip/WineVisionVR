#!/usr/bin/env python3
"""Run production OpenXR session transitions under ASan/UBSan on the host.

Reproduces OpenComposite's begun startup frame -> request exit -> STOPPING ->
end session sequence. No guest loading, graphics submission or headset execution.
"""
import argparse
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build', type=Path, required=True)
parser.add_argument('--openxr-include', type=Path, default=ROOT/'third-party/openxr/include')
args = parser.parse_args()
build = args.build.resolve()
build.mkdir(parents=True, exist_ok=True)
source = (ROOT/'windows-vr-openxr/src/WindowsVROpenXR.cpp').read_text()
def function(name):
    start=source.index('XrResult XRAPI_CALL '+name+'(')
    brace=source.index('{',start)
    depth=1
    end=brace+1
    while depth:
        if source[end]=='{': depth+=1
        elif source[end]=='}': depth-=1
        end+=1
    return source[start:end]
pre=r'''
#include <openxr/openxr.h>
#include <cassert>
#include <condition_variable>
#include <future>
#include <mutex>
#include <vector>
struct Session {
  bool begun=false,waitTokenPending=false,activeFrame=false,exitRequested=false;
  uint64_t frameIndex=0,pendingFrameIndex=0,activeFrameIndex=0;
  XrTime predictedTime=0;
  XrSessionState state=XR_SESSION_STATE_READY;
  bool localOriginValid=false;
  std::mutex frameMutex,localOriginMutex;
  std::condition_variable frameCondition;
  std::vector<XrSessionState> events;
};
Session *valid=nullptr;
Session *GetSession(XrSession h) {return h && reinterpret_cast<Session*>(h)==valid?valid:nullptr;}
void QueueSessionState(Session *s,XrSessionState state) {s->state=state;s->events.push_back(state);}
'''
test=r'''
int main() {
  Session session;valid=&session;
  const auto h=reinterpret_cast<XrSession>(&session);
  XrSessionBeginInfo begin{XR_TYPE_SESSION_BEGIN_INFO};
  begin.primaryViewConfigurationType=XR_VIEW_CONFIGURATION_TYPE_PRIMARY_STEREO;
  assert(EndSessionImpl(XR_NULL_HANDLE)==XR_ERROR_HANDLE_INVALID);
  assert(EndSessionImpl(h)==XR_ERROR_SESSION_NOT_RUNNING);
  assert(BeginSessionImpl(h,&begin)==XR_SUCCESS);
  session.activeFrame=true;session.activeFrameIndex=41;session.waitTokenPending=true;
  // Rejected early ends must preserve the running frame.
  assert(EndSessionImpl(h)==XR_ERROR_SESSION_NOT_STOPPING);
  assert(session.begun && session.activeFrame && session.waitTokenPending);
  assert(RequestExitSession(h)==XR_SUCCESS);
  assert(session.state==XR_SESSION_STATE_STOPPING);
  session.events.clear();
  std::promise<void> waiting;
  auto waiter=std::async(std::launch::async,[&]{
    std::unique_lock<std::mutex> lock(session.frameMutex);
    waiting.set_value();
    session.frameCondition.wait(lock,[&]{return !session.begun;});
  });
  waiting.get_future().wait();
  assert(EndSessionImpl(h)==XR_SUCCESS);
  assert(waiter.wait_for(std::chrono::seconds(2))==std::future_status::ready);
  waiter.get();
  assert(!session.begun && !session.activeFrame && !session.waitTokenPending);
  assert(session.activeFrameIndex==0);
  assert((session.events==std::vector<XrSessionState>{XR_SESSION_STATE_IDLE,XR_SESSION_STATE_EXITING}));
  assert(EndSessionImpl(h)==XR_ERROR_SESSION_NOT_RUNNING);
  // Runtime-requested stop can restart the same session with reset frame state.
  session.exitRequested=false;session.state=XR_SESSION_STATE_READY;
  session.activeFrame=true;session.waitTokenPending=true;session.frameIndex=99;
  assert(BeginSessionImpl(h,&begin)==XR_SUCCESS);
  assert(!session.activeFrame && !session.waitTokenPending && session.frameIndex==0);
  session.state=XR_SESSION_STATE_STOPPING;session.events.clear();
  assert(EndSessionImpl(h)==XR_SUCCESS);
  assert((session.events==std::vector<XrSessionState>{XR_SESSION_STATE_IDLE,XR_SESSION_STATE_READY}));
  assert(BeginSessionImpl(h,&begin)==XR_SUCCESS);
}
'''
fixture=build/'session-stop.cpp'
fixture.write_text(pre+'\n'.join(function(n) for n in ['BeginSessionImpl','EndSessionImpl','RequestExitSession'])+test)
exe=build/'session-stop'
subprocess.run(['xcrun','--sdk','macosx','clang++','-std=c++17','-g','-O1','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I',str(args.openxr_include.resolve()),str(fixture),'-o',str(exe)],check=True)
subprocess.run([str(exe)],check=True,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'})
print('PASS: production STOPPING accepts begun frame without submission, preserves early rejection, resets tokens, wakes waiter, and supports runtime-stop restart (ASan/UBSan)')
