#pragma once
/**
 * DualTitleConfig.hpp -- User configuration + hotkey remapping for DualTitle.
 *
 * Persists every user-tunable option as JSON:
 *   data/config.json   (portable, next to the application)
 *   %LOCALAPPDATA%\DualTitle\config.json  (fallback for installed copy)
 *
 * Hotkeys are fully remappable: each action stores a key name string plus
 * Ctrl/Alt/Shift modifiers. The Win32 layer (Overlay) translates these into
 * RegisterHotKey / GetKeyState calls at startup so nothing is hardcoded.
 *
 * Designed for busy players: while a subtitle is on screen, holding the
 * "reveal_words" key lets the user hover individual words to inspect them,
 * without stealing focus from the game (no hooks, no injection).
 *
 * This header is platform-independent (pure C++17) so tests can run headless.
 */

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#include "DualTitleEngine.hpp"  // MiniJson (parse-only), common std includes

namespace fs = std::filesystem;

namespace DualTitle {
namespace DualTitleConfig {

// ---------------------------------------------------------------------------
// Hotkey bindings
// ---------------------------------------------------------------------------

struct HotkeyBinding {
    std::string action;   // stable id, see kKnownActions
    std::string key;      // display/VK name, e.g. "F9", "ESC", "SPACE", "N" ...
    bool ctrl = false;
    bool alt = false;
    bool shift = false;
    HotkeyBinding() {}
    HotkeyBinding(std::string a, std::string k, bool c = false, bool al = false, bool sh = false)
        : action(std::move(a)), key(std::move(k)), ctrl(c), alt(al), shift(sh) {}
};

// Every supported hotkey action (also used by the remap UI, in display order).
inline const char* kKnownActions[] = {
    "pause_game",     // send the user's mapped game pause key
    "pause_subs",     // freeze/unfreeze subtitle auto-advance
    "next_line",
    "prev_line",
    "toggle_hud",
    "borderless",
    "reveal_words",   // HOLD: enable word hover for the current subtitle
    "speed_down",
    "speed_up",
    "toggle_dict",
};

// Friendly label for the remap panel / README table.
inline std::string ActionLabel(const std::string& action) {
    if (action == "pause_game") return "Pause Game";
    if (action == "pause_subs") return "Pause Subtitles";
    if (action == "next_line") return "Next Line";
    if (action == "prev_line") return "Previous Line";
    if (action == "toggle_hud") return "Show/Hide HUD";
    if (action == "borderless") return "Force Borderless";
    if (action == "reveal_words") return "Hold: Reveal Words";
    if (action == "speed_down") return "Speed Down";
    if (action == "speed_up") return "Speed Up";
    if (action == "toggle_dict") return "Toggle Dict Card";
    return action;
}

// Normalizes accepted key spellings so user files stay tolerant.
inline std::string NormalizeKey(std::string k) {
    for (auto& c : k) c = static_cast<char>(::toupper(static_cast<unsigned char>(c)));
    if (k == "ESCAPE") k = "ESC";
    if (k == "PAGEUP") k = "PGUP";
    if (k == "PAGEDOWN") k = "PGDN";
    return k;
}

// A key name is "known" iff it maps to a virtual key in the Win32 layer.
// This list is kept in sync with DualTitleOverlay.hpp's KeyNameToVk().
inline bool IsKnownKeyName(const std::string& k) {
    if (k.size() == 1 && k[0] >= 'A' && k[0] <= 'Z') return true;
    const char* list[] = {
        "ESC","F1","F2","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12",
        "SPACE","ENTER","TAB","CAPSLOCK","LEFT","RIGHT","UP","DOWN",
        "PGUP","PGDN","HOME","END","INSERT","DELETE","BACKSPACE",
        "PRINTSCREEN","SCROLLLOCK"
    };
    for (const char* n : list) if (k == n) return true;
    return false;
}

// ---------------------------------------------------------------------------
// Application configuration
// ---------------------------------------------------------------------------

struct AppConfig {
    std::vector<HotkeyBinding> hotkeys;

    // Subtitle presentation (mimic the game's own subtitle look or DualTitle's).
    std::string subtitle_style = "aurora";  // aurora | mimic_frostbite | classic_console
    bool hide_game_log_hint = false;        // suppress "exclusive fullscreen!" pill

    // Dictionary card contents ("the job of the word" = part of speech).
    bool show_card_phonetics = true;
    bool show_card_pos = true;
    bool show_card_synonyms = true;
    bool show_card_translation = true;
    bool show_card_definition = true;
    int  hover_dwell_ms = 160;              // dwell time before the card pops

    // Playback defaults.
    bool  auto_play = false;
    double playback_speed = 1.0;
};

// The single source of truth for defaults -- also written out as a template
// on first save so users can hand-edit the JSON.
inline AppConfig DefaultConfig() {
    AppConfig c;
    c.hotkeys = {
        {"pause_game",    "ESC",    false, false, false},
        {"pause_subs",    "F9",     false, true,  false},
        {"next_line",     "F10",    false, true,  false},
        {"prev_line",     "F7",     false, true,  false},
        {"toggle_hud",    "F8",     false, true,  false},
        {"borderless",    "F11",    false, true,  false},
        {"reveal_words",  "CAPSLOCK", false, false, false},
        {"speed_down",    "F5",     false, true,  false},
        {"speed_up",      "F6",     false, true,  false},
        {"toggle_dict",   "D",      false, true,  false},
    };
    return c;
}

inline bool IsKnownAction(const std::string& a) {
    for (const char* x : kKnownActions) if (a == x) return true;
    return false;
}

inline const HotkeyBinding* FindBinding(const AppConfig& c, const std::string& action) {
    for (const auto& h : c.hotkeys) if (h.action == action) return &h;
    return nullptr;
}

// Overwrites (or adds) a binding, keeping vector order stable.
inline void SetBinding(AppConfig& c, const HotkeyBinding& hb) {
    for (auto& h : c.hotkeys) {
        if (h.action == hb.action) { h = hb; return; }
    }
    c.hotkeys.push_back(hb);
}

// ---------------------------------------------------------------------------
// JSON serialization (writer is intentionally tiny; parser is MiniJson)
// ---------------------------------------------------------------------------

inline std::string JsonEscape(const std::string& s) {
    std::string out;
    out.reserve(s.size() + 8);
    for (unsigned char ch : s) {
        switch (ch) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (ch < 0x20) {  // other control chars -> \u00XX (ASCII only, safe for MSVC)
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", ch);
                    out += buf;
                } else {
                    out += static_cast<char>(ch);
                }
        }
    }
    return out;
}

inline std::string Serialize(const AppConfig& c) {
    std::ostringstream o;
    o << "{\n  \"subtitle_style\": \"" << JsonEscape(c.subtitle_style) << "\"";
    o << ",\n  \"hide_game_log_hint\": " << (c.hide_game_log_hint ? "true" : "false");
    o << ",\n  \"card\": {"
      << " \"phonetics\": "  << (c.show_card_phonetics  ? "true" : "false")
      << ", \"pos\": "       << (c.show_card_pos        ? "true" : "false")
      << ", \"synonyms\": "  << (c.show_card_synonyms   ? "true" : "false")
      << ", \"translation\": " << (c.show_card_translation ? "true" : "false")
      << ", \"definition\": " << (c.show_card_definition ? "true" : "false")
      << ", \"hover_dwell_ms\": " << c.hover_dwell_ms
      << " }";
    o << ",\n  \"playback\": { \"auto\": " << (c.auto_play ? "true" : "false")
      << ", \"speed\": " << c.playback_speed << " }";
    o << ",\n  \"hotkeys\": [";
    for (size_t i = 0; i < c.hotkeys.size(); ++i) {
        const auto& h = c.hotkeys[i];
        o << (i ? "," : "") << "\n    { \"action\": \"" << JsonEscape(h.action)
          << "\", \"key\": \"" << JsonEscape(h.key)
          << "\", \"ctrl\": " << (h.ctrl ? "true" : "false")
          << ", \"alt\": "    << (h.alt  ? "true" : "false")
          << ", \"shift\": "  << (h.shift ? "true" : "false") << " }";
    }
    o << "\n  ]\n}\n";
    return o.str();
}

inline bool Parse(const std::string& text, AppConfig& out, std::string* err = nullptr) {
    out = DefaultConfig();  // sensible defaults for anything missing
    std::string parse_err;
    MiniJson j = MiniJson::Parse(text, &parse_err);
    if (!parse_err.empty()) { if (err) *err = parse_err; return false; }
    if (j.type != MiniJson::Obj) { if (err) *err = "root must be an object"; return false; }

    out.subtitle_style = j.get_str("subtitle_style", out.subtitle_style);
    out.hide_game_log_hint = j.get_bool("hide_game_log_hint", out.hide_game_log_hint);

    if (auto* card = j.find("card"); card && card->type == MiniJson::Obj) {
        out.show_card_phonetics  = card->get_bool("phonetics",  out.show_card_phonetics);
        out.show_card_pos        = card->get_bool("pos",        out.show_card_pos);
        out.show_card_synonyms   = card->get_bool("synonyms",   out.show_card_synonyms);
        out.show_card_translation = card->get_bool("translation", out.show_card_translation);
        out.show_card_definition = card->get_bool("definition",  out.show_card_definition);
        if (auto* d = card->find("hover_dwell_ms"); d && d->type == MiniJson::Num)
            out.hover_dwell_ms = static_cast<int>(d->num);
    }
    if (auto* pb = j.find("playback"); pb && pb->type == MiniJson::Obj) {
        out.auto_play = pb->get_bool("auto", out.auto_play);
        if (auto* s = pb->find("speed"); s && s->type == MiniJson::Num)
            out.playback_speed = s->num;
    }
    if (auto* hk = j.find("hotkeys"); hk && hk->type == MiniJson::Arr) {
        for (const auto& item : hk->arr) {
            if (item.type != MiniJson::Obj) continue;
            std::string action = item.get_str("action");
            if (!IsKnownAction(action)) continue;               // unknown: keep default
            std::string key = NormalizeKey(item.get_str("key"));
            if (!IsKnownKeyName(key)) continue;                 // unknown key: keep default
            SetBinding(out, HotkeyBinding{action, key,
                item.get_bool("ctrl", false), item.get_bool("alt", false),
                item.get_bool("shift", false)});
        }
    }
    return true;
}

// ---------------------------------------------------------------------------
// File resolution: portable next to exe/data, %LOCALAPPDATA% fallback
// ---------------------------------------------------------------------------

inline bool WriteTextFileUtf8(const fs::path& path, const std::string& text, std::string* err = nullptr) {
    std::error_code ec;
    auto parent = path.parent_path();
    if (!parent.empty()) fs::create_directories(parent, ec);
    std::ofstream f(path, std::ios::binary | std::ios::trunc);
    if (!f.good()) { if (err) *err = "cannot open " + path.string(); return false; }
    f << text;
    f.close();
    if (!f.good()) { if (err) *err = "write failed on " + path.string(); return false; }
    return true;
}

inline bool ReadTextFileUtf8(const fs::path& path, std::string& text, std::string* err = nullptr) {
    std::ifstream f(path, std::ios::binary);
    if (!f.good()) { if (err) *err = "cannot open " + path.string(); return false; }
    std::ostringstream ss;
    ss << f.rdbuf();
    text = ss.str();
    return true;
}

// data/config.json next to the exe (or CWD) when a data dir exists there;
// otherwise %LOCALAPPDATA%\DualTitle\config.json.
inline fs::path ResolveConfigPath() {
    fs::path base = fs::current_path();
    if (fs::is_directory(base / "data")) return base / "data" / "config.json";
#ifdef _WIN32
    {
        const char* lappd = std::getenv("LOCALAPPDATA");
        if (lappd && *lappd) return fs::path(lappd) / "DualTitle" / "config.json";
    }
#endif
    return base / "data" / "config.json";
}

inline bool Save(const fs::path& path, const AppConfig& c, std::string* err = nullptr) {
    return WriteTextFileUtf8(path, Serialize(c), err);
}

inline bool Load(const fs::path& path, AppConfig& out, std::string* err = nullptr) {
    if (!fs::exists(path)) {
        out = DefaultConfig();
        if (err) *err = "not found (defaults in use)";
        return false;
    }
    std::string text;
    if (!ReadTextFileUtf8(path, text, err)) { out = DefaultConfig(); return false; }
    return Parse(text, out, err);
}

// Load with automatic fallback + default bootstrap: never fails for the caller.
inline AppConfig LoadOrCreate(fs::path* resolved = nullptr) {
    AppConfig c;
    fs::path p = ResolveConfigPath();
    if (resolved) *resolved = p;
    std::string err;
    if (!Load(p, c, &err)) {
        c = DefaultConfig();
        Save(p, c, nullptr);  // best effort bootstrap; ignore failure (test sandboxes)
    }
    return c;
}

}  // namespace DualTitleConfig
}  // namespace DualTitle
