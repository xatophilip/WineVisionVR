/* App-owned i386 startup probe. A marker requires reaching main and ntdll. */
#include <windows.h>
#include <stdio.h>

__declspec(dllimport) DWORD WINAPI RtlRunOnceExecuteOnce(
    PRTL_RUN_ONCE once, PRTL_RUN_ONCE_INIT_FN callback, PVOID parameter, PVOID *context);

static unsigned callbacks;
static DWORD WINAPI initialize(PRTL_RUN_ONCE once, PVOID parameter, PVOID *context)
{
    (void)once;
    ++callbacks;
    *context = parameter;
    return TRUE;
}

int wmain(int argc, wchar_t **argv)
{
    RTL_RUN_ONCE once = RTL_RUN_ONCE_INIT;
    PVOID context = NULL;
    DWORD first, second;
    const wchar_t *marker = argc == 2 ? argv[1] : L"direct-child-result.json";
    HANDLE file;
    DWORD written;
    char result[256];
    int length;
    if (sizeof(void *) != 4 || argc > 2) return 10;
    first = RtlRunOnceExecuteOnce(&once, initialize, (PVOID)(ULONG_PTR)0x100, &context);
    second = RtlRunOnceExecuteOnce(&once, initialize, (PVOID)(ULONG_PTR)0x200, &context);
    if (first || second || callbacks != 1 || context != (PVOID)(ULONG_PTR)0x100) return 11;
    length = snprintf(result, sizeof(result),
        "{\"fixture\":\"mixed-architecture-child-v1\",\"pointerBits\":32,"
        "\"callbacks\":1,\"firstStatus\":0,\"secondStatus\":0,\"exitCode\":0}\n");
    if (length <= 0 || length >= (int)sizeof(result)) return 12;
    file = CreateFileW(marker, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 13;
    if (!WriteFile(file, result, (DWORD)length, &written, NULL) || written != (DWORD)length) {
        CloseHandle(file); return 14;
    }
    if (!FlushFileBuffers(file)) { CloseHandle(file); return 15; }
    CloseHandle(file);
    return 0;
}
