# DualTitle v5.1.0 "Aurora" (C++17 Anti-Cheat-Safe Universal Edition)

<div align="center">
  <img src="assets/logo.png" alt="DualTitle Logo" width="120" />
  <p><strong>Modern-Minimal Dual-Subtitle Overlay HUD • Game Library Picker • Save Restoration</strong></p>
  <p>
    <a href="https://github.com/ybreakless/dualtitle/releases/download/v5.1.0/DualTitle.exe">⬇️ Download DualTitle.exe</a> •
    <a href="https://github.com/ybreakless/dualtitle/releases/download/v5.1.0/RestoreSave.exe">💾 RestoreSave.exe</a> •
    <a href="https://ybreakless.github.io/dualtitle/">🌐 Website</a> •
    <a href="#-project-structure">📁 Project Layout</a>
  </p>
</div>

---

## 🧭 What is DualTitle?

**DualTitle** is a 100% **Anti-Cheat-Safe** C++17, Rust, and Win32 application suite that lets you watch **dual subtitles** (your language + a second language) over any game you own — with an interactive in-game dictionary for every word, and 1-click save backup & restoration.

> All of your games start **natively and cleanly**. DualTitle sits *outside* the game process — it never touches game memory, never injects DLLs, and never hooks graphics pipelines.

### 🆕 v5 "Aurora" — Modern Minimal Redesign

- 🎨 **New dark design system** (`src/DualTitleTheme.hpp`): charcoal cards, sky-blue + gold accents, rounded corners, GDI+ anti-aliasing.
- 🔍 **Per-Monitor V2 DPI awareness** — crisp on any scaled display (Segoe UI Variable with graceful fallback).
- 🖱️ **Region-drawn buttons with hover + pressed states** — no more clunky default controls.
- ⚡ **Non-blocking game library scan** — runs on a background thread; the UI never freezes.
- 📋 **Version metadata + embedded manifest** in the exe (proper details view everywhere).
- 🎯 Same 100% anti-cheat-safe architecture as before — zero injection, zero hooks.

### 🧱 Technology Stack

| Layer | Technology |
| :--- | :--- |
| Native GUI / Overlay | C++17 + Win32 (`src/DualTitle.cpp`, `src/DualTitleEngine.hpp`, `src/DualTitleOverlay.hpp`, `src/DualTitleTheme.hpp`) |
| Fallback / Tray tools | Rust (`src/main.rs`, built with `cargo`) |
| Subtitle engines | Python 3 (`universal_dualsub.py` + engine modules) |
| Build system | `build_cpp.bat` (MSVC auto-located via vswhere), `CMakeLists.txt`, `Cargo.toml` |

---

## 📥 Downloads (Windows 10 / 11, 64-Bit)

Grab any file below — every link goes to the official **[v5.1.0 Release](https://github.com/ybreakless/dualtitle/releases/tag/v5.1.0)**:

| File | What it is |
| :--- | :--- |
| **[DualTitle.exe](https://github.com/ybreakless/dualtitle/releases/download/v5.1.0/DualTitle.exe)** | Main launcher (PE32+ GUI, x86_64) — the Control Panel & Game Picker with the embedded DualTitle icon |
| **[RestoreSave.exe](https://github.com/ybreakless/dualtitle/releases/download/v5.1.0/RestoreSave.exe)** | Standalone 1-click save & profile recovery tool |
| **[DualTitle-Windows-x64.zip](https://github.com/ybreakless/dualtitle/releases/download/v5.1.0/DualTitle-Windows-x64.zip)** | Complete portable suite (launchers, sources, assets, offline lexicons) |

Prefer portable copies? All three files are also mirrored in [`docs/downloads/`](docs/downloads/).

---

## 🚀 Quick Start (3 Steps)

1. **Launch the Control Panel**
   Double-click `DualTitle.exe` (or `DualTitle.bat`). DualTitle scans every drive (`C:`–`Z:`) in the background and lists installed games automatically — no lag.
   💡 Run `install_dualtitle.bat` once to copy the suite to `%LocalAppData%\Programs\DualTitle` and register a Start-Menu + Desktop shortcut — then `DualTitle` is searchable from the Windows Start Menu.

2. **Pick a Game + Subtitle Style + Hotkeys**
   Choose your game from the dropdown, then pick your **Spoken Audio**, **Primary (top) subtitle**, **Secondary (bottom) subtitle**, and **subtitle speed**.
   Open **Hotkeys & Style** to:
   - Set the **Reveal Words** hold key (default `CAPSLOCK`, must be unmodified)
   - Remap any of the 10 actions (click a chip, press the new key + optional modifiers)
   - Choose a **Subtitle Style**: Aurora / Mimic Frostbite / Classic Console
   - Toggle which dictionary card fields show (Phonetics / POS / Synonyms / Translation / Definition)

3. **Launch & Enjoy**
   Click **Launch Game + Overlay HUD** — you get live dual subtitles, a clickable word dictionary, and save protection while you play.
   In game: **HOLD the Reveal key** and hover any subtitle word for its dictionary card.
   **⚠️ Requires the game to run in borderless/windowed mode** so the OS cursor reaches the overlay. Exclusive fullscreen keeps the cursor locked to the game — DualTitle cannot override that without hooks (which we refuse to use). Use the **Force Borderless** button (`ALT+F11` default) if needed.

> 💡 No install needed. Everything runs from the folder you downloaded.

---

## ✨ Key Features

### 🛡️ 100% Anti-Cheat Safe — Zero Injection Architecture

- ❌ **Never injects DLLs** into game processes.
- ❌ **Never hooks** DirectX/Vulkan graphics pipelines.
- ❌ **Never opens intrusive process handles** (`OpenProcess`).
- ✅ **Crafts clean game launches** — stale synthetic `.utoc` / `.ucas` / `.pak` or injected mod files are cleaned up automatically before launch, so games open natively without triggering anti-cheat or file-integrity checks.

### 🖥️ Modern Minimal "Aurora" Control Panel

- Dark charcoal design system with card-grouped sections: **Game Library → Languages & Playback → Actions**.
- Auto-detected games populate a dark-styled dropdown while the scan runs in the background.
- One prominent **Launch Game + Overlay HUD** action; Backup / Restore / Repair / Apply as quiet secondary buttons with live status feedback.

### 🎮 Choose Any Game You Own & Launch Directly

- Double-click `DualTitle.bat` (or `build_cpp.bat`) to open the **DualTitle Control Panel GUI**.
- Auto-scans all drives (`C:` through `Z:`) across Steam, EA App / Origin, Epic Games, Ubisoft Connect, GOG, and custom folders.
- Pick any game from the dropdown and click **Launch Game + Overlay HUD**.

### 💬 Interactive In-Game Dual-Subtitle Overlay HUD

Two tilted subtitle bars over the game:

- **Top line — Primary subtitle** in gold `#FFD700`
- **Bottom line — Secondary subtitle** in ice-white `#E2E8F0`

**Hold-to-Reveal Word Inspector (v5.1.0):**
- **HOLD the "Reveal Words" key** (default **CAPSLOCK**, fully remappable) while the HUD is visible.
- Word hitboxes become live; **dwell ~160 ms** on a word → an async dictionary popup card appears with meaning, phonetics, part-of-speech, gender, synonyms, translation, and definition.
- Release the key → card closes, overlay returns to click-through.
- **Zero hooks, zero injection** — cursor polling + `GetKeyState` only.
- **⚠️ Requires borderless/windowed mode** so the OS cursor reaches the overlay.

**Clickable Words (legacy, still works):** Click any word in either subtitle line to inspect it without holding a key.

In-game control buttons:

| Button | Action |
| :--- | :--- |
| `◀ Prev` / `Next ▶` | Step backward / forward through dialogue lines |
| `▶ Auto:ON/OFF` → **`▶ Pause Subs` / `▶ Resume Subs`** | Toggle automatic subtitle cadence |
| `- Spd` / `⚡ 1.00x` / `+ Spd` | Live speed control (`0.25x` – `2.00x`) |
| `⏸ Game (ESC)` → **`⏸ Pause Game`** | Sends your **mapped pause key** to the game (no process hooks) |
| `🔲 Borderless` | Convert the active game window to borderless fullscreen (`ALT+F11`) |
| `💾 Restore Save` | 1-click save & profile restoration right from the HUD |

### 🔥 Fully Remappable Hotkeys (10 Actions, v5.1.0)

| Action | Default | Description |
| :--- | :--- | :--- |
| **Pause Game** | `ESC` | Sends your mapped key to the game window (`SendInput`, no process handles) |
| **Pause Subtitles** | `ALT+F9` | Freezes/resumes subtitle auto-advance cadence (game untouched) |
| **Next Line** | `ALT+F10` | Advance to next subtitle line |
| **Previous Line** | `ALT+F7` | Go back one subtitle line |
| **Show/Hide HUD** | `ALT+F8` | Toggle overlay visibility |
| **Force Borderless** | `ALT+F11` | Convert exclusive fullscreen → borderless window |
| **Hold: Reveal Words** | `CAPSLOCK` | **Polled live** (must stay unmodified; modifiers reserved for other hotkeys) |
| **Speed Down** | `ALT+F5` | Decrease subtitle speed (0.25x steps) |
| **Speed Up** | `ALT+F6` | Increase subtitle speed (0.25x steps) |
| **Toggle Dict Card** | `ALT+D` | Manually open/close the dictionary popup |

All bindings persist to `data/config.json` (portable) or `%LOCALAPPDATA%\DualTitle\config.json` (fallback). Remap in the Control Panel → **Hotkeys & Style** card: click a chip, press the new key (+ optional Ctrl/Alt/Shift), ESC cancels, duplicates rejected.

### 🎨 Subtitle Style Presets (v5.1.0)

| Preset | Visual | Use Case |
| :--- | :--- | :--- |
| **Aurora** (default) | Charcoal rounded card, gold primary / ice-white secondary, subtle glow | DualTitle signature |
| **Mimic Frostbite** | Flat near-black band, sharp corners, white/gray game-like subs | Battlefield / Apex / Need for Speed vibe |
| **Classic Console** | Deep black phosphor slab, green primary / amber secondary, thin border | Retro terminal aesthetic |

Selected in the GUI **Hotkeys & Style** card or by editing `subtitle_style` in `config.json`.

### 📚 Dictionary Card Visibility Toggles (v5.1.0)

Per-field chips: **Phonetics / POS / Synonyms / Translation / Definition** — trim the popup to exactly what you need. State persists in config.

### 💾 Automatic Save Backup & 1-Click "Restore Save"

- Automatically backs up user save files before every operation — `Saved/SaveGames`, `Documents/<App>/settings/PROF_SAVE*`, `Saves`, `*.sav`, and profile `.ini`s — into `.dualtitle_save_backup/` and `backups/`.
- Restore saved progress any time from the **GUI**, the **in-game HUD**, the **system tray menu**, or via `RESTORE_SAVE.bat`.

---

## 🔍 Multi-Engine Support

The subtitle engine merges and restores subtitles across many game engines and formats:

| Engine / Format | Handles |
| :--- | :--- |
| **Unreal Engine 4 & 5** | `.locres` v1–v3 hash-preserving merges, `.pak` v11, IoStore `.utoc`/`.ucas` |
| **Frostbite** | `.sb` / `.toc` bundles (`Patches/Wars/`), `PROF_SAVE_profile`, `user.cfg` |
| **FORGE v27** | `DataPC*.forge` patch slot injection & save backup |
| **Generic text formats** | `.srt`, `.vtt`, `.ass`, `.ssa`, `.json`, `.csv` — timestamp-aligned merge & restore |

Plus an offline **Famous Dictionary Engine** (Oxford / Duden / Wiktionary) with stemming, German gender articles, and a built-in cache — see `dictionaries/`.

---

## 🧪 Pre-Flight Verification

Before every push (this is exactly how this repository was authored):

```bash
python universal_dualsub.py --self-test
```

This runs the full automated verification suite:

| # | Suite |
| :--- | :--- |
| 1 | FORGE v27, Config Patcher & SaveBackupManager ('Restore Save') |
| 2 | Frostbite `PROF_SAVE_profile`, `user.cfg` & `Loc/*.sb` bundle merge/restore |
| 3 | Unreal Engine 5 `.locres` v3 hash preservation (+ en-GB slots, Pak v11) |
| 4 | In-place SRT / ASS / JSON subtitle merger & restore |
| 5 | Famous Dictionary Engine (Oxford / Duden / Wiktionary) |
| 6 | 32-bit BGRA system tray `.ico` & StartupManager |

---

## 📁 Project Structure

```text
dualtitle/
├── DualTitle.exe               # Main launcher (Windows x64, v5.1.0 metadata)
├── RestoreSave.exe             # 1-click save & profile recovery
├── DualTitle.bat               # GUI launcher shortcut
├── RESTORE_SAVE.bat            # Standalone restore shortcut
├── EMERGENCY_REPAIR.bat        # Post-restore / integrity repair
├── build_cpp.bat               # Compile the native C++17 GUI (auto-locates MSVC)
├── install_dualtitle.bat       # Install to LocalAppData + Start-Menu shortcuts (searchable)
├── PUBLISH_TO_GITHUB.bat       # Repo bootstrap helper
├── RELEASE_NOTES_v4.1.0.md     # Historical release notes (v4.1.0)
├── RELEASE_NOTES_v5.1.0.md     # Release notes (v5.1.0)
│
├── docs/                       # GitHub Pages website (+ downloads mirror)
│   ├── index.html
│   └── downloads/
│       ├── DualTitle.exe
│       ├── RestoreSave.exe
│       └── DualTitle-Windows-x64.zip
│
├── assets/                     # Branding (logo.svg, logo.png, dualtitle.ico)
│
├── src/                        # C++17 & Rust source
│   ├── DualTitle.cpp           # Win32 "Aurora" GUI + game picker
│   ├── DualTitleEngine.hpp     # Engine internals
│   ├── DualTitleConfig.hpp     # Portable config + hotkey remap schema
│   ├── DualTitleDictService.hpp # Background async dictionary worker
│   ├── DualTitleTheme.hpp      # "Aurora" modern-minimal design system
│   ├── DualTitleOverlay.hpp    # Topmost overlay HUD (Win32)
│   ├── DualTitle.rc            # Icon + version + manifest resources
│   ├── app.manifest            # PerMonitorV2 DPI manifest
│   └── main.rs                 # Rust entry point
│
├── universal_dualsub.py        # Main engine + verification suite
├── subtitle_engine.py          # Subtitle format merge/restore core
├── config_patcher.py           # INI / config patching
├── dictionary_engine.py        # Offline dictionary lookups
├── startup_manager.py          # No-background startup manager
├── dualsub_installer.py        # Install / integration helper
├── tray_controller.py          # System tray controller
├── DualSub.lua                 # Lua runtime shim
├── CMakeLists.txt              # CMake build definition
├── Cargo.toml                  # Rust build definition
│
├── data/                       # Language data (de_en.json, en_de.json) + config.json (runtime)
└── dictionaries/               # Offline Oxford / Duden / Wiktionary caches
```

---

## 🛠️ Build From Source

The pre-built launchers (`DualTitle.exe`, `RestoreSave.exe`) are included, but you can rebuild everything yourself:

| Target | How |
| :--- | :--- |
| Native C++17 GUI + overlay | Double-click `build_cpp.bat` — auto-locates VS 2022 via `vswhere`, compiles `DualTitle.exe` and runs the self-test suite |
| Manual MSVC | `rc /nologo /fo src\DualTitle.res src\DualTitle.rc` then `cl /std:c++17 /O2 /EHsc /utf-8 /Fe:DualTitle.exe src\DualTitle.cpp src\DualTitle.res user32.lib gdi32.lib shell32.lib comdlg32.lib gdiplus.lib uxtheme.lib winmm.lib` |
| CMake | `cmake -S . -B build && cmake --build build --config Release` |
| Rust entry point | `cargo build --release` |
| Run verification suite | `python universal_dualsub.py --self-test` |
| Install & make searchable | Run `install_dualtitle.bat` (Start-Menu + Desktop shortcut, typeable in Windows search) |

---

## 🌐 Links

- **Website (GitHub Pages):** <https://ybreakless.github.io/dualtitle/>
- **Releases / Downloads:** <https://github.com/ybreakless/dualtitle/releases>
- **Issues:** open an issue on this repository

---

<div align="center">
  <sub><strong>DualTitle v5.1.0 "Aurora"</strong> — Universal Anti-Cheat-Safe Edition (Windows x64)</sub>
</div>
