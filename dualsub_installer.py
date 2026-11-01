#!/usr/bin/env python3
"""
DualTitle Universal Installer & Archive/Config Manager
Supports:
  • Frostbite Engine (`Data/Win32/Loc/*.sb` & `*.toc`, `PROF_SAVE_profile`, `user.cfg`)
  • Unreal Engine 4 & 5 (`.locres` v1/v2/v3, `.pak` v11, IoStore `.utoc`/`.ucas`, `GameUserSettings.ini`)
  • FORGE v27 & v50 Archives (`DataPC.forge`, `DataPC_boot.forge`, `steam_api.ini`, `upc_r2.ini`)
  • Unity, Source, & Generic Applications (`.srt`, `.vtt`, `.ass`, `.ssa`, `.json`, `.csv`)
  • Automatic Save Backup & 1-Click Save Restore (`SaveBackupManager`)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import struct
import sys
from pathlib import Path

from config_patcher import GameConfigPatcher, SaveBackupManager, LANGUAGE_NAMES, CULTURES, find_unreal_subprojects
from subtitle_engine import (
    MAGIC,
    FORGE_JOURNAL as JOURNAL,
    FORGE_ARCHIVES as ARCHIVES,
    ForgeError,
    ForgeBundle as Bundle,
    read_toc_ex,
    read_toc,
    append_entries,
    restore_entries,
    find_forge_bundles,
    patch_forge_game,
    unpatch_forge_game,
)

HERE = Path(__file__).parent.resolve()
SETTINGS = HERE / "dualsub-settings.json"


def looks_like_game_dir(path) -> bool:
    if not path:
        return False
    p = Path(path)
    if not p.is_dir():
        return False
    if (p / "universal_dualsub.py").is_file() and not any((p / s).is_file() for s in ARCHIVES):
        return False
    return (
        any((p / s).exists() for s in ARCHIVES)
        or (p / "Data" / "Win32" / "Loc").is_dir()
        or (p / "Engine").is_dir()
        or bool(find_unreal_subprojects(p))
        or any(p.glob("*.exe"))
    )


def find_game_dir():
    """Find installed applications across saved settings, drives C:-Z:, Steam, EA/Origin, Epic, and Ubisoft."""
    if SETTINGS.is_file():
        try:
            saved = json.loads(SETTINGS.read_text(encoding="utf-8")).get("game_dir")
            if looks_like_game_dir(saved):
                return Path(saved)
        except (OSError, ValueError):
            pass

    for candidate in (HERE, HERE.parent, HERE.parent.parent):
        if looks_like_game_dir(candidate):
            return candidate

    try:
        from universal_dualsub import scan_installed_games
        scanned = scan_installed_games()
        if scanned:
            return scanned[0][1]
    except Exception:
        pass

    return None


def save_game_dir(game_dir):
    try:
        data = {}
        if SETTINGS.is_file():
            try:
                data = json.loads(SETTINGS.read_text(encoding="utf-8"))
            except ValueError:
                data = {}
        data["game_dir"] = str(game_dir)
        SETTINGS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def detect_game_language(game_dir):
    if not game_dir:
        return None
    patcher = GameConfigPatcher(game_dir)
    return patcher.detect_current_settings().get("subtitle_lang")


def find_bundles():
    return find_forge_bundles(HERE)


def read_journal(game_dir):
    p = Path(game_dir) / JOURNAL
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def install_pair(game_dir, bundle, second, audio_lang=None):
    """Back up saves, install a DualTitle language pair, and update audio/subtitle config."""
    SaveBackupManager(game_dir).backup_saves(log=print)
    patcher = GameConfigPatcher(game_dir)
    patcher.apply_audio_and_subtitle_config(
        primary_sub_lang=bundle.primary,
        secondary_sub_lang=second,
        audio_lang=audio_lang or bundle.primary,
        log=print,
    )
    ok = patch_forge_game(game_dir, bundle.primary, second, bundles_root=HERE, log=print)
    return ok


def uninstall(game_dir):
    """Restore original archives, config files, and backed-up saves."""
    unpatch_forge_game(game_dir, log=print)
    GameConfigPatcher(game_dir).restore_game_configs(log=print)
    SaveBackupManager(game_dir).restore_saves(log=print)
    return True


def main():
    from universal_dualsub import main_menu
    detected = find_game_dir()
    return main_menu(initial_game_path=str(detected) if detected else None)


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    sys.exit(main())
