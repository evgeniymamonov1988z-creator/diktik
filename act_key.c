#include <windows.h>
#include <shlobj.h>
#include <stdio.h>
#include <string.h>
#include <wchar.h>
#include <objbase.h>
#include <tlhelp32.h>

/* Diktik activation key (AG).
   1) deletes demo.flag next to program exe  -> full version
   2) writes license_AG.dat (marker)         -> stays activated even if
                                                 the demo installer is run again
   3) clears demo start date (file + registry)
   --silent -> no dialogs, exit code only (0 = ok, 2 = program exe not found)
*/

#define PROD_EN L"Diktik"

/* EN text by default; RU only when the Windows UI language is Russian.
   Language does not follow the product name: RU Windows -> Russian window,
   any other Windows -> English window. */
static int ui_ru(void) {
    LANGID lid = GetUserDefaultUILanguage();
    return PRIMARYLANGID(lid) == LANG_RUSSIAN;
}

static void msg2(const wchar_t *en, const wchar_t *ru) {
    MessageBoxW(NULL, ui_ru() ? ru : en, PROD_EN,
                MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND);
}

#define PRODUCT_CODE_STR "AG"
#define PROD_CODE_W L"AG"
#define LICENSE_FILE L"license_AG.dat"
#define LICENSE_MARK L"2ebf8a0cc42dc24243a267e544e4b095"
#define PROD_RU L"Diktik"
#define PROG_EXE L"diktik.exe"
#define PROG_DIR L"Diktik"
#define UNINST_NAME L"Diktik"
#define LNK_EN L"Diktik.lnk"
#define LNK_RU L"Diktik.lnk"

static int file_exists(const wchar_t *p) {
    DWORD a = GetFileAttributesW(p);
    return a != INVALID_FILE_ATTRIBUTES;
}

static void add_candidate(const wchar_t *dir);

static void write_license(const wchar_t *dir) {
    wchar_t path[MAX_PATH * 2];
    _snwprintf(path, MAX_PATH * 2, L"%ls\\" LICENSE_FILE, dir);
    SetFileAttributesW(path, FILE_ATTRIBUTE_NORMAL);
    HANDLE h = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                           FILE_ATTRIBUTE_NORMAL, NULL);
    if (h == INVALID_HANDLE_VALUE) return;
    const char *body = "Diktik AG\r\n"
                       "2ebf8a0cc42dc24243a267e544e4b095\r\n"
                       "Activated. Do not delete this file.\r\n";
    DWORD w = 0;
    WriteFile(h, body, (DWORD)strlen(body), &w, NULL);
    CloseHandle(h);
    /* hide it, like other program service files */
    SetFileAttributesW(path, FILE_ATTRIBUTE_HIDDEN);
}

/* ---------- candidate folders (dedup) ---------- */
#define MAXCAND 64
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

static int try_unlock(const wchar_t *dir) {
    wchar_t exe[MAX_PATH * 2], flag[MAX_PATH * 2];
    _snwprintf(exe, MAX_PATH * 2, L"%ls\\" PROG_EXE, dir);
    if (!file_exists(exe)) return 0;
    _snwprintf(flag, MAX_PATH * 2, L"%ls\\demo.flag", dir);
    if (file_exists(flag)) {
        SetFileAttributesW(flag, FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(flag);
    }
    write_license(dir);
    add_candidate(dir);  /* license_AG.dat -> its own folder */
    return 1;
}

static void clear_date(void) {
    wchar_t appdata[MAX_PATH * 2], path[MAX_PATH * 2];
    if (SHGetFolderPathW(NULL, CSIDL_APPDATA, NULL, 0, appdata) == S_OK) {
        _snwprintf(path, MAX_PATH * 2, L"%ls\\MAMONOV\\.demo_date_" PROD_CODE_W, appdata);
        if (file_exists(path)) {
            SetFileAttributesW(path, FILE_ATTRIBUTE_NORMAL);
            DeleteFileW(path);
        }
    }
    HKEY hk;
    if (RegOpenKeyExW(HKEY_CURRENT_USER, L"Software\\MAMONOV", 0, KEY_SET_VALUE, &hk) == ERROR_SUCCESS) {
        RegDeleteValueW(hk, L"first_" PROD_CODE_W);
        RegCloseKey(hk);
    }
}

static void msg(const wchar_t *t) {
    MessageBoxW(NULL, t, PROD_EN, MB_OK | MB_ICONINFORMATION | MB_SETFOREGROUND);
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


/* ---------- folders of the program exe that are running right now ---------- */
static void add_running_dirs(void) {
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return;
    PROCESSENTRY32W pe;
    pe.dwSize = sizeof(pe);
    if (Process32FirstW(snap, &pe)) {
        do {
            if (_wcsicmp(pe.szExeFile, PROG_EXE) != 0) continue;
            HANDLE ph = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pe.th32ProcessID);
            if (!ph) continue;
            wchar_t full[MAX_PATH * 2];
            DWORD n = MAX_PATH * 2;
            if (QueryFullProcessImageNameW(ph, 0, full, &n)) {
                wchar_t *s = wcsrchr(full, L'\\');
                if (s) { *s = 0; add_candidate(full); }
            }
            CloseHandle(ph);
        } while (Process32NextW(snap, &pe));
    }
    CloseHandle(snap);
}

/* ---------- find the program folder via shortcut / scan ---------- */
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
                if (s2 && _wcsicmp(s2 + 1, PROG_EXE) == 0) { *s2 = 0; wcscpy(out, target); ok = 1; }
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
            wchar_t dir[MAX_PATH * 2], exe[MAX_PATH * 2];
            _snwprintf(dir, MAX_PATH * 2, L"%ls\\%ls", base, fd.cFileName);
            _snwprintf(exe, MAX_PATH * 2, L"%ls\\" PROG_EXE, dir);
            if (file_exists(exe)) add_candidate(dir);
        }
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

/* ---------- last resort: walk all fixed/removable drives ---------- */
static DWORD g_deadline = 0;

static int skip_dir(const wchar_t *name) {
    static const wchar_t *skip[] = {
        L"Windows", L"$Recycle.Bin", L"System Volume Information", L"ProgramData",
        L"Recovery", L"PerfLogs", L"MSOCache", L"Config.Msi", L"AppData"
    };
    for (size_t i = 0; i < sizeof(skip) / sizeof(skip[0]); i++)
        if (_wcsicmp(name, skip[i]) == 0) return 1;
    return 0;
}

static void scan_disk_dir(const wchar_t *dir, int depth) {
    if (depth > 6 || g_n >= MAXCAND || GetTickCount() > g_deadline) return;
    wchar_t pat[MAX_PATH * 3];
    _snwprintf(pat, MAX_PATH * 3, L"%ls\\*", dir);
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(pat, &fd);
    if (h == INVALID_HANDLE_VALUE) return;
    do {
        if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)) continue;
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT) continue; /* no junction loops */
        if (wcscmp(fd.cFileName, L".") == 0 || wcscmp(fd.cFileName, L"..") == 0) continue;
        if (skip_dir(fd.cFileName)) continue;
        wchar_t sub[MAX_PATH * 2], exe[MAX_PATH * 2];
        _snwprintf(sub, MAX_PATH * 2, L"%ls\\%ls", dir, fd.cFileName);
        _snwprintf(exe, MAX_PATH * 2, L"%ls\\" PROG_EXE, sub);
        if (file_exists(exe)) add_candidate(sub);
        scan_disk_dir(sub, depth + 1);
        if (GetTickCount() > g_deadline) break;
    } while (FindNextFileW(h, &fd));
    FindClose(h);
}

static void scan_all_drives(void) {
    g_deadline = GetTickCount() + 120000; /* at most 2 minutes */
    for (wchar_t d = L'C'; d <= L'Z'; d++) {
        wchar_t root[8];
        _snwprintf(root, 8, L"%lc:\\", d);
        UINT t = GetDriveTypeW(root);
        if (t != DRIVE_FIXED && t != DRIVE_REMOVABLE) continue;
        wchar_t base[8];
        _snwprintf(base, 8, L"%lc:", d);
        scan_disk_dir(base, 0);
        if (GetTickCount() > g_deadline) break;
    }
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmdline, int show) {
    (void)hInst; (void)hPrev; (void)cmdline; (void)show;
    int argc = 0;
    wchar_t **argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) argc = 0;
    int silent = 0;
    for (int i = 1; i < argc; i++)
        if (wcscmp(argv[i], L"--silent") == 0) silent = 1;

    /* --exe "<full path to the program exe>": license exactly that copy */
    for (int i = 1; i + 1 < argc; i++) {
        if (wcscmp(argv[i], L"--exe") == 0) {
            wchar_t d[MAX_PATH * 2];
            wcsncpy(d, argv[i + 1], MAX_PATH * 2 - 1);
            d[MAX_PATH * 2 - 1] = 0;
            wchar_t *s = wcsrchr(d, L'\\');
            if (s) { *s = 0; add_candidate(d); }
        }
    }

    wchar_t local[MAX_PATH * 2] = {0}, pf[MAX_PATH * 2] = {0}, pf86[MAX_PATH * 2] = {0};
    SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA, NULL, 0, local);
    GetEnvironmentVariableW(L"ProgramFiles", pf, MAX_PATH * 2);
    GetEnvironmentVariableW(L"ProgramFiles(x86)", pf86, MAX_PATH * 2);

    wchar_t b[MAX_PATH * 2];

    /* 1) standard install folders */
    if (local[0]) { _snwprintf(b, MAX_PATH * 2, L"%ls\\Programs\\" PROG_DIR, local); add_candidate(b); }
    if (pf[0])    { _snwprintf(b, MAX_PATH * 2, L"%ls\\" PROG_DIR, pf);    add_candidate(b); }
    if (pf86[0])  { _snwprintf(b, MAX_PATH * 2, L"%ls\\" PROG_DIR, pf86);  add_candidate(b); }

    /* 2) folder of the key itself (per-user install = same folder) */
    wchar_t self[MAX_PATH * 2];
    GetModuleFileNameW(NULL, self, MAX_PATH * 2);
    wchar_t *slash = wcsrchr(self, L'\\');
    if (slash) { *slash = 0; add_candidate(self); }

    /* 2b) copies of the program exe that are running right now (e.g. a portable copy) */
    add_running_dirs();

    /* 3) where the uninstaller says the program actually is */
    {
        wchar_t un[2000] = {0};
        DWORD sz = sizeof(un) - sizeof(wchar_t);
        LONG r = RegGetValueW(HKEY_CURRENT_USER, L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" UNINST_NAME,
                              L"InstallLocation", RRF_RT_REG_SZ, NULL, un, &sz);
        if (r != ERROR_SUCCESS)
            r = RegGetValueW(HKEY_LOCAL_MACHINE, L"Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" UNINST_NAME,
                             L"InstallLocation", RRF_RT_REG_SZ, NULL, un, &sz);
        if (r == ERROR_SUCCESS) {
            size_t L = wcslen(un);
            while (L > 2 && (un[L - 1] == L'\\' || un[L - 1] == L'"')) un[--L] = 0;
            add_candidate(un);
        }
    }

    /* 4) desktop shortcuts (user + all users) */
    {
        const wchar_t *tails[] = { L"\\Desktop\\" LNK_EN, L"\\Desktop\\" LNK_RU };
        for (int t = 0; t < 2; t++) {
            wchar_t lnk[MAX_PATH * 2], dir[MAX_PATH * 2];
            _snwprintf(lnk, MAX_PATH * 2, L"%ls%ls", local, tails[t]);
            if (shortcut_dir(lnk, dir)) add_candidate(dir);
            _snwprintf(lnk, MAX_PATH * 2, L"%ls%ls", pf, tails[t]);
            if (shortcut_dir(lnk, dir)) add_candidate(dir);
        }
    }

    /* 5) shallow scan */
    if (local[0]) { _snwprintf(b, MAX_PATH * 2, L"%ls\\Programs", local); scan_subdirs(b); }
    if (pf[0]) scan_subdirs(pf);
    if (pf86[0]) scan_subdirs(pf86);

    int found = 0;
    for (int i = 0; i < g_n; i++) if (try_unlock(g_cand[i])) found = 1;

    if (!found) {
        /* nothing in the usual places -> search all drives */
        int start = g_n;
        scan_all_drives();
        for (int i = start; i < g_n; i++) if (try_unlock(g_cand[i])) found = 1;
    }

    if (!found) {
        if (!silent) msg2(PROG_EXE L" was not found.\n\n"
                          L"Please install the program first, then run the key.",
                          PROG_EXE L" \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.\n\n"
                          L"\u0421\u043d\u0430\u0447\u0430\u043b\u0430 \u0443\u0441\u0442\u0430\u043d\u043e\u0432\u0438\u0442\u0435 \u043f\u0440\u043e\u0433\u0440\u0430\u043c\u043c\u0443 \u0438 \u0437\u0430\u0442\u0435\u043c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u0435 \u043a\u043b\u044e\u0447.");
        return 2;
    }

    clear_date();

    if (!silent)
        msg2(L"Done! You now have the full version.\n\n"
             L"Open " PROD_EN L" \u2014 there is no time limit.",
             L"\u0413\u043e\u0442\u043e\u0432\u043e! \u0422\u0435\u043f\u0435\u0440\u044c \u0443 \u0432\u0430\u0441 \u043f\u043e\u043b\u043d\u0430\u044f \u0432\u0435\u0440\u0441\u0438\u044f.\n\n"
             L"\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 " PROD_RU L" \u2014 \u043e\u0433\u0440\u0430\u043d\u0438\u0447\u0435\u043d\u0438\u0439 \u043f\u043e \u0434\u043d\u044f\u043c \u043d\u0435\u0442.");

    self_delete();
    return 0;
}
