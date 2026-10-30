from pathlib import Path

from app.pipeline.languages import (
    Glottolog,
    canonicalize_languages,
    enable_searchable,
    import_glottolog_languages,
    is_historical,
    refresh_language_stats,
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
