#!/usr/bin/env python3
"""Test the actual native child mapper, guest init block and native DLL retry.
Compile production functions under ASan/UBSan with OS/PE map boundaries faked.
Use original init-block code as a negative control; never run Wine or a guest.
"""
import argparse
from pathlib import Path
import hashlib,json,re,shutil,subprocess,struct,tempfile
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--runtime-source',required=True,type=Path)
p.add_argument('--resource-source',type=Path,help='Optional PE farm root; defaults to runtime-source/app/Madeira')
p.add_argument('--build',required=True,type=Path)
a=p.parse_args()
a.build.mkdir(parents=True,exist_ok=True)
b=Path(tempfile.mkdtemp(prefix='native-child-',dir=a.build.resolve()))
root=a.runtime_source.resolve()
relative_files=['build/ntdll-unix/loader_ios.c','build/ntdll-unix/ios_mixed.h',
                'build/ntdll-unix/signal_arm64_ios.c','wine/dlls/ntdll/loader.c']
for rel in relative_files:
    target=b/'source'/rel
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(root/rel,target)
patch=ROOT/'windows-runtime-plugin/patches/0016-wine-i386-child-native-ntdll.patch'
def apply(*flags):
    return subprocess.run(['git','apply',*flags,str(patch)],cwd=b/'source',capture_output=True,text=True)
if apply('--check').returncode:
    result=apply('--reverse','--check')
    assert result.returncode==0,result.stderr
    result=apply('--reverse')
    assert result.returncode==0,result.stderr
before=(b/'source/build/ntdll-unix/loader_ios.c').read_text()
before_pe=(b/'source/wine/dlls/ntdll/loader.c').read_text()
result=apply()
assert result.returncode==0,result.stderr
after=(b/'source/build/ntdll-unix/loader_ios.c').read_text()
header=(b/'source/build/ntdll-unix/ios_mixed.h').read_text()
signal=(b/'source/build/ntdll-unix/signal_arm64_ios.c').read_text()
def function(s, signature):
 start=s.index(signature);opening=s.index('{',start);depth=1;end=opening+1
 while depth:
  depth+=(s[end]=='{')-(s[end]=='}');end+=1
 return s[start:end]
helper=function(after,'static int ios_load_child_native_ntdll(')
selection=function(after,'if (ios_cur_image_info()->Machine == IMAGE_FILE_MACHINE_I386 && is_arm64ec())')
pe_dir=function(after,'static const char *get_pe_dir(')
structure=re.search(r'struct ios_ntdll_funcs\n\{.*?\n\};',header,re.S).group()
winternl=(root/'wine/include/winternl.h').read_text()
start=winternl.index('typedef struct\n{',winternl.index('/* undocumented layout of LdrSystemDllInitBlock */'))
end=winternl.index('} SYSTEM_DLL_INIT_BLOCK;',start)+len('} SYSTEM_DLL_INIT_BLOCK;')
init_structure=winternl[start:end]
pe=(b/'source/wine/dlls/ntdll/loader.c').read_text()
start=pe.index('#ifdef __aarch64__\n    /* A native WoW64 child');end=pe.index('#endif',start)+len('#endif')
retry=pe[start:end]
# Exact unchanged EC inverse path still exists, and native path runs before the
# guest init data publication; private images skip the session-image copy.
assert function(before,'static int ios_load_child_ec_ntdll(').replace('        EC_GET( funcs.LdrInitializeThunk,','        EC_GET( funcs.LdrSystemDllInitBlock,           "LdrSystemDllInitBlock" );\n        EC_GET( funcs.LdrInitializeThunk,',1).replace('if (!funcs.LdrInitializeThunk || !p__wine_syscall_dispatcher || !p__wine_unixlib_handle)', 'if (!funcs.LdrInitializeThunk || !funcs.LdrSystemDllInitBlock || !p__wine_syscall_dispatcher || !p__wine_unixlib_handle)')==function(after,'static int ios_load_child_ec_ntdll(')
assert after.index('CHILD_STAGE( "load_child_native_ntdll" )')<after.index('CHILD_STAGE( "load_wow64_ntdll" )')
assert 'else if (!ios_cur_ntdll_funcs())\n        /* S1:' in after
assert 'SYSTEM_DLL_INIT_BLOCK *init_block = IOS_PFUNC(LdrSystemDllInitBlock);' in signal
assert 'i386_context->Eip = init_block->pRtlUserThreadStart;' in signal
# Real native PE must provide every export required by helper, not an assumed
# feature of the EC counterpart. Inspect actual supplied native PE resources.
resource=(a.resource_source or root/'app/Madeira')/'aarch64-windows/ntdll.dll'
required=re.findall(r'NATIVE_GET\(.*?,\s*"([^"]+)"\s*\)',helper)
resource_report={'status':'skipped','reason':'No ARM64 ntdll PE supplied; source contracts still run'}
if resource.is_file():
    data=resource.read_bytes();p=struct.unpack_from('<I',data,0x3c)[0];opt=p+24;sec=opt+struct.unpack_from('<H',data,p+20)[0];count=struct.unpack_from('<H',data,p+6)[0]
    assert struct.unpack_from('<H',data,p+4)[0]==0xaa64
    sections=[struct.unpack_from('<IIII',data,sec+i*40+8) for i in range(count)]
    def off(r):
     for vs,va,rs,raw in sections:
      if va<=r<va+max(vs,rs):return raw+r-va
     return r
    e=off(struct.unpack_from('<I',data,opt+112)[0]);n=struct.unpack_from('<I',data,e+24)[0];names=off(struct.unpack_from('<I',data,e+32)[0]);exports=set()
    for i in range(n):
     o=off(struct.unpack_from('<I',data,names+i*4)[0]);exports.add(data[o:data.index(b'\0',o)].decode())
    assert set(required)<=exports, set(required)-exports
    resource_report={'status':'verified','path':str(resource),'sha256':hashlib.sha256(data).hexdigest()}
else:
    print('SKIP real native PE export check: no aarch64-windows/ntdll.dll; pass --resource-source for PE verification')
# Native Unix compiles Wine WCHAR as16-bit while Darwin wchar_t is32-bit.
# Compile the exact mapper declaration with the real width; a wide literal
# initializer incorrectly accepted by the general string harness must fail here.
path_declaration=re.search(r'    static WCHAR path\[\] = .*?;',helper).group()
width_probe=b/'native-wchar-width.c'
width_probe.write_text('#include <stdint.h>\ntypedef uint16_t WCHAR;\n'+path_declaration+'\nint main(void) { return path[0] != 92 || path[1] != 63; }\n')
subprocess.run(['/usr/bin/clang','-std=c11','-Werror',str(width_probe),'-o',str(width_probe.with_suffix(''))],check=True)
subprocess.run([str(width_probe.with_suffix(''))],check=True)

# The recorded device failure is a real EC export with no native redirect:
# ARM64 FEX CRT calls ntdll!__chkstk, whose EC raw export is x64 RET (C3).
# Compare actual native and EC PE export bytes and metadata without executing PEs.
def pe_exports(path):
    binary=path.read_bytes(); nt=struct.unpack_from('<I',binary,0x3c)[0]; opt=nt+24
    sections=opt+struct.unpack_from('<H',binary,nt+20)[0]
    spans=[struct.unpack_from('<IIII',binary,sections+i*40+8) for i in range(struct.unpack_from('<H',binary,nt+6)[0])]
    def offset(rva):
        for vs,va,rs,raw in spans:
            if va<=rva<va+max(vs,rs): return raw+rva-va
        return rva
    directory=offset(struct.unpack_from('<I',binary,opt+112)[0])
    number=struct.unpack_from('<I',binary,directory+24)[0]
    functions=offset(struct.unpack_from('<I',binary,directory+28)[0])
    names=offset(struct.unpack_from('<I',binary,directory+32)[0])
    ordinals=offset(struct.unpack_from('<I',binary,directory+36)[0])
    exports={}
    for i in range(number):
        n=offset(struct.unpack_from('<I',binary,names+i*4)[0])
        name=binary[n:binary.index(b'\0',n)].decode()
        ordinal=struct.unpack_from('<H',binary,ordinals+i*2)[0]
        exports[name]=struct.unpack_from('<I',binary,functions+ordinal*4)[0]
    return binary,offset,opt,exports
farm=a.resource_source or root/'app/Madeira'
ec_resource=farm/'arm64ec-windows/ntdll.dll'
chkstk_report={'status':'skipped','reason':'Requires native and EC ntdll PE resources'}
if resource.is_file() and ec_resource.is_file():
    native,native_offset,_,native_exports=pe_exports(resource)
    ec,ec_offset,opt,ec_exports=pe_exports(ec_resource)
    native_rva=native_exports['__chkstk'];ec_rva=ec_exports['__chkstk']
    assert struct.unpack_from('<I',native,native_offset(native_rva))[0]==0xd65f03c0 # ARM64 RET
    assert ec[ec_offset(ec_rva)]==0xc3 # x64 RET; this is not an ARM64 instruction
    config=ec_offset(struct.unpack_from('<I',ec,opt+112+10*8)[0])
    base=struct.unpack_from('<Q',ec,opt+24)[0]
    metadata=ec_offset(struct.unpack_from('<Q',ec,config+200)[0]-base)
    table=ec_offset(struct.unpack_from('<I',ec,metadata+16)[0])
    count=struct.unpack_from('<I',ec,metadata+52)[0]
    redirects=dict(struct.unpack_from('<II',ec,table+i*8) for i in range(count))
    assert redirects.get(ec_rva,ec_rva)==ec_rva #0015 has no native body to select
    chkstk_report={'status':'verified','nativeRVA':hex(native_rva),'ecRVA':hex(ec_rva),
                   'ecSha256':hashlib.sha256(ec).hexdigest(),'nativeBytes':'c0035fd6','ecFirstByte':'c3','nativeRedirectionAbsent':True}
    print('PASS actual native/EC __chkstk export ABI boundary:',chkstk_report['nativeRVA'],chkstk_report['ecRVA'])
else:
    print('SKIP actual __chkstk PE metadata boundary: supply native and EC ntdll resources')

prelude=r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#define __aarch64__ 1
#define _WIN64 1
#define WINE_IOS 1
#define IMAGE_FILE_MACHINE_I386 0x14c
#define IMAGE_FILE_MACHINE_AMD64 0x8664
#define IMAGE_FILE_MACHINE_ARM64 0xaa64
#define IMAGE_FILE_MACHINE_ARM64EC 0xa641
#define IMAGE_FILE_MACHINE_ARM64X 0xa64e
#define IMAGE_FILE_MACHINE_ARMNT 0x1c4
#define IMAGE_DIRECTORY_ENTRY_EXPORT 0
#define IMAGE_FILE_EXPORT_DIRECTORY 0
#define STATUS_IMAGE_NOT_AT_BASE 1
#define STATUS_INVALID_IMAGE_FORMAT 2
#define STATUS_DLL_NOT_FOUND 3
#define STATUS_SUCCESS 0
#define STATUS_NO_MEMORY 4
#define FALSE 0
#define MAX_PATH 260
#define ARRAY_SIZE(x) (sizeof(x)/sizeof((x)[0]))
#define ERR(...) ((void)0)
typedef wchar_t WCHAR;
typedef void *HMODULE;
typedef void *HANDLE;
typedef uintptr_t ULONG_PTR;
typedef uintptr_t UINT_PTR;
typedef uintptr_t unixlib_handle_t;
typedef size_t SIZE_T;
typedef unsigned short WORD;
typedef struct { int dummy; } IMAGE_EXPORT_DIRECTORY;
typedef struct { int dummy; } PEB;
typedef struct { unsigned Machine; int ImageContainsCode,ComPlusNativeReady; } SECTION_IMAGE_INFORMATION;
typedef int BOOL;
#define TRUE 1
typedef struct { WCHAR *Buffer; } UNICODE_STRING;
typedef struct { int dummy; } OBJECT_ATTRIBUTES;
typedef uint32_t ULONG;
typedef uint64_t ULONG64;
'''+init_structure+r'''
'''+structure+r'''
static union {max_align_t align;unsigned char b[4096];} native, guest;
static SYSTEM_DLL_INIT_BLOCK parent_block;
static SYSTEM_DLL_INIT_BLOCK *pLdrSystemDllInitBlock=&parent_block;
static struct ios_ntdll_funcs owner;
static int registered,synced,map_status,map_machine=IMAGE_FILE_MACHINE_ARM64,guest_machine=IMAGE_FILE_MACHINE_I386;
static const char *missing;
static char mapped_path[1024];
static int build_dir=1;
static const char *ntdll_dir="/runtime",*dll_dir="/dll";
int ios_teb_tls_slot_offset=0x60;
static uintptr_t unix_call_funcs[1], unix_call_wow64_funcs[1];
static void __wine_syscall_dispatcher(void){}
static void __wine_unix_call_dispatcher(void){}
static void *p__wine_ctrl_routine;
void *ios_jit_reverse_translate_addr(const void *p){return (void*)p;}
void ios_jit_sync_write(void *p,size_t n){assert(p && n);++synced;}
static int ios_is_arm64ec_cur(void){return guest_machine==IMAGE_FILE_MACHINE_AMD64;}
static void init_unicode_string(UNICODE_STRING *s,WCHAR *v){s->Buffer=v;}
#define InitializeObjectAttributes(a,b,c,d,e) ((void)0)
static int open_builtin_pe_file(const char *name,OBJECT_ATTRIBUTES *a,void **module,SIZE_T *size,SECTION_IMAGE_INFORMATION *info,int x,int y,unsigned machine,int q,int r){
 (void)a;(void)x;(void)y;(void)q;(void)r;
 assert(machine==IMAGE_FILE_MACHINE_ARM64);snprintf(mapped_path,sizeof(mapped_path),"%s",name);
 *module=native.b;*size=sizeof(native.b);info->Machine=map_machine;return map_status;
}
static unsigned virtual_relocate_module(void *m){assert(m==native.b);return 0;}
static const IMAGE_EXPORT_DIRECTORY *get_module_data_dir(void *m,unsigned d,void *z){(void)m;(void)d;(void)z;return (void*)1;}
static const char *names[]={"LdrInitializeThunk","LdrSystemDllInitBlock","RtlUserThreadStart","KiUserExceptionDispatcher","KiUserApcDispatcher","KiUserCallbackDispatcher","KiRaiseUserExceptionDispatcher","DbgUiRemoteBreakin","__wine_syscall_dispatcher","__wine_unix_call_dispatcher","__wine_unixlib_handle","ios_teb_tsd_offset","p_ios_jit_reverse_translate_addr","__wine_ctrl_routine"};
static ULONG_PTR find_named_export(void *module,const IMAGE_EXPORT_DIRECTORY *e,const char *name){
 (void)e;if(missing && !strcmp(missing,name))return 0;
 for(unsigned i=0;i<ARRAY_SIZE(names);++i)if(!strcmp(names[i],name))return (uintptr_t)module+(!strcmp(name,"LdrSystemDllInitBlock")?0x400:0x100+i*16);
 return 0;
}
static void ios_set_proc_ntdll(void *peb,void *module,const struct ios_ntdll_funcs *f){assert(peb==(void*)0x123 && module==native.b);owner=*f;registered=1;}
static const struct ios_ntdll_funcs *ios_cur_ntdll_funcs(void){return registered?&owner:NULL;}
static int session_ec=1,boot_failed;
static int is_arm64ec(void){return session_ec;}
static const SECTION_IMAGE_INFORMATION *ios_cur_image_info(void){static SECTION_IMAGE_INFORMATION info;info.Machine=guest_machine;return &info;}
#define CHILD_STAGE(s) ((void)0)
#define CHILD_BOOT_FAIL(...) do {boot_failed=1;return;} while(0)

static ULONG_PTR ios_wow_base(void){return (uintptr_t)guest.b-0x100000;}
static struct {int WowTebOffset;} teb;
static WORD current_machine=IMAGE_FILE_MACHINE_ARM64;
static int hybrid_metadata,ilonly;
static int has_chpe_metadata(void *file,const SECTION_IMAGE_INFORMATION *info){(void)file;(void)info;return hybrid_metadata;}
static int is_com_ilonly(void *file,const SECTION_IMAGE_INFORMATION *info){(void)file;(void)info;return ilonly;}
#define NtCurrentTeb() (&teb)
static WCHAR retried_path[MAX_PATH];
static int opened;
static void RtlInitUnicodeString(UNICODE_STRING *s,const WCHAR *v){s->Buffer=(WCHAR*)v;}
static int open_dll_file(UNICODE_STRING *s,void *p,void *m,void *i,void *id){(void)p;(void)m;(void)i;(void)id;wcscpy(retried_path,s->Buffer);++opened;return 0;}
static void RtlFreeUnicodeString(UNICODE_STRING *s){free(s->Buffer);}
static int RtlCreateUnicodeString(UNICODE_STRING *s,const WCHAR *v){s->Buffer=wcsdup(v);return !!s->Buffer;}
'''
selection_wrapper='static void select_child_host(void) {PEB *child_peb=(PEB*)0x123;\n'+selection+'\n}\n'
retry_wrapper='static int retry_module(int status,const WCHAR *libname) {\n UNICODE_STRING storage={0},*nt_name=&storage;void *pwm=NULL,*mapping=NULL,*image_info=NULL,*id=NULL;\n'+retry+'\nfree(storage.Buffer);return status;\n}\n'
main=r'''
static void reset(void){memset(&native,0,sizeof(native));memset(&guest,0,sizeof(guest));memset(&parent_block,0x5a,sizeof(parent_block));((SYSTEM_DLL_INIT_BLOCK*)(native.b+0x400))->version=0xf0;registered=synced=boot_failed=0;session_ec=1;map_status=0;map_machine=IMAGE_FILE_MACHINE_ARM64;missing=NULL;guest_machine=IMAGE_FILE_MACHINE_I386;}
int main(void){
 SECTION_IMAGE_INFORMATION image={IMAGE_FILE_MACHINE_AMD64,1,0};
 teb.WowTebOffset=1;
#ifdef OLD
 assert(is_valid_binary(NULL,&image));
 puts("PASS negative control: original native WoW64 loader silently accepts AMD64/EC system DLL");
#else
 assert(!is_valid_binary(NULL,&image));
 puts("PASS native WoW64 rejects AMD64/EC code so native farm retry can run");
#endif
#ifndef OLD
 image.Machine=IMAGE_FILE_MACHINE_ARM64EC;assert(!is_valid_binary(NULL,&image));
 image.Machine=IMAGE_FILE_MACHINE_ARM64X;assert(!is_valid_binary(NULL,&image));
#endif
 image.Machine=IMAGE_FILE_MACHINE_ARM64;assert(is_valid_binary(NULL,&image));
 image.Machine=IMAGE_FILE_MACHINE_ARMNT;assert(is_valid_binary(NULL,&image));
 image.Machine=IMAGE_FILE_MACHINE_I386;assert(is_valid_binary(NULL,&image));
 teb.WowTebOffset=0;assert(!is_valid_binary(NULL,&image));
 image.ImageContainsCode=0;assert(is_valid_binary(NULL,&image));
 image.ImageContainsCode=1;image.ComPlusNativeReady=1;assert(is_valid_binary(NULL,&image));
 image.ComPlusNativeReady=0;ilonly=1;assert(is_valid_binary(NULL,&image));ilonly=0;
 reset();select_child_host();assert(registered && !boot_failed);
 reset();session_ec=0;select_child_host();assert(!registered && !boot_failed);
 reset();guest_machine=IMAGE_FILE_MACHINE_AMD64;select_child_host();assert(!registered && !boot_failed);
 reset();guest_machine=IMAGE_FILE_MACHINE_ARM64;select_child_host();assert(!registered && !boot_failed);
 reset();map_status=99;select_child_host();assert(!registered && boot_failed);
 reset();assert(!ios_load_child_native_ntdll((PEB*)0x123));
 assert(registered && synced==5 && !strcmp(mapped_path,"/runtime/aarch64-windows/ntdll.dll"));
 assert(owner.LdrInitializeThunk==(void*)(native.b+0x100));assert(owner.LdrSystemDllInitBlock==(void*)(native.b+0x400));
 assert(!owner.KiUserEmulationDispatcher);
 assert(*(void**)(native.b+0x180)==__wine_syscall_dispatcher);
 assert(*(void**)(native.b+0x190)==__wine_unix_call_dispatcher);
 assert(*(uintptr_t*)(native.b+0x1a0)==(uintptr_t)unix_call_funcs);
 assert(*(unsigned*)(native.b+0x1b0)==0x60);
 assert(*(void**)(native.b+0x1c0)==ios_jit_reverse_translate_addr);
 SYSTEM_DLL_INIT_BLOCK parent_saved=parent_block;
 load_ntdll_wow64_functions(guest.b);
 SYSTEM_DLL_INIT_BLOCK *child=(void*)(native.b+0x400),*g=(void*)(guest.b+0x400);
#ifdef OLD
 assert(!child->ntdll_handle && !child->pRtlUserThreadStart && child->version==0xf0);
 assert(memcmp(&parent_block,&parent_saved,sizeof(parent_block)));
 puts("PASS negative control: original function mutates parent init block and leaves native child empty");
#else
 assert(!memcmp(&parent_block,&parent_saved,sizeof(parent_block)));
 assert(child->version==0xf0);
 assert(child->ntdll_handle==0x100000 && child->pLdrInitializeThunk==0x100100 && child->pRtlUserThreadStart==0x100120);
 assert(!child->pRtlpFreezeTimeBias && !child->pRtlpQueryProcessDebugInformationRemote);
 assert(!memcmp(child,g,sizeof(*child)) && synced==6);
 puts("PASS draft: private child init block and guest copy use guest VAs; parent unchanged");
#endif
 reset();missing="p_ios_jit_reverse_translate_addr";assert(ios_load_child_native_ntdll((PEB*)0x123)==-1 && !registered);
 reset();map_status=99;assert(ios_load_child_native_ntdll((PEB*)0x123)==-1 && !registered);
 reset();map_machine=IMAGE_FILE_MACHINE_AMD64;assert(ios_load_child_native_ntdll((PEB*)0x123)==-1 && !registered);
 reset();build_dir=0;map_status=STATUS_IMAGE_NOT_AT_BASE;assert(!ios_load_child_native_ntdll((PEB*)0x123));assert(!strcmp(mapped_path,"/dll/aarch64-windows/ntdll.dll"));
 teb.WowTebOffset=1;opened=0;assert(!retry_module(STATUS_INVALID_IMAGE_FORMAT,L"C:\\windows\\system32\\ucrtbase.dll"));assert(opened==1 && !wcscmp(retried_path,L"\\??\\C:\\windows\\sysaa64\\ucrtbase.dll"));
 opened=0;assert(!retry_module(STATUS_DLL_NOT_FOUND,L"kernel32"));assert(opened==1 && !wcscmp(retried_path,L"\\??\\C:\\windows\\sysaa64\\kernel32.dll"));
 opened=0;teb.WowTebOffset=0;assert(retry_module(STATUS_INVALID_IMAGE_FORMAT,L"ucrtbase.dll")==STATUS_INVALID_IMAGE_FORMAT && !opened);
 teb.WowTebOffset=1;assert(retry_module(99,L"ucrtbase.dll")==99 && !opened);
 puts("PASS actual native mapper: required exports, dispatcher/JIT slots, relocated image, missing/wrong-machine rejection; native farm retry scoped to WoW64");
 return 0;
}
'''
matrix_results=[]
for architecture,native in [('native',True),('ec',False)]:
    definitions='' if native else '#undef __aarch64__\n'
    predicates=function(before_pe,'static BOOL is_valid_binary(').replace('is_valid_binary(', 'valid_before(',1)+'\n'+function(pe,'static BOOL is_valid_binary(').replace('is_valid_binary(', 'valid_after(',1)
    matrix=r'''int main(void) {
 unsigned machines[]={IMAGE_FILE_MACHINE_ARM64,IMAGE_FILE_MACHINE_AMD64,IMAGE_FILE_MACHINE_ARM64EC,IMAGE_FILE_MACHINE_ARM64X,IMAGE_FILE_MACHINE_I386,IMAGE_FILE_MACHINE_ARMNT,0};
 current_machine=NATIVE?IMAGE_FILE_MACHINE_ARM64:IMAGE_FILE_MACHINE_AMD64;
 for(unsigned m=0;m<ARRAY_SIZE(machines);++m)for(int wow=0;wow<2;++wow)for(int code=0;code<2;++code)for(int com=0;com<2;++com)for(int hybrid=0;hybrid<2;++hybrid)for(int il=0;il<2;++il) {
  SECTION_IMAGE_INFORMATION image={machines[m],code,com};teb.WowTebOffset=wow;hybrid_metadata=hybrid;ilonly=il;
  int rejected=NATIVE && wow && (machines[m]==IMAGE_FILE_MACHINE_AMD64 || machines[m]==IMAGE_FILE_MACHINE_ARM64EC || machines[m]==IMAGE_FILE_MACHINE_ARM64X);
  assert(valid_after(NULL,&image)==(rejected?FALSE:valid_before(NULL,&image)));
 }
 return 0;
}
'''
    path=b/(architecture+'-binary-predicate.c');path.write_text(prelude+'\n'+definitions+predicates+'\n'+matrix)
    command=['/usr/bin/clang','-std=gnu11','-fsanitize=address,undefined','-DNATIVE='+str(int(native)),str(path),'-o',str(path.with_suffix(''))]
    subprocess.run(command,check=True)
    subprocess.run([str(path.with_suffix(''))],check=True)
    matrix_results.append({'architecture':architecture,'combinations':224,'command':command,'sourceSha256':hashlib.sha256(path.read_bytes()).hexdigest()})
print('PASS actual binary predicate matrix: native EC identities rejected; i386/ARMNT/native, COM and EC-compiled behavior preserved')
results=[]
for state,src in [('before',before),('after',after)]:
 valid_source=before_pe if state=='before' else pe
 harness=prelude+'\n'+function(valid_source,'static BOOL is_valid_binary(')+'\n'+pe_dir+'\n'+helper+'\n'+function(src,'static void load_ntdll_wow64_functions(')+'\n'+selection_wrapper+'\n'+retry_wrapper+'\n'+main
 path=b/(state+'-native-loader-contract.c');path.write_text(harness)
 command=['/usr/bin/clang','-std=gnu11','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-Werror=implicit-function-declaration','-Werror=unknown-escape-sequence',str(path),'-o',str(path.with_suffix(''))]
 if state=='before':command+=['-DOLD=1']
 p=subprocess.run(command,text=True,capture_output=True)
 if p.returncode:raise RuntimeError(p.stderr)
 run=subprocess.run([str(path.with_suffix(''))],text=True,capture_output=True)
 print(run.stdout,end='');assert run.returncode==0,run.stderr
 results.append({'state':state,'compileCommand':command,'exit':run.returncode,'stdout':run.stdout,'stderr':run.stderr,'sourceSha256':hashlib.sha256(harness.encode()).hexdigest()})
(b/'contract-receipt.json').write_text(json.dumps({'scope':'actual production mapper and original/patched init-block functions compiled with ASan/UBSan; OS/PE map boundaries mocked; no engine compile or runtime execution','nativeResource':resource_report,'chkstkBoundary':chkstk_report,'binaryPredicateMatrices':matrix_results,'actualInitBlockDefinitionSha256':hashlib.sha256(init_structure.encode()).hexdigest(),'requiredExports':required,'tests':results},indent=2)+'\n')
print('PASS native-child architecture/order contract; artifacts:',b)
