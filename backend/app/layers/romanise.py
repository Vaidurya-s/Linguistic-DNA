"""Table-driven romanisation for the scripts `services/transliterate.py` does not cover.

Used only to build the `translit_rule` key of layers.word_key: a deterministic, rule-based
spelling in Latin letters, so that a word written in its own script can be found from a
scholarly Latin
spelling. No fuzzy matching; every letter is one table entry. Output keeps diacritics, because the
key is `keys.fold_key(romanise(...))` and the fold decides what is merged.

Scripts and tables (all lower-case; unknown characters pass through unchanged):

CYRILLIC  ISO 9 / scholarly style, one table for Russian, Ukrainian, Belarusian, Bulgarian,
          Macedonian, Serbian, Ossetic and Church Slavonic. After the fold this means: ж -> z,
          ч -> c, ш -> s, щ -> sc, ю -> u, я -> a, э -> e, х -> x, г -> g (also in Ukrainian),
          и and і -> i, ы -> y, ъ and ь dropped in modern languages (the fold drops the ISO 9
          marks ″ and ′), but ъ -> ŭ, ь -> ĭ and the old letters ѣ ѧ ѫ ѹ in Church Slavonic and
          Old Russian. Ossetic дз -> ʒ and ӕ -> æ.
GREEK     ISO 843 / scholarly style, polytonic marks stripped. Ancient (default): η -> ē, ω -> ō,
          υ -> y, φ -> ph, χ -> ch, initial rough breathing -> h, ῥ -> rh. Modern (language list
          MODERN_GREEK, and the dialects that follow modern spelling): η -> ī, φ -> f, β -> v.
          γγ -> ng (ancient) or gg (modern), γκ -> nk or gk, ου -> ou, αυ -> au, ευ -> eu.
ARMENIAN  Hübschmann-Meillet style: ու -> ow in every variety (IE-CoR mixes ow and u for Eastern),
          և -> ew, aspirates with ʿ (թ tʿ, փ pʿ, ք kʿ, ց cʿ, չ čʿ), ռ -> ṙ, ղ -> ł.
ARABIC    Consonant skeleton ONLY. Vowels are not recovered: ا و ي ی ى ئ ؤ أ إ آ ء ع and the
          short-vowel marks are dropped, every other letter maps to a consonant letter of the
          Latin key; a Latin query is reduced the same way (vowel letters a e i o u y w dropped,
          digraphs sh zh -> s z; kh gh ch -> x g c; final h dropped; doubled letters collapsed).
          Skeleton keys carry the prefix `sk:` so
          they never meet a full romanisation. Words that differ only in vowels share a key.
HEBREW    Not covered (no gold words, no time).

Public: script_of, romanise, consonant_skeleton, latin_skeleton, rule_key, rule_query_keys.
"""

from __future__ import annotations

import unicodedata

RULES_VERSION = "romanise-1"

SCRIPTS = ("CYRILLIC", "GREEK", "ARMENIAN", "ARABIC")
SKELETON_PREFIX = "sk:"

# --- language groups -----------------------------------------------------------------------------
CHURCH_SLAVONIC = {"gl-chur1257", "gl-oldr1238", "wkt-zls-chs-ru", "gl-olds1250"}
OSSETIC = {"gl-iron1242", "gl-digo1242", "gl-osse1243"}
MODERN_GREEK = {
    "gl-mode1248",
    "ell",
    "gl-pont1253",
    "gl-capp1239",
    "gl-cypr1249",
    "gl-apul1236",
    "gl-grik1234",
    "gl-tsak1248",
    "gl-cret1239",
}

# --- Cyrillic ------------------------------------------------------------------------------------
_CYR = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "ë", "ж": "ž", "з": "z",
    "и": "i", "й": "j", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "x", "ц": "c", "ч": "č", "ш": "š", "щ": "šč",
    "ъ": "″", "ы": "y", "ь": "′", "э": "è", "ю": "û", "я": "â",
    "і": "ì", "ї": "ï", "є": "ê", "ґ": "g", "ў": "ǔ", "ј": "j", "љ": "lj", "њ": "nj", "ћ": "ć",
    "ђ": "đ", "џ": "dž", "ѓ": "ǵ", "ќ": "ḱ", "ѕ": "dz", "ӕ": "æ", "ҕ": "ɣ",
    "’": "", "ʼ": "", "'": "",
}  # fmt: skip
_CYR_OLD = {"ъ": "ŭ", "ь": "ĭ", "ѣ": "ě", "ѧ": "ę", "ѫ": "ǫ", "ѹ": "u", "ꙋ": "u", "ѵ": "ü",
            "ѥ": "je", "ѩ": "ję", "ѭ": "jǫ", "ѡ": "ō", "ѻ": "o", "ѿ": "ōt", "ѳ": "f", "ꙗ": "ja",
            "ѯ": "ks", "ѱ": "ps", "і": "i", "ї": "ji", "ѕ": "dz", "ꙁ": "z", "ꙃ": "dz"}  # fmt: skip
_CYR_OSS = {"дз": "ʒ", "дж": "ǯ", "гъ": "ǧ", "къ": "k", "пъ": "p", "тъ": "t", "цъ": "c",
            "чъ": "č", "хъ": "q"}  # fmt: skip

# --- Greek ---------------------------------------------------------------------------------------
_GRC_BASE = {
    "α": "a", "β": "b", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "ē", "θ": "th", "ι": "i",
    "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x", "ο": "o", "π": "p", "ρ": "r", "σ": "s",
    "ς": "s", "τ": "t", "υ": "y", "φ": "ph", "χ": "ch", "ψ": "ps", "ω": "ō", "ϝ": "w", "ϲ": "s",
    "ϻ": "s", "ϸ": "š", "ϙ": "q", "ϟ": "q", "ͷ": "w", "ϡ": "ss",
}  # fmt: skip
_GRC_ANCIENT_DI = {"γγ": "ng", "γκ": "nk", "γξ": "nx", "γχ": "nch", "αυ": "au", "ευ": "eu",
                   "ου": "ou", "ηυ": "ēu", "υι": "ui"}  # fmt: skip
_GRC_MODERN = {"η": "ī", "φ": "f", "β": "v", "ω": "ō"}
_GRC_MODERN_DI = {"γγ": "gg", "γκ": "g", "αυ": "au", "ευ": "eu", "ου": "ou"}
_ROUGH = "̔"
_VOWELS_GRC = "αεηιουω"

# --- Armenian ------------------------------------------------------------------------------------
_ARM = {
    "ա": "a", "բ": "b", "գ": "g", "դ": "d", "ե": "e", "զ": "z", "է": "ē", "ը": "ə", "թ": "tʿ",
    "ժ": "ž", "ի": "i", "լ": "l", "խ": "x", "ծ": "c", "կ": "k", "հ": "h", "ձ": "j", "ղ": "ł",
    "ճ": "č", "մ": "m", "յ": "y", "ն": "n", "շ": "š", "ո": "o", "չ": "čʿ", "պ": "p", "ջ": "ǰ",
    "ռ": "ṙ", "ս": "s", "վ": "v", "տ": "t", "ր": "r", "ց": "cʿ", "ւ": "w", "փ": "pʿ", "ք": "kʿ",
    "օ": "ō", "ֆ": "f", "և": "ew", "ու": "ow",
}  # fmt: skip

# --- Arabic script: consonant skeleton ---------------------------------------------------------
# vowel letters, hamza, ayn and the short-vowel marks (U+064B-0655, U+0670) are not consonants
_ARA_DROP = set("اوييىئؤأإآءعەٱۆۇۉۊۋېۑےۓێ") | {chr(c) for c in range(0x064B, 0x0656)} | {"\u0670"}
_ARA = {
    "ب": "b", "پ": "p", "ت": "t", "ث": "s", "ج": "j", "چ": "c", "ح": "h", "خ": "x", "د": "d",
    "ذ": "z", "ر": "r", "ز": "z", "ژ": "z", "س": "s", "ش": "s", "ص": "s", "ض": "z", "ط": "t",
    "ظ": "z", "غ": "g", "ف": "f", "ق": "q", "ک": "k", "ك": "k", "گ": "g", "ل": "l", "م": "m",
    "ن": "n", "ه": "h", "ہ": "h", "ھ": "h", "ة": "h", "ټ": "t", "ډ": "d", "ړ": "r", "ڼ": "n",
    "ږ": "g", "ښ": "x", "ځ": "j", "څ": "c", "ڑ": "r", "ٹ": "t", "ڈ": "d", "ں": "n", "ݨ": "n",
    "ڻ": "n", "ڭ": "g", "ڤ": "v", "ڠ": "g", "ݰ": "s", "ݱ": "s", "ڕ": "r", "ڵ": "l",
    "ڎ": "d", "ڄ": "j", "ڊ": "d", "ڙ": "r", "ڪ": "k", "ڳ": "g", "ڱ": "n", "ݔ": "n",
}  # fmt: skip
_LATIN_VOWELS = set("aeiouyw")


def _script_of_char(ch: str) -> str:
    name = unicodedata.name(ch, "")
    return name.split(" ", 1)[0] if name else ""


def script_of(text: str) -> str | None:
    """The covered script that most letters of the text are written in, else None."""
    counts: dict[str, int] = {}
    for ch in text:
        if ch.isalpha():
            s = _script_of_char(ch)
            if s in SCRIPTS or s == "ARABIC":
                counts[s] = counts.get(s, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def _greedy(text: str, table: dict[str, str]) -> str:
    out: list[str] = []
    i = 0
    longest = max(len(k) for k in table)
    while i < len(text):
        for n in range(min(longest, len(text) - i), 0, -1):
            piece = text[i : i + n]
            if piece in table:
                out.append(table[piece])
                i += n
                break
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _cyrillic(text: str, language_id: str | None) -> str:
    table = dict(_CYR)
    if language_id in CHURCH_SLAVONIC:
        table.update(_CYR_OLD)
    elif language_id in OSSETIC:
        table.update(_CYR_OSS)
    else:
        table.update({"ѣ": "ě", "ѧ": "ę", "ѫ": "ǫ", "ѹ": "u", "ѵ": "i", "ѳ": "f", "ѡ": "ō"})
    text = unicodedata.normalize("NFC", text.casefold())
    # stress marks are not letters; й ё ї stay composed
    text = text.replace("́", "").replace("̀", "")
    return _greedy(text, table)


def _greek(text: str, language_id: str | None) -> str:
    modern = language_id in MODERN_GREEK
    base = dict(_GRC_BASE)
    di = dict(_GRC_ANCIENT_DI)
    if modern:
        base.update(_GRC_MODERN)
        di = dict(_GRC_MODERN_DI)
    out: list[str] = []
    for word in unicodedata.normalize("NFC", text.casefold()).split(" "):
        decomposed = unicodedata.normalize("NFD", word)
        letters: list[str] = []
        rough_first = False
        for ch in decomposed:
            if unicodedata.combining(ch):
                if ch == _ROUGH and len(letters) <= 2:
                    rough_first = True
                continue  # accents, breathings, diaeresis, iota subscript, macron: stripped
            letters.append(ch)
        plain = "".join(letters)
        rom = _greedy(plain, {**base, **di})
        if rough_first and not modern:
            rom = ("rh" + rom[1:]) if plain[:1] == "ρ" else "h" + rom
        out.append(rom)
    return " ".join(out)


def _armenian(text: str, language_id: str | None) -> str:
    return _greedy(unicodedata.normalize("NFC", text.casefold()), _ARM)


def romanise(text: str, language_id: str | None = None) -> str | None:
    """Latin spelling (with diacritics) of a Cyrillic, Greek or Armenian word; None for any other
    script, including Arabic (use consonant_skeleton)."""
    script = script_of(text)
    if script == "CYRILLIC":
        return _cyrillic(text, language_id)
    if script == "GREEK":
        return _greek(text, language_id)
    if script == "ARMENIAN":
        return _armenian(text, language_id)
    return None


def _finish_skeleton(sk: str) -> str:
    """Shared last step of both skeletons: aspirates merged (kh -> x, gh -> g, ch -> c), doubled
    letters (shadda, geminates) collapsed, a final h dropped (it is often only a vowel letter)."""
    for a, b in (("kh", "x"), ("gh", "g"), ("ch", "c")):
        sk = sk.replace(a, b)
    out = [ch for i, ch in enumerate(sk) if i == 0 or ch != sk[i - 1]]
    if len(out) > 2 and out[-1] == "h":
        out.pop()
    return "".join(out)


def consonant_skeleton(text: str) -> str:
    """Consonant skeleton of an Arabic-script word (vowels are not recovered)."""
    out = []
    for ch in unicodedata.normalize("NFKC", text):
        if ch in _ARA_DROP or unicodedata.category(ch)[0] in "MPZSC":
            continue
        out.append(_ARA.get(ch, ch if ch.isalnum() and ch.isascii() else ""))
    return _finish_skeleton("".join(out))


def latin_skeleton(text: str) -> str:
    """The same skeleton for a Latin spelling: folded, digraphs merged, vowel letters dropped."""
    from app.layers.keys import fold_key  # avoids an import cycle

    s = fold_key(text)
    for a, b in (("sh", "s"), ("ch", "C"), ("zh", "z"), ("kh", "kh"), ("gh", "gh")):
        s = s.replace(a, b)
    s = "".join(ch for ch in s if ch not in _LATIN_VOWELS and ch.isascii())
    return _finish_skeleton(s.replace("C", "ch"))


# --- keys ---------------------------------------------------------------------------------------


def rule_key(text: str, language_id: str | None = None) -> str | None:
    """The translit_rule key of a stored word: fold of its rule romanisation, or `sk:` + skeleton
    for Arabic script; None when the script is not covered or nothing is left."""
    from app.layers.keys import fold_key

    script = script_of(text)
    if script is None:
        return None
    if script == "ARABIC":
        sk = consonant_skeleton(text)
        return SKELETON_PREFIX + sk if len(sk) >= 2 else None
    rom = romanise(text, language_id)
    return fold_key(rom) if rom else None


def rule_query_keys(form: str, language_id: str | None = None) -> list[str]:
    """Keys to look up for a query: a Latin query is its own romanisation and also gives a
    skeleton; a covered-script query gives its rule key."""
    from app.layers.keys import fold_key, is_latin_script

    if is_latin_script(form):
        keys = [fold_key(form)]
        sk = latin_skeleton(form)
        if len(sk) >= 2:
            keys.append(SKELETON_PREFIX + sk)
        return [k for k in keys if k]
    key = rule_key(form, language_id)
    return [key] if key else []
