#!/usr/bin/env python3
"""Exercise the production WoW64 SMC gate and FEX atomic/alias helpers on ARM64 Mac.

Compile exact extracted production functions under ASan/UBSan. Fake only
thread/JIT identity, Unix-call boundary and exception delivery; no Wine, guest or device executes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--runtime-source', required=True, type=Path)
parser.add_argument('--build', required=True, type=Path)
args = parser.parse_args()
prepared = args.runtime_source.resolve()
output = args.build.resolve()
assert not output.is_relative_to(prepared) and not output.is_relative_to(ROOT), 'build must be outside source trees'
output.mkdir(parents=True, exist_ok=True)
work = Path(tempfile.mkdtemp(prefix='smc-atomic-', dir=output))
relative = 'FEX/Source/Windows/WOW64/Module.cpp'
target = work / 'source' / relative
target.parent.mkdir(parents=True)
shutil.copyfile(prepared / relative, target)
patch = ROOT / 'windows-runtime-plugin/patches/0017-fex-wow64-unaligned-smc-exchange.patch'
def apply(*flags):
    return subprocess.run(['git', 'apply', *flags, str(patch)], cwd=work/'source',
                          capture_output=True, text=True)
if apply('--check').returncode:
    result = apply('--reverse')
    assert result.returncode == 0, result.stderr
before = target.read_text()
result = apply()
assert result.returncode == 0, result.stderr
after = target.read_text()
def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    end, depth = opening + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]
def smc_tail(text):
    anchor = text.index('Context->X1 = 1; // Set ENTRY_FILL_SRA_SINGLE_INST_REG')
    start = text.index('        } else {', anchor) + len('        } else {')
    end = text.index('\n        if (Handled) return true;', start) if 'if (Handled) return true;' in text[start:] else text.index('\n        return true;', start)
    # Exclude the closing else brace; this wrapper executes the exact else body.
    return text[start:end].rsplit('        }', 1)[0]

# Privately apply the normal Wine bridge patch, including already-prepared inputs.
handoff_patch = ROOT/'windows-runtime-plugin/patches/0019-wow64-mono-bridge-handoff.patch'
wine_paths = ['wine/dlls/ntdll/signal_arm64.c', 'wine/dlls/ntdll/ntdll.spec',
              'wine/dlls/wow64/syscall.c']
wine_original = {}
for relative in wine_paths:
    original = prepared/relative
    destination = work/'source'/relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original, destination)
    wine_original[relative] = hashlib.sha256(original.read_bytes()).hexdigest()
def apply_handoff(*flags):
    return subprocess.run(['git','apply',*flags,str(handoff_patch)], cwd=work/'source',
                          capture_output=True,text=True)
if apply_handoff('--check').returncode:
    result = apply_handoff('--reverse')
    assert result.returncode == 0, result.stderr
result = apply_handoff()
assert result.returncode == 0, result.stderr
signal = (work/'source'/wine_paths[0]).read_text()
spec = (work/'source'/wine_paths[1]).read_text()
wow64 = (work/'source'/wine_paths[2]).read_text()
getter = function(signal, 'NTSTATUS WINAPI __wine_ios_get_mono_bridge(')
handoff = function(wow64, 'static void init_ios_mono_bridge(')
process_init = function(wow64, 'static DWORD WINAPI process_init(')
# Verify actual loader wiring: native export resolved from ntdll, backend export
# from the CPU DLL, both translated before any call, before guest initialization.
ordered = ['GET_PTR( __wine_ios_get_mono_bridge );', 'module = load_cpu_dll(',
           'GET_PTR( BTCpuIosSetMonoBridge );', 'XLATE_PTR( BTCpuIosSetMonoBridge );',
           'XLATE_PTR( __wine_ios_get_mono_bridge );', 'pBTCpuProcessInit();',
           'init_ios_mono_bridge();', 'init_image_mapping( module );']
positions = [process_init.index(marker) for marker in ordered]
assert positions == sorted(positions), 'native-to-guest bridge init ordering changed'
assert '#define XLATE_PTR(name) p ## name = jit_pool_code_ptr( p ## name )' in process_init
assert '@ stdcall -private -arch=arm64 __wine_ios_get_mono_bridge(ptr)' in spec
unix_enum = function((prepared/'wine/dlls/ntdll/unixlib.h').read_text(), 'enum ntdll_unix_funcs') + ';'

atomic = (prepared/'FEX/FEXCore/Source/Utils/ArchHelpers/Arm64.cpp').read_text()
alias = (prepared/'FEX/Source/Windows/WOW64/IosMonoBridge.cpp').read_text()
bridge = (prepared/'FEX/Source/Windows/ARM64EC/IosMonoBridge.h').read_text()
gate = function(after, 'std::optional<bool> HandleIosSmcUnalignedExchange(')
context = function(after, 'bool HandleUnalignedAccess(TLS TLS, CONTEXT* Context)')
# Extract the real JIT atomic-memory dispatch branch, including the production
# mask/decoder and success offset; unrelated instruction families are not faked.
dispatch = function(atomic[atomic.index('  const auto Frame = Thread->CurrentFrame;'):], '} else if ((Instr & ArchHelpers::Arm64::ATOMIC_MEM_MASK) == ArchHelpers::Arm64::ATOMIC_MEM_INST)')
dispatch = dispatch.removeprefix('} else ')
# Select the actual JIT branch, after its production frame/block lookup.
constants = '\n'.join(re.findall(r'^constexpr uint32_t ATOMIC_.*?;', atomic, re.M))
shell = r"""
#include <atomic>
#include <array>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <optional>
#include <thread>
#include <vector>
#define FEX_IOS_HOST 1
#define FEXCORE_TELEMETRY_SET(...) ((void)0)
namespace LogMan::Msg {
template<class... T> void DFmt(const char*,T...) {}
template<class... T> void EFmt(const char*,T...) {}
}
namespace FEXCore::Utils::SpinWaitLock {
template<class T> struct UniqueSpinMutex { explicit UniqueSpinMutex(T*) { std::abort(); } };
}
namespace FEXCore::DualMap { int64_t WriteOffset=1; }
""" + bridge + r"""
#define WINAPI
#define __declspec(...)
#define TRACE(...) ((void)0)
#define ERR(...) ((void)0)
using ULONG64=uint64_t;
using NTSTATUS=int32_t;
constexpr NTSTATUS STATUS_INVALID_PARAMETER=static_cast<int32_t>(0xc000000d);
ios_mono_bridge Table{};
ios_mono_bridge* g_MonoBridge=nullptr;
unsigned UnixCalls{},PublishCalls{};
NTSTATUS UnixStatus{};
ULONG64 UnixBridge{};
void* Published{};
void ios_fex_mono_bridge_publish(void* b) { ++PublishCalls;Published=b; }
""" + unix_enum + r"""
NTSTATUS TestUnixCall(unsigned ordinal,ULONG64* out) {
 assert(ordinal==unix_ios_mono_bridge_ptr);++UnixCalls;
 *out=UnixBridge;return UnixStatus;
}
#define WINE_UNIX_CALL(ordinal,args) TestUnixCall(ordinal,args)
""" + getter + r"""
extern "C" {
""" + function(alias, '__declspec(dllexport) void BTCpuIosSetMonoBridge(') + '\n' + function(alias, 'uint64_t IosMonoResolveRW(') + r"""
}
static void (WINAPI *pBTCpuIosSetMonoBridge)(ULONG64);
static NTSTATUS (WINAPI *p__wine_ios_get_mono_bridge)(ULONG64*);
""" + handoff + r"""
namespace FEXCore::ArchHelpers::Arm64 {
""" + constants + '\n' + function(atomic, 'static uint64_t IosAtomicWritableAlias(') + r"""
template<class T> using CASExpectedFn=T (*)(T,T);
template<class T> using CASDesiredFn=T (*)(T,T);
""" + '\n'.join(function(atomic, s) for s in [
    'static uint32_t LoadAcquire32(', 'static bool StoreCAS32(']) + '\n' + (
    'template<bool Retry>\n' + function(atomic, 'static uint32_t DoCAS32(')) + r"""
// The gate admits 32-bit SWP only. Reaching another-width implementation is
// a contract error; the complete production decoder remains compiled unchanged.
template<bool R, class... A> uint16_t DoCAS16(A...) { std::abort(); }
template<bool R, class... A> uint64_t DoCAS64(A...) { std::abort(); }
""" + function(atomic, 'static bool HandleAtomicMemOp(') + r"""
}
struct FakeCTX {
 uint64_t lo{},hi{};
 bool IsAddressInCodeBuffer(void*,uint64_t pc) { return pc>=lo && pc<hi; }
};
struct ThreadState { FakeCTX* CTX; };
struct TLS {
 ThreadState* thread;
 ThreadState* ThreadState() const { return thread; }
};
struct CONTEXT {
 union { uint64_t X[31]; struct { uint64_t X0; }; };
 uint64_t Pc;
};
namespace FEXCore::ArchHelpers::Arm64 {
enum class UnalignedHandlerType { Atomic };
bool ForceZeroSkip=false;
std::optional<int32_t> HandleUnalignedAccess(::ThreadState*,UnalignedHandlerType,
                                           uintptr_t ProgramCounter,uint64_t* GPRs) {
 if (ForceZeroSkip) return 0;
 uint32_t* PC=reinterpret_cast<uint32_t*>(ProgramCounter);
 uint32_t Instr=PC[0];
 uint32_t* StrictSplitLockMutex=nullptr;
""" + dispatch + r"""
 return std::nullopt;
}
}
struct Config {
 auto GetUnalignedHandlerType() { return FEXCore::ArchHelpers::Arm64::UnalignedHandlerType::Atomic; }
};
std::optional<Config> HandlerConfig{Config{}};
namespace Context {
""" + context + '\n' + gate + r"""
}
bool OldSmc(TLS TLS,CONTEXT* Context,uint64_t FaultAddress) {
""" + smc_tail(before) + r"""
 return true;
}
bool NewSmc(TLS TLS,CONTEXT* Context,uint64_t FaultAddress) {
 bool Handled=true;
""" + smc_tail(after) + r"""
 return Handled;
}
"""
driver = r"""
int main() {
 alignas(16) std::array<uint8_t,1024> bytes{};
 alignas(4) uint32_t instruction=0xb8e48304u;
 const uint64_t pc=reinterpret_cast<uintptr_t>(&instruction);
 const uint64_t rx=0x7903340000ULL;
 FakeCTX ctx{pc,pc+4};ThreadState thread{&ctx};TLS tls{&thread};
 Table.alias_count=1;
 auto live=[&] { Table.aliases[0]={rx,reinterpret_cast<uintptr_t>(bytes.data()),bytes.size(),1,0}; };
 auto prepare=[&](unsigned offset=0x207) {
  live();bytes.fill(0xa5);instruction=0xb8e48304u;
  uint32_t old=0x11223344;
  memcpy(bytes.data()+offset,&old,4);
  CONTEXT c{};c.Pc=pc;c.X[24]=rx+offset;c.X[4]=0x55667788;
  return c;
 };
 auto value=[&](unsigned o) { uint32_t v;memcpy(&v,bytes.data()+o,4);return v; };
 auto canaries=[&](unsigned o) {
  for(unsigned i=0;i<bytes.size();i++)
   if(i<o || i>=o+4) assert(bytes[i]==0xa5);
 };
 // The native alias table can be live while this separately linked WoW64
 // FEX copy is still unbound: reproduce the actual missing handoff seam.
 auto c=prepare();
 auto absent=Context::HandleIosSmcUnalignedExchange(tls,&c,c.X[24]);
 assert(absent && !*absent && c.Pc==pc && value(0x207)==0x11223344);
 assert(IosMonoResolveRW(rx+0x200,16)==0);
 assert(__wine_ios_get_mono_bridge(nullptr)==STATUS_INVALID_PARAMETER && UnixCalls==0);
 UnixBridge=reinterpret_cast<uintptr_t>(&Table);
 assert(UnixBridge>UINT32_MAX); // real full-width host pointer, never guest ULONG
 auto resetBinding=[&] {g_MonoBridge=nullptr;Published=nullptr;PublishCalls=UnixCalls=0;};
 pBTCpuIosSetMonoBridge=nullptr;p__wine_ios_get_mono_bridge=__wine_ios_get_mono_bridge;
 init_ios_mono_bridge();assert(!g_MonoBridge && UnixCalls==0);
 pBTCpuIosSetMonoBridge=BTCpuIosSetMonoBridge;p__wine_ios_get_mono_bridge=nullptr;
 init_ios_mono_bridge();assert(!g_MonoBridge && UnixCalls==0);
 p__wine_ios_get_mono_bridge=__wine_ios_get_mono_bridge;
 UnixStatus=static_cast<int32_t>(0xc0000002);init_ios_mono_bridge();
 assert(!g_MonoBridge && UnixCalls==1 && PublishCalls==0);
 resetBinding();UnixStatus=0;UnixBridge=0;init_ios_mono_bridge();
 assert(!g_MonoBridge && UnixCalls==1 && PublishCalls==0);
 resetBinding();UnixBridge=reinterpret_cast<uintptr_t>(&Table);
 Table.abi_version=IOS_MONO_ABI_VERSION+1;init_ios_mono_bridge();
 assert(!g_MonoBridge && UnixCalls==1 && PublishCalls==0);
 BTCpuIosSetMonoBridge(0);assert(!g_MonoBridge && PublishCalls==0);
 resetBinding();Table.abi_version=IOS_MONO_ABI_VERSION;init_ios_mono_bridge();
 assert(g_MonoBridge==&Table && Published==&Table && UnixCalls==1 && PublishCalls==1);
 assert(IosMonoResolveRW(rx+0x200,16)==reinterpret_cast<uintptr_t>(bytes.data()+0x200));
 puts("PASS actual native getter/WoW64 init/FEX setter: missing hooks/status/null/ABI fail closed; full64 pointer publishes actual alias table");
 // Actual old SMC else reports success at an unchanged PC with no write.
 c=prepare();
 assert(OldSmc(tls,&c,c.X[24]) && c.Pc==pc && value(0x207)==0x11223344);
 puts("PASS exact old SMC negative: claimed handled with unchanged PC/value");
 for(unsigned offset:{0x201,0x202,0x203,0x205,0x206,0x207,0x209,0x20a,0x20b}) {
  c=prepare(offset);
  auto result=Context::HandleIosSmcUnalignedExchange(tls,&c,c.X[24]);
  assert(result && *result && c.Pc==pc+4 && c.X[4]==0x11223344);
  assert(value(offset)==0x55667788);canaries(offset);
 }
 c=prepare();assert(NewSmc(tls,&c,c.X[24]) && c.Pc==pc+4);
 assert(value(0x207)==0x55667788 && c.X[4]==0x11223344);canaries(0x207);
 puts("PASS recorded SWPAL returns old32, writes new32, advances PC+4, preserves canaries");
 auto unchanged=[&](bool applicable) {
  const auto original=c;
  const auto snapshot=bytes;
  auto r=Context::HandleIosSmcUnalignedExchange(tls,&c,c.X[24]);
  assert(r.has_value()==applicable);
  if(r) assert(!*r);
  assert(c.Pc==original.Pc && std::equal(std::begin(c.X),std::end(c.X),std::begin(original.X)));
  assert(bytes==snapshot);
 };
 c=prepare(0x208);unchanged(false); // aligned: existing path remains
 c=prepare();instruction=0x88'9f'fc'04;unchanged(false); // byte STLR: never backpatch
 c=prepare();instruction=0xf8e48304;unchanged(false); // width64 outside scope
 c=prepare();instruction=0xb8e40304;unchanged(false); // LDADD outside scope
 c=prepare();ctx.hi=pc;unchanged(false);ctx.hi=pc+4; // non-JIT before instruction read
 c=prepare();c.X[24]=UINT64_MAX-1;unchanged(true); // footprint overflow
 c=prepare(0x20f);unchanged(true); // crosses16: do not enter split-CAS fallback
 c=prepare();Table.aliases[0].generation=2;unchanged(true);
 c=prepare();Table.aliases[0].size=0x20b;unchanged(true); // 4 fits, whole16 doesn't
 c=prepare();Table.aliases[0].host_rw++;unchanged(true);
 c=prepare();g_MonoBridge=nullptr;unchanged(true);g_MonoBridge=&Table;
 c=prepare();assert(!Context::HandleIosSmcUnalignedExchange(tls,&c,c.X[24]+1).value());
 assert(c.Pc==pc && value(0x207)==0x11223344);
 c=prepare();FEXCore::ArchHelpers::Arm64::ForceZeroSkip=true;
 assert(!NewSmc(tls,&c,c.X[24]) && c.Pc==pc && value(0x207)==0x11223344);
 FEXCore::ArchHelpers::Arm64::ForceZeroSkip=false;
 puts("PASS aligned/byte/unknown/non-JIT remain outside; mismatch/cross16/stale/short/misaligned/missing alias/unchanged-PC fail closed");

 // Exchange linearizability: old values plus final value must be precisely
 // initial plus every distinct written value, even with overlapping writers.
 c=prepare();
 constexpr unsigned count=1000,workers=4;
 std::array<std::vector<uint32_t>,workers> oldValues;
 std::vector<std::thread> tasks;
 for(unsigned t=0;t<workers;t++) tasks.emplace_back([&,t]{
  for(unsigned i=0;i<count;i++) {
   CONTEXT local{};local.Pc=pc;local.X[24]=rx+0x207;local.X[4]=1+t*count+i;
   assert(NewSmc(tls,&local,local.X[24]) && local.Pc==pc+4);
   oldValues[t].push_back(local.X[4]);
  }
 });
 for(auto& task:tasks) task.join();
 std::vector<uint32_t> actual,expected{0x11223344};
 for(auto& values:oldValues) actual.insert(actual.end(),values.begin(),values.end());
 actual.push_back(value(0x207));
 for(unsigned i=1;i<=count*workers;i++) expected.push_back(i);
 std::sort(actual.begin(),actual.end());std::sort(expected.begin(),expected.end());
 assert(actual==expected);canaries(0x207);
 puts("PASS 4000 contended production exchanges: no lost/duplicated values, canaries intact");
}
"""
unit = work/'production-atomic.cpp'
unit.write_text(shell+driver)
command = ['xcrun','--sdk','macosx','clang++','-std=c++20','-O1','-g',
           '-fsanitize=address,undefined','-fno-omit-frame-pointer',str(unit),'-o',str(work/'probe')]
subprocess.run(command,check=True,timeout=120)
result=subprocess.run([str(work/'probe')],capture_output=True,text=True,timeout=30)
(work/'stdout.txt').write_text(result.stdout)
(work/'stderr.txt').write_text(result.stderr)
assert result.returncode==0, result.stdout+result.stderr

# Compile the COMPLETE original and patched reset functions. External helpers
# are controlled boundaries here; the first probe above exercises the real
# atomic gate/decoder/alias/CAS bodies. Together these cover both emulation and
# its negative dispatch integration, rather than assuming false means cleanup.
full_shell = r"""
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <mutex>
#include <optional>
#include <cstdio>
#include <vector>
#define FEX_IOS_HOST 1
#define FEXCORE_PROFILE_ACCUMULATION(...) ((void)0)
#define FEXCORE_PROFILE_INSTANT_INCREMENT(...) ((void)0)
constexpr uint32_t EXCEPTION_ACCESS_VIOLATION=0xc0000005,EXCEPTION_DATATYPE_MISALIGNMENT=0x80000002,EXCEPTION_SINGLE_STEP=0x80000004;
struct CONTEXT { uint64_t X[31]{},X25{},X1{},Pc{};__uint128_t V[32]{}; };
struct EXCEPTION_RECORD { uint32_t ExceptionCode{};uint64_t ExceptionInformation[2]{}; };
struct EXCEPTION_POINTERS { EXCEPTION_RECORD* ExceptionRecord; CONTEXT* ContextRecord; };
struct WOW64_CONTEXT { uint32_t Eip{},Eax{},Ecx{},EFlags{}; };
struct Frame { struct {uint64_t rip{};} State;int SynchronousFaultData{}; };
struct ContextType {
 bool IsAddressInCodeBuffer(void*,uint64_t){return true;}
 bool IsCurrentBlockSingleInst(void*){return false;}
 bool IsAddressInCurrentBlock(void*,uint64_t,uint64_t){return false;}
};
ContextType CTXObj;auto CTX=&CTXObj;
struct ThreadType { ContextType* CTX=&CTXObj;Frame frame;Frame* CurrentFrame=&frame; };
ThreadType ThreadObj;
CONTEXT entry{.Pc=0xfeed};
struct TLS { void* TEB=this; ThreadType* ThreadStateIfInitialised(){return &ThreadObj;} CONTEXT* EntryContext(){return &entry;} };
TLS GetTLS(){return {};}
struct TrackerType { bool HandleAccessViolation(uint64_t){return false;} bool HandleRWXAccessViolation(void*,uint64_t,uint64_t){return true;} };
TrackerType tracker;TrackerType* OvercommitTracker=nullptr;TrackerType* InvalidationTracker=&tracker;
std::mutex ThreadCreationMutex;
namespace LogMan::Msg {template<class...T>void DFmt(const char*,T...){}}
namespace GuestWindow {uint64_t ToGuestIfInWindow(uint64_t a){return a;}}
namespace FEXCore::Utils {constexpr uint64_t FEX_PAGE_MASK=~4095ULL,FEX_PAGE_SIZE=4096;}
namespace FEXCore::X86State {constexpr int RFLAG_TF_RAW_LOC=8;}
int reconstructed{},guestException{},contextSet{},unlocked{};
std::vector<int> events;
std::optional<bool> atomicResult;
namespace FEX::Windows {
 namespace CallRetStack {bool HandleAccessViolation(void*,uint64_t,uint64_t){return false;}}
 namespace JITGuardPage {bool HandleJITGuardPage(void*,void*,uint64_t*,__uint128_t*,uint64_t*){return false;}}
 EXCEPTION_RECORD HandleGuestException(int&,EXCEPTION_RECORD record,uint32_t,uint32_t,uint32_t){guestException++;events.push_back(2);return record;}
}
namespace Context {
 bool HandleSuspendInterrupt(TLS,CONTEXT*,uint64_t){return false;}
 void ReconstructThreadState(TLS,CONTEXT*){}
 std::optional<bool> HandleIosSmcUnalignedExchange(TLS,CONTEXT* context,uint64_t){if(atomicResult && *atomicResult)context->Pc+=4;return atomicResult;}
 bool HandleUnalignedAccess(TLS,CONTEXT*){return false;}
 WOW64_CONTEXT ReconstructWowContext(TLS,CONTEXT*){reconstructed++;events.push_back(1);return {};}
 void UnlockJITContext(TLS){unlocked++;events.push_back(4);}
}
struct ConfigType {uint64_t AbsoluteLoopTopAddressFillSRA{};};
struct Signals {ConfigType GetConfig(){return {};}} signals;
auto SignalDelegator=&signals;
bool IsAddressInJit(uint64_t){return true;}
void* GetCurrentThread(){return nullptr;} void* GetCurrentProcess(){return nullptr;}
void BTCpuSetContext(void*,void*,void*,WOW64_CONTEXT*){contextSet++;events.push_back(3);}
"""
full_driver = r"""
int main(){
 auto reset=[] {
  reconstructed=guestException=contextSet=unlocked=0;events.clear();
 };
 EXCEPTION_RECORD record{.ExceptionCode=EXCEPTION_ACCESS_VIOLATION,.ExceptionInformation={1,0x7903340207}};
 CONTEXT context{.Pc=0x702636d184};EXCEPTION_POINTERS pointers{&record,&context};
 // Baseline complete production path claims SMC success without changing PC.
 atomicResult=false;reset();
 assert(ActualBefore(&pointers) && context.Pc==0x702636d184 && events.empty());
 puts("PASS complete baseline negative: old SMC handled unchanged PC");
 // Recognized unsafe emulation must leave scoped SMC handling and take the
 // exact existing reconstruction, guest exception, context set and unlock path.
 context.Pc=0x702636d184;reset();
 assert(!ActualAfter(&pointers));
 if (!(reconstructed==1 && guestException==1 && contextSet==1 && unlocked==1)) return 77;
 assert((events==std::vector<int>{1,2,3,4}) && context.Pc==entry.Pc);
 assert(ThreadCreationMutex.try_lock());ThreadCreationMutex.unlock();
 puts("PASS recognized-false runs guest reconstruction/exception/context/unlock in order, restores EntryContext, releases mutex");
 // A successful exact instruction advance still halts dispatch immediately.
 atomicResult=true;context.Pc=0x702636d184;reset();
 assert(ActualAfter(&pointers) && context.Pc==0x702636d188 && events.empty());
 assert(ThreadCreationMutex.try_lock());ThreadCreationMutex.unlock();
 puts("PASS atomic success PC+4 continues directly without guest exception");
 // Outside the narrow atomic gate, existing SMC behavior remains intact.
 atomicResult=std::nullopt;context.Pc=0x702636d184;reset();
 assert(ActualAfter(&pointers) && context.Pc==0x702636d184 && events.empty());
 puts("PASS unrecognized access retains legacy SMC retry");
 // Other exception types still take the same normal full-function fallback.
 atomicResult=false;record.ExceptionCode=EXCEPTION_DATATYPE_MISALIGNMENT;
 context.Pc=0x702636d184;reset();
 assert(!ActualAfter(&pointers) && (events==std::vector<int>{1,2,3,4}) && context.Pc==entry.Pc);
 puts("PASS non-SMC exception preserves existing reconstruction path");
}
"""

full_before = function(before, 'bool BTCpuResetToConsistentStateImpl(')
full_after = function(after, 'bool BTCpuResetToConsistentStateImpl(')
full_unit = work/'complete-reset.cpp'
full_unit.write_text(full_shell + full_before.replace('BTCpuResetToConsistentStateImpl(', 'ActualBefore(', 1) +
                     '\n' + full_after.replace('BTCpuResetToConsistentStateImpl(', 'ActualAfter(', 1) + full_driver)
full_command = ['xcrun','--sdk','macosx','clang++','-std=c++20','-O1','-g',
                '-fsanitize=address,undefined','-fno-omit-frame-pointer',
                str(full_unit),'-o',str(work/'complete-reset')]
subprocess.run(full_command,check=True,timeout=120)
full_result = subprocess.run([str(work/'complete-reset')],capture_output=True,text=True,timeout=30)
(work/'complete-reset.stdout.txt').write_text(full_result.stdout)
(work/'complete-reset.stderr.txt').write_text(full_result.stderr)
assert full_result.returncode == 0, full_result.stdout + full_result.stderr

# Mutation negative reproduces the exact rejected prior0017 return statement
# in the complete production function. The same driver must detect skipped
# reconstruction without deliberately crashing or generating a core dump.
assert 'Handled = *Atomic;' in full_after
broken_after = full_after.replace('Handled = *Atomic;', 'return *Atomic;', 1)
broken_unit = work/'prior-early-return-negative.cpp'
broken_unit.write_text(full_shell + full_before.replace('BTCpuResetToConsistentStateImpl(', 'ActualBefore(', 1) +
                       '\n' + broken_after.replace('BTCpuResetToConsistentStateImpl(', 'ActualAfter(', 1) + full_driver)
broken_command = [*full_command[:-3], str(broken_unit), '-o', str(work/'prior-early-return-negative')]
subprocess.run(broken_command,check=True,timeout=120)
broken_result = subprocess.run([str(work/'prior-early-return-negative')],capture_output=True,text=True,timeout=30)
assert broken_result.returncode == 77, 'complete-function test did not reject prior early-return bug: ' + broken_result.stdout + broken_result.stderr
(work/'prior-early-return-negative.stdout.txt').write_text(broken_result.stdout)
(work/'prior-early-return-negative.stderr.txt').write_text(broken_result.stderr)

report=dict(passed=True,scope=__doc__,command=command,stdout=result.stdout,
            completeResetCommand=full_command, completeResetStdout=full_result.stdout,
            priorEarlyReturnNegativeCommand=broken_command,
            priorEarlyReturnRejectedWithExit=broken_result.returncode,
            testSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            completeResetBeforeSha256=hashlib.sha256(full_before.encode()).hexdigest(),
            completeResetAfterSha256=hashlib.sha256(full_after.encode()).hexdigest(),
            completeResetProbeSha256=hashlib.sha256(full_unit.read_bytes()).hexdigest(),
            patchSha256=hashlib.sha256(patch.read_bytes()).hexdigest(),
            handoffPatchSha256=hashlib.sha256(handoff_patch.read_bytes()).hexdigest(),
            nativeGetterSha256=hashlib.sha256(getter.encode()).hexdigest(),
            wow64HandoffSha256=hashlib.sha256(handoff.encode()).hexdigest(),
            fexSetterSha256=hashlib.sha256(function(alias, '__declspec(dllexport) void BTCpuIosSetMonoBridge(').encode()).hexdigest(),
            loaderOrdering=ordered,
            winePreparedSources=wine_original,
            winePatchedSources={r: hashlib.sha256((work/'source'/r).read_bytes()).hexdigest() for r in wine_paths},
            originalWineSourcesUnchanged=all(hashlib.sha256((prepared/r).read_bytes()).hexdigest()==h for r,h in wine_original.items()),
            preparedSourceSha256=hashlib.sha256(before.encode()).hexdigest(),
            patchedSourceSha256=hashlib.sha256(after.encode()).hexdigest(),
            atomicSourceSha256=hashlib.sha256(atomic.encode()).hexdigest(),
            bridgeSourceSha256=hashlib.sha256(alias.encode()).hexdigest(),
            generatedProbeSha256=hashlib.sha256(unit.read_bytes()).hexdigest(),
            limitations=['Host ARM64 production functions with thread/JIT/exception boundaries controlled; not FEX guest execution.',
                         '32-bit SWP fitting aligned16 only; no cross16 atomic support claim.'])
(work/'result.json').write_text(json.dumps(report,indent=2)+'\n')
print(result.stdout,end='')
print(full_result.stdout,end='')
print('PASS complete-function negative rejects prior early return with exit77')
print('Receipt:',work/'result.json')
