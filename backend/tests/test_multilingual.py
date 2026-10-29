"""Native-script and romanised search across all eleven target languages (Phase 2 gate).

Each query is written in the language's own script; the fixture stores the same words in
scholarly romanisation, so a hit proves the script-to-romanisation path works.
"""

import pytest

from app.services.normalize import normalize_form
from app.services.transliterate import romanize, romanize_variants

# Tier 1 additions: Devanagari queries against each language's own LSI record (lsi_mini).
TIER1_CASES = [
    ("पाँच", "nep", "pā̃ch"),  # Grierson writes च as ch (Hunterian)
    ("दुई", "nep", "dui"),
    ("दू", "mai", "dū"),
    ("इक", "doi", "ik"),
    ("से", "brx", "sè"),
    ("दोन", "gom", "dōn"),
    ("दो", "awa", "dō"),
    ("दोय", "mwr", "dōy"),
]

CASES = [  # (query in native script, language, form stored in the fixture)
    ("दाँत", "hin", "dāt"),
    ("দাঁত", "ben", "dā̃t"),
    ("दाँत", "mar", "dā̃t"),
    ("દાંત", "guj", "dā̃t"),
    ("ਦੰਦ", "pan", "dand"),
    ("ଦାନ୍ତ", "ory", "dānta"),
    ("দাঁত", "asm", "dā̃t"),
    ("ஓட்டம்", "tam", "ōṭṭam"),
    ("ఓట", "tel", "ōṭa"),
    ("ಓಡು", "kan", "ōḍu"),
    ("ഓടുക", "mal", "ōṭuka"),
]


@pytest.mark.parametrize(("query", "language", "form"), CASES)
def test_native_script_query_finds_romanised_record(client, query, language, form):
    body = client.get("/api/v1/search", params={"q": query, "language_id": language}).json()
    hits = {m["form"].strip(): m for m in body["matches"]}
    assert form in hits, list(hits)
    match = hits[form]
    # A record that already stores the native spelling matches exactly instead (KEED Kannada).
    assert match["match_type"] in ("transliteration", "native_exact")
    if match["match_type"] == "transliteration":
        assert match["via"] and "by rule" in match["via"]


@pytest.mark.parametrize(("query", "language", "form"), TIER1_CASES)
def test_tier1_languages_found_from_devanagari(client, lsi_imported, query, language, form):
    body = client.get("/api/v1/search", params={"q": query, "language_id": language}).json()
    # Raw source forms keep their original Unicode encoding; compare composed forms.
    forms = {normalize_form(m["form"]): m["match_type"] for m in body["matches"]}
    assert forms.get(normalize_form(form)) == "transliteration", forms


def test_transliteration_is_restricted_to_languages_using_the_script(client):
    body = client.get("/api/v1/search", params={"q": "ದಾಂತ"}).json()  # Kannada script
    assert all(m["language_id"] == "kan" for m in body["matches"])


def test_romanised_alias_path(client, imported_db):
    from app.importers.common import connect

    with connect(imported_db) as conn:
        conn.execute(
            "INSERT INTO transliteration_alias (language_id, native, roman, roman_key, dataset,"
            " weight) VALUES ('hin', 'दाँत', 'daant', 'daant', 'dakshina', 5)"
            " ON CONFLICT DO NOTHING"
        )
    body = client.get("/api/v1/search", params={"q": "daant"}).json()
    hit = next(m for m in body["matches"] if m["language_id"] == "hin" and m["form"] == "dāt")
    assert hit["match_type"] == "transliteration" and "dakshina" in hit["via"]


@pytest.mark.parametrize(
    ("native", "expected"),
    [
        ("पानी", "pānī"),
        ("समझना", "samajhnā"),
        ("कलम", "kalam"),
        ("हँसना", "hãsnā"),
        ("गंगा", "gaṅgā"),
        ("জল", "jal"),
        ("தண்ணீர்", "taṇṇīr"),
        ("ಹಗಲು", "hagalu"),
        ("നീളം", "nīḷaṁ"),
        ("ପାଣି", "pāṇi"),
        ("ਪਾਣੀ", "pāṇī"),
        ("પાણી", "pāṇī"),
    ],
)
def test_romanize(native, expected):
    assert romanize(native) == expected


def test_variants_cover_both_schwa_and_nasal_readings():
    assert romanize_variants("दंत") == ["dant", "dãt", "danta", "dãta"]
    assert "pā̃ch" in romanize_variants("पाँच")  # Hunterian spelling of ISO pā̃c
    assert romanize("abc") is None


def test_khanda_ta_and_addak():
    assert romanize("বিদ্যুৎ") == "bidyut"
    assert romanize("ਪੱਤਾ") == "pattā"


def test_native_records_are_keyed_by_language_aware_romanisation():
    from app.services.normalize import lexeme_search_key

    assert lexeme_search_key("अंगारा", "hin") == "angara"
    assert lexeme_search_key("जनक", "san") == "janaka"  # Sanskrit keeps inherent vowels
    assert lexeme_search_key("जनक", "hin") == "janak"
    assert lexeme_search_key("dā̃t", "hin") == "dat"


def test_romanised_query_finds_native_only_record(client, imported_db):
    from app.importers.common import connect
    from app.services.normalize import lexeme_search_key

    with connect(imported_db) as conn:
        conn.execute(
            "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key, native_form,"
            " gloss, form_kind, reconstruction_status, dataset, source_id, source_record_id)"
            " VALUES ('lx_test_angara', 'hin', 'अंगारा', 'अंगारा', %s, 'अंगारा', 'ember', 'word',"
            " 'attested', 'wikidata-lexemes', 'wikidata-lexemes', 'L-test')"
            " ON CONFLICT DO NOTHING",
            (lexeme_search_key("अंगारा", "hin"),),
        )
    body = client.get("/api/v1/search", params={"q": "angara"}).json()
    assert ("अंगारा", "loose") in [(m["form"], m["match_type"]) for m in body["matches"]]
    # ...but a native-script query never matches unrelated romanised records by bare key
    deva = client.get("/api/v1/search", params={"q": "पल"}).json()
    assert all(
        m["language_id"] in ("hin", "mar", "san", "oia", "pra", "pli") for m in deva["matches"]
    )
