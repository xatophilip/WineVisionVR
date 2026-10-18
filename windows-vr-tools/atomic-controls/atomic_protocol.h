/* SPDX-License-Identifier: GPL-3.0-or-later
 * Copyright 2026 WineVision VR contributors */
#ifndef OWNED_ATOMIC_PROTOCOL_H
#define OWNED_ATOMIC_PROTOCOL_H
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#define ATOMIC_INITIAL 0x11223344u
#define ATOMIC_DESIRED 0x55667788u
#define ATOMIC_STUB_RESULT 0x12345678u
struct atomic_case { const char *name; DWORD protect, offset; int execute; };
static const struct atomic_case atomic_cases[] = {
    {"rw-aligned",PAGE_READWRITE,0x208,0},
    {"rw-unaligned",PAGE_READWRITE,0x207,0},
    {"rwx-aligned",PAGE_EXECUTE_READWRITE,0x208,0},
    {"rwx-unaligned",PAGE_EXECUTE_READWRITE,0x207,0},
    {"rwx-unaligned-execute",PAGE_EXECUTE_READWRITE,0x207,1}
};
static inline const struct atomic_case *atomic_parse_case(const char *name) {
    for(unsigned i=0;i<sizeof(atomic_cases)/sizeof(atomic_cases[0]);i++)
        if(!strcmp(name,atomic_cases[i].name)) return &atomic_cases[i];
    return NULL;
}
static inline int atomic_ascii(const WCHAR *wide,char *out,size_t capacity) {
    size_t n=wcslen(wide);
    if(!n || n>=capacity)return 0;
    for(size_t i=0;i<n;i++) {
        WCHAR c=wide[i];
        if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='-'||c=='_'))return 0;
        out[i]=(char)c;
    }
    out[n]=0;return 1;
}
static inline int atomic_marker_name(char *out,size_t size,const char *token,const char *name,const char *stage) {
    int n=snprintf(out,size,"atomic-%s-%s.%s.json",token,name,stage);
    return n>0 && (size_t)n<size;
}
static inline int atomic_write_new(const char *path,const char *json) {
    HANDLE file=CreateFileA(path,GENERIC_WRITE,0,NULL,CREATE_NEW,FILE_ATTRIBUTE_NORMAL|FILE_FLAG_WRITE_THROUGH,NULL);
    if(file==INVALID_HANDLE_VALUE)return 0;
    DWORD n=0,length=(DWORD)strlen(json);
    int good=WriteFile(file,json,length,&n,NULL)&&n==length&&FlushFileBuffers(file);
    CloseHandle(file);return good;
}
static inline int atomic_read(const char *path,char *out,DWORD capacity) {
    HANDLE file=CreateFileA(path,GENERIC_READ,FILE_SHARE_READ,NULL,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,NULL);
    if(file==INVALID_HANDLE_VALUE)return 0;
    DWORD size=GetFileSize(file,NULL),n=0;
    int good=size>0 && size<capacity && ReadFile(file,out,size,&n,NULL)&&n==size;
    CloseHandle(file);if(good)out[n]=0;return good;
}
#endif
