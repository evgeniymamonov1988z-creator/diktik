/* Diktik activation key (AG).
   1) deletes demo.flag next to Diktik exe     -> full version
   2) writes license_AG.dat (marker)           -> stays activated
   3) clears demo start date (file + registry)
   --silent -> no dialogs, exit code only (0 = ok, 2 = exe not found)
*/
#include <windows.h>
#include <shlobj.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include <objbase.h>

#define PRODUCT_CODE_STR "AG"
#define LICENSE_FILE L"license_AG.dat"

/* demo edition EXE names (renamed in CI): "diktik.exe" / "VoiceNote.exe" */
static const wchar_t *g_exe[3];
static int g_exe_n = 0;

static int file_exists(const wchar_t *p) {
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES;
}

static void write_license(const wchar_t *dir) {
    wchar_t path[MAX_PATH * 2];
    _snwprintf(path, MAX_PATH * 2, L"%ls\\" LICENSE_FILE, dir);
    SetFileAttributesW(path, FILE_ATTRIBUTE_NORMAL);
    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    const char *body = "Diktik AG\r\nc31e8d7f4a2b9e506d87f1c3ab52e6d4\r\n"
                       "Activated. Do not delete this file.\r\n";
    DWORD w = 0;
    WriteFile(h, body, (DWORD)strlen(body), &w, NULL);
    CloseHandle(h);
    SetFileAttributesW(path, FILE_ATTRIBUTE_HIDDEN);
}

#define MAXCAND 12
static wchar_t *g_cand[MAXCAND];
static int g_n = 0;

static void add_candidate(const wchar_t *dir) {
    if (!dir || !dir[0]) return;
    for (int i = 0; i < g_n; i++)
        if (_wcsicmp(g_cand[i], dir) == 0) return;
    if (g_n >= MAXCAND) return;
    size_t n = (wcslen(dir) + 1) * sizeof(wchar_t);
    wchar_t *p = (wchar_t *)malloc(n);
    if (!p) return;
    memcpy(p, dir, n);
    g_cand[g_n++] = p;
}

static int has_exe(const wchar_t *dir) {
    wchar_t exe[MAX_PATH * 2];
    for (int i = 0; i < g_exe_n; i++) {
        _snwprintf(exe, MAX_PATH * 2, L"%ls\\%ls", dir, g_exe[i]);
        if (file_exists(exe)) return 1;
    }
    return 0;
}

static int try_unlock(const wchar_t *dir) {
    if (!has_exe(dir)) return 0;
    wchar_t flag[MAX_PATH * 2];
    _snwprintf(flag, MAX_PATH * 2, L"%ls\\demo.flag", dir);
    if (file_exists(flag)) {
        SetFileAttributesW(flag, FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(flag);
    }
    write_license(dir);
    return 1;
}

static void clear_date(void) {
    wchar_t appdata[MAX_PATH * 2], path[MAX_PATH * 2];
    if (SHGetFolderPathW(NULL, CSIDL_APPDATA, NULL, 0, appdata) == S_OK) {
        _snwprintf(path, MAX_PATH * 2, L"%ls\\MAMONOV\\.demo_date_AG", appdata);
        if (file_exists(path)) {
            SetFileAttributesW(path, FILE_ATTRIBUTE_NORMAL);
            DeleteFileW(path);
        }
    }
    HKEY hk;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\MAMONOV", 0, KEY_SET_VALUE, &hk) == ERROR_SUCCESS) {
        RegDeleteValueW(hk, L"first_AG");
        RegCloseKey(hk);
    }
}

static int g_lang_en = 0;

static void msg(const wchar_t *t) {
    MessageBoxW(NULL, t, L"Diktik", MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND);
}

static void self_delete(void) {
    wchar_t self[MAX_PATH * 2], cmd[MAX_PATH * 3];
    GetModuleFileNameW(NULL, self, MAX_PATH * 2);
    _snwprintf(cmd, MAX_PATH * 3,
               L"cmd.exe /c ping 127.0.0.1 -n 3 >nul & del /f /q \"%ls\"", self);
    STARTUPINFOW si = {0};
    PROCESS_INFORMATION pi = {0};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    if (CreateProcessW(NULL, cmd, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
    }
}

static int shortcut_dir(const wchar_t *lnk, wchar_t *out) {
    IShellLinkW *sl = NULL;
    IPersistFile *pfile = NULL;
    if (FAILED(CoCreateInstance(&CLSID_ShellLink, NULL, CLSCTX_INPROC_SERVER, &IID_IShellLinkW, (void **)&sl)))
        return 0;
    int ok = 0;
    if (SUCCEEDED(sl->lpVtbl->QueryInterface(sl, &IID_IPersistFile, (void **)&pfile))) {
        if (SUCCEEDED(pfile->lpVtbl->Load(pfile, lnk, STGM_READ))) {
            wchar_t target[MAX_PATH * 2];
            if (SUCCEEDED(sl->lpVtbl->GetPath(sl, target, MAX_PATH * 2, NULL, 0)) && target[0]) {
                wchar_t *s2 = wcsrchr(target, L'\\');
                if (s2) { *s2 = 0; wcscpy(out, target); ok = 1; }
            }
        }
        pfile->lpVtbl->Release(pfile);
    }
    sl->lpVtbl->Release(sl);
    return ok;
}

static void scan_subdirs(const wchar_t *base) {
    wchar_t pat[MAX_PATH * 3];
    _snwprintf(pat, MAX_PATH * 3, L"%ls\\*", base);
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(pat, &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    int guard = 0;
    do {
        if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && guard++ < 300) {
            wchar_t dir[MAX_PATH * 2];
            _snwprintf(dir, MAX_PATH * 2, L"%ls\\%ls", base, fd.cFileName);
            if (has_exe(dir)) add_candidate(dir);
        }
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

static void detect_lang(void) {
    wchar_t ln[85] = {0};
    if (GetEnvironmentVariableW(L"DIKTIK_LANG", ln, 85) && ln[0]) {
        g_lang_en = (ln[0] == L'e' || ln[0] == L'E') ? 1 : 0;
        return;
    }
    LANGID lid = GetUserDefaultUILanguage();
    g_lang_en = (PRIMARYLANGID(lid) != LANG_RUSSIAN) ? 1 : 0;
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmdline, int show) {
    (void)hInst; (void)hPrev; (void)cmdline; (void)show;
    detect_lang();
    g_exe[0] = L"diktik.exe";
    /* Diktik / VoiceNote */
    g_exe[1] = L"VoiceNote.exe";
    g_exe_n = 2;

    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) argc = 0;
    int silent = 0;
    for (int i = 1; i < argc; i++)
        if (wcscmp(argv[i], L"--silent") == 0) silent = 1;

    wchar_t local[MAX_PATH * 2] = {0}, pf[MAX_PATH * 2] = {0}, pf86[MAX_PATH * 2] = {0};
    SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, 0, local);
    GetEnvironmentVariableW(L"ProgramFiles", pf, MAX_PATH * 2);
    GetEnvironmentVariableW(L"ProgramFiles(x86)", pf86, MAX_PATH * 2);

    wchar_t b[MAX_PATH * 2];
    if (local[0]) { _snwprintf(b, MAX_PATH * 2, L"%ls\\Programs\\Diktik", local); add_candidate(b); }
    if (pf[0])    { _snwprintf(b, MAX_PATH * 2, L"%ls\\Diktik", pf);    add_candidate(b); }
    if (pf86[0])  { _snwprintf(b, MAX_PATH * 2, L"%ls\\Diktik", pf86);  add_candidate(b); }

    wchar_t self[MAX_PATH * 2];
    GetModuleFileNameW(NULL, self, MAX_PATH * 2);
    wchar_t *slash = wcsrchr(self, L'\\');
    if (slash) { *slash = 0; add_candidate(self); }

    {
        wchar_t un[2000] = {0};
        DWORD sz = sizeof(un) - sizeof(wchar_t);
        LONG r = RegGetValueW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Diktik",
                              L"InstallLocation", RRF_RT_REG_SZ, NULL, un, &sz);
        if (r != ERROR_SUCCESS)
            r = RegGetValueW(HKEY_LOCAL_MACHINE, L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Diktik",
                             L"InstallLocation", RRF_RT_REG_SZ, NULL, un, &sz);
        if (r == ERROR_SUCCESS) {
            size_t L = wcslen(un);
            while (L > 2 && (un[L - 1] == L'\\' || un[L - 1] == L'"')) un[--L] = 0;
            add_candidate(un);
        }
    }

    {
        const wchar_t *tails[] = { L"\\Desktop\\Diktik.lnk", L"\\Desktop\\VoiceNote.lnk", L"\\Desktop\\\u0414\u0438\u043a\u0442\u0438\u043a.lnk" };
        for (int t = 0; t < 3; t++) {
            wchar_t lnk[MAX_PATH * 2], dir[MAX_PATH * 2];
            if (local[0]) { _snwprintf(lnk, MAX_PATH * 2, L"%ls%ls", local, tails[t]); if (shortcut_dir(lnk, dir)) add_candidate(dir); }
            if (pf[0])    { _snwprintf(lnk, MAX_PATH * 2, L"%ls%ls", pf, tails[t]);    if (shortcut_dir(lnk, dir)) add_candidate(dir); }
        }
    }

    if (local[0]) { _snwprintf(b, MAX_PATH * 2, L"%ls\\Programs", local); scan_subdirs(b); }
    if (pf[0]) scan_subdirs(pf);
    if (pf86[0]) scan_subdirs(pf86);

    int found = 0;
    for (int i = 0; i < g_n; i++) if (try_unlock(g_cand[i])) found = 1;

    if (!found) {
        if (!silent) {
            if (g_lang_en)
                msg(L"diktik.exe was not found.\n\n"
                    L"Please install the program first, then run the key.");
            else
                msg(L"diktik.exe \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.\n\n"
                    L"\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0435 \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0443 \u0438 \u0437\u0430\u0442\u0435\u043c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 \u043a\u043b\u044e\u0447.");
        }
        return 2;
    }

    clear_date();

    if (!silent) {
        if (g_lang_en)
            msg(L"Done! You now have the full version.\n\n"
                L"Open VoiceNote / Diktik \u2014 there is no time limit.");
        else
            msg(L"\u0413\u043e\u0442\u043e\u0432\u043e! \u0422\u0435\u043f\u0435\u0440\u044c \u0443 \u0432\u0430\u0441 \u043f\u043e\u043b\u043d\u0430\u044f \u0432\u0435\u0440\u0441\u0438\u044f.\n\n"
                L"\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 \u0414\u0438\u043a\u0442\u0438\u043a \u2014 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0439 \u043f\u043e \u0434\u043d\u044f\u043c \u043d\u0435\u0442.");
    }

    self_delete();
    return 0;
}
