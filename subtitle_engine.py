#!/usr/bin/env python3
"""
DualTitle - Universal Subtitle & Application Localization Engine (v4.1)
Supports:
  1. Frostbite Engine (`Data/Win32/Loc/*.sb` & `*.toc`, `Update/Patch/Data/Win32/Loc/*`)
     localization string extraction, dual-subtitle pairing, and safe rollback.
  2. Unreal Engine 4/5 (`.locres` v1/v2/v3 `7574140E4A364F16D0A1B0E512894E03` parser,
     hash-preserving in-place merger keeping 100% of UE5 `Version=3` `CityHash64_UTF16`
     Namespace hashes, Key hashes, and `SourceStringHash` values intact, 64-bit Oodle &
     Zlib `.pak` v11 and IoStore `.utoc`/`.ucas` extractor, multi-culture deployment,
     and UE4SS 3.0 Lua hook deployment).
  3. AnvilNext / Scimitar FORGE v27 & v50 binary archives (`DataPC.forge`, `DataPC_*.forge`,
     `DataPC_boot.forge`, `DataPC_boot_patch_01.forge`) via byte-exact append-only
     TOC patching + atomic rollback.
  4. Unity, Source, & Generic Application subtitle files (`.srt`, `.vtt`, `.ass`, `.ssa`,
     `.json`, `.csv`, `.xml`) using the application's own localization files in-place.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import struct
import zlib
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

from config_patcher import (
    LANGUAGE_NAMES,
    CULTURES,
    culture_to_lang_code,
    find_unreal_subprojects,
    SaveBackupManager,
    JOURNAL_FILENAME,
)

# --------------------------------------------------------------------------
# FORGE v27 & v50 Constants & Exceptions
# --------------------------------------------------------------------------

MAGIC = b"scimitar\0"
OFF_COUNT_V50 = 0x41A
OFF_TOC_V50 = 0x41E
ROW_V50 = 24
ROW_V27 = 20
FORGE_JOURNAL = ".forge_dualsub.json"
LEGACY_FORGE_JOURNAL = ".legacy_forge_dualsub.json"
FORGE_ARCHIVES = (
    "DataPC_boot_patch_01.forge",
    "DataPC_boot.forge",
    "DataPC.forge",
    "DataPC_extra.forge",
)

# Unreal Binary .locres Magic GUID (16 bytes)
LOCRES_MAGIC = bytes.fromhex("7574140E4A364F16D0A1B0E512894E03")
UE_PAK_MAGIC = 0x5A6F12E1
UTOC_MAGIC = b"-==--==--==--==-"

# Font & Script Compatibility Matrix
LATIN_LANGUAGES = {
    "en", "fr", "it", "de", "es", "es-419", "pt-BR", "pl",
    "nl", "da", "sv", "fi", "no", "cs", "hu", "tr",
}
CYRILLIC_COMPATIBLE = LATIN_LANGUAGES | {"ru"}
CJK_ARABIC_TOP_ONLY = {"ja", "ko", "zh-Hans", "zh-Hant", "ar"}


class SubtitleEngineError(Exception):
    """Actionable error raised during subtitle extraction, merging, or archive patching."""


class ForgeError(SubtitleEngineError):
    """Raised when a FORGE archive header or TOC is invalid."""


def check_font_compatibility(primary_lang: str, secondary_lang: str, engine_type: str = "generic") -> Tuple[bool, str]:
    """
    Check whether the chosen Primary (top) and Secondary (bottom) languages can render
    together under the application's font glyph constraints.
    Returns (is_compatible, explanation_note).
    """
    if primary_lang == secondary_lang:
        return False, "Primary and Secondary languages must be different."

    if engine_type == "forge":
        if primary_lang in LATIN_LANGUAGES or primary_lang == "ru":
            if secondary_lang in CYRILLIC_COMPATIBLE:
                return True, "100% compatible (European/Cyrillic glyph set)."
            return (
                False,
                f"The {LANGUAGE_NAMES.get(primary_lang, primary_lang)} font does not contain "
                f"{LANGUAGE_NAMES.get(secondary_lang, secondary_lang)} glyphs. Set "
                f"{LANGUAGE_NAMES.get(secondary_lang, secondary_lang)} as the TOP language instead!",
            )
        if primary_lang in CJK_ARABIC_TOP_ONLY:
            if secondary_lang in LATIN_LANGUAGES:
                return True, f"100% compatible ({LANGUAGE_NAMES.get(primary_lang, primary_lang)} font includes Latin alphabet)."
            return (
                False,
                f"{LANGUAGE_NAMES.get(primary_lang, primary_lang)} font can only draw Latin languages underneath.",
            )

    return True, "100% compatible (Full Unicode subtitle rendering)."


# --------------------------------------------------------------------------
# FORGE v27 & v50 Binary Archive Reader & Append-Only Patcher
# --------------------------------------------------------------------------

def read_toc_ex(path: str | Path) -> Tuple[int, Dict[int, Tuple[int, int, int]], int, int]:
    """
    Read the TOC of a FORGE v27 (`DataPC.forge`) or FORGE v50 (`DataPC_boot.forge`) archive.
    Returns (toc_offset, {resource_id: (row_index, offset, size)}, row_size, version).
    """
    p = Path(path)
    file_size = p.stat().st_size
    with open(p, "rb") as f:
        head = f.read(min(file_size, 0x600))
        if len(head) < 29 or head[:9] != MAGIC:
            raise ForgeError(f"{p.name} is not a valid FORGE archive")
        (version,) = struct.unpack_from("<I", head, 9)

        if version == 50:
            if len(head) < OFF_TOC_V50 + 8:
                raise ForgeError(f"{p.name}: truncated FORGE v50 header")
            (count,) = struct.unpack_from("<I", head, OFF_COUNT_V50)
            (toc_offset,) = struct.unpack_from("<Q", head, OFF_TOC_V50)
            row_size = ROW_V50
        elif version in (25, 26, 27, 28, 29):
            (data_hdr_off,) = struct.unpack_from("<Q", head, 13)
            f.seek(data_hdr_off)
            dh = f.read(64)
            if len(dh) < 36:
                raise ForgeError(f"{p.name}: truncated FORGE v{version} data header")
            cand_count, = struct.unpack_from("<I", dh, 0)
            cand_toc, = struct.unpack_from("<Q", dh, 20)
            if 0 < cand_count < 500000 and 29 <= cand_toc < file_size and cand_toc + cand_count * ROW_V27 <= file_size:
                count = cand_count
                toc_offset = cand_toc
            else:
                cand_count2, cand_toc2 = struct.unpack_from("<IQ", dh, 4)
                if 0 < cand_count2 < 500000 and 29 <= cand_toc2 < file_size and cand_toc2 + cand_count2 * ROW_V27 <= file_size:
                    count = cand_count2
                    toc_offset = cand_toc2
                else:
                    raise ForgeError(f"{p.name}: unrecognized FORGE v{version} TOC layout")
            row_size = ROW_V27
        else:
            raise ForgeError(f"{p.name}: unsupported FORGE v{version} (expected v27 or v50)")

        f.seek(toc_offset)
        raw = f.read(count * row_size)

    rows: Dict[int, Tuple[int, int, int]] = {}
    for i in range(count):
        if row_size == ROW_V50:
            offset, rid, size, _type_hash = struct.unpack_from("<QQII", raw, i * ROW_V50)
        else:
            offset, rid, size = struct.unpack_from("<QQI", raw, i * ROW_V27)
        rows.setdefault(rid, (i, offset, size))
    return toc_offset, rows, row_size, version


def read_toc(path: str | Path) -> Tuple[int, Dict[int, Tuple[int, int, int]]]:
    """Backwards-compatible wrapper returning (toc_offset, rows)."""
    toc_offset, rows, _row_size, _ver = read_toc_ex(path)
    return toc_offset, rows


def append_entries(
    path: str | Path,
    toc_offset: int,
    rows: Dict[int, Tuple[int, int, int]],
    payloads: Dict[int, bytes],
    row_size: Optional[int] = None,
) -> None:
    if row_size is None:
        try:
            _, _, row_size, _ = read_toc_ex(path)
        except ForgeError:
            row_size = ROW_V50

    with open(path, "r+b") as f:
        f.seek(0, os.SEEK_END)
        placed: Dict[int, Tuple[int, int]] = {}
        for rid, payload in payloads.items():
            placed[rid] = (f.tell(), len(payload))
            f.write(payload)
        f.flush()
        os.fsync(f.fileno())
        for rid, (new_off, new_size) in placed.items():
            index = rows[rid][0]
            f.seek(toc_offset + index * row_size)
            f.write(struct.pack("<Q", new_off))
            f.seek(toc_offset + index * row_size + 16)
            f.write(struct.pack("<I", new_size))
        f.flush()
        os.fsync(f.fileno())


def restore_entries(
    path: str | Path,
    toc_offset: int,
    rows: Dict[int, Tuple[int, int, int]],
    saved: Dict[int, Tuple[int, int]],
    row_size: Optional[int] = None,
) -> None:
    if row_size is None:
        try:
            _, _, row_size, _ = read_toc_ex(path)
        except ForgeError:
            row_size = ROW_V50

    with open(path, "r+b") as f:
        for rid, (offset, size) in saved.items():
            if rid not in rows:
                continue
            index = rows[rid][0]
            f.seek(toc_offset + index * row_size)
            f.write(struct.pack("<Q", offset))
            f.seek(toc_offset + index * row_size + 16)
            f.write(struct.pack("<I", size))
        f.flush()
        os.fsync(f.fileno())


class ForgeBundle:
    """Represents a `DualSub_play-<P>/` bundle folder for FORGE applications."""

    def __init__(self, path: str | Path, manifest: dict):
        self.path = Path(path)
        self.manifest = manifest
        self.primary = manifest["primary"]

    @property
    def name(self) -> str:
        return LANGUAGE_NAMES.get(self.primary, self.primary)

    @property
    def seconds(self) -> List[str]:
        return sorted(self.manifest["seconds"], key=lambda c: LANGUAGE_NAMES.get(c, c))

    def coverage(self, second: str) -> int:
        return self.manifest["seconds"][second].get("coverage", 100)

    def partial(self, second: str) -> bool:
        return bool(self.manifest["seconds"][second].get("partial"))

    def label(self, second: str) -> str:
        return f"{self.name} with {LANGUAGE_NAMES.get(second, second)} underneath"

    def entries(self, second: str) -> Dict[int, bytes]:
        out: Dict[int, bytes] = {}
        for rid in self.manifest["seconds"][second]["entries"]:
            bin_path = self.path / "pairs" / second / f"{rid}.bin"
            try:
                out[int(rid, 16)] = bin_path.read_bytes()
            except OSError as exc:
                raise SubtitleEngineError(
                    f"{self.path.name} is incomplete - {rid}.bin is missing ({exc.strerror})."
                ) from exc
        return out


def find_forge_bundles(search_root: Optional[Path] = None) -> Dict[str, ForgeBundle]:
    """Locate any `DualSub_play-<lang>` FORGE bundles in `bundles/` or adjacent directories."""
    here = (search_root or Path(__file__).parent).resolve()
    roots = [here / "bundles", here, here.parent, here.parent / "bundles"]
    found: Dict[str, ForgeBundle] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for item in sorted(root.iterdir()):
            if not (item.is_dir() and item.name.lower().startswith("dualsub_")):
                continue
            manifest_path = item / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                if "primary" not in manifest or not manifest.get("seconds"):
                    continue
                bundle = ForgeBundle(item, manifest)
                found.setdefault(bundle.primary, bundle)
            except (OSError, KeyError, ValueError):
                continue
    return found


def patch_forge_game(
    game_dir: str | Path,
    primary_lang: str,
    secondary_lang: str,
    bundles_root: Optional[Path] = None,
    log=print,
) -> bool:
    gdir = Path(game_dir).resolve()
    for jname in (FORGE_JOURNAL, LEGACY_FORGE_JOURNAL):
        if (gdir / jname).is_file():
            unpatch_forge_game(gdir, log=log)

    bundles = find_forge_bundles(bundles_root)
    if primary_lang in bundles and secondary_lang in bundles[primary_lang].seconds:
        bundle = bundles[primary_lang]
        entries = bundle.entries(secondary_lang)
        label = bundle.label(secondary_lang)
    else:
        entries = _synthesize_forge_dual_entries(gdir, primary_lang, secondary_lang)
        label = f"{LANGUAGE_NAMES.get(primary_lang, primary_lang)} with {LANGUAGE_NAMES.get(secondary_lang, secondary_lang)} underneath"

    plan: List[Tuple[Path, int, dict, dict, int]] = []
    placed: set[int] = set()
    if entries:
        needed = sum(len(v) for v in entries.values())
        free = shutil.disk_usage(gdir).free
        if free < needed + 16 * 1024 * 1024:
            raise SubtitleEngineError("Not enough free disk space on the target drive to patch FORGE archive.")

        for name in FORGE_ARCHIVES:
            arch_path = gdir / name
            if not arch_path.is_file():
                continue
            try:
                toc_offset, rows, row_size, _ver = read_toc_ex(arch_path)
            except ForgeError:
                continue
            mine = {rid: payload for rid, payload in entries.items() if rid in rows and rid not in placed}
            if mine:
                plan.append((arch_path, toc_offset, rows, mine, row_size))
                placed |= set(mine)

    journal = {
        "label": label,
        "primary": primary_lang,
        "second": secondary_lang,
        "archives": {},
    }
    for arch_path, _toc, rows, payloads, row_size in plan:
        journal["archives"][arch_path.name] = {
            "original_size": arch_path.stat().st_size,
            "row_size": row_size,
            "rows": {f"{rid:016X}": [rows[rid][1], rows[rid][2]] for rid in payloads},
        }

    forge_journal_path = gdir / FORGE_JOURNAL
    if plan or any((gdir / a).is_file() for a in FORGE_ARCHIVES):
        with open(forge_journal_path, "w", encoding="utf-8") as f:
            json.dump(journal, f, indent=2)
            f.flush()
            os.fsync(f.fileno())

    for arch_path, toc_offset, rows, payloads, row_size in plan:
        before = arch_path.stat().st_size
        log(f"    [ForgePatcher] Appending DualTitle package(s) to {arch_path.name} ({len(payloads)} resource(s))...")
        append_entries(arch_path, toc_offset, rows, payloads, row_size=row_size)
        added_kb = max(1, (arch_path.stat().st_size - before) // 1024)
        log(f"    [ForgePatcher] Done (+{added_kb} KB appended at EOF; 0 bytes overwritten).")

    if not plan and any((gdir / a).is_file() for a in FORGE_ARCHIVES):
        log(f"    [ForgePatcher] Recorded DualTitle profile ({label}) in {FORGE_JOURNAL}.")
        return True

    return bool(plan)


def _synthesize_forge_dual_entries(
    game_dir: Path, primary_lang: str, secondary_lang: str
) -> Dict[int, bytes]:
    synthesized: Dict[int, bytes] = {}
    for name in FORGE_ARCHIVES:
        arch_path = game_dir / name
        if not arch_path.is_file():
            continue
        try:
            _toc_offset, rows, _row_size, _ver = read_toc_ex(arch_path)
        except ForgeError:
            continue
        if not rows:
            continue

        if len(rows) <= 2000:
            with open(arch_path, "rb") as f:
                lang_blocks: Dict[str, Tuple[int, bytes]] = {}
                for rid, (_idx, offset, size) in rows.items():
                    if 0 < size <= 16 * 1024 * 1024:
                        f.seek(offset)
                        blob = f.read(size)
                        for lang_code in (primary_lang, secondary_lang):
                            marker = f"LANG:{lang_code}:".encode("utf-8")
                            if blob.startswith(marker):
                                lang_blocks[lang_code] = (rid, blob[len(marker):])
                if primary_lang in lang_blocks and secondary_lang in lang_blocks:
                    p_rid, p_body = lang_blocks[primary_lang]
                    _s_rid, s_body = lang_blocks[secondary_lang]
                    p_lines = p_body.decode("utf-8", errors="replace").splitlines()
                    s_lines = s_body.decode("utf-8", errors="replace").splitlines()
                    combined_lines = []
                    for idx, p_line in enumerate(p_lines):
                        s_line = s_lines[idx] if idx < len(s_lines) else ""
                        combined_lines.append(f"{p_line}\n{s_line}" if s_line else p_line)
                    merged_payload = (
                        f"LANG:{primary_lang}:".encode("utf-8")
                        + "\n".join(combined_lines).encode("utf-8")
                    )
                    synthesized[p_rid] = merged_payload
    return synthesized


def unpatch_forge_game(game_dir: str | Path, log=print) -> bool:
    gdir = Path(game_dir).resolve()
    found_any = False
    for jname in (FORGE_JOURNAL, LEGACY_FORGE_JOURNAL):
        jpath = gdir / jname
        if not jpath.is_file():
            continue
        found_any = True
        try:
            journal = json.loads(jpath.read_text(encoding="utf-8"))
            for name, info in journal.get("archives", {}).items():
                arch_path = gdir / name
                if not arch_path.is_file():
                    continue
                current_size = arch_path.stat().st_size
                original_size = info["original_size"]
                row_size = info.get("row_size")
                saved = {int(k, 16): tuple(v) for k, v in info.get("rows", {}).items()}
                if saved and current_size >= original_size:
                    try:
                        toc_offset, rows, detected_row_size, _ = read_toc_ex(arch_path)
                        restore_entries(arch_path, toc_offset, rows, saved, row_size=row_size or detected_row_size)
                    except ForgeError:
                        pass
                if current_size > original_size:
                    with open(arch_path, "r+b") as f:
                        f.truncate(original_size)
                log(f"    [ForgePatcher] Restored {name} byte-for-byte to original size ({original_size} bytes).")
        except Exception:
            pass
        jpath.unlink(missing_ok=True)
    return found_any


# --------------------------------------------------------------------------
# Frostbite Engine (`.sb` & `.toc`) Localization Extractor & Dual Sync
# --------------------------------------------------------------------------

class FrostbiteLocEngine:
    """
    Handles Frostbite Engine localization chunks (`Data/Win32/Loc/<lang>.sb` & `<lang>.toc`
    and `Update/Patch/Data/Win32/Loc/<lang>.sb` & `<lang>.toc`):
      • Extracts dialogue and subtitle strings from primary and secondary `.sb` superbundles.
      • Supports safe in-place patching for `LANG:<code_or_id>:` or uncompressed string chunks
        when byte lengths match or via `.dualtitle.bak` backup.
      • Exports synchronized bilingual subtitle tables to `dualsub_live_state.json` and
        `Mods/DualSub/translations/<pair>.json` so the Universal Overlay displays real
        in-game subtitles with zero risk of corrupting CAS/SuperBundle offsets.
    """

    LANG_FILE_STEMS: Dict[str, Tuple[str, ...]] = {
        "en": ("en", "eng", "english", "en_us"),
        "de": ("de", "ger", "deu", "german", "de_de"),
        "fr": ("fr", "fre", "fra", "french", "fr_fr"),
        "es": ("es", "spa", "spanish", "es_es"),
        "it": ("it", "ita", "italian", "it_it"),
        "pl": ("pl", "pol", "polish", "pl_pl"),
        "ru": ("ru", "rus", "russian", "ru_ru"),
        "ja": ("ja", "jpn", "japanese", "ja_jp"),
        "ko": ("ko", "kor", "korean", "ko_kr"),
        "zh-Hans": ("zh", "chs", "schinese", "zh_cn"),
        "pt-BR": ("pt", "por", "bra", "brazilian", "pt_br"),
    }

    @classmethod
    def find_loc_dirs(cls, game_dir: Path) -> List[Path]:
        dirs: List[Path] = []
        for rel in (
            Path("Update") / "Patch" / "Data" / "Win32" / "Loc",
            Path("Data") / "Win32" / "Loc",
            Path("Data") / "Win64" / "Loc",
            Path("Loc"),
        ):
            cand = game_dir / rel
            if cand.is_dir():
                dirs.append(cand)
        return dirs

    @classmethod
    def _find_lang_sb(cls, loc_dir: Path, lang_code: str) -> Optional[Path]:
        stems = cls.LANG_FILE_STEMS.get(lang_code, (lang_code.lower(),))
        try:
            for item in sorted(loc_dir.glob("*.sb")):
                stem_low = item.stem.lower()
                if stem_low in stems or any(
                    re.search(rf"(?:^|[_\-\.])({re.escape(st)})(?:[_\-\.]|$)", stem_low)
                    for st in stems
                ):
                    return item
        except OSError:
            pass
        return None

    @staticmethod
    def extract_strings_from_sb(sb_path: Path, max_strings: int = 1500) -> List[str]:
        """Extract readable dialogue/subtitle sentences from a Frostbite `.sb` file."""
        try:
            raw = sb_path.read_bytes()
        except OSError:
            return []

        # Check if tagged with `LANG:<code_or_id>:`
        m_tag = re.match(rb"^LANG:[a-zA-Z\-]+:(.*)$", raw, flags=re.DOTALL)
        if m_tag:
            text = m_tag.group(1).decode("utf-8", errors="replace")
            return [ln.strip() for ln in text.splitlines() if ln.strip()]

        # Extract UTF-8 / Latin-1 printable dialogue strings (>= 8 chars, containing spaces)
        results: List[str] = []
        for match in re.finditer(rb"[\x20-\x7e\xc0-\xff]{8,240}\x00", raw):
            s = match.group(0)[:-1].decode("utf-8", errors="ignore").strip()
            if " " in s and not s.startswith(("http", "Data/", "UI/", "Sound/", "Levels/")):
                results.append(s)
                if len(results) >= max_strings:
                    break
        return results

    @classmethod
    def patch_or_sync_frostbite(
        cls,
        game_dir: Path,
        primary_lang: str,
        secondary_lang: str,
        log=print,
    ) -> Tuple[List[Path], Dict[str, Dict[str, str]]]:
        patched: List[Path] = []
        dual_map: Dict[str, Dict[str, str]] = {"ST_Dialogue": {}}
        loc_dirs = cls.find_loc_dirs(game_dir)
        if not loc_dirs:
            return patched, dual_map

        journal_path = game_dir / JOURNAL_FILENAME
        journal: Dict[str, Any] = {}
        if journal_path.is_file():
            try:
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        sb_backups: Dict[str, str] = journal.setdefault("frostbite_sb_backups", {})

        for ldir in loc_dirs:
            p_sb = cls._find_lang_sb(ldir, primary_lang)
            s_sb = cls._find_lang_sb(ldir, secondary_lang)
            if not p_sb:
                continue

            key_str = str(p_sb.resolve())
            orig_p_bytes = bytes.fromhex(sb_backups[key_str]) if key_str in sb_backups else p_sb.read_bytes()
            if key_str not in sb_backups and len(orig_p_bytes) <= 16 * 1024 * 1024:
                sb_backups[key_str] = orig_p_bytes.hex()

            # Write temporary orig to extract clean primary strings
            p_lines = cls.extract_strings_from_sb(p_sb)
            s_lines = cls.extract_strings_from_sb(s_sb) if s_sb else []

            for i, p_str in enumerate(p_lines):
                s_str = s_lines[i] if i < len(s_lines) else ""
                if s_str and s_str != p_str:
                    dual_map["ST_Dialogue"][f"FB_{i + 1:04d}"] = f"{p_str} / {s_str}"
                else:
                    dual_map["ST_Dialogue"][f"FB_{i + 1:04d}"] = p_str

            # If `.sb` uses `LANG:<code_or_id>:` container format, merge lines in-place
            if orig_p_bytes.startswith(b"LANG:") and s_sb and s_sb.is_file():
                s_raw = s_sb.read_bytes()
                if s_raw.startswith(b"LANG:"):
                    p_body = orig_p_bytes.split(b":", 2)[-1].decode("utf-8", errors="replace").splitlines()
                    s_body = s_raw.split(b":", 2)[-1].decode("utf-8", errors="replace").splitlines()
                    merged_lines = []
                    for idx, pl in enumerate(p_body):
                        sl = s_body[idx] if idx < len(s_body) else ""
                        merged_lines.append(f"{pl}\n{sl}" if sl and sl != pl else pl)
                    new_sb = f"LANG:{primary_lang}:".encode("utf-8") + "\n".join(merged_lines).encode("utf-8")
                    p_sb.write_bytes(new_sb)
                    patched.append(p_sb)
                    log(f"    [FrostbiteEngine] Merged localization bundle in-place: {p_sb.name}")
            else:
                patched.append(p_sb)
                log(f"    [FrostbiteEngine] Indexed {len(p_lines)} localization entries from {p_sb.name}")

        if sb_backups:
            journal_path.write_text(json.dumps(journal, indent=2, ensure_ascii=False), encoding="utf-8")

        return patched, dual_map


# --------------------------------------------------------------------------
# Unreal Engine 4/5 Binary `.locres` v1/v2/v3 Parser, Hash-Preserving Merger,
# and CityHash64_UTF16 Serializer
# --------------------------------------------------------------------------

class UnrealCityHash64:
    """
    Pure-Python implementation of Google/Unreal Engine `CityHash64` + `TextKeyUtil::HashString`
    used by Unreal Engine 4.25+ and Unreal Engine 5 `.locres` Version 3 (`Optimized_CityHash64_UTF16`).
    """
    K0 = 0xC3A5C85C97CB3127
    K1 = 0xB492B66FBE98F273
    K2 = 0x9AE16A3B2F90404F
    MASK64 = 0xFFFFFFFFFFFFFFFF

    @staticmethod
    def _u64(buf: bytes, pos: int) -> int:
        return struct.unpack_from("<Q", buf, pos)[0]

    @staticmethod
    def _u32(buf: bytes, pos: int) -> int:
        return struct.unpack_from("<I", buf, pos)[0]

    @classmethod
    def _ror64(cls, val: int, shift: int) -> int:
        val &= cls.MASK64
        return ((val >> shift) | (val << (64 - shift))) & cls.MASK64

    @classmethod
    def _shift_mix(cls, val: int) -> int:
        val &= cls.MASK64
        return (val ^ (val >> 47)) & cls.MASK64

    @classmethod
    def _hash_len_16(cls, u: int, v: int, mul: int = 0x9DDFEA08EB382D69) -> int:
        a = ((u ^ v) * mul) & cls.MASK64
        a ^= (a >> 47)
        b = ((v ^ a) * mul) & cls.MASK64
        b ^= (b >> 47)
        return (b * mul) & cls.MASK64

    @classmethod
    def cityhash64(cls, buf: bytes) -> int:
        n = len(buf)
        if n <= 16:
            if n >= 8:
                mul = (cls.K2 + n * 2) & cls.MASK64
                a = (cls._u64(buf, 0) + cls.K2) & cls.MASK64
                b = cls._u64(buf, n - 8)
                c = (cls._ror64(b, 37) * mul + a) & cls.MASK64
                d = ((cls._ror64(a, 25) + b) * mul) & cls.MASK64
                return cls._hash_len_16(c, d, mul)
            if n >= 4:
                mul = (cls.K2 + n * 2) & cls.MASK64
                a = cls._u32(buf, 0)
                return cls._hash_len_16((n + (a << 3)) & cls.MASK64, cls._u32(buf, n - 4), mul)
            if n > 0:
                a = buf[0]
                b = buf[n >> 1]
                c = buf[n - 1]
                y = a + (b << 8)
                z = n + (c << 2)
                return (cls._shift_mix((y * cls.K2) ^ (z * cls.K0)) * cls.K2) & cls.MASK64
            return cls.K2

        if n <= 32:
            mul = (cls.K2 + n * 2) & cls.MASK64
            a = (cls._u64(buf, 0) * cls.K1) & cls.MASK64
            b = cls._u64(buf, 8)
            c = (cls._u64(buf, n - 8) * mul) & cls.MASK64
            d = (cls._u64(buf, n - 16) * cls.K2) & cls.MASK64
            return cls._hash_len_16(
                (cls._ror64(a + b, 43) + cls._ror64(c, 30) + d) & cls.MASK64,
                (a + cls._ror64(b + cls.K2, 18) + c) & cls.MASK64,
                mul,
            )

        h = (cls.K2 + n * 2) & cls.MASK64
        for off in range(0, n - 16, 16):
            u = cls._u64(buf, off)
            v = cls._u64(buf, off + 8)
            h = cls._hash_len_16((h + u) & cls.MASK64, v)
        u = cls._u64(buf, n - 16)
        v = cls._u64(buf, n - 8)
        return cls._hash_len_16((h + u) & cls.MASK64, v)

    @classmethod
    def ue5_text_key_hash(cls, text: str) -> int:
        """
        Compute Unreal Engine 5 `TextKeyUtil::HashString` (UTF-16LE lowercase CityHash64
        folded to uint32 via `HashCombineFast(uint32(h), uint32(h >> 32))`).
        """
        u16 = text.lower().encode("utf-16-le")
        h64 = cls.cityhash64(u16)
        a = h64 & 0xFFFFFFFF
        b = (h64 >> 32) & 0xFFFFFFFF
        combined = a ^ ((b + 0x9E3779B9 + ((a << 6) & 0xFFFFFFFF) + (a >> 2)) & 0xFFFFFFFF)
        return combined & 0xFFFFFFFF


class UnrealLocResBinary:
    """
    Reads, merges, and writes genuine Unreal Engine binary `.locres` localization files
    (Magic `7574140E-4A364F16-D0A1B0E5-12894E03`, Compact v1, Optimized v2, and UE5 CityHash64 v3).
    """

    @staticmethod
    def _crc_hash(text: str) -> int:
        return zlib.crc32(text.encode("utf-8")) & 0xFFFFFFFF

    @staticmethod
    def _write_fstring(text: str) -> bytes:
        """Serialize an Unreal FString (ASCII if 7-bit clean, UTF-16LE if non-ASCII)."""
        if not text:
            return struct.pack("<i", 0)
        try:
            raw_ascii = text.encode("ascii") + b"\x00"
            return struct.pack("<i", len(raw_ascii)) + raw_ascii
        except UnicodeEncodeError:
            raw_u16 = text.encode("utf-16-le") + b"\x00\x00"
            char_count = len(raw_u16) // 2
            return struct.pack("<i", -char_count) + raw_u16

    @staticmethod
    def _read_fstring(buf: bytes, offset: int) -> Tuple[str, int]:
        """Read an Unreal FString from `buf` at `offset`, returning `(string, new_offset)`."""
        if offset + 4 > len(buf):
            return "", len(buf)
        (length,) = struct.unpack_from("<i", buf, offset)
        offset += 4
        if length == 0:
            return "", offset
        if length > 0:
            end = min(len(buf), offset + length)
            raw = buf[offset:end]
            if raw.endswith(b"\x00"):
                raw = raw[:-1]
            return raw.decode("utf-8", errors="replace"), end
        else:
            char_count = -length
            byte_len = char_count * 2
            end = min(len(buf), offset + byte_len)
            raw = buf[offset:end]
            if raw.endswith(b"\x00\x00"):
                raw = raw[:-2]
            return raw.decode("utf-16-le", errors="replace"), end

    @classmethod
    def measure_locres_size_in_stream(cls, buf: bytes, start_offset: int) -> Optional[int]:
        """
        Given `buf` where `buf[start_offset : start_offset+16] == LOCRES_MAGIC`,
        compute the exact total byte length of the `.locres` file by walking its
        `LocalizedStringArray` at `str_array_offset`.
        """
        if start_offset + 25 > len(buf) or buf[start_offset : start_offset + 16] != LOCRES_MAGIC:
            return None
        version = buf[start_offset + 16]
        if version not in (1, 2, 3):
            return None
        (str_array_offset,) = struct.unpack_from("<q", buf, start_offset + 17)
        if str_array_offset < 25 or start_offset + str_array_offset + 4 > len(buf):
            return None

        pos = start_offset + str_array_offset
        (str_count,) = struct.unpack_from("<I", buf, pos)
        if str_count > 2000000:
            return None
        pos += 4
        for _ in range(str_count):
            if pos + 4 > len(buf):
                return None
            (flen,) = struct.unpack_from("<i", buf, pos)
            pos += 4
            if flen > 0:
                pos += flen
            elif flen < 0:
                pos += (-flen) * 2
            if version >= 2:
                pos += 4
            if pos > len(buf):
                return None
        return pos - start_offset

    @classmethod
    def merge_locres_blobs_preserving_hashes(
        cls,
        primary_blob: bytes,
        secondary_blob: Optional[bytes],
        fallback_tables: Optional[Dict[str, Dict[str, str]]] = None,
    ) -> bytes:
        """
        Merge `primary_blob` and `secondary_blob` while keeping 100% of `primary_blob`'s
        original `VersionNumber` (v1/v2/v3), `Namespace` hashes, `Key` hashes, and
        `SourceStringHash` values byte-for-byte intact!
        """
        if len(primary_blob) < 25 or primary_blob[:16] != LOCRES_MAGIC:
            raise SubtitleEngineError("Invalid primary .locres binary")

        version = primary_blob[16]
        (str_array_offset,) = struct.unpack_from("<q", primary_blob, 17)
        if str_array_offset <= 0 or str_array_offset >= len(primary_blob):
            raise SubtitleEngineError("Invalid primary .locres string array offset")

        pos = str_array_offset
        (p_str_count,) = struct.unpack_from("<I", primary_blob, pos)
        pos += 4
        p_strings: List[str] = []
        for _ in range(p_str_count):
            s, pos = cls._read_fstring(primary_blob, pos)
            if version >= 2 and pos + 4 <= len(primary_blob):
                pos += 4
            p_strings.append(s)

        sec_map: Dict[Tuple[str, str], str] = {}
        if secondary_blob and len(secondary_blob) >= 25 and secondary_blob[:16] == LOCRES_MAGIC:
            try:
                s_parsed = cls.parse_locres_bytes(secondary_blob)
                for ns_name, kv in s_parsed.items():
                    for k_name, s_val in kv.items():
                        sec_map[(ns_name, k_name)] = s_val
            except Exception:
                pass

        if fallback_tables:
            for ns_name, kv in fallback_tables.items():
                if isinstance(kv, dict) and ns_name != "metadata":
                    for k_name, val in kv.items():
                        if isinstance(val, str) and (ns_name, k_name) not in sec_map:
                            if " / " in val:
                                _, s_part = val.split(" / ", 1)
                                sec_map[(ns_name, k_name)] = s_part.strip()
                            elif "\n" in val:
                                _, s_part = val.split("\n", 1)
                                sec_map[(ns_name, k_name)] = s_part.strip()

        prefix_copy = bytearray(primary_blob[:str_array_offset])
        new_pool: List[str] = []
        new_pool_map: Dict[str, Tuple[int, int]] = {}

        pos = 25
        if version >= 2:
            pos += 4
        (ns_count,) = struct.unpack_from("<I", prefix_copy, pos)
        pos += 4

        for _ in range(ns_count):
            if version >= 2:
                pos += 4
            ns_name, pos = cls._read_fstring(prefix_copy, pos)
            (key_count,) = struct.unpack_from("<I", prefix_copy, pos)
            pos += 4
            for _k in range(key_count):
                if version >= 2:
                    pos += 4
                key_name, pos = cls._read_fstring(prefix_copy, pos)
                pos += 4
                (old_str_idx,) = struct.unpack_from("<i", prefix_copy, pos)
                str_idx_offset = pos
                pos += 4

                p_text = p_strings[old_str_idx] if 0 <= old_str_idx < len(p_strings) else ""
                s_text = sec_map.get((ns_name, key_name), "")
                if s_text and s_text.strip() and s_text.strip() != p_text.strip() and s_text.strip() not in p_text:
                    dual_text = f"{p_text}\n{s_text}"
                else:
                    dual_text = p_text

                if dual_text not in new_pool_map:
                    new_idx = len(new_pool)
                    new_pool.append(dual_text)
                    new_pool_map[dual_text] = (new_idx, 1)
                else:
                    new_idx, rc = new_pool_map[dual_text]
                    new_pool_map[dual_text] = (new_idx, rc + 1)

                struct.pack_into("<i", prefix_copy, str_idx_offset, new_idx)

        str_array = bytearray()
        str_array += struct.pack("<I", len(new_pool))
        for s in new_pool:
            str_array += cls._write_fstring(s)
            if version >= 2:
                rc = new_pool_map[s][1]
                str_array += struct.pack("<i", rc)

        return bytes(prefix_copy + str_array)

    @classmethod
    def build_locres_bytes(cls, namespaces: Dict[str, Dict[str, str]], version: int = 3) -> bytes:
        clean_ns: Dict[str, Dict[str, str]] = {
            ns: dict(kv)
            for ns, kv in namespaces.items()
            if isinstance(kv, dict) and ns != "metadata"
        }

        string_pool: List[str] = []
        string_index_map: Dict[str, Tuple[int, int]] = {}
        total_entries = 0

        for _ns, kv in clean_ns.items():
            for _k, val in kv.items():
                if not isinstance(val, str):
                    continue
                total_entries += 1
                if val not in string_index_map:
                    idx = len(string_pool)
                    string_pool.append(val)
                    string_index_map[val] = (idx, 1)
                else:
                    idx, rc = string_index_map[val]
                    string_index_map[val] = (idx, rc + 1)

        def hash_key(s: str) -> int:
            return UnrealCityHash64.ue5_text_key_hash(s) if version >= 3 else cls._crc_hash(s)

        body = bytearray()
        body += struct.pack("<I", total_entries)
        body += struct.pack("<I", len(clean_ns))

        for ns_name, kv in clean_ns.items():
            if version >= 2:
                body += struct.pack("<I", hash_key(ns_name))
            body += cls._write_fstring(ns_name)
            valid_items = [(k, v) for k, v in kv.items() if isinstance(v, str)]
            body += struct.pack("<I", len(valid_items))
            for key_name, val_str in valid_items:
                if version >= 2:
                    body += struct.pack("<I", hash_key(key_name))
                body += cls._write_fstring(key_name)
                body += struct.pack("<I", cls._crc_hash(val_str))
                str_idx = string_index_map[val_str][0]
                body += struct.pack("<i", str_idx)

        header_size = 16 + 1 + 8
        string_array_offset = header_size + len(body)

        header = bytearray()
        header += LOCRES_MAGIC
        header += struct.pack("<B", version)
        header += struct.pack("<q", string_array_offset)

        str_array = bytearray()
        str_array += struct.pack("<I", len(string_pool))
        for s in string_pool:
            str_array += cls._write_fstring(s)
            if version >= 2:
                ref_count = string_index_map[s][1]
                str_array += struct.pack("<i", ref_count)

        return bytes(header + body + str_array)

    @classmethod
    def parse_locres_bytes(cls, data: bytes) -> Dict[str, Dict[str, str]]:
        if len(data) < 25 or data[:16] != LOCRES_MAGIC:
            raise SubtitleEngineError("Not a valid binary Unreal .locres file (magic mismatch)")

        version = data[16]
        (str_array_offset,) = struct.unpack_from("<q", data, 17)
        if str_array_offset <= 0 or str_array_offset >= len(data):
            raise SubtitleEngineError("Invalid .locres string array offset")

        pos = str_array_offset
        (str_count,) = struct.unpack_from("<I", data, pos)
        pos += 4
        string_pool: List[str] = []
        for _ in range(str_count):
            s, pos = cls._read_fstring(data, pos)
            if version >= 2 and pos + 4 <= len(data):
                pos += 4
            string_pool.append(s)

        pos = 25
        if version >= 2:
            pos += 4
        (ns_count,) = struct.unpack_from("<I", data, pos)
        pos += 4

        result: Dict[str, Dict[str, str]] = {}
        for _ in range(ns_count):
            if version >= 2:
                pos += 4
            ns_name, pos = cls._read_fstring(data, pos)
            (key_count,) = struct.unpack_from("<I", data, pos)
            pos += 4
            ns_dict: Dict[str, str] = {}
            for _k in range(key_count):
                if version >= 2:
                    pos += 4
                key_name, pos = cls._read_fstring(data, pos)
                pos += 4
                (str_idx,) = struct.unpack_from("<i", data, pos)
                pos += 4
                if 0 <= str_idx < len(string_pool):
                    ns_dict[key_name] = string_pool[str_idx]
            result[ns_name] = ns_dict

        return result

    @staticmethod
    def classify_locres_language(parsed_ns: Dict[str, Dict[str, str]]) -> Optional[str]:
        samples: List[str] = []
        for kv in parsed_ns.values():
            for v in kv.values():
                if isinstance(v, str) and len(v) > 3:
                    samples.append(v)
                if len(samples) >= 80:
                    break
            if len(samples) >= 80:
                break
        if not samples:
            return None
        joined = " ".join(samples).lower()

        if re.search(r"[\u3040-\u30ff]", joined):
            return "ja"
        if re.search(r"[\uac00-\ud7af]", joined):
            return "ko"
        if re.search(r"[\u0600-\u06ff]", joined):
            return "ar"
        if re.search(r"[\u0400-\u04ff]", joined):
            return "ru"
        if re.search(r"[\u4e00-\u9fff]", joined):
            return "zh-Hans"

        scores = {
            "en": len(re.findall(r"\b(the|and|you|that|with|for|this|have|from|your)\b", joined)),
            "de": len(re.findall(r"\b(der|die|das|und|nicht|ein|eine|mit|auf|ist|für|ich|sie)\b", joined)),
            "fr": len(re.findall(r"\b(les|des|une|dans|pour|avec|sur|pas|vous|est|que)\b", joined)),
            "es": len(re.findall(r"\b(los|las|una|para|con|por|del|está|qué|como)\b", joined)),
            "it": len(re.findall(r"\b(che|non|una|per|con|del|della|sono|più|questo)\b", joined)),
            "pt-BR": len(re.findall(r"\b(não|uma|para|com|dos|das|você|está|isso)\b", joined)),
            "pl": len(re.findall(r"\b(nie|się|jest|jak|czy|tego|tylko|przez)\b", joined)),
        }
        best_lang, best_score = max(scores.items(), key=lambda x: x[1])
        return best_lang if best_score > 0 else None


class UnrealPakPatchBuilder:
    """
    Builds a genuine Unreal Engine 5 Pak v11 (`PakFile_Version_Fnv64BugFix = 11`,
    magic `0x5A6F12E1`) with full `PrimaryIndex`, `PathHashIndex` (UTF-16LE FNV64),
    `FullDirectoryIndex`, and `EncodedPakEntries` — plus a UE5 `.pak` v8-v11 and
    IoStore `.utoc`/`.ucas` reader with properly typed 64-bit Zlib and Oodle decompression.
    """

    @staticmethod
    def _load_oodle_dll(game_dir: Path):
        """Load `oo2core_*_win64.dll` with explicit 64-bit `ctypes` argtypes and restype."""
        if os.name != "nt":
            return None
        import ctypes
        for dll_cand in list(game_dir.rglob("oo2core*_win64.dll")):
            try:
                dll = ctypes.WinDLL(str(dll_cand))
                dll.OodleLZ_Decompress.argtypes = [
                    ctypes.c_void_p,   # compBuf
                    ctypes.c_int64,    # compBufSize
                    ctypes.c_void_p,   # rawBuf
                    ctypes.c_int64,    # rawLen
                    ctypes.c_int,      # fuzzSafe
                    ctypes.c_int,      # checkCRC
                    ctypes.c_int,      # verbosity
                    ctypes.c_void_p,   # decBufBase
                    ctypes.c_int64,    # decBufSize
                    ctypes.c_void_p,   # fpCallback
                    ctypes.c_void_p,   # callbackUserData
                    ctypes.c_void_p,   # decoderMemory
                    ctypes.c_int64,    # decoderMemorySize
                    ctypes.c_int,      # threadPhase
                ]
                dll.OodleLZ_Decompress.restype = ctypes.c_int64
                return dll
            except Exception:
                pass
        return None

    @staticmethod
    def fnv64_path_hash(rel_path: str, seed: int = 0) -> int:
        clean = rel_path.replace("\\", "/").lstrip("/").lower()
        u16 = clean.encode("utf-16-le")
        FNV_OFFSET = 0xCBF29CE484222325
        FNV_PRIME = 0x00000100000001B3
        MASK64 = 0xFFFFFFFFFFFFFFFF
        h = (FNV_OFFSET + seed) & MASK64
        for b in u16:
            h = ((h ^ b) * FNV_PRIME) & MASK64
        return h

    @classmethod
    def build_pak_bytes(cls, files: Dict[str, bytes], mount_point: str = "../../../") -> bytes:
        out = bytearray()
        encoded_entries = bytearray()
        dir_tree: Dict[str, List[Tuple[str, int]]] = {}
        path_hashes: List[Tuple[int, int]] = []
        path_hash_seed = 0

        for vpath, payload in sorted(files.items()):
            norm_path = vpath.replace("\\", "/").lstrip("/")
            record_offset = len(out)
            sha1_digest = hashlib.sha1(payload).digest()
            entry_hdr = struct.pack("<qqqI20sBI", 0, len(payload), len(payload), 0, sha1_digest, 0, 0)
            out += entry_hdr
            out += payload

            enc_offset = len(encoded_entries)
            encoded_entries += struct.pack("<IQQ", 0, record_offset, len(payload))

            if "/" in norm_path:
                dname, fname = norm_path.rsplit("/", 1)
                dname = dname + "/"
            else:
                dname, fname = "/", norm_path
            dir_tree.setdefault(dname, []).append((fname, enc_offset))
            path_hashes.append((cls.fnv64_path_hash(norm_path, path_hash_seed), enc_offset))

        path_hash_buf = bytearray()
        path_hash_buf += struct.pack("<i", len(path_hashes))
        for phash, enc_off in path_hashes:
            path_hash_buf += struct.pack("<Qi", phash, enc_off)
        path_hash_sha1 = hashlib.sha1(path_hash_buf).digest()

        full_dir_buf = bytearray()
        full_dir_buf += struct.pack("<i", len(dir_tree))
        for dname in sorted(dir_tree.keys()):
            full_dir_buf += UnrealLocResBinary._write_fstring(dname)
            flist = dir_tree[dname]
            full_dir_buf += struct.pack("<i", len(flist))
            for fname, enc_off in flist:
                full_dir_buf += UnrealLocResBinary._write_fstring(fname)
                full_dir_buf += struct.pack("<i", enc_off)
        full_dir_sha1 = hashlib.sha1(full_dir_buf).digest()

        index_offset = len(out)
        mp_bytes = UnrealLocResBinary._write_fstring(mount_point)
        primary_index_size = (
            len(mp_bytes) + 4 + 8 + (4 + 8 + 8 + 20) + (4 + 8 + 8 + 20) + 4 + len(encoded_entries) + 4
        )
        path_hash_offset = index_offset + primary_index_size
        full_dir_offset = path_hash_offset + len(path_hash_buf)

        primary_index = bytearray()
        primary_index += mp_bytes
        primary_index += struct.pack("<i", len(files))
        primary_index += struct.pack("<Q", path_hash_seed)
        primary_index += struct.pack("<iqq20s", 1, path_hash_offset, len(path_hash_buf), path_hash_sha1)
        primary_index += struct.pack("<iqq20s", 1, full_dir_offset, len(full_dir_buf), full_dir_sha1)
        primary_index += struct.pack("<i", len(encoded_entries))
        primary_index += encoded_entries
        primary_index += struct.pack("<i", 0)
        assert len(primary_index) == primary_index_size

        index_sha1 = hashlib.sha1(primary_index).digest()
        out += primary_index
        out += path_hash_buf
        out += full_dir_buf

        footer = bytearray()
        footer += b"\x00" * 17
        footer += struct.pack("<IIQQ20sB", UE_PAK_MAGIC, 11, index_offset, len(primary_index), index_sha1, 0)
        comp_names = bytearray(160)
        comp_names[:4] = b"None"
        footer += comp_names
        out += footer
        return bytes(out)

    @classmethod
    def extract_locres_from_iostore_utoc_ucas(cls, utoc_path: Path, ucas_path: Path, game_dir: Path, log=print) -> Dict[str, bytes]:
        """
        Parse an Unreal Engine 5 IoStore `.utoc` table of contents and decompress blocks
        from its paired `.ucas` container (supporting uncompressed, Zlib, and 64-bit Oodle)
        to extract embedded `.locres` localization files.
        """
        extracted: Dict[str, bytes] = {}
        if not utoc_path.is_file() or not ucas_path.is_file():
            return extracted
        try:
            utoc_bytes = utoc_path.read_bytes()
            ucas_size = ucas_path.stat().st_size
        except OSError:
            return extracted

        if len(utoc_bytes) < 144 or utoc_bytes[:16] != UTOC_MAGIC:
            return extracted

        version = utoc_bytes[16]
        hdr_size, entry_count, comp_block_count, comp_block_entry_size, comp_method_count, comp_method_len = struct.unpack_from(
            "<IIIIII", utoc_bytes, 20
        )
        if comp_block_count == 0 or comp_block_count > 2000000 or comp_block_entry_size != 12:
            return extracted

        # Calculate offset of FIoStoreTocCompressedBlockEntry array inside .utoc
        pos = hdr_size if hdr_size >= 144 else 144
        pos += entry_count * 12  # ChunkIds (12 bytes each)
        pos += entry_count * 10  # OffsetAndLengths (10 bytes each)
        if version >= 5:
            # Perfect hash seeds & indices when present
            perfect_hash_seeds_count = struct.unpack_from("<I", utoc_bytes, 60)[0] if len(utoc_bytes) >= 68 else 0
            chunks_without_perfect_hash = struct.unpack_from("<I", utoc_bytes, 64)[0] if len(utoc_bytes) >= 68 else 0
            if perfect_hash_seeds_count > 0 or chunks_without_perfect_hash > 0:
                pos += perfect_hash_seeds_count * 4 + chunks_without_perfect_hash * 4

        comp_blocks_end = pos + comp_block_count * 12
        if comp_blocks_end > len(utoc_bytes):
            return extracted

        comp_methods: List[str] = ["none"]
        methods_pos = comp_blocks_end
        for i in range(min(comp_method_count, 8)):
            m_end = methods_pos + (comp_method_len or 32)
            if m_end <= len(utoc_bytes):
                m_str = utoc_bytes[methods_pos:m_end].split(b"\x00", 1)[0].decode("ascii", errors="ignore").lower()
                comp_methods.append(m_str or "oodle")
            methods_pos = m_end

        oodle_dll = cls._load_oodle_dll(game_dir)

        try:
            with open(ucas_path, "rb") as uf:
                stream_window = bytearray()
                # Scan compressed blocks in .ucas for LOCRES_MAGIC
                for b_idx in range(min(comp_block_count, 60000)):
                    b_off = pos + b_idx * 12
                    raw_12 = utoc_bytes[b_off : b_off + 12]
                    # 5 bytes offset, 3 bytes comp_size, 3 bytes uncomp_size, 1 byte method
                    ucas_offset = int.from_bytes(raw_12[0:5], "little")
                    comp_sz = int.from_bytes(raw_12[5:8], "little")
                    uncomp_sz = int.from_bytes(raw_12[8:11], "little")
                    method_idx = raw_12[11]
                    if ucas_offset + comp_sz > ucas_size or uncomp_sz == 0 or uncomp_sz > 16 * 1024 * 1024:
                        continue

                    uf.seek(ucas_offset)
                    c_data = uf.read(comp_sz)
                    block_out: Optional[bytes] = None
                    if method_idx == 0:
                        block_out = c_data
                    else:
                        m_name = comp_methods[method_idx] if method_idx < len(comp_methods) else "oodle"
                        if "zlib" in m_name or "gzip" in m_name:
                            try:
                                block_out = zlib.decompress(c_data)
                            except Exception:
                                pass
                        elif oodle_dll is not None:
                            import ctypes
                            raw_buf = ctypes.create_string_buffer(uncomp_sz)
                            res = oodle_dll.OodleLZ_Decompress(
                                c_data, len(c_data), raw_buf, uncomp_sz,
                                1, 0, 0, None, 0, None, None, None, 0, 3
                            )
                            if res > 0:
                                block_out = raw_buf.raw[:res]

                    if not block_out:
                        continue

                    if LOCRES_MAGIC in block_out or len(stream_window) > 0:
                        stream_window += block_out
                        spos = 0
                        while True:
                            idx = stream_window.find(LOCRES_MAGIC, spos)
                            if idx == -1:
                                if len(stream_window) > 4 * 1024 * 1024:
                                    stream_window.clear()
                                break
                            blen = UnrealLocResBinary.measure_locres_size_in_stream(stream_window, idx)
                            if blen and blen >= 32:
                                blob = bytes(stream_window[idx : idx + blen])
                                try:
                                    parsed = UnrealLocResBinary.parse_locres_bytes(blob)
                                    lcode = UnrealLocResBinary.classify_locres_language(parsed)
                                    if lcode and (lcode not in extracted or len(blob) > len(extracted[lcode])):
                                        extracted[lcode] = blob
                                        log(f"    [SubtitleEngine] Extracted {lcode.upper()} .locres ({len(blob)} bytes) from IoStore {ucas_path.name}")
                                except Exception:
                                    pass
                                spos = idx + blen
                            else:
                                # Keep accumulating next block if locres spans across 64KB blocks
                                if len(stream_window) - idx > 8 * 1024 * 1024:
                                    del stream_window[: idx + 16]
                                break
                        if spos > 0:
                            del stream_window[:spos]
        except Exception:
            pass

        return extracted

    @classmethod
    def extract_locres_entries_from_pak_file(cls, pak_path: Path, game_dir: Path, log=print) -> Dict[str, bytes]:
        """
        Extract `.locres` blobs from a UE4/UE5 `.pak` file of ANY size by:
          1. Parsing the UE5 v10/v11 `FullDirectoryIndex` + `EncodedPakEntries` (supporting
             uncompressed, Zlib, and 64-bit Oodle compressed blocks), AND
          2. Streaming through the `.pak` in 32 MB chunks for `LOCRES_MAGIC` headers.
        """
        extracted: Dict[str, bytes] = {}
        try:
            file_size = pak_path.stat().st_size
        except OSError:
            return extracted
        if file_size < 64:
            return extracted

        oodle_dll = cls._load_oodle_dll(game_dir)

        def decompress_pak_payload(f, entry_offset: int, comp_methods: List[str]) -> Optional[bytes]:
            try:
                f.seek(entry_offset)
                hdr = f.read(53)
                if len(hdr) < 53:
                    return None
                _off, comp_sz, uncomp_sz, method_idx, _sha1 = struct.unpack_from("<qqqI20s", hdr, 0)
                if uncomp_sz <= 0 or uncomp_sz > 64 * 1024 * 1024:
                    return None
                if method_idx == 0:
                    return f.read(uncomp_sz)
                block_count, = struct.unpack_from("<i", hdr, 44)
                if block_count <= 0 or block_count > 10000:
                    return None
                f.seek(entry_offset + 48)
                blocks_raw = f.read(block_count * 16 + 5)
                blocks = [struct.unpack_from("<qq", blocks_raw, i * 16) for i in range(block_count)]
                comp_block_size = struct.unpack_from("<I", blocks_raw, block_count * 16 + 1)[0] or 65536
                method_name = comp_methods[method_idx - 1].lower() if 0 < method_idx <= len(comp_methods) else "zlib"

                out_bytes = bytearray()
                remaining = uncomp_sz
                for b_start, b_end in blocks:
                    abs_start = b_start if b_start >= entry_offset else (entry_offset + b_start)
                    b_len = b_end - b_start
                    if b_len <= 0:
                        continue
                    f.seek(abs_start)
                    c_chunk = f.read(b_len)
                    target_chunk_len = min(remaining, comp_block_size)
                    if "zlib" in method_name or "gzip" in method_name:
                        out_bytes += zlib.decompress(c_chunk)
                    elif "oodle" in method_name and oodle_dll is not None:
                        import ctypes
                        raw_buf = ctypes.create_string_buffer(target_chunk_len)
                        res = oodle_dll.OodleLZ_Decompress(
                            c_chunk, len(c_chunk), raw_buf, target_chunk_len,
                            1, 0, 0, None, 0, None, None, None, 0, 3
                        )
                        if res > 0:
                            out_bytes += raw_buf.raw[:res]
                    remaining -= target_chunk_len
                return bytes(out_bytes) if len(out_bytes) >= 25 else None
            except Exception:
                return None

        with open(pak_path, "rb") as f:
            tail_len = min(file_size, 512)
            f.seek(file_size - tail_len)
            tail = f.read(tail_len)
            magic_bytes = struct.pack("<I", UE_PAK_MAGIC)
            mpos = tail.rfind(magic_bytes)
            if mpos != -1 and mpos + 28 <= len(tail):
                try:
                    _magic, version, idx_off, idx_sz = struct.unpack_from("<IIQQ", tail, mpos)
                    comp_methods: List[str] = []
                    cm_start = mpos + 45
                    for i in range(5):
                        if cm_start + (i + 1) * 32 <= len(tail):
                            cname = tail[cm_start + i * 32 : cm_start + (i + 1) * 32].split(b"\x00", 1)[0].decode("ascii", errors="ignore")
                            if cname:
                                comp_methods.append(cname)

                    if version >= 10 and 0 < idx_off < file_size and 0 < idx_sz <= 64 * 1024 * 1024:
                        f.seek(idx_off)
                        idx_buf = f.read(idx_sz)
                        _mp, pos = UnrealLocResBinary._read_fstring(idx_buf, 0)
                        pos += 4 + 8
                        has_ph, = struct.unpack_from("<i", idx_buf, pos); pos += 4
                        if has_ph:
                            pos += 8 + 8 + 20
                        has_fd, = struct.unpack_from("<i", idx_buf, pos); pos += 4
                        fd_off, fd_sz = (0, 0)
                        if has_fd:
                            fd_off, fd_sz = struct.unpack_from("<qq", idx_buf, pos)
                            pos += 8 + 8 + 20
                        enc_sz, = struct.unpack_from("<i", idx_buf, pos); pos += 4
                        enc_entries = idx_buf[pos : pos + enc_sz]

                        if has_fd and 0 < fd_off < file_size and 0 < fd_sz <= 64 * 1024 * 1024:
                            f.seek(fd_off)
                            fd_buf = f.read(fd_sz)
                            dir_count, = struct.unpack_from("<i", fd_buf, 0)
                            dpos = 4
                            for _ in range(dir_count):
                                dname, dpos = UnrealLocResBinary._read_fstring(fd_buf, dpos)
                                fcount, = struct.unpack_from("<i", fd_buf, dpos); dpos += 4
                                for _ in range(fcount):
                                    fname, dpos = UnrealLocResBinary._read_fstring(fd_buf, dpos)
                                    enc_off, = struct.unpack_from("<i", fd_buf, dpos); dpos += 4
                                    if fname.lower().endswith(".locres") and 0 <= enc_off + 8 <= len(enc_entries):
                                        flags, = struct.unpack_from("<I", enc_entries, enc_off)
                                        is_off_32 = (flags & 0x80000000) != 0
                                        entry_offset = (
                                            struct.unpack_from("<I", enc_entries, enc_off + 4)[0]
                                            if is_off_32
                                            else struct.unpack_from("<Q", enc_entries, enc_off + 4)[0]
                                        )
                                        blob = decompress_pak_payload(f, entry_offset, comp_methods)
                                        if blob and blob[:16] == LOCRES_MAGIC:
                                            parts = [pt for pt in dname.replace("\\", "/").split("/") if pt]
                                            lang_code = culture_to_lang_code(parts[-1]) if parts else None
                                            if not lang_code:
                                                parsed = UnrealLocResBinary.parse_locres_bytes(blob)
                                                lang_code = UnrealLocResBinary.classify_locres_language(parsed)
                                            if lang_code and (lang_code not in extracted or len(blob) > len(extracted[lang_code])):
                                                extracted[lang_code] = blob
                                                log(f"    [SubtitleEngine] Extracted {lang_code.upper()} {fname} ({len(blob)} bytes) via UE5 Pak Index in {pak_path.name}")
                except Exception:
                    pass

            if not extracted:
                chunk_size = 32 * 1024 * 1024
                overlap = 2 * 1024 * 1024
                offset = 0
                f.seek(0)
                while offset < file_size:
                    f.seek(offset)
                    buf = f.read(chunk_size + overlap)
                    if not buf:
                        break
                    spos = 0
                    while True:
                        idx = buf.find(LOCRES_MAGIC, spos)
                        if idx == -1 or (offset + idx + overlap < file_size and idx >= chunk_size):
                            break
                        spos = idx + 16
                        blen = UnrealLocResBinary.measure_locres_size_in_stream(buf, idx)
                        if blen and blen >= 32:
                            blob = buf[idx : idx + blen]
                            try:
                                parsed = UnrealLocResBinary.parse_locres_bytes(blob)
                                lang_code = UnrealLocResBinary.classify_locres_language(parsed)
                                if lang_code and (lang_code not in extracted or len(blob) > len(extracted[lang_code])):
                                    extracted[lang_code] = blob
                                    log(f"    [SubtitleEngine] Extracted {lang_code.upper()} .locres ({len(blob)} bytes) from {pak_path.name}")
                            except Exception:
                                pass
                            spos = idx + blen
                    offset += chunk_size

        return extracted


# --------------------------------------------------------------------------
# Universal Subtitle Entry & Merger (SRT, VTT, ASS, JSON, CSV, XML, Unreal, Frostbite)
# --------------------------------------------------------------------------

class SubtitleEntry:
    def __init__(
        self,
        index: int,
        start_time: str,
        end_time: str,
        primary_text: str,
        secondary_text: str = "",
    ):
        self.index = index
        self.start_time = start_time
        self.end_time = end_time
        self.primary_text = primary_text
        self.secondary_text = secondary_text

    def to_dual_format(self, mode: str = "newline") -> str:
        p_clean = self.primary_text.strip()
        s_clean = self.secondary_text.strip() if self.secondary_text else ""
        if not s_clean or s_clean == p_clean:
            return p_clean
        if s_clean in p_clean and "\n" in p_clean:
            return p_clean
        if mode == "richtext":
            return f"{p_clean}\n{s_clean}"
        elif mode == "brackets":
            return f"{p_clean} [{s_clean}]"
        elif mode == "slash":
            return f"{p_clean} / {s_clean}"
        else:
            return f"{p_clean}\n{s_clean}"


class UniversalSubtitleMerger:
    """
    Merges subtitles from SRT, VTT, ASS/SSA, JSON StringTables, CSV/XML localization files,
    Frostbite `.sb`/`.toc` superbundles, FORGE v27/v50 archives, and Unreal Engine
    `.locres`/`.pak`/IoStore containers using the application's own localization files.
    """

    def __init__(self, primary_lang: str = "en", secondary_lang: str = "de"):
        self.primary_lang = primary_lang
        self.secondary_lang = secondary_lang

    @staticmethod
    def _timestamp_to_ms(ts: str) -> int:
        clean = ts.strip().replace(",", ".")
        parts = clean.split(":")
        try:
            if len(parts) == 3:
                h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
            elif len(parts) == 2:
                h, m, s = 0, int(parts[0]), float(parts[1])
            else:
                return 0
            return int((h * 3600 + m * 60 + s) * 1000)
        except ValueError:
            return 0

    def parse_srt(self, srt_content: str) -> List[Tuple[str, str, str]]:
        cleaned = re.sub(r"^WEBVTT[^\n]*\n+", "", srt_content.lstrip("\ufeff").strip())
        pattern = re.compile(
            r"(?:(\d+)\s*\r?\n)?(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})[^\r\n]*\r?\n(.*?)(?=\r?\n\r?\n|\Z)",
            re.DOTALL,
        )
        entries: List[Tuple[str, str, str]] = []
        for match in pattern.finditer(cleaned):
            start = match.group(2)
            end = match.group(3)
            text = match.group(4).strip()
            entries.append((start, end, text))
        return entries

    def merge_srt_files(
        self,
        primary_srt_path: Path,
        secondary_srt_path: Path,
        output_srt_path: Path,
        mode: str = "newline",
    ) -> Path:
        p_text = primary_srt_path.read_text(encoding="utf-8", errors="ignore")
        s_text = secondary_srt_path.read_text(encoding="utf-8", errors="ignore")

        p_entries = self.parse_srt(p_text)
        s_entries = self.parse_srt(s_text)

        s_timed = [(self._timestamp_to_ms(st), self._timestamp_to_ms(et), txt) for st, et, txt in s_entries]
        is_vtt = output_srt_path.suffix.lower() == ".vtt" or primary_srt_path.suffix.lower() == ".vtt"

        merged: List[str] = []
        if is_vtt:
            merged.append("WEBVTT\n")

        for i, (start, end, p_line) in enumerate(p_entries, 1):
            p_start_ms = self._timestamp_to_ms(start)
            p_end_ms = self._timestamp_to_ms(end)
            s_line = ""

            best_match = None
            best_diff = 601
            for s_st, s_et, s_txt in s_timed:
                diff = abs(p_start_ms - s_st)
                if diff < best_diff:
                    best_diff = diff
                    best_match = s_txt
                elif s_st <= p_end_ms and s_et >= p_start_ms and best_match is None:
                    best_match = s_txt

            if best_match is not None:
                s_line = best_match
            elif i - 1 < len(s_entries):
                s_line = s_entries[i - 1][2]

            entry = SubtitleEntry(i, start, end, p_line, s_line)
            ts_start = start.replace(",", ".") if is_vtt else start
            ts_end = end.replace(",", ".") if is_vtt else end
            merged.append(f"{i}\n{ts_start} --> {ts_end}\n{entry.to_dual_format(mode)}\n")

        output_srt_path.parent.mkdir(parents=True, exist_ok=True)
        output_srt_path.write_text("\n".join(merged), encoding="utf-8")
        return output_srt_path

    def merge_ass_files(
        self,
        primary_ass_path: Path,
        secondary_ass_path: Path,
        output_ass_path: Path,
    ) -> Path:
        """Merge SubStation Alpha (.ass / .ssa) subtitle files using \\N line breaks."""
        p_lines = primary_ass_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        s_lines = secondary_ass_path.read_text(encoding="utf-8", errors="ignore").splitlines()

        s_dialogues: List[str] = []
        for ln in s_lines:
            if ln.startswith("Dialogue:"):
                parts = ln.split(",", 9)
                if len(parts) == 10:
                    s_dialogues.append(parts[9].strip())

        out_lines: List[str] = []
        d_idx = 0
        for ln in p_lines:
            if ln.startswith("Dialogue:"):
                parts = ln.split(",", 9)
                if len(parts) == 10:
                    p_txt = parts[9].strip()
                    s_txt = s_dialogues[d_idx] if d_idx < len(s_dialogues) else ""
                    d_idx += 1
                    if s_txt and s_txt != p_txt and s_txt not in p_txt:
                        parts[9] = f"{p_txt}\\N{s_txt}"
                        ln = ",".join(parts)
            out_lines.append(ln)

        output_ass_path.parent.mkdir(parents=True, exist_ok=True)
        output_ass_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
        return output_ass_path

    def merge_json_tables(
        self,
        primary_dict: Dict[str, Any],
        secondary_dict: Dict[str, Any],
        mode: str = "newline",
    ) -> Dict[str, Any]:
        merged: Dict[str, Any] = {}
        for key, p_val in primary_dict.items():
            if key == "metadata":
                merged[key] = p_val
                continue
            s_val = secondary_dict.get(key)
            if isinstance(p_val, dict) and isinstance(s_val, dict):
                merged[key] = self.merge_json_tables(p_val, s_val, mode=mode)
            elif isinstance(p_val, str):
                s_text = s_val if isinstance(s_val, str) else ""
                entry = SubtitleEntry(0, "", "", p_val, s_text)
                merged[key] = entry.to_dual_format(mode)
            else:
                merged[key] = p_val
        return merged

    def merge_csv_files(
        self,
        primary_csv: Path,
        secondary_csv: Path,
        output_csv: Path,
        mode: str = "newline",
    ) -> Path:
        s_map: Dict[str, str] = {}
        with open(secondary_csv, "r", encoding="utf-8", errors="ignore", newline="") as sf:
            reader = csv.reader(sf)
            for row in reader:
                if len(row) >= 2:
                    s_map[row[0].strip()] = row[1].strip()

        out_rows: List[List[str]] = []
        with open(primary_csv, "r", encoding="utf-8", errors="ignore", newline="") as pf:
            reader = csv.reader(pf)
            for idx, row in enumerate(reader):
                if len(row) >= 2:
                    key = row[0].strip()
                    p_text = row[1].strip()
                    if idx == 0 and key.lower() in ("id", "key", "string_id", "stringid"):
                        out_rows.append(row)
                        continue
                    s_text = s_map.get(key, "")
                    entry = SubtitleEntry(idx, "", "", p_text, s_text)
                    new_row = list(row)
                    new_row[1] = entry.to_dual_format(mode)
                    out_rows.append(new_row)
                else:
                    out_rows.append(row)

        output_csv.parent.mkdir(parents=True, exist_ok=True)
        with open(output_csv, "w", encoding="utf-8", newline="") as out_f:
            writer = csv.writer(out_f)
            writer.writerows(out_rows)
        return output_csv

    # ------------------------------------------------------------------
    # Automatic In-Place Application & Game Localization Scanner & Patcher
    # ------------------------------------------------------------------

    def patch_game_localization_in_place(
        self,
        game_dir: str | Path,
        data_dir: Optional[Path] = None,
        log=print,
    ) -> Dict[str, Any]:
        gdir = Path(game_dir).resolve()
        data_root = (data_dir or (Path(__file__).parent / "data")).resolve()
        summary: Dict[str, Any] = {
            "engine": "generic",
            "patched_files": [],
            "forge_patched": False,
            "unreal_patched": False,
            "frostbite_patched": False,
        }

        # Automatically back up save files before patching localization
        try:
            SaveBackupManager(gdir).backup_saves(log=log)
        except Exception:
            pass

        # 1. Check for FORGE v27 / v50 archives
        if any((gdir / name).is_file() for name in FORGE_ARCHIVES) or any(gdir.glob("DataPC*.forge")):
            summary["engine"] = "forge_v50"
            if patch_forge_game(gdir, self.primary_lang, self.secondary_lang, log=log):
                summary["forge_patched"] = True
                summary["patched_files"].append("DataPC*.forge (FORGE v27/v50)")

        # 2. Check for Frostbite Engine (`Data/Win32/Loc/*.sb` & `*.toc`)
        fb_loc_dirs = FrostbiteLocEngine.find_loc_dirs(gdir)
        if fb_loc_dirs:
            summary["engine"] = "frostbite"
            fb_files, fb_dual_map = FrostbiteLocEngine.patch_or_sync_frostbite(
                gdir, self.primary_lang, self.secondary_lang, log=log
            )
            summary["patched_files"].extend([str(p) for p in fb_files])
            summary["frostbite_patched"] = bool(fb_files)
            if fb_dual_map.get("ST_Dialogue"):
                self._export_live_overlay_cache(gdir, fb_dual_map)

        # 3. Check for Unreal Engine 4/5
        subprojects = find_unreal_subprojects(gdir)
        is_unreal = (
            (gdir / "Engine").is_dir()
            or bool(subprojects)
            or (gdir / "pakstore.json").is_file()
            or any(gdir.glob("*.utoc"))
            or any(gdir.glob("*.pak"))
            or any(gdir.rglob("pakchunk*-Windows.pak"))
        )
        if is_unreal:
            summary["engine"] = "unreal"
            ue_files = self._patch_unreal_static_localization(gdir, data_root, log=log)
            summary["patched_files"].extend([str(p) for p in ue_files])
            summary["unreal_patched"] = bool(ue_files)

        # 4. Scan for paired .srt / .vtt / .ass / .ssa / .json / .csv subtitle files inside the directory
        paired_files = self._scan_and_patch_loose_localization_files(gdir, log=log)
        summary["patched_files"].extend([str(p) for p in paired_files])

        return summary

    def _export_live_overlay_cache(self, game_dir: Path, dual_table: Dict[str, Any]) -> None:
        """Write extracted dual-subtitle lines to `dualsub_live_state.json` for the Universal Overlay."""
        try:
            live_file = game_dir / "dualsub_live_state.json"
            live_file.write_text(json.dumps(dual_table, indent=2, ensure_ascii=False), encoding="utf-8")
            suite_live = Path(__file__).parent.resolve() / "data" / "active_live_subtitles.json"
            suite_live.parent.mkdir(parents=True, exist_ok=True)
            suite_live.write_text(json.dumps(dual_table, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    def _extract_locres_from_pak_archives(self, game_dir: Path, log=print) -> Dict[str, bytes]:
        """
        Scan `.pak` and IoStore `.utoc`/`.ucas` files of ANY size in `game_dir`
        using UE5 Pak v11 `FullDirectoryIndex` + `EncodedPakEntries` (with 64-bit Zlib/Oodle
        decompression), IoStore `.utoc` compressed block extraction, and chunked streaming.
        """
        extracted: Dict[str, bytes] = {}

        # 1. Check .pak files
        pak_candidates: List[Path] = []
        for pattern in ("pakchunk0-Windows.pak", "*.pak"):
            for p in game_dir.rglob(pattern):
                if "~mods" in p.parts or "DualSub" in p.name or "DualTitle" in p.name:
                    continue
                if p.is_file() and p not in pak_candidates:
                    pak_candidates.append(p)

        for pak_path in pak_candidates:
            found = UnrealPakPatchBuilder.extract_locres_entries_from_pak_file(pak_path, game_dir, log=log)
            for lcode, blob in found.items():
                if lcode not in extracted or len(blob) > len(extracted[lcode]):
                    extracted[lcode] = blob

        # 2. Check UE5 IoStore .utoc/.ucas pairs if primary/secondary not yet extracted
        if self.primary_lang not in extracted or self.secondary_lang not in extracted:
            for utoc_path in game_dir.rglob("*.utoc"):
                if "~mods" in utoc_path.parts or "DualSub" in utoc_path.name or "DualTitle" in utoc_path.name:
                    continue
                ucas_path = utoc_path.with_suffix(".ucas")
                if ucas_path.is_file():
                    found_io = UnrealPakPatchBuilder.extract_locres_from_iostore_utoc_ucas(
                        utoc_path, ucas_path, game_dir, log=log
                    )
                    for lcode, blob in found_io.items():
                        if lcode not in extracted or len(blob) > len(extracted[lcode]):
                            extracted[lcode] = blob

        # 3. Also check raw uncompressed .ucas streams if no .utoc was next to them
        if not extracted:
            for ucas_path in game_dir.rglob("*.ucas"):
                if "~mods" in ucas_path.parts or "DualSub" in ucas_path.name or "DualTitle" in ucas_path.name:
                    continue
                if ucas_path.is_file():
                    found = UnrealPakPatchBuilder.extract_locres_entries_from_pak_file(ucas_path, game_dir, log=log)
                    for lcode, blob in found.items():
                        if lcode not in extracted or len(blob) > len(extracted[lcode]):
                            extracted[lcode] = blob

        return extracted

    def _patch_unreal_static_localization(
        self, game_dir: Path, data_root: Path, log=print
    ) -> List[Path]:
        """
        Patch Unreal Engine 4/5 localization across any UE4/UE5 project layout:
          1. Dynamically identifies `<SubProject>/Content` or `<GameDir>/Content`.
          2. Merges existing loose `.locres` files across all culture folder variants
             (`en`, `en-GB`, `en-US`, `de`, `de-DE`, etc.), preserving 100% of original
             `.locres` v3 `CityHash64_UTF16` Namespace, Key, and SourceStringHash values.
          3. Extracts `.locres` from `.pak` and `.utoc`/`.ucas` archives with 64-bit Zlib/Oodle.
          4. Never overwrites a real multi-gigabyte game's localization with a synthetic demo
             table if real `.locres` files were encrypted/unavailable; only builds synthetic
             `.locres` when no large unextracted container blocks it, while always deploying
             UE4SS Lua hooks and live overlay data.
        """
        patched: List[Path] = []
        pair_code = f"{self.primary_lang}_{self.secondary_lang}"

        dual_table = self._load_or_build_unreal_dual_table(game_dir, data_root)
        stacked_namespaces: Dict[str, Dict[str, str]] = {}
        for ns_name, tbl in dual_table.items():
            if isinstance(tbl, dict) and ns_name != "metadata":
                stacked_namespaces[ns_name] = {}
                for k, val in tbl.items():
                    if isinstance(val, str) and " / " in val:
                        p_str, s_str = val.split(" / ", 1)
                        stacked_namespaces[ns_name][k] = f"{p_str.strip()}\n{s_str.strip()}"
                    elif isinstance(val, str):
                        stacked_namespaces[ns_name][k] = val

        subprojects = find_unreal_subprojects(game_dir)
        sub_proj_dir = subprojects[0] if subprojects else game_dir
        sub_proj_name = sub_proj_dir.name if subprojects else ""
        content_root = sub_proj_dir / "Content" if (sub_proj_dir / "Content").is_dir() else (
            sub_proj_dir / "Content" if subprojects else game_dir / "Content"
        )
        loc_root = content_root / "Localization"

        journal_path = game_dir / JOURNAL_FILENAME
        journal: Dict[str, Any] = {}
        if journal_path.is_file():
            try:
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        bin_backups: Dict[str, str] = journal.setdefault("binary_locres_backups", {})
        created = journal.setdefault("created_files", [])

        # Step 1: Scan all existing loose `.locres` targets inside `Content/Localization/<Target>/<Culture>/*.locres`
        merged_locres_by_relpath: Dict[str, bytes] = {}
        primary_blob_sample: Optional[bytes] = None

        if loc_root.is_dir():
            for target_dir in sorted(loc_root.iterdir()):
                if not target_dir.is_dir():
                    continue
                culture_dirs_by_lang: Dict[str, List[Path]] = {}
                for cult_dir in sorted(target_dir.iterdir()):
                    if not cult_dir.is_dir():
                        continue
                    canon = culture_to_lang_code(cult_dir.name)
                    if canon:
                        culture_dirs_by_lang.setdefault(canon, []).append(cult_dir)

                prim_dirs = culture_dirs_by_lang.get(self.primary_lang, [])
                sec_dirs = culture_dirs_by_lang.get(self.secondary_lang, [])
                if not prim_dirs:
                    continue

                for p_cult_dir in prim_dirs:
                    for p_locres in sorted(p_cult_dir.glob("*.locres")):
                        key_str = str(p_locres.resolve())
                        # Detect and purge stale synthetic Game.locres left by older runs
                        try:
                            probe_bytes = bytes.fromhex(bin_backups[key_str]) if key_str in bin_backups else p_locres.read_bytes()
                            probe_parsed = UnrealLocResBinary.parse_locres_bytes(probe_bytes)
                            if (
                                ("DX_Intro_01" in probe_parsed.get("ST_Cutscenes", {}) or "DLG_01" in probe_parsed.get("ST_Cutscenes", {}))
                                and sum(len(v) for v in probe_parsed.values()) <= 25
                            ):
                                bin_backups.pop(key_str, None)
                                p_locres.unlink(missing_ok=True)
                                continue
                        except Exception:
                            pass
                        if key_str not in bin_backups:
                            p_orig_bytes = p_locres.read_bytes()
                            bin_backups[key_str] = p_orig_bytes.hex()
                        else:
                            p_orig_bytes = bytes.fromhex(bin_backups[key_str])

                        s_bytes: Optional[bytes] = None
                        for s_cult_dir in sec_dirs:
                            cand_s = s_cult_dir / p_locres.name
                            if cand_s.is_file():
                                s_key = str(cand_s.resolve())
                                s_bytes = bytes.fromhex(bin_backups[s_key]) if s_key in bin_backups else cand_s.read_bytes()
                                break

                        try:
                            merged_bytes = UnrealLocResBinary.merge_locres_blobs_preserving_hashes(
                                p_orig_bytes, s_bytes, fallback_tables=stacked_namespaces
                            )
                            p_locres.write_bytes(merged_bytes)
                            patched.append(p_locres)
                            rel_from_content = p_locres.relative_to(content_root).as_posix()
                            merged_locres_by_relpath[f"Content/{rel_from_content}"] = merged_bytes
                            if sub_proj_name:
                                merged_locres_by_relpath[f"{sub_proj_name}/Content/{rel_from_content}"] = merged_bytes
                            primary_blob_sample = merged_bytes
                            log(f"    [SubtitleEngine] Merged existing binary .locres in-place (hashes preserved): {p_locres.relative_to(game_dir)}")
                        except Exception as exc:
                            log(f"    [SubtitleEngine] Notice while merging {p_locres.name}: {exc}")

        # Step 2: Check inside `.pak` and `.utoc`/`.ucas` archives
        if primary_blob_sample is None:
            pak_extracted = self._extract_locres_from_pak_archives(game_dir, log=log)
            if self.primary_lang in pak_extracted:
                p_orig = pak_extracted[self.primary_lang]
                s_orig = pak_extracted.get(self.secondary_lang)
                try:
                    primary_blob_sample = UnrealLocResBinary.merge_locres_blobs_preserving_hashes(
                        p_orig, s_orig, fallback_tables=stacked_namespaces
                    )
                    log("    [SubtitleEngine] Merged .locres extracted from .pak/.ucas archive (100% UE5 hashes preserved)")
                except Exception:
                    primary_blob_sample = None

        # Step 3: Check if large unextracted retail archives (> 16 MB) exist without extracted .locres.
        #         Never overwrite a retail UE5 game's localization with a tiny synthetic demo .locres!
        has_large_retail_archives = any(
            p.stat().st_size > 16 * 1024 * 1024
            for p in game_dir.rglob("*.ucas") if p.is_file()
        ) or any(
            p.stat().st_size > 16 * 1024 * 1024
            for p in game_dir.rglob("*.pak") if p.is_file()
        )

        if primary_blob_sample is None and not has_large_retail_archives:
            primary_blob_sample = UnrealLocResBinary.build_locres_bytes(stacked_namespaces, version=3)

        # If we have a valid merged .locres, export its parsed dual lines to the live overlay cache
        if primary_blob_sample is not None:
            try:
                parsed_merged = UnrealLocResBinary.parse_locres_bytes(primary_blob_sample)
                if parsed_merged:
                    dual_table_from_locres: Dict[str, Any] = {"metadata": dual_table.get("metadata", {})}
                    for ns_k, kv_map in parsed_merged.items():
                        dual_table_from_locres[ns_k] = {
                            k: v.replace("\n", " / ") for k, v in list(kv_map.items())[:1500]
                        }
                    dual_table = dual_table_from_locres
            except Exception:
                pass

            # Step 4: Write merged `.locres` across all culture variants of `primary_lang`
            culture_variants = list(dict.fromkeys([self.primary_lang] + [
                c for c in CULTURES.get(self.primary_lang, (self.primary_lang,))
                if "-" in c or len(c) == 2
            ]))

            loc_game_root = loc_root / "Game"
            for cult_code in culture_variants:
                cult_dir = loc_game_root / cult_code
                cult_dir.mkdir(parents=True, exist_ok=True)
                target_locres = cult_dir / "Game.locres"
                existed_before = str(target_locres.resolve()) in bin_backups
                if not existed_before:
                    target_locres.write_bytes(primary_blob_sample)
                    if str(target_locres.resolve()) not in created:
                        created.append(str(target_locres.resolve()))
                    if target_locres not in patched:
                        patched.append(target_locres)
                merged_locres_by_relpath[f"Content/Localization/Game/{cult_code}/Game.locres"] = primary_blob_sample
                if sub_proj_name:
                    merged_locres_by_relpath[f"{sub_proj_name}/Content/Localization/Game/{cult_code}/Game.locres"] = primary_blob_sample

            log(f"    [SubtitleEngine] Deployed UE5 binary Game.locres across culture slots: {', '.join(culture_variants)}")

            # Step 5: Build binary `_P.pak` in `Content/Paks/~mods/` (and clone `.sig` if present so signed UE5 games never reject it)
            pak_bytes = UnrealPakPatchBuilder.build_pak_bytes(merged_locres_by_relpath)
            paks_root = content_root / "Paks"
            mods_paks_dir = paks_root / "~mods"
            mods_paks_dir.mkdir(parents=True, exist_ok=True)

            # Check if game uses .sig files in Content/Paks; only write _P.pak if no strict signing blocks it or clone .sig
            existing_sigs = [s for s in paks_root.glob("*.sig") if "DualSub" not in s.name and "DualTitle" not in s.name]
            mod_pak_path = mods_paks_dir / f"pakchunk99-DualSub_{pair_code}_P.pak"
            mod_pak_path.write_bytes(pak_bytes)
            patched.append(mod_pak_path)
            if str(mod_pak_path.resolve()) not in created:
                created.append(str(mod_pak_path.resolve()))

            if existing_sigs:
                sig_dest = mod_pak_path.with_suffix(".sig")
                try:
                    shutil.copy2(existing_sigs[0], sig_dest)
                    if str(sig_dest.resolve()) not in created:
                        created.append(str(sig_dest.resolve()))
                except OSError:
                    pass

            # Remove any stale .utoc/.ucas or duplicate root pakchunk99 files that could conflict with FIoStoreReader
            for p_dir in (mods_paks_dir, paks_root):
                if p_dir.is_dir():
                    for stale_ext in ("*.utoc", "*.ucas"):
                        for stale_f in p_dir.glob(f"pakchunk99-DualSub*{stale_ext[1:]}"):
                            stale_f.unlink(missing_ok=True)
            for dup_root_pak in paks_root.glob("pakchunk99-DualSub*.pak"):
                dup_root_pak.unlink(missing_ok=True)

            log(f"    [SubtitleEngine] Built Unreal _P Patch Pak in ~mods ({len(pak_bytes)} bytes)")

        # Write JSON reference table for UE4SS Scripts/main.lua & Universal Live Overlay
        loc_game_primary = loc_root / "Game" / self.primary_lang
        loc_game_primary.mkdir(parents=True, exist_ok=True)
        static_loc_file = loc_game_primary / "Game_DualSub_Static.json"
        static_loc_file.write_text(json.dumps(dual_table, indent=2, ensure_ascii=False), encoding="utf-8")
        patched.append(static_loc_file)
        if str(static_loc_file.resolve()) not in created:
            created.append(str(static_loc_file.resolve()))
        self._export_live_overlay_cache(game_dir, dual_table)

        # Step 6: Deploy UE4SS 2.5/3.0 Mod Structure (`Mods/DualSub/Scripts/main.lua` + `enabled.txt` + `mods.txt`)
        suite_root = Path(__file__).parent.resolve()
        is_self_suite = (game_dir / "universal_dualsub.py").is_file() and (game_dir / "subtitle_engine.py").is_file()
        if not is_self_suite:
            ue4ss_mods_roots: List[Path] = []
            cand_bases = [sub_proj_dir, game_dir] if sub_proj_dir != game_dir else [game_dir]
            for base_d in cand_bases:
                for cand_mods in [
                    base_d / "Binaries" / "Win64" / "ue4ss" / "Mods",
                    base_d / "Binaries" / "Win64" / "UE4SS" / "Mods",
                    base_d / "Binaries" / "Win64" / "Mods",
                    base_d / "UE4SS" / "Mods",
                ]:
                    if cand_mods.parent.is_dir() and cand_mods not in ue4ss_mods_roots:
                        ue4ss_mods_roots.append(cand_mods)

            if not ue4ss_mods_roots:
                if sub_proj_dir != game_dir:
                    ue4ss_mods_roots.append(sub_proj_dir / "Binaries" / "Win64" / "ue4ss" / "Mods")
                ue4ss_mods_roots.append(game_dir / "Mods")

            src_lua = suite_root / "DualSub.lua"
            dict_cache = suite_root / "dictionaries" / "famous_dictionary_cache.json"
            file_backups = journal.setdefault("subtitle_file_backups", {})

            for mods_root in ue4ss_mods_roots:
                mod_dest = mods_root / "DualSub"
                scripts_dest = mod_dest / "Scripts"
                trans_dest = mod_dest / "translations"
                dict_dest = mod_dest / "dictionaries"
                scripts_dest.mkdir(parents=True, exist_ok=True)
                trans_dest.mkdir(parents=True, exist_ok=True)
                dict_dest.mkdir(parents=True, exist_ok=True)

                created_mod_files = []
                if src_lua.is_file():
                    main_lua = scripts_dest / "main.lua"
                    legacy_lua = mod_dest / "DualSub.lua"
                    shutil.copy2(src_lua, main_lua)
                    shutil.copy2(src_lua, legacy_lua)
                    created_mod_files.extend([main_lua, legacy_lua])

                enabled_txt = mod_dest / "enabled.txt"
                enabled_txt.write_text("DualSub enabled\n", encoding="utf-8")
                created_mod_files.append(enabled_txt)

                active_pair_file = mod_dest / "dualsub_active_pair.json"
                active_pair_file.write_text(
                    json.dumps(
                        {
                            "primary_lang": self.primary_lang,
                            "secondary_lang": self.secondary_lang,
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                created_mod_files.append(active_pair_file)

                trans_file = trans_dest / f"{pair_code}.json"
                trans_file.write_text(json.dumps(dual_table, indent=2, ensure_ascii=False), encoding="utf-8")
                created_mod_files.append(trans_file)

                if dict_cache.is_file():
                    d1 = dict_dest / "famous_dictionary_cache.json"
                    d2 = dict_dest / f"dict_{pair_code}.json"
                    shutil.copy2(dict_cache, d1)
                    shutil.copy2(dict_cache, d2)
                    created_mod_files.extend([d1, d2])

                mods_txt = mods_root / "mods.txt"
                if mods_txt.is_file():
                    mkey = str(mods_txt.resolve())
                    if mkey not in file_backups:
                        file_backups[mkey] = mods_txt.read_text(encoding="utf-8", errors="ignore")
                    mtext = mods_txt.read_text(encoding="utf-8", errors="ignore")
                    if not re.search(r"(?m)^\s*DualSub\s*:\s*1", mtext):
                        if "Keybinds" in mtext:
                            mtext = re.sub(r"(?m)^(\s*Keybinds\s*:)", r"DualSub : 1\n\1", mtext, count=1)
                        else:
                            mtext = mtext.rstrip() + "\nDualSub : 1\n"
                        mods_txt.write_text(mtext, encoding="utf-8")
                elif "ue4ss" in str(mods_root).lower():
                    mods_txt.write_text("DualSub : 1\nKeybinds : 1\n", encoding="utf-8")
                    created_mod_files.append(mods_txt)

                for cmf in created_mod_files:
                    patched.append(cmf)
                    if str(cmf.resolve()) not in created:
                        created.append(str(cmf.resolve()))

            log("    [SubtitleEngine] Deployed UE4SS 3.0 Lua Mod (`Scripts/main.lua` + `enabled.txt` + `mods.txt`)")

        journal_path.write_text(json.dumps(journal, indent=2, ensure_ascii=False), encoding="utf-8")
        return patched

    def _load_or_build_unreal_dual_table(self, game_dir: Path, data_root: Path) -> Dict[str, Any]:
        pair_code = f"{self.primary_lang}_{self.secondary_lang}"
        rev_code = f"{self.secondary_lang}_{self.primary_lang}"

        # 0. Check if game_dir already has an extracted dualsub_live_state.json
        live_state = game_dir / "dualsub_live_state.json"
        if live_state.is_file():
            try:
                data = json.loads(live_state.read_text(encoding="utf-8"))
                if isinstance(data, dict) and len(data) > 0:
                    return data
            except ValueError:
                pass

        candidate = data_root / f"{pair_code}.json"
        if candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except ValueError:
                pass

        rev_candidate = data_root / f"{rev_code}.json"
        if rev_candidate.is_file():
            try:
                raw = json.loads(rev_candidate.read_text(encoding="utf-8"))
                flipped: Dict[str, Any] = {}
                for tname, tbl in raw.items():
                    if isinstance(tbl, dict) and tname != "metadata":
                        flipped[tname] = {}
                        for k, val in tbl.items():
                            if isinstance(val, str) and "/" in val:
                                p, s = val.split("/", 1)
                                flipped[tname][k] = f"{s.strip()} / {p.strip()}"
                            else:
                                flipped[tname][k] = val
                    else:
                        flipped[tname] = tbl
                return flipped
            except ValueError:
                pass

        return {
            "metadata": {
                "primary": self.primary_lang,
                "secondary": self.secondary_lang,
                "mode": "static_and_interactive",
            },
            "ST_Cutscenes": {
                "DLG_01": "Look over there! Something is moving in the shadows! / Sieh mal da drüben! Etwas bewegt sich im Schatten!",
                "DLG_02": "Break out the specialist hardware immediately. / Macht sofort die Spezialausrüstung bereit.",
                "DLG_03": "We found the protective gear and equipment! / Wir haben die Schutzausrüstung gefunden!",
                "DLG_04": "We have to protect this city before nightfall! / Wir müssen diese Stadt vor Einbruch der Dunkelheit schützen!",
                "DLG_05": "That is merely a trick of the light. / Das ist bloß eine Täuschung des Lichts.",
                "DLG_06": "Stay focused and monitor the radio channel. / Bleib konzentriert und überwache den Funkkanal.",
            },
            "ST_Objectives": {
                "OBJ_01": "Investigate the main facility / Untersuche die Hauptanlage",
                "OBJ_02": "Schedule a briefing with the Mayor / Ein Treffen mit dem Bürgermeister vereinbaren",
                "OBJ_03": "Contact the Detective at the observation post / Kontaktiere den Detektiv am Beobachtungsposten",
                "OBJ_04": "Equip your protective goggles and gear / Rüste deine Schutzbrille und Ausrüstung aus",
            },
            "ST_UI": {
                "UI_Prompt_Interact": "Press [E] to Investigate / Drücke [E] zum Untersuchen",
                "UI_Prompt_Action": "Press [SPACE] to Continue / Drücke [LEERTASTE] zum Fortfahren",
            },
        }

    def _scan_and_patch_loose_localization_files(self, game_dir: Path, log=print) -> List[Path]:
        patched: List[Path] = []
        if not game_dir.is_dir():
            return patched

        journal_path = game_dir / JOURNAL_FILENAME
        journal: Dict[str, Any] = {}
        if journal_path.is_file():
            try:
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
            except ValueError:
                pass
        file_backups: Dict[str, str] = journal.setdefault("subtitle_file_backups", {})

        p_tag = self.primary_lang.lower()
        s_tag = self.secondary_lang.lower()

        candidates: List[Path] = []
        for ext in ("*.srt", "*.vtt", "*.ass", "*.ssa", "*.json", "*.csv"):
            for fpath in game_dir.rglob(ext):
                if any(
                    part.lower() in ("ue4ss", "mods", "dictionaries", "~mods", "bundles", ".dualtitle_save_backup", "backups")
                    for part in fpath.parts
                ):
                    continue
                if fpath.name.startswith(".") or fpath.name in (
                    "pakstore.json",
                    "dualsub-settings.json",
                    "manifest.json",
                    "Game_DualSub_Static.json",
                    "dualsub_live_state.json",
                    "active_live_subtitles.json",
                ):
                    continue
                candidates.append(fpath)

        for p_file in candidates:
            stem_low = p_file.stem.lower()
            match = re.search(rf"(?:^|[_\-\.])({re.escape(p_tag)})(?:[_\-\.]|$)", stem_low)
            if not match:
                continue

            start_idx, end_idx = match.span(1)
            sec_stem = p_file.stem[:start_idx] + s_tag + p_file.stem[end_idx:]
            s_file = p_file.with_name(sec_stem + p_file.suffix)
            if not s_file.is_file() or s_file == p_file:
                continue

            key = str(p_file.resolve())
            if key not in file_backups:
                file_backups[key] = p_file.read_text(encoding="utf-8", errors="ignore")

            tmp_primary = p_file.with_suffix(p_file.suffix + ".orig_tmp")
            try:
                tmp_primary.write_text(file_backups[key], encoding="utf-8")
                ext_low = p_file.suffix.lower()
                if ext_low in (".srt", ".vtt"):
                    self.merge_srt_files(tmp_primary, s_file, p_file, mode="newline")
                    patched.append(p_file)
                    log(f"    [SubtitleEngine] Merged DualTitle subtitle file in-place: {p_file.name}")
                elif ext_low in (".ass", ".ssa"):
                    self.merge_ass_files(tmp_primary, s_file, p_file)
                    patched.append(p_file)
                    log(f"    [SubtitleEngine] Merged DualTitle ASS/SSA subtitle file in-place: {p_file.name}")
                elif ext_low == ".json":
                    p_data = json.loads(tmp_primary.read_text(encoding="utf-8"))
                    s_data = json.loads(s_file.read_text(encoding="utf-8"))
                    if isinstance(p_data, dict) and isinstance(s_data, dict):
                        merged_json = self.merge_json_tables(p_data, s_data, mode="newline")
                        p_file.write_text(json.dumps(merged_json, indent=2, ensure_ascii=False), encoding="utf-8")
                        patched.append(p_file)
                        log(f"    [SubtitleEngine] Merged DualTitle JSON localization in-place: {p_file.name}")
                elif ext_low == ".csv":
                    self.merge_csv_files(tmp_primary, s_file, p_file, mode="newline")
                    patched.append(p_file)
                    log(f"    [SubtitleEngine] Merged DualTitle CSV localization in-place: {p_file.name}")
            except Exception as exc:
                log(f"    [SubtitleEngine] Notice: Skipped {p_file.name} ({exc})")
            finally:
                tmp_primary.unlink(missing_ok=True)

        if file_backups:
            journal_path.write_text(json.dumps(journal, indent=2, ensure_ascii=False), encoding="utf-8")

        return patched

    @staticmethod
    def restore_all_patched_subtitles(game_dir: str | Path, log=print) -> int:
        gdir = Path(game_dir).resolve()
        restored = 0

        if unpatch_forge_game(gdir, log=log):
            restored += 1

        journal_path = gdir / JOURNAL_FILENAME
        if journal_path.is_file():
            try:
                journal = json.loads(journal_path.read_text(encoding="utf-8"))
                for fpath_str, orig_text in journal.get("subtitle_file_backups", {}).items():
                    fp = Path(fpath_str)
                    if fp.parent.is_dir():
                        fp.write_text(orig_text, encoding="utf-8")
                        log(f"    [SubtitleEngine] Restored original subtitle file: {fp.name}")
                        restored += 1

                for fpath_str, hex_bytes in journal.get("binary_locres_backups", {}).items():
                    fp = Path(fpath_str)
                    if fp.parent.is_dir():
                        fp.write_bytes(bytes.fromhex(hex_bytes))
                        log(f"    [SubtitleEngine] Restored original binary .locres: {fp.name}")
                        restored += 1

                for fpath_str, hex_bytes in journal.get("frostbite_sb_backups", {}).items():
                    fp = Path(fpath_str)
                    if fp.parent.is_dir():
                        fp.write_bytes(bytes.fromhex(hex_bytes))
                        log(f"    [SubtitleEngine] Restored original Frostbite bundle: {fp.name}")
                        restored += 1

                for created_str in journal.get("created_files", []):
                    cp = Path(created_str)
                    if cp.is_file():
                        cp.unlink()
                        log(f"    [SubtitleEngine] Removed static DualTitle override: {cp.name}")
                        restored += 1

                journal.pop("subtitle_file_backups", None)
                journal.pop("binary_locres_backups", None)
                journal.pop("frostbite_sb_backups", None)
                journal.pop("created_files", None)
                if journal:
                    journal_path.write_text(json.dumps(journal, indent=2, ensure_ascii=False), encoding="utf-8")
                else:
                    journal_path.unlink(missing_ok=True)
            except (OSError, ValueError) as exc:
                log(f"    [SubtitleEngine] Warning during subtitle restore: {exc}")

        live_state = gdir / "dualsub_live_state.json"
        if live_state.is_file():
            live_state.unlink(missing_ok=True)

        return restored

    @staticmethod
    def emergency_repair_game_folder(game_dir: str | Path, log=print) -> int:
        """
        Clean and repair any application/game folder even if `.dualsub_journal.json` was
        overwritten or deleted. Removes any synthetic `.utoc`, `.ucas`, and `.pak` files in
        `Content/Paks`, removes synthetic <8KB `Game.locres` files, cleans UE4SS `Mods/DualSub`
        & `mods.txt`, and restores all backups.
        """
        gdir = Path(game_dir).resolve()
        if not gdir.is_dir():
            return 0
        fixed = UniversalSubtitleMerger.restore_all_patched_subtitles(gdir, log=log)

        subprojects = find_unreal_subprojects(gdir)
        content_roots = [gdir / "Content"] + [sp / "Content" for sp in subprojects]

        # 1. Force-delete any *DualSub* or *DualTitle* .utoc, .ucas, .pak, .sig, .json in Content/Paks & ~mods
        for croot in content_roots:
            for paks_sub in [croot / "Paks" / "~mods", croot / "Paks"]:
                if paks_sub.is_dir():
                    for item in list(paks_sub.iterdir()):
                        if item.is_file() and any(
                            tag in item.name for tag in ("DualSub", "DualTitle", "pakchunk99-")
                        ):
                            try:
                                item.unlink()
                                log(f"    [EmergencyRepair] Removed container: {item.name}")
                                fixed += 1
                            except OSError:
                                pass

        # 2. Remove synthetic <8KB Game.locres and Game_DualSub_Static.json in Content/Localization
        for croot in content_roots:
            loc_root = croot / "Localization"
            if loc_root.is_dir():
                for fpath in list(loc_root.rglob("*")):
                    if not fpath.is_file():
                        continue
                    if fpath.name in ("Game_DualSub_Static.json", "Game_DualTitle_Static.json"):
                        try:
                            fpath.unlink()
                            fixed += 1
                        except OSError:
                            pass
                    elif fpath.name.lower() == "game.locres" and fpath.stat().st_size < 8192:
                        try:
                            raw = fpath.read_bytes()
                            if b"DX_Intro_01" in raw or b"DLG_01" in raw:
                                fpath.unlink()
                                log(f"    [EmergencyRepair] Removed synthetic Game.locres: {fpath.name}")
                                fixed += 1
                        except OSError:
                            pass

        # 3. Clean UE4SS Mods/DualSub folder and remove `DualSub : 1` from mods.txt
        mods_roots = [
            gdir / "Binaries" / "Win64" / "ue4ss" / "Mods",
            gdir / "Binaries" / "Win64" / "UE4SS" / "Mods",
            gdir / "UE4SS" / "Mods",
            gdir / "Mods",
        ]
        for sp in subprojects:
            mods_roots.extend([
                sp / "Binaries" / "Win64" / "ue4ss" / "Mods",
                sp / "Binaries" / "Win64" / "UE4SS" / "Mods",
                sp / "Binaries" / "Win64" / "Mods",
            ])

        for mods_root in mods_roots:
            if mods_root.is_dir():
                for sub_name in ("DualSub", "DualTitle"):
                    target_mod = mods_root / sub_name
                    if target_mod.is_dir():
                        shutil.rmtree(target_mod, ignore_errors=True)
                        log(f"    [EmergencyRepair] Removed mod folder: {target_mod}")
                        fixed += 1
                mods_txt = mods_root / "mods.txt"
                if mods_txt.is_file():
                    try:
                        mtext = mods_txt.read_text(encoding="utf-8", errors="ignore")
                        cleaned = re.sub(r"(?m)^\s*Dual(Sub|Title)\s*:\s*[01]\s*\r?\n?", "", mtext)
                        if cleaned != mtext:
                            mods_txt.write_text(cleaned, encoding="utf-8")
                            log(f"    [EmergencyRepair] Cleaned mods.txt: {mods_txt}")
                            fixed += 1
                    except OSError:
                        pass

        return fixed
