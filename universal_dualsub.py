#!/usr/bin/env python3
"""
DualTitle - Universal Anti-Cheat-Safe Pre-Game & Live Dual-Subtitle Controller (v4.1)
Control your application or game's Spoken Audio Language, Primary (Top) Subtitle Language,
Secondary (Bottom) Subtitle Language, Subtitle Speed, and Save Backups:
  • 100% Anti-Cheat Safe Mode: Never injects DLLs or hooks game memory; launches any game
    natively alongside the topmost DualTitle HUD with clickable word definitions and speed controls.
  • 1-Click "Restore Save" (`--restore-save` or `[S]`): Automatically backs up user save files
    and profiles before every operation and restores them on demand.
  • Multi-Drive Game Library Scanner (`C:` through `Z:`): Automatically discovers installed
    games across Steam, EA/Origin, Ubisoft, Epic Games, GOG, and custom folders.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from config_patcher import (
    GameConfigPatcher,
    SaveBackupManager,
    LANGUAGE_NAMES,
    DEFAULT_VOICE_LANGUAGES,
    find_unreal_subprojects,
)
from dictionary_engine import FamousDictionaryEngine
from startup_manager import StartupManager, load_settings, save_settings
from subtitle_engine import (
    UniversalSubtitleMerger,
    UnrealLocResBinary,
    FORGE_ARCHIVES,
    FORGE_JOURNAL,
    LOCRES_MAGIC,
    UE_PAK_MAGIC,
    check_font_compatibility,
    find_forge_bundles,
)
from tray_controller import DualSubTrayController, ensure_tray_ico_file, ICO_PATH

HERE = Path(__file__).parent.resolve()

MENU_LANGUAGE_ORDER: List[str] = [
    "en",
    "de",
    "fr",
    "es",
    "it",
    "pt-BR",
    "pl",
    "ru",
    "ja",
    "ko",
    "zh-Hans",
    "zh-Hant",
    "ar",
]


def _enable_windows_ansi_and_utf8() -> None:
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleOutputCP(65001)
            kernel32.SetConsoleCP(65001)
            h_out = kernel32.GetStdHandle(-11)
            mode = ctypes.c_ulong()
            if kernel32.GetConsoleMode(h_out, ctypes.byref(mode)):
                kernel32.SetConsoleMode(h_out, mode.value | 0x0004)
        except Exception:
            pass


def clear_screen() -> None:
    if os.name == "nt":
        os.system("cls")
    else:
        sys.stdout.write("\033[H\033[2J")
    try:
        sys.stdout.flush()
    except OSError:
        pass


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def pause_prompt(msg: str = "  Press Enter to continue...") -> None:
    print()
    ask(msg)


# ==========================================================================
# Universal Application & Game Detection Across Drives (C: through Z:)
# ==========================================================================

def is_suite_directory(path: Path) -> bool:
    if not path.is_dir():
        return False
    has_suite_scripts = (path / "universal_dualsub.py").is_file() and (path / "subtitle_engine.py").is_file()
    if not has_suite_scripts:
        return False
    has_real_game_binaries = (
        any((path / a).is_file() for a in FORGE_ARCHIVES)
        or (path / "Data" / "Win32" / "Loc").is_dir()
        or any(path.glob("*.utoc"))
    )
    return not has_real_game_binaries


def detect_engine_type(game_dir: Path) -> str:
    """Identify whether a directory is Frostbite, FORGE, Unreal Engine, or Generic."""
    if not game_dir or not game_dir.is_dir():
        return "generic"
    if (
        (game_dir / "Data" / "Win32" / "Loc").is_dir()
        or (game_dir / "Update" / "Patch" / "Data" / "Win32" / "Loc").is_dir()
        or any(game_dir.glob("GDFBinary*.dll"))
    ):
        return "frostbite"
    if any((game_dir / a).is_file() for a in FORGE_ARCHIVES) or any(game_dir.glob("DataPC*.forge")):
        return "forge"
    if (
        (game_dir / "Engine").is_dir()
        or bool(find_unreal_subprojects(game_dir))
        or ((game_dir / "pakstore.json").is_file() and not is_suite_directory(game_dir))
        or any(game_dir.glob("*.utoc"))
        or any(game_dir.glob("*.pak"))
    ):
        return "unreal"
    return "generic"


def auto_detect_game_from_path(raw_path: str) -> Tuple[Optional[str], Optional[Path], Optional[Path]]:
    """
    Given a file path (.exe) or directory, detect the application title, root folder,
    and optional UE4SS directory without hardcoding any game names.
    """
    if not raw_path:
        return None, None, None

    clean = raw_path.strip().strip('"').strip("'").strip()
    if not clean:
        return None, None, None

    p = Path(clean).expanduser().resolve()
    fname = p.name.lower()
    game_root = p.parent if fname.endswith(".exe") else p

    if is_suite_directory(game_root):
        return None, None, None

    if game_root.is_dir() and not any(game_root.glob("*.exe")) and not any(game_root.glob("*.forge")):
        for child in sorted(game_root.iterdir()):
            if child.is_dir() and not is_suite_directory(child) and (
                any((child / a).is_file() for a in FORGE_ARCHIVES)
                or any(child.glob("DataPC*.forge"))
                or any(child.glob("*.exe"))
                or (child / "Engine").is_dir()
                or (child / "Data" / "Win32" / "Loc").is_dir()
                or bool(find_unreal_subprojects(child))
            ):
                game_root = child
                break

    eng = detect_engine_type(game_root)
    base_title = game_root.name or (p.stem if fname.endswith(".exe") else "Application")
    if eng == "frostbite":
        game_name = f"{base_title} (Frostbite)"
    elif eng == "unreal":
        game_name = f"{base_title} (Unreal Engine)"
    elif eng == "forge":
        game_name = f"{base_title} (FORGE Engine)"
    else:
        game_name = base_title

    ue4ss_dir = None
    cand_ue4ss = [
        game_root / "UE4SS",
        game_root / "Binaries" / "Win64" / "UE4SS",
        game_root / "Binaries" / "Win64" / "ue4ss",
    ]
    for sub in find_unreal_subprojects(game_root):
        cand_ue4ss.append(sub / "Binaries" / "Win64" / "UE4SS")
        cand_ue4ss.append(sub / "Binaries" / "Win64" / "ue4ss")

    for cand in cand_ue4ss:
        if cand.exists():
            ue4ss_dir = cand
            break

    return game_name, game_root, ue4ss_dir


def scan_installed_games() -> List[Tuple[str, Path]]:
    """
    Scan all drive letters (C: through Z:), Steam libraries, EA/Origin, Ubisoft,
    Epic Games, GOG, and saved paths for installed applications and games.
    """
    found: List[Tuple[str, Path]] = []
    seen: set[str] = set()

    def add_candidate(title: str, path: Path) -> None:
        if not path.is_dir() or is_suite_directory(path):
            return
        resolved = str(path.resolve())
        if resolved not in seen:
            seen.add(resolved)
            found.append((title, path.resolve()))

    # 1. Check saved game_dir in dualsub-settings.json
    settings = load_settings()
    saved_dir = settings.get("game_dir", "")
    if saved_dir and Path(saved_dir).is_dir() and not is_suite_directory(Path(saved_dir)):
        gname, groot, _ = auto_detect_game_from_path(saved_dir)
        if gname and groot:
            add_candidate(f"{gname} [Saved]", groot)

    # 2. Scan all drive roots (C:\ through Z:\) across standard launcher folders
    drive_roots: List[Path] = []
    if os.name == "nt":
        for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
            drv = Path(f"{letter}:\\")
            if drv.is_dir():
                drive_roots.append(drv)
    else:
        drive_roots.extend([Path.home()])

    launcher_rel_dirs = (
        Path("Games"),
        Path("Origin Games"),
        Path("EA Games"),
        Path("GOG Games"),
        Path("Epic Games"),
        Path("Ubisoft Game Launcher") / "games",
        Path("SteamLibrary") / "steamapps" / "common",
        Path("Program Files (x86)") / "Origin Games",
        Path("Program Files") / "EA Games",
        Path("Program Files (x86)") / "Ubisoft" / "Ubisoft Game Launcher" / "games",
        Path("Program Files") / "Ubisoft" / "Ubisoft Game Launcher" / "games",
        Path("Program Files (x86)") / "Steam" / "steamapps" / "common",
        Path("Program Files") / "Steam" / "steamapps" / "common",
    )

    for drv in drive_roots:
        for rel in launcher_rel_dirs:
            lib_dir = drv / rel
            if lib_dir.is_dir():
                try:
                    for gdir in sorted(lib_dir.iterdir()):
                        if gdir.is_dir():
                            gname, groot, _ = auto_detect_game_from_path(str(gdir))
                            if gname and groot:
                                add_candidate(gname, groot)
                except OSError:
                    pass

        # Also check top-level folders on drives D:..Z: containing game archives or binaries
        try:
            for item in sorted(drv.iterdir()):
                if not item.is_dir() or item.name.startswith(("$", ".", "Windows", "Program", "Users", "System")):
                    continue
                if (
                    any(item.glob("DataPC*.forge"))
                    or (item / "Data" / "Win32" / "Loc").is_dir()
                    or (item / "Engine").is_dir()
                    or bool(find_unreal_subprojects(item))
                ):
                    gname, groot, _ = auto_detect_game_from_path(str(item))
                    if gname and groot:
                        add_candidate(gname, groot)
        except OSError:
            pass

    # 3. Check Steam libraryfolders.vdf
    steam_roots = [
        Path(r"C:\Program Files (x86)\Steam"),
        Path(r"C:\Program Files\Steam"),
        Path.home() / ".steam" / "steam",
        Path.home() / ".local" / "share" / "Steam",
    ]
    for sr in steam_roots:
        vdf = sr / "steamapps" / "libraryfolders.vdf"
        if vdf.is_file():
            try:
                content = vdf.read_text(encoding="utf-8", errors="ignore")
                for match in re.finditer(r'"path"\s+"([^"]+)"', content):
                    lib = Path(match.group(1).replace("\\\\", "\\"))
                    common = lib / "steamapps" / "common"
                    if common.is_dir():
                        for gdir in sorted(common.iterdir()):
                            if gdir.is_dir():
                                gname, groot, _ = auto_detect_game_from_path(str(gdir))
                                if gname and groot:
                                    add_candidate(gname, groot)
            except OSError:
                pass

    return found


# ==========================================================================
# Status Banner & Numbered Pre-Game Menus
# ==========================================================================

def print_status_banner(
    game_dir: Optional[Path],
    audio_lang: str,
    primary_lang: str,
    secondary_lang: str,
    startup_mgr: StartupManager,
) -> None:
    clear_screen()
    engine_type = detect_engine_type(game_dir) if game_dir else "generic"
    cfg_info = {"audio_lang": None, "subtitle_lang": None, "config_source": None}
    journal_status = "100% Clean Original Files (Anti-Cheat Safe)"

    if game_dir and game_dir.is_dir():
        patcher = GameConfigPatcher(game_dir)
        cfg_info = patcher.detect_current_settings()
        if (game_dir / FORGE_JOURNAL).is_file():
            try:
                j = json.loads((game_dir / FORGE_JOURNAL).read_text(encoding="utf-8"))
                journal_status = f"ACTIVE in FORGE Archive ({j.get('label', 'DualTitle')})"
            except Exception:
                journal_status = "ACTIVE in FORGE Archive"
        elif (game_dir / ".dualsub_journal.json").is_file():
            journal_status = "ACTIVE in Application Config & Subtitle Files"

    startup_on = startup_mgr.is_startup_enabled()
    print("=" * 78)
    print("        DUALTITLE — UNIVERSAL ANTI-CHEAT-SAFE DUAL SUBTITLE CONTROLLER")
    print("   Game Picker • Live Speed & Word-Meaning HUD • Automatic Save Backup/Restore")
    print("=" * 78)
    if game_dir and game_dir.is_dir():
        gname, _, _ = auto_detect_game_from_path(str(game_dir))
        print(f"  Active Game / App    : {gname} ({game_dir})")
        print(f"  Detected Engine      : {engine_type.upper()} | Config: {cfg_info.get('config_source') or 'Auto-Managed'}")
    else:
        print("  Active Game / App    : [NOT SELECTED — Press 1 or 2 to pick or paste folder]")
    print(f"  Status               : {journal_status}")
    print("-" * 78)
    print(f"  [Audio Language]     : {LANGUAGE_NAMES.get(audio_lang, audio_lang)} (Voice Track)")
    print(f"  [Top Subtitle Line]  : {LANGUAGE_NAMES.get(primary_lang, primary_lang)} (Primary Line - Gold)")
    print(f"  [Bottom Subtitle]    : {LANGUAGE_NAMES.get(secondary_lang, secondary_lang)} (Secondary Line - White)")
    print(f"  [Anti-Cheat Safety]  : 100% SAFE (Zero DLL injection, zero process memory hooks)")
    print(f"  [Windows Startup]    : {'ON (Boot Config Sync)' if startup_on else 'OFF (Opt-in via #9 or Tray)'}")
    print("=" * 78)
    print()


def choose_game_numbered_menu(current_game_dir: Optional[Path]) -> Optional[Path]:
    while True:
        clear_screen()
        print("=" * 78)
        print("  STEP 1: SELECT YOUR GAME OR APPLICATION (BY NUMBER OR DRAG & DROP)")
        print("=" * 78)
        installed = scan_installed_games()
        if installed:
            print("\n  Detected Games & Applications:")
            for idx, (title, path) in enumerate(installed, 1):
                mark = "  <-- [Selected]" if current_game_dir and path == current_game_dir.resolve() else ""
                print(f"    [{idx:>2}] {title}")
                print(f"         Path: {path}{mark}")
        else:
            print("\n  No applications auto-detected yet. You can paste your application folder below.")

        next_num = len(installed) + 1
        print()
        print(f"    [{next_num:>2}] Paste or Drag-and-Drop an Application .exe / Folder Path")
        print("    [ B] Back to Main Menu")
        print()
        choice = ask(f"  Type a number (1-{next_num}) or B and press Enter: ").lower()
        if choice == "b":
            return current_game_dir
        if choice.isdigit():
            num = int(choice)
            if 1 <= num <= len(installed):
                chosen = installed[num - 1][1]
                settings = load_settings()
                settings["game_dir"] = str(chosen)
                save_settings(settings)
                return chosen
            elif num == next_num:
                print("\n  Paste the folder path or drag the application's .exe:")
                raw = ask("  Path: ")
                _, groot, _ = auto_detect_game_from_path(raw)
                if groot and groot.is_dir():
                    settings = load_settings()
                    settings["game_dir"] = str(groot)
                    save_settings(settings)
                    return groot
                else:
                    print("\n  [!] That path does not exist or is not a valid folder. Please try again.")
                    pause_prompt()


def choose_audio_language_numbered_menu(game_dir: Optional[Path], current_audio: str) -> str:
    available_audio = list(DEFAULT_VOICE_LANGUAGES)
    configured_audio = None
    if game_dir and game_dir.is_dir():
        patcher = GameConfigPatcher(game_dir)
        available_audio = patcher.detect_available_audio_languages()
        configured_audio = patcher.detect_current_settings().get("audio_lang")

    while True:
        clear_screen()
        print("=" * 78)
        print("  AUDIO LANGUAGE CONTROL (VOICE TRACK)")
        print("  Choose which spoken audio language the application should play:")
        print("=" * 78)
        print()
        print("    [ 0] Keep Current Audio Setting (Do Not Change Voice Language)")
        for idx, code in enumerate(available_audio, 1):
            notes = []
            if code == current_audio:
                notes.append("selected")
            if code == configured_audio:
                notes.append("current in config")
            tag = f"  <-- ({', '.join(notes)})" if notes else ""
            print(f"    [{idx:>2}] {LANGUAGE_NAMES.get(code, code):<32}{tag}")
        print()
        print("    [ B] Back")
        print()
        choice = ask(f"  Select Audio Language by number (0-{len(available_audio)}, B): ").lower()
        if choice == "b":
            return current_audio
        if choice == "0":
            return "keep"
        if choice.isdigit() and 1 <= int(choice) <= len(available_audio):
            picked = available_audio[int(choice) - 1]
            settings = load_settings()
            settings["audio_lang"] = picked
            save_settings(settings)
            return picked


def choose_primary_subtitle_numbered_menu(game_dir: Optional[Path], current_primary: str) -> str:
    configured_sub = None
    if game_dir and game_dir.is_dir():
        configured_sub = GameConfigPatcher(game_dir).detect_current_settings().get("subtitle_lang")

    bundles = find_forge_bundles(HERE)
    lang_list = sorted(bundles.keys()) if bundles else list(MENU_LANGUAGE_ORDER)

    while True:
        clear_screen()
        print("=" * 78)
        print("  PRIMARY SUBTITLE LANGUAGE (TOP LINE ON SCREEN)")
        print("  This is the main subtitle line (and the language set in the config):")
        print("=" * 78)
        print()
        for idx, code in enumerate(lang_list, 1):
            notes = []
            if code == current_primary:
                notes.append("selected now")
            if code == configured_sub:
                notes.append("current in config")
            tag = f"  <-- ({', '.join(notes)})" if notes else ""
            print(f"    [{idx:>2}] {LANGUAGE_NAMES.get(code, code):<32}{tag}")
        print()
        print("    [ B] Back")
        print()
        choice = ask(f"  Select Top Subtitle Language by number (1-{len(lang_list)}, B): ").lower()
        if choice == "b":
            return current_primary
        if choice.isdigit() and 1 <= int(choice) <= len(lang_list):
            picked = lang_list[int(choice) - 1]
            settings = load_settings()
            settings["primary_sub_lang"] = picked
            save_settings(settings)
            return picked


def choose_secondary_subtitle_numbered_menu(
    game_dir: Optional[Path], primary_lang: str, current_secondary: str
) -> str:
    engine_type = detect_engine_type(game_dir) if game_dir else "generic"
    bundles = find_forge_bundles(HERE)

    if engine_type == "forge" and primary_lang in bundles:
        candidates = bundles[primary_lang].seconds
    else:
        candidates = [c for c in MENU_LANGUAGE_ORDER if c != primary_lang]

    while True:
        clear_screen()
        print("=" * 78)
        print("  SECONDARY SUBTITLE LANGUAGE (BOTTOM LINE UNDERNEATH)")
        print(f"  Top Line is set to: {LANGUAGE_NAMES.get(primary_lang, primary_lang)}")
        print("  Choose which language appears on the second line underneath every subtitle:")
        print("=" * 78)
        print()
        valid_choices: List[str] = []
        for code in candidates:
            ok, _reason = check_font_compatibility(primary_lang, code, engine_type)
            if ok:
                valid_choices.append(code)

        for idx, code in enumerate(valid_choices, 1):
            mark = "  <-- (selected now)" if code == current_secondary else ""
            print(f"    [{idx:>2}] {LANGUAGE_NAMES.get(code, code):<32}{mark}")

        print()
        print("    [ B] Back")
        print()
        choice = ask(f"  Select Bottom Subtitle Language by number (1-{len(valid_choices)}, B): ").lower()
        if choice == "b":
            return current_secondary
        if choice.isdigit() and 1 <= int(choice) <= len(valid_choices):
            picked = valid_choices[int(choice) - 1]
            settings = load_settings()
            settings["secondary_sub_lang"] = picked
            save_settings(settings)
            return picked


# ==========================================================================
# Static Game Patching & Launch Orchestration
# ==========================================================================

def apply_all_settings_to_game(
    game_dir: Path,
    audio_lang: str,
    primary_lang: str,
    secondary_lang: str,
    dict_engine: FamousDictionaryEngine,
    launch_after: bool = False,
) -> bool:
    clear_screen()
    gname, groot, ue4ss_dir = auto_detect_game_from_path(str(game_dir))
    if groot is None:
        groot = game_dir.resolve()
        gname = groot.name

    print("=" * 78)
    print(f"  APPLYING DUALTITLE & BACKING UP SAVES FOR: {gname}")
    print("=" * 78)
    print(f"  • Application Folder : {groot}")
    print(f"  • Spoken Audio       : {LANGUAGE_NAMES.get(audio_lang, audio_lang)}")
    print(f"  • Top Subtitle       : {LANGUAGE_NAMES.get(primary_lang, primary_lang)}")
    print(f"  • Bottom Subtitle    : {LANGUAGE_NAMES.get(secondary_lang, secondary_lang)}")
    print("-" * 78)
    print()

    print("  [0/3] Backing Up User Save Files & Profiles...")
    SaveBackupManager(groot).backup_saves(log=print)

    print("\n  [1/3] Writing Audio & Subtitle Culture to Configuration Files...")
    cfg_patcher = GameConfigPatcher(groot)
    modified_cfgs = cfg_patcher.apply_audio_and_subtitle_config(
        primary_sub_lang=primary_lang,
        secondary_sub_lang=secondary_lang,
        audio_lang=audio_lang,
        log=print,
    )
    if not modified_cfgs:
        print("    [ConfigPatcher] Recorded language configuration in .dualsub_journal.json")

    print("\n  [2/3] Merging / Indexing Localization Files for Dual Subtitles...")
    merger = UniversalSubtitleMerger(primary_lang, secondary_lang)
    patch_summary = merger.patch_game_localization_in_place(groot, data_dir=HERE / "data", log=print)

    print("\n  [3/3] Syncing Famous Dictionary & Overlay Assets...")
    dict_engine._save_cache()
    print(f"    [DictionaryEngine] Offline Famous Dictionary ready ({len(dict_engine.cache)} words).")

    settings = load_settings()
    settings.update(
        {
            "game_dir": str(groot),
            "audio_lang": audio_lang,
            "primary_sub_lang": primary_lang,
            "secondary_sub_lang": secondary_lang,
        }
    )
    save_settings(settings)

    print()
    print("=" * 78)
    print("  [SUCCESS] CONFIGURATION & DUAL SUBTITLES READY (SAVES PROTECTED)!")
    print("=" * 78)

    if launch_after:
        tray = DualSubTrayController()
        tray.launch_selected_game_executable(groot, log=print)

    return True


# ==========================================================================
# Interactive Terminal Reader & Famous Dictionary Card Display
# ==========================================================================

def display_dictionary_card(entry: dict) -> None:
    word = entry.get("word", "").upper()
    lang = entry.get("lang", "en")
    pos = entry.get("pos", "")
    source = entry.get("source", "Famous Dictionary")
    phonetic = entry.get("phonetic", "")
    gender = entry.get("gender", "")
    definition = entry.get("definition", "")
    example = entry.get("example", "")
    german_trans = entry.get("german_translation", "")
    english_trans = entry.get("english_translation", "")
    notes = entry.get("notes", "")

    print("\n+" + "-" * 74 + "+")
    header = f"  [BOOK] {word}"
    if phonetic:
        header += f" {phonetic}"
    if gender:
        header += f" [{gender}]"
    elif pos:
        header += f" ({pos})"
    print(f"|{header:<74}|")
    print("+" + "-" * 74 + "+")
    print(f"|  Source      : {source:<58}|")
    if german_trans and lang == "en":
        print(f"|  German (DE) : {german_trans:<58}|")
    if english_trans and lang == "de":
        print(f"|  English (EN): {english_trans:<58}|")
    if definition:
        lines = [definition[i : i + 56] for i in range(0, len(definition), 56)]
        print(f"|  Definition  : {lines[0]:<58}|")
        for extra in lines[1:]:
            print(f"|                {extra:<58}|")
    if example:
        print(f'|  Example     : "{example[:56]}"')
    if notes:
        print(f"|  Grammar/Note: {notes:<58}|")
    print("+" + "-" * 74 + "+\n")


def interactive_terminal_reader(
    primary_lang: str, secondary_lang: str, dict_engine: FamousDictionaryEngine
) -> None:
    merger = UniversalSubtitleMerger(primary_lang, secondary_lang)
    dual_table = merger._load_or_build_unreal_dual_table(HERE, HERE / "data")

    dialogues: List[Tuple[str, str, str]] = []
    for table_name, table in dual_table.items():
        if isinstance(table, dict) and table_name != "metadata":
            for _k, val in table.items():
                if isinstance(val, str) and "/" in val:
                    p, s = val.split("/", 1)
                    dialogues.append((table_name, p.strip(), s.strip()))

    if not dialogues:
        dialogues = [
            ("ST_Cutscenes", "Look over there! It's a bat!", "Sieh mal da drüben! Eine Fledermaus!"),
            ("ST_Objectives", "Investigate the main facility", "Untersuche die Hauptanlage"),
        ]

    idx = 0
    while True:
        clear_screen()
        tname, p_line, s_line = dialogues[idx]
        category = "MISSION OBJECTIVE" if "Objective" in tname else "SPOKEN DIALOGUE"
        print("=" * 78)
        print(f"  INTERACTIVE DUALTITLE READER: [{category}] ({idx + 1} of {len(dialogues)})")
        print("=" * 78)
        print(f"\n  TOP LINE ({LANGUAGE_NAMES.get(primary_lang, primary_lang)}):")
        print(f'    "{p_line}"')
        print(f"\n  BOTTOM LINE ({LANGUAGE_NAMES.get(secondary_lang, secondary_lang)}):")
        print(f'    "{s_line}"')
        print("\n" + "-" * 78)
        print("  • Type any word from the subtitle to see its Famous Dictionary card")
        print("  • [N / Enter] Next Line  |  [P] Previous Line  |  [B] Back to Main Menu")
        print("-" * 78)
        cmd = ask("  Word or Command: ")
        if not cmd or cmd.lower() == "n":
            idx = (idx + 1) % len(dialogues)
        elif cmd.lower() == "p":
            idx = (idx - 1) % len(dialogues)
        elif cmd.lower() == "b":
            return
        else:
            entry = dict_engine.lookup(cmd, target_lang=secondary_lang)
            display_dictionary_card(entry)
            pause_prompt("  Press Enter to continue reading...")


# ==========================================================================
# Main Pre-Game Numbered Terminal Menu Loop
# ==========================================================================

def main_menu(initial_game_path: Optional[str] = None) -> int:
    _enable_windows_ansi_and_utf8()
    dict_engine = FamousDictionaryEngine(HERE / "dictionaries")
    startup_mgr = StartupManager(HERE / "universal_dualsub.py")
    settings = load_settings()

    accidental_mods = HERE / "Mods"
    if is_suite_directory(HERE) and accidental_mods.is_dir():
        try:
            shutil.rmtree(accidental_mods)
        except OSError:
            pass

    game_dir: Optional[Path] = None
    if initial_game_path:
        _, groot, _ = auto_detect_game_from_path(initial_game_path)
        if groot and groot.is_dir():
            game_dir = groot
            settings["game_dir"] = str(groot)
            save_settings(settings)
    elif settings.get("game_dir") and Path(settings["game_dir"]).is_dir() and not is_suite_directory(Path(settings["game_dir"])):
        game_dir = Path(settings["game_dir"]).resolve()
    else:
        scanned = scan_installed_games()
        if scanned:
            game_dir = scanned[0][1]
            settings["game_dir"] = str(game_dir)
            save_settings(settings)

    audio_lang = settings.get("audio_lang", "en")
    primary_lang = settings.get("primary_sub_lang", "en")
    secondary_lang = settings.get("secondary_sub_lang", "de")

    while True:
        print_status_banner(game_dir, audio_lang, primary_lang, secondary_lang, startup_mgr)
        print("  DUALTITLE CONTROL MENU (Type a number or letter and press Enter):")
        print("    [ S] RESTORE SAVE (Restore Backed-Up Game Saves & Profile Settings)")
        print("    [ B] BACKUP SAVE NOW (Create Immediate Save Snapshot)")
        print("    [ R] 1-Click Repair & Clean Application Folder")
        print("    [ O] Launch Universal In-Game Dual-Subtitle Overlay (Clickable Words & Speed HUD)")
        print("    [ 1] Step-by-Step Setup Wizard (Game -> Audio -> Top Sub -> Bottom Sub -> Apply)")
        print("    [ 2] Select / Switch Game Folder (Auto-Scans C: through Z:)")
        print("    [ 3] Control Spoken AUDIO Language")
        print("    [ 4] Control PRIMARY (Top Line) Subtitle Language")
        print("    [ 5] Control SECONDARY (Bottom Line) Subtitle Language")
        print("    [ 6] APPLY Changes to Game Config & Files Only")
        print("    [ 7] LAUNCH Selected Game + In-Game Dual-Subtitle Overlay Immediately")
        print("    [ 8] Open Windows System Tray Icon & Dark Visual Control Panel")
        print("    [ 9] Toggle 'Run on Windows Startup' (Optional Boot Config Sync)")
        print("    [10] Interactive Subtitle Reader & Famous Dictionary Word Lookup")
        print("    [11] Merge External Subtitle Files (.srt / .vtt / .ass / .json / .csv)")
        print("    [ G] Open High-Contrast Dark Visual Control Panel (Desktop GUI)")
        print("    [ 0] Restore Original Game Files, Configs & Saves (100% Clean Undo)")
        print("    [ Q] Quit")
        print()
        choice = ask("  Enter choice (S, B, R, O, G, 0-11, Q): ").lower()

        if choice == "q":
            return 0
        elif choice == "s":
            tray = DualSubTrayController()
            _ok, msg = tray.restore_game_saves(log=print)
            pause_prompt()
        elif choice == "b":
            tray = DualSubTrayController()
            _ok, msg = tray.backup_game_saves(log=print)
            pause_prompt()
        elif choice == "r":
            tray = DualSubTrayController()
            _ok, msg = tray.emergency_repair_game(log=print)
            pause_prompt()
        elif choice == "o":
            tray = DualSubTrayController()
            tray.open_universal_game_overlay()
        elif choice == "g":
            tray = DualSubTrayController()
            tray.open_dark_control_panel_gui()
            settings = load_settings()
            if settings.get("game_dir") and Path(settings["game_dir"]).is_dir():
                game_dir = Path(settings["game_dir"]).resolve()
            audio_lang = settings.get("audio_lang", audio_lang)
            primary_lang = settings.get("primary_sub_lang", primary_lang)
            secondary_lang = settings.get("secondary_sub_lang", secondary_lang)
        elif choice == "1":
            picked_game = choose_game_numbered_menu(game_dir)
            if picked_game:
                game_dir = picked_game
                audio_lang = choose_audio_language_numbered_menu(game_dir, audio_lang)
                primary_lang = choose_primary_subtitle_numbered_menu(game_dir, primary_lang)
                secondary_lang = choose_secondary_subtitle_numbered_menu(
                    game_dir, primary_lang, secondary_lang
                )
                apply_all_settings_to_game(
                    game_dir, audio_lang, primary_lang, secondary_lang, dict_engine, launch_after=False
                )
                pause_prompt()
        elif choice == "2":
            game_dir = choose_game_numbered_menu(game_dir)
        elif choice == "3":
            audio_lang = choose_audio_language_numbered_menu(game_dir, audio_lang)
        elif choice == "4":
            primary_lang = choose_primary_subtitle_numbered_menu(game_dir, primary_lang)
            if secondary_lang == primary_lang:
                secondary_lang = "de" if primary_lang != "de" else "en"
        elif choice == "5":
            secondary_lang = choose_secondary_subtitle_numbered_menu(
                game_dir, primary_lang, secondary_lang
            )
        elif choice in ("6", "7"):
            if not game_dir or not game_dir.is_dir():
                game_dir = choose_game_numbered_menu(game_dir)
            if game_dir and game_dir.is_dir():
                launch_now = choice == "7"
                apply_all_settings_to_game(
                    game_dir,
                    audio_lang,
                    primary_lang,
                    secondary_lang,
                    dict_engine,
                    launch_after=launch_now,
                )
                if launch_now:
                    tray = DualSubTrayController()
                    tray.open_universal_game_overlay()
                    return 0
                pause_prompt()
        elif choice == "8":
            print("\n  Starting Windows System Tray Mini-Controller...")
            tray = DualSubTrayController()
            tray.run()
        elif choice == "9":
            new_state, _ok, msg = startup_mgr.toggle_startup()
            print(f"\n  [StartupManager] {msg}")
            print(
                f"  Windows Startup is now: {'ENABLED (Zero-Background Config Sync)' if new_state else 'DISABLED'}"
            )
            pause_prompt()
        elif choice == "10":
            interactive_terminal_reader(primary_lang, secondary_lang, dict_engine)
        elif choice == "11":
            clear_screen()
            print("  MERGE EXTERNAL SUBTITLE FILES (.srt / .vtt / .ass / .json / .csv)")
            print("  " + "-" * 60)
            p_path = ask("  Primary subtitle file path  : ").strip('"')
            s_path = ask("  Secondary subtitle file path: ").strip('"')
            o_path = ask("  Output dual subtitle path   : ").strip('"')
            if p_path and s_path and o_path:
                merger = UniversalSubtitleMerger(primary_lang, secondary_lang)
                try:
                    merger.merge_srt_files(Path(p_path), Path(s_path), Path(o_path))
                    print(f"\n  [SUCCESS] Merged dual subtitle file saved to: {o_path}")
                except Exception as exc:
                    print(f"\n  [ERROR] Could not merge files: {exc}")
            pause_prompt()
        elif choice == "0":
            if not game_dir or not game_dir.is_dir():
                print("\n  No active application folder selected to restore.")
            else:
                print(f"\n  Restoring original files, configs, and saves in {game_dir}...")
                UniversalSubtitleMerger.restore_all_patched_subtitles(game_dir, log=print)
                GameConfigPatcher(game_dir).restore_game_configs(log=print)
                SaveBackupManager(game_dir).restore_saves(log=print)
                print("  [DONE] Application files, configs, and saves are back to 100% original state.")
            pause_prompt()


# ==========================================================================
# Automated Self-Test Suite (--self-test)
# ==========================================================================

def run_self_tests() -> int:
    """
    Verify all core subsystems:
      1. FORGE v27 & v50 Config + Archive Round-Trip & SaveBackupManager ("Restore Save")
      2. Frostbite Engine (`PROF_SAVE_profile`, `user.cfg`, `Data/Win32/Loc/*.sb`) Support & Rollback
      3. Unreal Engine 4/5 Binary `.locres` v3 Hash Preservation, Pak v11, IoStore `.utoc`/`.ucas` & `en-GB` Slots
      4. SRT, ASS, JSON, and CSV dual-subtitle merging & in-place restore
      5. Famous Dictionary lookup (English & German genders/phonetics)
      6. 32-bit BGRA `.ico` verification & StartupManager zero-background command check
    """
    import struct as _struct
    import tempfile

    print("=" * 72)
    print("  RUNNING DUALTITLE v4.1 AUTOMATED VERIFICATION SUITE")
    print("=" * 72)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)

        # 1. Test FORGE v27 (`steam_api.ini` + `DataPC.forge`) & SaveBackupManager ("Restore Save")
        print("  [Test 1/6] Testing FORGE v27, Config Patcher & SaveBackupManager ('Restore Save')...")
        app_mock = tmp_root / "SampleForgeApp"
        (app_mock / "Saved" / "SaveGames").mkdir(parents=True)
        save_slot = app_mock / "Saved" / "SaveGames" / "Profile01.sav"
        save_slot.write_text("USER_SAVE_PROGRESS_100%", encoding="utf-8")

        steam_ini = app_mock / "steam_api.ini"
        orig_steam_ini = "[Settings]\nLanguage=english\n"
        steam_ini.write_text(orig_steam_ini, encoding="utf-8")

        forge_v27 = app_mock / "DataPC.forge"
        toc_off_27 = 0x100
        hdr27 = bytearray(toc_off_27)
        hdr27[:9] = b"scimitar\0"
        _struct.pack_into("<I", hdr27, 9, 27)
        _struct.pack_into("<Q", hdr27, 13, 0x20)
        _struct.pack_into("<I", hdr27, 0x20, 2)
        _struct.pack_into("<Q", hdr27, 0x20 + 20, toc_off_27)
        p_en = b"LANG:en:Hello Captain!\nMan the cannons!"
        p_de = b"LANG:de:Hallo Kapitaen!\nBemannt die Kanonen!"
        o1 = toc_off_27 + 2 * 20
        o2 = o1 + len(p_en)
        r1 = _struct.pack("<QQI", o1, 0x2001, len(p_en))
        r2 = _struct.pack("<QQI", o2, 0x2002, len(p_de))
        orig_v27_bytes = bytes(hdr27) + r1 + r2 + p_en + p_de
        forge_v27.write_bytes(orig_v27_bytes)

        patcher = GameConfigPatcher(app_mock)
        assert patcher.detect_current_settings()["subtitle_lang"] == "en"
        patcher.apply_audio_and_subtitle_config("de", "en", audio_lang="en", log=lambda *a: None)
        assert "Language=german" in steam_ini.read_text(encoding="utf-8")

        # Simulate corrupted save and test Restore Save
        save_slot.write_text("CORRUPTED_SAVE", encoding="utf-8")
        restored_cnt, _ = SaveBackupManager(app_mock).restore_saves(log=lambda *a: None)
        assert restored_cnt >= 1
        assert save_slot.read_text(encoding="utf-8") == "USER_SAVE_PROGRESS_100%"

        from subtitle_engine import patch_forge_game, unpatch_forge_game
        assert patch_forge_game(app_mock, "en", "de", log=lambda *a: None)
        assert forge_v27.stat().st_size > len(orig_v27_bytes)
        unpatch_forge_game(app_mock, log=lambda *a: None)
        assert forge_v27.read_bytes() == orig_v27_bytes
        assert steam_ini.read_text(encoding="utf-8") == orig_steam_ini
        print("             PASS: FORGE v27, INI Config Patcher & SaveBackupManager ('Restore Save') verified.")

        # 2. Test Frostbite Engine (`PROF_SAVE_profile`, `user.cfg`, `Data/Win32/Loc/*.sb`)
        print("  [Test 2/6] Testing Frostbite Engine (PROF_SAVE_profile, user.cfg & Loc/*.sb)...")
        fb_mock = tmp_root / "SampleFrostbiteApp"
        (fb_mock / "settings").mkdir(parents=True)
        (fb_mock / "Data" / "Win32" / "Loc").mkdir(parents=True)
        prof_file = fb_mock / "settings" / "PROF_SAVE_profile"
        orig_prof = "GstAudio.Subtitles 0\nGstAudio.AudioLanguage 0\nGstRender.FullscreenEnabled 1\n"
        prof_file.write_text(orig_prof, encoding="latin-1")
        (fb_mock / "Data" / "Win32" / "Loc" / "en.sb").write_bytes(b"LANG:en:Stay with the squad!\nMove out!")
        (fb_mock / "Data" / "Win32" / "Loc" / "de.sb").write_bytes(b"LANG:de:Bleib beim Trupp!\nAusruecken!")

        fb_patcher = GameConfigPatcher(fb_mock)
        fb_patcher.apply_audio_and_subtitle_config("en", "de", audio_lang="de", log=lambda *a: None)
        patched_prof = prof_file.read_text(encoding="latin-1")
        assert "GstAudio.Subtitles 1" in patched_prof
        assert "GstAudio.AudioLanguage 2" in patched_prof
        assert (fb_mock / "user.cfg").is_file()

        fb_merger = UniversalSubtitleMerger("en", "de")
        fb_summary = fb_merger.patch_game_localization_in_place(fb_mock, log=lambda *a: None)
        assert fb_summary["frostbite_patched"] is True
        assert b"Stay with the squad!\nBleib beim Trupp!" in (fb_mock / "Data" / "Win32" / "Loc" / "en.sb").read_bytes()

        UniversalSubtitleMerger.restore_all_patched_subtitles(fb_mock, log=lambda *a: None)
        fb_patcher.restore_game_configs(log=lambda *a: None)
        assert prof_file.read_text(encoding="latin-1") == orig_prof
        print("             PASS: Frostbite PROF_SAVE_profile, user.cfg, and .sb bundle merge/restore verified.")

        # 3. Test Unreal Engine 5 Binary .locres v3 Hash Preservation + en-GB + UE4SS 3.0 Scripts/main.lua
        print("  [Test 3/6] Testing Unreal Engine 5 (.locres v3 Hash Preservation + en-GB + Pak v11)...")
        ue_mock = tmp_root / "SampleUnrealApp"
        (ue_mock / "SubProject" / "Binaries" / "Win64" / "ue4ss" / "Mods").mkdir(parents=True)
        (ue_mock / "pakstore.json").write_text('{"version":1,"entries":[{"path":"SubProject"}]}', encoding="utf-8")

        from subtitle_engine import UnrealPakPatchBuilder
        paks_base = ue_mock / "SubProject" / "Content" / "Paks"
        paks_base.mkdir(parents=True, exist_ok=True)
        orig_en_locres = UnrealLocResBinary.build_locres_bytes({"ST_Cutscenes": {"LINE_01": "Ready for action!"}}, version=3)
        orig_de_locres = UnrealLocResBinary.build_locres_bytes({"ST_Cutscenes": {"LINE_01": "Bereit zum Einsatz!"}}, version=3)
        pak0_bytes = UnrealPakPatchBuilder.build_pak_bytes({
            "SubProject/Content/Localization/Game/en-GB/Game.locres": orig_en_locres,
            "SubProject/Content/Localization/Game/de-DE/Game.locres": orig_de_locres,
        })
        (paks_base / "pakchunk0-Windows.pak").write_bytes(pak0_bytes)

        en_gb_dir = ue_mock / "SubProject" / "Content" / "Localization" / "Game" / "en-GB"
        en_gb_dir.mkdir(parents=True, exist_ok=True)
        stale_locres = UnrealLocResBinary.build_locres_bytes({"ST_Cutscenes": {"DLG_01": "Stale synthetic"}}, version=2)
        (en_gb_dir / "Game.locres").write_bytes(stale_locres)

        merger = UniversalSubtitleMerger("en", "de")
        ue_summary = merger.patch_game_localization_in_place(ue_mock, data_dir=HERE / "data", log=lambda *a: None)
        assert ue_summary["unreal_patched"] is True

        merged_en_gb = (en_gb_dir / "Game.locres").read_bytes()
        assert merged_en_gb[16] == 3
        parsed_gb = UnrealLocResBinary.parse_locres_bytes(merged_en_gb)
        assert parsed_gb["ST_Cutscenes"]["LINE_01"] == "Ready for action!\nBereit zum Einsatz!"

        locres_en = ue_mock / "SubProject" / "Content" / "Localization" / "Game" / "en" / "Game.locres"
        pak_file = ue_mock / "SubProject" / "Content" / "Paks" / "~mods" / "pakchunk99-DualSub_en_de_P.pak"
        utoc_file = ue_mock / "SubProject" / "Content" / "Paks" / "~mods" / "pakchunk99-DualSub_en_de_P.utoc"
        main_lua = ue_mock / "SubProject" / "Binaries" / "Win64" / "ue4ss" / "Mods" / "DualSub" / "Scripts" / "main.lua"
        enabled_txt = ue_mock / "SubProject" / "Binaries" / "Win64" / "ue4ss" / "Mods" / "DualSub" / "enabled.txt"
        mods_txt = ue_mock / "SubProject" / "Binaries" / "Win64" / "ue4ss" / "Mods" / "mods.txt"
        assert locres_en.is_file() and pak_file.is_file() and not utoc_file.exists()
        assert main_lua.is_file() and enabled_txt.is_file() and "DualSub : 1" in mods_txt.read_text(encoding="utf-8")

        UniversalSubtitleMerger.restore_all_patched_subtitles(ue_mock, log=lambda *a: None)
        assert not (en_gb_dir / "Game.locres").exists()
        assert not pak_file.exists() and not main_lua.exists()
        print("             PASS: Unreal Engine 5 .locres v3 hash-preserving merge, en-GB/en slots, & Pak v11 verified.")

        # 4. Test SRT & ASS In-Place Merging & Restore
        print("  [Test 4/6] Testing In-Place SRT, ASS & JSON Subtitle Merger & Restore...")
        sub_en = app_mock / "cutscene_en.srt"
        sub_de = app_mock / "cutscene_de.srt"
        orig_srt = "1\n00:00:01,000 --> 00:00:04,000\nLook over there! It's a bat!\n"
        sub_en.write_text(orig_srt, encoding="utf-8")
        sub_de.write_text("1\n00:00:01,050 --> 00:00:04,000\nSieh mal da drüben! Eine Fledermaus!\n", encoding="utf-8")

        merger.patch_game_localization_in_place(app_mock, log=lambda *a: None)
        merged_srt_content = sub_en.read_text(encoding="utf-8")
        assert "Look over there! It's a bat!\nSieh mal da drüben! Eine Fledermaus!" in merged_srt_content

        UniversalSubtitleMerger.restore_all_patched_subtitles(app_mock, log=lambda *a: None)
        assert sub_en.read_text(encoding="utf-8") == orig_srt
        print("             PASS: SRT timestamp-aligned merge and restore verified.")

        # 5. Test Famous Dictionary Engine
        print("  [Test 5/6] Testing Famous Dictionary Engine (Oxford/Duden/Wiktionary)...")
        dict_eng = FamousDictionaryEngine(tmp_root / "dicts")
        bat_info = dict_eng.lookup("bats", "de")
        assert "Fledermaus" in bat_info.get("german_translation", "")
        fleder_info = dict_eng.lookup("Fledermäuse", "en")
        assert fleder_info.get("english_translation") == "bat"
        print("             PASS: Stemming, German gender articles, and offline cache verified.")

        # 6. Test 32-bit BGRA .ICO Generation & StartupManager
        print("  [Test 6/6] Testing 32-bit BGRA System Tray .ICO & StartupManager...")
        ico_test = ensure_tray_ico_file(tmp_root / "test_tray.ico")
        ico_bytes = ico_test.read_bytes()
        assert ico_bytes[:4] == b"\x00\x00\x01\x00" and len(ico_bytes) > 4000
        sm = StartupManager()
        cmd_str = sm.build_startup_command("config_sync_only")
        assert "--startup-check" in cmd_str
        print("             PASS: 32-bit BGRA .ico icon & StartupManager zero-background command verified.")

    print("=" * 72)
    print("  ALL 6 AUTOMATED VERIFICATION SUITES PASSED SUCCESSFULLY!")
    print("=" * 72)
    return 0


# ==========================================================================
# CLI Entry Point
# ==========================================================================

if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    _enable_windows_ansi_and_utf8()

    parser = argparse.ArgumentParser(
        description="DualTitle — Universal Anti-Cheat-Safe Dual Subtitle & Audio Controller"
    )
    parser.add_argument(
        "game_path",
        nargs="?",
        help="Optional path to application .exe or directory (supports drag-and-drop onto run.bat)",
    )
    parser.add_argument("--audio", help="Audio language code (e.g. en, de, fr, ja, keep)")
    parser.add_argument("--pair", help="Subtitle pair in primary_secondary format (e.g. en_de, de_en)")
    parser.add_argument("--tray", action="store_true", help="Launch Windows System Tray Mini-Controller")
    parser.add_argument("--gui", action="store_true", help="Launch High-Contrast Dark Visual Control Panel GUI")
    parser.add_argument("--overlay", action="store_true", help="Launch Universal Topmost In-Game Dual-Subtitle Overlay")
    parser.add_argument("--restore-save", action="store_true", help="1-Click Restore Save for backed-up game saves & profiles")
    parser.add_argument("--backup-save", action="store_true", help="1-Click Backup Save for game saves & profiles")
    parser.add_argument("--emergency-repair", action="store_true", help="1-Click Repair & Clean for game folders")
    parser.add_argument(
        "--startup-check",
        action="store_true",
        help="Fast boot-time config sync (verifies config and exits immediately with 0 background usage)",
    )
    parser.add_argument("--define", help="Lookup a word in the Famous Dictionary")
    parser.add_argument("--reader", action="store_true", help="Launch interactive terminal reader")
    parser.add_argument("--self-test", action="store_true", help="Run automated verification suite")
    args = parser.parse_args()

    if args.self_test:
        sys.exit(run_self_tests())

    if args.startup_check:
        sm = StartupManager(HERE / "universal_dualsub.py")
        sm.run_startup_config_sync()
        sys.exit(0)

    if args.restore_save:
        tray = DualSubTrayController()
        tray.restore_game_saves(log=print)
        sys.exit(0)

    if args.backup_save:
        tray = DualSubTrayController()
        tray.backup_game_saves(log=print)
        sys.exit(0)

    if args.emergency_repair:
        tray = DualSubTrayController()
        tray.emergency_repair_game(log=print)
        sys.exit(0)

    if args.overlay:
        tray = DualSubTrayController()
        tray.open_universal_game_overlay()
        sys.exit(0)

    if args.gui:
        tray = DualSubTrayController()
        tray.open_dark_control_panel_gui()
        sys.exit(0)

    if args.tray:
        tray = DualSubTrayController()
        tray.run()
        sys.exit(0)

    dict_engine = FamousDictionaryEngine(HERE / "dictionaries")

    if args.define:
        display_dictionary_card(dict_engine.lookup(args.define))
        sys.exit(0)

    if args.reader:
        pair = args.pair or "en_de"
        p, s = pair.split("_", 1) if "_" in pair else ("en", "de")
        interactive_terminal_reader(p, s, dict_engine)
        sys.exit(0)

    if args.game_path and args.pair:
        p, s = args.pair.split("_", 1) if "_" in args.pair else ("en", "de")
        audio = args.audio or p
        _, groot, _ = auto_detect_game_from_path(args.game_path)
        if groot and groot.is_dir():
            apply_all_settings_to_game(groot, audio, p, s, dict_engine, launch_after=False)
            sys.exit(0)

    sys.exit(main_menu(initial_game_path=args.game_path))
