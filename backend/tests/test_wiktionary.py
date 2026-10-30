from pathlib import Path

from app.importers.wiktionary import import_wiktionary
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id

FIXTURE = Path(__file__).parent / "fixtures" / "wiktionary_mini"
CODES = {"hi": "hin", "sa": "san", "pa": "pan"}


def wid(code: str, term: str) -> str:
    return lexeme_id("wiktionary", f"{code}:{term}")


def edge(db, child: str, parent: str) -> str | None:
    row = db.execute(
        "SELECT type_id FROM relationship WHERE source_lexeme_id = %s AND target_lexeme_id = %s",
        (child, parent),
    ).fetchone()
    return row[0] if row else None


def test_wiktionary_entries_and_typed_etymologies(db):
    stats = import_wiktionary(
        db, sorted(FIXTURE.glob("*.jsonl")), "fixture", CODES, reference_codes={"inc-pro"}
    )
    try:
        # 5 entries (4 configured + the Proto-Indo-Aryan reference entry; not the English
        # one) + 5 terms named only by templates (Proto-Indo-Iranian among them)
        assert stats["entries"] == 5 and stats["template_terms"] == 5
        pani = wid("hi", "पानी")
        row = db.execute(
            "SELECT language_id, gloss, transliteration, reconstruction_status::text"
            " FROM lexeme WHERE id = %s",
            (pani,),
        ).fetchone()
        assert row == ("hin", "water", "pānī", "attested")
        assert edge(db, pani, wid("inc-pro", "pāníyam")) == "inherited_form"
        assert edge(db, pani, wid("sa", "पानीय")) == "etymon"
        assert edge(db, wid("hi", "जलमार्ग"), wid("hi", "जल")) == "has_component"
        assert edge(db, wid("hi", "कंप्यूटर"), wid("en", "computer")) == "borrowed_from"
        # the Sanskrit entry and the term the Hindi template names are one record
        assert edge(db, wid("sa", "पानीय"), wid("inc-pro", "pāníyam")) == "inherited_form"
        cognate = db.execute(
            "SELECT direction::text FROM relationship WHERE type_id = 'cognate'"
            " AND dataset = 'wiktionary'"
        ).fetchone()
        assert cognate == ("undirected",)
        proto = db.execute(
            "SELECT g.id, g.name, g.is_enabled, l.reconstruction_status::text FROM lexeme l"
            " JOIN language g ON g.id = l.language_id WHERE l.id = %s",
            (wid("inc-pro", "pāníyam"),),
        ).fetchone()
        assert proto == ("wkt-inc-pro", "Proto-Indo-Aryan", False, "reconstructed")
        # the reference entry's own etymology continues the chain
        assert edge(db, wid("inc-pro", "pāníyam"), wid("iir-pro", "paHníyam")) == "inherited_form"
        cite = db.execute(
            "SELECT e.citation, e.locator FROM evidence e JOIN relationship r"
            " ON r.id = e.relationship_id WHERE r.source_lexeme_id = %s AND r.type_id = 'etymon'",
            (pani,),
        ).fetchone()
        assert cite == (
            "Wiktionary, “पानी”, etymology ({{der}})",
            "https://en.wiktionary.org/wiki/पानी",
        )
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
