// SPDX-License-Identifier: GPL-3.0-or-later
// Copyright 2026 WineVision VR contributors

/* Owned local integration boundary: launch actual x86 DOSBox from Win64,
 * send only generated VK transitions to that exact child's SDL window, and
 * request DOSBox's own screenshots. No global SendInput or screen capture. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include <io.h>
static DWORD child_pid;
static HWND target;
static BOOL CALLBACK find_window(HWND w, LPARAM unused) {
    DWORD pid; WCHAR cls[256]; (void)unused;
    GetWindowThreadProcessId(w,&pid); GetClassNameW(w,cls,256);
    if(pid==child_pid && IsWindowVisible(w) && !wcscmp(cls,L"SDL_app")) target=w;
    return TRUE;
}
static int post_key(unsigned vk,unsigned down) {
    EnumWindows(find_window,0);
    DWORD pid=0; GetWindowThreadProcessId(target,&pid);
    if(!target || pid!=child_pid || !IsWindow(target)) return 0;
    LPARAM flags=1|((LPARAM)MapVirtualKeyW(vk,MAPVK_VK_TO_VSC)<<16);
    if(vk>=VK_LEFT && vk<=VK_DOWN) flags|=(LPARAM)1<<24;
    if(!down) flags|=(LPARAM)3<<30;
    return PostMessageW(target,down?WM_KEYDOWN:WM_KEYUP,vk,flags);
}

static unsigned nonblack(const BYTE *bits,DWORD bytes) {
    unsigned count=0;for(DWORD i=0;i<bytes;i+=4)if(bits[i]||bits[i+1]||bits[i+2])count++;return count;
}
static int capture_client(const char *label,FILE *events) {
    for(const char *c=label;*c;c++)if(!((*c>='a'&&*c<='z')||(*c>='0'&&*c<='9')||*c=='-'))return 0;
    EnumWindows(find_window,0);DWORD pid=0;GetWindowThreadProcessId(target,&pid);RECT rect={0};
    if(!target||pid!=child_pid||!GetClientRect(target,&rect))return 0;
    int width=rect.right-rect.left,height=rect.bottom-rect.top;
    if(width<=0||height<=0||width>4096||height>4096)return 0;
    DWORD bytes=(DWORD)width*(DWORD)height*4;
    BYTE *bits=calloc(bytes,1);HDC source=GetDC(target),memory=source?CreateCompatibleDC(source):NULL;
    HBITMAP bitmap=source?CreateCompatibleBitmap(source,width,height):NULL;
    int success=0;BOOL copied=FALSE,printed=FALSE;unsigned visible=0;int scans=0;
    if(bits&&source&&memory&&bitmap) {
        BITMAPINFO info={0};info.bmiHeader.biSize=sizeof(BITMAPINFOHEADER);info.bmiHeader.biWidth=width;info.bmiHeader.biHeight=-height;info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;info.bmiHeader.biSizeImage=bytes;
        HGDIOBJ old=SelectObject(memory,bitmap);
        copied=BitBlt(memory,0,0,width,height,source,0,0,SRCCOPY);GdiFlush();
        SelectObject(memory,old);scans=GetDIBits(memory,bitmap,0,height,bits,&info,DIB_RGB_COLORS);visible=nonblack(bits,bytes);
        if(!copied||!visible) {
            SelectObject(memory,bitmap);printed=PrintWindow(target,memory,PW_CLIENTONLY);GdiFlush();SelectObject(memory,old);
            memset(bits,0,bytes);scans=GetDIBits(memory,bitmap,0,height,bits,&info,DIB_RGB_COLORS);visible=nonblack(bits,bytes);
        }
        GetWindowThreadProcessId(target,&pid);
        if(pid==child_pid && IsWindow(target) && scans==height) {
            if(!CreateDirectoryA("gdi-captures",NULL)&&GetLastError()!=ERROR_ALREADY_EXISTS)goto done;
            DWORD attr=GetFileAttributesA("gdi-captures");if(attr==INVALID_FILE_ATTRIBUTES||!(attr&FILE_ATTRIBUTE_DIRECTORY)||(attr&FILE_ATTRIBUTE_REPARSE_POINT))goto done;
            char path[180];snprintf(path,sizeof(path),"gdi-captures/%s.bmp",label);
            HANDLE file=CreateFileA(path,GENERIC_WRITE,FILE_SHARE_READ,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,NULL);
            if(file!=INVALID_HANDLE_VALUE) {
                BITMAPFILEHEADER header={0};header.bfType=0x4d42;header.bfOffBits=sizeof(header)+sizeof(BITMAPINFOHEADER);header.bfSize=header.bfOffBits+bytes;
                DWORD wrote;success=WriteFile(file,&header,sizeof(header),&wrote,NULL)&&wrote==sizeof(header)&&WriteFile(file,&info.bmiHeader,sizeof(BITMAPINFOHEADER),&wrote,NULL)&&wrote==sizeof(BITMAPINFOHEADER)&&WriteFile(file,bits,bytes,&wrote,NULL)&&wrote==bytes;
                CloseHandle(file);
            }
        }
    }
done:
    fprintf(events,"GDI_FRAME label=%s hwnd=%p pid=%lu size=%dx%d bitblt=%d printwindow=%d scanlines=%d nonblack=%u saved=%d\n",label,target,pid,width,height,copied,printed,scans,visible,success);fflush(events);
    if(bitmap)DeleteObject(bitmap);if(memory)DeleteDC(memory);if(source)ReleaseDC(target,source);free(bits);
    return success&&visible>0;
}
int wmain(int argc,WCHAR **argv) {
    if(argc!=4&&argc!=5) return 2;
    BOOL gdi=argc==5&&!wcscmp(argv[4],L"gdi");
    FILE *f=_wfopen(argv[1],L"rb"); if(!f) return 3;
    fseek(f,0,SEEK_END);long size=ftell(f);rewind(f);
    if(size<=0 || size>60000 || size%2){fclose(f);return 4;}
    WCHAR *command=calloc(size+2,1);if(!command){fclose(f);return 4;}
    if(fread(command,1,size,f)!=(size_t)size){fclose(f);free(command);return 4;}fclose(f);
    f=NULL;
    STARTUPINFOW s={.cb=sizeof(s)};PROCESS_INFORMATION p={0};
    printf("PARENT_POINTER_BITS %u\n",(unsigned)(sizeof(void*)*8));
    wprintf(L"COMMAND %ls\nCWD %ls\n",command,argv[2]);fflush(stdout);
    if(!CreateProcessW(NULL,command,NULL,NULL,FALSE,0,NULL,argv[2],&s,&p)){
        printf("HARNESS_CREATEPROCESS_ERROR %lu\n",GetLastError());free(command);return 6;}
    free(command);BOOL wow64=FALSE;
    if(!IsWow64Process(p.hProcess,&wow64)||!wow64){TerminateProcess(p.hProcess,124);CloseHandle(p.hThread);CloseHandle(p.hProcess);return 13;}
    child_pid=p.dwProcessId;
    FILE *events=_wfopen(L"owned-driver-events.txt",L"w");
    f=_wfopen(argv[3],L"r");
    if(!events || !f){TerminateProcess(p.hProcess,124);CloseHandle(p.hThread);CloseHandle(p.hProcess);return 15;}
    fprintf(events,"PARENT_POINTER_BITS 64\nCHILD_WOW64 1\nOWN_CHILD_PID %lu\n",child_pid);fflush(events);
    ULONGLONG start=GetTickCount64();char line[256];int status=0;unsigned held[256]={0};
    while(fgets(line,sizeof(line),f)){
        if(GetTickCount64()-start>240000){status=7;break;}
        if(WaitForSingleObject(p.hProcess,0)!=WAIT_TIMEOUT){status=8;break;}
        unsigned a,b;char label[128];
        if(sscanf(line,"WAIT %u",&a)==1 && a<=30000) Sleep(a);
        else if(sscanf(line,"KEY %u %u",&a,&b)==2 && a<256 && b<=1){
            if(held[a]==b || !post_key(a,b)){status=9;break;}held[a]=b;
            fprintf(events,"MAPPED_KEY t=%llu vk=%u down=%u hwnd=%p pid=%lu\n",GetTickCount64()-start,a,b,target,child_pid);
        } else if(sscanf(line,"CAPTURE %127s",label)==1){
            if(gdi){if(!capture_client(label,events)){status=16;break;}continue;}
            EnumWindows(find_window,0);
            fprintf(events,"NATIVE_CAPTURE t=%llu label=%s hwnd=%p pid=%lu\n",GetTickCount64()-start,label,target,child_pid);fflush(events);
            if(!post_key(VK_CONTROL,1)){status=10;break;}Sleep(50);
            if(!post_key(VK_F5,1)){status=10;break;}Sleep(100);
            if(!post_key(VK_F5,0)||!post_key(VK_CONTROL,0)){status=10;break;}Sleep(200);
        } else {status=11;break;}
        fflush(events);
    }
    fclose(f);unsigned unreleased=0;
    for(unsigned i=0;i<256;i++)if(held[i]){post_key(i,0);unreleased++;}
    fprintf(events,"HELD_AT_PLAN_END %u\nHARNESS_STATUS %d\n",unreleased,status);fflush(events);
    /* Interactive game termination is owned cleanup, never a gameplay PASS. */
    if(WaitForSingleObject(p.hProcess,0)==WAIT_TIMEOUT){TerminateProcess(p.hProcess,124);WaitForSingleObject(p.hProcess,5000);}
    DWORD code=999;GetExitCodeProcess(p.hProcess,&code);fprintf(events,"OWN_CHILD_CLEANUP_EXIT %lu\n",code);
    fclose(events);CloseHandle(p.hThread);CloseHandle(p.hProcess);
    return status || unreleased ? 12 : 0;
}
