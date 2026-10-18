/* App-owned x64 launcher: exercise the same architecture transition as Steam. */
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>

static BOOL read_marker(const wchar_t *path, char *contents, DWORD capacity)
{
    DWORD got;
    HANDLE file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return FALSE;
    if (!ReadFile(file, contents, capacity-1, &got, NULL)) { CloseHandle(file); return FALSE; }
    CloseHandle(file);
    contents[got] = 0;
    return got > 0 && got < capacity-1 && contents[got-1] == '\n';
}

int wmain(void)
{
    wchar_t child[32768], folder[32768], command[32768], marker[32768], before[32768];
    const wchar_t *name = L"child32.exe", *marker_name = L"mixed-child-result.json";
    wchar_t *slash;
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    DWORD size, code, wait;
    char contents[512], stage[512], *flags, *end;
    unsigned long context_flags;
    if (sizeof(void *) != 8) return 20;
    size = GetModuleFileNameW(NULL, folder, 32768);
    if (!size || size >= 32768) return 21;
    slash = wcsrchr(folder, L'\\');
    if (!slash) return 22;
    slash[1] = 0;
    if (wcslen(folder) + wcslen(marker_name) + wcslen(L".before-seh.json") + 1 >= 32768) return 23;
    wcscpy(child, folder); wcscat(child, name);
    wcscpy(marker, folder); wcscat(marker, marker_name);
    wcscpy(before, marker); wcscat(before, L".before-seh.json");
    if (_snwprintf(command, 32768, L"\"%ls\" \"%ls\"", child, marker) < 0) return 24;
    /* Neither stale marker may hide loader/context failure. */
    if (!DeleteFileW(marker) && GetLastError() != ERROR_FILE_NOT_FOUND) return 25;
    if (!DeleteFileW(before) && GetLastError() != ERROR_FILE_NOT_FOUND) return 25;
    startup.cb = sizeof(startup);
    if (!CreateProcessW(child, command, NULL, NULL, FALSE, 0, NULL, folder, &startup, &process)) return 26;
    CloseHandle(process.hThread);
    wait = WaitForSingleObject(process.hProcess, 30000);
    if (wait != WAIT_OBJECT_0) {
        TerminateProcess(process.hProcess, 27);
        WaitForSingleObject(process.hProcess, 3000);
        CloseHandle(process.hProcess); return 27;
    }
    if (!GetExitCodeProcess(process.hProcess, &code)) { CloseHandle(process.hProcess); return 28; }
    CloseHandle(process.hProcess);
    printf("CHILD_EXIT code=%lu beforeStage=%u\n", (unsigned long)code,
        GetFileAttributesW(before) != INVALID_FILE_ATTRIBUTES);
    if (code != 0) return 29;
    if (!read_marker(before, stage, sizeof(stage)) ||
        !strstr(stage, "\"stage\":\"beforeRaiseException\"") ||
        !strstr(stage, "\"pointerBits\":32,") || !strstr(stage, "\"callbacks\":1,")) return 30;
    if (!read_marker(marker, contents, sizeof(contents))) return 31;
    if (!strstr(contents, "\"fixture\":\"mixed-architecture-child-v1\"") ||
        !strstr(contents, "\"pointerBits\":32,") || !strstr(contents, "\"callbacks\":1,") ||
        !strstr(contents, "\"firstStatus\":0,") || !strstr(contents, "\"secondStatus\":0,") ||
        !strstr(contents, "\"vehCalls\":1,") || !strstr(contents, "\"contextI386\":1,") ||
        !strstr(contents, "\"contextStackValid\":1,") || !strstr(contents, "\"exceptionValid\":1,") ||
        !strstr(contents, "\"continuedAfterRaise\":1,") || !strstr(contents, "\"exitCode\":0}")) return 32;
    flags = strstr(contents, "\"contextFlags\":");
    if (!flags) return 33;
    context_flags = strtoul(flags + strlen("\"contextFlags\":"), &end, 10);
    if (*end != ',' || (context_flags & 0x00ff0000) != 0x00010000 || (context_flags & 3) != 3) return 33;
    puts("PASS: x64 parent -> i386 child, RtlRunOnce callback once, VEH once, i386 context/stack, resumed after RaiseException, fresh markers, child exit 0");
    return 0;
}
