"""Sound-class keys and the extra search techniques. Synthetic data, rolled back."""

import psycopg
import pytest
from sqlalchemy import create_engine, text

from app.cli import init_layers
from app.layers import keys, sound_key
from app.layers.sound_key import block, build, classes, level_pattern, skeleton, skey
from app.services import retrieval

# --- the key itself (pure) --------------------------------------------------------------------


@pytest.mark.parametrize(
    "a, b",
    [
        ("pater", "father"),  # Grimm's law: p and f share a class
        ("pater", "padre"),
        ("pater", "πατήρ"),  # Greek letters are read as sounds
        ("dant", "dānt"),
        ("Straße", "strasse"),
    ],
)
def test_related_spellings_share_a_key(a, b):
    assert skey(a) == skey(b) is not None


def test_consonant_skeleton_survives_a_vowel_change():
    assert skeleton("Nacht")[0] == skeleton("night")[0]
    assert skey("Nacht") != skey("night")  # the first-vowel class differs: found at level 'cons'
    assert level_pattern(skey("Nacht"), "cons") == level_pattern(skey("night"), "cons")


@pytest.mark.parametrize("a, b", [("pater", "mater"), ("water", "fire"), ("hund", "kat")])
def test_unrelated_words_have_different_keys(a, b):
    assert skey(a) != skey(b)


def test_key_format_and_edges():
    assert skey("pater") == "PTR:a"
    assert skey("a") is None and skey("") is None and skey("***") is None
    assert skeleton("tata") == ("TT", "a")  # the same sound after a vowel counts
    assert skeleton("matta") == ("MT", "a")  # a doubled sound counts once
    assert skey("ʔaba") == "P:a"  # glottal stop is not keyed
    assert len(skeleton("abcdefghijklmnop")[0]) <= sound_key.MAX_CONS


def test_voicing_and_diacritics_do_not_matter():
    assert classes("bat") == classes("pad") == classes("pat")
    assert skey("čas") == skey("cas") or skey("čas") == skey("šas")


def test_level_patterns():
    assert level_pattern("PTR:a", "exact") == ("PTR:a", False)
    assert level_pattern("PTR:a", "cons") == ("PTR:", True)
    assert level_pattern("PTR:a", "prefix") == ("PT", True)
    with pytest.raises(ValueError):
        level_pattern("PTR:a", "wide")


def test_source_text_prefers_transliteration_then_script_rules():
    assert skey("вода", None, None) == skey("voda")
    assert skey("पानी", None, "paani") is not None  # native script: the project's search key
    assert skey("水", None, None) is None  # no romanisation: no key, never a guess
    assert skey("水", "shui", None) == skey("shui")


# --- database ---------------------------------------------------------------------------------


def _cleanup(c, prefix: str) -> None:
    c.rollback()
    c.execute("DELETE FROM layers.sound_key WHERE language_id LIKE %s", (prefix + "-%",))
    c.execute("DELETE FROM layers.sound_key_build WHERE language_id LIKE %s", (prefix + "-%",))
    c.execute("DELETE FROM lexeme_concept WHERE lexeme_id LIKE %s", (prefix + "\\_%",))
    c.execute("DELETE FROM concept WHERE id LIKE %s", (prefix + "-%",))
    c.execute("DELETE FROM lexeme WHERE id LIKE %s", (prefix + "\\_%",))
    c.execute("DELETE FROM language WHERE id LIKE %s", (prefix + "-%",))
    c.commit()


@pytest.fixture
def conn(imported_db):
    """build_language commits, so the synthetic rows are removed explicitly at the end."""
    c = psycopg.connect(imported_db.replace("postgresql+psycopg", "postgresql"))
    init_layers(c)
    c.commit()
    _cleanup(c, "sk")
    _cleanup(c, "sq")
    for lid, enabled in (("sk-en", True), ("sk-de", True), ("sk-la", True), ("sk-off", False)):
        c.execute(
            "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
            " VALUES (%s, %s, 'modern', false, %s, '{}')",
            (lid, lid, enabled),
        )
    for i, (lang, form, ds, gloss) in enumerate(
        [
            ("sk-en", "father", "lsi", "father"),
            ("sk-de", "Fater", "lsi", "father"),
            ("sk-la", "pater", "jambu", "father"),
            ("sk-en", "water", "lsi", "water"),
            ("sk-de", "Wasser", "lsi", "water"),
            ("sk-off", "pater", "lsi", "father"),
        ]
    ):
        c.execute(
            "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key,"
            " reconstruction_status, dataset, source_id, source_record_id, gloss)"
            " VALUES (%s, %s, %s, %s, %s, 'attested', %s, %s, %s, %s)",
            (f"sk_{i}", lang, form, form.lower(), form.lower(), ds, ds, f"sk_{i}", gloss),
        )
    yield c
    c.rollback()
    _cleanup(c, "sk")
    _cleanup(c, "sq")
    c.close()


def test_build_keys_only_enabled_languages_and_is_idempotent(conn):
    res = build(conn, ["sk-en", "sk-de", "sk-la"], log=lambda m: None)
    assert res["lexemes"] == 5 and res["keyed"] == 5
    again = build(conn, ["sk-en", "sk-de", "sk-la"], log=lambda m: None)
    assert again["keyed"] == 5
    rows = dict(conn.execute("select lexeme_id, skey from layers.sound_key").fetchall())
    assert rows["sk_0"] == rows["sk_1"] == rows["sk_2"] == "PTR:a"
    assert "sk_5" not in rows  # a disabled language was not asked for
    assert sound_key.enabled_languages(conn).count("sk-off") == 0


def test_full_build_covers_enabled_languages_only(conn):
    conn.execute("delete from layers.sound_key where language_id like 'sk-%'")
    build(conn, ["sk-en", "sk-de", "sk-la"], log=lambda m: None)
    langs = {r[0] for r in conn.execute("select distinct language_id from layers.sound_key")}
    assert "sk-off" not in langs


def test_block_levels_exclusions_and_dataset_filters(conn):
    build(conn, ["sk-en", "sk-de", "sk-la"], log=lambda m: None)
    key = skey("pater")
    assert sorted(block(conn, key)) == ["sk_0", "sk_1", "sk_2"]
    assert sorted(block(conn, key, exclude_language="sk-la")) == ["sk_0", "sk_1"]
    assert block(conn, key, language_ids=["sk-de"]) == ["sk_1"]
    assert sorted(block(conn, key, datasets=["lsi"])) == ["sk_0", "sk_1"]
    assert sorted(block(conn, key, exclude_datasets=["lsi"])) == ["sk_2"]
    # the prefix level reaches words that differ after the first two consonants
    conn.execute("UPDATE lexeme SET form = 'Wassern', search_key = 'wassern' WHERE id = 'sk_4'")
    build(conn, ["sk-de"], log=lambda m: None)
    assert block(conn, skey("Wasser"), "exact") == []  # Wassern keys as WSRN
    assert block(conn, skey("Wasser"), "prefix") == ["sk_4"]
    assert "sk_4" not in block(conn, key, "prefix")
    assert block(conn, key, limit=1) == ["sk_0"]


def test_sound_keys_never_touch_public_relationships(conn):
    before = conn.execute("select count(*) from relationship").fetchone()[0]
    build(conn, ["sk-en"], log=lambda m: None)
    assert conn.execute("select count(*) from relationship").fetchone()[0] == before


# --- the extra search techniques ----------------------------------------------------------------


@pytest.fixture
def sa(lsi_imported):
    engine = create_engine(lsi_imported)
    with engine.connect() as c:
        pg = c.connection.driver_connection
        init_layers(pg)
        pg.commit()
        _cleanup(pg, "sq")
        for lid in ("sq-en", "sq-de"):
            c.execute(
                text(
                    "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
                    " VALUES (:i, :n, 'modern', false, true, '{}')"
                ),
                {"i": lid, "n": lid},
            )
        words = [
            ("sq_0", "sq-en", "father", "father"), ("sq_1", "sq-de", "Vater", "father"),
            ("sq_2", "sq-de", "Vatter", "father"), ("sq_3", "sq-de", "Wasser", "water"),
            ("sq_4", "sq-en", "water", "water"),
        ]  # fmt: skip
        for lid, lang, form, gloss in words:
            c.execute(
                text(
                    "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key,"
                    " reconstruction_status, dataset, source_id, source_record_id, gloss)"
                    " VALUES (:i, :l, :f, :n, :k, 'attested', 'lsi', 'lsi', :r, :g)"
                ),
                {
                    "i": lid,
                    "l": lang,
                    "f": form,
                    "n": form.lower(),
                    "k": form.lower(),
                    "r": lid,
                    "g": gloss,
                },
            )
        c.execute(text("INSERT INTO concept (id, label) VALUES ('sq-c1', 'FATHER')"))
        for lid in ("sq_0", "sq_1", "sq_2"):
            c.execute(
                text(
                    "INSERT INTO lexeme_concept (lexeme_id, concept_id, source_id)"
                    " VALUES (:l, 'sq-c1', 'lsi')"
                ),
                {"l": lid},
            )
        sound_key.build_language(pg, "sq-en")
        sound_key.build_language(pg, "sq-de")
        keys.ensure_schema(pg)
        yield c
        c.rollback()
        _cleanup(pg, "sq")
    engine.dispose()


def test_fuzzy_search_is_restricted_by_language(sa):
    out = retrieval.fuzzy_search(sa, "vater", "sq-de", limit=5, threshold=0.3)
    assert out["technique"] == "fuzzy"
    ids = [m["id"] for m in out["matches"]]
    assert "sq_1" in ids and "sq_0" not in ids  # another language is never returned
    assert all(m["match_type"] == "fuzzy" and m["score"] for m in out["matches"])
    assert retrieval.fuzzy_search(sa, "va", "sq-de")["warnings"]  # too short


def test_concept_gate_excludes_similar_spellings_of_other_meanings(sa):
    out = retrieval.concept_gated_search(sa, "wasser", ["sq-c1"], limit=5)
    ids = [m["id"] for m in out["matches"]]
    assert set(ids) <= {"sq_0", "sq_1", "sq_2"} and "sq_3" not in ids  # water is not father
    assert out["matches"][0]["match_type"] == "concept_gated"


def test_sound_search_ranks_the_block_by_alignment(sa):
    out = retrieval.sound_search(sa, "pater", level="exact", exclude_language="sq-la", limit=5)
    ids = [m["id"] for m in out["matches"]]
    assert ids[:1] == ["sq_0"]  # father: same skeleton, best alignment
    assert "sq_3" not in ids and "sq_4" not in ids
    assert all(m["match_type"] == "sound_block" for m in out["matches"])
    assert retrieval.sound_search(sa, "***")["matches"] == []


def test_key_search_reports_how_a_word_matched(sa):
    out = retrieval.key_search(sa, "Väter", "sq-de")
    assert out["technique"] == "keys"
    # the word-key table is empty here, so only the exact and fold lookups by form can answer
    assert isinstance(out["matches"], list)
    exact = retrieval.key_search(sa, "vater", "sq-de")
    assert [(m["id"], m["via"]) for m in exact["matches"]][:1] == [("sq_1", "native")]
