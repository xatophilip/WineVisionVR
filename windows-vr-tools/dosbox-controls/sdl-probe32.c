/* Owned diagnostic using the genuine user-supplied SDL 1 DLL. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
typedef unsigned (__cdecl *ticks_fn)(void);
typedef unsigned (__cdecl *callback_fn)(unsigned,void *);
typedef void *(__cdecl *add_fn)(unsigned,callback_fn,void *);
typedef int (__cdecl *remove_fn)(void *);
static ticks_fn ticks;
static LONG calls,failures;
static void mark(const char *stage,int value) {
 FILE *file=fopen("sdl-milestones.txt","a");
 if(file){fprintf(file,"%s value=%d pointerBits=%u pid=%lu tid=%lu\n",stage,value,(unsigned)(sizeof(void*)*8),GetCurrentProcessId(),GetCurrentThreadId());fclose(file);}
}
static DWORD WINAPI worker(void *unused) {
 (void)unused;mark("worker-before",0);LARGE_INTEGER q;
 for(unsigned i=0;i<10000;i++){ticks();if(!QueryPerformanceCounter(&q))InterlockedIncrement(&failures);}
 mark("worker-after",10000);return 0;
}
static unsigned __cdecl timer(unsigned interval,void *unused) {
 (void)unused;LARGE_INTEGER q;ticks();if(!QueryPerformanceCounter(&q))InterlockedIncrement(&failures);
 InterlockedIncrement(&calls);return interval;
}
int wmain(int argc,WCHAR **argv) {
 if(argc!=3)return 2;
 unsigned flags=wcstoul(argv[1],NULL,0);mark("load-before",flags);
 HMODULE dll=LoadLibraryW(argv[2]);if(!dll){mark("load-error",GetLastError());return 3;}
 int (__cdecl *init)(unsigned)=(void*)GetProcAddress(dll,"SDL_Init");
 void (__cdecl *quit)(void)=(void*)GetProcAddress(dll,"SDL_Quit");
 const char *(__cdecl *error)(void)=(void*)GetProcAddress(dll,"SDL_GetError");
 void *(__cdecl *video)(int,int,int,unsigned)=(void*)GetProcAddress(dll,"SDL_SetVideoMode");
 void (__cdecl *pump)(void)=(void*)GetProcAddress(dll,"SDL_PumpEvents");
 ticks=(void*)GetProcAddress(dll,"SDL_GetTicks");add_fn add=(void*)GetProcAddress(dll,"SDL_AddTimer");remove_fn remove=(void*)GetProcAddress(dll,"SDL_RemoveTimer");
 if(!init||!quit||!error||!ticks||!add||!remove||!video||!pump)return 4;
 mark("init-before",flags);int status=init(flags);mark("init-after",status);
 if(status){printf("SDL_INIT_ERROR %s\n",error());quit();return 20;}
 if(flags&0x20){mark("video-before",0);void *surface=video(320,200,0,0);mark("video-after",surface!=NULL);if(!surface){quit();return 21;}}
 LARGE_INTEGER q;mark("main-before",0);for(unsigned i=0;i<10000;i++){ticks();if(!QueryPerformanceCounter(&q))failures++;}
 mark("main-after",10000);
 HANDLE thread=CreateThread(NULL,0,worker,NULL,0,NULL);if(!thread){quit();return 22;}
 if(WaitForSingleObject(thread,10000)!=WAIT_OBJECT_0){quit();return 23;}CloseHandle(thread);
 mark("timer-before",0);void *id=add(10,timer,NULL);if(!id){quit();return 24;}
 for(unsigned i=0;i<500 && InterlockedCompareExchange(&calls,0,0)<100;i++){if(flags&0x20)pump();Sleep(10);}
 int removed=remove(id);mark("timer-after",InterlockedCompareExchange(&calls,0,0));mark("timer-remove",removed);
 int passed=InterlockedCompareExchange(&calls,0,0)>=100 && InterlockedCompareExchange(&failures,0,0)==0 && removed;
 quit();FreeLibrary(dll);mark("final",passed);return passed?0:25;
}
