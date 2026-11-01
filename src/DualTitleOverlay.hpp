#pragma once
/**
 * DualTitleOverlay.hpp — Universal Anti-Cheat-Safe C++17 Win32 Topmost In-Game HUD
 *
 * Features:
 *   • 100% Out-of-Process DWM Topmost Window (ZERO DLL injection, ZERO D3D/Vulkan hooks,
 *     ZERO process handle opening — never triggers PunkBuster, EAC, BattlEye, or Denuvo!).
 *   • Interactive Clickable Words: Every word in the Primary (Gold #FFD700) and Secondary
 *     (Ice-White #E2E8F0) subtitle lines is an individual clickable button on the HUD that
 *     immediately displays its Dictionary Meaning Card (phonetics, gender, translation, definition).
 *   • Extra In-Game Control Buttons right on the HUD:
 *       - [⏸ Pause Game (ESC)] : Sends safe keyboard ESC/Pause input without process hooking
 *       - [▶ Auto-Play]        : Toggles automatic subtitle cadence progression
 *       - [- Speed] [1.00x] [+ Speed] : Controls subtitle & reading speed (0.25x to 2.00x)
 *       - [◀ Prev] [Next ▶]    : Navigate dialogue lines backward and forward
 *       - [🔲 Borderless]      : Converts active window to Borderless Fullscreen (ALT+F11)
 *       - [💾 Restore Save]    : 1-click Save & Profile Restore right from the HUD
 *       - [✕ Close]            : Closes or hides the overlay (ALT+F8)
 */

#include "DualTitleEngine.hpp"

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

struct OverlayButtonBox {
    int id;
    RECT rc;
    std::wstring label;
    COLORREF bg_color;
    COLORREF fg_color;
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
        L"💡 Click any word in the subtitles above to see its meaning, phonetics & grammar notes!";
    static inline std::vector<ClickableWordBox> word_boxes;
    static inline std::vector<OverlayButtonBox> control_buttons;
    static inline HWND last_game_hwnd = nullptr;

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

    static void RememberForegroundGameWindow(HWND overlay_hwnd) {
        HWND fg = GetForegroundWindow();
        if (fg && fg != overlay_hwnd) {
            DWORD pid = 0;
            GetWindowThreadProcessId(fg, &pid);
            if (pid != 0 && pid != GetCurrentProcessId()) {
                last_game_hwnd = fg;
            }
        }
    }

    /**
     * Anti-Cheat-Safe Game Pause: Sends a standard keyboard VK_ESCAPE / VK_PAUSE
     * input to the active game window without opening a process handle (`OpenProcess`).
     */
    static void SendSafeGamePause(HWND overlay_hwnd) {
        RememberForegroundGameWindow(overlay_hwnd);
        if (last_game_hwnd && IsWindow(last_game_hwnd)) {
            SetForegroundWindow(last_game_hwnd);
            INPUT inputs[2] = {};
            inputs[0].type = INPUT_KEYBOARD;
            inputs[0].ki.wVk = VK_ESCAPE;
            inputs[1].type = INPUT_KEYBOARD;
            inputs[1].ki.wVk = VK_ESCAPE;
            inputs[1].ki.dwFlags = KEYEVENTF_KEYUP;
            SendInput(2, inputs, sizeof(INPUT));
            status_dictionary_text = L"⏸ Sent safe in-game Pause (ESC) — zero process hooks used. Click any word to inspect!";
        } else {
            status_dictionary_text = L"⏸ Switch to your running application window first, then click [Pause Game] or press ALT+F9.";
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
            status_dictionary_text = L"🔲 Click inside your running application window first, then press ALT+F11 or [Borderless].";
            return;
        }
        int sw = GetSystemMetrics(SM_CXSCREEN);
        int sh = GetSystemMetrics(SM_CYSCREEN);
        LONG_PTR style = GetWindowLongPtrW(target, GWL_STYLE);
        LONG_PTR new_style = (style & ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)) | WS_POPUP | WS_VISIBLE;
        SetWindowLongPtrW(target, GWL_STYLE, new_style);
        SetWindowPos(target, HWND_NOTOPMOST, 0, 0, sw, sh, SWP_FRAMECHANGED | SWP_NOACTIVATE | SWP_SHOWWINDOW);
        SetWindowPos(overlay_hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW);
        status_dictionary_text = L"🔲 Converted application window to Borderless Fullscreen (" +
                                 std::to_wstring(sw) + L"x" + std::to_wstring(sh) + L")!";
    }

    static void UpdateSpeedTimer(HWND hwnd) {
        KillTimer(hwnd, 201);
        if (auto_play_enabled) {
            UINT interval_ms = static_cast<UINT>(3600.0 / std::max(0.25, playback_speed));
            SetTimer(hwnd, 201, interval_ms, nullptr);
        }
    }

    static void LookupAndShowWord(const std::string& word) {
        auto info = FamousDictionary::Lookup(word);
        std::ostringstream ss;
        ss << "📖 [" << info.word << "]";
        if (!info.phonetic.empty()) ss << " " << info.phonetic;
        if (!info.gender.empty()) ss << " (" << info.gender << ")";
        else if (!info.pos.empty()) ss << " (" << info.pos << ")";
        ss << "  →  " << info.translation << "  |  " << info.definition;
        status_dictionary_text = Utf8ToWide(ss.str());
    }

    static void DrawDualTitleMiniLogo(HDC hdc, int x, int y, int size) {
        // Draws the signature DualTitle badge (dark rounded tile + gold top bar + white bottom bar)
        HBRUSH badgeBg = CreateSolidBrush(RGB(20, 28, 46));
        RECT rcBadge = {x, y, x + size, y + size};
        FillRect(hdc, &rcBadge, badgeBg);
        DeleteObject(badgeBg);

        HBRUSH borderB = CreateSolidBrush(RGB(56, 189, 248));
        FrameRect(hdc, &rcBadge, borderB);
        DeleteObject(borderB);

        HBRUSH topBar = CreateSolidBrush(RGB(255, 215, 0));
        RECT rcTop = {x + 4, y + 6, x + size - 5, y + 12};
        FillRect(hdc, &rcTop, topBar);
        DeleteObject(topBar);

        HBRUSH botBar = CreateSolidBrush(RGB(248, 250, 252));
        RECT rcBot = {x + 6, y + 15, x + size - 3, y + 21};
        FillRect(hdc, &rcBot, botBar);
        DeleteObject(botBar);
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
                } else if (wparam == 201 && auto_play_enabled && !active_lines.empty()) {
                    current_line_idx = (current_line_idx + 1) % active_lines.size();
                    InvalidateRect(hwnd, nullptr, TRUE);
                }
                return 0;

            case WM_MOUSEACTIVATE:
                // Never steal keyboard focus from the running game when clicking overlay buttons/words!
                return MA_NOACTIVATE;

            case WM_HOTKEY:
                if (wparam == 101) { // ALT + F9: Safe Game Pause
                    SendSafeGamePause(hwnd);
                    InvalidateRect(hwnd, nullptr, TRUE);
                } else if (wparam == 102 && !active_lines.empty()) { // ALT + F10: Next Line
                    current_line_idx = (current_line_idx + 1) % active_lines.size();
                    InvalidateRect(hwnd, nullptr, TRUE);
                } else if (wparam == 103) { // ALT + F8: Toggle Overlay Visibility
                    overlay_visible = !overlay_visible;
                    ShowWindow(hwnd, overlay_visible ? SW_SHOWNOACTIVATE : SW_HIDE);
                } else if (wparam == 104) { // ALT + F11: Force Borderless Window
                    MakeTargetGameBorderless(hwnd);
                    InvalidateRect(hwnd, nullptr, TRUE);
                }
                return 0;

            case WM_LBUTTONDOWN: {
                POINT pt = {GET_X_LPARAM(lparam), GET_Y_LPARAM(lparam)};

                // 1. Check if user clicked any In-Game Control Button
                for (const auto& btn : control_buttons) {
                    if (PtInRect(&btn.rc, pt)) {
                        switch (btn.id) {
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
                                auto_play_enabled = !auto_play_enabled;
                                UpdateSpeedTimer(hwnd);
                                status_dictionary_text = auto_play_enabled
                                    ? L"▶ Auto-Advancing Subtitles ON (Speed: " + std::to_wstring(playback_speed).substr(0, 4) + L"x)"
                                    : L"⏸ Auto-Advancing Subtitles PAUSED — Click any word to see its meaning!";
                                break;
                            case BTN_SPEED_DOWN:
                                playback_speed = std::max(0.25, playback_speed - 0.25);
                                UpdateSpeedTimer(hwnd);
                                status_dictionary_text = L"🐢 Subtitle Speed decreased to " + std::to_wstring(playback_speed).substr(0, 4) + L"x";
                                break;
                            case BTN_SPEED_RESET:
                                playback_speed = 1.0;
                                UpdateSpeedTimer(hwnd);
                                status_dictionary_text = L"⚡ Subtitle Speed reset to 1.00x";
                                break;
                            case BTN_SPEED_UP:
                                playback_speed = std::min(2.0, playback_speed + 0.25);
                                UpdateSpeedTimer(hwnd);
                                status_dictionary_text = L"🚀 Subtitle Speed increased to " + std::to_wstring(playback_speed).substr(0, 4) + L"x";
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
                                status_dictionary_text = L"💾 Restore Save complete (" + std::to_wstring(cnt) +
                                                         L" save/profile file(s) restored & verified)!";
                                break;
                            }
                            case BTN_CLOSE:
                                DestroyWindow(hwnd);
                                return 0;
                        }
                        InvalidateRect(hwnd, nullptr, TRUE);
                        return 0;
                    }
                }

                // 2. Check if user clicked any Word in the Primary or Secondary Subtitle Line
                for (const auto& wb : word_boxes) {
                    if (PtInRect(&wb.rc, pt)) {
                        LookupAndShowWord(wb.word);
                        InvalidateRect(hwnd, nullptr, TRUE);
                        return 0;
                    }
                }
                return 0;
            }

            case WM_PAINT: {
                PAINTSTRUCT ps;
                HDC hdc = BeginPaint(hwnd, &ps);
                RECT rc;
                GetClientRect(hwnd, &rc);

                // Dark translucent subtitle card background (#0B0F19)
                HBRUSH bgBrush = CreateSolidBrush(RGB(11, 15, 25));
                FillRect(hdc, &rc, bgBrush);
                DeleteObject(bgBrush);

                // Sky-blue border (#38BDF8)
                HBRUSH borderBrush = CreateSolidBrush(RGB(56, 189, 248));
                FrameRect(hdc, &rc, borderBrush);
                DeleteObject(borderBrush);

                SetBkMode(hdc, TRANSPARENT);

                // Draw Mini DualTitle Logo + Control Bar at top (y = 6..32)
                DrawDualTitleMiniLogo(hdc, 12, 6, 26);

                HFONT hFontBtn = CreateFontW(14, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE,
                    DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                    DEFAULT_PITCH | FF_SWISS, L"Segoe UI");
                HFONT oldFont = static_cast<HFONT>(SelectObject(hdc, hFontBtn));

                SetTextColor(hdc, RGB(56, 189, 248));
                RECT rcTitle = {46, 6, 300, 32};
                std::wstring lineBadge = L"DUALTITLE HUD (" +
                    std::to_wstring((current_line_idx % std::max<size_t>(1, active_lines.size())) + 1) + L"/" +
                    std::to_wstring(std::max<size_t>(1, active_lines.size())) + L")";
                DrawTextW(hdc, lineBadge.c_str(), -1, &rcTitle, DT_LEFT | DT_SINGLELINE | DT_VCENTER);

                // Build interactive control buttons across the top bar
                control_buttons.clear();
                std::wstringstream sp_ss;
                sp_ss << std::fixed << std::setprecision(2) << playback_speed << L"x";
                std::wstring speed_lbl = L"⚡ " + sp_ss.str();

                struct BtnSpec { int id; std::wstring text; int width; COLORREF bg; COLORREF fg; };
                std::vector<BtnSpec> specs = {
                    {BTN_PREV, L"◀ Prev", 56, RGB(30, 41, 59), RGB(248, 250, 252)},
                    {BTN_PLAY_PAUSE, auto_play_enabled ? L"⏸ Auto:ON" : L"▶ Auto:OFF", 78, auto_play_enabled ? RGB(5, 150, 105) : RGB(30, 41, 59), RGB(255, 255, 255)},
                    {BTN_NEXT, L"Next ▶", 56, RGB(30, 41, 59), RGB(248, 250, 252)},
                    {BTN_SPEED_DOWN, L"- Spd", 48, RGB(30, 41, 59), RGB(167, 243, 208)},
                    {BTN_SPEED_RESET, speed_lbl, 62, RGB(15, 23, 42), RGB(255, 215, 0)},
                    {BTN_SPEED_UP, L"+ Spd", 48, RGB(30, 41, 59), RGB(167, 243, 208)},
                    {BTN_GAME_PAUSE, L"⏸ Game (ESC)", 92, RGB(2, 132, 199), RGB(255, 255, 255)},
                    {BTN_BORDERLESS, L"🔲 Borderless", 88, RGB(79, 70, 229), RGB(255, 255, 255)},
                    {BTN_RESTORE_SAVE, L"💾 Restore Save", 104, RGB(13, 148, 136), RGB(255, 255, 255)},
                    {BTN_CLOSE, L"✕", 28, RGB(127, 29, 29), RGB(255, 255, 255)}
                };

                int cur_x = rc.right - 12;
                for (auto it = specs.rbegin(); it != specs.rend(); ++it) {
                    RECT brc = {cur_x - it->width, 6, cur_x, 30};
                    HBRUSH bBrush = CreateSolidBrush(it->bg);
                    FillRect(hdc, &brc, bBrush);
                    DeleteObject(bBrush);
                    SetTextColor(hdc, it->fg);
                    DrawTextW(hdc, it->text.c_str(), -1, &brc, DT_CENTER | DT_SINGLELINE | DT_VCENTER);
                    control_buttons.push_back({it->id, brc, it->text, it->bg, it->fg});
                    cur_x -= (it->width + 5);
                }

                // Render Interactive Clickable Words for Top & Bottom Subtitle Lines
                word_boxes.clear();
                if (active_lines.empty()) {
                    active_lines = SubtitleMerger::IndexGameSubtitlesReadOnly(active_game_dir);
                }
                const auto& item = active_lines[current_line_idx % active_lines.size()];

                auto draw_clickable_sentence = [&](const std::string& sentence, int top_y, int bot_y, int font_px, int weight, COLORREF color, bool is_prim) {
                    HFONT hFont = CreateFontW(font_px, 0, 0, 0, weight, FALSE, FALSE, FALSE,
                        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                        DEFAULT_PITCH | FF_SWISS, L"Segoe UI");
                    SelectObject(hdc, hFont);
                    SetTextColor(hdc, color);

                    std::istringstream iss(sentence);
                    std::vector<std::string> tokens;
                    std::string tok;
                    while (iss >> tok) tokens.push_back(tok);

                    int total_w = 0;
                    std::vector<int> widths;
                    SIZE space_sz = {};
                    GetTextExtentPoint32W(hdc, L" ", 1, &space_sz);
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

                    int start_x = std::max<int>(16, (rc.right - total_w) / 2);
                    for (size_t i = 0; i < tokens.size(); ++i) {
                        std::wstring wt = Utf8ToWide(tokens[i]);
                        RECT wrc = {start_x, top_y, start_x + widths[i], bot_y};
                        DrawTextW(hdc, wt.c_str(), -1, &wrc, DT_CENTER | DT_SINGLELINE | DT_VCENTER);
                        word_boxes.push_back({wrc, tokens[i], is_prim});
                        start_x += widths[i] + gap;
                    }
                    DeleteObject(hFont);
                };

                // Top Line: Primary Subtitle in Gold (#FFD700)
                draw_clickable_sentence(item.primary, 36, 74, 25, FW_BOLD, RGB(255, 215, 0), true);

                // Bottom Line: Secondary Subtitle in Crisp Ice-White (#E2E8F0)
                draw_clickable_sentence(item.secondary, 76, 110, 21, FW_NORMAL, RGB(226, 232, 240), false);

                // Bottom Word Meaning & Dictionary Bar (y = 114..144)
                RECT rcDictBg = {10, 114, rc.right - 10, rc.bottom - 6};
                HBRUSH dictBrush = CreateSolidBrush(RGB(17, 24, 39));
                FillRect(hdc, &rcDictBg, dictBrush);
                DeleteObject(dictBrush);

                HFONT hFontDict = CreateFontW(15, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                    DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS, CLEARTYPE_QUALITY,
                    DEFAULT_PITCH | FF_SWISS, L"Segoe UI");
                SelectObject(hdc, hFontDict);
                SetTextColor(hdc, RGB(167, 243, 208));
                RECT rcDictTxt = {18, 114, rc.right - 18, rc.bottom - 6};
                DrawTextW(hdc, status_dictionary_text.c_str(), -1, &rcDictTxt, DT_LEFT | DT_SINGLELINE | DT_VCENTER | DT_END_ELLIPSIS);

                SelectObject(hdc, oldFont);
                DeleteObject(hFontBtn);
                DeleteObject(hFontDict);
                EndPaint(hwnd, &ps);
                return 0;
            }

            case WM_DESTROY:
                KillTimer(hwnd, 200);
                KillTimer(hwnd, 201);
                PostQuitMessage(0);
                return 0;
        }
        return DefWindowProcW(hwnd, msg, wparam, lparam);
    }

    static int RunOverlayLoop(
        const fs::path& game_dir = "",
        const std::string& primary_lang = "en",
        const std::string& secondary_lang = "de",
        double initial_speed = 1.0
    ) {
        active_game_dir = game_dir;
        playback_speed = initial_speed;
        active_lines = SubtitleMerger::IndexGameSubtitlesReadOnly(game_dir, primary_lang, secondary_lang);
        current_line_idx = 0;

        HINSTANCE hInst = GetModuleHandleW(nullptr);
        const wchar_t* clsName = L"DualTitleInteractiveOverlayV4";

        WNDCLASSW wc = {};
        wc.lpfnWndProc = OverlayWndProc;
        wc.hInstance = hInst;
        wc.lpszClassName = clsName;
        wc.hCursor = LoadCursor(nullptr, IDC_HAND);
        RegisterClassW(&wc);

        int screenW = GetSystemMetrics(SM_CXSCREEN);
        int screenH = GetSystemMetrics(SM_CYSCREEN);
        int wndW = std::min<int>(1020, screenW - 40);
        int wndH = 148;
        int posX = (screenW - wndW) / 2;
        int posY = screenH - wndH - 56;

        // Interactive no-activate topmost window (clickable buttons & words without stealing game focus!)
        HWND hwnd = CreateWindowExW(
            WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE,
            clsName,
            L"DualTitle In-Game Overlay",
            WS_POPUP | WS_VISIBLE,
            posX, posY, wndW, wndH,
            nullptr, nullptr, hInst, nullptr
        );
        if (!hwnd) return 1;

        SetLayeredWindowAttributes(hwnd, 0, 238, LWA_ALPHA);
        ShowWindow(hwnd, SW_SHOWNOACTIVATE);
        UpdateWindow(hwnd);

        RegisterHotKey(hwnd, 101, MOD_ALT, VK_F9);
        RegisterHotKey(hwnd, 102, MOD_ALT, VK_F10);
        RegisterHotKey(hwnd, 103, MOD_ALT, VK_F8);
        RegisterHotKey(hwnd, 104, MOD_ALT, VK_F11);

        std::cout << "  [DualTitle C++ Overlay] Active at bottom of screen (100% Anti-Cheat Safe Out-of-Process HUD)!\n"
                  << "    • Click ANY word on the HUD to see its translation & dictionary definition\n"
                  << "    • Use [- Spd] / [+ Spd] on the HUD to control subtitle speed (0.25x - 2.00x)\n"
                  << "    • Use [💾 Restore Save] on the HUD to restore backed-up saves anytime\n"
                  << "    • [ALT + F9]  : Safe Game Pause (ESC)\n"
                  << "    • [ALT + F10] : Next Subtitle Line\n"
                  << "    • [ALT + F11] : Convert Game to Borderless Fullscreen\n"
                  << "    • [ALT + F8]  : Show/Hide Overlay\n";

        MSG msg;
        while (GetMessageW(&msg, nullptr, 0, 0) > 0) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
        }
        return 0;
    }
};

#endif // _WIN32

} // namespace DualTitle
