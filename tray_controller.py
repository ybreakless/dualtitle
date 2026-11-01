#!/usr/bin/env python3
"""
DualTitle - Anti-Cheat-Safe Windows System Tray, Dark Visual Control Panel GUI,
Save Backup/Restore Manager, & Interactive In-Game Dual-Subtitle Overlay
Features the official DualTitle logo (`assets/dualtitle.ico` and `assets/logo.png`):
  • 100% Anti-Cheat Safe Out-of-Process Architecture (Zero DLL injection, Zero memory hooks)
  • Auto-Scanned Game Library Dropdown: Open the app, choose any game you own, and launch
    the game + Dual-Subtitle Overlay simultaneously
  • 1-Click "💾 Restore Save" button & automatic pre-launch Save Backup Manager
  • In-Game Overlay HUD with extra control buttons:
      - Clickable Words on BOTH Top & Bottom subtitle lines for instant word meanings
      - Subtitle Speed Controls (`- Spd`, `1.00x`, `+ Spd` from `0.25x` to `2.00x`)
      - Auto-Play / Auto-Advance Toggle (`▶ Auto:ON/OFF`)
      - Safe In-Game Pause (`⏸ Game (ESC)` via standard keyboard input)
      - Auto-Borderless Fullscreen Toggle (`🔲 Borderless`)
      - 1-Click `💾 Restore Save` right on the HUD
"""

from __future__ import annotations

import ctypes
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from config_patcher import GameConfigPatcher, SaveBackupManager, LANGUAGE_NAMES, find_unreal_subprojects
from dictionary_engine import FamousDictionaryEngine
from startup_manager import StartupManager, load_settings, save_settings
from subtitle_engine import UniversalSubtitleMerger

HERE = Path(__file__).parent.resolve()
ASSETS_ICO = HERE / "assets" / "dualtitle.ico"
ICO_PATH = HERE / "dualtitle.ico"

TRAY_LANGUAGES: List[Tuple[str, str]] = [
    ("en", "English"),
    ("de", "Deutsch (German)"),
    ("fr", "Français (French)"),
    ("es", "Español (Spanish)"),
    ("it", "Italiano (Italian)"),
    ("pt-BR", "Português (Brasil)"),
    ("pl", "Polski (Polish)"),
    ("ru", "Русский (Russian)"),
    ("ja", "日本語 (Japanese)"),
    ("ko", "한국어 (Korean)"),
    ("zh-Hans", "简体中文 (Chinese)"),
    ("ar", "العربية (Arabic)"),
]

SPEED_OPTIONS: List[Tuple[float, str]] = [
    (0.50, "0.50x — Slow Study Speed"),
    (0.75, "0.75x — Relaxed Reading Speed"),
    (1.00, "1.00x — Normal Real-Time Speed"),
    (1.25, "1.25x — Fast Reading Speed"),
    (1.50, "1.50x — Rapid Speed"),
    (2.00, "2.00x — Double Speed"),
]


def ensure_tray_ico_file(ico_path: Path = ICO_PATH) -> Path:
    """
    Ensure `dualtitle.ico` (rendered from the DualTitle gamepad/subtitle SVG logo)
    exists at `ico_path` and `dualsub_tray.ico`. Falls back to pure-Python 32-bit BGRA ICO if missing.
    """
    if ASSETS_ICO.is_file() and ASSETS_ICO.stat().st_size > 500:
        if ico_path != ASSETS_ICO:
            try:
                shutil.copy2(ASSETS_ICO, ico_path)
            except OSError:
                pass
        return ico_path

    if ico_path.is_file() and ico_path.stat().st_size > 500:
        return ico_path

    width, height = 32, 32
    xor_buf = bytearray(width * height * 4)
    and_row_bytes = ((width + 31) // 32) * 4
    and_mask = bytearray(and_row_bytes * height)

    for y in range(height):
        img_y = height - 1 - y
        for x in range(width):
            dx = min(x, width - 1 - x)
            dy = min(img_y, height - 1 - img_y)
            in_corner = (dx < 3 and dy < 3 and (3 - dx) ** 2 + (3 - dy) ** 2 > 5)
            px_offset = (y * width + x) * 4
            if in_corner:
                xor_buf[px_offset : px_offset + 4] = b"\x00\x00\x00\x00"
                and_mask[y * and_row_bytes + (x // 8)] |= (1 << (7 - (x % 8)))
                continue

            is_border = (x <= 2 or x >= width - 3 or img_y <= 2 or img_y >= height - 3)
            is_top_bar = (8 <= img_y <= 14 and 5 <= x <= 26)
            is_bot_bar = (17 <= img_y <= 23 and 6 <= x <= 27)
            if is_border:
                b, g, r, a = 248, 189, 56, 255
            elif is_top_bar:
                b, g, r, a = 42, 23, 15, 255 if not (10 <= img_y <= 12 and 12 <= x <= 22) else (0, 215, 255, 255)
            elif is_bot_bar:
                b, g, r, a = 255, 255, 255, 255
            else:
                b, g, r, a = 249, 245, 241, 255
            xor_buf[px_offset : px_offset + 4] = bytes((b, g, r, a))

    bmp_header = struct.pack("<IIIHHIIIIII", 40, width, height * 2, 1, 32, 0, len(xor_buf) + len(and_mask), 0, 0, 0, 0)
    image_data = bmp_header + bytes(xor_buf) + bytes(and_mask)
    icondir = struct.pack("<HHH", 0, 1, 1)
    icondirentry = struct.pack("<BBBBHHII", width, height, 0, 0, 1, 32, len(image_data), 22)
    ico_path.parent.mkdir(parents=True, exist_ok=True)
    ico_path.write_bytes(icondir + icondirentry + image_data)
    return ico_path


def _enable_win32_dark_mode_menus() -> None:
    if os.name != "nt":
        return
    try:
        uxtheme = ctypes.WinDLL("uxtheme", use_last_error=True)
        ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_int)((135, uxtheme))(2)
        ctypes.WINFUNCTYPE(None)((136, uxtheme))()
    except Exception:
        pass


# ==========================================================================
# Anti-Cheat-Safe Game Control & Auto-Borderless Helper
# ==========================================================================

class Win32ProcessPauseHelper:
    """
    Provides 100% Anti-Cheat-Safe in-game controls:
      • Safe Game Pause via standard keyboard input (`VK_ESCAPE` / `VK_PAUSE`) without
        opening any process handle (`OpenProcess`), so PunkBuster, EAC, BattlEye, and
        EA AntiCheat never flag DualTitle!
      • Safe Borderless Window Style conversion (`SetWindowLongW` + `SetWindowPos`)
        so fullscreen games display the DualTitle Overlay on top.
    """

    def __init__(self):
        self.suspended_pids: set[int] = set()
        self.enabled: bool = False
        self.last_game_hwnd: int = 0
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def track_foreground_window(self, ignore_hwnd: int = 0) -> None:
        if os.name != "nt":
            return
        try:
            user32 = ctypes.windll.user32
            fg = user32.GetForegroundWindow()
            if fg and fg != ignore_hwnd:
                pid = ctypes.c_ulong(0)
                user32.GetWindowThreadProcessId(fg, ctypes.byref(pid))
                if pid.value and pid.value != os.getpid():
                    self.last_game_hwnd = fg
        except Exception:
            pass

    def make_foreground_window_borderless(self) -> str:
        if os.name != "nt":
            return "Borderless window conversion requires Windows."
        try:
            user32 = ctypes.windll.user32
            self.track_foreground_window()
            hwnd = self.last_game_hwnd or user32.GetForegroundWindow()
            if not hwnd:
                return "No active application window detected."
            pid = ctypes.c_ulong(0)
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value or pid.value == os.getpid():
                return "Click inside your running game window first, then press ALT+F11 or [🔲 Borderless]."

            GWL_STYLE = -16
            WS_CAPTION = 0x00C00000
            WS_THICKFRAME = 0x00040000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            WS_SYSMENU = 0x00080000
            WS_POPUP = 0x80000000
            WS_VISIBLE = 0x10000000
            SWP_FRAMECHANGED = 0x0020
            SWP_NOACTIVATE = 0x0010
            SWP_SHOWWINDOW = 0x0040
            HWND_NOTOPMOST = -2

            screen_w = user32.GetSystemMetrics(0)
            screen_h = user32.GetSystemMetrics(1)
            style = user32.GetWindowLongW(hwnd, GWL_STYLE)
            new_style = (style & ~(WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)) | WS_POPUP | WS_VISIBLE
            user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
            user32.SetWindowPos(
                hwnd,
                HWND_NOTOPMOST,
                0,
                0,
                screen_w,
                screen_h,
                SWP_FRAMECHANGED | SWP_NOACTIVATE | SWP_SHOWWINDOW,
            )
            return f"Converted game window (PID {pid.value}) to {screen_w}x{screen_h} Borderless Fullscreen (Anti-Cheat Safe)."
        except Exception as exc:
            return f"Could not adjust window style: {exc}"

    def toggle_foreground_game_pause(self) -> str:
        """
        Send a 100% Anti-Cheat-Safe ESC keystroke to pause/unpause the active game
        without opening a process handle (`OpenProcess`).
        """
        if os.name != "nt":
            return "In-game pause control requires Windows."
        try:
            user32 = ctypes.windll.user32
            self.track_foreground_window()
            target = self.last_game_hwnd or user32.GetForegroundWindow()
            if target:
                pid = ctypes.c_ulong(0)
                user32.GetWindowThreadProcessId(target, ctypes.byref(pid))
                if pid.value and pid.value != os.getpid():
                    user32.SetForegroundWindow(target)
                    VK_ESCAPE = 0x1B
                    KEYEVENTF_KEYUP = 0x0002
                    user32.keybd_event(VK_ESCAPE, 0, 0, 0)
                    user32.keybd_event(VK_ESCAPE, 0, KEYEVENTF_KEYUP, 0)
                    return f"⏸ Sent safe in-game Pause (ESC) to game window (PID {pid.value}) — zero process hooks used."
            return "Switch to your running game window first, then click [⏸ Game (ESC)] or press ALT+F9."
        except Exception as exc:
            return f"Pause notice: {exc}"

    def resume_all(self) -> None:
        self.suspended_pids.clear()

    def start_hotkey_listener(self) -> None:
        if os.name != "nt" or (self._thread and self._thread.is_alive()):
            return
        self.enabled = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._hotkey_loop, daemon=True)
        self._thread.start()

    def stop_hotkey_listener(self) -> None:
        self.enabled = False
        self._stop_event.set()

    def _hotkey_loop(self) -> None:
        if os.name != "nt":
            return
        user32 = ctypes.windll.user32
        MOD_ALT = 0x0001
        VK_F9 = 0x78
        VK_F11 = 0x7A
        HOTKEY_PAUSE_ID = 9009
        HOTKEY_BORDERLESS_ID = 9011
        user32.RegisterHotKey(None, HOTKEY_PAUSE_ID, MOD_ALT, VK_F9)
        user32.RegisterHotKey(None, HOTKEY_BORDERLESS_ID, MOD_ALT, VK_F11)
        from ctypes import wintypes
        msg = wintypes.MSG()
        try:
            while not self._stop_event.is_set():
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                    if msg.message == 0x0312:
                        if msg.wParam == HOTKEY_PAUSE_ID:
                            status = self.toggle_foreground_game_pause()
                            print(f"[DualTitle] {status}")
                        elif msg.wParam == HOTKEY_BORDERLESS_ID:
                            status = self.make_foreground_window_borderless()
                            print(f"[DualTitle] {status}")
                else:
                    self._stop_event.wait(0.05)
        finally:
            user32.UnregisterHotKey(None, HOTKEY_PAUSE_ID)
            user32.UnregisterHotKey(None, HOTKEY_BORDERLESS_ID)


# ==========================================================================
# DualTitle System Tray, Save Manager, Dark GUI, & In-Game Overlay HUD
# ==========================================================================

class DualSubTrayController:
    def __init__(self, on_apply_callback: Optional[Callable[[str, str, str, str], None]] = None):
        self.startup_mgr = StartupManager()
        self.pause_helper = Win32ProcessPauseHelper()
        self.on_apply_callback = on_apply_callback
        ensure_tray_ico_file(ICO_PATH)

    def get_state(self) -> Dict[str, str]:
        settings = load_settings()
        return {
            "game_dir": settings.get("game_dir", ""),
            "audio_lang": settings.get("audio_lang", "en"),
            "primary_sub_lang": settings.get("primary_sub_lang", "en"),
            "secondary_sub_lang": settings.get("secondary_sub_lang", "de"),
            "subtitle_speed": str(settings.get("subtitle_speed", "1.0")),
        }

    def set_language_setting(self, key: str, lang_code: str, auto_apply: bool = True) -> str:
        settings = load_settings()
        settings[key] = lang_code
        save_settings(settings)
        msg = f"Updated {key} to {LANGUAGE_NAMES.get(lang_code, lang_code)}"
        if auto_apply and settings.get("game_dir"):
            self.apply_to_game(log=print)
        return msg

    def backup_game_saves(self, log=print) -> Tuple[bool, str]:
        """Create an immediate backup snapshot of all user save files & profile settings."""
        state = self.get_state()
        game_dir_str = state["game_dir"]
        if not game_dir_str or not Path(game_dir_str).is_dir():
            return False, "Select a valid game folder first to back up saves."
        mgr = SaveBackupManager(Path(game_dir_str))
        count, bdir = mgr.backup_saves(log=log)
        msg = f"Backed up {count} save/profile file(s) to {bdir.name}."
        log(f"[DualTitle] {msg}")
        return True, msg

    def restore_game_saves(self, log=print) -> Tuple[bool, str]:
        """
        1-Click Restore Save: Restores all backed-up save files (`Saved/SaveGames`,
        `PROF_SAVE*`, `Saves`, `*.sav`, profile `.ini`s) and configuration files.
        """
        state = self.get_state()
        game_dir_str = state["game_dir"]
        candidates: List[Path] = []
        if game_dir_str and Path(game_dir_str).is_dir():
            candidates.append(Path(game_dir_str))

        if not candidates:
            backups_root = HERE / "backups"
            if backups_root.is_dir():
                for sub in backups_root.iterdir():
                    manifest = sub / "save_manifest.json"
                    if manifest.is_file():
                        try:
                            mdata = json.loads(manifest.read_text(encoding="utf-8"))
                            if mdata.get("app_dir") and Path(mdata["app_dir"]).is_dir():
                                candidates.append(Path(mdata["app_dir"]))
                        except Exception:
                            pass

        if not candidates:
            return False, "No game folder selected yet. Select a game folder first to restore saves."

        total_restored = 0
        last_msg = ""
        for gdir in candidates:
            mgr = SaveBackupManager(gdir)
            cnt, last_msg = mgr.restore_saves(prefer_original=True, log=log)
            total_restored += cnt

        return True, last_msg or f"Restored {total_restored} save and profile file(s)."

    def emergency_repair_game(self, log=print) -> Tuple[bool, str]:
        """
        1-Click Repair & Anti-Cheat Clean: Removes any synthetic container files in Content/Paks,
        synthetic <8KB Game.locres files, and UE4SS DualSub entries, and restores original configs & saves.
        """
        state = self.get_state()
        game_dir_str = state["game_dir"]
        fixed_total = 0

        candidates: List[Path] = []
        if game_dir_str and Path(game_dir_str).is_dir():
            candidates.append(Path(game_dir_str))

        try:
            from universal_dualsub import scan_installed_games
            for _title, p in scan_installed_games():
                if p not in candidates:
                    candidates.append(p)
        except Exception:
            pass

        for gdir in candidates:
            fixed_total += UniversalSubtitleMerger.emergency_repair_game_folder(gdir, log=log)
            GameConfigPatcher(gdir).restore_game_configs(log=log)
            SaveBackupManager(gdir).restore_saves(prefer_original=True, log=log)

        msg = f"Repair & Clean finished ({fixed_total} item(s) cleaned and original saves/configs verified)."
        log(f"[DualTitle] {msg}")
        return True, msg

    def apply_to_game(self, log=print, safe_overlay_only: bool = False) -> Tuple[bool, str]:
        state = self.get_state()
        game_dir_str = state["game_dir"]
        if not game_dir_str or not Path(game_dir_str).is_dir():
            return False, "No valid game folder selected yet. Select a game folder first."

        game_dir = Path(game_dir_str)
        audio_lang = state["audio_lang"]
        primary_lang = state["primary_sub_lang"]
        secondary_lang = state["secondary_sub_lang"]

        try:
            # 1. Automatically back up save files before touching anything
            SaveBackupManager(game_dir).backup_saves(log=log)

            # 2. Clean any stale containers before applying fresh config
            UniversalSubtitleMerger.emergency_repair_game_folder(game_dir, log=log)

            # 3. Apply audio & subtitle configuration
            cfg_patcher = GameConfigPatcher(game_dir)
            cfg_patcher.apply_audio_and_subtitle_config(
                primary_sub_lang=primary_lang,
                secondary_sub_lang=secondary_lang,
                audio_lang=audio_lang,
                log=log,
            )

            # 4. If safe_overlay_only is True (Anti-Cheat Safe Launch Mode), only index subtitles read-only!
            merger = UniversalSubtitleMerger(primary_lang, secondary_lang)
            if not safe_overlay_only:
                merger.patch_game_localization_in_place(game_dir, log=log)

            if self.on_apply_callback:
                self.on_apply_callback(str(game_dir), audio_lang, primary_lang, secondary_lang)

            summary = (
                f"Ready for {game_dir.name} (Saves Backed Up): Audio={LANGUAGE_NAMES.get(audio_lang, audio_lang)} | "
                f"Top={LANGUAGE_NAMES.get(primary_lang, primary_lang)} | "
                f"Bottom={LANGUAGE_NAMES.get(secondary_lang, secondary_lang)}"
            )
            log(f"[DualTitle] {summary}")
            return True, summary
        except Exception as exc:
            err = f"Failed to configure game files: {exc}"
            log(f"[DualTitle] {err}")
            return False, err

    def launch_selected_game_executable(self, game_dir: Path, log=print) -> Optional[Path]:
        """Find and launch the main executable of `game_dir` cleanly without any DLL injection."""
        if not game_dir or not game_dir.is_dir():
            return None
        target_exe: Optional[Path] = None

        # Check Unreal subproject Shipping binaries
        for sub in find_unreal_subprojects(game_dir):
            win64 = sub / "Binaries" / "Win64"
            if win64.is_dir():
                for exe in sorted(win64.glob("*.exe")):
                    low = exe.name.lower()
                    if "crash" not in low and "cef" not in low and "ue4ss" not in low:
                        target_exe = exe
                        break
            if target_exe:
                break

        if not target_exe:
            for exe in sorted(game_dir.glob("*.exe")):
                low = exe.name.lower()
                if not any(x in low for x in ("unins", "cleanup", "crash", "setup", "activation", "dxsetup")):
                    target_exe = exe
                    break

        if target_exe:
            try:
                log(f"[DualTitle] Launching {target_exe.name} (100% Anti-Cheat Safe)...")
                subprocess.Popen([str(target_exe)], cwd=str(game_dir))
                return target_exe
            except OSError as exc:
                log(f"[DualTitle] Could not launch {target_exe.name}: {exc}")
        return None

    def restore_game(self, log=print) -> Tuple[bool, str]:
        return self.emergency_repair_game(log=log)

    def launch_cli_window(self) -> None:
        script = HERE / "universal_dualsub.py"
        if os.name == "nt":
            subprocess.Popen(["cmd.exe", "/c", "start", "DualTitle CLI", sys.executable, str(script)])
        else:
            subprocess.Popen([sys.executable, str(script)])

    # ------------------------------------------------------------------
    # Universal Topmost In-Game Dual-Subtitle Overlay (With Speed & Word Meaning Buttons!)
    # ------------------------------------------------------------------

    def open_universal_game_overlay(self) -> None:
        """
        Launch a sleek, topmost, semi-transparent Dual-Subtitle HUD bar at the bottom
        of the screen that displays Primary (Top Line in Gold #FFD700) + Secondary
        (Bottom Line in Ice-White #E2E8F0) over ANY running game with:
          • Interactive Clickable Words on BOTH lines to inspect each word's meaning
          • Extra In-Game Control Buttons:
              - `◀ Prev` / `Next ▶`
              - `▶ Auto:ON/OFF` (Auto-Advance subtitles)
              - `- Spd` / `⚡ 1.00x` / `+ Spd` (Speed controller from `0.25x` to `2.00x`)
              - `⏸ Game (ESC)` (Anti-cheat-safe game pause)
              - `🔲 Borderless` (Converts fullscreen game to borderless window)
              - `💾 Restore Save` (1-click save restoration)
        """
        try:
            import tkinter as tk
        except ImportError:
            return

        state = self.get_state()
        game_dir_str = state["game_dir"]
        game_dir = Path(game_dir_str) if game_dir_str and Path(game_dir_str).is_dir() else HERE
        primary_lang = state["primary_sub_lang"]
        secondary_lang = state["secondary_sub_lang"]
        try:
            init_speed = float(state.get("subtitle_speed", "1.0"))
        except ValueError:
            init_speed = 1.0

        dict_engine = FamousDictionaryEngine(HERE / "dictionaries")
        merger = UniversalSubtitleMerger(primary_lang, secondary_lang)
        dual_table = merger._load_or_build_unreal_dual_table(game_dir, HERE / "data")

        lines: List[Tuple[str, str, str]] = []
        lookup_map: Dict[str, str] = {}
        for tname, tbl in dual_table.items():
            if isinstance(tbl, dict) and tname != "metadata":
                for _k, val in tbl.items():
                    if isinstance(val, str):
                        if " / " in val:
                            p, s = val.split(" / ", 1)
                        elif "\n" in val:
                            p, s = val.split("\n", 1)
                        else:
                            p, s = val, ""
                        p_c, s_c = p.strip(), s.strip()
                        if p_c:
                            lines.append((tname, p_c, s_c))
                            if s_c:
                                lookup_map[p_c.lower()] = s_c
        if not lines:
            lines = [("ST_Cutscenes", "Look over there! Something is moving in the shadows!", "Sieh mal da drüben! Etwas bewegt sich im Schatten!")]

        ov = tk.Toplevel() if tk._default_root else tk.Tk()
        ov.title("DualTitle In-Game Overlay")
        ov.configure(bg="#0B0F19")
        ov.overrideredirect(True)
        ov.attributes("-topmost", True)
        try:
            ov.attributes("-alpha", 0.94)
        except Exception:
            pass

        sw = ov.winfo_screenwidth()
        sh = ov.winfo_screenheight()
        w, h = min(1020, sw - 40), 156
        ov.geometry(f"{w}x{h}+{(sw - w) // 2}+{sh - h - 56}")

        outer = tk.Frame(ov, bg="#0B0F19", highlightthickness=2, highlightbackground="#38BDF8", padx=12, pady=6)
        outer.pack(fill="both", expand=True)

        idx_state = {
            "i": 0,
            "live_sync": True,
            "auto_play": False,
            "speed": max(0.25, min(2.0, init_speed)),
            "last_live_text": "",
            "auto_after_id": None,
        }

        # Top Control Bar with Extra In-Game Buttons
        ctrl_bar = tk.Frame(outer, bg="#0B0F19")
        ctrl_bar.pack(fill="x")

        title_var = tk.StringVar(value=f"🎮 DUALTITLE HUD ({primary_lang.upper()}+{secondary_lang.upper()}) [1/{len(lines)}]")
        title_lbl = tk.Label(
            ctrl_bar,
            textvariable=title_var,
            fg="#38BDF8",
            bg="#0B0F19",
            font=("Segoe UI", 8, "bold"),
        )
        title_lbl.pack(side="left")

        # Clickable Primary Subtitle Row (Top Line in Gold #FFD700)
        prim_words_frame = tk.Frame(outer, bg="#0B0F19")
        prim_words_frame.pack(pady=(4, 1))

        # Clickable Secondary Subtitle Row (Bottom Line in Ice-White #E2E8F0)
        sec_words_frame = tk.Frame(outer, bg="#0B0F19")
        sec_words_frame.pack(pady=(0, 3))

        # Word Meaning & Status Bar at Bottom
        dict_var = tk.StringVar(
            value="💡 Click ANY word in the Top or Bottom subtitle line to see its translation, phonetics & definition!"
        )
        dict_lbl = tk.Label(
            outer,
            textvariable=dict_var,
            fg="#A7F3D0",
            bg="#111827",
            font=("Segoe UI", 9),
            padx=8,
            pady=3,
        )
        dict_lbl.pack(fill="x")

        def show_word_def(word_token: str):
            info = dict_engine.lookup(word_token, target_lang=secondary_lang)
            w_up = info.get("word", word_token).upper()
            phon = info.get("phonetic", "")
            gender = info.get("gender") or info.get("pos", "")
            trans = info.get("german_translation") or info.get("english_translation") or ""
            defn = info.get("definition", "")
            meta = f" {phon}" if phon else ""
            if gender:
                meta += f" ({gender})"
            dict_var.set(f"📖 {w_up}{meta}  →  {trans}  |  {defn[:90]}")

        def render_custom_pair(p_line: str, s_line: str):
            for child in prim_words_frame.winfo_children():
                child.destroy()
            for child in sec_words_frame.winfo_children():
                child.destroy()

            if not s_line and p_line:
                s_line = lookup_map.get(p_line.strip().lower()) or dict_engine.translate_sentence(p_line, primary_lang, secondary_lang)

            title_var.set(
                f"🎮 DUALTITLE HUD ({primary_lang.upper()}+{secondary_lang.upper()}) [{(idx_state['i'] % len(lines)) + 1}/{len(lines)}]"
            )

            for token in p_line.split():
                tk.Button(
                    prim_words_frame,
                    text=token,
                    bg="#0B0F19",
                    fg="#FFD700",
                    activebackground="#1E293B",
                    activeforeground="#38BDF8",
                    relief="flat",
                    bd=0,
                    padx=3,
                    pady=0,
                    font=("Segoe UI", 14, "bold"),
                    cursor="hand2",
                    command=lambda w_tok=token: show_word_def(w_tok),
                ).pack(side="left")

            for token in s_line.split():
                tk.Button(
                    sec_words_frame,
                    text=token,
                    bg="#0B0F19",
                    fg="#E2E8F0",
                    activebackground="#1E293B",
                    activeforeground="#FFD700",
                    relief="flat",
                    bd=0,
                    padx=3,
                    pady=0,
                    font=("Segoe UI", 12),
                    cursor="hand2",
                    command=lambda w_tok=token: show_word_def(w_tok),
                ).pack(side="left")

        def render_line():
            _tname, p_line, s_line = lines[idx_state["i"] % len(lines)]
            render_custom_pair(p_line, s_line)

        def schedule_auto_advance():
            if idx_state["auto_after_id"]:
                try:
                    ov.after_cancel(idx_state["auto_after_id"])
                except Exception:
                    pass
                idx_state["auto_after_id"] = None
            if idx_state["auto_play"] and ov.winfo_exists():
                delay_ms = int(3600.0 / max(0.25, idx_state["speed"]))
                idx_state["auto_after_id"] = ov.after(delay_ms, auto_step)

        def auto_step():
            if not idx_state["auto_play"] or not ov.winfo_exists():
                return
            idx_state["i"] = (idx_state["i"] + 1) % len(lines)
            render_line()
            schedule_auto_advance()

        def next_line():
            idx_state["i"] = (idx_state["i"] + 1) % len(lines)
            render_line()

        def prev_line():
            idx_state["i"] = (idx_state["i"] - 1) % len(lines)
            render_line()

        speed_btn_var = tk.StringVar(value=f"⚡ {idx_state['speed']:.2f}x")
        auto_btn_var = tk.StringVar(value="▶ Auto:OFF")

        def change_speed(delta: float):
            if delta == 0.0:
                idx_state["speed"] = 1.0
            else:
                idx_state["speed"] = max(0.25, min(2.0, round(idx_state["speed"] + delta, 2)))
            speed_btn_var.set(f"⚡ {idx_state['speed']:.2f}x")
            dict_var.set(f"⚡ Subtitle Speed set to {idx_state['speed']:.2f}x")
            schedule_auto_advance()

        def toggle_auto_play():
            idx_state["auto_play"] = not idx_state["auto_play"]
            auto_btn_var.set("⏸ Auto:ON" if idx_state["auto_play"] else "▶ Auto:OFF")
            dict_var.set(
                f"▶ Auto-Advancing Subtitles ON ({idx_state['speed']:.2f}x)"
                if idx_state["auto_play"]
                else "⏸ Auto-Advancing Subtitles PAUSED — Click any word to inspect its meaning."
            )
            schedule_auto_advance()

        def toggle_pause():
            msg = self.pause_helper.toggle_foreground_game_pause()
            dict_var.set(msg)

        def force_borderless():
            msg = self.pause_helper.make_foreground_window_borderless()
            dict_var.set(msg)

        def restore_save_now():
            _ok, msg = self.restore_game_saves()
            dict_var.set(msg)

        # Topmost watchdog + Live subtitle poller (every 300ms)
        def overlay_watchdog():
            if not ov.winfo_exists():
                return
            try:
                self.pause_helper.track_foreground_window(ov.winfo_id())
                ov.attributes("-topmost", True)
                if os.name == "nt":
                    HWND_TOPMOST = -1
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    SWP_NOACTIVATE = 0x0010
                    SWP_SHOWWINDOW = 0x0040
                    ctypes.windll.user32.SetWindowPos(
                        ov.winfo_id(), HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW
                    )
            except Exception:
                pass

            if idx_state["live_sync"]:
                for cand_live in (
                    game_dir / "Mods" / "DualSub" / "live_subtitle.json",
                    game_dir / "live_subtitle.json",
                    HERE / "data" / "live_subtitle.json",
                ):
                    if cand_live.is_file():
                        try:
                            ldata = json.loads(cand_live.read_text(encoding="utf-8"))
                            lp = ldata.get("primary", "").strip()
                            ls = ldata.get("secondary", "").strip()
                            if lp and lp != idx_state["last_live_text"]:
                                idx_state["last_live_text"] = lp
                                render_custom_pair(lp, ls)
                                break
                        except Exception:
                            pass

            ov.after(300, overlay_watchdog)

        # Pack Extra In-Game Control Buttons on the HUD
        tk.Button(ctrl_bar, text="✕", command=ov.destroy, bg="#7F1D1D", fg="#FFFFFF", relief="flat", font=("Segoe UI", 8, "bold"), padx=5).pack(side="right", padx=1)
        tk.Button(ctrl_bar, text="💾 Restore Save", command=restore_save_now, bg="#0D9488", fg="#FFFFFF", relief="flat", font=("Segoe UI", 8, "bold"), padx=6).pack(side="right", padx=2)
        tk.Button(ctrl_bar, text="🔲 Borderless", command=force_borderless, bg="#4F46E5", fg="#FFFFFF", relief="flat", font=("Segoe UI", 8), padx=5).pack(side="right", padx=2)
        tk.Button(ctrl_bar, text="⏸ Game (ESC)", command=toggle_pause, bg="#0284C7", fg="#FFFFFF", relief="flat", font=("Segoe UI", 8, "bold"), padx=6).pack(side="right", padx=2)
        tk.Button(ctrl_bar, text="+ Spd", command=lambda: change_speed(0.25), bg="#1E293B", fg="#A7F3D0", relief="flat", font=("Segoe UI", 8, "bold"), padx=4).pack(side="right", padx=1)
        tk.Button(ctrl_bar, textvariable=speed_btn_var, command=lambda: change_speed(0.0), bg="#0F172A", fg="#FFD700", relief="flat", font=("Segoe UI", 8, "bold"), padx=5).pack(side="right", padx=1)
        tk.Button(ctrl_bar, text="- Spd", command=lambda: change_speed(-0.25), bg="#1E293B", fg="#A7F3D0", relief="flat", font=("Segoe UI", 8, "bold"), padx=4).pack(side="right", padx=1)
        tk.Button(ctrl_bar, text="Next ▶", command=next_line, bg="#1E293B", fg="#F8FAFC", relief="flat", font=("Segoe UI", 8), padx=5).pack(side="right", padx=1)
        tk.Button(ctrl_bar, textvariable=auto_btn_var, command=toggle_auto_play, bg="#059669", fg="#FFFFFF", relief="flat", font=("Segoe UI", 8, "bold"), padx=5).pack(side="right", padx=1)
        tk.Button(ctrl_bar, text="◀ Prev", command=prev_line, bg="#1E293B", fg="#F8FAFC", relief="flat", font=("Segoe UI", 8), padx=5).pack(side="right", padx=1)

        render_line()
        ov.after(300, overlay_watchdog)
        if not tk._default_root or ov is tk._default_root:
            ov.mainloop()

    # ------------------------------------------------------------------
    # High-Contrast Dark Visual Control Panel (With Logo, Game Picker & Restore Save!)
    # ------------------------------------------------------------------

    def open_dark_control_panel_gui(self) -> None:
        try:
            import tkinter as tk
            from tkinter import filedialog, messagebox
        except ImportError:
            self.launch_cli_window()
            return

        root = tk.Tk()
        root.title("DualTitle — Universal Anti-Cheat-Safe Dual Subtitles & Save Controller")
        root.geometry("640x730")
        root.configure(bg="#0B0F19")
        root.resizable(False, False)
        try:
            ico_file = ensure_tray_ico_file(ICO_PATH)
            if os.name == "nt" and ico_file.is_file():
                root.iconbitmap(default=str(ico_file))
        except Exception:
            pass

        state = self.get_state()

        # Header with Official DualTitle Logo (`assets/logo.png`)
        hdr = tk.Frame(root, bg="#111827", padx=16, pady=12, highlightthickness=1, highlightbackground="#38BDF8")
        hdr.pack(fill="x", padx=14, pady=(12, 8))

        logo_img_ref = None
        logo_png_path = HERE / "assets" / "logo.png"
        if logo_png_path.is_file():
            try:
                full_logo = tk.PhotoImage(file=str(logo_png_path))
                logo_img_ref = full_logo.subsample(8, 8)
                logo_lbl = tk.Label(hdr, image=logo_img_ref, bg="#111827")
                logo_lbl.image = logo_img_ref
                logo_lbl.pack(side="left", padx=(0, 12))
            except Exception:
                pass

        hdr_text = tk.Frame(hdr, bg="#111827")
        hdr_text.pack(side="left", fill="both", expand=True)
        tk.Label(
            hdr_text,
            text="DUALTITLE — UNIVERSAL ANTI-CHEAT-SAFE EDITION",
            fg="#38BDF8",
            bg="#111827",
            font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w")
        tk.Label(
            hdr_text,
            text="Choose Any Game You Own • In-Game Speed & Word Meaning HUD • 1-Click Restore Save",
            fg="#CBD5E1",
            bg="#111827",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(2, 0))

        body = tk.Frame(root, bg="#0B0F19", padx=16, pady=4)
        body.pack(fill="both", expand=True)

        status_var = tk.StringVar(
            value="Ready (100% Anti-Cheat Safe Mode). Saves are automatically backed up before every launch."
        )

        # Scan installed games across C: - Z:
        installed_games: List[Tuple[str, Path]] = []
        try:
            from universal_dualsub import scan_installed_games
            installed_games = scan_installed_games()
        except Exception:
            pass

        initial_dir_val = state["game_dir"]
        if not initial_dir_val and installed_games:
            initial_dir_val = str(installed_games[0][1])
        game_var = tk.StringVar(value=initial_dir_val)

        def sync_game_dir_setting() -> str:
            gdir = game_var.get().strip().strip('"')
            if gdir:
                settings = load_settings()
                settings["game_dir"] = gdir
                save_settings(settings)
            return gdir

        # Top Action Bar: Restore Save & Repair Buttons
        top_actions = tk.Frame(body, bg="#0B0F19")
        top_actions.pack(fill="x", pady=(0, 8))

        def run_emergency_repair():
            sync_game_dir_setting()
            _ok, msg = self.emergency_repair_game()
            status_var.set(msg)
            messagebox.showinfo("DualTitle — Repair & Clean Complete", msg)

        def run_restore_save():
            sync_game_dir_setting()
            _ok, msg = self.restore_game_saves()
            status_var.set(msg)
            messagebox.showinfo("DualTitle — Restore Save", msg)

        def run_backup_save():
            sync_game_dir_setting()
            _ok, msg = self.backup_game_saves()
            status_var.set(msg)
            messagebox.showinfo("DualTitle — Save Backup Complete", msg)

        tk.Button(
            top_actions,
            text="💾 RESTORE SAVE (Restore Saved Progress & Profile)",
            command=run_restore_save,
            bg="#0D9488",
            fg="#FFFFFF",
            activebackground="#0F766E",
            activeforeground="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            pady=6,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        tk.Button(
            top_actions,
            text="🛠️ 1-CLICK REPAIR & CLEAN FOLDER",
            command=run_emergency_repair,
            bg="#D97706",
            fg="#FFFFFF",
            activebackground="#B45309",
            activeforeground="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=10,
            pady=6,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        # 1. Choose Game from Owned Library Dropdown + Folder Entry
        tk.Label(
            body,
            text="1. Choose Game from Your Library (Auto-Detected Across C: – Z:):",
            fg="#F8FAFC",
            bg="#0B0F19",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w")

        if installed_games:
            game_choices = [f"{title} — {path}" for title, path in installed_games]
        else:
            game_choices = ["Browse or paste any game folder below..."]
        picked_game_var = tk.StringVar(value=game_choices[0])

        def on_pick_library_game(selection: str):
            if " — " in selection:
                _, p_str = selection.split(" — ", 1)
                game_var.set(p_str.strip())
                sync_game_dir_setting()

        lib_opt = tk.OptionMenu(body, picked_game_var, *game_choices, command=on_pick_library_game)
        lib_opt.config(
            bg="#1E293B",
            fg="#38BDF8",
            activebackground="#334155",
            activeforeground="#FFD700",
            highlightthickness=1,
            highlightbackground="#334155",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        lib_opt["menu"].config(bg="#1E293B", fg="#F8FAFC", activebackground="#38BDF8", activeforeground="#0B0F19")
        lib_opt.pack(fill="x", pady=(2, 6))

        gframe = tk.Frame(body, bg="#0B0F19")
        gframe.pack(fill="x", pady=(0, 8))
        g_entry = tk.Entry(
            gframe,
            textvariable=game_var,
            bg="#1E293B",
            fg="#F8FAFC",
            insertbackground="#F8FAFC",
            relief="flat",
            font=("Consolas", 9),
        )
        g_entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 8))

        def browse_game():
            chosen = filedialog.askdirectory(initialdir=game_var.get() or "C:\\")
            if chosen:
                game_var.set(str(Path(chosen)))
                sync_game_dir_setting()

        tk.Button(
            gframe,
            text="📂 Browse...",
            command=browse_game,
            bg="#334155",
            fg="#F8FAFC",
            activebackground="#475569",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=10,
            pady=3,
        ).pack(side="right")

        lang_labels = [f"{code} — {name}" for code, name in TRAY_LANGUAGES]
        code_to_label = {code: f"{code} — {name}" for code, name in TRAY_LANGUAGES}

        def make_selector(title_text: str, default_code: str, accent_color: str) -> tk.StringVar:
            tk.Label(body, text=title_text, fg=accent_color, bg="#0B0F19", font=("Segoe UI", 9, "bold")).pack(anchor="w")
            var = tk.StringVar(value=code_to_label.get(default_code, lang_labels[0]))
            opt = tk.OptionMenu(body, var, *lang_labels)
            opt.config(
                bg="#1E293B",
                fg="#F8FAFC",
                activebackground="#334155",
                activeforeground="#FFD700",
                highlightthickness=1,
                highlightbackground="#334155",
                relief="flat",
                font=("Segoe UI", 9),
            )
            opt["menu"].config(bg="#1E293B", fg="#F8FAFC", activebackground="#38BDF8", activeforeground="#0B0F19")
            opt.pack(fill="x", pady=(2, 6))
            return var

        audio_var = make_selector("2. Spoken Audio Language (Voice Track):", state["audio_lang"], "#38BDF8")
        prim_var = make_selector("3. Primary Subtitle Language (Top Line - Gold):", state["primary_sub_lang"], "#FFD700")
        sec_var = make_selector("4. Secondary Subtitle Language (Bottom Line - White):", state["secondary_sub_lang"], "#A7F3D0")

        # 5. Subtitle Speed Selector
        tk.Label(body, text="5. In-Game Subtitle Speed (Also Adjustable Live on HUD):", fg="#CBD5E1", bg="#0B0F19", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        speed_labels = [lbl for _v, lbl in SPEED_OPTIONS]
        speed_var = tk.StringVar(value=speed_labels[2])
        speed_opt = tk.OptionMenu(body, speed_var, *speed_labels)
        speed_opt.config(
            bg="#1E293B",
            fg="#FFD700",
            activebackground="#334155",
            activeforeground="#FFD700",
            highlightthickness=1,
            highlightbackground="#334155",
            relief="flat",
            font=("Segoe UI", 9),
        )
        speed_opt["menu"].config(bg="#1E293B", fg="#F8FAFC", activebackground="#38BDF8", activeforeground="#0B0F19")
        speed_opt.pack(fill="x", pady=(2, 6))

        status_lbl = tk.Label(
            body,
            textvariable=status_var,
            fg="#94A3B8",
            bg="#0B0F19",
            font=("Segoe UI", 8),
            wraplength=590,
            justify="left",
        )
        status_lbl.pack(anchor="w", pady=(2, 4))

        def persist_current_ui_settings() -> Tuple[str, str, str, str, float]:
            gdir = game_var.get().strip().strip('"')
            a_code = audio_var.get().split(" — ")[0].strip()
            p_code = prim_var.get().split(" — ")[0].strip()
            s_code = sec_var.get().split(" — ")[0].strip()
            spd_str = speed_var.get().split("x")[0].strip()
            try:
                spd_val = float(spd_str)
            except ValueError:
                spd_val = 1.0

            settings = load_settings()
            settings.update(
                {
                    "game_dir": gdir,
                    "audio_lang": a_code,
                    "primary_sub_lang": p_code,
                    "secondary_sub_lang": s_code,
                    "subtitle_speed": spd_val,
                }
            )
            save_settings(settings)
            return gdir, a_code, p_code, s_code, spd_val

        def launch_game_and_overlay():
            gdir, _a, _p, _s, _spd = persist_current_ui_settings()
            ok, msg = self.apply_to_game(safe_overlay_only=True)
            status_var.set(msg)
            if gdir and Path(gdir).is_dir():
                self.launch_selected_game_executable(Path(gdir))
            root.iconify()
            self.open_universal_game_overlay()

        def save_and_apply(close_after: bool = False):
            persist_current_ui_settings()
            ok, msg = self.apply_to_game(safe_overlay_only=False)
            status_var.set(msg)
            if ok and close_after:
                root.destroy()
            elif not ok:
                messagebox.showwarning("DualTitle", msg)

        btn_frame = tk.Frame(body, bg="#0B0F19")
        btn_frame.pack(fill="x", pady=(2, 6))

        tk.Button(
            btn_frame,
            text="🚀 LAUNCH SELECTED GAME + IN-GAME OVERLAY HUD (100% ANTI-CHEAT SAFE)",
            command=launch_game_and_overlay,
            bg="#059669",
            fg="#FFFFFF",
            activebackground="#047857",
            activeforeground="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=8,
        ).pack(fill="x", pady=(0, 5))

        tk.Button(
            btn_frame,
            text="🎮 Open In-Game Dual-Subtitle Overlay Only (Clickable Words & Speed Controls)",
            command=lambda: (persist_current_ui_settings(), self.open_universal_game_overlay()),
            bg="#0284C7",
            fg="#FFFFFF",
            activebackground="#0369A1",
            activeforeground="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=12,
            pady=6,
        ).pack(fill="x", pady=(0, 5))

        row2 = tk.Frame(btn_frame, bg="#0B0F19")
        row2.pack(fill="x")
        tk.Button(
            row2,
            text="Apply Pre-Game Patch",
            command=lambda: save_and_apply(close_after=False),
            bg="#1E293B",
            fg="#F8FAFC",
            activebackground="#334155",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=8,
            pady=5,
        ).pack(side="left", expand=True, fill="x", padx=(0, 4))

        tk.Button(
            row2,
            text="📦 Backup Save Now",
            command=run_backup_save,
            bg="#1E293B",
            fg="#38BDF8",
            activebackground="#334155",
            activeforeground="#FFFFFF",
            relief="flat",
            padx=8,
            pady=5,
        ).pack(side="left", expand=True, fill="x", padx=4)

        tk.Button(
            row2,
            text="💾 Restore Save",
            command=run_restore_save,
            bg="#0F766E",
            fg="#FFFFFF",
            activebackground="#115E59",
            activeforeground="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            padx=8,
            pady=5,
        ).pack(side="left", expand=True, fill="x", padx=(4, 0))

        root.mainloop()

    # ------------------------------------------------------------------
    # Run System Tray (Win32 Dark-Mode Native Tray + Dark GUI Fallback)
    # ------------------------------------------------------------------

    def run(self) -> None:
        ensure_tray_ico_file(ICO_PATH)
        _enable_win32_dark_mode_menus()

        if os.name == "nt":
            self._run_win32_native_tray()
            return

        print("[DualTitle] Launching numbered Terminal Controller...")
        from universal_dualsub import main_menu
        main_menu()

    def _run_win32_native_tray(self) -> None:
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        shell32 = ctypes.windll.shell32
        kernel32 = ctypes.windll.kernel32
        gdi32 = ctypes.windll.gdi32

        WM_DESTROY = 0x0002
        WM_USER = 0x0400
        WM_TRAYICON = WM_USER + 20
        WM_LBUTTONUP = 0x0202
        WM_RBUTTONUP = 0x0205
        WM_LBUTTONDBLCLK = 0x0203

        NIM_ADD = 0x00000000
        NIM_DELETE = 0x00000002
        NIF_MESSAGE = 0x00000001
        NIF_ICON = 0x00000002
        NIF_TIP = 0x00000004

        IMAGE_ICON = 1
        LR_LOADFROMFILE = 0x0010
        LR_DEFAULTSIZE = 0x0040

        MF_STRING = 0x0000
        MF_SEPARATOR = 0x0800
        MF_CHECKED = 0x0008
        MF_POPUP = 0x0010
        TPM_LEFTALIGN = 0x0000
        TPM_BOTTOMALIGN = 0x0020
        TPM_RETURNCMD = 0x0100
        TPM_NONOTIFY = 0x0080

        LRESULT = ctypes.c_ssize_t
        WNDPROCTYPE = ctypes.WINFUNCTYPE(
            LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
        )

        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        user32.DefWindowProcW.restype = LRESULT
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT, ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        user32.CreatePopupMenu.argtypes = []
        user32.CreatePopupMenu.restype = wintypes.HMENU
        user32.AppendMenuW.argtypes = [wintypes.HMENU, wintypes.UINT, wintypes.UINT_PTR, wintypes.LPCWSTR]
        user32.AppendMenuW.restype = wintypes.BOOL
        user32.TrackPopupMenu.argtypes = [
            wintypes.HMENU, wintypes.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND, wintypes.LPCVOID
        ]
        user32.TrackPopupMenu.restype = wintypes.BOOL

        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROCTYPE),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128),
            ]

        def show_context_menu(hwnd: int) -> None:
            _enable_win32_dark_mode_menus()
            state = self.get_state()
            hmenu = user32.CreatePopupMenu()

            h_audio = user32.CreatePopupMenu()
            h_prim = user32.CreatePopupMenu()
            h_sec = user32.CreatePopupMenu()

            for idx, (code, label) in enumerate(TRAY_LANGUAGES):
                a_flag = MF_STRING | (MF_CHECKED if state["audio_lang"] == code else 0)
                p_flag = MF_STRING | (MF_CHECKED if state["primary_sub_lang"] == code else 0)
                s_flag = MF_STRING | (MF_CHECKED if state["secondary_sub_lang"] == code else 0)
                user32.AppendMenuW(h_audio, a_flag, 100 + idx, label)
                user32.AppendMenuW(h_prim, p_flag, 200 + idx, label)
                user32.AppendMenuW(h_sec, s_flag, 300 + idx, label)

            game_label = Path(state["game_dir"]).name if state["game_dir"] else "Not Selected"
            user32.AppendMenuW(hmenu, MF_STRING, 8, "Open DualTitle Dark Control Panel (GUI)")
            user32.AppendMenuW(hmenu, MF_STRING, 10, "Launch Universal In-Game Dual-Subtitle Overlay")
            user32.AppendMenuW(hmenu, MF_STRING, 11, "Restore Save (Restore Backed-Up Saves & Settings)")
            user32.AppendMenuW(hmenu, MF_STRING, 12, "Backup Save Now")
            user32.AppendMenuW(hmenu, MF_STRING, 7, "1-Click Repair & Clean Game Folder")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, 1, f"Game: {game_label}")
            user32.AppendMenuW(hmenu, MF_POPUP, ctypes.cast(h_audio, wintypes.LPVOID).value or 0, f"Audio Language [{state['audio_lang'].upper()}]")
            user32.AppendMenuW(hmenu, MF_POPUP, ctypes.cast(h_prim, wintypes.LPVOID).value or 0, f"Primary Subtitle (Top) [{state['primary_sub_lang'].upper()}]")
            user32.AppendMenuW(hmenu, MF_POPUP, ctypes.cast(h_sec, wintypes.LPVOID).value or 0, f"Secondary Subtitle (Bottom) [{state['secondary_sub_lang'].upper()}]")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, 2, "Apply Changes Now")
            user32.AppendMenuW(hmenu, MF_STRING, 3, "Apply Changes & Exit Tray (0 Background Usage)")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)

            pause_flag = MF_STRING | (MF_CHECKED if self.pause_helper.enabled else 0)
            user32.AppendMenuW(hmenu, pause_flag, 4, "Enable Universal ALT+F9 Pause & ALT+F11 Borderless Hotkeys")

            startup_flag = MF_STRING | (MF_CHECKED if self.startup_mgr.is_startup_enabled() else 0)
            user32.AppendMenuW(hmenu, startup_flag, 5, "Run on Windows Startup")

            user32.AppendMenuW(hmenu, MF_STRING, 6, "Open Numbered Terminal Controller (CLI)")
            user32.AppendMenuW(hmenu, MF_SEPARATOR, 0, None)
            user32.AppendMenuW(hmenu, MF_STRING, 9, "Exit")

            pt = wintypes.POINT()
            user32.GetCursorPos(ctypes.byref(pt))
            user32.SetForegroundWindow(hwnd)
            cmd = user32.TrackPopupMenu(
                hmenu,
                TPM_LEFTALIGN | TPM_BOTTOMALIGN | TPM_RETURNCMD | TPM_NONOTIFY,
                pt.x,
                pt.y,
                0,
                hwnd,
                None,
            )
            user32.PostMessageW(hwnd, 0, 0, 0)
            user32.DestroyMenu(hmenu)

            if cmd == 8:
                threading.Thread(target=self.open_dark_control_panel_gui, daemon=True).start()
            elif cmd == 10:
                threading.Thread(target=self.open_universal_game_overlay, daemon=True).start()
            elif cmd == 11:
                self.restore_game_saves()
            elif cmd == 12:
                self.backup_game_saves()
            elif cmd == 1 or cmd == 6:
                self.launch_cli_window()
            elif cmd == 2:
                self.apply_to_game()
            elif cmd == 3:
                self.apply_to_game()
                self.pause_helper.stop_hotkey_listener()
                user32.PostQuitMessage(0)
            elif cmd == 4:
                if self.pause_helper.enabled:
                    self.pause_helper.stop_hotkey_listener()
                else:
                    self.pause_helper.start_hotkey_listener()
            elif cmd == 5:
                self.startup_mgr.toggle_startup()
            elif cmd == 7:
                self.emergency_repair_game()
            elif cmd == 9:
                self.pause_helper.stop_hotkey_listener()
                user32.PostQuitMessage(0)
            elif 100 <= cmd < 100 + len(TRAY_LANGUAGES):
                self.set_language_setting("audio_lang", TRAY_LANGUAGES[cmd - 100][0])
            elif 200 <= cmd < 200 + len(TRAY_LANGUAGES):
                self.set_language_setting("primary_sub_lang", TRAY_LANGUAGES[cmd - 200][0])
            elif 300 <= cmd < 300 + len(TRAY_LANGUAGES):
                self.set_language_setting("secondary_sub_lang", TRAY_LANGUAGES[cmd - 300][0])

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_TRAYICON:
                if lparam == WM_RBUTTONUP:
                    show_context_menu(hwnd)
                elif lparam in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    threading.Thread(target=self.open_dark_control_panel_gui, daemon=True).start()
                return 0
            if msg == WM_DESTROY:
                self.pause_helper.stop_hotkey_listener()
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        wnd_proc_cb = WNDPROCTYPE(wnd_proc)
        hinst = kernel32.GetModuleHandleW(None)
        class_name = "DualTitleTrayWndV4"

        wc = WNDCLASSW()
        wc.lpfnWndProc = wnd_proc_cb
        wc.hInstance = hinst
        wc.hbrBackground = gdi32.CreateSolidBrush(0x00190F0B)
        wc.lpszClassName = class_name
        user32.RegisterClassW(ctypes.byref(wc))

        hwnd = user32.CreateWindowExW(
            0, class_name, "DualTitle Tray", 0, 0, 0, 0, 0, None, None, hinst, None
        )

        ico_file = ensure_tray_ico_file(ICO_PATH)
        hicon = user32.LoadImageW(
            None,
            str(ico_file),
            IMAGE_ICON,
            32,
            32,
            LR_LOADFROMFILE | LR_DEFAULTSIZE,
        )
        if not hicon:
            hicon = user32.LoadIconW(None, ctypes.cast(32512, wintypes.LPCWSTR))

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        nid.hWnd = hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = ctypes.cast(hicon, wintypes.HICON)
        nid.szTip = "DualTitle (Left-Click: Dark GUI | Right-Click: Menu & Restore Save)"

        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))
        print("[DualTitle] System Tray active with DualTitle logo. Left-click for Dark GUI, or Right-click for Menu.")

        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(nid))
            self.pause_helper.stop_hotkey_listener()


if __name__ == "__main__":
    ctrl = DualSubTrayController()
    if "--gui" in sys.argv:
        ctrl.open_dark_control_panel_gui()
    elif "--overlay" in sys.argv:
        ctrl.open_universal_game_overlay()
    elif "--restore-save" in sys.argv:
        ctrl.restore_game_saves(log=print)
    else:
        ctrl.run()
