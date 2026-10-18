/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 WineVision VR contributors */
#include "atomic_protocol.h"
_Static_assert(sizeof(void*)==8,"Build this parent as x86_64");
static int field(const char *json,const char *key,unsigned long value) {
    char expected[96];snprintf(expected,sizeof(expected),"\"%s\":%lu",key,value);
    const char *match=strstr(json,expected);
    if(!match)return 0;
    char next=match[strlen(expected)];return next==','||next=='}';
}
int wmain(int argc,WCHAR **argv) {
    char name[48],token[65],path[180],json[1600],expected[180];
    if(argc!=4 || wcslen(argv[1])>30000 || wcschr(argv[1],L'"') ||
       !atomic_ascii(argv[2],name,sizeof(name)) || !atomic_ascii(argv[3],token,sizeof(token)))return 2;
    const struct atomic_case *c=atomic_parse_case(name);if(!c)return 2;
    const char *stages[]={"prepared","before","after"};
    for(unsigned i=0;i<3;i++) {
        if(!atomic_marker_name(path,sizeof(path),token,name,stages[i]))return 3;
        if(GetFileAttributesA(path)!=INVALID_FILE_ATTRIBUTES)return 4; /* Refuse stale token; never overwrite. */
    }
    WCHAR command[32768];
    if(swprintf(command,sizeof(command)/sizeof(command[0]),L"\"%ls\" \"%ls\" \"%ls\"",argv[1],argv[2],argv[3])<0)return 3;
    STARTUPINFOW startup={0};startup.cb=sizeof(startup);
    PROCESS_INFORMATION process={0};
    if(!CreateProcessW(NULL,command,NULL,NULL,FALSE,0,NULL,NULL,&startup,&process)) {
        printf("CREATE_ERROR=%lu\n",GetLastError());return 5;
    }
    BOOL wow=FALSE;int architecture=IsWow64Process(process.hProcess,&wow)&&wow;
    printf("PARENT pointerBits=64 CHILD_PID=%lu CHILD_WOW64=%d\n",process.dwProcessId,architecture);fflush(stdout);
    DWORD wait=WaitForSingleObject(process.hProcess,20000);
    if(wait!=WAIT_OBJECT_0) {
        /* Only this parent's owned child; no global wineserver/process kill. */
        TerminateProcess(process.hProcess,124);WaitForSingleObject(process.hProcess,5000);
    }
    DWORD exit=STILL_ACTIVE;int gotExit=GetExitCodeProcess(process.hProcess,&exit);
    printf("CHILD_WAIT=%lu CHILD_EXIT=%lu\n",wait,exit);fflush(stdout);
    DWORD pid=process.dwProcessId;
    CloseHandle(process.hThread);CloseHandle(process.hProcess);
    if(wait!=WAIT_OBJECT_0 || !gotExit || exit!=0 || !architecture)return 6;
    for(unsigned i=0;i<3;i++) {
        atomic_marker_name(path,sizeof(path),token,name,stages[i]);
        if(!atomic_read(path,json,sizeof(json)))return 7;
        snprintf(expected,sizeof(expected),"\"case\":\"%s\",\"token\":\"%s\"",name,token);
        if(!strstr(json,"\"fixture\":\"owned-atomic-v1\"") || !strstr(json,expected) ||
           !field(json,"pointerBits",32) || !field(json,"childPID",pid) ||
           !field(json,"protect",c->protect) || !field(json,"offset",c->offset) ||
           !field(json,"executeStub",(unsigned)c->execute))return 8;
        if(i==1 && (!strstr(json,"\"stage\":\"beforeExchange\"") ||
                    !field(json,"initial",ATOMIC_INITIAL)||!field(json,"desired",ATOMIC_DESIRED)))return 8;
        if(i==2 && (!strstr(json,"\"stage\":\"afterExchange\"") ||
                    !field(json,"returnedOld",ATOMIC_INITIAL)||!field(json,"observedNew",ATOMIC_DESIRED)||
                    !field(json,"canary",1)||!field(json,"exitCode",0)||
                    !field(json,"stubResult",c->execute?ATOMIC_STUB_RESULT:0)))return 8;
    }
    printf("PASS mixed atomic case=%s token=%s freshMarkers=3 childExit=0\n",name,token);fflush(stdout);
    return 0;
}
