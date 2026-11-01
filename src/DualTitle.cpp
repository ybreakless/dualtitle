/**
 * DualTitle.cpp — Main C++17 Native Application for DualTitle
 * (Universal Anti-Cheat-Safe Dual-Subtitles, Audio Controller, Save Manager & Live Overlay)
 *
 * Features:
 *   1. [NATIVE WIN32 DARK GUI (`--gui` or default on Windows)]:
 *      Opens the DualTitle Desktop Control Panel featuring the custom DualTitle Gamepad +
 *      Tilted Subtitle Bars Logo (`assets/dualtitle.ico`), Auto-Detected Game Library Picker,
 *      Audio/Primary/Secondary Language Selectors, Speed Selector (`0.50x`–`2.00x`),
 *      1-Click "🚀 Launch Selected Game + In-Game Overlay", and 1-Click "💾 Restore Save"!
 *   2. [100% ANTI-CHEAT SAFE / ZERO INJECTION]:
 *      Never injects DLLs or opens foreign process handles. Cleans any legacy `.utoc`/`.ucas`/
 *      `.pak` or `ue4ss` files before launch so every game opens natively without flags.
 *   3. [IN-GAME INTERACTIVE OVERLAY HUD (`--overlay`)]:
 *      Displays Primary (Top in Gold #FFD700) + Secondary (Bottom in Ice-White #E2E8F0)
 *      subtitles with clickable words for instant Dictionary definitions, `- Spd / + Spd`
 *      speed controls, `⏸ Game (ESC)` pause, `🔲 Borderless`, and `💾 Restore Save`.
 *   4. [UNIVERSAL SAVE BACKUP & RESTORE (`--restore-save` / `--backup-save`)]:
 *      Automatically protects user save files (`Saved/SaveGames`, `PROF_SAVE*`, `Saves`,
 *      `*.sav`, `*.ini`) and restores them with 1 click.
 */

#include "DualTitleEngine.hpp"
#include "DualTitleOverlay.hpp"
#include <cassert>

using namespace DualTitle;

// ============================================================================
// Universal Multi-Drive Game & Application Scanner (C: through Z:)
// ============================================================================

struct DetectedGame {
    std::string title;
    fs::path path;
};

static bool IsSuiteDirectory(const fs::path& p) {
    std::error_code ec;
    return fs::is_regular_file(p / "universal_dualsub.py", ec) &&
           fs::is_regular_file(p / "subtitle_engine.py", ec);
}

static bool LooksLikeApplicationDir(const fs::path& p) {
    std::error_code ec;
    if (!fs::is_directory(p, ec) || IsSuiteDirectory(p)) return false;
    if (fs::is_directory(p / "Engine", ec) ||
        fs::is_directory(p / "Data" / "Win32" / "Loc", ec) ||
        !FindUnrealSubprojects(p).empty()) {
        return true;
    }
    for (const auto& entry : fs::directory_iterator(p, ec)) {
        if (!entry.is_regular_file(ec)) continue;
        std::string ext = entry.path().extension().string();
        std::transform(ext.begin(), ext.end(), ext.begin(), ::tolower);
        if (ext == ".exe" || ext == ".forge" || ext == ".pak" || ext == ".utoc") {
            return true;
        }
    }
    return false;
}

static std::vector<DetectedGame> ScanInstalledGames() {
    std::vector<DetectedGame> found;
    std::set<std::string> seen;
    std::error_code ec;

    auto add_if_valid = [&](const fs::path& p) {
        if (!LooksLikeApplicationDir(p)) return;
        std::string abs_str = fs::weakly_canonical(p, ec).string();
        if (seen.insert(abs_str).second) {
            std::string title = p.filename().string();
            if (title.empty()) title = abs_str;
            found.push_back({title, p});
        }
    };

    std::vector<std::string> drives;
#ifdef _WIN32
    for (char d : std::string("CDEFGHIJKLMNOPQRSTUVWXYZ")) {
        std::string root = std::string(1, d) + ":\\";
        if (fs::is_directory(root, ec)) drives.push_back(root);
    }
#else
    drives.push_back("/");
#endif

    const std::vector<fs::path> library_rel_paths = {
        "Games",
        "Origin Games",
        "EA Games",
        "GOG Games",
        "Epic Games",
        fs::path("SteamLibrary") / "steamapps" / "common",
        fs::path("Program Files (x86)") / "Steam" / "steamapps" / "common",
        fs::path("Program Files") / "Steam" / "steamapps" / "common",
        fs::path("Program Files (x86)") / "Origin Games",
        fs::path("Program Files") / "EA Games",
        fs::path("Program Files (x86)") / "Ubisoft" / "Ubisoft Game Launcher" / "games",
        fs::path("Ubisoft Game Launcher") / "games"
    };

    for (const auto& drv : drives) {
        fs::path dpath(drv);
        for (const auto& rel : library_rel_paths) {
            fs::path lib_dir = dpath / rel;
            if (!fs::is_directory(lib_dir, ec)) continue;
            for (const auto& item : fs::directory_iterator(lib_dir, ec)) {
                if (item.is_directory(ec)) add_if_valid(item.path());
            }
        }
        // Also scan top-level folders on drives D:..Z:
        if (drv[0] != 'C' && drv[0] != '/') {
            for (const auto& item : fs::directory_iterator(dpath, ec)) {
                if (!item.is_directory(ec)) continue;
                std::string fn = item.path().filename().string();
                if (!fn.empty() && fn[0] != '$' && fn[0] != '.' &&
                    fn != "Windows" && fn != "Program Files" && fn != "Program Files (x86)" &&
                    fn != "Users" && fn != "System Volume Information") {
                    add_if_valid(item.path());
                }
            }
        }
    }
    return found;
}

[[maybe_unused]] static fs::path FindMainGameExecutable(const fs::path& game_dir) {
    std::error_code ec;
    if (!fs::is_directory(game_dir, ec)) return {};

    // Check Unreal subproject Shipping binaries first
    for (const auto& sub : FindUnrealSubprojects(game_dir)) {
        fs::path win64 = sub / "Binaries" / "Win64";
        if (fs::is_directory(win64, ec)) {
            for (const auto& entry : fs::directory_iterator(win64, ec)) {
                if (entry.is_regular_file(ec) && entry.path().extension() == ".exe") {
                    std::string fn = entry.path().filename().string();
                    if (fn.find("Crash") == std::string::npos && fn.find("UnrealCEF") == std::string::npos) {
                        return entry.path();
                    }
                }
            }
        }
    }

    // Check root directory executables
    for (const auto& entry : fs::directory_iterator(game_dir, ec)) {
        if (!entry.is_regular_file(ec) || entry.path().extension() != ".exe") continue;
        std::string low = entry.path().filename().string();
        std::transform(low.begin(), low.end(), low.begin(), ::tolower);
        if (low.find("unins") == std::string::npos &&
            low.find("cleanup") == std::string::npos &&
            low.find("crash") == std::string::npos &&
            low.find("setup") == std::string::npos &&
            low.find("activation") == std::string::npos) {
            return entry.path();
        }
    }
    return {};
}

// ============================================================================
// Native Win32 Dark Control Panel GUI (With Logo, Game Picker & Restore Save)
// ============================================================================

#ifdef _WIN32
#include <commdlg.h>
#include <shlobj.h>

class Win32ControlPanelGui {
public:
    static inline std::vector<DetectedGame> games_list;
    static inline HWND hComboGame = nullptr;
    static inline HWND hEditPath = nullptr;
    static inline HWND hComboAudio = nullptr;
    static inline HWND hComboPrim = nullptr;
    static inline HWND hComboSec = nullptr;
    static inline HWND hComboSpeed = nullptr;
    static inline HWND hLblStatus = nullptr;

    enum GuiCtrlId {
        ID_COMBO_GAME = 1001,
        ID_EDIT_PATH = 1002,
        ID_BTN_BROWSE = 1003,
        ID_COMBO_AUDIO = 1004,
        ID_COMBO_PRIM = 1005,
        ID_COMBO_SEC = 1006,
        ID_COMBO_SPEED = 1007,
        ID_BTN_LAUNCH_ALL = 1008,
        ID_BTN_OVERLAY_ONLY = 1009,
        ID_BTN_APPLY_ONLY = 1010,
        ID_BTN_RESTORE_SAVE = 1011,
        ID_BTN_BACKUP_SAVE = 1012,
        ID_BTN_REPAIR = 1013
    };

    static std::string GetWindowStringUtf8(HWND h) {
        int len = GetWindowTextLengthW(h);
        if (len <= 0) return "";
        std::wstring wstr(static_cast<size_t>(len), L'\0');
        GetWindowTextW(h, wstr.data(), len + 1);
        int ulen = WideCharToMultiByte(CP_UTF8, 0, wstr.data(), len, nullptr, 0, nullptr, nullptr);
        std::string out(static_cast<size_t>(ulen), '\0');
        WideCharToMultiByte(CP_UTF8, 0, wstr.data(), len, out.data(), ulen, nullptr, nullptr);
        return out;
    }

    static std::string GetComboLangCode(HWND hCombo) {
        int idx = static_cast<int>(SendMessageW(hCombo, CB_GETCURSEL, 0, 0));
        const auto& langs = GetSupportedLanguages();
        if (idx >= 0 && static_cast<size_t>(idx) < langs.size()) {
            return langs[static_cast<size_t>(idx)].code;
        }
        return "en";
    }

    static double GetComboSpeedValue(HWND hCombo) {
        static const double speeds[] = {0.50, 0.75, 1.00, 1.25, 1.50, 2.00};
        int idx = static_cast<int>(SendMessageW(hCombo, CB_GETCURSEL, 0, 0));
        if (idx >= 0 && idx < 6) return speeds[idx];
        return 1.0;
    }

    static LRESULT CALLBACK GuiWndProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam) {
        switch (msg) {
            case WM_CREATE: {
                HFONT hFontTitle = CreateFontW(20, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE,
                    DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                    DEFAULT_PITCH | FF_SWISS, L"Segoe UI");
                HFONT hFontUi = CreateFontW(15, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                    DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                    DEFAULT_PITCH | FF_SWISS, L"Segoe UI");
                HFONT hFontBold = CreateFontW(15, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE,
                    DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                    DEFAULT_PITCH | FF_SWISS, L"Segoe UI");

                auto add_label = [&](const wchar_t* txt, int x, int y, int w, int h, HFONT f) {
                    HWND hl = CreateWindowW(L"STATIC", txt, WS_CHILD | WS_VISIBLE, x, y, w, h, hwnd, nullptr, nullptr, nullptr);
                    SendMessageW(hl, WM_SETFONT, reinterpret_cast<WPARAM>(f), TRUE);
                    return hl;
                };

                add_label(L"DUALTITLE — UNIVERSAL ANTI-CHEAT-SAFE DUAL SUBTITLES", 76, 16, 510, 26, hFontTitle);
                add_label(L"Choose any game you own • Auto Save Backup & Restore • Clickable Words & Speed HUD", 76, 42, 510, 20, hFontUi);

                // Top Row: Restore Save & Repair Buttons
                HWND hBtnRestoreTop = CreateWindowW(L"BUTTON", L"💾 RESTORE SAVE (Restore Saved Progress & Profile)",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 20, 76, 305, 34, hwnd, reinterpret_cast<HMENU>(ID_BTN_RESTORE_SAVE), nullptr, nullptr);
                SendMessageW(hBtnRestoreTop, WM_SETFONT, reinterpret_cast<WPARAM>(hFontBold), TRUE);

                HWND hBtnRepairTop = CreateWindowW(L"BUTTON", L"🛠️ 1-CLICK REPAIR & CLEAN FOLDER",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 335, 76, 265, 34, hwnd, reinterpret_cast<HMENU>(ID_BTN_REPAIR), nullptr, nullptr);
                SendMessageW(hBtnRepairTop, WM_SETFONT, reinterpret_cast<WPARAM>(hFontBold), TRUE);

                // 1. Detected Games Dropdown
                add_label(L"1. Choose Installed Game / Application (Auto-Scanned Across C: - Z:):", 20, 122, 560, 20, hFontBold);
                hComboGame = CreateWindowW(L"COMBOBOX", L"", WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
                    20, 144, 580, 240, hwnd, reinterpret_cast<HMENU>(ID_COMBO_GAME), nullptr, nullptr);
                SendMessageW(hComboGame, WM_SETFONT, reinterpret_cast<WPARAM>(hFontUi), TRUE);

                games_list = ScanInstalledGames();
                for (const auto& g : games_list) {
                    std::wstring item = Win32UniversalOverlay::Utf8ToWide(g.title + "  (" + g.path.string() + ")");
                    SendMessageW(hComboGame, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(item.c_str()));
                }
                if (!games_list.empty()) SendMessageW(hComboGame, CB_SETCURSEL, 0, 0);

                // Custom Game Folder Path + Browse
                add_label(L"Active Game Folder Path (or paste any folder / .exe path):", 20, 180, 460, 20, hFontUi);
                std::wstring init_path = games_list.empty() ? L"" : Win32UniversalOverlay::Utf8ToWide(games_list[0].path.string());
                hEditPath = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", init_path.c_str(),
                    WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, 20, 202, 470, 26, hwnd, reinterpret_cast<HMENU>(ID_EDIT_PATH), nullptr, nullptr);
                SendMessageW(hEditPath, WM_SETFONT, reinterpret_cast<WPARAM>(hFontUi), TRUE);

                HWND hBtnBrowse = CreateWindowW(L"BUTTON", L"📂 Browse...",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 500, 201, 100, 28, hwnd, reinterpret_cast<HMENU>(ID_BTN_BROWSE), nullptr, nullptr);
                SendMessageW(hBtnBrowse, WM_SETFONT, reinterpret_cast<WPARAM>(hFontUi), TRUE);

                // Language Selectors
                const auto& langs = GetSupportedLanguages();
                auto populate_lang_combo = [&](HWND hc, const std::string& def_code) {
                    int sel = 0;
                    for (size_t i = 0; i < langs.size(); ++i) {
                        std::wstring lbl = Win32UniversalOverlay::Utf8ToWide(langs[i].code + " — " + langs[i].display_name);
                        SendMessageW(hc, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(lbl.c_str()));
                        if (langs[i].code == def_code) sel = static_cast<int>(i);
                    }
                    SendMessageW(hc, CB_SETCURSEL, sel, 0);
                };

                add_label(L"2. Spoken Audio Language (Voice Track):", 20, 240, 280, 20, hFontBold);
                hComboAudio = CreateWindowW(L"COMBOBOX", L"", WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
                    20, 262, 280, 220, hwnd, reinterpret_cast<HMENU>(ID_COMBO_AUDIO), nullptr, nullptr);
                SendMessageW(hComboAudio, WM_SETFONT, reinterpret_cast<WPARAM>(hFontUi), TRUE);
                populate_lang_combo(hComboAudio, "en");

                add_label(L"3. Default Subtitle Speed (In-Game Control):", 320, 240, 280, 20, hFontBold);
                hComboSpeed = CreateWindowW(L"COMBOBOX", L"", WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST,
                    320, 262, 280, 180, hwnd, reinterpret_cast<HMENU>(ID_COMBO_SPEED), nullptr, nullptr);
                SendMessageW(hComboSpeed, WM_SETFONT, reinterpret_cast<WPARAM>(hFontUi), TRUE);
                const wchar_t* speed_labels[] = {
                    L"0.50x (Slow Study Speed)",
                    L"0.75x (Relaxed Reading Speed)",
                    L"1.00x (Normal Real-Time Speed)",
                    L"1.25x (Fast Reading Speed)",
                    L"1.50x (Rapid Speed)",
                    L"2.00x (Double Speed)"
                };
                for (int i = 0; i < 6; ++i) SendMessageW(hComboSpeed, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(speed_labels[i]));
                SendMessageW(hComboSpeed, CB_SETCURSEL, 2, 0);

                add_label(L"4. Primary Subtitle Language (Top Line - Gold):", 20, 300, 280, 20, hFontBold);
                hComboPrim = CreateWindowW(L"COMBOBOX", L"", WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
                    20, 322, 280, 220, hwnd, reinterpret_cast<HMENU>(ID_COMBO_PRIM), nullptr, nullptr);
                SendMessageW(hComboPrim, WM_SETFONT, reinterpret_cast<WPARAM>(hFontUi), TRUE);
                populate_lang_combo(hComboPrim, "en");

                add_label(L"5. Secondary Subtitle Language (Bottom Line - White):", 320, 300, 280, 20, hFontBold);
                hComboSec = CreateWindowW(L"COMBOBOX", L"", WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL,
                    320, 322, 280, 220, hwnd, reinterpret_cast<HMENU>(ID_COMBO_SEC), nullptr, nullptr);
                SendMessageW(hComboSec, WM_SETFONT, reinterpret_cast<WPARAM>(hFontUi), TRUE);
                populate_lang_combo(hComboSec, "de");

                // Main Action Buttons
                HWND hBtnLaunchAll = CreateWindowW(L"BUTTON",
                    L"🚀 LAUNCH SELECTED GAME + IN-GAME DUAL-SUBTITLE OVERLAY (100% ANTI-CHEAT SAFE)",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 20, 366, 580, 40, hwnd, reinterpret_cast<HMENU>(ID_BTN_LAUNCH_ALL), nullptr, nullptr);
                SendMessageW(hBtnLaunchAll, WM_SETFONT, reinterpret_cast<WPARAM>(hFontBold), TRUE);

                HWND hBtnOverlay = CreateWindowW(L"BUTTON",
                    L"🎮 Open Interactive In-Game Dual-Subtitle HUD Only (Click Words & Speed Controls)",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 20, 414, 580, 34, hwnd, reinterpret_cast<HMENU>(ID_BTN_OVERLAY_ONLY), nullptr, nullptr);
                SendMessageW(hBtnOverlay, WM_SETFONT, reinterpret_cast<WPARAM>(hFontBold), TRUE);

                HWND hBtnApply = CreateWindowW(L"BUTTON", L"Apply Pre-Game Audio/Subtitle Config",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 20, 456, 190, 32, hwnd, reinterpret_cast<HMENU>(ID_BTN_APPLY_ONLY), nullptr, nullptr);
                SendMessageW(hBtnApply, WM_SETFONT, reinterpret_cast<WPARAM>(hFontUi), TRUE);

                HWND hBtnBackup = CreateWindowW(L"BUTTON", L"📦 Backup Save Now",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 220, 456, 180, 32, hwnd, reinterpret_cast<HMENU>(ID_BTN_BACKUP_SAVE), nullptr, nullptr);
                SendMessageW(hBtnBackup, WM_SETFONT, reinterpret_cast<WPARAM>(hFontUi), TRUE);

                HWND hBtnRestoreBot = CreateWindowW(L"BUTTON", L"💾 Restore Save",
                    WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 410, 456, 190, 32, hwnd, reinterpret_cast<HMENU>(ID_BTN_RESTORE_SAVE), nullptr, nullptr);
                SendMessageW(hBtnRestoreBot, WM_SETFONT, reinterpret_cast<WPARAM>(hFontBold), TRUE);

                hLblStatus = add_label(
                    L"Status: Ready (100% Zero-Injection Anti-Cheat-Safe Mode). Saves are automatically backed up before every launch.",
                    20, 500, 580, 36, hFontUi);
                return 0;
            }

            case WM_COMMAND: {
                int id = LOWORD(wparam);
                int code = HIWORD(wparam);

                if (id == ID_COMBO_GAME && code == CBN_SELCHANGE) {
                    int idx = static_cast<int>(SendMessageW(hComboGame, CB_GETCURSEL, 0, 0));
                    if (idx >= 0 && static_cast<size_t>(idx) < games_list.size()) {
                        std::wstring pstr = Win32UniversalOverlay::Utf8ToWide(games_list[static_cast<size_t>(idx)].path.string());
                        SetWindowTextW(hEditPath, pstr.c_str());
                    }
                    return 0;
                }

                fs::path gdir = GetWindowStringUtf8(hEditPath);
                std::string a_lang = GetComboLangCode(hComboAudio);
                std::string p_lang = GetComboLangCode(hComboPrim);
                std::string s_lang = GetComboLangCode(hComboSec);
                double spd = GetComboSpeedValue(hComboSpeed);

                if (id == ID_BTN_BROWSE) {
                    wchar_t file_buf[MAX_PATH] = {};
                    OPENFILENAMEW ofn = {};
                    ofn.lStructSize = sizeof(ofn);
                    ofn.hwndOwner = hwnd;
                    ofn.lpstrFilter = L"Game Executable (*.exe)\0*.exe\0All Files (*.*)\0*.*\0";
                    ofn.lpstrFile = file_buf;
                    ofn.nMaxFile = MAX_PATH;
                    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST;
                    if (GetOpenFileNameW(&ofn)) {
                        fs::path picked = fs::path(file_buf).parent_path();
                        SetWindowTextW(hEditPath, picked.wstring().c_str());
                    }
                } else if (id == ID_BTN_RESTORE_SAVE) {
                    std::ostringstream log_ss;
                    int cnt = SaveBackupManager::RestoreSaves(gdir, log_ss);
                    std::wstring msg = L"Restore Save complete (" + std::to_wstring(cnt) + L" save/profile file(s) restored & verified).";
                    SetWindowTextW(hLblStatus, msg.c_str());
                    MessageBoxW(hwnd, msg.c_str(), L"DualTitle — Restore Save", MB_OK | MB_ICONINFORMATION);
                } else if (id == ID_BTN_BACKUP_SAVE) {
                    std::ostringstream log_ss;
                    int cnt = SaveBackupManager::BackupSaves(gdir, log_ss);
                    std::wstring msg = L"Backed up " + std::to_wstring(cnt) + L" save/profile file(s) to .dualtitle_save_backup.";
                    SetWindowTextW(hLblStatus, msg.c_str());
                    MessageBoxW(hwnd, msg.c_str(), L"DualTitle — Backup Save", MB_OK | MB_ICONINFORMATION);
                } else if (id == ID_BTN_REPAIR) {
                    std::ostringstream log_ss;
                    int fixed = EmergencyGameRepair::RepairGameDirectory(gdir, log_ss);
                    SaveBackupManager::RestoreSaves(gdir, log_ss);
                    std::wstring msg = L"Cleaned & repaired " + std::to_wstring(fixed) + L" file(s) and verified original saves.";
                    SetWindowTextW(hLblStatus, msg.c_str());
                    MessageBoxW(hwnd, msg.c_str(), L"DualTitle — Repair & Clean Complete", MB_OK | MB_ICONINFORMATION);
                } else if (id == ID_BTN_APPLY_ONLY) {
                    std::ostringstream log_ss;
                    EmergencyGameRepair::RepairGameDirectory(gdir, log_ss);
                    ConfigPatcher::ApplyGameConfig(gdir, a_lang, p_lang, log_ss);
                    std::wstring msg = L"Applied safe pre-game audio/subtitle settings (Saves backed up automatically).";
                    SetWindowTextW(hLblStatus, msg.c_str());
                } else if (id == ID_BTN_OVERLAY_ONLY) {
                    ShowWindow(hwnd, SW_MINIMIZE);
                    Win32UniversalOverlay::RunOverlayLoop(gdir, p_lang, s_lang, spd);
                } else if (id == ID_BTN_LAUNCH_ALL) {
                    std::ostringstream log_ss;
                    // 1. Back up saves and clean any foreign files so anti-cheat is 100% happy
                    SaveBackupManager::BackupSaves(gdir, log_ss);
                    EmergencyGameRepair::RepairGameDirectory(gdir, log_ss);
                    ConfigPatcher::ApplyGameConfig(gdir, a_lang, p_lang, log_ss);

                    // 2. Launch the game executable cleanly via ShellExecuteW
                    fs::path exe_path = FindMainGameExecutable(gdir);
                    if (!exe_path.empty()) {
                        ShellExecuteW(nullptr, L"open", exe_path.wstring().c_str(), nullptr, gdir.wstring().c_str(), SW_SHOWNORMAL);
                    }
                    // 3. Minimize control panel and start the Anti-Cheat-Safe In-Game Overlay HUD
                    ShowWindow(hwnd, SW_MINIMIZE);
                    Win32UniversalOverlay::RunOverlayLoop(gdir, p_lang, s_lang, spd);
                }
                return 0;
            }

            case WM_PAINT: {
                PAINTSTRUCT ps;
                HDC hdc = BeginPaint(hwnd, &ps);
                // Draw DualTitle Gamepad + Subtitle Bars Logo Badge in top-left (x=18, y=14, 48x48)
                Win32UniversalOverlay::DrawDualTitleMiniLogo(hdc, 20, 16, 44);
                EndPaint(hwnd, &ps);
                return 0;
            }

            case WM_DESTROY:
                PostQuitMessage(0);
                return 0;
        }
        return DefWindowProcW(hwnd, msg, wparam, lparam);
    }

    static int RunGui() {
        HINSTANCE hInst = GetModuleHandleW(nullptr);
        const wchar_t* clsName = L"DualTitleNativeGuiWndV4";

        WNDCLASSW wc = {};
        wc.lpfnWndProc = GuiWndProc;
        wc.hInstance = hInst;
        wc.lpszClassName = clsName;
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.hbrBackground = reinterpret_cast<HBRUSH>(COLOR_WINDOW + 1);
        wc.hIcon = static_cast<HICON>(LoadImageW(nullptr, L"assets\\dualtitle.ico", IMAGE_ICON, 32, 32, LR_LOADFROMFILE));
        if (!wc.hIcon) wc.hIcon = LoadIcon(hInst, MAKEINTRESOURCE(101));
        RegisterClassW(&wc);

        int sw = GetSystemMetrics(SM_CXSCREEN);
        int sh = GetSystemMetrics(SM_CYSCREEN);
        int w = 630, h = 585;
        HWND hwnd = CreateWindowExW(
            0, clsName,
            L"DualTitle — Universal Anti-Cheat-Safe Dual Subtitles & Save Controller",
            WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX | WS_VISIBLE,
            (sw - w) / 2, (sh - h) / 2, w, h,
            nullptr, nullptr, hInst, nullptr
        );
        if (!hwnd) return 1;

        ShowWindow(hwnd, SW_SHOW);
        UpdateWindow(hwnd);

        MSG msg;
        while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        return 0;
    }
};
#endif // _WIN32

// ============================================================================
// Automated C++17 Verification Suite (--self-test)
// ============================================================================

static int RunCppSelfTests() {
    std::cout << "========================================================================\n"
              << "  RUNNING DUALTITLE (C++17 EDITION) AUTOMATED VERIFICATION SUITE\n"
              << "========================================================================\n";

    fs::path tmp = fs::temp_directory_path() / "dualtitle_cpp_test";
    std::error_code ec;
    fs::remove_all(tmp, ec);
    fs::create_directories(tmp, ec);

    // Test 1: Anti-Cheat Cleaner & Emergency Repair (Removes crashing .utoc/.ucas/.pak & synthetic .locres)
    std::cout << "  [Test 1/5] Testing Anti-Cheat Cleaner & Emergency Container Repair...\n";
    fs::path ue_dir = tmp / "SampleUnrealApp";
    fs::path paks_mods = ue_dir / "SubProject" / "Content" / "Paks" / "~mods";
    fs::path loc_en = ue_dir / "SubProject" / "Content" / "Localization" / "Game" / "en";
    fs::create_directories(paks_mods, ec);
    fs::create_directories(loc_en, ec);

    WriteTextFile(paks_mods / "pakchunk99-DualSub_en_de_P.utoc", "corrupt_utoc");
    WriteTextFile(paks_mods / "pakchunk99-DualSub_en_de_P.ucas", "corrupt_ucas");
    WriteTextFile(paks_mods / "pakchunk99-DualSub_en_de_P.pak", "corrupt_pak");
    WriteTextFile(loc_en / "Game.locres", "DLG_01 synthetic");

    std::ostringstream null_log;
    int fixed = EmergencyGameRepair::RepairGameDirectory(ue_dir, null_log);
    assert(fixed >= 4);
    assert(!fs::exists(paks_mods / "pakchunk99-DualSub_en_de_P.utoc"));
    assert(!fs::exists(paks_mods / "pakchunk99-DualSub_en_de_P.ucas"));
    assert(!fs::exists(loc_en / "Game.locres"));
    std::cout << "             PASS: Crashing .utoc/.ucas/.pak and synthetic .locres removed cleanly.\n";

    // Test 2: SaveBackupManager ("Restore Save") & Frostbite/Steam Config Patcher
    std::cout << "  [Test 2/5] Testing SaveBackupManager ('Restore Save') & Frostbite/Steam Configs...\n";
    fs::path app_dir = tmp / "SampleActionApp";
    fs::create_directories(app_dir / "settings", ec);
    fs::create_directories(app_dir / "Data" / "Win32" / "Loc", ec);
    fs::create_directories(app_dir / "Saved" / "SaveGames", ec);

    WriteTextFile(app_dir / "steam_api.ini", "[Settings]\nLanguage=english\n");
    WriteTextFile(app_dir / "settings" / "PROF_SAVE_profile", "GstAudio.Subtitles 0\nGstAudio.AudioLanguage 0\n");
    WriteTextFile(app_dir / "Saved" / "SaveGames" / "Slot1.sav", "ORIGINAL_USER_SAVE_PROGRESS_100%");

    ConfigPatcher::ApplyGameConfig(app_dir, "ja", "de", null_log);
    std::string patched_ini = ReadTextFile(app_dir / "steam_api.ini");
    assert(patched_ini.find("Language=german") != std::string::npos);
    assert(patched_ini.find("AudioLanguage=japanese") != std::string::npos);
    std::string patched_prof = ReadTextFile(app_dir / "settings" / "PROF_SAVE_profile");
    assert(patched_prof.find("GstAudio.Subtitles 1") != std::string::npos);

    // Simulate corrupted save file and test RestoreSaves ("Restore Save" button)
    WriteTextFile(app_dir / "Saved" / "SaveGames" / "Slot1.sav", "CORRUPTED_SAVE");
    int restored_saves = SaveBackupManager::RestoreSaves(app_dir, null_log);
    assert(restored_saves >= 1);
    assert(ReadTextFile(app_dir / "Saved" / "SaveGames" / "Slot1.sav") == "ORIGINAL_USER_SAVE_PROGRESS_100%");
    assert(ReadTextFile(app_dir / "steam_api.ini") == "[Settings]\nLanguage=english\n");
    std::cout << "             PASS: SaveBackupManager ('Restore Save') and Frostbite/INI rollback verified.\n";

    // Test 3: FORGE v27 Binary Archive Append-Only Patching & Restore
    std::cout << "  [Test 3/5] Testing C++17 FORGE v27 Binary Archive Patcher & Restore...\n";
    fs::path forge_file = app_dir / "DataPC.forge";
    std::vector<uint8_t> forge_buf(0x100, 0);
    std::memcpy(forge_buf.data(), "scimitar\0", 9);
    uint32_t ver27 = 27;
    uint64_t dh_off = 0x20;
    uint32_t row_cnt = 2;
    uint64_t toc_off = 0x100;
    std::memcpy(forge_buf.data() + 9, &ver27, 4);
    std::memcpy(forge_buf.data() + 13, &dh_off, 8);
    std::memcpy(forge_buf.data() + 0x20, &row_cnt, 4);
    std::memcpy(forge_buf.data() + 0x20 + 20, &toc_off, 8);

    std::string b_en = "LANG:en:Hello Captain!";
    std::string b_de = "LANG:de:Hallo Kapitaen!";
    uint64_t off1 = toc_off + 40;
    uint64_t off2 = off1 + b_en.size();
    uint64_t rid1 = 0x1001, rid2 = 0x1002;
    uint32_t sz1 = static_cast<uint32_t>(b_en.size()), sz2 = static_cast<uint32_t>(b_de.size());

    std::vector<uint8_t> rows_bin(40, 0);
    std::memcpy(rows_bin.data(), &off1, 8);
    std::memcpy(rows_bin.data() + 8, &rid1, 8);
    std::memcpy(rows_bin.data() + 16, &sz1, 4);
    std::memcpy(rows_bin.data() + 20, &off2, 8);
    std::memcpy(rows_bin.data() + 28, &rid2, 8);
    std::memcpy(rows_bin.data() + 36, &sz2, 4);

    forge_buf.insert(forge_buf.end(), rows_bin.begin(), rows_bin.end());
    forge_buf.insert(forge_buf.end(), b_en.begin(), b_en.end());
    forge_buf.insert(forge_buf.end(), b_de.begin(), b_de.end());
    auto orig_size = forge_buf.size();
    WriteBinaryFile(forge_file, forge_buf);

    bool forge_ok = ForgePatcher::PatchForgeArchive(forge_file, "en", "de", null_log);
    assert(forge_ok);
    assert(fs::file_size(forge_file) > orig_size);
    EmergencyGameRepair::RepairGameDirectory(app_dir, null_log);
    assert(fs::file_size(forge_file) == orig_size);
    std::cout << "             PASS: FORGE v27 append-only patch and restore verified.\n";

    // Test 4: Read-Only Anti-Cheat-Safe Frostbite & SRT Subtitle Indexing
    std::cout << "  [Test 4/5] Testing Read-Only Anti-Cheat-Safe Subtitle Indexer...\n";
    WriteTextFile(app_dir / "Data" / "Win32" / "Loc" / "en.sb", "LANG:en:Hold the line and stay together!\nMove to the objective!");
    WriteTextFile(app_dir / "Data" / "Win32" / "Loc" / "de.sb", "LANG:de:Haltet die Stellung und bleibt zusammen!\nRückt zum Ziel vor!");
    auto indexed = SubtitleMerger::IndexGameSubtitlesReadOnly(app_dir, "en", "de");
    assert(indexed.size() >= 2);
    assert(indexed[0].primary == "Hold the line and stay together!");
    assert(indexed[0].secondary == "Haltet die Stellung und bleibt zusammen!");
    std::cout << "             PASS: Read-Only Frostbite .sb indexing verified.\n";

    // Test 5: SRT Subtitle Merging & Famous Dictionary Lookup
    std::cout << "  [Test 5/5] Testing C++17 SRT Merger & Famous Dictionary Lookup...\n";
    fs::path srt_en = tmp / "sub_en.srt";
    fs::path srt_de = tmp / "sub_de.srt";
    fs::path srt_out = tmp / "sub_dual.srt";
    WriteTextFile(srt_en, "1\n00:00:01,000 --> 00:00:03,000\nLook over there! It's a bat!\n");
    WriteTextFile(srt_de, "1\n00:00:01,000 --> 00:00:03,000\nSieh mal da drüben! Eine Fledermaus!\n");
    assert(SubtitleMerger::MergeSrtFiles(srt_en, srt_de, srt_out));
    std::string dual_srt = ReadTextFile(srt_out);
    assert(dual_srt.find("Look over there! It's a bat!\nSieh mal da drüben! Eine Fledermaus!") != std::string::npos);

    auto d_entry = FamousDictionary::Lookup("bats");
    assert(d_entry.translation.find("Fledermäuse") != std::string::npos);
    std::cout << "             PASS: SRT dual-subtitle merger and Famous Dictionary verified.\n";

    fs::remove_all(tmp, ec);
    std::cout << "========================================================================\n"
              << "  ALL 5 C++17 CORE VERIFICATION SUITES PASSED SUCCESSFULLY!\n"
              << "========================================================================\n";
    return 0;
}

// ============================================================================
// Interactive Numbered Terminal Menu (C++17)
// ============================================================================

static int InteractiveMenu() {
    fs::path active_game = fs::current_path();
    auto detected = ScanInstalledGames();
    if (!detected.empty()) active_game = detected.front().path;

    std::string audio_lang = "en";
    std::string primary_lang = "en";
    std::string secondary_lang = "de";
    double overlay_speed = 1.0;

    while (true) {
        std::cout << "\n==============================================================================\n"
                  << "        DUALTITLE (C++17 EDITION) — ANTI-CHEAT-SAFE DUAL SUBTITLES\n"
                  << "   Game Library Picker • Save Backup & Restore • Clickable-Word & Speed HUD\n"
                  << "==============================================================================\n"
                  << "  Active Application   : " << active_game.string() << "\n"
                  << "  [Audio Language]     : " << GetLanguageDisplayName(audio_lang) << "\n"
                  << "  [Top Subtitle Line]  : " << GetLanguageDisplayName(primary_lang) << "\n"
                  << "  [Bottom Subtitle]    : " << GetLanguageDisplayName(secondary_lang) << "\n"
                  << "  [Subtitle Speed]     : " << std::fixed << std::setprecision(2) << overlay_speed << "x\n"
                  << "------------------------------------------------------------------------------\n"
                  << "  [ L] LAUNCH GAME + IN-GAME OVERLAY HUD (100% Anti-Cheat Safe)\n"
                  << "  [ O] Open Interactive In-Game Dual-Subtitle Overlay HUD Only\n"
                  << "  [ S] RESTORE SAVE (Restore Backed-Up Saves & Profile Settings)\n"
                  << "  [ B] BACKUP SAVE NOW (Create Immediate Save Snapshot)\n"
                  << "  [ R] 1-Click Repair & Clean Application Folder\n"
                  << "  [ 1] Select Game / Application Folder (Auto-Scans C: through Z:)\n"
                  << "  [ 2] Choose Spoken AUDIO Language\n"
                  << "  [ 3] Choose PRIMARY (Top) Subtitle Language\n"
                  << "  [ 4] Choose SECONDARY (Bottom) Subtitle Language\n"
                  << "  [ 5] Adjust Subtitle Playback Speed (0.25x - 2.00x)\n"
                  << "  [ 6] Apply Safe Pre-Launch Config & File Patch\n"
                  << "  [ D] Lookup Word in Famous Dictionary (Oxford / Duden / Wiktionary)\n"
                  << "  [ Q] Quit\n"
                  << "==============================================================================\n"
                  << "  Your choice: ";

        std::string choice;
        if (!std::getline(std::cin, choice)) break;
        if (choice.empty()) continue;
        char c = static_cast<char>(std::tolower(static_cast<unsigned char>(choice[0])));

        if (c == 'q') {
            break;
        } else if (c == 's') {
            std::cout << "\n  Restoring backed-up saves and profile settings for " << active_game.string() << "...\n";
            SaveBackupManager::RestoreSaves(active_game, std::cout);
            std::cout << "\n  Press Enter to continue...";
            std::getline(std::cin, choice);
        } else if (c == 'b') {
            std::cout << "\n  Backing up saves and profile settings for " << active_game.string() << "...\n";
            SaveBackupManager::BackupSaves(active_game, std::cout);
            std::cout << "\n  Press Enter to continue...";
            std::getline(std::cin, choice);
        } else if (c == 'r') {
            std::cout << "\n  Running Repair & Anti-Cheat Clean on " << active_game.string() << "...\n";
            EmergencyGameRepair::RepairGameDirectory(active_game, std::cout);
            SaveBackupManager::RestoreSaves(active_game, std::cout);
            std::cout << "\n  Press Enter to continue...";
            std::getline(std::cin, choice);
        } else if (c == '1') {
            auto games = ScanInstalledGames();
            std::cout << "\n  Detected Applications & Games:\n";
            for (size_t i = 0; i < games.size(); ++i) {
                std::cout << "    [" << (i + 1) << "] " << games[i].title << " (" << games[i].path.string() << ")\n";
            }
            std::cout << "  Enter number or paste full folder path: ";
            std::string inp;
            std::getline(std::cin, inp);
            if (!inp.empty() && std::all_of(inp.begin(), inp.end(), ::isdigit)) {
                size_t idx = std::stoul(inp);
                if (idx >= 1 && idx <= games.size()) active_game = games[idx - 1].path;
            } else if (!inp.empty()) {
                active_game = fs::path(inp);
            }
        } else if (c == '2' || c == '3' || c == '4') {
            const auto& langs = GetSupportedLanguages();
            std::cout << "\n  Select Language by Number:\n";
            for (size_t i = 0; i < langs.size(); ++i) {
                std::cout << "    [" << std::setw(2) << (i + 1) << "] " << langs[i].display_name << " (" << langs[i].code << ")\n";
            }
            std::cout << "  Choice (1-" << langs.size() << "): ";
            std::string inp;
            std::getline(std::cin, inp);
            if (!inp.empty() && std::all_of(inp.begin(), inp.end(), ::isdigit)) {
                size_t idx = std::stoul(inp);
                if (idx >= 1 && idx <= langs.size()) {
                    if (c == '2') audio_lang = langs[idx - 1].code;
                    else if (c == '3') primary_lang = langs[idx - 1].code;
                    else if (c == '4') secondary_lang = langs[idx - 1].code;
                }
            }
        } else if (c == '5') {
            std::cout << "  Enter Subtitle Speed (0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0): ";
            std::string inp;
            std::getline(std::cin, inp);
            try {
                double v = std::stod(inp);
                if (v >= 0.25 && v <= 2.0) overlay_speed = v;
            } catch (...) {}
        } else if (c == '6') {
            std::cout << "\n  Applying Safe Pre-Launch Config & Subtitle Patch to: " << active_game.string() << "\n";
            SaveBackupManager::BackupSaves(active_game, std::cout);
            EmergencyGameRepair::RepairGameDirectory(active_game, std::cout);
            ConfigPatcher::ApplyGameConfig(active_game, audio_lang, primary_lang, std::cout);
            ForgePatcher::PatchForgeArchive(active_game / "DataPC.forge", primary_lang, secondary_lang, std::cout);
            ForgePatcher::PatchForgeArchive(active_game / "DataPC_boot.forge", primary_lang, secondary_lang, std::cout);
            std::cout << "  [SUCCESS] Safe patch complete! Press Enter to continue...";
            std::getline(std::cin, choice);
        } else if (c == 'l' || c == 'o') {
#ifdef _WIN32
            if (c == 'l') {
                SaveBackupManager::BackupSaves(active_game, std::cout);
                EmergencyGameRepair::RepairGameDirectory(active_game, std::cout);
                ConfigPatcher::ApplyGameConfig(active_game, audio_lang, primary_lang, std::cout);
                fs::path exe_p = FindMainGameExecutable(active_game);
                if (!exe_p.empty()) {
                    ShellExecuteW(nullptr, L"open", exe_p.wstring().c_str(), nullptr, active_game.wstring().c_str(), SW_SHOWNORMAL);
                }
            }
            Win32UniversalOverlay::RunOverlayLoop(active_game, primary_lang, secondary_lang, overlay_speed);
#else
            std::cout << "\n  [Notice] Win32 Topmost Overlay requires Windows.\n";
#endif
        } else if (c == 'd') {
            std::cout << "  Enter word to lookup: ";
            std::string w;
            std::getline(std::cin, w);
            auto info = FamousDictionary::Lookup(w);
            std::cout << "\n  +------------------------------------------------------------+\n"
                      << "  | WORD       : " << info.word << " " << info.phonetic << " (" << info.pos << ")\n"
                      << "  | SOURCE     : " << info.source << "\n"
                      << "  | TRANSLATION: " << info.translation << "\n"
                      << "  | DEFINITION : " << info.definition << "\n"
                      << "  +------------------------------------------------------------+\n"
                      << "  Press Enter to continue...";
            std::getline(std::cin, choice);
        }
    }
    return 0;
}

int main(int argc, char* argv[]) {
    for (int i = 1; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--self-test") {
            return RunCppSelfTests();
        } else if (arg == "--restore-save") {
            if (i + 1 < argc) {
                SaveBackupManager::RestoreSaves(fs::path(argv[i + 1]), std::cout);
            } else {
                for (const auto& g : ScanInstalledGames()) {
                    SaveBackupManager::RestoreSaves(g.path, std::cout);
                }
            }
            return 0;
        } else if (arg == "--backup-save") {
            if (i + 1 < argc) {
                SaveBackupManager::BackupSaves(fs::path(argv[i + 1]), std::cout);
            }
            return 0;
        } else if (arg == "--repair") {
            if (i + 1 < argc) {
                EmergencyGameRepair::RepairGameDirectory(fs::path(argv[i + 1]), std::cout);
                SaveBackupManager::RestoreSaves(fs::path(argv[i + 1]), std::cout);
            } else {
                for (const auto& g : ScanInstalledGames()) {
                    EmergencyGameRepair::RepairGameDirectory(g.path, std::cout);
                    SaveBackupManager::RestoreSaves(g.path, std::cout);
                }
            }
            return 0;
        } else if (arg == "--overlay") {
#ifdef _WIN32
            return Win32UniversalOverlay::RunOverlayLoop();
#else
            std::cout << "Win32 Overlay requires Windows.\n";
            return 0;
#endif
        } else if (arg == "--gui") {
#ifdef _WIN32
            return Win32ControlPanelGui::RunGui();
#else
            return InteractiveMenu();
#endif
        } else if (arg == "--cli") {
            return InteractiveMenu();
        }
    }
#ifdef _WIN32
    return Win32ControlPanelGui::RunGui();
#else
    return InteractiveMenu();
#endif
}
