#!/usr/bin/env python3
"""Run production input/profile helpers natively; no game or headset required."""
from pathlib import Path
import subprocess
import tempfile
root = Path(__file__).resolve().parents[2]
source = (root / 'windows-vr-openxr/src/WindowsVROpenXR.cpp').read_text()
def function(signature):
    start = source.index(signature)
    brace = source.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]
preamble = r'''
#include <openxr/openxr.h>
#include "WindowsVRHandles.h"
#include "WindowsVRActionPlan.h"
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <memory>
#include <limits>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
constexpr uint32_t kControllerLeft=0,kControllerRight=1;
struct Instance;struct Action;
struct ActionValue {bool boolean=false;float scalar=0;XrVector2f vector{};XrTime lastChangeTime=0;bool changed=false;};
struct ActionSet {Instance* instance;std::vector<XrAction> actions;bool bindingsAttached=false;};
struct Action {std::string name;ActionSet* set;XrActionType type;std::vector<XrPath> subactionPaths,bindingPaths,plannedBindingPaths;WVRActionRolePlan rolePlans[2];std::unordered_map<uint32_t,ActionValue> values;};
struct Instance {std::mutex mutex;std::unordered_map<std::string,XrPath> paths;std::unordered_map<XrPath,std::string> pathStrings;std::vector<std::unique_ptr<Action>> actions;std::vector<std::unique_ptr<ActionSet>> actionSets;std::unordered_map<XrPath,XrPath> interactionProfiles;std::unordered_map<XrPath,XrAction> bindings;std::unordered_map<XrPath,std::vector<XrActionSuggestedBinding>> profileBindings;XrPath selectedProfile=XR_NULL_PATH;int selectedProfilePriority=-1;uint64_t nextPath=1;};
struct WVRDXMTControllerV1 {uint64_t buttons=0,timestampNanoseconds=0;uint32_t flags=7;float trigger=0,grip=0,thumbstickX=0,thumbstickY=0;};
struct ControllerSample {WVRDXMTControllerV1 left{},right{};};
struct Session {Instance* instance;std::atomic<XrSessionState> state{XR_SESSION_STATE_FOCUSED};std::recursive_mutex actionMutex;std::mutex eventMutex;bool interactionProfileChanged=false;bool begun=true;bool actionSetsAttached=true;std::vector<XrActionSet> attachedActionSets,activeActionSets;std::unordered_map<XrActionSet,uint32_t> activeSetSubactions;std::vector<XrActiveActionSet> synchronizedActionSets;ControllerSample controllers;};
Instance* GetInstance(XrInstance h){return reinterpret_cast<Instance*>(h);}
Action* GetAction(XrAction h){return reinterpret_cast<Action*>(h);}
ActionSet* GetActionSet(XrActionSet h){return reinterpret_cast<ActionSet*>(h);}
std::vector<std::string> traceLines;
void TraceLine(const char* line){traceLines.emplace_back(line);}
struct WVRDXMTHapticV1 {uint32_t role;float amplitude,frequencyHz,durationSeconds;};
std::vector<WVRDXMTHapticV1> sentHaptics;
Session* GetSession(XrSession h){return reinterpret_cast<Session*>(h);}
bool failHapticSubmit=false;
int SubmitSessionHaptic(Session*,const WVRDXMTHapticV1* request){if(failHapticSubmit)return -1;sentHaptics.push_back(*request);return 0;}
ControllerSample sampledControllers;
bool failControllerRead=false;
unsigned observeCalls=0;
struct WVRFrameStateRequestV1 {WVRDXMTControllerV1 controllers[2];};
bool useFrameState=false;
bool GetSessionFrameState(Session*,WVRFrameStateRequestV1& out){if(!useFrameState)return false;out.controllers[0]=sampledControllers.left;out.controllers[1]=sampledControllers.right;return true;}
void CopyFrameController(const WVRDXMTControllerV1& in,WVRDXMTControllerV1& out){out=in;}
void ObserveSessionExitRequest(Session*,void*,void*,void*,const WVRFrameStateRequestV1*){++observeCalls;}
int GetSessionController(Session*,uint32_t role,WVRDXMTControllerV1* out){if(failControllerRead)return -1;*out=role==0?sampledControllers.left:sampledControllers.right;return 0;}
#define FAILED(result) ((result)<0)
uint64_t ButtonForBinding(const std::string&);
'''
haptic_enum = source[source.index('enum HapticTracePhase :'):source.index('XrResult HapticResult(')]
functions = [haptic_enum, function('XrResult HapticResult(')] + [function(x) for x in [
    'bool AnalogBinding(', 'uint32_t RoleForPath(', 'XrPath UserPathForRole(', 'bool ActionAllowsRole(',
    'void CompileActionBindings(', 'bool ActionHasBindingForRole(', 'uint64_t ButtonForBinding(const std::string &binding) {',
    'ActionValue SampleAction(', 'void UpdateActionSnapshot(', 'bool ControllerConnected(', 'bool ActionSetIsActive(', 'bool ActionSetRoleIsActive(', 'XrResult XRAPI_CALL SyncActions(', 'XrResult GetActionSnapshot(',
    'XrResult XRAPI_CALL SuggestInteractionProfileBindings(', 'XrResult XRAPI_CALL AttachSessionActionSets(',
    'XrResult XRAPI_CALL ApplyHapticFeedback(', 'XrResult XRAPI_CALL StopHapticFeedback(']]
tests = r'''
int main(){
 Instance i;i.actionSets.push_back(std::make_unique<ActionSet>());ActionSet& set=*i.actionSets.back();set.instance=&i;
 auto path=[&](const std::string& name){auto found=i.paths.find(name);if(found!=i.paths.end())return found->second;auto p=i.nextPath++;i.paths[name]=p;i.pathStrings[p]=name;return p;};
 auto action=[&](XrActionType type){auto a=std::make_unique<Action>();a->set=&set;a->type=type;auto raw=a.get();i.actions.push_back(std::move(a));set.actions.push_back(reinterpret_cast<XrAction>(raw));return raw;};
 WVRDXMTControllerV1 c;c.buttons=3;c.trigger=.8f;c.grip=.7f;c.thumbstickX=-.6f;c.thumbstickY=.4f;
 auto a=action(XR_ACTION_TYPE_BOOLEAN_INPUT);
 for(auto name:{"x/click","y/click","a/click","b/click","trigger/value","squeeze/value","trigger","squeeze","grip"}){
   a->bindingPaths={path(std::string("/user/hand/left/input/")+name)};
   assert(ActionHasBindingForRole(a,0));assert(SampleAction(a,0,c).boolean);assert(!ActionHasBindingForRole(a,1));
 }
 c.buttons|=1ull<<4;a->bindingPaths={path("/user/hand/left/input/select/click")};assert(SampleAction(a,0,c).boolean);
 c.trigger=.2f;a->bindingPaths={path("/user/hand/left/input/trigger/value")};assert(!SampleAction(a,0,c).boolean);
 auto axis=action(XR_ACTION_TYPE_FLOAT_INPUT);
 axis->bindingPaths={path("/user/hand/left/input/thumbstick/x")};assert(ActionHasBindingForRole(axis,0));assert(SampleAction(axis,0,c).scalar==-.6f);
 axis->bindingPaths={path("/user/hand/left/input/thumbstick/y")};assert(SampleAction(axis,0,c).scalar==.4f);
 auto vector=action(XR_ACTION_TYPE_VECTOR2F_INPUT);vector->bindingPaths={path("/user/hand/left/input/thumbstick")};assert(SampleAction(vector,0,c).vector.x==-.6f);
 UpdateActionSnapshot(axis,0,c);assert(axis->values[0].changed);UpdateActionSnapshot(axis,0,c);assert(!axis->values[0].changed);c.thumbstickY=-.2f;UpdateActionSnapshot(axis,0,c);assert(axis->values[0].changed);
 auto other=action(XR_ACTION_TYPE_FLOAT_INPUT);
 const auto squeeze=path("/user/hand/left/input/squeeze/value");
 const auto touch=path("/interaction_profiles/oculus/touch_controller");
 const auto simple=path("/interaction_profiles/khr/simple_controller");
 XrActionSuggestedBinding bindings[]={{reinterpret_cast<XrAction>(a),squeeze},{reinterpret_cast<XrAction>(other),squeeze}};
 XrInteractionProfileSuggestedBinding info{XR_TYPE_INTERACTION_PROFILE_SUGGESTED_BINDING};info.interactionProfile=touch;info.countSuggestedBindings=2;info.suggestedBindings=bindings;
 assert(SuggestInteractionProfileBindings(reinterpret_cast<XrInstance>(&i),&info)==XR_SUCCESS);
 assert(i.selectedProfile==touch);assert(a->bindingPaths.size()==1&&other->bindingPaths.size()==1);assert(axis->bindingPaths.empty());
 const auto select=path("/user/hand/left/input/select/click");XrActionSuggestedBinding fallback{reinterpret_cast<XrAction>(a),select};info.interactionProfile=simple;info.countSuggestedBindings=1;info.suggestedBindings=&fallback;
 assert(SuggestInteractionProfileBindings(reinterpret_cast<XrInstance>(&i),&info)==XR_SUCCESS);
 assert(i.selectedProfile==touch);assert(a->bindingPaths[0]==squeeze);
 Session attachment;attachment.instance=&i;attachment.actionSetsAttached=false;
 const auto originalSetHandle=reinterpret_cast<XrActionSet>(&set);
 XrActionSet attachHandles[]={originalSetHandle,XR_NULL_HANDLE};
 XrSessionActionSetsAttachInfo attach{XR_TYPE_SESSION_ACTION_SETS_ATTACH_INFO};attach.countActionSets=2;attach.actionSets=attachHandles;
 auto attachmentHandle=reinterpret_cast<XrSession>(&attachment);
 assert(AttachSessionActionSets(attachmentHandle,&attach)==XR_ERROR_HANDLE_INVALID);
 assert(!attachment.actionSetsAttached&&attachment.attachedActionSets.empty()&&!set.bindingsAttached);
 attachHandles[1]=originalSetHandle;
 assert(AttachSessionActionSets(attachmentHandle,&attach)==XR_ERROR_VALIDATION_FAILURE);
 assert(!attachment.actionSetsAttached&&attachment.attachedActionSets.empty()&&!set.bindingsAttached);
 attach.countActionSets=1;
 assert(AttachSessionActionSets(attachmentHandle,&attach)==XR_SUCCESS);
 assert(set.bindingsAttached&&attachment.actionSetsAttached);
 assert(SuggestInteractionProfileBindings(reinterpret_cast<XrInstance>(&i),&info)==XR_ERROR_ACTIONSETS_ALREADY_ATTACHED);
 // Unrelated new sets can suggest bindings even while the original session exists.
 ActionSet freshSet{&i};auto fresh=std::make_unique<Action>();fresh->set=&freshSet;fresh->type=XR_ACTION_TYPE_BOOLEAN_INPUT;
 const auto freshHandle=reinterpret_cast<XrAction>(fresh.get());freshSet.actions.push_back(freshHandle);i.actions.push_back(std::move(fresh));
 XrActionSuggestedBinding freshBinding{freshHandle,select};info.suggestedBindings=&freshBinding;
 assert(SuggestInteractionProfileBindings(reinterpret_cast<XrInstance>(&i),&info)==XR_SUCCESS);
 // Session destruction never unfreezes a previously attached set. A replacement
 // session can attach a fresh set; invalid multi-set calls do not freeze it early.
 attachment.attachedActionSets.clear();attachment.actionSetsAttached=false;
 info.suggestedBindings=&fallback;
 assert(SuggestInteractionProfileBindings(reinterpret_cast<XrInstance>(&i),&info)==XR_ERROR_ACTIONSETS_ALREADY_ATTACHED);
 info.suggestedBindings=&freshBinding;assert(SuggestInteractionProfileBindings(reinterpret_cast<XrInstance>(&i),&info)==XR_SUCCESS);
 Session replacement;replacement.instance=&i;replacement.actionSetsAttached=false;
 const auto freshSetHandle=reinterpret_cast<XrActionSet>(&freshSet);attach.actionSets=&freshSetHandle;
 assert(AttachSessionActionSets(reinterpret_cast<XrSession>(&replacement),&attach)==XR_SUCCESS);
 assert(SuggestInteractionProfileBindings(reinterpret_cast<XrInstance>(&i),&info)==XR_ERROR_ACTIONSETS_ALREADY_ATTACHED);
 // Empty suggestions reference no sets and may replace an existing profile.
 info.countSuggestedBindings=0;info.suggestedBindings=nullptr;
 assert(SuggestInteractionProfileBindings(reinterpret_cast<XrInstance>(&i),&info)==XR_SUCCESS);
 Session session;session.instance=&i;session.activeActionSets={reinterpret_cast<XrActionSet>(&set)};session.attachedActionSets=session.activeActionSets;session.activeSetSubactions[session.activeActionSets[0]]=3;
 auto triggerAction=action(XR_ACTION_TYPE_FLOAT_INPUT);
 auto left=UserPathForRole(&i,0),right=UserPathForRole(&i,1);
 triggerAction->subactionPaths={left,right};triggerAction->bindingPaths={path("/user/hand/right/input/trigger/value")};
 session.controllers.right.trigger=1.0f;UpdateActionSnapshot(triggerAction,1,session.controllers.right);
 XrActionStateGetInfo get{XR_TYPE_ACTION_STATE_GET_INFO};get.action=reinterpret_cast<XrAction>(triggerAction);get.subactionPath=right;
 Action* actual=nullptr;ActionValue result{};bool active=false;
 assert(GetActionSnapshot(&session,&get,XR_ACTION_TYPE_FLOAT_INPUT,actual,result,active)==XR_SUCCESS);assert(active&&result.scalar==1.0f);
 get.subactionPath=XR_NULL_PATH;result={};assert(GetActionSnapshot(&session,&get,XR_ACTION_TYPE_FLOAT_INPUT,actual,result,active)==XR_SUCCESS);assert(active&&result.scalar==1.0f);
 get.subactionPath=left;result={};assert(GetActionSnapshot(&session,&get,XR_ACTION_TYPE_FLOAT_INPUT,actual,result,active)==XR_SUCCESS);assert(!active&&result.scalar==0);
 session.state=XR_SESSION_STATE_VISIBLE;get.subactionPath=right;result={};assert(GetActionSnapshot(&session,&get,XR_ACTION_TYPE_FLOAT_INPUT,actual,result,active)==XR_SUCCESS);assert(!active);
 session.state=XR_SESSION_STATE_FOCUSED;
 auto grab=action(XR_ACTION_TYPE_BOOLEAN_INPUT);grab->subactionPaths={left,right};
 for(uint32_t role:{0u,1u}){
   grab->bindingPaths={path(role==0?"/user/hand/left/input/trigger":"/user/hand/right/input/trigger")};
   auto& controller=role==0?session.controllers.left:session.controllers.right;
   for(float amount:{0.0f,0.3f,0.8f,1.0f,0.0f}){
     controller.trigger=amount;UpdateActionSnapshot(grab,role,controller);
     get.action=reinterpret_cast<XrAction>(grab);get.subactionPath=role==0?left:right;result={};
     assert(GetActionSnapshot(&session,&get,XR_ACTION_TYPE_BOOLEAN_INPUT,actual,result,active)==XR_SUCCESS);assert(active);assert(result.boolean==(amount>=.5f));
   }
 }
 triggerAction->bindingPaths={path("/user/hand/right/input/trigger")};session.controllers.right.trigger=.75f;UpdateActionSnapshot(triggerAction,1,session.controllers.right);get.action=reinterpret_cast<XrAction>(triggerAction);get.subactionPath=right;result={};assert(GetActionSnapshot(&session,&get,XR_ACTION_TYPE_FLOAT_INPUT,actual,result,active)==XR_SUCCESS);assert(active&&result.scalar==.75f);
 assert(!AnalogBinding("/user/hand/right/input/trigger/touch","trigger"));
 assert(!AnalogBinding("/user/hand/right/input/trigger/click","trigger"));
 auto menu=action(XR_ACTION_TYPE_BOOLEAN_INPUT);menu->subactionPaths={left,right};
 menu->bindingPaths={path("/user/hand/left/input/menu/click"),path("/user/hand/right/input/menu/click")};
 for(uint32_t role:{0u,1u}){
   auto& controller=role==0?session.controllers.left:session.controllers.right;
   for(bool pressed:{true,false}){
     controller.buttons=pressed?(1ull<<2):0;UpdateActionSnapshot(menu,role,controller);
     get.action=reinterpret_cast<XrAction>(menu);get.subactionPath=role==0?left:right;result={};
     assert(GetActionSnapshot(&session,&get,XR_ACTION_TYPE_BOOLEAN_INPUT,actual,result,active)==XR_SUCCESS);
     assert(active&&result.boolean==pressed);
   }
 }
 auto vibration=action(XR_ACTION_TYPE_VIBRATION_OUTPUT);vibration->subactionPaths={left,right};
 vibration->bindingPaths={path("/user/hand/left/output/haptic"),path("/user/hand/right/output/haptic")};
 XrHapticActionInfo hapticInfo{XR_TYPE_HAPTIC_ACTION_INFO};hapticInfo.action=reinterpret_cast<XrAction>(vibration);
 XrHapticVibration pulse{XR_TYPE_HAPTIC_VIBRATION};pulse.amplitude=.7f;pulse.frequency=120;pulse.duration=3000000000LL;
 auto sessionHandle=reinterpret_cast<XrSession>(&session);
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_SUCCESS);
 assert(sentHaptics.size()==2&&sentHaptics[0].role==0&&sentHaptics[1].role==1&&sentHaptics[0].durationSeconds==3);
 sentHaptics.clear();hapticInfo.subactionPath=right;
 assert(StopHapticFeedback(sessionHandle,&hapticInfo)==XR_SUCCESS);
 assert(sentHaptics.size()==1&&sentHaptics[0].role==1&&sentHaptics[0].amplitude==0&&sentHaptics[0].durationSeconds==0);
 sentHaptics.clear();pulse.duration=XR_MIN_HAPTIC_DURATION;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_SUCCESS);
 assert(sentHaptics.size()==1&&sentHaptics[0].durationSeconds==.05f);
 sentHaptics.clear();pulse.amplitude=2;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_VALIDATION_FAILURE);
 assert(sentHaptics.empty());

 // Execute production SyncActions, including OpenComposite's two-hand list.
 const auto setHandle=reinterpret_cast<XrActionSet>(&set);
 XrActiveActionSet both[]={{setHandle,left},{setHandle,right}};
 XrActionsSyncInfo sync{XR_TYPE_ACTIONS_SYNC_INFO};sync.countActiveActionSets=2;sync.activeActionSets=both;
 sampledControllers.left.trigger=.2f;sampledControllers.right.trigger=.9f;
 triggerAction->bindingPaths={path("/user/hand/left/input/trigger/value"),path("/user/hand/right/input/trigger/value")};
 assert(SyncActions(sessionHandle,&sync)==XR_SUCCESS);
 assert(session.activeActionSets.size()==1&&session.activeSetSubactions.at(setHandle)==3);
 auto readTrigger=[&](XrPath hand,float expected,bool expectedActive){
   get.action=reinterpret_cast<XrAction>(triggerAction);get.subactionPath=hand;result={};
   assert(GetActionSnapshot(&session,&get,XR_ACTION_TYPE_FLOAT_INPUT,actual,result,active)==XR_SUCCESS);
   assert(active==expectedActive&&result.scalar==expected);
 };
 readTrigger(left,.2f,true);readTrigger(right,.9f,true);readTrigger(XR_NULL_PATH,.9f,true);
 sync.countActiveActionSets=1;
 assert(SyncActions(sessionHandle,&sync)==XR_SUCCESS);
 assert(ActionSetRoleIsActive(&session,&set,0)&&!ActionSetRoleIsActive(&session,&set,1));
 readTrigger(left,.2f,true);readTrigger(right,0,false);readTrigger(XR_NULL_PATH,.2f,true);
 // Identical pairs are idempotent; wildcard unions do not depend on order.
 both[1]=both[0];sync.countActiveActionSets=2;
 assert(SyncActions(sessionHandle,&sync)==XR_SUCCESS&&session.activeSetSubactions.at(setHandle)==1);
 for(bool wildcardFirst:{false,true}){
   both[wildcardFirst?0:1]={setHandle,XR_NULL_PATH};both[wildcardFirst?1:0]={setHandle,left};
   assert(SyncActions(sessionHandle,&sync)==XR_SUCCESS&&session.activeSetSubactions.at(setHandle)==3);
   readTrigger(right,.9f,true);
 }
 auto savedMask=session.activeSetSubactions;
 auto savedSets=session.activeActionSets;
 const float savedTrigger=session.controllers.right.trigger;
 const auto savedValues=triggerAction->values;
 unsigned savedObserve=observeCalls;
 auto unchanged=[&]{assert(session.activeSetSubactions==savedMask&&session.activeActionSets==savedSets&&session.controllers.right.trigger==savedTrigger&&triggerAction->values.at(1).scalar==savedValues.at(1).scalar&&observeCalls==savedObserve);};
 both[0]={setHandle,left};both[1]={XR_NULL_HANDLE,right};
 assert(SyncActions(sessionHandle,&sync)==XR_ERROR_HANDLE_INVALID);unchanged();
 ActionSet unattached{&i};both[1]={reinterpret_cast<XrActionSet>(&unattached),right};
 assert(SyncActions(sessionHandle,&sync)==XR_ERROR_ACTIONSET_NOT_ATTACHED);unchanged();
 Instance foreignInstance;ActionSet foreign{&foreignInstance};both[1]={reinterpret_cast<XrActionSet>(&foreign),right};
 assert(SyncActions(sessionHandle,&sync)==XR_ERROR_HANDLE_INVALID);unchanged();
 both[1]={setHandle,path("/user/head")};assert(SyncActions(sessionHandle,&sync)==XR_ERROR_PATH_UNSUPPORTED);unchanged();
 // A recognized hand path still must be declared by some action in this set.
 auto undeclared=std::make_unique<ActionSet>();undeclared->instance=&i;auto undeclaredHandle=reinterpret_cast<XrActionSet>(undeclared.get());
 session.attachedActionSets.push_back(undeclaredHandle);i.actionSets.push_back(std::move(undeclared));
 both[1]={undeclaredHandle,right};assert(SyncActions(sessionHandle,&sync)==XR_ERROR_PATH_UNSUPPORTED);unchanged();
 both[1]={setHandle,right};failControllerRead=true;
 assert(SyncActions(sessionHandle,&sync)==XR_ERROR_RUNTIME_FAILURE);
 assert(session.activeSetSubactions==savedMask&&session.controllers.right.trigger==savedTrigger);
 failControllerRead=false;
 sync.countActiveActionSets=0;sync.activeActionSets=nullptr;
 assert(SyncActions(sessionHandle,&sync)==XR_SUCCESS&&session.activeActionSets.empty()&&session.activeSetSubactions.empty());
 readTrigger(right,0,false);
 sync.countActiveActionSets=2;sync.activeActionSets=both;
 session.state=XR_SESSION_STATE_VISIBLE;
 assert(SyncActions(sessionHandle,&sync)==XR_SESSION_NOT_FOCUSED&&session.activeSetSubactions.empty());
 readTrigger(left,0,false);session.state=XR_SESSION_STATE_FOCUSED;
 assert(SyncActions(sessionHandle,&sync)==XR_SUCCESS);
 // Both-hand activation must not broaden an explicitly single-hand haptic request.
 sentHaptics.clear();pulse.amplitude=.7f;hapticInfo.subactionPath=left;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_SUCCESS);
 assert(sentHaptics.size()==1&&sentHaptics[0].role==0);
 sentHaptics.clear();hapticInfo.subactionPath=right;
 assert(StopHapticFeedback(sessionHandle,&hapticInfo)==XR_SUCCESS);
 assert(sentHaptics.size()==1&&sentHaptics[0].role==1);


 // Khronos haptic semantics: valid requests need no physical output device.
 // Exercise the actual production functions, with only transport replaced.
 sentHaptics.clear();pulse.amplitude=.7f;pulse.frequency=120;pulse.duration=1000000;
 auto unboundHaptic=action(XR_ACTION_TYPE_VIBRATION_OUTPUT);unboundHaptic->subactionPaths={left};
 hapticInfo.action=reinterpret_cast<XrAction>(unboundHaptic);hapticInfo.subactionPath=left;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_SUCCESS);
 assert(StopHapticFeedback(sessionHandle,&hapticInfo)==XR_SUCCESS&&sentHaptics.empty());
 // No binding is different from an explicitly undeclared subaction path.
 hapticInfo.subactionPath=right;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_PATH_UNSUPPORTED);
 assert(StopHapticFeedback(sessionHandle,&hapticInfo)==XR_ERROR_PATH_UNSUPPORTED);
 hapticInfo.action=reinterpret_cast<XrAction>(vibration);hapticInfo.subactionPath=left;
 for(auto state:{XR_SESSION_STATE_READY,XR_SESSION_STATE_VISIBLE,XR_SESSION_STATE_STOPPING}){
   session.state=state;
   assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_SESSION_NOT_FOCUSED);
   assert(StopHapticFeedback(sessionHandle,&hapticInfo)==XR_SESSION_NOT_FOCUSED&&sentHaptics.empty());
 }
 // Validation must remain effective even when unfocused (and no output occurs).
 pulse.amplitude=2;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_VALIDATION_FAILURE);
 pulse.amplitude=.7f;session.state=XR_SESSION_STATE_FOCUSED;
 pulse.duration=-2;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_VALIDATION_FAILURE);
 pulse.duration=1000000;pulse.frequency=std::numeric_limits<float>::quiet_NaN();
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_VALIDATION_FAILURE);
 pulse.frequency=120;pulse.amplitude=std::numeric_limits<float>::infinity();
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_VALIDATION_FAILURE);
 pulse.amplitude=.7f;hapticInfo.action=reinterpret_cast<XrAction>(axis);
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_ACTION_TYPE_MISMATCH);
 assert(StopHapticFeedback(sessionHandle,&hapticInfo)==XR_ERROR_ACTION_TYPE_MISMATCH);
 hapticInfo.action=XR_NULL_HANDLE;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_HANDLE_INVALID);
 assert(StopHapticFeedback(sessionHandle,&hapticInfo)==XR_ERROR_HANDLE_INVALID);
 hapticInfo.action=reinterpret_cast<XrAction>(vibration);
 assert(ApplyHapticFeedback(XR_NULL_HANDLE,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_HANDLE_INVALID);
 assert(StopHapticFeedback(XR_NULL_HANDLE,&hapticInfo)==XR_ERROR_HANDLE_INVALID);
 failHapticSubmit=true;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_ERROR_RUNTIME_FAILURE);
 assert(StopHapticFeedback(sessionHandle,&hapticInfo)==XR_ERROR_RUNTIME_FAILURE&&sentHaptics.empty());
 failHapticSubmit=false;
 assert(ApplyHapticFeedback(sessionHandle,&hapticInfo,reinterpret_cast<XrHapticBaseHeader*>(&pulse))==XR_SUCCESS);
 assert(sentHaptics.size()==1&&sentHaptics[0].role==0);


 // Check actual entry points identify the error before testing helper bounds.
 auto traced=[&](const char* text){return std::any_of(traceLines.begin(),traceLines.end(),[&](const auto& line){return line.find(text)!=std::string::npos;});};
 assert(traced("haptic-apply phase=vibration result=-1 detail=-2"));
 assert(traced("haptic-apply phase=subaction result=-22"));
 assert(traced("haptic-apply phase=focus result=8"));
 assert(traced("haptic-apply phase=bridge result=-2 detail=-1"));
 // Diagnostics run only for exceptional results and are bounded per phase/op.
 traceLines.clear();
 for(int n=0;n<2048;++n)assert(HapticResult(false,HapticStructure,XR_SUCCESS)==XR_SUCCESS);
 assert(traceLines.empty());
 for(int n=0;n<1024;++n)assert(HapticResult(false,HapticBridge,XR_ERROR_RUNTIME_FAILURE,-7)==XR_ERROR_RUNTIME_FAILURE);
 // Earlier transport-failure check consumed count1; this adds2..1025:
 // seven initial records, then512 and1024. Other phases cannot suppress this.
 assert(traceLines.size()==9);
 assert(traceLines.front().find("haptic-apply phase=bridge result=-2 detail=-7")!=std::string::npos);
 assert(traceLines.back().find("count=1024")!=std::string::npos);
 traceLines.clear();
 assert(HapticResult(true,HapticStructure,XR_ERROR_VALIDATION_FAILURE)==XR_ERROR_VALIDATION_FAILURE);
 assert(traceLines.size()==1&&traceLines[0].find("haptic-stop phase=structure result=-1")!=std::string::npos);

 puts("PASS: production input values, multi-hand synchronization, duplicate/wildcard union, transactional validation, focus, hand isolation, profiles, menus, haptic routing, unfocused/unbound outputs and preserved error validation");
}
'''
with tempfile.TemporaryDirectory(prefix='wvr-input-') as work:
    cpp = Path(work)/'test.cpp'
    cpp.write_text(preamble+'\n'.join(functions)+tests)
    exe = Path(work)/'test'
    subprocess.run(['clang++','-std=c++20','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(root/'third-party/openxr/include'),'-I',str(root/'windows-vr-openxr/include'),str(cpp),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
