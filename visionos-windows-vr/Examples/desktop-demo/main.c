#ifndef UNICODE
#define UNICODE 1
#endif
#ifndef _UNICODE
#define _UNICODE 1
#endif
#include <windows.h>
#include <stdio.h>

/* A small real Windows/GDI app for checking display, input and persistent I/O.
 * It uses only the system Win32 libraries shipped by Wine; no Steam account. */
enum { EDIT_NOTE = 100, BUTTON_COUNT, BUTTON_SAVE, BUTTON_LOAD };
static HWND editor, status;
static unsigned int clicks;
static WNDPROC original_button_proc;
static const WCHAR *note_path = L"demo-note.txt";
static BOOL last_save_ok, last_load_ok;
static unsigned self_test_step, self_test_initial_clicks;
static BOOL trace_input;
static unsigned input_trace_count;


/* Diagnostic events contain IDs/counts only, never the user's note text. */
static void trace(const char *event) {
    HANDLE file = CreateFileW(L"demo-events.txt", FILE_APPEND_DATA,
        FILE_SHARE_READ | FILE_SHARE_WRITE, NULL, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return;
    DWORD written;
    WriteFile(file, event, (DWORD)lstrlenA(event), &written, NULL);
    WriteFile(file, "\r\n", 2, &written, NULL);
    CloseHandle(file);
}

/* Opt-in fixture diagnostics: IDs and coordinates only, bounded to avoid
 * flooding persistent logs during normal desktop use. */
static BOOL is_input_trace_message(UINT message) {
    return (message >= WM_MOUSEFIRST && message <= WM_MOUSELAST && message != WM_MOUSEMOVE) ||
        (message >= WM_NCMOUSEMOVE && message <= WM_NCXBUTTONDBLCLK && message != WM_NCMOUSEMOVE);
}

static void trace_input_message(const char *stage, const MSG *msg, LRESULT result) {
    if (!trace_input || !is_input_trace_message(msg->message) || input_trace_count >= 256) return;
    char line[280];
    snprintf(line, sizeof(line),
        "input #%u %s hwnd=%p msg=0x%x wp=0x%llx lp=0x%llx pt=%ld,%ld result=%lld active=%p foreground=%p",
        ++input_trace_count, stage, msg->hwnd, msg->message,
        (unsigned long long)msg->wParam, (unsigned long long)(ULONG_PTR)msg->lParam,
        (long)msg->pt.x, (long)msg->pt.y, (long long)result, GetActiveWindow(), GetForegroundWindow());
    trace(line);
}

static void trace_input_callback(const char *stage, HWND window, UINT event,
                                 WPARAM wparam, LPARAM lparam, LRESULT result) {
    MSG msg = {0};
    msg.hwnd = window; msg.message = event; msg.wParam = wparam; msg.lParam = lparam;
    trace_input_message(stage, &msg, result);
}

static void trace_input_ancestry(const char *name, HWND window) {
    if (!trace_input) return;
    HWND ancestors[3];
    DWORD errors[3];
    const UINT kinds[3] = { GA_PARENT, GA_ROOT, GA_ROOTOWNER };
    for (unsigned index = 0; index < 3; ++index) {
        SetLastError(0);
        ancestors[index] = GetAncestor(window, kinds[index]);
        errors[index] = ancestors[index] ? 0 : GetLastError();
    }
    char line[280];
    snprintf(line, sizeof(line),
        "ancestry %s hwnd=%p GA_PARENT=%p err=%lu GA_ROOT=%p err=%lu GA_ROOTOWNER=%p err=%lu desktop=%p active=%p",
        name, window, ancestors[0], (unsigned long)errors[0],
        ancestors[1], (unsigned long)errors[1], ancestors[2], (unsigned long)errors[2],
        GetDesktopWindow(), GetActiveWindow());
    trace(line);
    HWND current = window;
    for (unsigned depth = 0; current && depth < 8; ++depth) {
        HWND parent = GetParent(current);
        snprintf(line, sizeof(line), "ancestry %s GetParent[%u] hwnd=%p parent=%p",
            name, depth, current, parent);
        trace(line);
        if (parent == current) { trace("ancestry self-parent cycle"); break; }
        current = parent;
    }
}

static LRESULT CALLBACK button_proc(HWND window, UINT event, WPARAM wparam, LPARAM lparam) {
    trace_input_callback("button-before", window, event, wparam, lparam, 0);
    if ((event >= WM_MOUSEFIRST && event <= WM_MOUSELAST && event != WM_MOUSEMOVE) ||
        event == BM_CLICK || event == WM_CAPTURECHANGED || event == WM_CANCELMODE) {
        char text[100];
        snprintf(text, sizeof(text), "button id=%d event=0x%x", GetDlgCtrlID(window), event);
        trace(text);
    }
    LRESULT result = CallWindowProcW(original_button_proc, window, event, wparam, lparam);
    trace_input_callback("button-after", window, event, wparam, lparam, result);
    if (event == WM_MOUSEACTIVATE) {
        char text[160];
        snprintf(text, sizeof(text), "button activate id=%d result=%lld active=%p foreground=%p",
            GetDlgCtrlID(window), (long long)result, GetActiveWindow(), GetForegroundWindow());
        trace(text);
    }
    return result;
}

static void message(const WCHAR *text) {
    trace(SetWindowTextW(status, text) ? "status text updated" : "status text update failed");
}

static void save_note(void) {
    last_save_ok = FALSE;
    WCHAR text[8192];
    char utf8[32768];
    int length = GetWindowTextW(editor, text, 8192);
    int bytes = WideCharToMultiByte(CP_UTF8, 0, text, length, utf8, sizeof(utf8), NULL, NULL);
    HANDLE file = CreateFileW(note_path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) { message(L"Save failed: could not create demo-note.txt"); return; }
    DWORD written = 0;
    BOOL ok = WriteFile(file, utf8, bytes, &written, NULL);
    CloseHandle(file);
    last_save_ok = ok && written == (DWORD)bytes;
    message(last_save_ok ? L"Saved demo-note.txt. Close and reopen to test persistence." : L"Save failed: incomplete write.");
}

static void load_note(void) {
    last_load_ok = FALSE;
    char utf8[32768];
    WCHAR text[8192];
    HANDLE file = CreateFileW(note_path, GENERIC_READ, FILE_SHARE_READ, NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) { message(L"No saved demo-note.txt yet. Type a note and choose Save note."); return; }
    DWORD bytes = 0;
    BOOL ok = ReadFile(file, utf8, sizeof(utf8), &bytes, NULL);
    CloseHandle(file);
    int count = ok ? MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, utf8, bytes, text, 8191) : 0;
    if (!ok || (bytes && count == 0)) { message(L"Load failed: could not read the UTF-8 note."); return; }
    text[count] = 0;
    last_load_ok = SetWindowTextW(editor, text);
    message(last_load_ok ? L"Loaded demo-note.txt." : L"Load failed: edit control rejected the note.");
}

static LRESULT CALLBACK window_proc(HWND window, UINT event, WPARAM wparam, LPARAM lparam) {
    trace_input_callback("parent-entry", window, event, wparam, lparam, 0);
    switch (event) {
    case WM_CREATE:
        trace("window created");
        CreateWindowW(L"STATIC", L"A Windows app running locally on Vision Pro", WS_CHILD | WS_VISIBLE,
            20, 16, 660, 24, window, NULL, NULL, NULL);
        editor = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"Type here, count clicks, then save and reload your note.",
            WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL | ES_MULTILINE | ES_AUTOVSCROLL | ES_WANTRETURN,
            20, 52, 660, 230, window, (HMENU)(INT_PTR)EDIT_NOTE, NULL, NULL);
        SendMessageW(editor, EM_SETLIMITTEXT, 8191, 0);
        CreateWindowW(L"BUTTON", L"Count clicks", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            20, 298, 150, 32, window, (HMENU)(INT_PTR)BUTTON_COUNT, NULL, NULL);
        CreateWindowW(L"BUTTON", L"Save note", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            184, 298, 150, 32, window, (HMENU)(INT_PTR)BUTTON_SAVE, NULL, NULL);
        CreateWindowW(L"BUTTON", L"Load note", WS_CHILD | WS_VISIBLE | WS_TABSTOP,
            348, 298, 150, 32, window, (HMENU)(INT_PTR)BUTTON_LOAD, NULL, NULL);
        status = CreateWindowW(L"STATIC", L"Ready. This test uses Windows GDI, not a Direct3D game.", WS_CHILD | WS_VISIBLE,
            20, 348, 660, 42, window, NULL, NULL, NULL);
        for (int id = BUTTON_COUNT; id <= BUTTON_LOAD; ++id) {
            HWND button = GetDlgItem(window, id);
            WNDPROC previous = (WNDPROC)SetWindowLongPtrW(button, GWLP_WNDPROC, (LONG_PTR)button_proc);
            if (!original_button_proc) original_button_proc = previous;
        }
        SetFocus(editor);
        return 0;
    case WM_SIZE: {
        int width = LOWORD(lparam), height = HIWORD(lparam);
        if (editor && width > 100 && height > 200) {
            MoveWindow(editor, 20, 52, width - 40, height - 170, TRUE);
            MoveWindow(GetDlgItem(window, BUTTON_COUNT), 20, height - 102, 150, 32, TRUE);
            MoveWindow(GetDlgItem(window, BUTTON_SAVE), 184, height - 102, 150, 32, TRUE);
            MoveWindow(GetDlgItem(window, BUTTON_LOAD), 348, height - 102, 150, 32, TRUE);
            MoveWindow(status, 20, height - 54, width - 40, 42, TRUE);
        }
        return 0;
    }
    case WM_COMMAND:
        {
            char text[100];
            snprintf(text, sizeof(text), "command id=%u notification=%u", LOWORD(wparam), HIWORD(wparam));
            trace(text);
        }
        if (HIWORD(wparam) == BN_CLICKED) {
            switch (LOWORD(wparam)) {
            case BUTTON_COUNT: {
                WCHAR text[80];
                wsprintfW(text, L"Clicks received by Windows: %u", ++clicks);
                char event_text[60];
                snprintf(event_text, sizeof(event_text), "count=%u", clicks);
                trace(event_text);
                message(text);
                break;
            }
            case BUTTON_SAVE: save_note(); break;
            case BUTTON_LOAD: load_note(); break;
            }
        }
        return 0;
    case WM_LBUTTONDOWN: trace("parent received mouse down"); break;
    case WM_LBUTTONUP: trace("parent received mouse up"); break;
    case WM_MOUSEACTIVATE: {
        LRESULT result = DefWindowProcW(window, event, wparam, lparam);
        char text[160];
        snprintf(text, sizeof(text), "parent activate result=%lld active=%p foreground=%p",
            (long long)result, GetActiveWindow(), GetForegroundWindow());
        trace(text);
        return result;
    }
    case WM_TIMER: {
        KillTimer(window, 1);
        if (self_test_step == 1) {
            /* Exercise actual EDIT/button handlers after the queued pointer
             * input had a message-loop turn. Keep ordinary user notes intact. */
            BOOL mouse_ok = clicks == self_test_initial_clicks + 1;
            const WCHAR *sample = L"WineVision GDI roundtrip \x2713";
            WCHAR loaded[128];
            note_path = L"demo-selftest-note.txt";
            SetWindowTextW(editor, L"");
            for (const WCHAR *character = sample; *character; ++character)
                SendMessageW(editor, WM_CHAR, *character, 0);
            GetWindowTextW(editor, loaded, 128);
            BOOL edit_ok = lstrcmpW(loaded, sample) == 0;
            unsigned before = clicks;
            SendMessageW(GetDlgItem(window, BUTTON_COUNT), BM_CLICK, 0, 0);
            BOOL button_ok = clicks == before + 1;
            SendMessageW(GetDlgItem(window, BUTTON_SAVE), BM_CLICK, 0, 0);
            SetWindowTextW(editor, L"cleared before load");
            SendMessageW(GetDlgItem(window, BUTTON_LOAD), BM_CLICK, 0, 0);
            GetWindowTextW(editor, loaded, 128);
            BOOL roundtrip_ok = last_save_ok && last_load_ok && lstrcmpW(loaded, sample) == 0;
            BOOL passed = mouse_ok && edit_ok && button_ok && roundtrip_ok;
            char result[240];
            snprintf(result, sizeof(result),
                "%s GDI desktop self-test pointerBits=%u SendInput=%d edit=%d button=%d save=%d load=%d UTF8roundtrip=%d\r\n",
                passed ? "PASS" : "FAIL", (unsigned)(sizeof(void *) * 8), mouse_ok,
                edit_ok, button_ok, last_save_ok, last_load_ok, roundtrip_ok);
            trace(result);
            HANDLE file = CreateFileW(L"demo-selftest-result.txt", GENERIC_WRITE,
                FILE_SHARE_READ, NULL, CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL);
            if (file != INVALID_HANDLE_VALUE) {
                DWORD written;
                WriteFile(file, result, (DWORD)lstrlenA(result), &written, NULL);
                CloseHandle(file);
            }
            note_path = L"demo-note.txt";
            self_test_step = 2;
            message(passed ? L"GDI self-test passed. You can now test the controls manually."
                           : L"GDI self-test failed. See demo-selftest-result.txt for the failed step.");
            return 0;
        }
        self_test_initial_clicks = clicks;
        trace("automatic Win32 input probe start");
        RECT rect;
        GetWindowRect(GetDlgItem(window, BUTTON_COUNT), &rect);
        SetCursorPos((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2);
        INPUT input[2] = {0};
        input[0].type = input[1].type = INPUT_MOUSE;
        input[0].mi.dwFlags = MOUSEEVENTF_LEFTDOWN;
        input[1].mi.dwFlags = MOUSEEVENTF_LEFTUP;
        trace(SendInput(2, input, sizeof(INPUT)) == 2 ? "SendInput accepted 2 events" : "SendInput failed");
        self_test_step = 1;
        SetTimer(window, 1, 700, NULL);
        return 0;
    }
    case WM_DESTROY: trace("window destroyed"); PostQuitMessage(0); return 0;
    }
    return DefWindowProcW(window, event, wparam, lparam);
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR command_line, int show) {
    (void)previous;
    trace_input = wcsstr(command_line, L"--trace-input") != NULL;
    if (trace_input) trace("input trace enabled; maximum 256 mouse-stage records");
    WNDCLASSW cls = {0};
    cls.lpfnWndProc = window_proc;
    cls.hInstance = instance;
    cls.lpszClassName = L"WineVisionDesktopDemo";
    cls.hCursor = LoadCursorW(NULL, IDC_ARROW);
    cls.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    if (!RegisterClassW(&cls)) return 1;
    HWND window = CreateWindowW(cls.lpszClassName, L"WineVision Windows Desktop Test",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE, 60, 50, 740, 480, NULL, NULL, instance, NULL);
    if (!window) return 2;
    ShowWindow(window, show);
    trace(SetForegroundWindow(window) ? "foreground request succeeded" : "foreground request failed");
    SetFocus(editor);
    trace_input_ancestry("root", window);
    trace_input_ancestry("button", GetDlgItem(window, BUTTON_COUNT));
    trace_input_ancestry("editor", editor);
    if (wcsstr(command_line, L"--self-test")) SetTimer(window, 1, 2000, NULL);
    MSG msg;
    int result;
    while ((result = GetMessageW(&msg, NULL, 0, 0)) > 0) {
        trace_input_message("GetMessage", &msg, result);
        MSG before_filter = msg;
        BOOL filtered = IsDialogMessageW(window, &msg);
        trace_input_message("filter-before", &before_filter, filtered);
        trace_input_message("filter-after", &msg, filtered);
        if (!filtered) {
            TranslateMessage(&msg);
            trace_input_message("dispatch-before", &msg, 0);
            LRESULT dispatched = DispatchMessageW(&msg);
            trace_input_message("dispatch-after", &msg, dispatched);
        }
    }
    return result < 0 ? 3 : (int)msg.wParam;
}
