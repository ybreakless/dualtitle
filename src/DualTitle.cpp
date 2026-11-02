/**
 * DualTitle.cpp -- Main C++17 Native Application for DualTitle ("Aurora" v5)
 * (Universal Anti-Cheat-Safe Dual-Subtitles, Audio Controller, Save Manager & Live Overlay)
 *
 * Features:
 *   1. [NATIVE WIN32 "AURORA" DARK GUI (`--gui` or default on Windows)]:
 *      Modern minimal DPI-aware control panel (src/DualTitleTheme.hpp design system):
 *      rounded cards, flat owner-drawn buttons with hover states, dark-styled combos,
 *      auto game library scan on a background thread (C:-Z:), 1-Click "Launch Game +
 *      Overlay HUD", and 1-Click "Restore Save".
 *   2. [100% ANTI-CHEAT SAFE / ZERO INJECTION]:
 *      Never injects DLLs or opens foreign process handles. Cleans any legacy `.utoc`/`.ucas`/
 *      `.pak` or `ue4ss` files before launch so every game opens natively without flags.
 *   3. [IN-GAME INTERACTIVE OVERLAY HUD (`--overlay`)]:
 *      Displays Primary (Top in Gold #FFD700) + Secondary (Bottom in Ice-White #E2E8F0)
 *      subtitles with clickable words for instant Dictionary definitions, `- Spd / + Spd`
 *      speed controls, `Pause (ESC)`, `Borderless`, and `Restore Save`.
 *   4. [UNIVERSAL SAVE BACKUP & RESTORE (`--restore-save` / `--backup-save`)]:
 *      Automatically protects user save files (`Saved/SaveGames`, `PROF_SAVE*`, `Saves`,
 *      `*.sav`, `*.ini`) and restores them with 1 click.
 */

#include "DualTitleEngine.hpp"
#include "DualTitleConfig.hpp"
#include "DualTitleDictService.hpp"
#include "DualTitleTheme.hpp"
#include "DualTitleOverlay.hpp"
#include <cassert>
#include <thread>

using namespace DualTitle;

// ============================================================================
// Universal Multi-Drive Game & Application Scanner (C: through Z:)
// ============================================================================

struct DetectedGame {
    std::string title;
    fs::path path;
    std::string source; // "steam", "ea", "scan", etc.
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

    auto add_if_valid = [&](const fs::path& p, const std::string& source = "scan") {
        if (!LooksLikeApplicationDir(p)) return;
        std::string abs_str = fs::weakly_canonical(p, ec).string();
        if (seen.insert(abs_str).second) {
            std::string title = p.filename().string();
            if (title.empty()) title = abs_str;
            found.push_back({title, p, source});
        }
    };

    // --- Steam libraryfolders.vdf parser ---
    auto scanSteamLibrary = [&](const fs::path& steam_root) {
        fs::path vdf_path = steam_root / "steamapps" / "libraryfolders.vdf";
        if (!fs::exists(vdf_path, ec)) return;
        std::string vdf = ReadTextFile(vdf_path);
        // Very simple VDF parser for "libraryfolders" { "0" { "path" "C:\\Games" } ... }
        std::regex path_regex("\"path\"\\s+\"([^\"]+)\"");
        std::smatch match;
        std::string::const_iterator search_start(vdf.cbegin());
        while (std::regex_search(search_start, vdf.cend(), match, path_regex)) {
            fs::path lib_path(match[1].str());
            fs::path common = lib_path / "steamapps" / "common";
            if (fs::is_directory(common, ec)) {
                for (const auto& item : fs::directory_iterator(common, ec)) {
                    if (item.is_directory(ec)) add_if_valid(item.path(), "steam");
                }
            }
            // Also read appmanifest_*.acf for game names
            for (const auto& acf : fs::directory_iterator(lib_path / "steamapps", ec)) {
                if (!acf.is_regular_file(ec)) continue;
                std::string fn = acf.path().filename().string();
                if (fn.rfind("appmanifest_", 0) == 0 && fn.size() > 12 && fn.substr(fn.size() - 4) == ".acf") {
                    std::string acf_text = ReadTextFile(acf.path());
                    std::regex name_regex("\"name\"\\s+\"([^\"]+)\"");
                    std::regex install_regex("\"installdir\"\\s+\"([^\"]+)\"");
                    std::smatch nm, im;
                    if (std::regex_search(acf_text, nm, name_regex) && std::regex_search(acf_text, im, install_regex)) {
                        fs::path game_path = common / im[1].str();
                        if (fs::is_directory(game_path, ec)) add_if_valid(game_path, "steam:" + nm[1].str());
                    }
                }
            }
            search_start = match.suffix().first;
        }
    };

    // --- EA App / Origin manifest parser ---
    auto scanEALibrary = [&](const fs::path& ea_root) {
        // EA App stores manifests in EAAppData/Local/EA/EA Desktop/Installed
        // Origin stores in Origin Games or Program Files/Origin Games
        std::vector<fs::path> ea_roots = {
            ea_root / "EA Games",
            ea_root / "Origin Games",
            ea_root / "Electronic Arts" / "EA Games",
            ea_root / "Electronic Arts" / "Origin Games"
        };
        if (const char* la = std::getenv("LOCALAPPDATA")) {
            ea_roots.push_back(fs::path(la) / "EA" / "EA Desktop" / "Installed");
            ea_roots.push_back(fs::path(la) / "Origin" / "Installed");
        }
        for (const auto& eroot : ea_roots) {
            if (!fs::is_directory(eroot, ec)) continue;
            for (const auto& item : fs::directory_iterator(eroot, ec)) {
                if (item.is_directory(ec)) add_if_valid(item.path(), "ea");
            }
        }
    };

    // --- Drive enumeration ---
    std::vector<std::string> drives;
#ifdef _WIN32
    for (char d : std::string("CDEFGHIJKLMNOPQRSTUVWXYZ")) {
        std::string root = std::string(1, d) + ":\\";
        if (fs::is_directory(root, ec)) drives.push_back(root);
    }
#else
    drives.push_back("/");
#endif

    // --- Known library paths per drive ---
    for (const auto& drv : drives) {
        fs::path dpath(drv);
        // Steam default locations
        scanSteamLibrary(dpath / "Program Files (x86)" / "Steam");
        scanSteamLibrary(dpath / "Program Files" / "Steam");
        scanSteamLibrary(dpath / "SteamLibrary");
        // EA/Origin
        scanEALibrary(dpath / "Program Files (x86)" / "Origin Games");
        scanEALibrary(dpath / "Program Files" / "EA Games");
        scanEALibrary(dpath / "Origin Games");
        scanEALibrary(dpath / "EA Games");
        // Other known launchers
        std::vector<fs::path> other_roots = {
            dpath / "Games",
            dpath / "GOG Games",
            dpath / "Epic Games",
            dpath / "Program Files (x86)" / "Ubisoft" / "Ubisoft Game Launcher" / "games",
            dpath / "Ubisoft Game Launcher" / "games",
            dpath / "Program Files (x86)" / "GOG Galaxy" / "Games",
            dpath / "Program Files" / "GOG Galaxy" / "Games",
            dpath / "Program Files (x86)" / "Epic Games",
            dpath / "Program Files" / "Epic Games"
        };
        for (const auto& oroot : other_roots) {
            if (fs::is_directory(oroot, ec)) {
                for (const auto& item : fs::directory_iterator(oroot, ec)) {
                    if (item.is_directory(ec)) add_if_valid(item.path(), "scan");
                }
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
                    add_if_valid(item.path(), "scan");
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
// Native Win32 "Aurora" Dark Control Panel (Modern Minimal, DPI-Aware)
// ============================================================================

#ifdef _WIN32
#include <commdlg.h>
#include <shlobj.h>

#include <uxtheme.h>
#pragma comment(lib, "uxtheme.lib")

class Win32ControlPanelGui {
public:
    enum : int {
        ID_COMBO_GAME = 1001,
        ID_EDIT_PATH = 1002,
        ID_COMBO_AUDIO = 1004,
        ID_COMBO_PRIM = 1005,
        ID_COMBO_SEC = 1006,
        ID_COMBO_SPEED = 1007,
        ID_BTN_LAUNCH_ALL = 1101,
        ID_BTN_OVERLAY_ONLY = 1102,
        ID_BTN_APPLY_ONLY = 1103,
        ID_BTN_RESTORE_SAVE = 1104,
        ID_BTN_BACKUP_SAVE = 1105,
        ID_BTN_REPAIR = 1106,
        ID_BTN_BROWSE = 1107
    };

    enum Tone { ToneInfo, ToneOk, ToneWarn };

    // ---- UI state -----------------------------------------------------------
    static inline std::vector<DetectedGame> games_list;
    static inline bool scan_ready = false;
    static inline HWND hComboGame = nullptr;
    static inline HWND hEditPath = nullptr;
    static inline HWND hComboAudio = nullptr;
    static inline HWND hComboPrim = nullptr;
    static inline HWND hComboSec = nullptr;
    static inline HWND hComboSpeed = nullptr;
    static inline Theme::FontSet fonts;
    static inline int dpi = 96;
    static inline std::vector<Theme::FlatBtn> buttons;
    static inline std::map<int, Theme::BtnState> btn_state;
    static inline std::wstring status_text =
        L"Ready -- 100% zero-injection anti-cheat-safe mode. Saves are backed up before every launch.";
    static inline Tone status_tone = ToneInfo;
    static inline bool mouse_tracking = false;
    static inline HBRUSH bEditBg = nullptr;
    static inline HBRUSH bListBg = nullptr;
    static inline const UINT WM_APP_SCANDONE = WM_APP + 1;

    // ---- Layout (logical 96-dpi design grid, scaled on demand) ---------------
    struct Layout {
        RECT card1{}, card2{}, card3{};
        RECT rComboGame{}, rEdit{}, rBrowse{}, rComboAudio{}, rComboSpeed{},
             rComboPrim{}, rComboSec{}, rLaunch{}, rActions[5]{}, rVersion{};
        RECT rStatusDot{}, rStatusText{};
        RECT micro1{}, micro2{}, micro3{}, micro4{}; // field captions in card 2
        RECT section1{}, section2{}, section3{}, footer{};
    };

    static Layout GetLayout() {
        auto R = [](int x, int y, int w, int h) -> RECT { RECT r{x, y, x + w, y + h}; return r; };
        auto s = [&](int v) { return Theme::S(v, dpi == 0 ? 96 : dpi); };
        Layout L;

        L.card1 = R(s(20), s(88), s(640), s(114));
        L.card2 = R(s(20), L.card1.bottom + s(14), s(640), s(138));
        L.card3 = R(s(20), L.card2.bottom + s(14), s(640), s(118));

        // Card 1 -- game library
        L.rComboGame = R(L.card1.left + s(16), L.card1.top + s(36), s(608), s(26));
        L.rEdit = R(L.card1.left + s(16), L.rComboGame.bottom + s(12), s(496), s(26));
        L.rBrowse = R(L.rEdit.right + s(8), L.rEdit.top, s(102), s(26));

        // Card 2 -- languages & playback (two columns, caption above each field)
        int colB = L.card2.left + s(320);
        L.rComboAudio = R(L.card2.left + s(16), L.card2.top + s(42), s(288), s(26));
        L.rComboSpeed = R(colB, L.card2.top + s(42), s(288), s(26));
        L.rComboPrim = R(L.card2.left + s(16), L.card2.top + s(96), s(288), s(26));
        L.rComboSec = R(colB, L.card2.top + s(96), s(288), s(26));
        L.micro1 = R(L.rComboAudio.left, L.rComboAudio.top - s(18), s(180), s(14));
        L.micro2 = R(L.rComboSpeed.left, L.micro1.top, s(180), s(14));
        L.micro3 = R(L.rComboPrim.left, L.rComboPrim.top - s(18), s(220), s(14));
        L.micro4 = R(L.rComboSec.left, L.micro3.top, s(220), s(14));

        // Card 3 -- actions
        L.rLaunch = R(L.card3.left + s(16), L.card3.top + s(16), s(608), s(46));
        int row_w = s(608);
        int gap = s(8);
        int each = (row_w - 4 * gap) / 5;          // last button absorbs the rounding remainder
        int last = row_w - 4 * (each + gap);
        int ax = L.card3.left + s(16);
        for (int i = 0; i < 5; ++i) {
            L.rActions[i] = R(ax, L.card3.top + s(76), i == 4 ? last : each, s(30));
            ax += each + gap;
        }

        // Status + footer
        L.rStatusDot = R(s(26), L.card3.bottom + s(24), s(9), s(9));
        L.rStatusText = R(s(46), L.card3.bottom + s(17), s(560), s(20));
        L.footer = R(s(20), L.rStatusText.bottom + s(8), s(640), s(14));

        // Header version pill
        L.rVersion = R(s(680) - s(76), s(26), s(56), s(21));

        L.section1 = R(L.card1.left + s(16), L.card1.top + s(11), s(300), s(16));
        L.section2 = R(L.card2.left + s(16), L.card2.top + s(8), s(300), s(14));
        L.section3 = R(L.card3.left + s(16), L.card3.top + s(12), s(300), s(16));
        return L;
    }

    /** Rebuilds the region-drawn button list from the current layout. */
    static void BuildButtons() {
        Layout L = GetLayout();
        buttons.clear();
        buttons.push_back({ID_BTN_BROWSE, L.rBrowse, L"Browse...", Theme::BtnGhost});
        buttons.push_back({ID_BTN_LAUNCH_ALL, L.rLaunch, L"Launch Game + Overlay HUD", Theme::BtnPrimary});
        const wchar_t* labels[5] = {
            L"Overlay Only", L"Apply Config", L"Backup Save", L"Restore Save", L"Repair & Clean"
        };
        const int ids[5] = {
            ID_BTN_OVERLAY_ONLY, ID_BTN_APPLY_ONLY, ID_BTN_BACKUP_SAVE,
            ID_BTN_RESTORE_SAVE, ID_BTN_REPAIR
        };
        for (int i = 0; i < 5; ++i) {
            buttons.push_back({ids[i], L.rActions[i], labels[i],
                ids[i] == ID_BTN_RESTORE_SAVE ? Theme::BtnTeal : Theme::BtnGhost});
        }
    }

    static Theme::FlatBtn* HitButton(const POINT& pt) {
        for (auto& b : buttons) {
            if (PtInRect(&b.rc, pt)) return &b;
        }
        return nullptr;
    }

    static void EnsureTrackMouse(HWND hwnd) {
        if (mouse_tracking) return;
        TRACKMOUSEEVENT tme{sizeof(tme), TME_LEAVE, hwnd, 0};
        if (TrackMouseEvent(&tme)) mouse_tracking = true;
    }

    static void SetStatus(HWND hwnd, const std::wstring& text, Tone tone) {
        status_text = text;
        status_tone = tone;
        InvalidateRect(hwnd, nullptr, TRUE);
    }

    // ---- Combo helpers -------------------------------------------------------
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

    /** Owner-draw painting for every combo (closed selection box + list rows). */
    static void DrawComboBoxItem(const DRAWITEMSTRUCT* dis) {
        Theme::BootGdiplus();
        HDC hdc = dis->hDC;
        RECT rc = dis->rcItem;
        bool edit_area = (dis->itemState & ODS_COMBOBOXEDIT) != 0;

        // Item text
        std::wstring txt;
        UINT item_id = edit_area
            ? (UINT)SendMessageW(dis->hwndItem, CB_GETCURSEL, 0, 0)
            : dis->itemID;
        int len = (int)SendMessageW(dis->hwndItem, CB_GETLBTEXTLEN, item_id, 0);
        if (len > 0) {
            txt.assign(static_cast<size_t>(len) + 1, L'\0');
            SendMessageW(dis->hwndItem, CB_GETLBTEXT, item_id, (LPARAM)txt.data());
            txt.resize(static_cast<size_t>(len));
        }

        if (edit_area) {
            // Full dark fill (square) -- the parent draws the rounded ring around the field
            HBRUSH fill = CreateSolidBrush(Theme::Inner);
            FillRect(hdc, &rc, fill);
            DeleteObject(fill);
        } else {
            bool sel = (dis->itemState & ODS_SELECTED) != 0;
            HBRUSH fill = CreateSolidBrush(sel ? Theme::ListSel : Theme::Inner);
            FillRect(hdc, &rc, fill);
            DeleteObject(fill);
        }

        if (!txt.empty()) {
            // While scanning the game combo shows a faint placeholder et al.
            bool faint = (!scan_ready && dis->hwndItem == hComboGame);
            COLORREF tx = faint ? Theme::TextFaint
                        : edit_area ? Theme::TextBody
                        : (dis->itemState & ODS_SELECTED) ? Theme::Accent : Theme::TextBody;
            RECT trc{rc.left + Theme::S(10, dpi), rc.top, rc.right, rc.bottom};
            HFONT old = static_cast<HFONT>(SelectObject(hdc, fonts.body));
            SetBkMode(hdc, TRANSPARENT);
            SetTextColor(hdc, tx);
            DrawTextW(hdc, txt.c_str(), -1, &trc, DT_LEFT | DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS | DT_NOPREFIX);
            SelectObject(hdc, old);
        }
        // (The chevron lives on the cover static that sits over the combo's native button)
    }

    // ---- Actions (same engine calls as v4 -- zero behavior change) ------------
    static void RunButton(HWND hwnd, int id) {
        BuildButtons();

        // Read the path as UTF-16 directly so every code page converts cleanly
        int plen = GetWindowTextLengthW(hEditPath);
        std::wstring path_w(static_cast<size_t>(plen) + 1, L'\0');
        GetWindowTextW(hEditPath, path_w.data(), plen + 1);
        path_w.resize(static_cast<size_t>(plen));
        fs::path gdir = path_w.empty() ? fs::path() : fs::path(path_w);

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
            SetStatus(hwnd, L"Restore complete -- " + std::to_wstring(cnt) +
                      L" save/profile file(s) restored & verified.", cnt > 0 ? ToneOk : ToneInfo);
            MessageBoxW(hwnd, L"Restore Save complete.", L"DualTitle", MB_OK | MB_ICONINFORMATION);
        } else if (id == ID_BTN_BACKUP_SAVE) {
            std::ostringstream log_ss;
            int cnt = SaveBackupManager::BackupSaves(gdir, log_ss);
            SetStatus(hwnd, L"Backup complete -- " + std::to_wstring(cnt) +
                      L" save/profile file(s) secured to .dualtitle_save_backup.", ToneOk);
            MessageBoxW(hwnd, L"Backup Save complete.", L"DualTitle", MB_OK | MB_ICONINFORMATION);
        } else if (id == ID_BTN_REPAIR) {
            std::ostringstream log_ss;
            int fixed_n = EmergencyGameRepair::RepairGameDirectory(gdir, log_ss);
            SaveBackupManager::RestoreSaves(gdir, log_ss);
            SetStatus(hwnd, L"Repair complete -- " + std::to_wstring(fixed_n) +
                      L" file(s) cleaned & original saves verified.", ToneOk);
            MessageBoxW(hwnd, L"Repair & Clean complete.", L"DualTitle", MB_OK | MB_ICONINFORMATION);
        } else if (id == ID_BTN_APPLY_ONLY) {
            std::ostringstream log_ss;
            EmergencyGameRepair::RepairGameDirectory(gdir, log_ss);
            int idx = static_cast<int>(SendMessageW(hComboGame, CB_GETCURSEL, 0, 0));
            const GameProfile* profile = (idx >= 0 && static_cast<size_t>(idx) < games_list.size())
                ? MatchGameProfile(games_list[static_cast<size_t>(idx)].title) : nullptr;
            ConfigPatcher::ApplyGameConfig(gdir, a_lang, p_lang, profile, log_ss);
            SetStatus(hwnd, L"Safe pre-game audio/subtitle config applied (saves backed up automatically).", ToneOk);
        } else if (id == ID_BTN_OVERLAY_ONLY) {
            SetStatus(hwnd, L"Overlay HUD running -- return to your game and press ALT+F8 to hide/show.", ToneInfo);
            ShowWindow(hwnd, SW_MINIMIZE);
            Win32UniversalOverlay::RunOverlayLoop(gdir, p_lang, s_lang, spd);
            SetStatus(hwnd, L"Overlay session ended.", ToneInfo);
        } else if (id == ID_BTN_LAUNCH_ALL) {
            std::ostringstream log_ss;
            // 1. Back up saves and clean any foreign files so anti-cheat is 100% happy
            SaveBackupManager::BackupSaves(gdir, log_ss);
            EmergencyGameRepair::RepairGameDirectory(gdir, log_ss, false); // dry_run=false for actual launch
            ConfigPatcher::ApplyGameConfig(gdir, a_lang, p_lang, nullptr, log_ss);

            // 2. Launch the game -- prefer Steam/EA deep link if profile has one
            int idx = static_cast<int>(SendMessageW(hComboGame, CB_GETCURSEL, 0, 0));
            const GameProfile* profile = (idx >= 0 && static_cast<size_t>(idx) < games_list.size())
                ? MatchGameProfile(games_list[static_cast<size_t>(idx)].title) : nullptr;

            bool launched = false;
            if (profile && !profile->steam_appid.empty()) {
                std::wstring steam_url = L"steam://rungameid/" + Win32UniversalOverlay::Utf8ToWide(profile->steam_appid);
                launched = (ShellExecuteW(nullptr, L"open", steam_url.c_str(), nullptr, nullptr, SW_SHOWNORMAL) > (HINSTANCE)32);
                if (launched) log_ss << "    [Launcher] Launched via Steam: " << profile->steam_appid << "\n";
            }
            if (!launched && profile && profile->launcher_hint == "ea") {
                // EA App deep link: link2ea://launchgame?productId=<id> (requires product ID)
                // Fallback: try to find ea_emu.ini or use direct exe
            }
            if (!launched) {
                fs::path exe_path = FindMainGameExecutable(gdir);
                if (!exe_path.empty()) {
                    ShellExecuteW(nullptr, L"open", exe_path.wstring().c_str(), nullptr, gdir.wstring().c_str(), SW_SHOWNORMAL);
                    launched = true;
                    log_ss << "    [Launcher] Launched direct: " << exe_path.string() << "\n";
                } else {
                    SetStatus(hwnd, L"No game executable found in that folder -- check the path or Browse again.", ToneWarn);
                }
            }

            // 3. Minimize control panel and start the Anti-Cheat-Safe In-Game Overlay HUD
            ShowWindow(hwnd, SW_MINIMIZE);
            Win32UniversalOverlay::RunOverlayLoop(gdir, p_lang, s_lang, spd);
            SetStatus(hwnd, L"Overlay session ended.", ToneInfo);
        }
    }

    // ---- Window procedure ----------------------------------------------------
    static LRESULT CALLBACK GuiWndProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam) {
        switch (msg) {
            case WM_CREATE: {
                dpi = Theme::WindowDpi(hwnd);
                Theme::MakeFontSet(dpi, fonts);
                bEditBg = CreateSolidBrush(Theme::Inner);
                bListBg = CreateSolidBrush(Theme::Inner);

                Layout L = GetLayout();
                auto make_combo = [&](RECT rc, HMENU id) -> HWND {
                    HWND h = CreateWindowW(L"COMBOBOX", L"",
                        WS_CHILD | WS_VISIBLE | WS_TABSTOP | CBS_DROPDOWNLIST |
                        CBS_OWNERDRAWFIXED | CBS_HASSTRINGS | WS_VSCROLL,
                        rc.left, rc.top, rc.right - rc.left, rc.bottom - rc.top,
                        hwnd, id, nullptr, nullptr);
                    SendMessageW(h, WM_SETFONT, reinterpret_cast<WPARAM>(fonts.body), TRUE);
                    SendMessageW(h, CB_SETITEMHEIGHT, 0, static_cast<LPARAM>(
                        static_cast<DWORD>(rc.bottom - rc.top)));
                    SetWindowTheme(h, L"DarkMode_Explorer", nullptr);
                    // Clip 1px inset -- hides the combo's classic light frame lines
                    HRGN inset = CreateRectRgn(1, 1, rc.right - rc.left - 1, rc.bottom - rc.top - 1);
                    if (inset) SetWindowRgn(h, inset, TRUE);
                    return h;
                };

                hComboGame = make_combo(L.rComboGame, reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(ID_COMBO_GAME)));

                hEditPath = CreateWindowExW(0, L"EDIT", L"",
                    WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL,
                    L.rEdit.left, L.rEdit.top, L.rEdit.right - L.rEdit.left,
                    L.rEdit.bottom - L.rEdit.top, hwnd,
                    reinterpret_cast<HMENU>(static_cast<INT_PTR>(ID_EDIT_PATH)), nullptr, nullptr);
                SendMessageW(hEditPath, WM_SETFONT, reinterpret_cast<WPARAM>(fonts.body), TRUE);
                SetWindowTheme(hEditPath, L"DarkMode_Explorer", nullptr);

                hComboAudio = make_combo(L.rComboAudio, reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(ID_COMBO_AUDIO)));
                hComboSpeed = make_combo(L.rComboSpeed, reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(ID_COMBO_SPEED)));
                hComboPrim = make_combo(L.rComboPrim, reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(ID_COMBO_PRIM)));
                hComboSec = make_combo(L.rComboSec, reinterpret_cast<HMENU>(
                    static_cast<INT_PTR>(ID_COMBO_SEC)));

                // Owner-drawn chevron covers over each combo's native (light) drop button
                auto cover_combo_button = [&](const RECT& field, INT_PTR id) {
                    RECT br{};
                    br.left = field.right - Theme::S(21, dpi);
                    br.top = field.top;
                    br.right = field.right;
                    br.bottom = field.bottom;
                    HWND cov = CreateWindowExW(0, L"STATIC", L"",
                        WS_CHILD | WS_VISIBLE | SS_OWNERDRAW,
                        br.left, br.top, br.right - br.left, br.bottom - br.top,
                        hwnd, reinterpret_cast<HMENU>(id), nullptr, nullptr);
                    if (cov) {
                        HRGN rg = CreateRoundRectRgn(0, 0,
                            br.right - br.left + 1, br.bottom - br.top + 1,
                            Theme::S(6, dpi), Theme::S(6, dpi));
                        SetWindowRgn(cov, rg, TRUE);
                    }
                    return cov;
                };
                cover_combo_button(L.rComboGame, 1301);
                cover_combo_button(L.rComboAudio, 1302);
                cover_combo_button(L.rComboSpeed, 1303);
                cover_combo_button(L.rComboPrim, 1304);
                cover_combo_button(L.rComboSec, 1305);

                // Populate language + speed selectors
                const auto& langs = GetSupportedLanguages();
                auto fill_lang = [&](HWND hc, const char* def) {
                    int sel = 0;
                    for (size_t i = 0; i < langs.size(); ++i) {
                        std::wstring lbl = Win32UniversalOverlay::Utf8ToWide(
                            langs[i].display_name + "  *  " + langs[i].code);
                        SendMessageW(hc, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(lbl.c_str()));
                        if (langs[i].code == def) sel = static_cast<int>(i);
                    }
                    SendMessageW(hc, CB_SETCURSEL, sel, 0);
                };
                fill_lang(hComboAudio, "en");
                fill_lang(hComboPrim, "en");
                fill_lang(hComboSec, "de");

                const wchar_t* speed_labels[] = {
                    L"0.50x  *  Slow Study",
                    L"0.75x  *  Relaxed",
                    L"1.00x  *  Real-Time",
                    L"1.25x  *  Fast",
                    L"1.50x  *  Rapid",
                    L"2.00x  *  Double"
                };
                for (int i = 0; i < 6; ++i) {
                    SendMessageW(hComboSpeed, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(speed_labels[i]));
                }
                SendMessageW(hComboSpeed, CB_SETCURSEL, 2, 0);

                // Game combo placeholder until the background scan returns
                SendMessageW(hComboGame, CB_ADDSTRING, 0,
                    reinterpret_cast<LPARAM>(L"Scanning installed games (C: - Z:)..."));
                SendMessageW(hComboGame, CB_SETCURSEL, 0, 0);

                // Background game library scan -- UI never freezes
                std::thread([hwnd]() {
                    auto games = ScanInstalledGames();
                    auto* payload = new std::vector<DetectedGame>(std::move(games));
                    if (!PostMessageW(hwnd, WM_APP_SCANDONE, 0,
                                      reinterpret_cast<LPARAM>(payload))) {
                        delete payload;
                    }
                }).detach();
                return 0;
            }

            case WM_APP_SCANDONE: {
                auto* payload = reinterpret_cast<std::vector<DetectedGame>*>(lparam);
                if (!payload) break;
                SendMessageW(hComboGame, CB_RESETCONTENT, 0, 0);
                games_list = std::move(*payload);
                delete payload;
                scan_ready = true;

                for (const auto& g : games_list) {
                    std::wstring item = Win32UniversalOverlay::Utf8ToWide(g.title);
                    SendMessageW(hComboGame, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(item.c_str()));
                }
                if (!games_list.empty()) {
                    SendMessageW(hComboGame, CB_SETCURSEL, 0, 0);
                    SetWindowTextW(hEditPath, games_list.front().path.wstring().c_str());
                    SetStatus(hwnd, L"Found " + std::to_wstring(games_list.size()) +
                        L" installed game(s). Pick one, choose your languages, then launch.", ToneOk);
                } else {
                    std::wstring ph = L"No games auto-detected -- paste a folder above or Browse...";
                    SendMessageW(hComboGame, CB_ADDSTRING, 0, reinterpret_cast<LPARAM>(ph.c_str()));
                    SendMessageW(hComboGame, CB_SETCURSEL, 0, 0);
                    SetStatus(hwnd, L"No games found automatically -- paste any game folder path or use Browse...", ToneWarn);
                }
                InvalidateRect(hwnd, nullptr, TRUE);
                return 0;
            }

            case WM_COMMAND: {
                int id = LOWORD(wparam);
                int code = HIWORD(wparam);

                if (id == ID_COMBO_GAME && code == CBN_SELCHANGE && scan_ready) {
                    int idx = static_cast<int>(SendMessageW(hComboGame, CB_GETCURSEL, 0, 0));
                    if (idx >= 0 && static_cast<size_t>(idx) < games_list.size()) {
                        SetWindowTextW(hEditPath, games_list[static_cast<size_t>(idx)].path.wstring().c_str());
                    }
                    return 0;
                }
                return 0;
            }

            case WM_DRAWITEM: {
                auto* dis = reinterpret_cast<DRAWITEMSTRUCT*>(lparam);
                if (dis->CtlType == ODT_COMBOBOX) {
                    DrawComboBoxItem(dis);
                    return TRUE;
                }
                if (dis->CtlType == ODT_STATIC) {
                    // Dark pill + chevron cover over the native combo drop button
                    Theme::RoundRectFill(dis->hDC, dis->rcItem, Theme::S(6, dpi), Theme::Inner);
                    int r = Theme::S(7, dpi);
                    int cx = (dis->rcItem.left + dis->rcItem.right) / 2;
                    int cy = (dis->rcItem.top + dis->rcItem.bottom) / 2 - 1;
                    Gdiplus::Graphics g(dis->hDC);
                    g.SetSmoothingMode(Gdiplus::SmoothingModeAntiAlias);
                    COLORREF chev = (dis->CtlID == 1301) ? Theme::Accent : Theme::TextFaint;
                    Gdiplus::SolidBrush br(Gdiplus::Color(210,
                        GetRValue(chev), GetGValue(chev), GetBValue(chev)));
                    Gdiplus::PointF pts[3] = {
                        Gdiplus::PointF(float(cx - r / 2.0), float(cy - r / 4.0)),
                        Gdiplus::PointF(float(cx + r / 2.0), float(cy - r / 4.0)),
                        Gdiplus::PointF(float(cx), float(cy + r / 2.0))
                    };
                    g.FillPolygon(&br, pts, 3);
                    return TRUE;
                }
                break;
            }

            case WM_MEASUREITEM: {
                auto* mis = reinterpret_cast<MEASUREITEMSTRUCT*>(lparam);
                if (mis->CtlType == ODT_COMBOBOX) {
                    mis->itemHeight = static_cast<UINT>(Theme::S(26, dpi));
                    return TRUE;
                }
                break;
            }

            case WM_CTLCOLOREDIT: {
                HDC hdc = reinterpret_cast<HDC>(wparam);
                SetTextColor(hdc, Theme::TextBody);
                SetBkColor(hdc, Theme::Inner);
                return reinterpret_cast<LRESULT>(bEditBg);
            }
            case WM_CTLCOLORSTATIC: {
                HDC hdc = reinterpret_cast<HDC>(wparam);
                SetTextColor(hdc, Theme::TextBody);
                SetBkColor(hdc, Theme::Inner);
                return reinterpret_cast<LRESULT>(bEditBg);
            }
            case WM_CTLCOLORLISTBOX:
                return reinterpret_cast<LRESULT>(bListBg);
            case WM_CTLCOLORSCROLLBAR:
                return reinterpret_cast<LRESULT>(bListBg);

            case WM_MOUSEMOVE: {
                EnsureTrackMouse(hwnd);
                POINT pt{GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
                BuildButtons();
                for (auto& b : buttons) {
                    auto& st = btn_state[b.id];
                    bool hov = PtInRect(&b.rc, pt) != FALSE;
                    if (!hov) st.pressed = false;
                    if (st.hover != hov) {
                        st.hover = hov;
                        InvalidateRect(hwnd, &b.rc, TRUE);
                    }
                }
                return 0;
            }

            case WM_MOUSELEAVE: {
                mouse_tracking = false;
                for (auto& b : buttons) {
                    auto& st = btn_state[b.id];
                    if (st.hover || st.pressed) {
                        st.hover = false;
                        st.pressed = false;
                        InvalidateRect(hwnd, &b.rc, TRUE);
                    }
                }
                return 0;
            }

            case WM_LBUTTONDOWN: {
                BuildButtons();
                POINT pt{GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
                if (auto* b = HitButton(pt)) {
                    btn_state[b->id].pressed = true;
                    SetCapture(hwnd);
                    InvalidateRect(hwnd, &b->rc, TRUE);
                }
                return 0;
            }

            case WM_LBUTTONUP: {
                BuildButtons();
                POINT pt{GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
                auto* hit = HitButton(pt);
                ReleaseCapture();
                for (auto& b : buttons) {
                    auto& st = btn_state[b.id];
                    if (st.pressed) {
                        st.pressed = false;
                        InvalidateRect(hwnd, &b.rc, TRUE);
                        if (hit && hit->id == b.id) {
                            RunButton(hwnd, b.id);
                            break; // RunButton may enter the overlay loop
                        }
                    }
                }
                return 0;
            }

            case WM_SETCURSOR: {
                if (LOWORD(lparam) == HTCLIENT) {
                    POINT pt{};
                    GetCursorPos(&pt);
                    ScreenToClient(hwnd, &pt);
                    BuildButtons();
                    SetCursor(HitButton(pt)
                        ? LoadCursor(nullptr, IDC_HAND)
                        : LoadCursor(nullptr, IDC_ARROW));
                    return TRUE;
                }
                break;
            }

            case WM_PAINT: {
                PAINTSTRUCT ps;
                HDC hdc = BeginPaint(hwnd, &ps);
                Theme::BootGdiplus();
                RECT crc{};
                GetClientRect(hwnd, &crc);
                Layout L = GetLayout();
                BuildButtons();
                auto s = [&](int v) { return Theme::S(v, dpi); };

                // Window background
                HBRUSH bg = CreateSolidBrush(Theme::Window);
                FillRect(hdc, &crc, bg);
                DeleteObject(bg);

                // --- Header
                Win32UniversalOverlay::DrawDualTitleMiniLogo(hdc, s(24), s(24), s(44));
                Theme::DrawLabel(hdc, L"DualTitle", RECT{s(84), s(18), s(320), s(48)}, fonts.title, Theme::TextTitle);
                Theme::DrawLabel(hdc, L"Universal Dual Subtitles * Anti-Cheat-Safe Overlay * Dictionary * Save Guard",
                    RECT{s(84), s(48), s(520), s(68)}, fonts.sub, Theme::TextMuted);
                Theme::RoundRectFill(hdc, L.rVersion, s(10), Theme::GhostFill, 255, Theme::GhostBorder, 220);
                Theme::DrawLabel(hdc, L"v5.0", L.rVersion, fonts.section, Theme::Accent, 1,
                                 DT_CENTER | DT_SINGLELINE | DT_VCENTER);

                // --- Card 1: GAME LIBRARY
                Theme::RoundRectFill(hdc, L.card1, s(10), Theme::Card, 255, Theme::CardBorder, 230);
                Theme::DrawLabel(hdc, L"GAME LIBRARY", L.section1, fonts.section, Theme::TextFaint, 2);

                // Path edit ring (child sits inside; ring reads as a crisp border)
                Theme::RoundRectFill(hdc,
                    RECT{L.rEdit.left, L.rEdit.top - 1, L.rEdit.right + 1, L.rEdit.bottom + 1},
                    s(6), Theme::Card, 255, Theme::CardBorder, 255);

                // Rounded rings for every combo field (combos are clipped inside these)
                for (const RECT* fr : {&L.rComboGame, &L.rComboAudio, &L.rComboSpeed,
                                       &L.rComboPrim, &L.rComboSec}) {
                    Theme::RoundRectFill(hdc,
                        RECT{fr->left, fr->top - 1, fr->right + 1, fr->bottom + 1},
                        s(6), Theme::Inner, 255, Theme::CardBorder, 255);
                }

                // --- Card 2: LANGUAGES & PLAYBACK
                Theme::RoundRectFill(hdc, L.card2, s(10), Theme::Card, 255, Theme::CardBorder, 230);
                Theme::DrawLabel(hdc, L"LANGUAGES & PLAYBACK", L.section2, fonts.section, Theme::TextFaint, 2);
                Theme::DrawLabel(hdc, L"SPOKEN AUDIO", L.micro1, fonts.section, Theme::TextFaint, 1);
                Theme::DrawLabel(hdc, L"PLAYBACK SPEED", L.micro2, fonts.section, Theme::TextFaint, 1);
                Theme::DrawLabel(hdc, L"PRIMARY * TOP LINE", L.micro3, fonts.section, Theme::Gold, 1);
                Theme::DrawLabel(hdc, L"SECONDARY * BOTTOM LINE", L.micro4, fonts.section, Theme::IceWhite, 1);

                // --- Card 3: ACTIONS
                Theme::RoundRectFill(hdc, L.card3, s(10), Theme::Card, 255, Theme::CardBorder, 230);
                Theme::DrawLabel(hdc, L"ACTIONS", L.section3, fonts.section, Theme::TextFaint, 2);

                // --- Buttons (region-drawn on top of cards)
                for (const auto& b : buttons) {
                    Theme::DrawBtn(hdc, b, btn_state[b.id], dpi, fonts.btn);
                }

                // --- Status line
                COLORREF dot = status_tone == ToneOk ? Theme::StatusOk
                             : status_tone == ToneWarn ? Theme::StatusWarn : Theme::StatusInfo;
                Theme::FillCircle(hdc,
                    (L.rStatusDot.left + L.rStatusDot.right) / 2,
                    (L.rStatusDot.top + L.rStatusDot.bottom) / 2,
                    s(4), dot);
                HFONT fnt_old = static_cast<HFONT>(SelectObject(hdc, fonts.status));
                SetBkMode(hdc, TRANSPARENT);
                SetTextColor(hdc, Theme::TextMuted);
                DrawTextW(hdc, status_text.c_str(), -1, &L.rStatusText,
                          DT_LEFT | DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS);
                SelectObject(hdc, fnt_old);

                // --- Footer
                Theme::DrawLabel(hdc, L"100% Anti-Cheat Safe * Zero Injection * Zero DLLs * Zero Hooks",
                    L.footer, fonts.section, Theme::TextFaint, 1, DT_CENTER | DT_SINGLELINE | DT_VCENTER);

                EndPaint(hwnd, &ps);
                return 0;
            }

            case WM_DESTROY:
                Theme::DestroyFontSet(fonts);
                if (bEditBg) { DeleteObject(bEditBg); bEditBg = nullptr; }
                if (bListBg) { DeleteObject(bListBg); bListBg = nullptr; }
                PostQuitMessage(0);
                return 0;
        }
        return DefWindowProcW(hwnd, msg, wparam, lparam);
    }

    static int RunGui() {
        Theme::EnablePerMonitorDpi();
        Theme::BootGdiplus();
        HINSTANCE hInst = GetModuleHandleW(nullptr);
        const wchar_t* clsName = L"DualTitleAuroraGuiWndV5";

        static HBRUSH bgBrush = CreateSolidBrush(Theme::Window);
        WNDCLASSW wc = {};
        wc.style = CS_HREDRAW | CS_VREDRAW;
        wc.lpfnWndProc = GuiWndProc;
        wc.hInstance = hInst;
        wc.lpszClassName = clsName;
        wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
        wc.hbrBackground = bgBrush;
        wc.hIcon = static_cast<HICON>(LoadImageW(nullptr, L"assets\\dualtitle.ico", IMAGE_ICON, 32, 32, LR_LOADFROMFILE));
        if (!wc.hIcon) wc.hIcon = LoadIcon(hInst, MAKEINTRESOURCE(101));
        RegisterClassW(&wc);

        // DPI-aware pre-window sizing
        HDC sdc = GetDC(nullptr);
        int screen_dpi = GetDeviceCaps(sdc, LOGPIXELSX);
        ReleaseDC(nullptr, sdc);
        if (screen_dpi == 0) screen_dpi = 96;
        dpi = screen_dpi; // used by GetLayout before WM_CREATE, refined in WM_CREATE

        int sw = GetSystemMetrics(SM_CXSCREEN);
        int sh = GetSystemMetrics(SM_CYSCREEN);
        DWORD style = WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX;
        RECT wr{0, 0, Theme::S(680, screen_dpi), Theme::S(590, screen_dpi)};
        AdjustWindowRect(&wr, style, FALSE);
        int w = wr.right - wr.left;
        int h = wr.bottom - wr.top;

        HWND hwnd = CreateWindowExW(
            WS_EX_APPWINDOW, clsName,
            L"DualTitle -- Universal Dual Subtitles",
            style | WS_VISIBLE,
            (sw - w) / 2, (sh - h) / 2, w, h,
            nullptr, nullptr, hInst, nullptr
        );
        if (!hwnd) return 1;

        // Dark title bar (Windows 10 1809+)
        using DwmSetWA = HRESULT (WINAPI*)(HWND, DWORD, LPCVOID, DWORD);
        HMODULE dwm = GetModuleHandleW(L"dwmapi.dll");
        if (dwm) {
            auto set_attr = reinterpret_cast<DwmSetWA>(GetProcAddress(dwm, "DwmSetWindowAttribute"));
            if (set_attr) {
                BOOL on = TRUE;
                set_attr(hwnd, 20, &on, sizeof(on));
                set_attr(hwnd, 19, &on, sizeof(on));
            }
        }

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
    int fixed = EmergencyGameRepair::RepairGameDirectory(ue_dir, null_log, false);
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

    ConfigPatcher::ApplyGameConfig(app_dir, "ja", "de", nullptr, null_log);
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
    EmergencyGameRepair::RepairGameDirectory(app_dir, null_log, false);
    assert(fs::file_size(forge_file) == orig_size);
    std::cout << "             PASS: FORGE v27 append-only patch and restore verified.\n";

    // Test 4: Read-Only Anti-Cheat-Safe Frostbite & SRT Subtitle Indexing
    std::cout << "  [Test 4/5] Testing Read-Only Anti-Cheat-Safe Subtitle Indexer...\n";
    WriteTextFile(app_dir / "Data" / "Win32" / "Loc" / "en.sb", "LANG:en:Hold the line and stay together!\nMove to the objective!");
    WriteTextFile(app_dir / "Data" / "Win32" / "Loc" / "de.sb", "LANG:de:Haltet die Stellung und bleibt zusammen!\nRueckt zum Ziel vor!");
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
    WriteTextFile(srt_de, "1\n00:00:01,000 --> 00:00:03,000\nSieh mal da drueben! Eine Fledermaus!\n");
    assert(SubtitleMerger::MergeSrtFiles(srt_en, srt_de, srt_out));
    std::string dual_srt = ReadTextFile(srt_out);
    assert(dual_srt.find("Look over there! It's a bat!\nSieh mal da drueben! Eine Fledermaus!") != std::string::npos);

    auto d_entry = FamousDictionary::Lookup("bats");
    assert(d_entry.translation.find("Fledermaeuse") != std::string::npos);
    std::cout << "             PASS: SRT dual-subtitle merger and Famous Dictionary verified.\n";

    // Test 6: Config persistence + hotkey roundtrip (remap subsystem)
    std::cout << "  [Test 6/6] Testing Config persistence + hotkey remapping...\n";
    {
        DualTitle::DualTitleConfig::AppConfig a = DualTitle::DualTitleConfig::DefaultConfig();
        a.subtitle_style = "mimic_frostbite";
        a.playback_speed = 1.25;
        a.show_card_synonyms = true;
        DualTitle::DualTitleConfig::SetBinding(a, {"pause_game", "P", true, false, false});
        fs::path cfg = tmp / "config.json";
        std::string cerr;
        assert(DualTitle::DualTitleConfig::Save(cfg, a, &cerr));
        DualTitle::DualTitleConfig::AppConfig b;
        std::string lerr;
        assert(DualTitle::DualTitleConfig::Load(cfg, b, &lerr));
        assert(b.subtitle_style == "mimic_frostbite");
        assert(b.playback_speed == 1.25);
        auto* pb = DualTitle::DualTitleConfig::FindBinding(b, "pause_game");
        assert(pb && pb->key == "P" && pb->ctrl);
        // Defaults survive invalid documents
        DualTitle::DualTitleConfig::AppConfig d;
        std::string perr;
        DualTitle::DualTitleConfig::Parse("{ not json", d, &perr);
        assert(!perr.empty());
        auto* rw = DualTitle::DualTitleConfig::FindBinding(d, "reveal_words");
        assert(rw && rw->key == "CAPSLOCK");
        fs::remove(cfg, ec);
    }
    std::cout << "             PASS: config.json roundtrip + remap defaults verified.\n";

    // Test 7: Background dictionary service (worker thread, stale result drop)
    std::cout << "  [Test 7/7] Testing background dictionary service...\n";
    {
        DualTitle::DictSvc::Start();
        // Known word with builtin synonyms
        int req_known = DualTitle::DictSvc::BeginRequest();
        DualTitle::DictSvc::Query("bats", req_known);
        DualTitle::DictSvc::DictResult r;
        bool got_known = false;
        for (int i = 0; i < 200 && !got_known; ++i) {         // <= 2 s
            got_known = DualTitle::DictSvc::Pump(r);
            if (got_known) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        assert(got_known);
        assert(r.req == req_known);
        assert(r.found);
        assert(r.word == "bats");
        bool has_syn = false;
        for (const auto& s : r.entry.synonyms) if (s == "clubs") has_syn = true;
        assert(has_syn);
        // Unknown word -> honest not-found
        int req_unknown = DualTitle::DictSvc::BeginRequest();
        DualTitle::DictSvc::Query("zzqxkj", req_unknown);
        bool got_unknown = false;
        for (int i = 0; i < 200 && !got_unknown; ++i) {
            got_unknown = DualTitle::DictSvc::Pump(r);
            if (got_unknown) break;
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        assert(got_unknown && r.req == req_unknown && !r.found);
        DualTitle::DictSvc::Stop();
    }
    std::cout << "             PASS: async lookup with synonyms verified (worker thread UIS).\n";

    fs::remove_all(tmp, ec);
    std::cout << "========================================================================\n"
              << "  ALL 7 C++17 CORE VERIFICATION SUITES PASSED SUCCESSFULLY!\n"
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
                  << "        DUALTITLE (C++17 EDITION) -- ANTI-CHEAT-SAFE DUAL SUBTITLES\n"
                  << "   Game Library Picker * Save Backup & Restore * Clickable-Word & Speed HUD\n"
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
            ConfigPatcher::ApplyGameConfig(active_game, audio_lang, primary_lang, nullptr, std::cout);
            ForgePatcher::PatchForgeArchive(active_game / "DataPC.forge", primary_lang, secondary_lang, std::cout);
            ForgePatcher::PatchForgeArchive(active_game / "DataPC_boot.forge", primary_lang, secondary_lang, std::cout);
            std::cout << "  [SUCCESS] Safe patch complete! Press Enter to continue...";
            std::getline(std::cin, choice);
        } else if (c == 'l' || c == 'o') {
#ifdef _WIN32
            if (c == 'l') {
                SaveBackupManager::BackupSaves(active_game, std::cout);
                EmergencyGameRepair::RepairGameDirectory(active_game, std::cout);
                ConfigPatcher::ApplyGameConfig(active_game, audio_lang, primary_lang, nullptr, std::cout);
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
            auto overlay_cfg = DualTitle::DualTitleConfig::LoadOrCreate();
            return Win32UniversalOverlay::RunOverlayLoop("", "en", "de", 1.0, overlay_cfg);
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
