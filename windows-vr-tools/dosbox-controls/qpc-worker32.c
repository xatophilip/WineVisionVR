#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
static int check(const char *name) {
 char path[100];sprintf(path,"qpc-%s-before.txt",name);
 FILE *f=fopen(path,"w");if(!f)return 10;fprintf(f,"before QPC pointerBits=%u pid=%lu tid=%lu\n",(unsigned)(sizeof(void*)*8),GetCurrentProcessId(),GetCurrentThreadId());fclose(f);
 LARGE_INTEGER value;
 for(unsigned i=0;i<100000;i++)if(!QueryPerformanceCounter(&value))return 11;
 sprintf(path,"qpc-%s-after.txt",name);f=fopen(path,"w");if(!f)return 12;fprintf(f,"PASS QPC calls=100000 pointerBits=%u\n",(unsigned)(sizeof(void*)*8));fclose(f);return 0;
}
static DWORD WINAPI worker(void *unused){(void)unused;return check("worker");}
int main(void) {
 HANDLE thread=CreateThread(NULL,0,worker,NULL,0,NULL);if(!thread)return 13;
 int mainResult=check("main");DWORD wait=WaitForSingleObject(thread,30000),code=99;
 if(wait!=WAIT_OBJECT_0)return 14;GetExitCodeThread(thread,&code);CloseHandle(thread);
 printf("QPC RESULT main=%d worker=%lu pointerBits=%u\n",mainResult,code,(unsigned)(sizeof(void*)*8));return mainResult?mainResult:(int)code;
}
