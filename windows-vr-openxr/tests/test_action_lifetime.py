#!/usr/bin/env python3
"""Run production action destruction and space lifetime paths with ASan/UBSan.

Host fixture supplies handle storage/controller samples, not a Windows loader.
"""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[2]
source = (root / 'windows-vr-openxr/src/WindowsVROpenXR.cpp').read_text()
def function(signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]
preamble = r'''
#include <openxr/openxr.h>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
constexpr uint32_t kControllerLeft=0,kControllerRight=1;
constexpr uint64_t kMagicSpace=1,kMagicAction=2,kMagicActionSet=3;
struct Instance;struct Action;struct ActionSet;
struct Session {Instance* instance;std::recursive_mutex actionMutex;std::mutex localOriginMutex;bool localOriginValid=false,actionSetsAttached=true;XrPosef localOrigin{};std::vector<XrActionSet> activeActionSets;std::unordered_map<XrActionSet,uint32_t> activeSetSubactions;};
struct Space {uint64_t magic=kMagicSpace;Session* session;XrAction action=XR_NULL_HANDLE;Action* actionResource=nullptr;XrPath subactionPath=XR_NULL_PATH;XrReferenceSpaceType type=XR_REFERENCE_SPACE_TYPE_STAGE;XrPosef poseInActionSpace{},poseInReferenceSpace{};};
struct ActionSet {uint64_t magic=kMagicActionSet;Instance* instance;std::vector<XrAction> actions;};
struct Action {uint64_t magic=kMagicAction;ActionSet* set;XrActionType type=XR_ACTION_TYPE_POSE_INPUT;std::vector<XrPath> subactionPaths,bindingPaths;};
struct Instance {std::mutex mutex;std::unordered_map<std::string,XrPath> paths;std::unordered_map<XrPath,std::string> pathStrings;uint64_t nextPath=1;std::vector<std::unique_ptr<ActionSet>> actionSets;std::vector<std::unique_ptr<Action>> actions;std::unordered_map<XrPath,XrAction> bindings;std::unordered_map<XrPath,std::vector<XrActionSuggestedBinding>> profileBindings;};
std::mutex g_mutex,g_handleMutex;
std::unordered_set<const void*> g_liveHandles;
std::vector<std::unique_ptr<Space>> g_spaces;
Session* GetSession(XrSession h){return reinterpret_cast<Session*>(h);}
struct WVRDXMTControllerV1 {uint32_t flags=7;float originFromController[16]{};};
struct WVRDXMTTrackingV1 {uint32_t flags=1;float originFromDevice[16]{};};
unsigned controllerReads=0;
int GetSessionController(Session*,uint32_t role,WVRDXMTControllerV1* controller){++controllerReads;controller->originFromController[12]=float(role+1);return 0;}
#define FAILED(value) ((value)<0)
XrPosef PoseFromMatrix(const float* m){return {{0,0,0,1},{m[12],m[13],m[14]}};}
XrPosef ComposePose(XrPosef a,XrPosef b){a.position.x+=b.position.x;a.position.y+=b.position.y;a.position.z+=b.position.z;return a;}
XrPosef EyeLevelOrigin(XrPosef p){return p;}
'''
functions = [function(signature) for signature in [
    'void RegisterHandle(', 'void UnregisterHandle(', 'bool IsLiveHandle(',
    'Space *GetSpace(', 'ActionSet *GetActionSet(', 'Action *GetAction(',
    'uint32_t RoleForPath(', 'XrPath UserPathForRole(', 'bool AnalogBinding(',
    'uint64_t ButtonForBinding(const std::string &binding) {',
    'bool ActionAllowsRole(', 'bool ActionHasBindingForRole(', 'uint32_t ActionRole(',
    'bool ActionSetIsActive(', 'bool ActionSetRoleIsActive(', 'bool OriginFromSpace(',
    'XrResult XRAPI_CALL CreateActionSpace(', 'XrResult XRAPI_CALL DestroySpace(',
    'void InvalidateActionHandle(', 'XrResult XRAPI_CALL DestroyActionSet(',
    'XrResult XRAPI_CALL DestroyAction(']]
tests = r'''
int main(){
 Instance instance;Session session;session.instance=&instance;
 auto set=[&](){auto p=std::make_unique<ActionSet>();p->instance=&instance;auto raw=p.get();instance.actionSets.push_back(std::move(p));RegisterHandle(raw);return raw;};
 auto path=[&](const std::string& text){auto p=instance.nextPath++;instance.paths[text]=p;instance.pathStrings[p]=text;return p;};
 const auto left=path("/user/hand/left"),binding=path("/user/hand/left/input/grip/pose");
 auto action=[&](ActionSet* parent){auto p=std::make_unique<Action>();p->set=parent;p->subactionPaths={left};p->bindingPaths={binding};auto raw=p.get();instance.actions.push_back(std::move(p));parent->actions.push_back(reinterpret_cast<XrAction>(raw));RegisterHandle(raw);return raw;};
 auto primary=set(),independent=set();auto pose=action(primary),otherChild=action(primary),survivor=action(independent);
 const auto primaryHandle=reinterpret_cast<XrActionSet>(primary),independentHandle=reinterpret_cast<XrActionSet>(independent);
 const auto poseHandle=reinterpret_cast<XrAction>(pose),otherHandle=reinterpret_cast<XrAction>(otherChild),survivorHandle=reinterpret_cast<XrAction>(survivor);
 instance.bindings[10]=poseHandle;instance.bindings[11]=otherHandle;instance.bindings[12]=survivorHandle;
 instance.profileBindings[20]={{poseHandle,binding},{otherHandle,binding},{survivorHandle,binding}};
 session.activeActionSets={primaryHandle,independentHandle};session.activeSetSubactions[primaryHandle]=1;session.activeSetSubactions[independentHandle]=1;
 XrActionSpaceCreateInfo create{XR_TYPE_ACTION_SPACE_CREATE_INFO};create.action=poseHandle;create.subactionPath=left;create.poseInActionSpace.orientation.w=1;
 XrSpace spaceHandle=XR_NULL_HANDLE;
 assert(CreateActionSpace(reinterpret_cast<XrSession>(&session),&create,&spaceHandle)==XR_SUCCESS);
 auto space=GetSpace(spaceHandle);assert(space&&space->actionResource==pose);
 WVRDXMTTrackingV1 tracking;XrPosef located{};uint32_t flags=0;
 assert(OriginFromSpace(&session,space,tracking,located,flags)&&flags&&located.position.x==1);
 assert(DestroyActionSet(primaryHandle)==XR_SUCCESS);
 assert(!GetActionSet(primaryHandle)&&!GetAction(poseHandle)&&!GetAction(otherHandle));
 assert(GetActionSet(independentHandle)==independent&&GetAction(survivorHandle)==survivor);
 assert(instance.bindings.size()==1&&instance.bindings.at(12)==survivorHandle);
 assert(instance.profileBindings.at(20).size()==1&&instance.profileBindings.at(20)[0].action==survivorHandle);
 assert(primary->actions.empty());
 assert(DestroyActionSet(primaryHandle)==XR_ERROR_HANDLE_INVALID);
 assert(DestroyAction(poseHandle)==XR_ERROR_HANDLE_INVALID);
 XrSpace rejected=XR_NULL_HANDLE;
 assert(CreateActionSpace(reinterpret_cast<XrSession>(&session),&create,&rejected)==XR_ERROR_HANDLE_INVALID);
 // Existing spaces keep their own live handle and backing pose resources.
 assert(GetSpace(spaceHandle)==space&&space->actionResource==pose);
 flags=0;assert(OriginFromSpace(&session,space,tracking,located,flags)&&flags&&located.position.x==1);
 // Deactivation at the next sync makes the surviving space unlocatable.
 session.activeActionSets={independentHandle};session.activeSetSubactions.erase(primaryHandle);
 flags=99;assert(!OriginFromSpace(&session,space,tracking,located,flags)&&flags==0);
 assert(DestroySpace(spaceHandle)==XR_SUCCESS&&!GetSpace(spaceHandle));
 // Individually destroying an action has the same non-cascading space lifetime.
 create.action=survivorHandle;
 assert(CreateActionSpace(reinterpret_cast<XrSession>(&session),&create,&spaceHandle)==XR_SUCCESS);
 space=GetSpace(spaceHandle);
 assert(DestroyAction(survivorHandle)==XR_SUCCESS&&!GetAction(survivorHandle));
 assert(GetActionSet(independentHandle)==independent&&GetSpace(spaceHandle)==space);
 assert(OriginFromSpace(&session,space,tracking,located,flags)&&flags);
 assert(DestroySpace(spaceHandle)==XR_SUCCESS);
 assert(DestroyActionSet(independentHandle)==XR_SUCCESS);
 assert(g_spaces.empty()&&g_liveHandles.empty());
 // Instance ownership releases every retained resource after spaces/session end.
 instance.actions.clear();instance.actionSets.clear();
 assert(instance.actions.empty()&&instance.actionSets.empty());
 puts("PASS: production action-set cascade, stale handles, binding cleanup, independent sets and surviving action-space lifetime (ASan/UBSan)");
}
'''
with tempfile.TemporaryDirectory(prefix='wvr-action-lifetime-') as work:
    cpp = Path(work)/'test.cpp'
    cpp.write_text(preamble+'\n'.join(functions)+tests)
    exe = Path(work)/'test'
    subprocess.run(['clang++','-std=c++20','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root/'third-party/openxr/include'),str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
