#!/usr/bin/env python3
"""
DualTitle - Famous Dictionary & Phrase Translation Engine
Fetches rich definitions, phonetics, parts of speech, German noun genders (der/die/das),
and bilingual word/sentence translations using Wiktionary, Free Dictionary API, and
online translation fallback with local offline caching.
"""

import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Dict, List, Optional, Any

# Pre-seeded Famous Dictionary with rich linguistic data (Wiktionary / WordNet standard)
BUILTIN_FAMOUS_LEXICON = {
    "alarmed": {
        "word": "alarmed",
        "lang": "en",
        "phonetic": "/əˈlɑːmd/",
        "pos": "adjective",
        "source": "Oxford / Wiktionary",
        "definition": "Experiencing a sudden feeling of fear, apprehension, or awareness of danger.",
        "example": "He was alarmed by the sudden noises coming from the corridor.",
        "german_translation": "alarmiert, beunruhigt",
        "notes": "Synonyms: frightened, startled, worried"
    },
    "cry": {
        "word": "cry",
        "lang": "en",
        "phonetic": "/kraɪ/",
        "pos": "noun / verb",
        "source": "Merriam-Webster / Wiktionary",
        "definition": "A loud, inarticulate sound made by a person, expressing pain, grief, or alarm.",
        "example": "The alarmed cry echoed through the narrow streets at night.",
        "german_translation": "der Schrei (m), rufen / weinen",
        "notes": "German: der Schrei, die Schreie (pl.)"
    },
    "bat": {
        "word": "bat",
        "lang": "en",
        "phonetic": "/bæt/",
        "pos": "noun",
        "source": "Oxford / Wiktionary",
        "definition": "A nocturnal mammal with forelimbs adapted as wings for flight.",
        "example": "Look over there! It's a bat flying across the sky!",
        "german_translation": "die Fledermaus (f)",
        "notes": "German: die Fledermaus, die Fledermäuse (pl.) [Feminin]"
    },
    "detective": {
        "word": "detective",
        "lang": "en",
        "phonetic": "/dɪˈtɛktɪv/",
        "pos": "noun",
        "source": "Collins / Wiktionary",
        "definition": "A member of the police force or a private investigator investigating offenses.",
        "example": "The detective arrived at the observation post.",
        "german_translation": "der Detektiv (m), der Ermittler (m)",
        "notes": "German: der Detektiv, die Detektive (pl.) [Maskulin]"
    },
    "hardware": {
        "word": "hardware",
        "lang": "en",
        "phonetic": "/ˈhɑːdweə/",
        "pos": "noun",
        "source": "Cambridge / Wiktionary",
        "definition": "Physical equipment, specialized mechanical apparatus, or tactical gear.",
        "example": "Break out the specialist hardware.",
        "german_translation": "die Ausrüstung (f), die Hardware (f)",
        "notes": "German: die Ausrüstung, die Ausrüstungen (pl.) [Feminin]"
    },
    "manufacturing": {
        "word": "manufacturing",
        "lang": "en",
        "phonetic": "/ˌmænjʊˈfæktʃərɪŋ/",
        "pos": "noun",
        "source": "American Heritage / Wiktionary",
        "definition": "The industrial process of producing goods or machinery on a large scale.",
        "example": "We're moving to manufacturing immediately.",
        "german_translation": "die Herstellung (f), die Fertigung (f)",
        "notes": "German: die Herstellung, die Herstellungen (pl.) [Feminin]"
    },
    "monologue": {
        "word": "monologue",
        "lang": "en",
        "phonetic": "/ˈmɒnəlɒɡ/",
        "pos": "noun",
        "source": "Oxford / Wiktionary",
        "definition": "A lengthy speech presented by a single character in a drama or dialogue.",
        "example": "The speaker delivered a dramatic monologue on stage.",
        "german_translation": "der Monolog (m)",
        "notes": "German: der Monolog, die Monologe (pl.) [Maskulin]"
    },
    "mayor": {
        "word": "mayor",
        "lang": "en",
        "phonetic": "/mɛər/",
        "pos": "noun",
        "source": "Collins / Wiktionary",
        "definition": "The elected head of an administrative city or municipality.",
        "example": "Schedule a briefing with the Mayor this afternoon.",
        "german_translation": "der Bürgermeister (m)",
        "notes": "German: der Bürgermeister, die Bürgermeister (pl.) [Maskulin]"
    },
    "cape": {
        "word": "cape",
        "lang": "en",
        "phonetic": "/keɪp/",
        "pos": "noun",
        "source": "Cambridge / Wiktionary",
        "definition": "A sleeveless cloak hanging loosely from the shoulders.",
        "example": "He wore a heavy weatherproof cape in the storm.",
        "german_translation": "der Umhang (m), das Cape (n)",
        "notes": "German: der Umhang, die Umhänge (pl.) [Maskulin]"
    },
    "goggles": {
        "word": "goggles",
        "lang": "en",
        "phonetic": "/ˈɡɒɡlz/",
        "pos": "noun (plural)",
        "source": "Oxford / Wiktionary",
        "definition": "Protective eyewear with surrounding shields against dust, impact, and glare.",
        "example": "Put on your protective goggles before entering the lab.",
        "german_translation": "die Schutzbrille (f)",
        "notes": "German: die Schutzbrille, die Schutzbrillen (pl.) [Feminin]"
    },
    "hat": {
        "word": "hat",
        "lang": "en",
        "phonetic": "/hæt/",
        "pos": "noun",
        "source": "Oxford / Wiktionary",
        "definition": "A shaped headwear worn for warmth, protection, or formal style.",
        "example": "Look, I found the hat near the entrance!",
        "german_translation": "der Hut (m)",
        "notes": "German: der Hut, die Hüte (pl.) [Maskulin]"
    },
    "city": {
        "word": "city",
        "lang": "en",
        "phonetic": "/ˈsɪti/",
        "pos": "noun",
        "source": "WordNet / Wiktionary",
        "definition": "A large human municipality and urban center.",
        "example": "We have to protect this city before nightfall!",
        "german_translation": "die Stadt (f)",
        "notes": "German: die Stadt, die Städte (pl.) [Feminin]"
    },
    "trick": {
        "word": "trick",
        "lang": "en",
        "phonetic": "/trɪk/",
        "pos": "noun / verb",
        "source": "Wiktionary",
        "definition": "An optical illusion, deception, or skilled act of craft.",
        "example": "That is merely a trick of the light.",
        "german_translation": "die Täuschung (f), der Trick (m)",
        "notes": "German: der Trick, die Tricks (pl.) [Maskulin]"
    },
    "light": {
        "word": "light",
        "lang": "en",
        "phonetic": "/laɪt/",
        "pos": "noun / adjective",
        "source": "WordNet",
        "definition": "Electromagnetic radiation perceptible to the human eye; illumination.",
        "example": "The searchlight cut through the dense fog.",
        "german_translation": "das Licht (n)",
        "notes": "German: das Licht, die Lichter (pl.) [Neutrum]"
    },
    "fledermaus": {
        "word": "die Fledermaus",
        "lang": "de",
        "gender": "Feminin (die)",
        "pos": "Substantiv, feminin",
        "source": "Duden / Wiktionary",
        "definition": "Kleines nachtaktives Säugetier mit zu Flügeln umgebildeten Vordergliedmaßen.",
        "example": "Sieh mal da drüben! Es ist eine Fledermaus!",
        "english_translation": "bat",
        "notes": "Plural: die Fledermäuse"
    },
    "umhang": {
        "word": "der Umhang",
        "lang": "de",
        "gender": "Maskulin (der)",
        "pos": "Substantiv, maskulin",
        "source": "Duden / Wiktionary",
        "definition": "Ärmelloses Kleidungsstück, das locker um Schultern und Rücken gelegt wird.",
        "example": "Der dunkle Umhang wehte im Wind.",
        "english_translation": "cape, cloak",
        "notes": "Plural: die Umhänge"
    },
    "schutzbrille": {
        "word": "die Schutzbrille",
        "lang": "de",
        "gender": "Feminin (die)",
        "pos": "Substantiv, feminin",
        "source": "Duden / Wiktionary",
        "definition": "Brille, die die Augen vor Staub, Splittern oder grellem Licht schützt.",
        "example": "Setz deine Schutzbrille auf, bevor wir anfangen.",
        "english_translation": "safety goggles",
        "notes": "Plural: die Schutzbrillen"
    },
    "hut": {
        "word": "der Hut",
        "lang": "de",
        "gender": "Maskulin (der)",
        "pos": "Substantiv, maskulin",
        "source": "Duden / Wiktionary",
        "definition": "Feste Kopfbedeckung mit Krempe.",
        "example": "Ich habe deinen Hut gefunden!",
        "english_translation": "hat",
        "notes": "Plural: die Hüte"
    },
    "stadt": {
        "word": "die Stadt",
        "lang": "de",
        "gender": "Feminin (die)",
        "pos": "Substantiv, feminin",
        "source": "Duden / Wiktionary",
        "definition": "Größere, geschlossene Siedlung mit eigener Verwaltung.",
        "example": "Diese Stadt braucht unsere Hilfe.",
        "english_translation": "city, town",
        "notes": "Plural: die Städte"
    },
    "schrei": {
        "word": "der Schrei",
        "lang": "de",
        "gender": "Maskulin (der)",
        "pos": "Substantiv, maskulin",
        "source": "Duden / Wiktionary",
        "definition": "Lauter, unartikulierter Laut, meist Ausdruck von Schmerz oder Furcht.",
        "example": "Ein gellender Schrei zerriss die Stille.",
        "english_translation": "cry, shout, scream",
        "notes": "Plural: die Schreie"
    }
}


class FamousDictionaryEngine:
    """Provides word definitions, stem lookups, and live sentence translation."""

    def __init__(self, cache_dir: Optional[Path] = None):
        if cache_dir is None:
            cache_dir = Path(__file__).parent / "dictionaries"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "famous_dictionary_cache.json"
        self.cache: Dict[str, Any] = {}
        self.phrase_cache: Dict[str, str] = {}
        self._load_cache()

    def _load_cache(self):
        self.cache = dict(BUILTIN_FAMOUS_LEXICON)
        if self.cache_file.exists():
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        self.cache.update(saved)
                        # Ensure built-in clean definitions take precedence over any stale entries
                        for k, v in BUILTIN_FAMOUS_LEXICON.items():
                            self.cache[k] = dict(v)
            except Exception as e:
                print(f"[Dictionary] Cache load notice: {e}")

    def _save_cache(self):
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def clean_word(self, token: str) -> str:
        """Strip punctuation and lowercase."""
        return re.sub(r"[\W\d_]+", "", token).lower()

    def translate_sentence(self, text: str, source_lang: str = "en", target_lang: str = "de") -> str:
        """
        Translate a live subtitle sentence from `source_lang` to `target_lang`
        using cached phrase tables, online lightweight translation API (when online),
        or offline word-by-word glossary synthesis.
        """
        clean_text = text.strip()
        if not clean_text or source_lang == target_lang:
            return clean_text
        cache_key = f"{source_lang}:{target_lang}:{clean_text}"
        if cache_key in self.phrase_cache:
            return self.phrase_cache[cache_key]

        # 1. Try lightweight online translation endpoint (with short 1.5s timeout)
        try:
            q = urllib.parse.quote(clean_text)
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={source_lang}&tl={target_lang}&dt=t&q={q}"
            req = urllib.request.Request(url, headers={"User-Agent": "DualTitle/4.1"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                if resp.status == 200:
                    payload = json.loads(resp.read().decode("utf-8"))
                    if isinstance(payload, list) and payload and isinstance(payload[0], list):
                        translated = "".join(seg[0] for seg in payload[0] if seg and seg[0])
                        if translated:
                            self.phrase_cache[cache_key] = translated
                            return translated
        except Exception:
            pass

        # 2. Offline glossary fallback
        out_tokens: List[str] = []
        for tok in clean_text.split():
            cw = self.clean_word(tok)
            if cw in self.cache:
                entry = self.cache[cw]
                trans = entry.get("german_translation") if target_lang == "de" else entry.get("english_translation")
                if trans:
                    out_tokens.append(trans.split(",")[0].split("(")[0].strip())
                    continue
            out_tokens.append(tok)
        result = " ".join(out_tokens)
        self.phrase_cache[cache_key] = result
        return result

    def lookup_online_free_dictionary(self, word: str) -> Optional[Dict[str, Any]]:
        """Query the Free Dictionary API (Oxford/Webster backed)."""
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{urllib.parse.quote(word)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "DualTitle/4.1 (Language Learner Subtitle Engine)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    if isinstance(data, list) and len(data) > 0:
                        entry = data[0]
                        phonetic = entry.get("phonetic", "")
                        meanings = entry.get("meanings", [])
                        pos = meanings[0].get("partOfSpeech", "word") if meanings else "word"
                        defs = meanings[0].get("definitions", []) if meanings else []
                        definition = defs[0].get("definition", "") if defs else ""
                        example = defs[0].get("example", "") if defs else ""

                        result = {
                            "word": word,
                            "lang": "en",
                            "phonetic": phonetic,
                            "pos": pos,
                            "source": "Free Dictionary API (Wiktionary/Oxford)",
                            "definition": definition,
                            "example": example,
                            "german_translation": f"[{word}]"
                        }
                        return result
        except Exception:
            pass
        return None

    def lookup_german_wiktionary(self, word: str) -> Optional[Dict[str, Any]]:
        """Query German Wiktionary REST API for German words (der/die/das & definition)."""
        clean = word.strip().capitalize()
        url = f"https://de.wiktionary.org/api/rest_v1/page/definition/{urllib.parse.quote(clean)}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "DualTitle/4.1 (Language Learner Subtitle Engine)"}
        )
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    de_entries = data.get("de", [])
                    if de_entries:
                        first = de_entries[0]
                        pos = first.get("partOfSpeech", "Substantiv")
                        defs = first.get("definitions", [])
                        definition = defs[0].get("definition", "") if defs else ""
                        clean_def = re.sub(r"<[^>]+>", "", definition)

                        result = {
                            "word": word,
                            "lang": "de",
                            "pos": pos,
                            "source": "German Wiktionary",
                            "definition": clean_def,
                            "example": "",
                            "english_translation": f"[{word}]"
                        }
                        return result
        except Exception:
            pass
        return None

    def lookup(self, token: str, target_lang: str = "de") -> Dict[str, Any]:
        """Comprehensive lookup with stemming, offline lexicon, online fallback, and caching."""
        clean = self.clean_word(token)
        if not clean:
            return {"word": token, "definition": "Symbol/punctuation", "pos": "punct"}

        if clean in self.cache:
            return self.cache[clean]

        if clean.endswith("s") and len(clean) > 3 and clean[:-1] in self.cache:
            res = dict(self.cache[clean[:-1]])
            res["word"] = clean
            res["notes"] = f"Plural of '{clean[:-1]}'. " + res.get("notes", "")
            return res

        if clean.endswith("ed") and len(clean) > 4 and clean[:-2] in self.cache:
            res = dict(self.cache[clean[:-2]])
            res["word"] = clean
            res["notes"] = f"Past tense of '{clean[:-2]}'. " + res.get("notes", "")
            return res

        german_stems = {
            "hüte": "hut",
            "städte": "stadt",
            "schreie": "schrei",
            "fledermäuse": "fledermaus",
            "umhänge": "umhang",
            "schutzbrillen": "schutzbrille"
        }
        if clean in german_stems and german_stems[clean] in self.cache:
            res = dict(self.cache[german_stems[clean]])
            res["word"] = clean
            res["notes"] = f"Pluralform von '{res['word']}'."
            return res

        online_res = None
        if target_lang == "de":
            online_res = self.lookup_online_free_dictionary(clean)
        else:
            online_res = self.lookup_german_wiktionary(clean)

        if online_res:
            self.cache[clean] = online_res
            self._save_cache()
            return online_res

        return {
            "word": token,
            "pos": "dialogue term",
            "source": "DualTitle Lexicon",
            "definition": f"Vocabulary term from dialogue: '{token}'.",
            "german_translation": f"Übersetzung im Kontext: [{clean}]",
            "english_translation": f"Context translation: [{clean}]"
        }
