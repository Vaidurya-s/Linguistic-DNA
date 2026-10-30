import json

from app.importers.wikidata_lexemes import import_wikidata_lexemes
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id


def lexeme(lid: str, lang: str, code: str, lemma: str, gloss: str, derived: str = "") -> dict:
    claims = {}
    if derived:
        claims["P5191"] = [
            {
                "id": f"{lid}$1",
                "mainsnak": {
                    "snaktype": "value",
                    "datavalue": {"value": {"id": derived}},
                },
            }
        ]
    return {
        "id": lid,
        "language": lang,
        "lemmas": {code: {"value": lemma}},
        "senses": [{"glosses": {"en": {"value": gloss}}}],
        "claims": claims,
    }


def test_all_languages_keeps_every_lexeme(db, tmp_path):
    dump = tmp_path / "lexemes.json"
    dump.write_text(
        "[\n"
        + ",\n".join(
            json.dumps(x, ensure_ascii=False)
            for x in (
                lexeme("L901", "Q1860", "en", "fuck", "to have sex", derived="L902"),
                lexeme("L902", "Q42365", "ang", "fuccian", "to strike"),
                lexeme("L903", "Q9299", "sr-el", "voda", "water"),
            )
        )
        + "\n]\n",
        encoding="utf-8",
    )
    try:
        # Serbian is resolved through its lemma code ("sr-el" counts as "sr")
        stats = import_wikidata_lexemes(db, dump, "fixture", {"sr": "hin"}, all_languages=True)
        assert stats["target_lexemes"] == 3 and stats["etymon"] == 1
        langs = dict(
            db.execute(
                "SELECT source_record_id, language_id FROM lexeme"
                " WHERE dataset = 'wikidata-lexemes'"
            ).fetchall()
        )
        assert langs == {"L901": "wd-q1860", "L902": "wd-q42365", "L903": "hin"}
        row = db.execute(
            "SELECT type_id FROM relationship WHERE source_lexeme_id = %s"
            " AND target_lexeme_id = %s",
            (lexeme_id("wikidata-lexemes", "L901"), lexeme_id("wikidata-lexemes", "L902")),
        ).fetchone()
        assert row == ("etymon",)
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
