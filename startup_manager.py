#!/usr/bin/env python3
"""
Universal DualSub - Windows Startup & Fast Boot-Time Config Sync Manager
Manages the optional "Run on Windows Startup" setting via the Windows Registry
(HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run) and provides a zero-overhead
startup config verification mode that exits in <1 second so nothing runs 24/7 in RAM.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from config_patcher import GameConfigPatcher

HERE = Path(__file__).parent.resolve()
SETTINGS_FILE = HERE / "dualsub-settings.json"
REG_RUN_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE_NAME = "UniversalDualSub"


def load_settings() -> Dict[str, Any]:
    """Load persistent user settings from dualsub-settings.json."""
    defaults: Dict[str, Any] = {
        "game_dir": "",
        "audio_lang": "en",
        "primary_sub_lang": "en",
        "secondary_sub_lang": "de",
        "static_mode": True,
        "run_on_startup": False,
        "startup_mode": "config_sync_only",  # "config_sync_only" (exits in <1s) or "tray_resident"
        "profiles": {},
    }
    if SETTINGS_FILE.is_file():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                defaults.update(data)
        except (OSError, ValueError):
            pass
    return defaults


def save_settings(settings: Dict[str, Any]) -> bool:
    """Save persistent user settings to dualsub-settings.json."""
    try:
        SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except OSError:
        return False


class StartupManager:
    """
    Controls optional Windows Startup registration.
    Off by default — only enabled when the user explicitly toggles it on in the
    Terminal CLI or Windows System Tray menu.
    """

    def __init__(self, script_path: Optional[Path] = None):
        self.script_path = (script_path or (HERE / "universal_dualsub.py")).resolve()

    def build_startup_command(self, mode: str = "config_sync_only") -> str:
        """
        Build the command line written to HKCU\\...\\Run.
        - 'config_sync_only': runs `--startup-check` at login, verifies the game's
          static dual-subtitle and audio config, and immediately exits (0 background usage).
        - 'tray_resident': launches the lightweight Windows System Tray mini-app.
        """
        python_exe = Path(sys.executable)
        if os.name == "nt" and python_exe.name.lower() == "python.exe":
            pythonw = python_exe.with_name("pythonw.exe")
            if pythonw.is_file():
                python_exe = pythonw

        flag = "--startup-check" if mode == "config_sync_only" else "--tray"
        return f'"{python_exe}" "{self.script_path}" {flag}'

    def is_startup_enabled(self) -> bool:
        """Check whether Universal DualSub is registered to run on Windows Startup."""
        if os.name == "nt":
            try:
                import winreg  # type: ignore
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, REG_RUN_PATH, 0, winreg.KEY_READ
                ) as key:
                    val, _ = winreg.QueryValueEx(key, REG_VALUE_NAME)
                    return bool(val)
            except FileNotFoundError:
                return False
            except OSError:
                pass

        settings = load_settings()
        return bool(settings.get("run_on_startup", False))

    def set_startup_enabled(self, enabled: bool, mode: str = "config_sync_only") -> Tuple[bool, str]:
        """
        Enable or disable Windows Startup registration.
        Returns (success, status_message).
        """
        settings = load_settings()
        settings["run_on_startup"] = bool(enabled)
        settings["startup_mode"] = mode
        save_settings(settings)

        if os.name == "nt":
            try:
                import winreg  # type: ignore
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, REG_RUN_PATH, 0, winreg.KEY_SET_VALUE
                ) as key:
                    if enabled:
                        cmd = self.build_startup_command(mode)
                        winreg.SetValueEx(key, REG_VALUE_NAME, 0, winreg.REG_SZ, cmd)
                        return True, f"Enabled Windows Startup ({mode}): {cmd}"
                    else:
                        try:
                            winreg.DeleteValue(key, REG_VALUE_NAME)
                        except FileNotFoundError:
                            pass
                        return True, "Disabled Windows Startup (Registry entry removed)."
            except OSError as exc:
                return False, f"Could not update Windows Registry startup key: {exc}"

        state_str = f"ON ({mode})" if enabled else "OFF"
        return True, f"Startup preference saved to dualsub-settings.json: {state_str}"

    def toggle_startup(self) -> Tuple[bool, bool, str]:
        """Toggle the current startup state and return (new_state, success, message)."""
        current = self.is_startup_enabled()
        new_state = not current
        settings = load_settings()
        mode = settings.get("startup_mode", "config_sync_only")
        ok, msg = self.set_startup_enabled(new_state, mode=mode)
        return new_state, ok, msg

    def run_startup_config_sync(self, log=print) -> bool:
        """
        Fast boot-time verification (`--startup-check`):
        Checks the saved game folder and ensures its config files (`upc_r2.ini`,
        `GameUserSettings.ini`, etc.) still have the user's chosen Audio Language
        and DualSub Subtitle Language applied, then exits immediately so nothing
        stays running in the background 24/7.
        """
        settings = load_settings()
        game_dir_str = settings.get("game_dir", "")
        if not game_dir_str:
            log("[StartupSync] No active game directory saved; exiting immediately.")
            return False

        game_dir = Path(game_dir_str)
        if not game_dir.is_dir():
            log(f"[StartupSync] Saved game folder not found ({game_dir}); exiting.")
            return False

        audio_lang = settings.get("audio_lang", "en")
        primary_lang = settings.get("primary_sub_lang", "en")
        secondary_lang = settings.get("secondary_sub_lang", "de")

        patcher = GameConfigPatcher(game_dir)
        current = patcher.detect_current_settings()
        if current.get("subtitle_lang") != primary_lang or (
            audio_lang != "keep" and current.get("audio_lang") != audio_lang
        ):
            log(
                f"[StartupSync] Re-syncing game config for {game_dir.name} "
                f"(Audio={audio_lang}, Top={primary_lang}, Bottom={secondary_lang})..."
            )
            patcher.apply_audio_and_subtitle_config(
                primary_sub_lang=primary_lang,
                secondary_sub_lang=secondary_lang,
                audio_lang=audio_lang,
                log=log,
            )
        else:
            log(f"[StartupSync] Game config for {game_dir.name} is already in sync. Exiting (0 background usage).")
        return True
