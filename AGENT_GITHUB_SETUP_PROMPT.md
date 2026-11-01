# 🤖 Master Agent Prompt: Deploy DualTitle GitHub Repository, GitHub Pages Website & Official Releases

Copy and paste the prompt below directly to your coding/deployment agent along with **`dualtitle.zip`**:

---

```markdown
You are tasked with setting up and publishing the official GitHub repository, GitHub Pages website, and GitHub Releases page for **DualTitle (v4.1.0)** using the provided `dualtitle.zip` archive.

## 1. Archive Inventory & Project Structure

When you unzip `dualtitle.zip`, all working source files, compiled Windows launchers, branding assets, website files, and CI/CD workflows are organized in `dualtitle/`:

- **Windows 64-Bit Native GUI Executables (Root & `docs/downloads/`)**:
  - `DualTitle.exe` — 64-bit Windows GUI launcher (`PE32+ x86-64, Subsystem: WINDOWS_GUI`) with the custom DualTitle icon embedded in `.rsrc`.
  - `RestoreSave.exe` — 64-bit Windows 1-Click Save & Profile recovery executable (`PE32+ x86-64, Subsystem: WINDOWS_GUI`).
  - `DualTitle.bat`, `RESTORE_SAVE.bat`, `EMERGENCY_REPAIR.bat`, `build_cpp.bat`, `PUBLISH_TO_GITHUB.bat`, `run.bat`, `run_tray.bat`.
- **Branding & Icon Assets (`assets/`)**:
  - `assets/logo.svg` — Official vector DualTitle Gamepad + Tilted Dual-Subtitle Bars logo.
  - `assets/logo.png` — High-resolution 512×512 PNG emblem.
  - `assets/dualtitle.ico` (plus `dualtitle.ico` and `dualsub_tray.ico` in root) — Multi-resolution 32-bit BGRA Windows icon.
- **C++17 & Rust Native Source Code (`src/`, `CMakeLists.txt`, `Cargo.toml`)**:
  - `src/DualTitle.cpp` — Main C++17 native Win32 Dark Control Panel GUI, multi-drive game scanner (`C:`–`Z:`), and `--self-test` suite.
  - `src/DualTitleEngine.hpp` — Anti-cheat-safe read-only subtitle indexer, `SaveBackupManager` (`RestoreSaves` / `BackupSaves`), Frostbite (`.sb`/`.toc` & `PROF_SAVE_profile`), Unreal Engine 4/5 (`.locres` v1–v3, `.pak` v11), FORGE v27/v50, and SRT/VTT/ASS/JSON/CSV engine.
  - `src/DualTitleOverlay.hpp` — Out-of-process Win32 topmost HUD (`WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_NOACTIVATE`) with interactive clickable words for instant dictionary definitions, live `0.25x`–`2.00x` speed controls (`- Spd`, `1.00x`, `+ Spd`, `▶ Auto:ON/OFF`), safe `ESC` game pause (`ALT+F9`), borderless window toggle (`ALT+F11`), and `💾 Restore Save`.
  - `src/DualTitle.rc` — Windows resource script embedding `assets/dualtitle.ico`.
  - `src/main.rs` & `Cargo.toml` — Native Rust entry point and build manifest.
- **Win32 & Python Modules (Root, `data/`, `dictionaries/`)**:
  - `universal_dualsub.py`, `tray_controller.py`, `subtitle_engine.py`, `config_patcher.py`, `dictionary_engine.py`, `startup_manager.py`, `dualsub_installer.py`, `DualSub.lua`, `dualsub-settings.json`.
  - `dictionaries/famous_dictionary_cache.json`, `dictionaries/dict_en_de.json`, `dictionaries/dict_de_en.json`, `data/en_de.json`, `data/de_en.json`.
- **GitHub Pages Website & Static Release Downloads (`docs/` & `index.html`)**:
  - `docs/index.html` (mirrored at root `index.html`) — Single-file interactive GitHub Pages site featuring the official DualTitle SVG logo, live interactive Control Panel & In-Game Overlay HUD simulator, **Official Releases & Direct Downloads (`#releases`)** section, and GitHub Setup Wizard.
  - `docs/downloads/DualTitle.exe`, `docs/downloads/RestoreSave.exe`, and `docs/downloads/DualTitle-Windows-x64.zip` — Direct static download binaries served immediately by GitHub Pages.
- **GitHub Actions CI/CD & Release Documentation (`.github/workflows/` & `RELEASE_NOTES_v4.1.0.md`)**:
  - `.github/workflows/deploy-pages.yml` — Automatically deploys `docs/` to GitHub Pages on push to `main`.
  - `.github/workflows/release-exe.yml` — Compiles `DualTitle_Native.exe` via MSVC `cl.exe` on `windows-latest`, runs automated verification tests, packages `DualTitle-Windows-x64.zip`, and publishes/updates the `v4.1.0` GitHub Release.
  - `RELEASE_NOTES_v4.1.0.md` — Full markdown release notes and asset table for the GitHub Releases page.

---

## 2. Step-by-Step Execution Instructions for the Agent

Execute the following steps in order:

### Step 1: Unzip and Verify Integrity
1. Extract `dualtitle.zip` and `cd` into the extracted `dualtitle/` directory.
2. Run the automated verification suite to confirm all 6 Python tests and all 5 C++17 tests pass before pushing:
   ```bash
   python3 universal_dualsub.py --self-test
   ```

### Step 2: Initialize Git & Create/Push to the GitHub Repository
1. Initialize the Git repository on the `main` branch and commit all files (ensuring `.github/workflows/`, `docs/index.html`, `docs/downloads/*`, `DualTitle.exe`, `RestoreSave.exe`, `assets/*`, and `src/*` are tracked):
   ```bash
   git init
   git branch -M main
   git add -f .
   git commit -m "Release DualTitle v4.1.0: Native .EXE Launcher, Anti-Cheat-Safe Overlay HUD, Save Restore & GitHub Pages"
   ```
2. If using the GitHub CLI (`gh`), create the public repository and push:
   ```bash
   gh repo create dualtitle --public --source=. --remote=origin --push
   ```
   *(Or if a remote repository URL already exists, run `git remote add origin <REPO_URL>` and `git push -u origin main --force`.)*

### Step 3: Publish the Official GitHub Release (`v4.1.0`) with Downloadable Binaries
1. Tag `v4.1.0` and push the tag so `.github/workflows/release-exe.yml` triggers automatically:
   ```bash
   git tag -a v4.1.0 -m "DualTitle v4.1.0 — Universal Anti-Cheat-Safe Edition (Windows x64)"
   git push origin v4.1.0
   ```
2. Also create/verify the GitHub Release immediately via `gh release create` attaching all downloadable binaries and `RELEASE_NOTES_v4.1.0.md`:
   ```bash
   gh release create v4.1.0 \
     DualTitle.exe \
     RestoreSave.exe \
     docs/downloads/DualTitle-Windows-x64.zip \
     --title "DualTitle v4.1.0 — Universal Anti-Cheat-Safe Edition (Windows x64)" \
     --notes-file RELEASE_NOTES_v4.1.0.md
   ```

### Step 4: Enable & Verify GitHub Pages (`docs/`)
1. Enable GitHub Pages via GitHub Actions (or from branch `main` `/docs` folder) using the GitHub API:
   ```bash
   gh api -X POST repos/{owner}/{repo}/pages \
     -f build_type="workflow" \
     -f source[branch]="main" \
     -f source[path]="/docs" || \
   gh api -X PUT repos/{owner}/{repo}/pages \
     -f build_type="workflow" \
     -f source[branch]="main" \
     -f source[path]="/docs"
   ```
2. Trigger `.github/workflows/deploy-pages.yml` if needed (`gh workflow run deploy-pages.yml`) and return:
   - The live **GitHub Pages URL** (`https://<owner>.github.io/<repo>/`)
   - The live **GitHub Releases URL** (`https://github.com/<owner>/<repo>/releases/tag/v4.1.0`)
   - Direct download URLs for `DualTitle.exe`, `RestoreSave.exe`, and `DualTitle-Windows-x64.zip`.

---

## 3. Hard Constraints (Do Not Violate)
- **Never mention specific third-party game titles** anywhere in the repository description, website text, release notes, or code comments. Keep DualTitle 100% universal across all games and applications.
- **Preserve the official DualTitle logo** (`assets/logo.svg`, `assets/logo.png`, `assets/dualtitle.ico`) and keep `DualTitle.exe` and `RestoreSave.exe` intact in both the repository root and `docs/downloads/`.
```
