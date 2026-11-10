from pathlib import Path

from app.pipeline.languages import (
    Glottolog,
    canonicalize_languages,
    enable_searchable,
    import_glottolog_languages,
    is_historical,
    may_merge,
    merge_duplicate_lexemes,
    refresh_language_stats,
    resolve_glottocode,
)


def glottolog_fixture(tmp_path: Path) -> Glottolog:
    d = tmp_path / "glottolog"
    d.mkdir()
    (d / "languages.csv").write_text(
        "ID,Name,Level,ISO639P3code,Language_ID\n"
        "indo1319,Indo-European,family,,\n"
        "germ1287,Germanic,family,,\n"
        "dutc1256,Dutch,language,nld,dutc1256\n"
        "holl1236,Hollandic,dialect,,dutc1256\n"
        "hind1269,Hindi,language,hin,hind1269\n",
        encoding="utf-8",
    )
    (d / "values.csv").write_text(
        "ID,Language_ID,Parameter_ID,Value\n"
        "dutc1256-c,dutc1256,classification,indo1319/germ1287\n"
        "hind1269-c,hind1269,classification,indo1319\n",
        encoding="utf-8",
    )
    return Glottolog(d)


def add_language(db, lid, name, glottocode=None, alias=None):
    db.execute(
        "INSERT INTO language (id, name, glottocode, role, is_proto, is_enabled, metadata_json)"
        " VALUES (%s, %s, %s, 'other', false, false, '{}')",
        (lid, name, glottocode),
    )
    if alias:
        db.execute(
            "INSERT INTO language_alias (language_id, scheme, value) VALUES (%s, %s, %s)",
            (lid, *alias),
        )


def test_historical_names():
    assert is_historical("Old Hindi") and is_historical("Middle Bengali")
    assert is_historical("Sauraseni Prakrit") and not is_historical("Bengali")


def test_one_record_per_language(db, tmp_path):
    glottolog = glottolog_fixture(tmp_path)
    try:
        stats = import_glottolog_languages(db, glottolog)
        assert stats["glottolog_languages"] == 1  # Dutch; Hindi is configured as 'hin'
        add_language(db, "wkt-nl", "Dutch", alias=("wiktionary", "nl"))
        add_language(db, "jb-holl", "Hollandic Dutch", glottocode="holl1236")
        add_language(db, "jb-oh", "Old Hindi", glottocode="hind1269")
        moved = db.execute("SELECT id FROM lexeme ORDER BY id LIMIT 2").fetchall()
        db.execute("UPDATE lexeme SET language_id = 'wkt-nl' WHERE id = %s", (moved[0][0],))
        db.execute("UPDATE lexeme SET language_id = 'jb-oh' WHERE id = %s", (moved[1][0],))

        result = canonicalize_languages(db, glottolog, {"nl": "nld"})
        assert result["merged_languages"] == 2 and result["kept_historical"] == 1
        row = db.execute(
            "SELECT language_id, variety_id FROM lexeme WHERE id = %s", (moved[0][0],)
        ).fetchone()
        assert row == ("gl-dutc1256", "wkt-nl")  # the source's own name survives as a variety
        assert db.execute(
            "SELECT language_id FROM lexeme WHERE id = %s", (moved[1][0],)
        ).fetchone() == ("jb-oh",)  # Old Hindi is not merged into modern Hindi
        gone = db.execute(
            "SELECT count(*) FROM language WHERE id IN ('wkt-nl', 'jb-holl')"
        ).fetchone()[0]
        assert gone == 0

        refresh_language_stats(db)
        enable_searchable(db, min_words=1)
        assert db.execute(
            "SELECT is_enabled, family_id FROM language WHERE id = 'gl-dutc1256'"
        ).fetchone() == (True, "indo1319")
    finally:
        db.rollback()


def variety_glottolog(tmp_path: Path) -> Glottolog:
    """French with Jerriais (own code nrf), Early Irish with Middle Irish (mga), Latvian with
    Standard Latvian, Yiddish, Sardinian, Malagasy, Zhuang, Gondi and Min Nan."""
    d = tmp_path / "glottolog_varieties"
    d.mkdir()
    (d / "languages.csv").write_text(
        "ID,Name,Level,ISO639P3code,Language_ID\n"
        "stan1290,French,language,fra,\n"
        "jerr1238,Jerriais,dialect,nrf,stan1290\n"
        "oldi1245,Early Irish,language,sga,\n"
        "midd1360,Middle Irish (10-12th century),dialect,mga,oldi1245\n"
        "lett1247,Latvian,language,lav,\n"
        "stan1325,Standard Latvian,dialect,lvs,lett1247\n"
        "mand1415,Mandarin Chinese,language,cmn,\n"
        "east2295,Eastern Yiddish,language,ydd,\n"
        "logu1236,Logudorese Sardinian,language,src,\n"
        "plat1254,Plateau Malagasy,language,plt,\n"
        "nong1247,Nong Zhuang,language,zhn,\n"
        "nort2702,Northern Gondi,language,gno,\n"
        "minn1241,Min Nan Chinese,language,nan,\n",
        encoding="utf-8",
    )
    (d / "values.csv").write_text("ID,Language_ID,Parameter_ID,Value\n", encoding="utf-8")
    return Glottolog(d)


PART1 = {
    "fr": "fra",
    "zh": "zho",
    "lv": "lav",
    "yi": "yid",
    "sc": "srd",
    "mg": "mlg",
    "za": "zha",
}


def resolve(glottolog: Glottolog, code: str) -> str | None:
    return resolve_glottocode(None, [("wiktionary", code)], glottolog, PART1)


def test_dialect_with_own_iso_code_stays_its_own_language(db, tmp_path):
    glottolog = variety_glottolog(tmp_path)
    assert resolve(glottolog, "fr") == "stan1290"
    assert resolve(glottolog, "nrf") is None  # Jerriais is not French
    assert resolve(glottolog, "mga") is None
    assert resolve(glottolog, "zh") == "mand1415" and resolve(glottolog, "cmn") == "mand1415"
    assert resolve(glottolog, "lv") == "lett1247"  # Standard Latvian is merged on purpose
    try:
        import_glottolog_languages(db, glottolog)
        add_language(db, "wkt-fr", "French", alias=("wiktionary", "fr"))
        add_language(db, "wkt-nrf", "Norman", alias=("wiktionary", "nrf"))
        add_language(db, "wkt-xno", "Anglo-Norman", alias=("wiktionary", "xno"))
        result = canonicalize_languages(db, glottolog, PART1)
        assert result["merged_languages"] == 1
        left = db.execute(
            "SELECT id FROM language WHERE id IN ('wkt-fr', 'wkt-nrf', 'wkt-xno') ORDER BY id"
        ).fetchall()
        assert left == [("wkt-nrf",), ("wkt-xno",)]
        assert db.execute("SELECT language_id FROM variety WHERE id = 'wkt-fr'").fetchone() == (
            "gl-stan1290",
        )
    finally:
        db.rollback()


def test_middle_irish_is_not_merged_into_early_irish(db, tmp_path):
    assert may_merge("Old Irish", "Early Irish") and may_merge("Early Irish", "Early Irish")
    assert not may_merge("Middle Irish", "Early Irish")
    assert not may_merge("Old Irish", "Irish") and not may_merge("Old Irish", "Middle Irish")
    assert may_merge("Irish", "Irish")
    glottolog = variety_glottolog(tmp_path)
    try:
        import_glottolog_languages(db, glottolog)
        # a source that names the dialect by its glottocode, as Jambu does
        add_language(db, "jb-mi", "Middle Irish", glottocode="midd1360")
        add_language(db, "jb-oi", "Old Irish", glottocode="oldi1245")
        result = canonicalize_languages(db, glottolog, {})
        assert result["kept_historical"] == 1 and result["merged_languages"] == 1
        left = db.execute("SELECT id FROM language WHERE id IN ('jb-mi', 'jb-oi')").fetchall()
        assert left == [("jb-mi",)]
    finally:
        db.rollback()


def test_macrolanguage_and_hyphenated_codes_resolve(tmp_path):
    glottolog = variety_glottolog(tmp_path)
    expected = {
        "yid": "east2295",
        "yi": "east2295",
        "srd": "logu1236",
        "sc": "logu1236",
        "mlg": "plat1254",
        "mg": "plat1254",
        "zha": "nong1247",
        "za": "nong1247",
        "gon": "nort2702",
        "nan-hbl": "minn1241",
    }
    assert {code: resolve(glottolog, code) for code in expected} == expected


def add_wiktionary_lexeme(db, lid: str, form: str, lang: str = "hin", gloss: str | None = "g"):
    db.execute(
        "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key, gloss,"
        " reconstruction_status, dataset, source_id, source_record_id)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'attested', 'wiktionary', 'jambu', %s)",
        (lid, lang, form, form, form, gloss, lid),
    )


def add_link(db, rid: str, src: str, tgt: str, type_id: str) -> None:
    db.execute(
        "INSERT INTO relationship (id, source_lexeme_id, target_lexeme_id, type_id, direction,"
        " status, source_id, dataset) VALUES (%s, %s, %s, %s, 'directed', 'documented', 'jambu',"
        " 'wiktionary')",
        (rid, src, tgt, type_id),
    )
    db.execute(
        "INSERT INTO evidence (relationship_id, source_id, citation) VALUES (%s, 'jambu', 'cite')",
        (rid,),
    )


def test_merge_duplicate_lexemes(db):
    try:
        type_id = db.execute("SELECT id FROM relationship_type LIMIT 1").fetchone()[0]
        db.execute("INSERT INTO concept (id, label) VALUES ('c_dup', 'dup')")
        add_wiktionary_lexeme(db, "lx_dup_a", "mot")  # the survivor: smallest id
        add_wiktionary_lexeme(db, "lx_dup_b", "mot")
        add_wiktionary_lexeme(db, "lx_dup_c", "mot", gloss="other sense")  # different gloss
        add_wiktionary_lexeme(db, "lx_dup_d", "tail")
        add_wiktionary_lexeme(db, "lx_dup_e", "root")
        db.execute("UPDATE lexeme SET dataset = 'jambu' WHERE id = 'lx_dup_e'")
        add_wiktionary_lexeme(db, "lx_dup_f", "root")  # same form as a non-wiktionary lexeme
        db.execute(
            "INSERT INTO lexeme_concept (lexeme_id, concept_id) VALUES ('lx_dup_b', 'c_dup')"
        )
        add_link(db, "rel_dup_1", "lx_dup_a", "lx_dup_d", type_id)
        add_link(db, "rel_dup_2", "lx_dup_b", "lx_dup_d", type_id)  # repeats rel_dup_1
        add_link(db, "rel_dup_3", "lx_dup_a", "lx_dup_b", type_id)  # becomes a self-loop
        add_link(db, "rel_dup_4", "lx_dup_d", "lx_dup_b", type_id)  # moves to lx_dup_a

        assert merge_duplicate_lexemes(db) == 1
        remaining = db.execute(
            "SELECT id FROM lexeme WHERE id LIKE 'lx_dup_%%' ORDER BY id"
        ).fetchall()
        assert [r[0] for r in remaining] == [f"lx_dup_{c}" for c in "acdef"]
        links = db.execute(
            "SELECT id, source_lexeme_id, target_lexeme_id FROM relationship"
            " WHERE id LIKE 'rel_dup_%%' ORDER BY id"
        ).fetchall()
        assert links == [
            ("rel_dup_1", "lx_dup_a", "lx_dup_d"),
            ("rel_dup_4", "lx_dup_d", "lx_dup_a"),
        ]
        evidence = db.execute(
            "SELECT relationship_id FROM evidence WHERE relationship_id LIKE 'rel_dup_%%'"
            " ORDER BY 1"
        ).fetchall()
        assert evidence == [("rel_dup_1",), ("rel_dup_4",)]
        assert db.execute(
            "SELECT lexeme_id FROM lexeme_concept WHERE concept_id = 'c_dup'"
        ).fetchall() == [("lx_dup_a",)]
        assert merge_duplicate_lexemes(db) == 0  # idempotent
        assert db.execute(
            "SELECT count(*) FROM relationship WHERE id LIKE 'rel_dup_%%'"
        ).fetchone() == (2,)
    finally:
        db.rollback()
