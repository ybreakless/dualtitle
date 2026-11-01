# DualTitle v4.1.0 — Official Windows x64 Release

**DualTitle** is a 100% Anti-Cheat-Safe C++17, Rust, and Win32 application suite featuring the custom **DualTitle Gamepad + Tilted Dual-Subtitle Bars** emblem (`assets/logo.svg`, `assets/logo.png`, `assets/dualtitle.ico`).

---

## 📥 Direct Downloads (Windows 10 / 11 64-Bit)

| File | Type | Description |
| :--- | :--- | :--- |
| **`DualTitle.exe`** | `PE32+ GUI (x86_64)` | Main Windows Desktop Launcher with embedded DualTitle icon (`Subsystem: WINDOWS_GUI`). Double-click to open the Control Panel & Game Picker. |
| **`RestoreSave.exe`** | `PE32+ GUI (x86_64)` | Standalone 1-Click Save & Profile Recovery executable. Restores backed-up save files (`.dualtitle_save_backup/` & `backups/`) immediately. |
| **`DualTitle_Native.exe`** | `PE32+ GUI (x86_64)` | Native compiled C++17 Win32 GUI & Topmost Overlay executable (built automatically via MSVC in GitHub Actions or `build_cpp.bat`). |
| **`DualTitle-Windows-x64.zip`** | `Complete Portable Suite` | Full portable package containing `DualTitle.exe`, `RestoreSave.exe`, all C++17 & Rust source files, `assets/`, offline Oxford/Duden/Wiktionary lexicons, and Win32 runtime. |

---

## ✨ Key Features in v4.1.0

1. **100% Anti-Cheat-Safe Out-of-Process Architecture**:
   - Zero DLL injection (`no dxgi.dll` / `dwmapi.dll` hooks) and zero foreign process memory handles (`no OpenProcess` attach during gameplay).
   - Automatically cleans any stale synthetic `.utoc`/`.ucas`/`.pak` or injected mod files before launch so every game starts natively without triggering anti-cheat or file-integrity checks.
2. **Auto-Scanned Game Library Picker (`C:` through `Z:`)**:
   - Automatically detects installed games across Steam, EA App / Origin, Epic Games, Ubisoft Connect, GOG Galaxy, and custom directories.
   - Choose any game you own from the dropdown, pick your **Spoken Audio**, **Primary (Top) Subtitle**, **Secondary (Bottom) Subtitle**, and **Subtitle Speed**, and click **🚀 Launch Selected Game + In-Game Overlay HUD**.
3. **Interactive In-Game Dual-Subtitle Overlay HUD**:
   - **Clickable Words on Both Lines**: Click any word in the Primary (Gold `#FFD700`) or Secondary (Ice-White `#E2E8F0`) subtitle bar to view its translation, phonetic pronunciation, part of speech, gender article, and definition.
   - **Live Speed Controller (`- Spd` / `⚡ 1.00x` / `+ Spd` & `▶ Auto:ON/OFF`)**: Adjust subtitle playback and reading speed live from `0.25x` to `2.00x`.
   - **In-Game Extra Control Buttons**: `◀ Prev` / `Next ▶` line navigation, `⏸ Game (ESC)` safe pause (`ALT+F9`), `🔲 Borderless` fullscreen window converter (`ALT+F11`), and `💾 Restore Save`.
4. **Automatic Save Protection & 1-Click `💾 Restore Save`**:
   - Automatically backs up user save files (`Saved/SaveGames`, `Documents/<App>/settings/PROF_SAVE*`, `Saves`, `*.sav`, profile `.ini`s) before every launch and restores them anytime with 1 click.
5. **Universal Multi-Engine Support**:
   - Supports Frostbite (`.sb`/`.toc` & `PROF_SAVE_profile`), Unreal Engine 4 & 5 (`.locres` v1–v3, `.pak` v11, 64-bit Oodle & IoStore `.utoc`/`.ucas`), FORGE v27/v50 (`DataPC*.forge`), and generic `.srt`/`.vtt`/`.ass`/`.ssa`/`.json`/`.csv` formats.
