/* App-owned i386 startup and continuable exception/context probe. */
#include <windows.h>
#include <stdio.h>
#include <wchar.h>

__declspec(dllimport) DWORD WINAPI RtlRunOnceExecuteOnce(
    PRTL_RUN_ONCE once, PRTL_RUN_ONCE_INIT_FN callback, PVOID parameter, PVOID *context);

#define PRIVATE_EXCEPTION ((DWORD)0xe0425648)
#define PRIVATE_ARGUMENT ((ULONG_PTR)0x1234abcd)
static unsigned callbacks;
static volatile LONG veh_calls, resumed;
static volatile DWORD context_flags;
static volatile LONG context_i386, context_stack_valid, exception_valid;

static DWORD WINAPI initialize(PRTL_RUN_ONCE once, PVOID parameter, PVOID *context)
{
    (void)once;
    ++callbacks;
    *context = parameter;
    return TRUE;
}

static LONG CALLBACK handle_exception(EXCEPTION_POINTERS *pointers)
{
    NT_TIB *tib;
    ULONG_PTR stack;
    if (!pointers || !pointers->ExceptionRecord || !pointers->ContextRecord ||
        pointers->ExceptionRecord->ExceptionCode != PRIVATE_EXCEPTION)
        return EXCEPTION_CONTINUE_SEARCH;
    if (InterlockedIncrement(&veh_calls) != 1) return EXCEPTION_CONTINUE_SEARCH;
    context_flags = pointers->ContextRecord->ContextFlags;
    context_i386 = (context_flags & 0x00ff0000) == CONTEXT_i386 &&
        (context_flags & (CONTEXT_CONTROL | CONTEXT_INTEGER)) == (CONTEXT_CONTROL | CONTEXT_INTEGER);
    tib = (NT_TIB *)NtCurrentTeb();
    stack = pointers->ContextRecord->Esp;
    context_stack_valid = pointers->ContextRecord->Eip != 0 &&
        stack >= (ULONG_PTR)tib->StackLimit && stack < (ULONG_PTR)tib->StackBase;
    exception_valid = !(pointers->ExceptionRecord->ExceptionFlags & EXCEPTION_NONCONTINUABLE) &&
        pointers->ExceptionRecord->NumberParameters == 1 &&
        pointers->ExceptionRecord->ExceptionInformation[0] == PRIVATE_ARGUMENT;
    return EXCEPTION_CONTINUE_EXECUTION;
}

static int write_marker(const wchar_t *path, const char *contents, int length)
{
    HANDLE file;
    DWORD written;
    if (length <= 0 || length >= 512) return 12;
    file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return 13;
    if (!WriteFile(file, contents, (DWORD)length, &written, NULL) || written != (DWORD)length) {
        CloseHandle(file); return 14;
    }
    if (!FlushFileBuffers(file)) { CloseHandle(file); return 15; }
    CloseHandle(file);
    return 0;
}

int wmain(int argc, wchar_t **argv)
{
    RTL_RUN_ONCE once = RTL_RUN_ONCE_INIT;
    PVOID context = NULL, handler;
    DWORD first, second;
    ULONG_PTR argument = PRIVATE_ARGUMENT;
    const wchar_t *marker = argc == 2 ? argv[1] : L"direct-child-result.json";
    wchar_t before[32768];
    char result[512];
    int length, status;
    if (sizeof(void *) != 4 || argc > 2) return 10;
    first = RtlRunOnceExecuteOnce(&once, initialize, (PVOID)(ULONG_PTR)0x100, &context);
    second = RtlRunOnceExecuteOnce(&once, initialize, (PVOID)(ULONG_PTR)0x200, &context);
    if (first || second || callbacks != 1 || context != (PVOID)(ULONG_PTR)0x100) return 11;
    if (wcslen(marker) + wcslen(L".before-seh.json") + 1 >= 32768) return 16;
    wcscpy(before, marker); wcscat(before, L".before-seh.json");
    handler = AddVectoredExceptionHandler(1, handle_exception);
    if (!handler) return 17;
    length = snprintf(result, sizeof(result),
        "{\"fixture\":\"mixed-architecture-child-v1\",\"stage\":\"beforeRaiseException\","
        "\"pointerBits\":32,\"callbacks\":1,\"exceptionCode\":%lu}\n", (unsigned long)PRIVATE_EXCEPTION);
    status = write_marker(before, result, length);
    if (status) { RemoveVectoredExceptionHandler(handler); return status; }
    RaiseException(PRIVATE_EXCEPTION, 0, 1, &argument);
    resumed = 1;
    if (!RemoveVectoredExceptionHandler(handler)) return 18;
    if (veh_calls != 1 || !context_i386 || !context_stack_valid || !exception_valid || resumed != 1) return 19;
    length = snprintf(result, sizeof(result),
        "{\"fixture\":\"mixed-architecture-child-v1\",\"pointerBits\":32,"
        "\"callbacks\":1,\"firstStatus\":0,\"secondStatus\":0,"
        "\"vehCalls\":%ld,\"contextFlags\":%lu,\"contextI386\":%ld,"
        "\"contextStackValid\":%ld,\"exceptionValid\":%ld,\"continuedAfterRaise\":%ld,\"exitCode\":0}\n",
        (long)veh_calls, (unsigned long)context_flags, (long)context_i386,
        (long)context_stack_valid, (long)exception_valid, (long)resumed);
    return write_marker(marker, result, length);
}
