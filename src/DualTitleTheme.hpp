#pragma once
/**
 * DualTitleTheme.hpp -- "Aurora" Modern-Minimal Design System (C++17 / Win32)
 *
 * A small, dependency-free design language shared by the DualTitle Control Panel
 * and the In-Game Overlay HUD:
 *
 *   * Dark charcoal palette with sky-blue (#38BDF8) + gold (#FFD700) accents
 *   * Segoe UI Variable typography (auto-fallback to Segoe UI), DPI-scaled fonts
 *   * Anti-aliased rounded cards / buttons / pills rendered with GDI+
 *   * Flat owner-drawn buttons with hover + pressed states (no child controls)
 *
 * 100% cosmetic layer -- never touches game processes (anti-cheat safe by design).
 */

#include "DualTitleEngine.hpp"

#ifdef _WIN32

#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <objidl.h>
#include <gdiplus.h>
#pragma comment(lib, "gdiplus.lib")

#include <string>
#include <vector>
#include <map>

namespace DualTitle {
namespace Theme {

// ============================================================================
// 1. Aurora Palette
// ============================================================================

inline namespace Palette {
    constexpr COLORREF Window      = RGB(11, 14, 19);    // #0B0E13 deep charcoal
    constexpr COLORREF Card        = RGB(18, 22, 30);    // #12161E surface
    constexpr COLORREF CardBorder  = RGB(33, 39, 51);    // #212733 hairline
    constexpr COLORREF Inner       = RGB(13, 17, 24);    // #0D1118 fields / HUD
    constexpr COLORREF ListSel     = RGB(24, 36, 52);    // selected list row
    constexpr COLORREF TextTitle   = RGB(244, 246, 251); // headings
    constexpr COLORREF TextBody    = RGB(213, 220, 231); // controls text
    constexpr COLORREF TextMuted   = RGB(139, 152, 174); // secondary labels
    constexpr COLORREF TextFaint   = RGB(99, 111, 133);  // placeholders / section labels
    constexpr COLORREF Accent      = RGB(56, 189, 248);  // #38BDF8 sky
    constexpr COLORREF PrimaryBtn  = RGB(2, 132, 199);   // launch button
    constexpr COLORREF PrimaryHov  = RGB(14, 165, 233);
    constexpr COLORREF Gold        = RGB(255, 215, 0);
    constexpr COLORREF TealBtn     = RGB(13, 148, 136);  // restore/save actions
    constexpr COLORREF TealHov     = RGB(20, 184, 166);
    constexpr COLORREF GhostFill   = RGB(23, 28, 38);
    constexpr COLORREF GhostHover  = RGB(31, 38, 51);
    constexpr COLORREF GhostBorder = RGB(42, 49, 63);
    constexpr COLORREF DangerFill  = RGB(51, 22, 26);
    constexpr COLORREF DangerHov   = RGB(72, 30, 34);
    constexpr COLORREF DangerText  = RGB(248, 113, 113);
    constexpr COLORREF StatusOk    = RGB(52, 211, 153);  // green status dot
    constexpr COLORREF StatusWarn  = RGB(251, 191, 36);  // amber status dot
    constexpr COLORREF StatusInfo  = RGB(56, 189, 248);  // sky status dot
    constexpr COLORREF DictText    = RGB(158, 230, 196); // HUD dictionary bar
    constexpr COLORREF IceWhite    = RGB(226, 232, 240); // secondary HUD line
}

// ============================================================================
// 2. DPI Scaling & Font Factory (Segoe UI Variable -> Segoe UI fallback)
// ============================================================================

/** Best UI font face available on this Windows version (probed once). */
inline const wchar_t* UiFace() {
    static const wchar_t* face = []() -> const wchar_t* {
        struct Cand { const wchar_t* name; };
        const Cand cands[3] = {
            {L"Segoe UI Variable Display"},
            {L"Segoe UI Variable Text"},
            {L"Segoe UI"}
        };
        HDC dc = GetDC(nullptr);
        const wchar_t* chosen = L"Segoe UI";
        for (const auto& c : cands) {
            HFONT t = CreateFontW(-14, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
                DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
                CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, c.name);
            HGDIOBJ old = SelectObject(dc, t);
            wchar_t fbuf[64] = {};
            GetTextFaceW(dc, 64, fbuf);
            SelectObject(dc, old);
            DeleteObject(t);
            if (wcscmp(fbuf, c.name) == 0) { chosen = c.name; break; }
        }
        ReleaseDC(nullptr, dc);
        return chosen;
    }();
    return face;
}

/** Logical (96-dpi) pixels -> physical pixels for a DPI value. */
inline int S(int logical, int dpi) {
    return MulDiv(logical, dpi, 96);
}

/** Enables Per-Monitor V2 DPI awareness at runtime (Windows 10 1703+; graceful fallback). */
inline void EnablePerMonitorDpi() {
    HMODULE u32 = GetModuleHandleW(L"user32.dll");
    if (!u32) return;
    using CtxFn = DPI_AWARENESS_CONTEXT (WINAPI*)(DPI_AWARENESS_CONTEXT);
    auto setCtx = reinterpret_cast<CtxFn>(GetProcAddress(u32, "SetProcessDpiAwarenessContext"));
    if (setCtx) {
        if (setCtx(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)) return;
        setCtx(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE);
        return;
    }
    SetProcessDPIAware();
}

/** DPI of a window (works during WM_CREATE; falls back to screen DPI). */
inline int WindowDpi(HWND hwnd) {
    using DpiFn = UINT (WINAPI*)(HWND);
    static DpiFn fn = []() -> DpiFn {
        HMODULE u32 = GetModuleHandleW(L"user32.dll");
        return reinterpret_cast<DpiFn>(GetProcAddress(u32, "GetDpiForWindow"));
    }();
    if (fn) {
        UINT d = fn(hwnd);
        if (d != 0) return static_cast<int>(d);
    }
    HDC dc = GetDC(hwnd);
    int dpi_x = GetDeviceCaps(dc, LOGPIXELSX);
    ReleaseDC(hwnd, dc);
    return dpi_x;
}

/** Creates a DPI-scaled UI font. `logical_px` is the point-ish size @96dpi. */
inline HFONT MakeFont(int dpi, int logical_px, int weight, bool italic = false) {
    int h = -MulDiv(logical_px, dpi, 96);
    return CreateFontW(h, 0, 0, 0, weight, italic, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        CLEARTYPE_QUALITY, DEFAULT_PITCH | FF_DONTCARE, UiFace());
}

// ============================================================================
// 3. GDI+ Rounded Art
// ============================================================================

namespace detail {
    inline ULONG_PTR g_gdiplus_token = 0;

    inline void AddRoundPath(Gdiplus::GraphicsPath& path, int x, int y, int w, int h, int radius) {
        if (w <= 0 || h <= 0) return;
        int r = radius;
        r = std::min(r, std::min(w, h) / 2);
        if (r <= 0) { path.AddRectangle(Gdiplus::Rect(x, y, w, h)); return; }
        path.AddArc(x, y, r, r, 180, 90);
        path.AddArc(x + w - r, y, r, r, 270, 90);
        path.AddArc(x + w - r, y + h - r, r, r, 0, 90);
        path.AddArc(x, y + h - r, r, r, 90, 90);
        path.CloseFigure();
    }
} // namespace detail

inline void BootGdiplus() {
    static bool booted = []() {
        Gdiplus::GdiplusStartupInput input;
        return Gdiplus::GdiplusStartup(&detail::g_gdiplus_token, &input, nullptr) == Gdiplus::Ok;
    }();
    (void)booted;
}

/** Anti-aliased rounded rectangle fill (optionally with a 1px hairline border). */
inline void RoundRectFill(HDC hdc, RECT rc, int radius, COLORREF fill,
                          int alpha_fill = 255,
                          COLORREF border = 0, int alpha_border = 255) {
    BootGdiplus();
    int w = rc.right - rc.left, h = rc.bottom - rc.top;
    if (w <= 0 || h <= 0) return;
    Gdiplus::Graphics g(hdc);
    g.SetSmoothingMode(Gdiplus::SmoothingModeAntiAlias);
    Gdiplus::GraphicsPath path;
    detail::AddRoundPath(path, rc.left, rc.top, w - 1, h - 1, radius);
    Gdiplus::SolidBrush brush(Gdiplus::Color(
        static_cast<BYTE>(alpha_fill), GetRValue(fill), GetGValue(fill), GetBValue(fill)));
    g.FillPath(&brush, &path);
    if (border != 0) {
        Gdiplus::Pen pen(Gdiplus::Color(
            static_cast<BYTE>(alpha_border), GetRValue(border), GetGValue(border), GetBValue(border)), 1.0f);
        g.DrawPath(&pen, &path);
    }
}

/** Anti-aliased filled circle (status dots, glyphs). */
inline void FillCircle(HDC hdc, int cx, int cy, int radius, COLORREF color, int alpha = 255) {
    BootGdiplus();
    Gdiplus::Graphics g(hdc);
    g.SetSmoothingMode(Gdiplus::SmoothingModeAntiAlias);
    Gdiplus::SolidBrush brush(Gdiplus::Color(
        static_cast<BYTE>(alpha), GetRValue(color), GetGValue(color), GetBValue(color)));
    g.FillEllipse(&brush, cx - radius, cy - radius, radius * 2, radius * 2);
}

/** Linear color blend (t=0 -> a, t=1 -> b). */
inline COLORREF Blend(COLORREF a, COLORREF b, double t) {
    t = std::max(0.0, std::min(1.0, t));
    int r = static_cast<int>(GetRValue(a) + (GetRValue(b) - GetRValue(a)) * t);
    int g = static_cast<int>(GetGValue(a) + (GetGValue(b) - GetGValue(a)) * t);
    int bl = static_cast<int>(GetBValue(a) + (GetBValue(b) - GetBValue(a)) * t);
    return RGB(r, g, bl);
}

// ============================================================================
// 4. Flat Owner-Drawn Buttons (hover + pressed, no child controls)
// ============================================================================

enum BtnKind { BtnGhost = 0, BtnPrimary = 1, BtnTeal = 2, BtnDanger = 3 };

struct FlatBtn {
    int id;
    RECT rc{};
    std::wstring label;
    BtnKind kind = BtnGhost;
    bool is_toggle = false;       // shows a state dot + colored label (e.g. Auto)
    bool toggle_on = false;
    COLORREF text_override = 0;   // 0 = use kind default text color
};

struct BtnState {
    bool hover = false;
    bool pressed = false;
};

struct FontSet {
    HFONT title = nullptr;    // 20px semibold
    HFONT sub = nullptr;      // 12px normal
    HFONT section = nullptr;  // 10px semibold (letter-spaced)
    HFONT body = nullptr;     // 14px normal (combos, edit, labels)
    HFONT btn = nullptr;      // 13px semibold (buttons)
    HFONT status = nullptr;   // 13px normal
};

inline void MakeFontSet(int dpi, FontSet& out) {
    out.title = MakeFont(dpi, 20, FW_SEMIBOLD);
    out.sub = MakeFont(dpi, 12, FW_NORMAL);
    out.section = MakeFont(dpi, 10, FW_SEMIBOLD);
    out.body = MakeFont(dpi, 14, FW_NORMAL);
    out.btn = MakeFont(dpi, 13, FW_SEMIBOLD);
    out.status = MakeFont(dpi, 13, FW_NORMAL);
}

inline void DestroyFontSet(FontSet& f) {
    for (HFONT* h : {&f.title, &f.sub, &f.section, &f.body, &f.btn, &f.status}) {
        if (*h) { DeleteObject(*h); *h = nullptr; }
    }
}

inline COLORREF BtnFill(BtnKind kind, bool hover, bool pressed) {
    switch (kind) {
        case BtnPrimary: return pressed ? Blend(PrimaryBtn, Window, 0.25)
                                 : hover ? PrimaryHov : PrimaryBtn;
        case BtnTeal:    return pressed ? Blend(TealBtn, Window, 0.25)
                                 : hover ? TealHov : TealBtn;
        case BtnDanger:  return hover ? DangerHov : DangerFill;
        default:         return pressed ? Blend(GhostFill, Window, 0.28)
                                 : hover ? GhostHover : GhostFill;
    }
}

inline COLORREF BtnText(BtnKind kind, const FlatBtn& btn) {
    switch (kind) {
        case BtnPrimary:
        case BtnTeal:    return RGB(255, 255, 255);
        case BtnDanger:  return DangerText;
        default:
            if (btn.is_toggle && btn.toggle_on) return StatusOk;
            return TextBody;
    }
}

inline COLORREF BtnBorder(BtnKind kind) {
    switch (kind) {
        case BtnDanger: return RGB(127, 29, 29);
        default:        return GhostBorder;
    }
}

inline void DrawTextCentered(HDC hdc, const std::wstring& text, RECT rc, HFONT font, COLORREF color) {
    HFONT old = static_cast<HFONT>(SelectObject(hdc, font));
    SetBkMode(hdc, TRANSPARENT);
    SetTextColor(hdc, color);
    DrawTextW(hdc, text.c_str(), -1, &rc, DT_CENTER | DT_VCENTER | DT_SINGLELINE | DT_END_ELLIPSIS | DT_NOPREFIX);
    SelectObject(hdc, old);
}

inline void DrawBtn(HDC hdc, const FlatBtn& btn, const BtnState& st, int dpi, HFONT font) {
    int radius = S(8, dpi);
    COLORREF fill = BtnFill(btn.kind, st.hover, st.pressed);
    COLORREF tx = btn.text_override ? btn.text_override : BtnText(btn.kind, btn);
    if (btn.is_toggle && !btn.toggle_on && st.hover) tx = TextBody;
    COLORREF border = (btn.kind == BtnGhost || btn.kind == BtnDanger) ? BtnBorder(btn.kind) : 0;
    RoundRectFill(hdc, btn.rc, radius, fill, 255, border, 210);

    // Draw the label, with a toggle indicator dot on the left if requested.
    RECT label_rc = btn.rc;
    if (btn.is_toggle) {
        int dot_r = S(4, dpi);
        int cy = (btn.rc.top + btn.rc.bottom) / 2;
        FillCircle(hdc, btn.rc.left + S(14, dpi), cy, dot_r,
                   btn.toggle_on ? StatusOk : TextFaint);
        label_rc.left += S(8, dpi);
    }
    DrawTextCentered(hdc, btn.label, label_rc, font, tx);
}

// ============================================================================
// 5. Text Helpers
// ============================================================================

/** Left-aligned text, optional letter-spacing (for small-caps section labels). */
inline void DrawLabel(HDC hdc, const std::wstring& text, RECT rc, HFONT font,
                      COLORREF color, int char_extra = 0,
                      UINT flags = DT_LEFT | DT_SINGLELINE | DT_VCENTER | DT_NOPREFIX) {
    HFONT old = static_cast<HFONT>(SelectObject(hdc, font));
    SetBkMode(hdc, TRANSPARENT);
    SetTextColor(hdc, color);
    int prev_extra = 0;
    if (char_extra != 0) {
        prev_extra = GetTextCharacterExtra(hdc);
        SetTextCharacterExtra(hdc, char_extra);
    }
    DrawTextW(hdc, text.c_str(), -1, &rc, flags);
    if (char_extra != 0) SetTextCharacterExtra(hdc, prev_extra);
    SelectObject(hdc, old);
}

} // namespace Theme
} // namespace DualTitle

#endif // _WIN32
