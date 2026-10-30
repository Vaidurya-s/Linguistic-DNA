from pathlib import Path

from app.importers.wiktionary import import_wiktionary
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id

FIXTURE = Path(__file__).parent / "fixtures" / "wiktionary_mini"
CODES = {"hi": "hin", "sa": "san", "pa": "pan", "pra": "pra"}


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
        # 7 entries (6 configured + the Proto-Indo-Aryan reference entry; not the English
        # one) + 5 terms named only by templates (Proto-Indo-Iranian among them)
        assert stats["entries"] == 7 and stats["template_terms"] == 5
        # a Sauraseni Prakrit etymon lands on the Prakrit entry, the variety kept in the label;
        # the Prakrit line's nested English translation comes first and must not hide it
        aag = db.execute(
            "SELECT r.type_id, r.original_label, t.language_id FROM relationship r"
            " JOIN lexeme t ON t.id = r.target_lexeme_id WHERE r.source_lexeme_id = %s",
            (wid("hi", "आग"),),
        ).fetchone()
        assert aag == ("inherited_form", "{{inh}} (pra-sau)", "pra")
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


def test_template_terms_with_modifiers_lists_and_html():
    from app.importers.wiktionary import parse_terms, strip_html

    assert parse_terms("பட்டினம்<t:town>,பட்டி,பட்டு<t:hamlet, village>") == [
        ("பட்டினம்", "town", None),
        ("பட்டி", None, None),
        ("பட்டு", "hamlet, village", None),
    ]
    assert parse_terms("𑀕𑀪𑀺𑀦𑀻<ts:gabbhinī>") == [("𑀕𑀪𑀺𑀦𑀻", None, "gabbhinī")]
    assert parse_terms("*𑀲𑁂𑀓𑁆𑀓𑀇<alt:*सेक्कइ>") == [("*𑀲𑁂𑀓𑁆𑀓𑀇", None, None)]
    assert parse_terms('<i class="Latn mention" lang="en">tele-</i> + -scope') == []
    assert parse_terms("-") == []
    assert strip_html('feminine of <i class="Arab mention">فُلَان</i> (fulān)') == (
        "feminine of فُلَان (fulān)"
    )


def test_language_lists_bad_codes_script_names_and_proto_stars(db, tmp_path):
    import json

    lines = [
        {  # a nested mention pairs Konkani with a script label; it must not name the language
            "word": "जीभ",
            "lang": "Marathi",
            "lang_code": "mr",
            "descendants": [{"lang": "Balbodh script", "lang_code": "kok", "word": "x"}],
            "senses": [{"glosses": ["tongue"]}],
            "etymology_templates": [
                {"name": "cog", "args": {"1": "hi,kok", "2": "जीभ"}},
                {"name": "inh", "args": {"1": "mr", "2": "*-hō<pos", "3": "x"}},
                {"name": "inh", "args": {"1": "mr", "2": "dra-pro", "3": "pal"}},
            ],
        },
    ]
    path = tmp_path / "mr.jsonl"
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    try:
        import_wiktionary(db, [path], "fixture", {"mr": "mar", "hi": "hin"})
        langs = {
            r[0]: r[1]
            for r in db.execute(
                "SELECT g.id, g.name FROM lexeme l JOIN language g ON g.id = l.language_id"
                " WHERE l.dataset = 'wiktionary'"
            )
        }
        assert set(langs) == {"mar", "hin", "wkt-kok", "wkt-dra-pro"}  # no "wkt-*-hō<pos"
        assert langs["wkt-kok"] != "Balbodh script"
        proto = db.execute(
            "SELECT form FROM lexeme WHERE dataset = 'wiktionary' AND language_id = 'wkt-dra-pro'"
        ).fetchone()
        assert proto == ("*pal",)
    finally:
        db.rollback()


def test_form_of_and_etymology_only_filters(db, tmp_path):
    import json

    lines = [
        {
            "word": "вода",
            "lang": "Russian",
            "lang_code": "ru",
            "senses": [{"glosses": ["water"]}],
            "etymology_templates": [{"name": "inh", "args": {"1": "ru", "2": "orv", "3": "вода"}}],
        },
        {
            "word": "воды",
            "lang": "Russian",
            "lang_code": "ru",
            "senses": [{"glosses": ["genitive of вода"], "form_of": [{"word": "вода"}]}],
        },
        {"word": "vesi", "lang": "Finnish", "lang_code": "fi", "senses": [{"glosses": ["water"]}]},
        {
            "word": "jää",
            "lang": "Finnish",
            "lang_code": "fi",
            "senses": [{"glosses": ["ice"]}],
            "etymology_templates": [
                {"name": "inh", "args": {"1": "fi", "2": "urj-pro", "3": "*jäŋe"}}
            ],
        },
    ]
    path = tmp_path / "x.jsonl"
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    try:
        stats = import_wiktionary(
            db, [path], "fixture", {}, reference_codes=["ru"], etymology_only_codes=["fi"]
        )
        assert stats["skipped_form_of"] == 1 and stats["skipped_without_etymology"] == 1
        forms = {r[0] for r in db.execute("SELECT form FROM lexeme WHERE dataset = 'wiktionary'")}
        assert forms == {"вода", "jää", "*jäŋe"}  # plus their etymons' terms
    finally:
        db.rollback()


def test_all_languages_descendants_and_etymon_template(db, tmp_path):
    """The English "fuck" pattern: an {{etymon}} chain, plain templates, a cognate, and a
    Descendants list of borrowings; with all_languages no code needs to be configured."""
    import json

    lines = [
        {
            "word": "fuck",
            "lang": "English",
            "lang_code": "en",
            "pos": "verb",
            "senses": [{"glosses": ["To have sexual intercourse."]}],
            "etymology_templates": [
                {
                    "name": "etymon",
                    "args": {"1": "en", "id": "copulate", "2": ":inh", "3": "enm:*fukken<id:x>"},
                },
                {"name": "inh", "args": {"1": "en", "2": "enm", "3": "*fukken"}},
                {"name": "der", "args": {"1": "en", "2": "gem-pro", "3": "*fukkōną"}},
                {"name": "cog", "args": {"1": "sco", "2": "fuk"}},
            ],
        },
        {  # a homograph on the same page: one record, glosses merged
            "word": "fuck",
            "lang": "English",
            "lang_code": "en",
            "pos": "intj",
            "senses": [{"glosses": ["Expressing anger."]}],
            "descendants": [
                {"lang": "Tok Pisin", "lang_code": "tpi", "word": "fak"},
                {"lang": "Afrikaans", "lang_code": "af", "word": "fok", "raw_tags": ["borrowed"]},
                {"lang_code": "ja", "lang": "Japanese", "raw_tags": ["borrowed"]},
                {
                    "lang": "Russian",
                    "lang_code": "ru",
                    "word": "фак",
                    "raw_tags": ["borrowed"],
                    "roman": "fak",
                    "descendants": [{"lang": "Ukrainian", "lang_code": "uk", "word": "фак"}],
                },
            ],
        },
        {
            "word": "ficken",
            "lang": "German",
            "lang_code": "de",
            "senses": [{"glosses": ["to fuck"]}],
            "etymology_templates": [{"name": "sl", "args": {"1": "de", "2": "en", "3": "fuck"}}],
        },
        {
            "word": "fukkōną",
            "lang": "Proto-Germanic",
            "lang_code": "gem-pro",
            "original_title": "Reconstruction:Proto-Germanic/fukkōną",
            "senses": [{"glosses": ["to strike"]}],
            "descendants": [{"lang": "Old Norse", "lang_code": "non", "word": "*fokka"}],
        },
    ]
    path = tmp_path / "all.jsonl"
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    try:
        stats = import_wiktionary(db, [path], "fixture", {}, all_languages=True)
        fuck = wid("en", "fuck")
        assert db.execute("SELECT gloss FROM lexeme WHERE id = %s", (fuck,)).fetchone() == (
            "To have sexual intercourse.; Expressing anger.",
        )
        assert edge(db, fuck, wid("enm", "fukken")) == "inherited_form"  # once, not twice
        assert stats["inherited_form"] == 4  # fukken, Tok Pisin fak, Ukrainian фак, Norse *fokka
        assert edge(db, fuck, wid("gem-pro", "fukkōną")) == "etymon"
        # the Proto-Germanic entry and the template's term are one record, with its gloss
        assert db.execute(
            "SELECT form, gloss, reconstruction_status::text FROM lexeme WHERE id = %s",
            (wid("gem-pro", "fukkōną"),),
        ).fetchone() == ("*fukkōną", "to strike", "reconstructed")
        assert edge(db, wid("af", "fok"), fuck) == "borrowed_from"
        assert edge(db, wid("tpi", "fak"), fuck) == "inherited_form"
        assert edge(db, wid("uk", "фак"), wid("ru", "фак")) == "inherited_form"  # nested
        assert edge(db, wid("de", "ficken"), fuck) == "calque_or_loan_translation"
        assert db.execute(
            "SELECT transliteration FROM lexeme WHERE id = %s", (wid("ru", "фак"),)
        ).fetchone() == ("fak",)
        cite = db.execute(
            "SELECT e.citation FROM evidence e JOIN relationship r ON r.id = e.relationship_id"
            " WHERE r.source_lexeme_id = %s",
            (wid("af", "fok"),),
        ).fetchone()
        assert cite == ("Wiktionary, “fuck”, descendants ({{desc}})",)
        locator = db.execute(
            "SELECT e.locator FROM evidence e JOIN relationship r ON r.id = e.relationship_id"
            " WHERE r.source_lexeme_id = %s",
            (wid("non", "fokka"),),
        ).fetchone()
        assert locator == ("https://en.wiktionary.org/wiki/Reconstruction:Proto-Germanic/fukkōną",)
        langs = {r[0] for r in db.execute("SELECT DISTINCT language_id FROM lexeme")}
        assert {"wkt-en", "wkt-gem-pro", "wkt-sco", "wkt-tpi"} <= langs
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
