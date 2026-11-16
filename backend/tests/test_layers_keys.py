"""Word-identity keys (layers.keys): fold rules, translit keys, lookup by kind. Synthetic data."""

import pytest

from app.layers import keys
from app.layers.keys import fold_key, is_latin_script, lexeme_keys, query_keys, resolve_form
from app.services.ids import lexeme_id
from app.services.normalize import normalize_form

# --- fold rules (pure) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Straße", "strasse"),
        ("Äpfel", "apfel"),
        ("café", "cafe"),
        ("dā̃t", "dat"),
        ("Dānt", "dant"),
        ("k'at'a", "kata"),  # apostrophes
        ("ʻōlelo", "olelo"),  # okina is an apostrophe-like modifier letter
        ("ice-cream", "icecream"),  # hyphen
        ("ice cream", "icecream"),  # space
        ("*dʰeǵʰ-", "dhegh"),  # star, hyphen, aspirated letters
        ("ǵʰ", "gh"),
        ("Łódź", "lodz"),
        ("đavo", "davo"),
        ("Ørsted", "orsted"),
        ("ħobż", "hobz"),
        ("ıspanak", "ispanak"),
        ("İstanbul", "istanbul"),
        ("ὕδωρ", "υδωρ"),  # Greek breathing and accent marks
        ("ΣΟΦΊΑΣ", "σοφιασ"),  # final sigma folds with capital sigma
        ("вода́", "вода"),  # Cyrillic stress mark
        ("Вода", "вода"),
        ("ʔ", "ʔ"),  # glottal stop is a consonant
        ("bank1", "bank1"),  # digits stay
    ],
)
def test_fold_key_examples(raw, expected):
    assert fold_key(raw) == expected


def test_fold_keeps_cyrillic_letters_distinct():
    # й ё ї are letters, not accents: folding must not merge them with и е і
    assert fold_key("мой") != fold_key("мои")
    assert fold_key("её") != fold_key("ее")
    assert fold_key("їжа") != fold_key("іжа")


def test_fold_keeps_indic_vowel_signs_and_viramas():
    assert fold_key("पानी") == "पानी"
    assert fold_key("पानी") != fold_key("पन")
    assert fold_key("क्त") != fold_key("कत")


def test_fold_does_not_merge_scripts_or_ligatures():
    assert fold_key("æ") != fold_key("e")
    assert fold_key("þ") != fold_key("t")
    assert fold_key("вода") != fold_key("voda")  # no cross-script merge in the fold kind


def test_fold_is_idempotent_and_never_changes_normalize_form():
    for word in ["Straße", "dā̃t", "вода́", "ὕδωρ", "पानी", "աչք", "ماء", "k'at'a"]:
        assert fold_key(fold_key(word)) == fold_key(word)
    # the id-bearing normaliser is untouched by this module
    assert normalize_form("Straße") == "Straße"
    assert normalize_form("dā̃t") == "dā̃t"


def test_is_latin_script():
    assert is_latin_script("dā̃t")
    assert is_latin_script("kʰat")
    assert not is_latin_script("вода")
    assert not is_latin_script("पानी")
    assert not is_latin_script("Σοφία")
    assert not is_latin_script("աչք")


# --- translit keys (pure) --------------------------------------------------------------------


def test_lexeme_keys_only_store_differences():
    assert lexeme_keys("cafe") == {}
    assert lexeme_keys("Cafe") == {"fold": "cafe"}
    assert lexeme_keys("café") == {"fold": "cafe"}


def test_translit_key_from_source_transliteration_column():
    # Cyrillic, Greek, Armenian, Arabic script: romanisation is the source's own column
    assert lexeme_keys("вода", "voda", "ukr") == {"translit": "voda"}
    assert lexeme_keys("Вода́", "vodá", "rus") == {"fold": "вода", "translit": "voda"}
    assert lexeme_keys("ὕδωρ", "hýdōr", "grc") == {"fold": "υδωρ", "translit": "hydor"}
    assert lexeme_keys("աչք", "ačʻkʻ", "hye")["translit"] == "ack"
    assert lexeme_keys("ماء", "māʾ", "arb")["translit"] == "maʾ"


def test_translit_key_from_indic_romaniser_without_a_column():
    keys_hi = lexeme_keys("पानी", None, "hin")
    assert keys_hi["translit"] == "pani"
    # Sanskrit keeps inherent vowels, Hindi drops word-final ones: the language decides
    assert lexeme_keys("जल", None, "hin")["translit"] == "jal"
    assert lexeme_keys("जल", None, "san")["translit"] == "jala"


def test_translit_missing_for_scripts_without_rules_or_column():
    assert "translit" not in lexeme_keys("вода", None, "ukr")
    assert "translit" not in lexeme_keys("աչք", None, "hye")


def test_latin_words_get_no_translit_row():
    assert "translit" not in lexeme_keys("dānt", "dānt", "hin")
    assert "translit" not in lexeme_keys("jījī", "jījī", "hin")


def test_query_keys():
    q = query_keys("Vodá")
    assert (q["native"], q["fold"], q["translit"]) == ("Vodá", "voda", "voda")
    assert q["translit_rule"] == ["voda", "sk:vd"]
    q = query_keys("पानी", "hin")
    assert q["translit"] == "pani" and q["fold"] == "पानी"
    # a script we cannot romanise has no translit key
    assert query_keys("вода")["translit"] is None


# --- lookup on the database ---------------------------------------------------------------------

A3 = "a3"


def _lang(conn, lid):
    conn.execute(
        "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
        " VALUES (%s, %s, 'other', false, true, '{}') ON CONFLICT DO NOTHING",
        (lid, lid),
    )


def _lex(conn, lang, form, translit=None, dataset="a3test"):
    nf = normalize_form(form)
    lid = lexeme_id(dataset, f"{lang}|{form}")
    conn.execute(
        "INSERT INTO lexeme (id, language_id, form, normalized_form, transliteration,"
        " reconstruction_status, dataset, source_record_id)"
        " VALUES (%s,%s,%s,%s,%s,'attested',%s,%s)"
        " ON CONFLICT DO NOTHING",
        (lid, lang, form, nf, translit, dataset, f"{lang}|{form}"),
    )
    return lid


@pytest.fixture
def keyed(db):
    keys.ensure_schema(db)
    for lang in ("a3-ukr", "a3-hin", "a3-deu", "a3-pol", "a3-grc"):
        _lang(db, lang)
    ids = {
        "voda": _lex(db, "a3-ukr", "вода", "voda"),
        "hin_pani": _lex(db, "a3-hin", "पानी"),
        "hin_latin": _lex(db, "a3-hin", "pānī", "pānī"),
        "deu_wasser": _lex(db, "a3-deu", "Wasser"),
        "deu_water_lc": _lex(db, "a3-deu", "wasser", dataset="a3other"),
        "deu_cafe": _lex(db, "a3-deu", "Café"),
        "pol_voda": _lex(db, "a3-pol", "woda"),
        "pol_voda_other": _lex(db, "a3-pol", "voda"),
        "grc_hydor": _lex(db, "a3-grc", "ὕδωρ", "hýdōr"),
        "ukr_latin": _lex(db, "a3-ukr", "voda", dataset="a3other"),
    }
    for lang in ("a3-ukr", "a3-hin", "a3-deu", "a3-pol", "a3-grc"):
        keys.build_language(db, lang)
    db.commit()
    yield ids
    db.execute("DELETE FROM lexeme WHERE dataset IN ('a3test', 'a3other')")
    db.execute("DELETE FROM layers.word_key WHERE language_id LIKE 'a3-%'")
    db.execute("DELETE FROM layers.word_key_build WHERE language_id LIKE 'a3-%'")
    db.execute("DELETE FROM language WHERE id LIKE 'a3-%'")
    db.commit()


def test_resolve_exact_native_first_then_translit(db, keyed):
    res = resolve_form(db, "a3-ukr", "voda")
    # the Latin lexeme is an exact native match; the Cyrillic one matches through its translit key
    assert res == [(keyed["ukr_latin"], "native"), (keyed["voda"], "translit")]


def test_resolve_kinds_restrict_what_is_found(db, keyed):
    assert resolve_form(db, "a3-ukr", "voda", kinds=("native",)) == [(keyed["ukr_latin"], "native")]
    assert resolve_form(db, "a3-ukr", "voda", kinds=("translit",)) == [(keyed["voda"], "translit")]
    assert resolve_form(db, "a3-ukr", "voda", kinds=("native", "fold")) == [
        (keyed["ukr_latin"], "native")
    ]


def test_resolve_native_script_query_is_exact(db, keyed):
    assert resolve_form(db, "a3-ukr", "вода") == [(keyed["voda"], "native")]
    # case and stress marks fold
    assert resolve_form(db, "a3-ukr", "Вода́") == [(keyed["voda"], "fold")]


def test_resolve_fold_matches_both_directions(db, keyed):
    # query folds to the stored spelling; stored spelling folds to the query
    assert (keyed["deu_wasser"], "native") in resolve_form(db, "a3-deu", "Wasser")
    got = dict(resolve_form(db, "a3-deu", "wasser"))
    assert got[keyed["deu_water_lc"]] == "native"
    assert got[keyed["deu_wasser"]] == "fold"
    assert dict(resolve_form(db, "a3-deu", "cafe"))[keyed["deu_cafe"]] == "fold"
    assert dict(resolve_form(db, "a3-deu", "CAFÉ"))[keyed["deu_cafe"]] == "fold"


def test_resolve_devanagari_both_ways(db, keyed):
    # Latin query finds the Devanagari word through the romaniser's translit key
    assert (keyed["hin_pani"], "translit") in resolve_form(db, "a3-hin", "pani")
    # Devanagari query finds the Latin-script word spelled like its romanisation, by translit
    got = dict(resolve_form(db, "a3-hin", "पानी"))
    assert got[keyed["hin_pani"]] == "native"
    assert got[keyed["hin_latin"]] == "translit"


def test_resolve_greek_with_transliteration_column(db, keyed):
    assert resolve_form(db, "a3-grc", "hydor") == [(keyed["grc_hydor"], "translit")]
    assert resolve_form(db, "a3-grc", "ΎΔΩΡ") == [(keyed["grc_hydor"], "fold")]  # case and accent
    assert resolve_form(db, "a3-grc", "ydor") == []  # no rule links ὕδωρ to ydor
    assert resolve_form(db, "a3-grc", "ὕδωρ") == [(keyed["grc_hydor"], "native")]
    assert resolve_form(db, "a3-grc", "ὑδωρ") == [(keyed["grc_hydor"], "fold")]


def test_no_false_merge_across_languages(db, keyed):
    # the same romanisation in another language never finds the Ukrainian word
    assert resolve_form(db, "a3-pol", "voda") == [(keyed["pol_voda_other"], "native")]
    assert keyed["voda"] not in {i for i, _ in resolve_form(db, "a3-pol", "voda")}
    assert resolve_form(db, "a3-deu", "voda") == []
    assert resolve_form(db, "a3-pol", "woda") == [(keyed["pol_voda"], "native")]


def test_resolve_exclude_datasets(db, keyed):
    res = resolve_form(db, "a3-ukr", "voda", exclude_datasets=["a3other"])
    assert res == [(keyed["voda"], "translit")]


def test_unkeyed_form_resolves_to_nothing(db, keyed):
    assert resolve_form(db, "a3-ukr", "nonexistent") == []
    assert resolve_form(db, "a3-ukr", "") == []


def test_build_is_idempotent_and_stores_only_differences(db, keyed):
    before = db.execute(
        "SELECT count(*) FROM layers.word_key WHERE language_id LIKE 'a3-%'"
    ).fetchone()[0]
    keys.build_language(db, "a3-deu")
    keys.build_language(db, "a3-deu")
    after = db.execute(
        "SELECT count(*) FROM layers.word_key WHERE language_id LIKE 'a3-%'"
    ).fetchone()[0]
    assert before == after
    # "wasser" is its own fold key: nothing stored for it
    n = db.execute(
        "SELECT count(*) FROM layers.word_key WHERE lexeme_id = %s", (keyed["deu_water_lc"],)
    ).fetchone()[0]
    assert n == 0


# --- translit_rule (layers.romanise) -------------------------------------------------------------


def test_romanise_cyrillic_variants():
    from app.layers.romanise import romanise

    assert romanise("вода", "gl-russ1263") == "voda"
    assert romanise("узкий", "gl-russ1263") == "uzkij"
    assert romanise("жёлтый", "gl-russ1263") == "žëltyj"
    assert romanise("гора", "gl-ukra1253") == "gora"
    assert romanise("тежък", "gl-bulg1262") == "tež″k"  # ъ is a mark in modern languages
    assert romanise("ротъ", "gl-oldr1238") == "rotŭ"  # but a vowel in Old Russian
    assert romanise("цвеќе", "gl-mace1250") == "cveḱe"


def test_romanise_greek_ancient_and_modern():
    from app.layers.romanise import romanise

    assert romanise("ὕδωρ", "gl-anci1242") == "hydōr"
    assert romanise("σελήνη", "gl-anci1242") == "selēnē"
    assert romanise("φέγγος", "gl-mode1248") == "feggos"
    assert romanise("νύχι", "gl-mode1248") == "nychi"


def test_romanise_armenian():
    from app.layers.romanise import romanise

    assert romanise("փոր", None) == "pʿor"
    assert romanise("լուսին", None) == "lowsin"


def test_arabic_skeleton_does_not_recover_vowels():
    from app.layers.romanise import consonant_skeleton, latin_skeleton

    assert consonant_skeleton("گوشت") == latin_skeleton("gūšt") == "gst"
    # words that differ only in vowels share a skeleton: the documented weakness
    assert latin_skeleton("kor") == latin_skeleton("kar")
    assert latin_skeleton("māh") == consonant_skeleton("ماه")


def test_rule_keys_only_with_flag_and_do_not_replace_translit():
    assert "translit_rule" not in lexeme_keys("вода", None, "gl-russ1263")
    got = lexeme_keys("вода", None, "gl-russ1263", rule=True)
    assert got == {"translit_rule": "voda"}
    got = lexeme_keys("вода", "voda", "gl-russ1263", rule=True)
    assert got == {"translit": "voda", "translit_rule": "voda"}
    assert lexeme_keys("cafe", rule=True) == {}


def test_resolve_translit_rule_kind(db, keyed):
    from app.layers.keys import ALL_KINDS, RULE_KIND, build_rule_language

    ru = _lex(db, "a3-ukr", "гора")  # no transliteration column
    sk = _lex(db, "a3-hin", "گوشت")
    for lang in ("a3-ukr", "a3-hin"):
        keys.build_language(db, lang)
        build_rule_language(db, lang)
    # Latin query finds a Cyrillic word with no source romanisation, labelled translit_rule
    assert resolve_form(db, "a3-ukr", "gora", kinds=ALL_KINDS) == [(ru, RULE_KIND)]
    assert resolve_form(db, "a3-ukr", "gora") == []  # default kinds do not use the rule keys
    # Arabic-script word is found only through the consonant skeleton
    assert resolve_form(db, "a3-hin", "gust", kinds=ALL_KINDS) == [(sk, RULE_KIND)]
    # no cross-language merge
    assert resolve_form(db, "a3-deu", "gora", kinds=ALL_KINDS) == []
    # a Cyrillic query finds the Latin-script word spelled like its romanisation
    lat = _lex(db, "a3-ukr", "gora", dataset="a3other")
    assert (lat, RULE_KIND) in resolve_form(db, "a3-ukr", "гора", kinds=("translit_rule",))
    db.execute("DELETE FROM layers.word_key WHERE language_id LIKE 'a3-%'")
    db.commit()
