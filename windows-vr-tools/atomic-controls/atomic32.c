/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 WineVision VR contributors
 *
 * One owned case per process. This intentionally exercises x86's unaligned
 * LOCK XCHG instruction through Wine's real exported implementation. It is
 * not a claim that Win32 documents unaligned Interlocked API use generally. */
#include "atomic_protocol.h"
typedef LONG (WINAPI *exchange_fn)(LONG volatile *,LONG);
typedef DWORD (__cdecl *stub_fn)(void);
_Static_assert(sizeof(void*)==4,"Build this fixture as i386");
int wmain(int argc,WCHAR **argv) {
    char name[48],token[65],prepared[180],before[180],after[180],json[1400];
    if(argc!=3 || !atomic_ascii(argv[1],name,sizeof(name)) ||
       !atomic_ascii(argv[2],token,sizeof(token)))return 2;
    const struct atomic_case *c=atomic_parse_case(name);
    if(!c)return 2;
    if(!atomic_marker_name(prepared,sizeof(prepared),token,name,"prepared") ||
       !atomic_marker_name(before,sizeof(before),token,name,"before") ||
       !atomic_marker_name(after,sizeof(after),token,name,"after"))return 3;
    if(GetFileAttributesA(prepared)!=INVALID_FILE_ATTRIBUTES ||
       GetFileAttributesA(before)!=INVALID_FILE_ATTRIBUTES ||
       GetFileAttributesA(after)!=INVALID_FILE_ATTRIBUTES)return 4;
    HMODULE kernel=GetModuleHandleW(L"kernel32.dll");
    exchange_fn exchange=(exchange_fn)(ULONG_PTR)GetProcAddress(kernel,"InterlockedExchange");
    if(!exchange)return 5;
    BYTE *base=VirtualAlloc(NULL,0x100000,MEM_RESERVE|MEM_COMMIT,c->protect);
    if(!base)return 6;
    BYTE expected[64];memset(expected,0xa5,sizeof(expected));
    DWORD initial=ATOMIC_INITIAL,desired=ATOMIC_DESIRED;
    memcpy(expected+16,&initial,sizeof(initial));
    BYTE *neighborhood=base+c->offset-16;
    memcpy(neighborhood,expected,sizeof(expected));
    static const BYTE code[]={0xb8,0x78,0x56,0x34,0x12,0xc3};
    if(c->execute)memcpy(base+0x100,code,sizeof(code));
    DWORD pid=GetCurrentProcessId(),stub=0;
    snprintf(json,sizeof(json),"{\"fixture\":\"owned-atomic-v1\",\"case\":\"%s\",\"token\":\"%s\",\"pointerBits\":32,\"childPID\":%lu,\"stage\":\"prepared\",\"protect\":%lu,\"offset\":%lu,\"executeStub\":%d,\"apiResolved\":1}\n",
             name,token,pid,c->protect,c->offset,c->execute);
    if(!atomic_write_new(prepared,json)){VirtualFree(base,0,MEM_RELEASE);return 7;}
    if(c->execute) {
        if(!FlushInstructionCache(GetCurrentProcess(),base+0x100,sizeof(code))){VirtualFree(base,0,MEM_RELEASE);return 8;}
        stub=((stub_fn)(ULONG_PTR)(base+0x100))();
        if(stub!=ATOMIC_STUB_RESULT){VirtualFree(base,0,MEM_RELEASE);return 9;}
    }
    snprintf(json,sizeof(json),"{\"fixture\":\"owned-atomic-v1\",\"case\":\"%s\",\"token\":\"%s\",\"pointerBits\":32,\"childPID\":%lu,\"stage\":\"beforeExchange\",\"protect\":%lu,\"offset\":%lu,\"executeStub\":%d,\"stubResult\":%lu,\"initial\":%lu,\"desired\":%lu,\"apiResolved\":1}\n",
             name,token,pid,c->protect,c->offset,c->execute,stub,initial,desired);
    if(!atomic_write_new(before,json)){VirtualFree(base,0,MEM_RELEASE);return 10;}
    /* GetProcAddress forces the exported kernel32 LOCK XCHG, not a compiler intrinsic. */
    LONG old=exchange((LONG volatile *)(base+c->offset),(LONG)desired);
    DWORD observed=0;memcpy(&observed,base+c->offset,sizeof(observed));
    memcpy(expected+16,&desired,sizeof(desired));
    int canary=memcmp(neighborhood,expected,sizeof(expected))==0;
    int passed=(DWORD)old==initial && observed==desired && canary;
    snprintf(json,sizeof(json),"{\"fixture\":\"owned-atomic-v1\",\"case\":\"%s\",\"token\":\"%s\",\"pointerBits\":32,\"childPID\":%lu,\"stage\":\"afterExchange\",\"protect\":%lu,\"offset\":%lu,\"executeStub\":%d,\"stubResult\":%lu,\"returnedOld\":%lu,\"observedNew\":%lu,\"canary\":%d,\"exitCode\":%d}\n",
             name,token,pid,c->protect,c->offset,c->execute,stub,(DWORD)old,observed,canary,passed?0:1);
    if(!atomic_write_new(after,json)){VirtualFree(base,0,MEM_RELEASE);return 11;}
    printf("%s atomic case=%s token=%s pointerBits=32 old=%lu new=%lu canary=%d\n",
           passed?"PASS":"FAIL",name,token,(DWORD)old,observed,canary);fflush(stdout);
    VirtualFree(base,0,MEM_RELEASE);
    return passed?0:1;
}
