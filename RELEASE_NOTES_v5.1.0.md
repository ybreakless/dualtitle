# DualTitle v5.1.0 — In-Game Word Inspector Edition

**DualTitle** is a 100% Anti-Cheat-Safe C++17 application featuring the custom **DualTitle Gamepad + Tilted Dual-Subtitle Bars** emblem (`assets/logo.svg`, `assets/logo.png`, `assets/dualtitle.ico`).

---

## 📥 Direct Downloads (Windows 10 / 11 64-Bit)

| File | Type | Description |
| :--- | :--- | :--- |
| **`DualTitle.exe`** | `PE32+ GUI (x86_64)` | Main Windows Desktop Launcher with embedded DualTitle icon (`Subsystem: WINDOWS_GUI`). Double-click to open the Control Panel & Game Picker. |
| **`RestoreSave.exe`** | `PE32+ GUI (x86_64)` | Standalone 1-Click Save & Profile Recovery executable. Restores backed-up save files (`.dualtitle_save_backup/` & `backups/`) immediately. |
| **`DualTitle_Native.exe`** | `PE32+ GUI (x86_64)` | Native compiled C++17 Win32 GUI & Topmost Overlay executable (built automatically via MSVC in GitHub Actions or `build_cpp.bat`). |
| **`DualTitle-Windows-x64.zip`** | `Complete Portable Suite` | Full portable package containing `DualTitle.exe`, `RestoreSave.exe`, all C++17 & Rust source files, `assets/`, offline Oxford/Duden/Wiktionary lexicons, and Win32 runtime. |

---

## ✨ Key Features in v5.1.0 (Builds on v4.1.0)

### 1. **Hold-to-Reveal Word Inspector (In-Game, Zero Hooks)**
- **HOLD the "Reveal Words" key** (default: **CAPSLOCK**, fully remappable) while the subtitle HUD is visible.
- The overlay toggles `WS_EX_TRANSPARENT` OFF only while the key is held — word hitboxes become live, the OS cursor can hover them.
- **Dwell (160 ms default)** on a word → an async dictionary popup card appears with:
  - Meaning, phonetics, part-of-speech ("job of the word"), gender article
  - **Synonyms** (from the shipped JSON lexicons or the builtin fallback table)
  - Translation and definition (English + German)
- Release the key → card closes, overlay returns to click-through. **No mouse/keyboard hooks, no injection, no DLLs** — cursor polling + `GetKeyState` only.
- **Honest limitation:** requires the game to run in **borderless/windowed** mode so the OS cursor reaches the overlay. Exclusive fullscreen keeps the cursor locked to the game; DualTitle cannot override that without hooks (which we refuse to use).

### 2. **Background Dictionary Service (Async, No UI Block)**
- Dedicated worker thread (`DictSvc`) services lookups so the overlay thread never blocks.
- Request IDs + dedup by word → stale results dropped automatically.
- **Honest "not found" state** when the word isn't in any loaded dictionary (no hallucinated definitions).
- Shipped `dictionaries/*.json` already carry synonyms in `notes` ("Synonyms: a, b, c"); the loader parses structured `synonyms` arrays OR extracts from that sentence.

### 3. **Fully Remappable Hotkeys (10 Actions, Modifiers Supported)**
| Action | Default | Description |
| :--- | :--- | :--- |
| **Pause Game** | `ESC` | Sends your mapped key to the game window (SendInput, no process handles) |
| **Pause Subtitles** | `ALT+F9` | Freezes/resumes subtitle auto-advance cadence (game untouched) |
| **Next Line** | `ALT+F10` | Advance to next subtitle line |
| **Previous Line** | `ALT+F7` | Go back one subtitle line |
| **Show/Hide HUD** | `ALT+F8` | Toggle overlay visibility |
| **Force Borderless** | `ALT+F11` | Convert exclusive fullscreen → borderless window |
| **Hold: Reveal Words** | `CAPSLOCK` | **Polled live** (must stay unmodified; modifiers reserved for other hotkeys) |
| **Speed Down** | `ALT+F5` | Decrease subtitle speed (0.25x steps) |
| **Speed Up** | `ALT+F6` | Increase subtitle speed (0.25x steps) |
| **Toggle Dict Card** | `ALT+D` | Manually open/close the dictionary popup |

All bindings persist to `data/config.json` (portable) or `%LOCALAPPDATA%\DualTitle\config.json` (fallback). The Control Panel **Hotkeys & Style** card has click-a-chip capture: click a chip, press the new key (+ optional Ctrl/Alt/Shift), ESC cancels, duplicates rejected.

### 4. **Two Distinct Pause Buttons**
- **[Pause Game]** → sends your mapped pause key to the game window.
- **[Pause Subs]** / **[Resume Subs]** → freezes or resumes the subtitle auto-advance timer only. The game keeps running.

### 5. **Subtitle Style Presets (3 Looks)**
| Preset | Visual | Use Case |
| :--- | :--- | :--- |
| **Aurora** (default) | Charcoal rounded card, gold primary / ice-white secondary, subtle glow | DualTitle signature |
| **Mimic Frostbite** | Flat near-black band, sharp corners, white/gray game-like subs | Battlefield / Apex / Need for Speed vibe |
| **Classic Console** | Deep black phosphor slab, green primary / amber secondary, thin border | Retro terminal aesthetic |

Selected in the GUI **Hotkeys & Style** card or by editing `subtitle_style` in `config.json`.

### 6. **Dictionary Card Visibility Toggles**
Per-field chips (Phonetics / POS / Synonyms / Translation / Definition) let you trim the popup to exactly what you need. State persists in config.

### 7. **Game Profile Pipeline Fixed End-to-End**
- Launch All / Overlay Only now match the selected game's **declarative GameProfile** and pass it through:
  - `ConfigPatcher::ApplyGameConfig` gets the profile → Frostbite `user.cfg` whitelist + Documents `PROF_SAVE_profile` path honored.
  - `RunOverlayLoop` forwards the profile to `SubtitleMerger::IndexGameSubtitlesReadOnly` → Frostbite `.sb`/`.toc` extraction + profile-declared subtitle globs run on the **primary launch path** too.
- Frostbite config patching verified: forces subtitle keys ON (`UI.DrawEnable 1` in `user.cfg` + `GstAudio.Subtitles 1` in `PROF_SAVE_profile`).

---

## 📦 Install & Run

1. Extract `DualTitle-Windows-x64.zip` anywhere (portable, no admin).
2. Run `install_dualtitle.bat` (optional) to create a Start Menu shortcut + file association for `.dualtitle` profiles.
3. Launch `DualTitle.exe` → pick a game → pick languages → **Launch Game + Overlay HUD**.
4. In game: **HOLD CAPSLOCK** (or your remapped key) and hover any subtitle word for its dictionary card.
5. **Remap anything** in the Control Panel → **Hotkeys & Style** tab.

---

## 🔧 Build from Source (MSVC 2022, C++17)

```cmd
rc /nologo /fo src\DualTitle.res src\DualTitle.rc
cl /std:c++17 /O2 /EHsc /utf-8 /Fe:DualTitle.exe src\DualTitle.cpp src\DualTitle.res ^
   user32.lib gdi32.lib shell32.lib comdlg32.lib gdiplus.lib uxtheme.lib winmm.lib
.\DualTitle.exe --self-test   # runs 7/7 core verification suites
```

---

## 🛡 Anti-Cheat Safety Guarantee

- **Zero injection, zero hooks, zero foreign process handles** during gameplay.
- `SendSafeGamePause` uses `SendInput` only; `PollRevealAndCard` polls `GetKeyState` + `GetCursorPos` (no `SetWindowsHookEx`, no `WH_MOUSE`, no `WH_KEYBOARD`).
- All file writes happen **before** the game process starts (saves backed up, `user.cfg` / `PROF_SAVE_profile` patched). The overlay is a separate topmost window that never touches the game process.

---

## ⚠ Known Limitations

- **Hover requires the OS cursor on the overlay.** Games in exclusive fullscreen capture the cursor; use the game's borderless/windowed setting or DualTitle's **Force Borderless** button (`ALT+F11` default).
- Offline lexicon is limited (~200 builtin + shipped JSONs). Unknown words show an honest "not found" card — no LLM, no network, no telemetry.
- Hotkey capture requires the Control Panel window to have focus (standard Win32 `WM_KEYDOWN`).

---

## 🙏 Credits

- Oxford / Duden / Wiktionary lexicon snippets (public domain / CC-BY-SA subsets).
- Minimal JSON parser (single-header, C++17).
- GDI+ for alpha-blended rounded cards.
- **This release is fully open source (MIT).** No telemetry, no accounts, no DRM.

---

**SHA256 (DualTitle.exe):** *(filled by CI on tag push)*  
**SHA256 (RestoreSave.exe):** *(filled by CI on tag push)*  
**SHA256 (DualTitle_Native.exe):** *(filled by CI on tag push)*