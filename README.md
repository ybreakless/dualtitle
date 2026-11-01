# DualTitle (C++17 & Rust Anti-Cheat-Safe Universal Edition v4.1)

<div align="center">
  <img src="assets/logo.png" alt="DualTitle Logo" width="120" />
  <p><strong>Dual-Subtitle Overlay HUD • Game Library Picker • Save Restoration</strong></p>
  <p>
    <a href="https://github.com/ybreakless/dualtitle/releases/download/v4.1.0/DualTitle.exe">⬇️ Download DualTitle.exe</a> •
    <a href="https://github.com/ybreakless/dualtitle/releases/download/v4.1.0/RestoreSave.exe">💾 RestoreSave.exe</a> •
    <a href="https://ybreakless.github.io/dualtitle/">🌐 Website</a> •
    <a href="#-project-structure">📁 Project Layout</a>
  </p>
</div>

---

## 🧭 What is DualTitle?

**DualTitle** is a 100% **Anti-Cheat-Safe** C++17, Rust, and Win32 application suite that lets you watch **dual subtitles** (your language + a second language) over any game you own — with an interactive in-game dictionary for every word, and 1-click save backup & restoration.

> All of your games start **natively and cleanly**. DualTitle sits *outside* the game process — it never touches game memory, never injects DLLs, and never hooks graphics pipelines.

### 🧱 Technology Stack

| Layer | Technology |
| :--- | :--- |
| Native GUI / Overlay | C++17 + Win32 (`src/DualTitle.cpp`, `src/DualTitleEngine.hpp`, `src/DualTitleOverlay.hpp`) |
| Fallback / Tray tools | Rust (`src/main.rs`, built with `cargo`) |
| Subtitle engines | Python 3 (`universal_dualsub.py` + engine modules) |
| Build system | `build_cpp.bat` (MSVC), `CMakeLists.txt`, `Cargo.toml` |

---

## 📥 Downloads (Windows 10 / 11, 64-Bit)

Grab any file below — every link goes to the official **[v4.1.0 Release](https://github.com/ybreakless/dualtitle/releases/tag/v4.1.0)**:

| File | What it is |
| :--- | :--- |
| **[DualTitle.exe](https://github.com/ybreakless/dualtitle/releases/download/v4.1.0/DualTitle.exe)** | Main launcher (PE32+ GUI, x86_64) — the Control Panel & Game Picker with the embedded DualTitle icon |
| **[RestoreSave.exe](https://github.com/ybreakless/dualtitle/releases/download/v4.1.0/RestoreSave.exe)** | Standalone 1-click save & profile recovery tool |
| **[DualTitle-Windows-x64.zip](https://github.com/ybreakless/dualtitle/releases/download/v4.1.0/DualTitle-Windows-x64.zip)** | Complete portable suite (launchers, sources, assets, offline lexicons) |

Prefer portable copies? All three files are also mirrored in [`docs/downloads/`](docs/downloads/).

---

## 🚀 Quick Start (3 Steps)

1. **Launch the Control Panel**
   Double-click `DualTitle.exe` (or `DualTitle.bat`). DualTitle scans every drive (`C:`–`Z:`) and lists installed games automatically.

2. **Pick a Game + Subtitle Style**
   Choose your game from the dropdown, then pick your **Spoken Audio**, **Primary (top) subtitle**, **Secondary (bottom) subtitle**, and **subtitle speed**.

3. **Launch & Enjoy**
   Click **🚀 Launch Selected Game + In-Game Overlay HUD** — you get live dual subtitles, a clickable word dictionary, and save protection while you play.

> 💡 No install needed. Everything runs from the folder you downloaded.

---

## ✨ Key Features

### 🛡️ 100% Anti-Cheat Safe — Zero Injection Architecture

- ❌ **Never injects DLLs** into game processes.
- ❌ **Never hooks** DirectX/Vulkan graphics pipelines.
- ❌ **Never opens intrusive process handles** (`OpenProcess`).
- ✅ **Crafts clean game launches** — stale synthetic `.utoc` / `.ucas` / `.pak` or injected mod files are cleaned up automatically before launch, so games open natively without triggering anti-cheat or file-integrity checks.

### 🎮 Choose Any Game You Own & Launch Directly

- Double-click `DualTitle.bat` (or `build_cpp.bat`) to open the **DualTitle Control Panel GUI**.
- Auto-scans all drives (`C:` through `Z:`) across Steam, EA App / Origin, Epic Games, Ubisoft Connect, GOG, and custom folders.
- Pick any game from the dropdown and click **🚀 Launch Selected Game + In-Game Overlay HUD**.

### 💬 Interactive In-Game Dual-Subtitle Overlay HUD

Two tilted subtitle bars over the game:

- **Top line — Primary subtitle** in gold `#FFD700`
- **Bottom line — Secondary subtitle** in ice-white `#E2E8F0`

**Both lines are clickable** — click any word to instantly see its translation, phonetic pronunciation, part of speech, gender article, and definition right on the HUD.

In-game control buttons:

| Button | Action |
| :--- | :--- |
| `◀ Prev` / `Next ▶` | Step backward / forward through dialogue lines |
| `▶ Auto:ON/OFF` | Toggle automatic subtitle cadence |
| `- Spd` / `⚡ 1.00x` / `+ Spd` | Live speed control (`0.25x` – `2.00x`) |
| `⏸ Game (ESC)` | Safe standard keyboard pause (`ALT+F9`, no process hooks) |
| `🔲 Borderless` | Convert the active game window to borderless fullscreen (`ALT+F11`) |
| `💾 Restore Save` | 1-click save & profile restoration right from the HUD |

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
├── DualTitle.exe               # Main launcher (Windows x64)
├── RestoreSave.exe             # 1-click save & profile recovery
├── DualTitle.bat               # GUI launcher shortcut
├── RESTORE_SAVE.bat            # Standalone restore shortcut
├── EMERGENCY_REPAIR.bat        # Post-restore / integrity repair
├── build_cpp.bat               # Compile the native C++17 GUI with MSVC
├── PUBLISH_TO_GITHUB.bat       # Repo bootstrap helper
├── RELEASE_NOTES_v4.1.0.md     # Official release notes
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
│   ├── DualTitle.cpp           # Win32 GUI + game picker
│   ├── DualTitleEngine.hpp     # Engine internals
│   ├── DualTitleOverlay.hpp    # Topmost overlay HUD (Win32)
│   ├── DualTitle.rc            # Icon + version resources
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
├── data/                       # Language data (de_en.json, en_de.json)
└── dictionaries/               # Offline Oxford / Duden / Wiktionary caches
```

---

## 🛠️ Build From Source

The pre-built launchers (`DualTitle.exe`, `RestoreSave.exe`) are included, but you can rebuild everything yourself:

| Target | How |
| :--- | :--- |
| Native C++17 GUI + overlay | Double-click `build_cpp.bat` (uses MSVC), or `cmake -S . -B build && cmake --build build` |
| Rust entry point | `cargo build --release` |
| Run verification suite | `python universal_dualsub.py --self-test` |

---

## 🌐 Links

- **Website (GitHub Pages):** <https://ybreakless.github.io/dualtitle/>
- **Releases / Downloads:** <https://github.com/ybreakless/dualtitle/releases>
- **v4.1.0 Release:** <https://github.com/ybreakless/dualtitle/releases/tag/v4.1.0>
- **Issues:** open an issue on this repository

---

<div align="center">
  <sub><strong>DualTitle v4.1.0</strong> — Universal Anti-Cheat-Safe Edition (Windows x64)</sub>
</div>
