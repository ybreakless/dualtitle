# MASTER ENGINEERING SPECIFICATION: DualTitle Universal Anti-Cheat-Safe Suite (v4.1)

## 1. Core Architectural Mandate

DualTitle is a unified C++17 (`src/DualTitle.cpp`, `src/DualTitleEngine.hpp`, `src/DualTitleOverlay.hpp`), Rust (`Cargo.toml`, `src/main.rs`), and Python/Win32 (`universal_dualsub.py`, `subtitle_engine.py`, `config_patcher.py`, `tray_controller.py`, `dictionary_engine.py`) application suite featuring the custom **DualTitle Gamepad + Tilted Dual-Subtitle Bars Logo** (`assets/dualtitle.ico`, `assets/logo.png`, `assets/logo.svg`).

### Supported Engines & Applications
1. **Frostbite Engine**:
   - `Documents/<App>/settings/PROF_SAVE_profile` (`GstAudio.Subtitles 1`, `GstAudio.AudioLanguage`, `GstRender.FullscreenEnabled 0`, `GstRender.FullscreenMode 1`), `<AppDir>/user.cfg`, and `Data/Win32/Loc/<lang>.sb` & `<lang>.toc` localization bundles.
2. **Unreal Engine 4 & 5**:
   - Binary `.locres` v1, v2, and v3 (`Optimized_CityHash64_UTF16`) hash-preserving merge, UE5 Pak v11 (`0x5A6F12E1`) with `PrimaryIndex`, `PathHashIndex`, `FullDirectoryIndex`, and `EncodedPakEntries`, 64-bit Zlib & Oodle (`oo2core_*_win64.dll`) decompression, and IoStore `.utoc`/`.ucas` compressed block extraction.
3. **FORGE v27 & v50 Archives**:
   - Append-only TOC patching for `DataPC*.forge` with byte-exact truncate rollback and `steam_api.ini` / `upc_r2.ini` configuration sync.
4. **Universal Desktop & Game Subtitle Formats**:
   - `.srt`, `.vtt`, `.ass`, `.ssa`, `.json`, `.csv`, and `.xml` synchronization plus live Out-of-Process DWM Topmost Overlay HUD.

## 2. Anti-Cheat Safety & Save Protection
- **Zero-Injection Mode**: Never injects DLLs or opens foreign process handles (`OpenProcess`), preventing any false-positive flags from anti-cheat systems.
- **SaveBackupManager ("Restore Save")**: Automatically backs up save files and user profiles before every operation and provides 1-click restoration across GUI, Overlay, System Tray, and CLI (`--restore-save`).
