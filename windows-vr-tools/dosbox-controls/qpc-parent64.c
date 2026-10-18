#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
int wmain(int argc,WCHAR **argv) {
 if(argc!=2)return 2;
 WCHAR command[1000];if(wcslen(argv[1])>980)return 3;swprintf(command,1000,L"\"%ls\"",argv[1]);
 STARTUPINFOW s={.cb=sizeof(s)};PROCESS_INFORMATION p={0};
 if(!CreateProcessW(NULL,command,NULL,NULL,FALSE,0,NULL,NULL,&s,&p)){printf("CREATE ERROR %lu\n",GetLastError());return 4;}
 printf("PARENT bits=64 CHILD_PID=%lu\n",p.dwProcessId);fflush(stdout);
 DWORD wait=WaitForSingleObject(p.hProcess,45000);if(wait!=WAIT_OBJECT_0){TerminateProcess(p.hProcess,124);WaitForSingleObject(p.hProcess,5000);}
 DWORD code=99;GetExitCodeProcess(p.hProcess,&code);printf("CHILD_EXIT=%lu\n",code);CloseHandle(p.hThread);CloseHandle(p.hProcess);return code==0?0:5;
}
