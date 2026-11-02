#pragma once
/**
 * DualTitleOverlay.hpp -- Universal Anti-Cheat-Safe C++17 Win32 Topmost In-Game HUD
 * ("Aurora" Modern-Minimal Edition)
 *
 * Features:
 *   - 100% Out-of-Process DWM Topmost Window (ZERO DLL injection, ZERO D3D/Vulkan hooks,
 *     ZERO process handle opening -- never triggers PunkBuster, EAC, BattlEye, or Denuvo!).
 *   - Interactive Clickable Words: Every word in the Primary (Gold #FFD700) and Secondary
 *     (Ice-White #E2E8F0) subtitle lines is individually clickable and instantly shows its
 *     Dictionary Meaning Card (phonetics, gender, translation, definition).
 *   - Modern flat control bar with hover feedback:
 *       [< Prev] [* Auto] [Next >] [-] [1.00x] [+] [Pause (ESC)] [Borderless] [Restore] [x]
 *   - Global hotkeys: ALT+F9 pause . ALT+F10 next line . ALT+F8 show/hide . ALT+F11 borderless
 */

#include "DualTitleEngine.hpp"
#include "DualTitleConfig.hpp"
#include "DualTitleDictService.hpp"
#include "DualTitleTheme.hpp"

#ifdef _WIN32
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <windowsx.h>
#include <shellapi.h>
#pragma comment(lib, "user32.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "shell32.lib")
#endif

namespace DualTitle {

#ifdef _WIN32

struct ClickableWordBox {
    RECT rc;
    std::string word;
    bool is_primary;
};

class Win32UniversalOverlay {
public:
    static inline std::vector<DualDialogueLine> active_lines;
    static inline fs::path active_game_dir;
    static inline size_t current_line_idx = 0;
    static inline bool overlay_visible = true;
    static inline bool auto_play_enabled = false;
    static inline double playback_speed = 1.0; // 0.25x .. 2.0x
    static inline std::wstring status_dictionary_text =
        L"Hold the Reveal key and hover any subtitle word for meaning, job & synonyms.";
    static inline std::vector<ClickableWordBox> word_boxes;
    static inline std::vector<Theme::FlatBtn> control_buttons;
    static inline std::map<int, Theme::BtnState> ctrl_state;
    static inline HWND last_game_hwnd = nullptr;
    static inline Theme::FontSet hud_fonts;
    // Cached large fonts (created once per DPI)
    static inline HFONT hFontPrimary = nullptr;
    static inline HFONT hFontSecondary = nullptr;
    static inline HFONT hFontHoverPrimary = nullptr;
    static inline HFONT hFontHoverSecondary = nullptr;
    static inline HFONT hFontDict = nullptr;
    static inline int hud_dpi = 96;
    static inline int hovered_word = -1;
    static inline bool mouse_tracking = false;
    static inline bool game_is_exclusive_fs = false;
    // Remap config + hold-to-reveal dict card state
    static inline DualTitle::DualTitleConfig::AppConfig cfg;
    static inline std::map<int, std::string> hotkey_slots;   // slot id -> action
    static inline bool reveal_active = false;                // reveal_words key held
    static inline DWORD hover_dwell_start_ms = 0;
    static inline int card_req = 0;
    static inline bool card_loaded = false;
    static inline DictSvc::DictResult card_result;
    static inline std::wstring card_word;
    static inline std::wstring card_status_line;             // short bottom-bar echo

    enum ButtonId {
        BTN_PREV = 1,
        BTN_PLAY_PAUSE = 2,
        BTN_NEXT = 3,
        BTN_SPEED_DOWN = 4,
        BTN_SPEED_RESET = 5,
        BTN_SPEED_UP = 6,
        BTN_GAME_PAUSE = 7,
        BTN_BORDERLESS = 8,
        BTN_RESTORE_SAVE = 9,
        BTN_CLOSE = 10
    };

    static std::wstring Utf8ToWide(const std::string& str) {
        if (str.empty()) return L"";
        int sz = MultiByteToWideChar(CP_UTF8, 0, str.data(), static_cast<int>(str.size()), nullptr, 0);
        if (sz <= 0) return std::wstring(str.begin(), str.end());
        std::wstring out(static_cast<size_t>(sz), L'\0');
        MultiByteToWideChar(CP_UTF8, 0, str.data(), static_cast<int>(str.size()), out.data(), sz);
        return out;
    }

    /** Creates/caches large fonts for the current DPI. */
    static void EnsureLargeFonts(int dpi) {
        if (hFontPrimary && hud_dpi == dpi) return;
        if (hFontPrimary) { DeleteObject(hFontPrimary); DeleteObject(hFontSecondary); 
                            DeleteObject(hFontHoverPrimary); DeleteObject(hFontHoverSecondary); DeleteObject(hFontDict); }
        hud_dpi = dpi;
        hFontPrimary = Theme::MakeFont(dpi, 24, FW_SEMIBOLD);
        hFontSecondary = Theme::MakeFont(dpi, 19, FW_NORMAL);
        hFontHoverPrimary = Theme::MakeFont(dpi, 24, FW_SEMIBOLD);
        hFontHoverSecondary = Theme::MakeFont(dpi, 19, FW_NORMAL);
        hFontDict = Theme::MakeFont(dpi, 13, FW_NORMAL);
    }

    static void CleanupLargeFonts() {
        if (hFontPrimary) { DeleteObject(hFontPrimary); hFontPrimary = nullptr; }
        if (hFontSecondary) { DeleteObject(hFontSecondary); hFontSecondary = nullptr; }
        if (hFontHoverPrimary) { DeleteObject(hFontHoverPrimary); hFontHoverPrimary = nullptr; }
        if (hFontHoverSecondary) { DeleteObject(hFontHoverSecondary); hFontHoverSecondary = nullptr; }
        if (hFontDict) { DeleteObject(hFontDict); hFontDict = nullptr; }
    }

    // ---- Remap helpers -------------------------------------------------------

    /** Converts a config key name (e.g. "F9", "ESC", "P") to a virtual key code. */
    static WORD KeyNameToVk(const std::string& name_in) {
        std::string k = DualTitle::DualTitleConfig::NormalizeKey(name_in);
        if (k.size() == 1 && k[0] >= 'A' && k[0] <= 'Z')
            return static_cast<WORD>('A' + (k[0] - 'A'));
        if (k.size() == 1 && k[0] >= '0' && k[0] <= '9')
            return static_cast<WORD>('0' + (k[0] - '0'));
        struct Pair { const char* name; WORD vk; };
        static const Pair pairs[] = {
            {"ESC", VK_ESCAPE}, {"F1", VK_F1}, {"F2", VK_F2}, {"F3", VK_F3},
            {"F4", VK_F4}, {"F5", VK_F5}, {"F6", VK_F6}, {"F7", VK_F7},
            {"F8", VK_F8}, {"F9", VK_F9}, {"F10", VK_F10}, {"F11", VK_F11}, {"F12", VK_F12},
            {"SPACE", VK_SPACE}, {"ENTER", VK_RETURN}, {"TAB", VK_TAB},
            {"CAPSLOCK", VK_CAPITAL}, {"LEFT", VK_LEFT}, {"RIGHT", VK_RIGHT},
            {"UP", VK_UP}, {"DOWN", VK_DOWN}, {"PGUP", VK_PRIOR}, {"PGDN", VK_NEXT},
            {"HOME", VK_HOME}, {"END", VK_END}, {"INSERT", VK_INSERT},
            {"DELETE", VK_DELETE}, {"BACKSPACE", VK_BACK},
            {"PRINTSCREEN", VK_SNAPSHOT}, {"SCROLLLOCK", VK_SCROLL},
        };
        for (const auto& p : pairs) if (k == p.name) return p.vk;
        return 0;
    }

    /** Convenience: display string of a binding (e.g. "ALT+F9") for the UI. */
    static std::wstring ActionKeyLabel(const std::string& action) {
        const auto* b = DualTitle::DualTitleConfig::FindBinding(cfg, action);
        if (!b || b->key.empty()) return L"?";
        std::wstring out;
        if (b->ctrl) out += L"CTRL+";
        if (b->alt)  out += L"ALT+";
        if (b->shift) out += L"SHIFT+";
        std::string kk = DualTitle::DualTitleConfig::NormalizeKey(b->key);
        return out + Utf8ToWide(kk);
    }

    /** Registers every configured hotkey on its own slot (except reveal_words,
     *  which is polled via GetKeyState instead of RegisterHotKey). */
    static bool ApplyHotkeys(HWND hwnd) {
        for (const auto& kv : hotkey_slots) UnregisterHotKey(hwnd, static_cast<int>(kv.first));
        hotkey_slots.clear();
        int slot = 101;
        bool any_ok = false;
        for (const auto& h : cfg.hotkeys) {
            if (h.action == "reveal_words") continue;
            WORD vk = KeyNameToVk(h.key);
            if (!vk) continue;
            UINT mods = 0;
            if (h.ctrl) mods |= MOD_CONTROL;
            if (h.alt)  mods |= MOD_ALT;
            if (h.shift) mods |= MOD_SHIFT;
            if (RegisterHotKey(hwnd, slot, mods, vk)) {
                hotkey_slots[slot] = h.action;
                any_ok = true;
            }
            ++slot;
            if (slot > 130) break;   // hard cap on global hotkeys
        }
        return any_ok;
    }

    /** The persisted key hold-to-reveal is bound to (polled, 0 disables). */
    static WORD RevealVk() {
        const auto* b = DualTitle::DualTitleConfig::FindBinding(cfg, "reveal_words");
        if (!b || b->key.empty()) return 0;
        // Plain keys only when unmodified (modifiers reserved for hotkeys).
        if (b->ctrl || b->alt || b->shift) return 0;
        return KeyNameToVk(b->key);
    }

    // Static string helpers to avoid parser issues with wide string literals in WM_PAINT
    static const wchar_t* Str_DualTitle() { return L"DUALTITLE"; }
    static const wchar_t* Str_NoSubtitleData() { return L"No subtitle data found -- import .srt or configure a Game Profile"; }
    static const wchar_t* Str_Slash() { return L" / "; }
    static const wchar_t* Str_Space() { return L" "; }
    static const wchar_t* Str_FullscreenHint() { return L"Game is in exclusive fullscreen -- press [Borderless] or ALT+F11 for overlay to appear"; }

    static void RememberForegroundGameWindow(HWND overlay_hwnd) {
        HWND fg = GetForegroundWindow();
        if (fg && fg != overlay_hwnd) {
            DWORD pid = 0;
            GetWindowThreadProcessId(fg, &pid);
            if (pid != 0 && pid != GetCurrentProcessId()) {
                last_game_hwnd = fg;
                // Check if the game window is exclusive fullscreen
                RECT rc;
                if (GetWindowRect(fg, &rc)) {
                    int sw = GetSystemMetrics(SM_CXSCREEN);
                    int sh = GetSystemMetrics(SM_CYSCREEN);
                    LONG_PTR style = GetWindowLongPtrW(fg, GWL_STYLE);
                    bool is_popup = (style & WS_POPUP) != 0;
                    bool fullscreen = (rc.left <= 0 && rc.top <= 0 && rc.right >= sw && rc.bottom >= sh);
                    game_is_exclusive_fs = is_popup && fullscreen;
                }
            }
        }
    }

    /**
     * Anti-Cheat-Safe Game Pause: sends the USER-MAPPED pause key to the active
     * game window without opening a process handle (SendInput only, no hooks).
     */
    static void SendSafeGamePause(HWND overlay_hwnd) {
        RememberForegroundGameWindow(overlay_hwnd);
        if (!(last_game_hwnd && IsWindow(last_game_hwnd))) {
            status_dictionary_text = L"Switch to your running application window first, then use Pause Game.";
            return;
        }
        const auto* b = DualTitle::DualTitleConfig::FindBinding(cfg, "pause_game");
        std::string key_name = (b && !b->key.empty()) ? b->key : "ESC";
        WORD vk = KeyNameToVk(key_name);
        if (!vk) vk = VK_ESCAPE;
        SetForegroundWindow(last_game_hwnd);
        // Modifier keys wrap the pause key (only those configured for it).
        std::vector<WORD> down, up;
        const auto* bb = DualTitle::DualTitleConfig::FindBinding(cfg, "pause_game");
        if (bb && bb->ctrl) { down.push_back(VK_CONTROL); up.push_back(VK_CONTROL); }
        if (bb && bb->alt)  { down.push_back(VK_MENU);    up.push_back(VK_MENU); }
        if (bb && bb->shift){ down.push_back(VK_SHIFT);   up.push_back(VK_SHIFT); }
        up.push_back(vk);  // key-down then key-up
        std::vector<INPUT> inputs;
        for (WORD m : down) {
            INPUT i{}; i.type = INPUT_KEYBOARD; i.ki.wVk = m; inputs.push_back(i);
        }
        INPUT kd{}; kd.type = INPUT_KEYBOARD; kd.ki.wVk = vk; inputs.push_back(kd);
        INPUT ku{}; ku.type = INPUT_KEYBOARD; ku.ki.wVk = vk; ku.ki.dwFlags = KEYEVENTF_KEYUP; inputs.push_back(ku);
        // Release modifiers in reverse order.
        for (auto rit = up.rbegin(); rit != up.rend(); ++rit) {
            INPUT i{}; i.type = INPUT_KEYBOARD; i.ki.wVk = *rit; i.ki.dwFlags = KEYEVENTF_KEYUP; inputs.push_back(i);
        }
        // Order: modifiers down, pause key down/up, modifiers up (reversed).
        SendInput(static_cast<UINT>(inputs.size()), inputs.data(), sizeof(INPUT));
        status_dictionary_text = L"Pause key (" + Utf8ToWide(
            DualTitle::DualTitleConfig::NormalizeKey(key_name)) + L") sent to the running window -- zero process hooks used.";
    }

    /** Pause Subtitles: freezes/unfreezes auto-advance cadence only (game untouched). */
    static void ToggleSubtitlePause(HWND hwnd) {
        auto_play_enabled = !auto_play_enabled;
        UpdateSpeedTimer(hwnd);
        status_dictionary_text = auto_play_enabled
            ? L"Subtitles auto-advance resumed."
            : L"Subtitles paused -- cadence frozen (game untouched).";
        InvalidateRect(hwnd, nullptr, TRUE);
    }

    // ---- Hold-to-reveal dictionary card --------------------------------------

    static const ClickableWordBox* WordAt(const POINT& pt) {
        for (const auto& wb : word_boxes) {
            if (PtInRect(&wb.rc, pt)) return &wb;
        }
        return nullptr;
    }

    static void ClearDictCard(HWND hwnd) {
        card_req = 0;
        card_loaded = false;
        card_result = DictSvc::DictResult{};
        card_word.clear();
        card_status_line.clear();
        DictSvc::SetCardVisible(false);
        DictSvc::SetActiveRequest(0);
        InvalidateRect(hwnd, nullptr, TRUE);
    }

    /** Kicks off an async lookup; the popup card appears once Pump() delivers. */
    static void StartWordLookup(HWND hwnd, const ClickableWordBox& wb) {
        card_req = DictSvc::BeginRequest();
        card_word = Utf8ToWide(wb.word);
        card_loaded = false;
        card_result = DictSvc::DictResult{};
        card_status_line = L"Looking up '" + card_word + L"' ...";
        DictSvc::Query(wb.word, card_req);
        InvalidateRect(hwnd, nullptr, TRUE);
    }

    /** Enters/leaves reveal mode: toggles click-through so words become live. */
    static void OnRevealChanged(HWND hwnd, bool active) {
        reveal_active = active;
        LONG_PTR ex = GetWindowLongPtrW(hwnd, GWL_EXSTYLE);
        if (active) {
            ex &= ~static_cast<LONG_PTR>(WS_EX_TRANSPARENT);
            status_dictionary_text = L"Reveal mode: hover a word to inspect it.";
        } else {
            ex |= WS_EX_TRANSPARENT;
            ClearDictCard(hwnd);
        }
        SetWindowLongPtrW(hwnd, GWL_EXSTYLE, ex);
        InvalidateRect(hwnd, nullptr, TRUE);
    }

    /** Tracks WM_MOUSEMOVE-like hover state from an arbitrary point (client coords). */
    static void UpdateHoverFromPoint(HWND hwnd, const POINT& pt_client) {
        int new_hover = -1;
        for (size_t i = 0; i < word_boxes.size(); ++i) {
            if (PtInRect(&word_boxes[i].rc, pt_client)) {
                new_hover = static_cast<int>(i);
                break;
            }
        }
        if (new_hover != hovered_word) {
            if (hovered_word >= 0 && hovered_word < static_cast<int>(word_boxes.size())) {
                InvalidateRect(hwnd, &word_boxes[static_cast<size_t>(hovered_word)].rc, TRUE);
            }
            hovered_word = new_hover;
            if (hovered_word >= 0) {
                InvalidateRect(hwnd, &word_boxes[static_cast<size_t>(hovered_word)].rc, TRUE);
                hover_dwell_start_ms = GetTickCount();
            }
        }
    }

    /** 16 ms fast tick: reveal-key polling, hover tracking, dwell + card pump. */
    static void PollRevealAndCard(HWND hwnd) {
        // 1) Hold-key state (polled; works even when the game window has focus)
        WORD rvk = RevealVk();
        bool want_reveal = false;
        if (rvk && !active_lines.empty()) {
            want_reveal = (GetKeyState(static_cast<int>(rvk)) & 0x8000) != 0;
        }
        if (want_reveal != reveal_active) OnRevealChanged(hwnd, want_reveal);

        // Pump async dictionary results (stale requests are dropped)
        DictSvc::DictResult r;
        while (DictSvc::Pump(r)) {
            if (r.req == card_req && DictSvc::CardVisible()) {
                card_result = r;
                card_loaded = true;
                std::wostringstream ss;
                ss << Utf8ToWide(r.entry.word);
                if (!r.entry.phonetic.empty()) ss << L"  " << Utf8ToWide(r.entry.phonetic);
                card_status_line = ss.str();
                if (r.found) {
                    if (!r.entry.pos.empty())
                        card_status_line += L"  [" + Utf8ToWide(r.entry.pos) + L"]";
                    card_status_line += L"  --  " + Utf8ToWide(r.entry.definition);
                } else {
                    card_status_line = L"No dictionary entry for '" + card_word + L"' (offline lexicon)";
                }
                InvalidateRect(hwnd, nullptr, TRUE);
            }
        }

        // 2) Hover tracking while reveal is held (pointer may be over the game)
        if (!reveal_active) return;
        DWORD now = GetTickCount();
        if (rvk) {
            POINT pt{};
            GetCursorPos(&pt);
            ScreenToClient(hwnd, &pt);
            RECT rc;
            GetClientRect(hwnd, &rc);
            if (PtInRect(&rc, pt)) {
                UpdateHoverFromPoint(hwnd, pt);
                if (hovered_word >= 0 &&
                    hover_dwell_start_ms != 0 &&
                    now - hover_dwell_start_ms >= static_cast<DWORD>(std::max(0, cfg.hover_dwell_ms))) {
                    const auto& wb = word_boxes[static_cast<size_t>(hovered_word)];
                    if (!DictSvc::CardVisible() || card_word != Utf8ToWide(wb.word)) {
                        StartWordLookup(hwnd, wb);
                    }
                }
            }
        }
    }


    /**
     * Converts the target application window to Borderless Fullscreen so the overlay
     * stays visible on top without hooking DirectX/Vulkan.
     */
    static void MakeTargetGameBorderless(HWND overlay_hwnd) {
        RememberForegroundGameWindow(overlay_hwnd);
        HWND target = last_game_hwnd ? last_game_hwnd : GetForegroundWindow();
        if (!target || target == overlay_hwnd || !IsWindow(target)) {
            status_dictionary_text = L"Click inside your running application window first, then press Borderless or ALT+F11.";
            return;
        }
        int sw = GetSystemMetrics(SM_CXSCREEN);
        int sh = GetSystemMetrics(SM_CYSCREEN);
        LONG_PTR style = GetWindowLongPtrW(target, GWL_STYLE);
        LONG_PTR new_style = (style & ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)) | WS_POPUP | WS_VISIBLE;
        SetWindowLongPtrW(target, GWL_STYLE, new_style);
        SetWindowPos(target, HWND_NOTOPMOST, 0, 0, sw, sh, SWP_FRAMECHANGED | SWP_NOACTIVATE | SWP_SHOWWINDOW);
        SetWindowPos(overlay_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
        status_dictionary_text = L"Borderless fullscreen applied (" + std::to_wstring(sw) + L" x " + std::to_wstring(sh) + L").";
    }

    static void UpdateSpeedTimer(HWND hwnd) {
        KillTimer(hwnd, 201);
        if (auto_play_enabled) {
            UINT interval_ms = static_cast<UINT>(3600.0 / std::max(0.25, playback_speed));
            SetTimer(hwnd, 201, interval_ms, nullptr);
        }
    }

    static void DrawDualTitleMiniLogo(HDC hdc, int x, int y, int size) {
        Theme::BootGdiplus();
        // Signature badge: rounded dark tile + gold top bar + white bottom bar + sky dots
        Theme::RoundRectFill(hdc, RECT{x, y, x + size, y + size},
                             size / 5, RGB(15, 19, 28), 255, RGB(38, 44, 58), 220);
        double u = size / 44.0;
        Theme::RoundRectFill(hdc, RECT{
            x + static_cast<int>(4 * u), y + static_cast<int>(9 * u),
            x + size - static_cast<int>(4 * u), y + static_cast<int>(13 * u)
        }, static_cast<int>(2 * u), Theme::Gold);
        Theme::RoundRectFill(hdc, RECT{
            x + static_cast<int>(4 * u), y + static_cast<int>(16 * u),
            x + size - static_cast<int>(4 * u), y + static_cast<int>(20 * u)
        }, static_cast<int>(2 * u), Theme::IceWhite);
        Theme::FillCircle(hdc, x + static_cast<int>(15 * u), y + static_cast<int>(30 * u),
                          static_cast<int>(3.5 * u), Theme::Accent);
        Theme::FillCircle(hdc, x + size - static_cast<int>(15 * u), y + static_cast<int>(30 * u),
                          static_cast<int>(3.5 * u), Theme::DangerText, 190);
    }

    static void BuildControlButtons(HWND hwnd) {
        control_buttons.clear();
        auto s = [&](int v) { return Theme::S(v, hud_dpi); };
        RECT rc_client{};
        GetClientRect(hwnd, &rc_client);
        int y = s(6), h = s(24);
        int x = rc_client.right - s(12);
        double spd_f = playback_speed;
        wchar_t spd_lbl[16];
        swprintf(spd_lbl, 16, L"%.2fx", spd_f);
        std::wstring pause_game_lbl = L"Pause Game";
        std::wstring pause_subs_lbl = auto_play_enabled ? L"Pause Subs" : L"Resume Subs";

        struct Spec { int id; std::wstring label; int w; Theme::BtnKind kind; };
        Spec specs[] = {
            {BTN_RESTORE_SAVE, L"Restore", s(64), Theme::BtnTeal},
            {BTN_BORDERLESS,  L"Borderless", s(80), Theme::BtnGhost},
            {BTN_GAME_PAUSE,  pause_game_lbl, s(102), Theme::BtnGhost},
            {BTN_PLAY_PAUSE,  pause_subs_lbl, s(96), Theme::BtnGhost},
            {BTN_SPEED_UP,    L"+", s(26), Theme::BtnGhost},
            {BTN_SPEED_RESET, spd_lbl, s(60), Theme::BtnGhost},
            {BTN_SPEED_DOWN,  L"-", s(26), Theme::BtnGhost},
            {BTN_NEXT,        L"Next >", s(58), Theme::BtnGhost},
            {BTN_PREV,        L"< Prev", s(54), Theme::BtnGhost},
            {BTN_CLOSE,       L"x", s(26), Theme::BtnDanger}
        };
        for (auto& sp : specs) {
            RECT br{ x - sp.w, y, x, y + h };
            control_buttons.push_back({sp.id, br, sp.label, sp.kind});
            x -= sp.w + s(6);
        }
        // Toggle attributes live on the matched buttons
        for (auto& b : control_buttons) {
            if (b.id == BTN_PLAY_PAUSE) { b.is_toggle = true; b.toggle_on = auto_play_enabled; }
            if (b.id == BTN_SPEED_RESET) b.text_override = Theme::Gold;
            if (b.id == BTN_GAME_PAUSE) b.text_override = Theme::Accent;
        }
    }

    static Theme::FlatBtn* HitControlButton(const POINT& pt) {
        for (auto& b : control_buttons) {
            if (PtInRect(&b.rc, pt)) return &b;
        }
        return nullptr;
    }

    static void EnsureTrackMouse(HWND hwnd) {
        if (mouse_tracking) return;
        TRACKMOUSEEVENT tme{sizeof(tme), TME_LEAVE, hwnd, 0};
        if (TrackMouseEvent(&tme)) mouse_tracking = true;
    }

    static LRESULT CALLBACK OverlayWndProc(HWND hwnd, UINT msg, WPARAM wparam, LPARAM lparam) {
        switch (msg) {
            case WM_CREATE:
                SetTimer(hwnd, 200, 300, nullptr); // Topmost watchdog timer
                return 0;

            case WM_TIMER:
                if (wparam == 200) {
                    RememberForegroundGameWindow(hwnd);
                    if (overlay_visible) {
                        SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                                     SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
                    }
                    // Fast poll for reveal-mode hover (runs every 300 ms as a
                    // fallback so the card works even if timer 202 is starved)
                    PollRevealAndCard(hwnd);
                } else if (wparam == 201 && auto_play_enabled && !active_lines.empty()) {
                    current_line_idx = (current_line_idx + 1) % active_lines.size();
                    InvalidateRect(hwnd, nullptr, TRUE);
                } else if (wparam == 202) {
                    // 16 ms fast tick: reveal key + hover dwell + async card
                    PollRevealAndCard(hwnd);
                }
                return 0;

            case WM_MOUSEMOVE: {
                EnsureTrackMouse(hwnd);
                POINT pt{GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
                BuildControlButtons(hwnd);
                for (auto& b : control_buttons) {
                    auto& st = ctrl_state[b.id];
                    bool hov = PtInRect(&b.rc, pt) != FALSE;
                    if (st.hover != hov) {
                        st.hover = hov;
                        InvalidateRect(hwnd, &b.rc, TRUE);
                    }
                }
                // Word hover tracking
                UpdateHoverFromPoint(hwnd, pt);
                return 0;
            }

            case WM_MOUSELEAVE: {
                mouse_tracking = false;
                for (auto& b : control_buttons) ctrl_state[b.id].hover = false;
                if (hovered_word >= 0 && hovered_word < static_cast<int>(word_boxes.size())) {
                    InvalidateRect(hwnd, &word_boxes[static_cast<size_t>(hovered_word)].rc, TRUE);
                }
                hovered_word = -1;
                InvalidateRect(hwnd, nullptr, TRUE);
                return 0;
            }

            case WM_SETCURSOR: {
                if (LOWORD(lparam) == HTCLIENT) {
                    POINT pt{};
                    GetCursorPos(&pt);
                    ScreenToClient(hwnd, &pt);
                    BuildControlButtons(hwnd);
                    bool hand = HitControlButton(pt) != nullptr;
                    if (reveal_active) {
                        for (const auto& wb : word_boxes) {
                            if (PtInRect(&wb.rc, pt)) { hand = true; break; }
                        }
                    }
                    SetCursor(LoadCursor(nullptr, hand ? IDC_HAND : IDC_ARROW));
                    return TRUE;
                }
                break;
            }

            case WM_NCHITTEST: {
                // Control bar clickable; words clickable while reveal is held;
                // body stays click-through otherwise (never blocks the game).
                POINT pt{GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};
                ScreenToClient(hwnd, &pt);
                BuildControlButtons(hwnd);
                for (const auto& b : control_buttons) {
                    if (PtInRect(&b.rc, pt)) return HTCLIENT;
                }
                if (reveal_active) {
                    for (const auto& wb : word_boxes) {
                        if (PtInRect(&wb.rc, pt)) return HTCLIENT;
                    }
                }
                // Body is transparent to clicks
                return HTTRANSPARENT;
            }
            case WM_MOUSEACTIVATE:
                // Never steal keyboard focus from the running game when clicking overlay buttons/words!
                return MA_NOACTIVATE;

            case WM_HOTKEY: {
                auto it = hotkey_slots.find(static_cast<int>(wparam));
                if (it == hotkey_slots.end()) return 0;
                const std::string& action = it->second;
                if (action == "pause_game") {
                    SendSafeGamePause(hwnd);
                } else if (action == "pause_subs") {
                    ToggleSubtitlePause(hwnd);
                } else if (action == "next_line" && !active_lines.empty()) {
                    current_line_idx = (current_line_idx + 1) % active_lines.size();
                } else if (action == "prev_line" && !active_lines.empty()) {
                    current_line_idx = (current_line_idx + active_lines.size() - 1) % active_lines.size();
                } else if (action == "toggle_hud") {
                    overlay_visible = !overlay_visible;
                    ShowWindow(hwnd, overlay_visible ? SW_SHOWNOACTIVATE : SW_HIDE);
                } else if (action == "borderless") {
                    MakeTargetGameBorderless(hwnd);
                } else if (action == "speed_down") {
                    playback_speed = std::max(0.25, playback_speed - 0.25);
                    UpdateSpeedTimer(hwnd);
                    status_dictionary_text = L"Speed: " + SpeedLabel();
                } else if (action == "speed_up") {
                    playback_speed = std::min(2.0, playback_speed + 0.25);
                    UpdateSpeedTimer(hwnd);
                    status_dictionary_text = L"Speed: " + SpeedLabel();
                } else if (action == "toggle_dict") {
                    if (DictSvc::CardVisible()) ClearDictCard(hwnd);
                }
                InvalidateRect(hwnd, nullptr, TRUE);
                return 0;
            }

            case WM_LBUTTONDOWN: {
                POINT pt = {GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};

                // 1. In-Game Control Buttons
                BuildControlButtons(hwnd);
                if (auto* btn = HitControlButton(pt)) {
                    switch (btn->id) {
                        case BTN_PREV:
                            if (!active_lines.empty()) {
                                current_line_idx = (current_line_idx + active_lines.size() - 1) % active_lines.size();
                            }
                            break;
                        case BTN_NEXT:
                            if (!active_lines.empty()) {
                                current_line_idx = (current_line_idx + 1) % active_lines.size();
                            }
                            break;
                        case BTN_PLAY_PAUSE:
                            ToggleSubtitlePause(hwnd);
                            break;
                        case BTN_SPEED_DOWN:
                            playback_speed = std::max(0.25, playback_speed - 0.25);
                            UpdateSpeedTimer(hwnd);
                            status_dictionary_text = L"Speed: " + SpeedLabel();
                            break;
                        case BTN_SPEED_RESET:
                            playback_speed = 1.0;
                            UpdateSpeedTimer(hwnd);
                            status_dictionary_text = L"Speed reset to 1.00x";
                            break;
                        case BTN_SPEED_UP:
                            playback_speed = std::min(2.0, playback_speed + 0.25);
                            UpdateSpeedTimer(hwnd);
                            status_dictionary_text = L"Speed: " + SpeedLabel();
                            break;
                        case BTN_GAME_PAUSE:
                            SendSafeGamePause(hwnd);
                            break;
                        case BTN_BORDERLESS:
                            MakeTargetGameBorderless(hwnd);
                            break;
                        case BTN_RESTORE_SAVE: {
                            std::ostringstream log_ss;
                            int cnt = SaveBackupManager::RestoreSaves(active_game_dir, log_ss);
                            status_dictionary_text = L"Restore complete -- " + std::to_wstring(cnt) +
                                                     L" save/profile file(s) restored & verified.";
                            break;
                        }
                        case BTN_CLOSE:
                            DestroyWindow(hwnd);
                            return 0;
                    }
                    InvalidateRect(hwnd, nullptr, TRUE);
                    return 0;
                }

                // 2. Words in the Primary or Secondary Subtitle Line
                for (const auto& wb : word_boxes) {
                    if (PtInRect(&wb.rc, pt)) {
                        StartWordLookup(hwnd, wb);
                        return 0;
                    }
                }
                return 0;
            }

            case WM_PAINT: {
                PAINTSTRUCT ps;
                HDC hdc = BeginPaint(hwnd, &ps);
                Theme::BootGdiplus();
                RECT rc;
                GetClientRect(hwnd, &rc);
                auto s = [&](int v) { return Theme::S(v, hud_dpi); };

                // Outer card -- rounded, translucent charcoal w/ hairline border
                // Subtitle style preset: 0 = aurora, 1 = mimic_frostbite, 2 = classic_console
                int style = 0;
                if (cfg.subtitle_style == "mimic_frostbite") style = 1;
                else if (cfg.subtitle_style == "classic_console") style = 2;
                if (style == 1) {
                    // Frostbite look: flat near-black band, no rounded card sheen
                    Theme::RoundRectFill(hdc, rc, s(2), RGB(8, 10, 14), 200, RGB(20, 24, 30), 220);
                } else if (style == 2) {
                    // Console look: deep black slab with a faint phosphor border
                    Theme::RoundRectFill(hdc, rc, s(2), RGB(0, 6, 0), 225, RGB(40, 160, 60), 150);
                } else {
                    Theme::RoundRectFill(hdc, rc, s(14), Theme::Inner, 238, RGB(36, 42, 56), 210);
                }

                // Header: logo + wordmark + progress
                DrawDualTitleMiniLogo(hdc, s(10), s(8), s(24));
                HFONT fWordmark = hud_fonts.section;
                RECT rcTitle{s(44), s(8), s(184), s(30)};
                Theme::DrawLabel(hdc, Str_DualTitle(), rcTitle, fWordmark, Theme::TextMuted, 2);

                // Progress or empty-state message
                if (active_lines.empty()) {
                    Theme::DrawLabel(hdc, Str_NoSubtitleData(),
                        RECT{s(150), s(8), s(500), s(30)}, hud_fonts.section, Theme::TextFaint, 1);
                } else {
                    std::wstring progress =
                        std::to_wstring((current_line_idx % active_lines.size()) + 1) +
                        Str_Slash() + std::to_wstring(active_lines.size());
                    Theme::DrawLabel(hdc, progress, RECT{s(150), s(8), s(230), s(30)}, hud_fonts.section, Theme::TextFaint, 1);
                }

                // Control buttons on the right
                BuildControlButtons(hwnd);
                for (const auto& b : control_buttons) {
                    Theme::DrawBtn(hdc, b, ctrl_state[b.id], hud_dpi, hud_fonts.btn);
                }

                // Current subtitle line pair
                if (!active_lines.empty()) {
                    const auto& item = active_lines[current_line_idx % active_lines.size()];

                    word_boxes.clear();
                    auto draw_clickable_sentence = [&](const std::string& sentence, int top_y, int bot_y,
                                                        HFONT hFont, COLORREF color, bool is_prim) {
                        HFONT old = static_cast<HFONT>(SelectObject(hdc, hFont));
                        SetTextColor(hdc, color);

                        std::istringstream iss(sentence);
                        std::vector<std::string> tokens;
                        std::string tok;
                        while (iss >> tok) tokens.push_back(tok);

                        int total_w = 0;
                        std::vector<int> widths;
                        SIZE space_sz = {};
                        GetTextExtentPoint32W(hdc, Str_Space(), 1, &space_sz);
                        int gap = std::max<int>(6, space_sz.cx + 2);

                        for (const auto& t : tokens) {
                            std::wstring wt = Utf8ToWide(t);
                            SIZE tsz = {};
                            GetTextExtentPoint32W(hdc, wt.c_str(), static_cast<int>(wt.size()), &tsz);
                            int w = tsz.cx + 6;
                            widths.push_back(w);
                            total_w += w;
                        }
                        if (!tokens.empty()) total_w += static_cast<int>(tokens.size() - 1) * gap;

                        int start_x = std::max<int>(s(16), (rc.right - total_w) / 2);
                        for (size_t i = 0; i < tokens.size(); ++i) {
                            std::wstring wt = Utf8ToWide(tokens[i]);
                            RECT wrc{start_x, top_y, start_x + widths[i], bot_y};
                            DrawTextW(hdc, wt.c_str(), -1, &wrc, DT_CENTER | DT_SINGLELINE | DT_VCENTER);
                            word_boxes.push_back({wrc, tokens[i], is_prim});
                            start_x += widths[i] + gap;
                        }
                        SelectObject(hdc, old);
                    };

                    // Style palette: aurora gold/ice, frostbite white/gray, console green/amber
                    COLORREF prim_col = Theme::Gold;
                    COLORREF sec_col = Theme::IceWhite;
                    if (style == 1) {
                        prim_col = RGB(242, 244, 246);
                        sec_col = RGB(186, 194, 204);
                    } else if (style == 2) {
                        prim_col = RGB(120, 255, 160);
                        sec_col = RGB(255, 200, 96);
                    }

                    // Top line -- primary subtitle; bottom line -- secondary
                    draw_clickable_sentence(item.primary, s(40), s(74), hFontPrimary, prim_col, true);
                    draw_clickable_sentence(item.secondary, s(78), s(108), hFontSecondary, sec_col, false);

                    // Hover highlight: pill under the hovered word, text redrawn on top
                    if (hovered_word >= 0 && hovered_word < static_cast<int>(word_boxes.size())) {
                        const auto& wb = word_boxes[static_cast<size_t>(hovered_word)];
                        RECT pr{wb.rc.left - s(3), wb.rc.top - s(1), wb.rc.right + s(3), wb.rc.bottom + s(1)};
                        Theme::RoundRectFill(hdc, pr, s(6), Theme::Accent, 42);
                        HFONT hHover = wb.is_primary ? hFontHoverPrimary : hFontHoverSecondary;
                        HFONT old_h = static_cast<HFONT>(SelectObject(hdc, hHover));
                        SetBkMode(hdc, TRANSPARENT);
                        SetTextColor(hdc, wb.is_primary ? prim_col : sec_col);
                        std::wstring wt = Utf8ToWide(wb.word);
                        RECT wrc_copy{wb.rc.left, wb.rc.top, wb.rc.right, wb.rc.bottom};
                        DrawTextW(hdc, wt.c_str(), -1, &wrc_copy, DT_CENTER | DT_SINGLELINE | DT_VCENTER);
                        SelectObject(hdc, old_h);
                    }

                    // Reveal-mode indicator: small pill top-right under the buttons row
                    if (reveal_active) {
                        RECT rev_rc{rc.right - s(120), s(32), rc.right - s(12), s(48)};
                        Theme::RoundRectFill(hdc, rev_rc, s(5), Theme::Accent, 80);
                        Theme::DrawLabel(hdc, (L"REVEAL (" + ActionKeyLabel("reveal_words") + L")").c_str(),
                            rev_rc, hud_fonts.btn, Theme::IceWhite, 0, DT_CENTER | DT_SINGLELINE | DT_VCENTER);
                    }

                    // ________________________
                    // Dictionary popup card (hover/click a word while reveal held)
                    if (DictSvc::CardVisible() && !card_word.empty()) {
                        // Anchor next to the hovered word (falls back to center-top)
                        const ClickableWordBox* anchor = nullptr;
                        for (const auto& wb : word_boxes)
                            if (Utf8ToWide(wb.word) == card_word) { anchor = &wb; break; }
                        int ax = anchor ? anchor->rc.left : s(240);
                        int ay = anchor ? anchor->rc.bottom + s(6) : s(48);

                        // Compose card lines respecting user toggles
                        struct Line { std::wstring text; COLORREF color; };
                        std::vector<Line> lines;
                        lines.push_back({card_word + (card_result.entry.phonetic.empty() && !card_loaded
                                                ? L"   --  looking up..." : L""),
                                         Theme::Gold});
                        if (card_loaded) {
                            const auto& e = card_result.entry;
                            bool known = card_result.found;
                            if (known) {
                                std::wstring head;
                                if (cfg.show_card_phonetics && !e.phonetic.empty())
                                    head += Utf8ToWide(e.phonetic) + L"   ";
                                if (cfg.show_card_pos && !e.pos.empty())
                                    head += L"(" + Utf8ToWide(e.pos) + L")";
                                if (!e.gender.empty()) head += L" " + Utf8ToWide(e.gender);
                                if (!head.empty()) lines.push_back({head, Theme::DictText});
                                if (cfg.show_card_translation && !e.translation.empty())
                                    lines.push_back({L"Translation: " + Utf8ToWide(e.translation), Theme::IceWhite});
                                if (cfg.show_card_definition && !e.definition.empty())
                                    lines.push_back({Utf8ToWide(e.definition), Theme::TextMuted});
                                if (cfg.show_card_synonyms && e.synonyms.size() > 0) {
                                    std::wstring syn = L"Synonyms: ";
                                    for (size_t i = 0; i < e.synonyms.size(); ++i) {
                                        if (i) syn += L", ";
                                        syn += Utf8ToWide(e.synonyms[i]);
                                    }
                                    lines.push_back({syn, Theme::Accent});
                                }
                                {
                                    std::wstring src = Utf8ToWide(e.source);
                                    if (!src.empty()) lines.push_back({L"Source: " + src, Theme::TextFaint});
                                }
                            } else {
                                lines.push_back({L"No dictionary entry for this word.", Theme::TextFaint});
                                lines.push_back({L"Try another word -- the offline lexicon is limited.", Theme::TextFaint});
                            }
                        }

                        // Measure the tallest wrapped section to size the card
                        int card_w = s(340);
                        int card_h = s(34);                       // header + padding
                        HFONT old_card = static_cast<HFONT>(SelectObject(hdc, hFontDict));
                        std::vector<RECT> line_rects;
                        for (const auto& ln : lines) {
                            RECT probe{0, 0, card_w - s(28), s(1000)};
                            DrawTextW(hdc, ln.text.c_str(), -1, &probe,
                                      DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX);
                            line_rects.push_back(probe);
                            card_h += probe.bottom + s(4);
                        }
                        SelectObject(hdc, old_card);

                        // Clamp into the client area
                        RECT crc{ax, ay, ax + card_w, ay + card_h};
                        if (crc.right > rc.right - s(8)) {
                            int shift = crc.right - (rc.right - s(8));
                            crc.left -= shift; crc.right -= shift;
                        }
                        if (crc.bottom > rc.bottom - s(8)) {
                            int up = crc.bottom - (rc.bottom - s(8));
                            crc.top -= up; crc.bottom -= up;
                        }
                        if (crc.top < s(8)) { crc.top = s(8); }

                        Theme::RoundRectFill(hdc, crc, s(10), RGB(13, 17, 26), 250,
                                             RGB(56, 130, 246), 160);
                        int yy = crc.top + s(8);
                        old_card = static_cast<HFONT>(SelectObject(hdc, hFontDict));
                        SetBkMode(hdc, TRANSPARENT);
                        for (size_t i = 0; i < lines.size(); ++i) {
                            SetTextColor(hdc, lines[i].color);
                            RECT tlr{crc.left + s(14), yy, crc.right - s(14),
                                     yy + line_rects[i].bottom};
                            DrawTextW(hdc, lines[i].text.c_str(), -1, &tlr,
                                      DT_WORDBREAK | DT_NOPREFIX);
                            yy += line_rects[i].bottom + s(4);
                        }
                        SelectObject(hdc, old_card);
                    }
                }

                // M0.4: Exclusive fullscreen hint pill
                if (game_is_exclusive_fs && active_lines.empty()) {
                    RECT hint_rc{s(16), s(110), rc.right - s(16), s(130)};
                    Theme::RoundRectFill(hdc, hint_rc, s(6), Theme::Accent, 60);
                    Theme::DrawLabel(hdc, Str_FullscreenHint(),
                        RECT{hint_rc.left + s(8), hint_rc.top, hint_rc.right - s(8), hint_rc.bottom},
                        hud_fonts.section, Theme::Gold, 0, DT_CENTER | DT_SINGLELINE | DT_VCENTER);
                }

                // Bottom dictionary bar -- rounded inner card
                RECT rcDict{s(12), s(116), rc.right - s(12), rc.bottom - s(6)};
                Theme::RoundRectFill(hdc, rcDict, s(8), RGB(15, 20, 28), 255, RGB(28, 34, 46), 200);
                HFONT old_d = static_cast<HFONT>(SelectObject(hdc, hFontDict));
                RECT rcDictTxt{rcDict.left + s(16), rcDict.top, rcDict.right - s(16), rcDict.bottom};
                SetBkMode(hdc, TRANSPARENT);
                SetTextColor(hdc, Theme::DictText);
                DrawTextW(hdc, status_dictionary_text.c_str(), -1, &rcDictTxt,
                          DT_LEFT | DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS);
                SelectObject(hdc, old_d);

                EndPaint(hwnd, &ps);
                return 0;
            }            case WM_DESTROY:
                KillTimer(hwnd, 200);
                KillTimer(hwnd, 201);
                KillTimer(hwnd, 202);
                Theme::DestroyFontSet(hud_fonts);
                PostQuitMessage(0);
                return 0;
        }
        return DefWindowProcW(hwnd, msg, wparam, lparam);
    }

    static std::wstring SpeedLabel() {
        wchar_t buf[16];
        swprintf(buf, 16, L"%.2fx", playback_speed);
        return buf;
    }

    static int RunOverlayLoop(
        const fs::path& game_dir = "",
        const std::string& primary_lang = "en",
        const std::string& secondary_lang = "de",
        double initial_speed = 1.0,
        const DualTitle::DualTitleConfig::AppConfig& cfg_in =
            DualTitle::DualTitleConfig::AppConfig{},
        const GameProfile* profile = nullptr
    ) {
        Theme::EnablePerMonitorDpi();
        Theme::BootGdiplus();
        cfg = cfg_in;

        // M0.6: Load dictionaries/*.json
        fs::path dict_dir = fs::path("dictionaries");
        if (fs::exists(dict_dir)) {
            std::ostringstream log_ss;
            FamousDictionary::LoadDictionariesFromDir(dict_dir, &log_ss);
            std::cout << log_ss.str();
        }

        active_game_dir = game_dir;
        playback_speed = (initial_speed == 1.0 && cfg.playback_speed != 1.0)
                            ? cfg.playback_speed : initial_speed;
        active_lines = SubtitleMerger::IndexGameSubtitlesReadOnly(
            game_dir, primary_lang, secondary_lang,
            game_dir.empty() ? nullptr : profile, &std::cout);
        current_line_idx = 0;
        hovered_word = -1;
        reveal_active = false;
        card_req = 0; card_loaded = false; card_word.clear();
        game_is_exclusive_fs = false;
        DictSvc::Start();

        HINSTANCE hInst = GetModuleHandleW(nullptr);
        const wchar_t* clsName = L"DualTitleAuroraOverlayV5";

        WNDCLASSW wc = {};
        wc.lpfnWndProc = OverlayWndProc;
        wc.hInstance = hInst;
        wc.lpszClassName = clsName;
        wc.hCursor = LoadCursor(nullptr, IDC_HAND);
        RegisterClassW(&wc);

        // M0.3: Use WS_EX_TRANSPARENT so the HUD body doesn't eat clicks,
        // but we'll handle mouse on the control bar via hit-testing in WM_NCHITTEST
        HWND hwnd = CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE | WS_EX_TRANSPARENT,
            clsName, L"DualTitle In-Game Overlay",
            WS_POPUP | WS_VISIBLE,
            CW_USEDEFAULT, CW_USEDEFAULT, 0, 0,
            nullptr, nullptr, hInst, nullptr
        );
        if (!hwnd) return 1;

        hud_dpi = Theme::WindowDpi(hwnd);
        Theme::MakeFontSet(hud_dpi, hud_fonts);
        EnsureLargeFonts(hud_dpi);

        int screenW = GetSystemMetrics(SM_CXSCREEN);
        int screenH = GetSystemMetrics(SM_CYSCREEN);
        int wndW = std::min<int>(Theme::S(1080, hud_dpi), screenW - Theme::S(40, hud_dpi));
        int wndH = Theme::S(156, hud_dpi);
        int posX = (screenW - wndW) / 2;
        int posY = screenH - wndH - Theme::S(56, hud_dpi);
        SetWindowPos(hwnd, HWND_TOPMOST, posX, posY, wndW, wndH, SWP_NOACTIVATE | SWP_SHOWWINDOW);

        SetLayeredWindowAttributes(hwnd, 0, 236, LWA_ALPHA);
        ShowWindow(hwnd, SW_SHOWNOACTIVATE);
        UpdateWindow(hwnd);

        // Remappable hotkeys + reveal poll timer + subtitle cadence from config
        ApplyHotkeys(hwnd);
        SetTimer(hwnd, 202, 16, nullptr);      // 16 ms fast tick: hover + reveal
        auto_play_enabled = cfg.auto_play;
        UpdateSpeedTimer(hwnd);

        std::cout << "  [DualTitle C++ Overlay] Aurora HUD active (100% Anti-Cheat Safe Out-of-Process)\n"
                  << "    - HOLD " << DualTitle::DualTitleConfig::ActionLabel("reveal_words")
                  << " key (" << (FindBinding(cfg, "reveal_words")
                                      ? FindBinding(cfg, "reveal_words")->key : "<unset>")
                  << ") to hover subtitle words -- a dictionary card pops up\n"
                  << "    - Buttons: [Pause Game] sends your mapped pause key, [Pause Subs] freezes cadence\n"
                  << "    - [-] / [+] control subtitle speed (0.25x - 2.00x)\n"
                  << "    - Every hotkey is remappable in the Control Panel (Hotkeys & Style)\n";

        MSG msg;
        while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        CleanupLargeFonts();
        DictSvc::Stop();          // join worker before leaving the message loop
        return 0;
    }
};

#endif // _WIN32

} // namespace DualTitle
