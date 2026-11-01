#!/usr/bin/env python3
"""
DualTitle - Universal Application & Game Audio, Subtitle, and Save Backup/Restore Manager
Reads, backs up, modifies, and restores startup/configuration files (.ini, .cfg, .acf,
.json, .xml, .txt, PROF_SAVE_profile) and user save files across all engines:
  • Frostbite Engine (`Documents/<App>/settings/PROF_SAVE_profile`, `PROF_SAVE_body`,
    `<AppDir>/user.cfg`, `<AppDir>/__Installer/installerdata.xml`, `Data/Win32/Loc/*.sb`)
  • Unreal Engine 4 & 5 (`GameUserSettings.ini`, `Engine.ini` in `<AppDir>`, `<SubProject>`,
    and `%LOCALAPPDATA%/<App>/Saved/Config/`)
  • AnvilNext / Scimitar FORGE (`upc_r2.ini`, `uplay_r1_loader.ini`, `steam_api.ini`,
    `Documents/<App>/*.ini`)
  • Unity, Source, Creation Engine, REDengine, Godot & Generic Applications
    (`settings.json`, `config.ini`, `autoexec.cfg`, `steam_emu.ini`, `force_language.txt`)
  • Universal Save Game Backup & 1-Click Restore (`SaveBackupManager`)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# Standard language display names
LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "de": "Deutsch (German)",
    "fr": "Français (French)",
    "es": "Español (Spanish)",
    "es-419": "Español (Latinoamérica)",
    "it": "Italiano (Italian)",
    "pt-BR": "Português (Brasil)",
    "pl": "Polski (Polish)",
    "ru": "Русский (Russian)",
    "ja": "日本語 (Japanese)",
    "ko": "한국어 (Korean)",
    "zh-Hans": "简体中文 (Chinese Simplified)",
    "zh-Hant": "繁體中文 (Chinese Traditional)",
    "ar": "العربية (Arabic)",
    "nl": "Nederlands (Dutch)",
    "da": "Dansk (Danish)",
    "sv": "Svenska (Swedish)",
    "fi": "Suomi (Finnish)",
    "no": "Norsk (Norwegian)",
    "cs": "Čeština (Czech)",
    "hu": "Magyar (Hungarian)",
    "tr": "Türkçe (Turkish)",
}

# ISO / Engine Culture Codes
CULTURES: Dict[str, Tuple[str, ...]] = {
    "en": ("en-US", "en-GB", "en", "eng", "english", "en_US", "en_GB"),
    "de": ("de-DE", "de", "ger", "deu", "german", "de_DE"),
    "fr": ("fr-FR", "fr", "fre", "fra", "french", "fr_FR"),
    "es": ("es-ES", "es-MX", "es", "spa", "spanish", "es_ES"),
    "es-419": ("es-MX", "es-419", "latam", "es_MX"),
    "it": ("it-IT", "it", "ita", "italian", "it_IT"),
    "pt-BR": ("pt-BR", "pt-PT", "pt", "por", "bra", "brazilian", "portuguese", "pt_BR"),
    "pl": ("pl-PL", "pl", "pol", "polish", "pl_PL"),
    "ru": ("ru-RU", "ru", "rus", "russian", "ru_RU"),
    "ja": ("ja-JP", "ja", "jpn", "japanese", "ja_JP"),
    "ko": ("ko-KR", "ko-KO", "ko", "kor", "koreana", "korean", "ko_KR"),
    "zh-Hans": ("zh-CN", "zh-Hans", "zh-CHS", "schinese", "chinese", "zh_CN"),
    "zh-Hant": ("zh-TW", "zh-Hant", "zh-CHT", "tchinese", "zh_TW"),
    "ar": ("ar-SA", "ar-AA", "ar", "ara", "arabic", "ar_SA"),
    "nl": ("nl-NL", "nl", "dut", "nld", "dutch", "nl_NL"),
    "da": ("da-DK", "da", "dan", "danish", "da_DK"),
    "sv": ("sv-SE", "sv", "swe", "swedish", "sv_SE"),
    "fi": ("fi-FI", "fi", "fin", "finnish", "fi_FI"),
    "no": ("nb-NO", "no", "nor", "norwegian", "nb_NO"),
    "cs": ("cs-CZ", "cs", "cze", "ces", "czech", "cs_CZ"),
    "hu": ("hu-HU", "hu", "hun", "hungarian", "hu_HU"),
    "tr": ("tr-TR", "tr", "tur", "turkish", "tr_TR"),
}

# Steam / Emulator API language identifiers
STEAM_LANGUAGES: Dict[str, str] = {
    "en": "english",
    "de": "german",
    "fr": "french",
    "es": "spanish",
    "es-419": "latam",
    "it": "italian",
    "pt-BR": "brazilian",
    "pl": "polish",
    "ru": "russian",
    "ja": "japanese",
    "ko": "koreana",
    "zh-Hans": "schinese",
    "zh-Hant": "tchinese",
    "ar": "arabic",
    "nl": "dutch",
    "da": "danish",
    "sv": "swedish",
    "fi": "finnish",
    "no": "norwegian",
    "cs": "czech",
    "hu": "hungarian",
    "tr": "turkish",
}

REVERSE_STEAM_LANGUAGES: Dict[str, str] = {v: k for k, v in STEAM_LANGUAGES.items()}

# Numeric language IDs used by AnvilNext / Scimitar INI files
NUMERIC_LANG_IDS: Dict[str, int] = {
    "en": 1,
    "fr": 2,
    "it": 3,
    "de": 4,
    "es": 5,
    "ru": 6,
    "pl": 7,
    "pt-BR": 9,
    "ja": 10,
    "nl": 11,
    "da": 12,
    "no": 13,
    "fi": 14,
    "sv": 15,
    "zh-Hant": 16,
    "zh-Hans": 17,
    "ko": 18,
    "cs": 19,
    "hu": 20,
}
REVERSE_NUMERIC_LANG_IDS: Dict[int, str] = {v: k for k, v in NUMERIC_LANG_IDS.items()}

# Frostbite GstAudio.AudioLanguage numeric IDs & locale codes
FROSTBITE_AUDIO_IDS: Dict[str, int] = {
    "en": 0,
    "fr": 1,
    "de": 2,
    "it": 3,
    "es": 4,
    "pl": 5,
    "ru": 6,
    "ja": 7,
    "pt-BR": 8,
    "zh-Hans": 9,
    "zh-Hant": 9,
    "ko": 10,
}
REVERSE_FROSTBITE_AUDIO_IDS: Dict[int, str] = {v: k for k, v in FROSTBITE_AUDIO_IDS.items() if k != "zh-Hant"}

FROSTBITE_LOCALE_CODES: Dict[str, str] = {
    "en": "en_US",
    "de": "de_DE",
    "fr": "fr_FR",
    "es": "es_ES",
    "it": "it_IT",
    "pl": "pl_PL",
    "ru": "ru_RU",
    "ja": "ja_JP",
    "ko": "ko_KR",
    "zh-Hans": "zh_CN",
    "zh-Hant": "zh_TW",
    "pt-BR": "pt_BR",
    "cs": "cs_CZ",
}

DEFAULT_VOICE_LANGUAGES: List[str] = [
    "en", "de", "fr", "es", "it", "pt-BR", "ru", "ja", "zh-Hans", "pl"
]

JOURNAL_FILENAME = ".dualsub_journal.json"
SAVE_BACKUP_DIRNAME = ".dualtitle_save_backup"


def culture_to_lang_code(culture_str: str) -> Optional[str]:
    """Convert a culture string like 'de-DE', 'de_DE', 'german', 'en-US', or '4' to canonical code ('de', 'en')."""
    if not culture_str:
        return None
    clean = culture_str.strip().strip('"').strip("'")
    if not clean:
        return None
    if clean.isdigit():
        num = int(clean)
        if num in REVERSE_NUMERIC_LANG_IDS:
            return REVERSE_NUMERIC_LANG_IDS[num]
    clean_lower = clean.lower()

    for code, variants in CULTURES.items():
        if clean_lower == code.lower():
            return code
        for v in variants:
            if clean_lower == v.lower():
                return code

    if clean_lower in REVERSE_STEAM_LANGUAGES:
        return REVERSE_STEAM_LANGUAGES[clean_lower]

    prefix = re.split(r"[-_]", clean_lower)[0]
    if prefix in CULTURES:
        return prefix
    return None


def lang_code_to_culture(lang_code: str) -> str:
    """Return the primary culture code (e.g. 'de-DE') for a canonical language code."""
    variants = CULTURES.get(lang_code)
    if variants:
        return variants[0]
    return lang_code


def find_unreal_subprojects(game_dir: Path) -> List[Path]:
    """
    Dynamically discover any Unreal Engine subproject folders inside `game_dir`
    (e.g., `<game_dir>/<SubProject>/Content/Paks` or `<game_dir>/<SubProject>/Binaries`)
    without hardcoding any specific application name.
    """
    subprojects: List[Path] = []
    if not game_dir or not game_dir.is_dir():
        return subprojects
    try:
        for child in sorted(game_dir.iterdir()):
            if not child.is_dir() or child.name.lower() in (
                "engine", "mods", "sounddata", "data", "update", "core",
                "__installer", "redist", "support", "directx", ".dualtitle_save_backup",
            ):
                continue
            if (
                (child / "Content").is_dir()
                or (child / "Binaries").is_dir()
                or (child / "Saved").is_dir()
            ):
                subprojects.append(child)
    except OSError:
        pass
    return subprojects


def _normalize_app_token(name: str) -> str:
    """Normalize an application folder or executable name for fuzzy matching against Documents/AppData."""
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def find_matching_user_dirs(game_dir: Path) -> List[Path]:
    """
    Locate matching application folders inside `%USERPROFILE%/Documents`,
    `%USERPROFILE%/Documents/My Games`, `%LOCALAPPDATA%`, and `%APPDATA%`
    dynamically based on `game_dir.name`, subproject names, and `.exe` stems.
    """
    candidates: List[Path] = []
    if not game_dir or not game_dir.is_dir():
        return candidates

    app_names: set[str] = {game_dir.name}
    for sub in find_unreal_subprojects(game_dir):
        app_names.add(sub.name)
    try:
        for exe in game_dir.glob("*.exe"):
            stem = exe.stem
            if not any(x in stem.lower() for x in ("unins", "crash", "cleanup", "setup", "dxsetup", "vc_redist")):
                app_names.add(stem)
    except OSError:
        pass

    norm_targets = {_normalize_app_token(n) for n in app_names if len(_normalize_app_token(n)) >= 2}

    search_roots: List[Path] = []
    user_profile = os.environ.get("USERPROFILE") or str(Path.home())
    if user_profile:
        up = Path(user_profile)
        search_roots.extend([
            up / "Documents",
            up / "Documents" / "My Games",
            up / "Saved Games",
        ])
    for env_key in ("LOCALAPPDATA", "APPDATA"):
        val = os.environ.get(env_key)
        if val:
            search_roots.append(Path(val))

    seen: set[str] = set()
    for sroot in search_roots:
        if not sroot.is_dir():
            continue
        # Exact name check first
        for raw_name in app_names:
            direct = sroot / raw_name
            if direct.is_dir():
                rstr = str(direct.resolve())
                if rstr not in seen:
                    seen.add(rstr)
                    candidates.append(direct)
        # Normalized directory match
        try:
            for item in sroot.iterdir():
                if not item.is_dir():
                    continue
                inorm = _normalize_app_token(item.name)
                if inorm and inorm in norm_targets:
                    rstr = str(item.resolve())
                    if rstr not in seen:
                        seen.add(rstr)
                        candidates.append(item)
        except OSError:
            pass

    return candidates


# ==========================================================================
# Universal Save Game & Profile Backup / Restore Manager ("Restore Save")
# ==========================================================================

class SaveBackupManager:
    """
    Discovers, backs up, and restores user save files and profile settings across all
    engines and applications:
      • Local application save folders (`Saved/SaveGames`, `Saves`, `Save`, `save3dmgames`, `Profile`, `settings`)
      • Unreal Engine subproject & `%LOCALAPPDATA%/<App>/Saved/SaveGames`
      • Frostbite `Documents/<App>/settings/PROF_SAVE*` (`PROF_SAVE`, `PROF_SAVE_body`, `PROF_SAVE_profile`)
      • Documents & My Games save directories (`Documents/<App>`, `Documents/My Games/<App>`)
      • Standalone `.sav`, `.save`, `PROF_SAVE*`, and profile `.ini`/`.cfg` files
    """

    MAX_SINGLE_SAVE_BYTES = 64 * 1024 * 1024  # 64 MB cap per save file

    def __init__(self, game_dir: str | Path, central_backup_root: Optional[Path] = None):
        self.game_dir = Path(game_dir).resolve()
        self.local_backup_dir = self.game_dir / SAVE_BACKUP_DIRNAME
        suite_root = Path(__file__).parent.resolve()
        slug = re.sub(r"[^A-Za-z0-9_\-]+", "_", self.game_dir.name).strip("_") or "app"
        self.central_backup_dir = (central_backup_root or (suite_root / "backups" / slug)).resolve()

    def discover_save_files(self) -> List[Path]:
        """Find all save game files and user profile files associated with `self.game_dir`."""
        found: List[Path] = []
        seen: set[str] = set()

        def add_file(fp: Path) -> None:
            try:
                if not fp.is_file():
                    return
                if SAVE_BACKUP_DIRNAME in fp.parts or "backups" in fp.parts:
                    return
                sz = fp.stat().st_size
                if sz > self.MAX_SINGLE_SAVE_BYTES:
                    return
                resolved = str(fp.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(fp.resolve())
            except OSError:
                pass

        if not self.game_dir.exists():
            return found

        # 1. Explicit save/profile directories inside game_dir and Unreal subprojects
        save_roots: List[Path] = [
            self.game_dir / "Saved" / "SaveGames",
            self.game_dir / "Saved" / "Config",
            self.game_dir / "Saves",
            self.game_dir / "Save",
            self.game_dir / "SaveGames",
            self.game_dir / "SaveData",
            self.game_dir / "save3dmgames",
            self.game_dir / "Profile",
            self.game_dir / "Profiles",
            self.game_dir / "settings",
            self.game_dir / "steam_settings",
        ]
        for sub in find_unreal_subprojects(self.game_dir):
            save_roots.append(sub / "Saved" / "SaveGames")
            save_roots.append(sub / "Saved" / "Config")

        # 2. Matching user directories in Documents, My Games, %LOCALAPPDATA%, %APPDATA%
        for udir in find_matching_user_dirs(self.game_dir):
            save_roots.extend([
                udir / "settings",
                udir / "Saved" / "SaveGames",
                udir / "Saved" / "Config",
                udir / "Saves",
                udir / "Save",
                udir / "SaveGames",
                udir / "save3dmgames",
                udir / "Profiles",
            ])
            # Also scan top-level files in udir (e.g., Documents/<App>/*.ini, *.sav, PROF_SAVE*)
            try:
                for item in udir.iterdir():
                    if item.is_file() and (
                        item.suffix.lower() in (".sav", ".save", ".ini", ".cfg", ".json", ".profsave")
                        or item.name.startswith("PROF_SAVE")
                    ):
                        add_file(item)
            except OSError:
                pass

        for sroot in save_roots:
            if sroot.is_dir():
                try:
                    for fp in sroot.rglob("*"):
                        if fp.is_file() and not fp.name.endswith((".dualsub.bak", ".dualtitle.bak")):
                            add_file(fp)
                except OSError:
                    pass

        # 3. Direct save files or Frostbite PROF_SAVE* / *.sav files inside game_dir
        try:
            for ext in ("*.sav", "*.save", "PROF_SAVE*", "user.cfg"):
                for fp in self.game_dir.rglob(ext):
                    if fp.is_file():
                        add_file(fp)
        except OSError:
            pass

        return found

    def backup_saves(self, log=print) -> Tuple[int, Path]:
        """
        Create a byte-exact backup of all discovered save files and profile settings
        in both `<game_dir>/.dualtitle_save_backup/` and `<suite_dir>/backups/<app>/`.
        Never overwrites an existing initial clean backup of a file unless `update_latest=True`
        is stored alongside the original snapshot.
        Returns `(backed_up_count, backup_dir_path)`.
        """
        save_files = self.discover_save_files()
        self.local_backup_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = self.local_backup_dir / "save_manifest.json"

        manifest: Dict[str, Any] = {"app_dir": str(self.game_dir), "timestamp": time.time(), "files": {}}
        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        files_map: Dict[str, Dict[str, Any]] = manifest.setdefault("files", {})

        count = 0
        for idx, fp in enumerate(save_files):
            try:
                raw_bytes = fp.read_bytes()
                # Skip empty 0-byte corrupted files if we already have a non-empty backup
                key = str(fp)
                slot_name = f"save_{idx:04d}_{fp.name}"
                if key in files_map and files_map[key].get("slot_name"):
                    slot_name = files_map[key]["slot_name"]

                local_slot = self.local_backup_dir / slot_name
                orig_slot = self.local_backup_dir / f"orig_{slot_name}"

                # Preserve the very first non-empty backup in `orig_slot`
                if not orig_slot.is_file() and len(raw_bytes) > 0:
                    orig_slot.write_bytes(raw_bytes)
                if len(raw_bytes) > 0 or not local_slot.is_file():
                    local_slot.write_bytes(raw_bytes)

                files_map[key] = {
                    "original_path": key,
                    "slot_name": slot_name,
                    "orig_slot_name": f"orig_{slot_name}",
                    "size": len(raw_bytes),
                    "mtime": fp.stat().st_mtime,
                }
                count += 1
            except OSError:
                pass

        manifest["timestamp"] = time.time()
        try:
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

        # Mirror to central backup directory inside DualTitle suite folder
        try:
            self.central_backup_dir.mkdir(parents=True, exist_ok=True)
            for item in self.local_backup_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, self.central_backup_dir / item.name)
        except OSError:
            pass

        if count > 0:
            log(f"    [SaveBackup] Backed up {count} save/profile file(s) to {self.local_backup_dir.name}")
        return count, self.local_backup_dir

    def restore_saves(self, prefer_original: bool = True, log=print) -> Tuple[int, str]:
        """
        Restore backed-up save files and profile settings for `self.game_dir`.
        Also repairs any native `.bak` save files inside save directories if a save was truncated.
        Returns `(restored_count, status_message)`.
        """
        restored = 0
        source_dir = self.local_backup_dir
        manifest_path = source_dir / "save_manifest.json"
        if not manifest_path.is_file() and (self.central_backup_dir / "save_manifest.json").is_file():
            source_dir = self.central_backup_dir
            manifest_path = source_dir / "save_manifest.json"

        if manifest_path.is_file():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                for orig_str, info in manifest.get("files", {}).items():
                    dest = Path(orig_str)
                    slot_name = info.get("orig_slot_name") if prefer_original else info.get("slot_name")
                    src_file = source_dir / (slot_name or "")
                    if not src_file.is_file():
                        src_file = source_dir / info.get("slot_name", "")
                    if src_file.is_file():
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src_file, dest)
                        log(f"    [RestoreSave] Restored save/profile file: {dest.name}")
                        restored += 1
            except (OSError, ValueError) as exc:
                log(f"    [RestoreSave] Warning reading save manifest: {exc}")

        # Also check for any `.dualsub.bak` or `.dualtitle.bak` or `.sav.bak` files in save folders
        for fp in self.discover_save_files():
            for suffix in (".dualsub.bak", ".dualtitle.bak", ".bak"):
                bak_cand = Path(str(fp) + suffix)
                if bak_cand.is_file() and bak_cand.stat().st_size > 0:
                    try:
                        shutil.copy2(bak_cand, fp)
                        if suffix in (".dualsub.bak", ".dualtitle.bak"):
                            bak_cand.unlink(missing_ok=True)
                        log(f"    [RestoreSave] Restored backup save: {fp.name}")
                        restored += 1
                    except OSError:
                        pass

        # Also restore game configuration files via GameConfigPatcher
        cfg_restored = GameConfigPatcher(self.game_dir).restore_game_configs(log=log)
        total = restored + cfg_restored

        if total > 0:
            msg = f"Restored {restored} save/profile file(s) and {cfg_restored} config file(s) for {self.game_dir.name}."
        else:
            # If no prior backup existed yet, create an initial safety snapshot right now!
            backed_up, _ = self.backup_saves(log=log)
            msg = (
                f"Save files verified ({backed_up} save/profile file(s) protected in backup snapshot for {self.game_dir.name})."
                if backed_up > 0
                else f"No modified save or config files found in {self.game_dir.name}; original saves are intact."
            )
        log(f"[DualTitle] {msg}")
        return total, msg


# ==========================================================================
# Universal Application & Game Audio/Subtitle Config Patcher
# ==========================================================================

class GameConfigPatcher:
    """
    Inspects, backs up, patches, and restores game configuration files (.ini, .cfg,
    PROF_SAVE_profile, .xml, .json, .txt) to control both Spoken Audio Language and
    Subtitle Language across all engines.
    """

    def __init__(self, game_dir: str | Path):
        self.game_dir = Path(game_dir).resolve()
        self.journal_path = self.game_dir / JOURNAL_FILENAME

    # ------------------------------------------------------------------
    # Discovery of Config Files & Installed Audio Languages
    # ------------------------------------------------------------------

    def find_config_files(self) -> Dict[str, List[Path]]:
        """Locate all relevant config files inside the application directory, Documents, and AppData."""
        found: Dict[str, List[Path]] = {
            "ubisoft_ini": [],
            "docs_ini": [],
            "unreal_ini": [],
            "steam_ini": [],
            "steam_txt": [],
            "frostbite_prof": [],
            "frostbite_cfg": [],
            "installer_xml": [],
        }
        if not self.game_dir.exists():
            return found

        # 1. Ubisoft / Uplay / AnvilNext INI files
        ubisoft_names = (
            "upc_r2.ini",
            "uplay_r2.ini",
            "uplay_r1_loader.ini",
            "uplay_r1.ini",
            "uplay.ini",
            "LumaPlay.ini",
            "orbit.ini",
        )
        for name in ubisoft_names:
            for candidate in [self.game_dir / name, self.game_dir / "bin" / name]:
                if candidate.is_file() and candidate not in found["ubisoft_ini"]:
                    found["ubisoft_ini"].append(candidate)

        # Also check any matching user folders in Documents / My Games for *.ini and Frostbite PROF_SAVE_profile
        for udir in find_matching_user_dirs(self.game_dir):
            try:
                for ini_cand in udir.glob("*.ini"):
                    if ini_cand.is_file() and ini_cand not in found["docs_ini"]:
                        found["docs_ini"].append(ini_cand)
            except OSError:
                pass
            for prof_cand in [
                udir / "settings" / "PROF_SAVE_profile",
                udir / "PROF_SAVE_profile",
            ]:
                if prof_cand.is_file() and prof_cand not in found["frostbite_prof"]:
                    found["frostbite_prof"].append(prof_cand)

        # Also check direct PROF_SAVE_profile or user.cfg inside game_dir
        for local_prof in [
            self.game_dir / "settings" / "PROF_SAVE_profile",
            self.game_dir / "PROF_SAVE_profile",
        ]:
            if local_prof.is_file() and local_prof not in found["frostbite_prof"]:
                found["frostbite_prof"].append(local_prof)

        if (self.game_dir / "user.cfg").is_file():
            found["frostbite_cfg"].append(self.game_dir / "user.cfg")

        installer_xml = self.game_dir / "__Installer" / "installerdata.xml"
        if installer_xml.is_file():
            found["installer_xml"].append(installer_xml)

        # 2. Steam / EA / Emulator INI files
        steam_names = (
            "steam_api.ini",
            "steam_emu.ini",
            "SteamConfig.ini",
            "configs.user.ini",
            "flt.ini",
            "codex.ini",
            "tenoke.ini",
            "ali213.ini",
            "3dmgame.ini",
            "skidrow.ini",
            "origin.ini",
            "ea_emu.ini",
        )
        search_dirs = [
            self.game_dir,
            self.game_dir / "bin",
            self.game_dir / "Core",
            self.game_dir / "Engine" / "Binaries" / "ThirdParty" / "Steamworks" / "Steamv153" / "Win64",
            self.game_dir / "Engine" / "Binaries" / "ThirdParty" / "Steamworks" / "Steamv157" / "Win64",
            self.game_dir / "steam_settings",
        ]
        for sub in find_unreal_subprojects(self.game_dir):
            search_dirs.append(sub / "Binaries" / "Win64")

        for root_candidate in search_dirs:
            if root_candidate.is_dir():
                for sname in steam_names:
                    p = root_candidate / sname
                    if p.is_file() and p not in found["steam_ini"]:
                        found["steam_ini"].append(p)
                for txt_name in ("force_language.txt", "language.txt"):
                    force_lang = root_candidate / txt_name
                    if force_lang.is_file() and force_lang not in found["steam_txt"]:
                        found["steam_txt"].append(force_lang)

        # 3. Unreal Engine INI files (GameUserSettings.ini, Engine.ini)
        unreal_candidates: List[Path] = []
        ue_roots = [self.game_dir] + find_unreal_subprojects(self.game_dir)
        for uroot in ue_roots:
            for cfg_variant in ("Windows", "WindowsNoEditor", "WinGDK"):
                for ini_name in ("GameUserSettings.ini", "Engine.ini"):
                    unreal_candidates.append(uroot / "Saved" / "Config" / cfg_variant / ini_name)

        for udir in find_matching_user_dirs(self.game_dir):
            for cfg_variant in ("Windows", "WindowsNoEditor", "WinGDK"):
                for ini_name in ("GameUserSettings.ini", "Engine.ini"):
                    unreal_candidates.append(udir / "Saved" / "Config" / cfg_variant / ini_name)

        for cand in unreal_candidates:
            if cand.is_file() and cand not in found["unreal_ini"]:
                found["unreal_ini"].append(cand)

        return found

    def detect_current_settings(self) -> Dict[str, Optional[str]]:
        """Read the application's current configuration for Audio Language and Subtitle Language."""
        result: Dict[str, Optional[str]] = {
            "audio_lang": None,
            "subtitle_lang": None,
            "config_source": None,
        }
        configs = self.find_config_files()

        # 0. Check .dualsub_journal.json active_config first if already patched
        journal = self._load_journal()
        active_cfg = journal.get("active_config", {})
        if isinstance(active_cfg, dict):
            if active_cfg.get("primary_sub_lang"):
                result["subtitle_lang"] = active_cfg.get("primary_sub_lang")
            if active_cfg.get("audio_lang"):
                result["audio_lang"] = active_cfg.get("audio_lang")

        # 1. Check Ubisoft & Documents INI files
        for ini_path in configs["ubisoft_ini"] + configs["docs_ini"]:
            try:
                content = ini_path.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith((";", "#")) or "=" not in stripped:
                        continue
                    k, _, v = stripped.partition("=")
                    key_lower = k.strip().lower()
                    val_code = culture_to_lang_code(v.strip())
                    if not val_code:
                        continue
                    if key_lower in ("language", "textlanguage", "subtitleslanguage", "culture"):
                        result["subtitle_lang"] = result["subtitle_lang"] or val_code
                        result["config_source"] = result["config_source"] or ini_path.name
                    if key_lower in ("audiolanguage", "voicelanguage", "speechlanguage", "soundlanguage"):
                        result["audio_lang"] = result["audio_lang"] or val_code
                        result["config_source"] = result["config_source"] or ini_path.name
                if result["subtitle_lang"] and not result["audio_lang"]:
                    result["audio_lang"] = result["subtitle_lang"]
            except OSError:
                pass

        # 2. Check Steam / Emulator INI files
        for ini_path in configs["steam_ini"]:
            try:
                content = ini_path.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith((";", "#")) or "=" not in stripped:
                        continue
                    k, _, v = stripped.partition("=")
                    key_lower = k.strip().lower()
                    val_code = culture_to_lang_code(v.strip())
                    if not val_code:
                        continue
                    if key_lower in ("language", "textlanguage", "subtitleslanguage", "locale"):
                        result["subtitle_lang"] = result["subtitle_lang"] or val_code
                        result["audio_lang"] = result["audio_lang"] or val_code
                        result["config_source"] = result["config_source"] or ini_path.name
                    elif key_lower in ("audiolanguage", "speechlanguage", "voicelanguage"):
                        result["audio_lang"] = result["audio_lang"] or val_code
                        result["config_source"] = result["config_source"] or ini_path.name
            except OSError:
                pass

        # 3. Check Frostbite PROF_SAVE_profile
        for prof_path in configs["frostbite_prof"]:
            try:
                raw = prof_path.read_text(encoding="latin-1", errors="replace")
                m = re.search(r"GstAudio\.AudioLanguage\s+(\d+)", raw)
                if m:
                    aid = int(m.group(1))
                    if aid in REVERSE_FROSTBITE_AUDIO_IDS:
                        result["audio_lang"] = result["audio_lang"] or REVERSE_FROSTBITE_AUDIO_IDS[aid]
                        result["config_source"] = result["config_source"] or prof_path.name
            except OSError:
                pass

        # 4. Check Unreal INI (Engine.ini / GameUserSettings.ini)
        for ini_path in configs["unreal_ini"]:
            try:
                content = ini_path.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith((";", "#")) or "=" not in stripped:
                        continue
                    k, _, v = stripped.partition("=")
                    key_lower = k.strip().lower()
                    val_code = culture_to_lang_code(v.strip())
                    if not val_code:
                        continue
                    if key_lower in ("culture", "language", "subtitlelanguage"):
                        result["subtitle_lang"] = result["subtitle_lang"] or val_code
                        result["config_source"] = result["config_source"] or ini_path.name
                    elif key_lower in ("audioculture", "voicelanguage", "audiolanguage"):
                        result["audio_lang"] = result["audio_lang"] or val_code
                        result["config_source"] = result["config_source"] or ini_path.name
            except OSError:
                pass

        return result

    def detect_available_audio_languages(self) -> List[str]:
        """
        Inspect installed sound/localization archives in the application folder
        (such as `sounddata/PC/sounds_*.pck`, `Data/Win32/Loc/*.sb`, `Content/Localization/*`)
        to list available spoken audio languages.
        """
        detected: List[str] = []
        if not self.game_dir.exists():
            return list(DEFAULT_VOICE_LANGUAGES)

        iso3_map = {
            "eng": "en", "en": "en", "english": "en", "en_us": "en", "en-us": "en", "en-gb": "en",
            "ger": "de", "deu": "de", "de": "de", "german": "de", "de_de": "de", "de-de": "de",
            "fre": "fr", "fra": "fr", "fr": "fr", "french": "fr", "fr_fr": "fr", "fr-fr": "fr",
            "spa": "es", "es": "es", "spanish": "es", "es_es": "es", "es-es": "es",
            "ita": "it", "it": "it", "italian": "it", "it_it": "it", "it-it": "it",
            "por": "pt-BR", "bra": "pt-BR", "pt": "pt-BR", "brazilian": "pt-BR", "pt_br": "pt-BR", "pt-br": "pt-BR",
            "rus": "ru", "ru": "ru", "russian": "ru", "ru_ru": "ru", "ru-ru": "ru",
            "jpn": "ja", "ja": "ja", "japanese": "ja", "ja_jp": "ja", "ja-jp": "ja",
            "chi": "zh-Hans", "zho": "zh-Hans", "chs": "zh-Hans", "zh_cn": "zh-Hans", "zh-cn": "zh-Hans",
            "pol": "pl", "pl": "pl", "polish": "pl", "pl_pl": "pl", "pl-pl": "pl",
            "kor": "ko", "ko": "ko", "korean": "ko", "ko_kr": "ko", "ko-kr": "ko",
        }

        probe_dirs = [
            self.game_dir / "sounddata" / "PC",
            self.game_dir / "sounddata" / "pc",
            self.game_dir / "sounddata",
            self.game_dir / "multiplayer" / "sounddata" / "PC",
            self.game_dir / "Data" / "Win32" / "Loc",
            self.game_dir / "Update" / "Patch" / "Data" / "Win32" / "Loc",
            self.game_dir / "Sound",
            self.game_dir / "Audio",
            self.game_dir / "Content" / "Paks",
            self.game_dir / "Content" / "Localization",
        ]
        for sub in find_unreal_subprojects(self.game_dir):
            probe_dirs.append(sub / "Content" / "Paks")
            probe_dirs.append(sub / "Content" / "Localization")

        for sound_dir in probe_dirs:
            if sound_dir.is_dir():
                try:
                    for item in sorted(sound_dir.iterdir()):
                        low = item.name.lower()
                        for tag, code in iso3_map.items():
                            if re.search(rf"(?:^|[_\-\.])({re.escape(tag)})(?:[_\-\.]|$)", low):
                                if code not in detected:
                                    detected.append(code)
                except OSError:
                    pass

        if not detected:
            return list(DEFAULT_VOICE_LANGUAGES)
        for base in ("en", "de"):
            if base not in detected:
                detected.insert(0, base)
        return detected

    # ------------------------------------------------------------------
    # Journal Backup Helpers
    # ------------------------------------------------------------------

    def _load_journal(self) -> Dict[str, Any]:
        if self.journal_path.is_file():
            try:
                return json.loads(self.journal_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        return {}

    def _save_journal(self, journal: Dict[str, Any]) -> None:
        self.game_dir.mkdir(parents=True, exist_ok=True)
        with open(self.journal_path, "w", encoding="utf-8") as f:
            json.dump(journal, f, indent=2, ensure_ascii=False)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass

    def _backup_config_file(self, file_path: Path) -> None:
        """Record the original byte/text content of a config file in .dualsub_journal.json before first edit."""
        journal = self._load_journal()
        backups = journal.setdefault("config_backups", {})
        key = str(file_path.resolve())
        if key not in backups:
            if file_path.is_file():
                raw = file_path.read_bytes()
                backups[key] = {
                    "existed": True,
                    "content": raw.decode("utf-8", errors="replace"),
                    "hex": raw.hex(),
                }
            else:
                backups[key] = {
                    "existed": False,
                    "content": "",
                }
            self._save_journal(journal)

    # ------------------------------------------------------------------
    # INI & Frostbite Modification Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _update_ini_keys(content: str, section_name: str, updates: Dict[str, str]) -> str:
        """
        Safely update or insert key=value pairs inside an INI section while preserving
        comments, formatting, and line endings.
        """
        line_ending = "\r\n" if "\r\n" in content else "\n"
        lines = content.splitlines()
        out_lines: List[str] = []

        target_sec_lower = f"[{section_name.lower()}]"
        in_target_section = False
        section_found = False
        updated_keys_lower: set[str] = set()
        key_map_lower = {k.lower(): (k, v) for k, v in updates.items()}

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                if in_target_section:
                    for k_low, (orig_k, val) in key_map_lower.items():
                        if k_low not in updated_keys_lower:
                            out_lines.append(f"{orig_k}={val}")
                            updated_keys_lower.add(k_low)
                in_target_section = (stripped.lower() == target_sec_lower)
                if in_target_section:
                    section_found = True
                out_lines.append(line)
                continue

            if stripped and not stripped.startswith((";", "#")) and "=" in stripped:
                k, _, _ = stripped.partition("=")
                k_low = k.strip().lower()
                if k_low in key_map_lower and (in_target_section or not section_found):
                    orig_k, new_val = key_map_lower[k_low]
                    eq_match = re.match(r"^(\s*[^=]+?\s*=\s*)", line)
                    prefix = eq_match.group(1) if eq_match else f"{orig_k}="
                    out_lines.append(f"{prefix}{new_val}")
                    updated_keys_lower.add(k_low)
                    continue

            out_lines.append(line)

        if in_target_section:
            for k_low, (orig_k, val) in key_map_lower.items():
                if k_low not in updated_keys_lower:
                    out_lines.append(f"{orig_k}={val}")
                    updated_keys_lower.add(k_low)

        if not section_found:
            remaining = [
                (orig_k, val)
                for k_low, (orig_k, val) in key_map_lower.items()
                if k_low not in updated_keys_lower
            ]
            if remaining:
                if out_lines and out_lines[-1].strip() != "":
                    out_lines.append("")
                if section_name:
                    out_lines.append(f"[{section_name}]")
                for orig_k, val in remaining:
                    out_lines.append(f"{orig_k}={val}")

        result = line_ending.join(out_lines)
        if content.endswith(("\n", "\r\n")) and not result.endswith(("\n", "\r\n")):
            result += line_ending
        return result

    @staticmethod
    def _update_frostbite_prof_save(raw_bytes: bytes, updates: Dict[str, str]) -> bytes:
        """
        Safely update `GstAudio.*` / `GstRender.*` settings inside a Frostbite
        `PROF_SAVE_profile` file (preserving any binary header/footer bytes untouched).
        """
        text = raw_bytes.decode("latin-1")
        for key, val in updates.items():
            pattern = re.compile(rf"({re.escape(key)}\s+)([^\r\n\x00]+)")
            if pattern.search(text):
                text = pattern.sub(rf"\g<1>{val}", text)
            else:
                if text.endswith("\n") or text.endswith("\x00"):
                    text += f"{key} {val}\n"
                else:
                    text += f"\n{key} {val}\n"
        return text.encode("latin-1")

    # ------------------------------------------------------------------
    # Apply & Restore Audio + Subtitle Configuration
    # ------------------------------------------------------------------

    def apply_audio_and_subtitle_config(
        self,
        primary_sub_lang: str,
        secondary_sub_lang: str,
        audio_lang: Optional[str] = None,
        log=print,
    ) -> List[Path]:
        """
        Write the selected Audio Language and Primary Subtitle Language directly into
        the application's configuration files, and automatically create a save backup first.
        """
        # Always back up user save files before applying configuration changes
        try:
            SaveBackupManager(self.game_dir).backup_saves(log=log)
        except Exception:
            pass

        effective_audio = audio_lang if audio_lang and audio_lang != "keep" else primary_sub_lang
        sub_culture = lang_code_to_culture(primary_sub_lang)
        audio_culture = lang_code_to_culture(effective_audio)
        steam_sub = STEAM_LANGUAGES.get(primary_sub_lang, "english")
        steam_audio = STEAM_LANGUAGES.get(effective_audio, steam_sub)
        fb_locale = FROSTBITE_LOCALE_CODES.get(primary_sub_lang, "en_US")
        fb_audio_id = str(FROSTBITE_AUDIO_IDS.get(effective_audio, 0))

        configs = self.find_config_files()
        modified_files: List[Path] = []

        # 1. Check if this is a FORGE archive application
        is_forge_game = any(self.game_dir.glob("*.forge"))
        ubisoft_targets = list(configs["ubisoft_ini"])
        if is_forge_game and not ubisoft_targets:
            ubisoft_targets.append(self.game_dir / "upc_r2.ini")
        if (self.game_dir / "uplay_r1.dll").is_file():
            uplay_r1_ini = self.game_dir / "uplay_r1_loader.ini"
            if uplay_r1_ini.is_file() and uplay_r1_ini not in ubisoft_targets:
                ubisoft_targets.append(uplay_r1_ini)

        for ini_path in ubisoft_targets:
            self._backup_config_file(ini_path)
            existing = ini_path.read_text(encoding="utf-8", errors="replace") if ini_path.is_file() else ""
            updates = {
                "Language": sub_culture,
                "TextLanguage": sub_culture,
                "SubtitlesLanguage": sub_culture,
                "AudioLanguage": audio_culture,
                "Subtitles": "1",
            }
            updated = self._update_ini_keys(existing, "Language", updates)
            ini_path.write_text(updated, encoding="utf-8")
            modified_files.append(ini_path)
            log(f"    [ConfigPatcher] Updated config: {ini_path.name} (Audio={audio_culture}, Text={sub_culture})")

        # 1b. Patch Documents INI files if present
        for docs_ini in configs["docs_ini"]:
            self._backup_config_file(docs_ini)
            existing = docs_ini.read_text(encoding="utf-8", errors="replace")
            sub_id = str(NUMERIC_LANG_IDS.get(primary_sub_lang, 1))
            aud_id = str(NUMERIC_LANG_IDS.get(effective_audio, 1))
            updated = self._update_ini_keys(
                existing,
                "Options",
                {
                    "Language": sub_id,
                    "Subtitles": "1",
                    "VoiceLanguage": aud_id,
                },
            )
            docs_ini.write_text(updated, encoding="utf-8")
            modified_files.append(docs_ini)
            log(f"    [ConfigPatcher] Updated Documents config: {docs_ini.name} (Subtitles=ON, AudioID={aud_id}, TextID={sub_id})")

        # 2. Patch Frostbite Engine (`PROF_SAVE_profile`, `user.cfg`, `installerdata.xml`)
        is_frostbite = (
            (self.game_dir / "Data" / "Win32" / "Loc").is_dir()
            or (self.game_dir / "Update" / "Patch" / "Data" / "Win32" / "Loc").is_dir()
            or bool(configs["frostbite_prof"])
            or any(self.game_dir.glob("GDFBinary*.dll"))
        )
        for prof_path in configs["frostbite_prof"]:
            self._backup_config_file(prof_path)
            raw_bytes = prof_path.read_bytes()
            patched_bytes = self._update_frostbite_prof_save(
                raw_bytes,
                {
                    "GstAudio.Subtitles": "1",
                    "GstAudio.AudioLanguage": fb_audio_id,
                    "GstRender.FullscreenEnabled": "0",
                    "GstRender.FullscreenMode": "1",
                },
            )
            prof_path.write_bytes(patched_bytes)
            modified_files.append(prof_path)
            log(f"    [ConfigPatcher] Updated Frostbite profile: {prof_path.name} (Subtitles=1, AudioID={fb_audio_id}, Borderless=1)")

        if is_frostbite:
            user_cfg = self.game_dir / "user.cfg"
            self._backup_config_file(user_cfg)
            existing_cfg = user_cfg.read_text(encoding="utf-8", errors="replace") if user_cfg.is_file() else ""
            cfg_lines = [
                ln for ln in existing_cfg.splitlines()
                if not ln.strip().lower().startswith(("ui.drawenable", "window.borders", "renderdevice.fullscreen"))
            ]
            cfg_lines.extend([
                "UI.DrawEnable 1",
                "Window.Borders 0",
            ])
            user_cfg.write_text("\n".join(cfg_lines) + "\n", encoding="utf-8")
            modified_files.append(user_cfg)
            log(f"    [ConfigPatcher] Updated Frostbite config: {user_cfg.name} (UI.DrawEnable=1, Borderless=ON)")

            # Also update Origin / EA locale config if present
            for xml_path in configs["installer_xml"]:
                self._backup_config_file(xml_path)
                xml_txt = xml_path.read_text(encoding="utf-8", errors="replace")
                xml_updated = re.sub(
                    r"(<locale[^>]*>)([^<]+)(</locale>)",
                    rf"\g<1>{fb_locale}\g<3>",
                    xml_txt,
                    count=1,
                    flags=re.IGNORECASE,
                )
                if xml_updated != xml_txt:
                    xml_path.write_text(xml_updated, encoding="utf-8")
                    modified_files.append(xml_path)

        # 3. Patch Steam / EA / Emulator INI files
        for ini_path in configs["steam_ini"]:
            self._backup_config_file(ini_path)
            existing = ini_path.read_text(encoding="utf-8", errors="replace")
            section = "Settings"
            for sec_cand in ("Settings", "Main", "Steam", "Language", "Origin"):
                if f"[{sec_cand.lower()}]" in existing.lower():
                    section = sec_cand
                    break
            updated = self._update_ini_keys(
                existing,
                section,
                {
                    "Language": steam_sub,
                    "AudioLanguage": steam_audio,
                    "SubtitlesLanguage": steam_sub,
                    "Locale": fb_locale,
                },
            )
            ini_path.write_text(updated, encoding="utf-8")
            modified_files.append(ini_path)
            log(f"    [ConfigPatcher] Updated Steam/Launcher config: {ini_path.name} (Audio={steam_audio}, Text={steam_sub})")

        for txt_path in configs["steam_txt"]:
            self._backup_config_file(txt_path)
            txt_path.write_text(f"{steam_sub}\n", encoding="utf-8")
            modified_files.append(txt_path)
            log(f"    [ConfigPatcher] Updated {txt_path.name} -> {steam_sub}")

        # 4. Patch Unreal Engine INI files (preserving existing GameUserSettings without wiping user saves)
        subprojects = find_unreal_subprojects(self.game_dir)
        is_unreal_game = (
            (self.game_dir / "Engine").is_dir()
            or bool(subprojects)
            or (self.game_dir / "pakstore.json").is_file()
            or any(self.game_dir.glob("*.utoc"))
            or any(self.game_dir.glob("*.pak"))
        )
        unreal_targets = list(configs["unreal_ini"])
        if is_unreal_game and not unreal_targets:
            sub_proj = subprojects[0] if subprojects else self.game_dir
            for ini_name in ("GameUserSettings.ini", "Engine.ini"):
                default_ue_cfg = sub_proj / "Saved" / "Config" / "Windows" / ini_name
                default_ue_cfg.parent.mkdir(parents=True, exist_ok=True)
                unreal_targets.append(default_ue_cfg)

        for ini_path in unreal_targets:
            self._backup_config_file(ini_path)
            existing = ini_path.read_text(encoding="utf-8", errors="replace") if ini_path.is_file() else ""
            intl_updates = {
                "Culture": primary_sub_lang,
                "Language": primary_sub_lang,
                "AudioCulture": effective_audio,
            }
            updated = self._update_ini_keys(existing, "Internationalization", intl_updates)
            updated = self._update_ini_keys(
                updated,
                "/Script/Engine.GameUserSettings",
                {
                    "bSubtitlesEnabled": "True",
                    "AudioLanguage": effective_audio,
                    "SubtitleLanguage": primary_sub_lang,
                    "FullscreenMode": "1",
                },
            )
            ini_path.parent.mkdir(parents=True, exist_ok=True)
            ini_path.write_text(updated, encoding="utf-8")
            modified_files.append(ini_path)
            log(f"    [ConfigPatcher] Updated Unreal config: {ini_path.name} (Audio={effective_audio}, Subtitles={primary_sub_lang})")

        # 5. Always record active audio & subtitle selection in .dualsub_journal.json
        journal = self._load_journal()
        journal["active_config"] = {
            "audio_lang": effective_audio,
            "audio_culture": audio_culture,
            "primary_sub_lang": primary_sub_lang,
            "secondary_sub_lang": secondary_sub_lang,
            "sub_culture": sub_culture,
            "static_background_free": True,
        }
        self._save_journal(journal)

        return modified_files

    def restore_game_configs(self, log=print) -> int:
        """Restore all modified configuration files to their exact original pre-DualTitle state."""
        journal = self._load_journal()
        backups: Dict[str, Dict[str, Any]] = journal.get("config_backups", {})
        restored_count = 0

        for path_str, info in list(backups.items()):
            p = Path(path_str)
            try:
                if info.get("existed", True):
                    p.parent.mkdir(parents=True, exist_ok=True)
                    if "hex" in info:
                        p.write_bytes(bytes.fromhex(info["hex"]))
                    else:
                        p.write_text(info.get("content", ""), encoding="utf-8")
                    log(f"    [ConfigPatcher] Restored original config: {p.name}")
                else:
                    if p.is_file():
                        p.unlink()
                        log(f"    [ConfigPatcher] Removed generated config: {p.name}")
                restored_count += 1
            except OSError as exc:
                log(f"    [ConfigPatcher] Warning: Could not restore {p.name}: {exc}")

        journal.pop("config_backups", None)
        journal.pop("active_config", None)
        if journal:
            self._save_journal(journal)
        elif self.journal_path.is_file():
            try:
                self.journal_path.unlink()
            except OSError:
                pass

        return restored_count
