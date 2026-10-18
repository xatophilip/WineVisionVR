/* App-owned x64 launcher: exercise the same architecture transition as Steam. */
#include <windows.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>

int wmain(void)
{
    wchar_t child[32768], folder[32768], command[32768], marker[32768];
    const wchar_t *name = L"child32.exe", *marker_name = L"mixed-child-result.json";
    wchar_t *slash;
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    DWORD size, code, wait, got;
    HANDLE file;
    char contents[256] = {0};
    if (sizeof(void *) != 8) return 20;
    size = GetModuleFileNameW(NULL, folder, 32768);
    if (!size || size >= 32768) return 21;
    slash = wcsrchr(folder, L'\\');
    if (!slash) return 22;
    slash[1] = 0;
    if (wcslen(folder) + wcslen(marker_name) + 1 >= 32768) return 23;
    wcscpy(child, folder); wcscat(child, name);
    wcscpy(marker, folder); wcscat(marker, marker_name);
    if (_snwprintf(command, 32768, L"\"%ls\" \"%ls\"", child, marker) < 0) return 24;
    /* A stale marker must never turn an unstarted/crashed child into a pass. */
    if (!DeleteFileW(marker) && GetLastError() != ERROR_FILE_NOT_FOUND) return 25;
    startup.cb = sizeof(startup);
    if (!CreateProcessW(child, command, NULL, NULL, FALSE, 0, NULL, folder, &startup, &process)) return 26;
    CloseHandle(process.hThread);
    wait = WaitForSingleObject(process.hProcess, 30000);
    if (wait != WAIT_OBJECT_0) {
        TerminateProcess(process.hProcess, 27);
        CloseHandle(process.hProcess); return 27;
    }
    if (!GetExitCodeProcess(process.hProcess, &code)) { CloseHandle(process.hProcess); return 28; }
    CloseHandle(process.hProcess);
    if (code != 0) return 29;
    file = CreateFileW(marker, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 30;
    if (!ReadFile(file, contents, sizeof(contents)-1, &got, NULL)) { CloseHandle(file); return 31; }
    CloseHandle(file);
    if (!got || !strstr(contents, "\"fixture\":\"mixed-architecture-child-v1\"") ||
        !strstr(contents, "\"pointerBits\":32") || !strstr(contents, "\"callbacks\":1") ||
        !strstr(contents, "\"exitCode\":0")) return 32;
    puts("PASS: x64 parent -> i386 child, RtlRunOnce callback once, marker verified, child exit 0");
    return 0;
}
