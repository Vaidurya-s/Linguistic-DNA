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
            "Wiktionary, “पानी”, etymology (derived)",
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
        assert cite == ("Wiktionary, “fuck”, descendants",)
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


def test_unmarked_descendant_yields_to_the_descendants_own_etymology(db, tmp_path):
    """An unmarked {{desc}} only defaults to "inherited". When the descendant's own entry says
    it was borrowed (or merely derived), that statement wins and no inherited link remains;
    an unmarked descendant with no statement of its own stays inherited."""
    import json

    lines = [
        {
            "word": "câmara",
            "lang": "Portuguese",
            "lang_code": "pt",
            "senses": [{"glosses": ["chamber"]}],
            "descendants": [
                {"lang": "Hindi", "lang_code": "hi", "word": "kamra"},
                {"lang": "Marathi", "lang_code": "mr", "word": "khoṇa"},
                {"lang": "Kannada", "lang_code": "kn", "word": "kemre"},
            ],
        },
        {
            "word": "kamra",
            "lang": "Hindi",
            "lang_code": "hi",
            "senses": [{"glosses": ["room"]}],
            "etymology_templates": [{"name": "bor", "args": {"1": "hi", "2": "pt", "3": "câmara"}}],
        },
        {
            "word": "kemre",
            "lang": "Kannada",
            "lang_code": "kn",
            "senses": [{"glosses": ["room"]}],
            "etymology_templates": [{"name": "der", "args": {"1": "kn", "2": "pt", "3": "câmara"}}],
        },
    ]
    path = tmp_path / "desc.jsonl"
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    try:
        import_wiktionary(db, [path], "fixture", {}, all_languages=True)
        pt = wid("pt", "câmara")
        for child, expected in (
            (wid("hi", "kamra"), "borrowed_from"),
            (wid("kn", "kemre"), "etymon"),
            (wid("mr", "khoṇa"), "inherited_form"),
        ):
            rows = db.execute(
                "SELECT type_id FROM relationship WHERE source_lexeme_id = %s"
                " AND target_lexeme_id = %s",
                (child, pt),
            ).fetchall()
            assert rows == [(expected,)]
    finally:
        db.rollback()


def _run(db, tmp_path, lines, **kw):
    import json

    path = tmp_path / "x.jsonl"
    path.write_text("\n".join(json.dumps(x, ensure_ascii=False) for x in lines), encoding="utf-8")
    return import_wiktionary(db, [path], "fixture", {}, all_languages=True, **kw)


def _types(db, child, parent):
    return [
        r[0]
        for r in db.execute(
            "SELECT type_id FROM relationship WHERE source_lexeme_id = %s"
            " AND target_lexeme_id = %s ORDER BY type_id",
            (child, parent),
        ).fetchall()
    ]


def test_entry_etymology_text_decides_an_unmarked_descendant(db, tmp_path):
    """Hindi कमरा: the Portuguese page lists it under Descendants with no tag, and the Hindi
    entry has no template, but its own etymology sentence says "Borrowed from"."""
    lines = [
        {
            "word": "câmara",
            "lang": "Portuguese",
            "lang_code": "pt",
            "senses": [{"glosses": ["chamber"]}],
            "descendants": [
                {"lang": "Hindi", "lang_code": "hi", "word": "kamra"},
                {"lang": "Marathi", "lang_code": "mr", "word": "khoṇa"},
                {"lang": "Tamil", "lang_code": "ta", "word": "araiyā"},
            ],
        },
        {
            "word": "kamra",
            "lang": "Hindi",
            "lang_code": "hi",
            "senses": [{"glosses": ["room"]}],
            "etymology_text": "Borrowed from Portuguese câmara, from Latin camera.",
        },
        {
            "word": "khoṇa",
            "lang": "Marathi",
            "lang_code": "mr",
            "senses": [{"glosses": ["x"]}],
            "etymology_text": "Inherited from Old Marathi.",
        },
        {  # two etymologies on one page, one borrowed and one inherited: ambiguous, so unchanged
            "word": "araiyā",
            "lang": "Tamil",
            "lang_code": "ta",
            "senses": [{"glosses": ["a"]}],
            "etymology_text": "Borrowed from X.",
        },
        {
            "word": "araiyā",
            "lang": "Tamil",
            "lang_code": "ta",
            "senses": [{"glosses": ["b"]}],
            "etymology_text": "Inherited from Old Tamil.",
        },
    ]
    try:
        stats = _run(db, tmp_path, lines)
        pt = wid("pt", "câmara")
        assert _types(db, wid("hi", "kamra"), pt) == ["borrowed_from"]
        assert _types(db, wid("mr", "khoṇa"), pt) == ["inherited_form"]
        assert _types(db, wid("ta", "araiyā"), pt) == ["inherited_form"]
        assert stats["links_retyped_borrowed_by_etymology_text"] == 1
        cite, label = db.execute(
            "SELECT e.citation, r.original_label FROM evidence e JOIN relationship r"
            " ON r.id = e.relationship_id WHERE r.source_lexeme_id = %s",
            (wid("hi", "kamra"),),
        ).fetchone()
        assert cite == "Wiktionary, “kamra”, etymology text (borrowing)".replace("kamra", "câmara")
        assert "{{" not in cite and label == "{{desc}} + entry etymology text"
    finally:
        db.rollback()


def test_contradicting_descendant_lines_leave_no_false_cycle(db, tmp_path):
    """Two pages that each list the other as a descendant: no link either way. When one side
    states its own {{inh}}, that statement is kept."""
    lines = [
        {
            "word": "a",
            "lang": "Alpha",
            "lang_code": "aaa",
            "senses": [{"glosses": ["a"]}],
            "descendants": [{"lang": "Beta", "lang_code": "bbb", "word": "b"}],
        },
        {
            "word": "b",
            "lang": "Beta",
            "lang_code": "bbb",
            "senses": [{"glosses": ["b"]}],
            "descendants": [{"lang": "Alpha", "lang_code": "aaa", "word": "a"}],
        },
        {
            "word": "c",
            "lang": "Alpha",
            "lang_code": "aaa",
            "senses": [{"glosses": ["c"]}],
            "etymology_templates": [{"name": "inh", "args": {"1": "aaa", "2": "bbb", "3": "d"}}],
        },
        {
            "word": "d",
            "lang": "Beta",
            "lang_code": "bbb",
            "senses": [{"glosses": ["d"]}],
            "descendants": [{"lang": "Alpha", "lang_code": "aaa", "word": "c"}],
        },
        {  # d's page also claims c is the ancestor of d: contradicts c's own {{inh}}
            "word": "c",
            "lang": "Alpha",
            "lang_code": "aaa",
            "senses": [{"glosses": ["c2"]}],
            "descendants": [{"lang": "Beta", "lang_code": "bbb", "word": "d"}],
        },
    ]
    try:
        _run(db, tmp_path, lines)
        assert _types(db, wid("aaa", "a"), wid("bbb", "b")) == []
        assert _types(db, wid("bbb", "b"), wid("aaa", "a")) == []
        assert _types(db, wid("aaa", "c"), wid("bbb", "d")) == ["inherited_form"]  # own {{inh}}
        assert _types(db, wid("bbb", "d"), wid("aaa", "c")) == []  # reverse desc line dropped
    finally:
        db.rollback()


def test_proto_status_follows_the_language_name_not_the_code_suffix(db, tmp_path):
    lines = [
        {  # oc-pro is Provençal in the dump, not a reconstruction
            "word": "sota",
            "lang": "Provençal",
            "lang_code": "oc-pro",
            "senses": [{"glosses": ["under"]}],
        },
        {
            "word": "h₂ster",
            "lang": "Proto-Indo-European",
            "lang_code": "ine-pro",
            "senses": [{"glosses": ["star"]}],
        },
    ]
    try:
        _run(db, tmp_path, lines)
        assert db.execute(
            "SELECT form, reconstruction_status::text FROM lexeme WHERE id = %s",
            (wid("oc-pro", "sota"),),
        ).fetchone() == ("sota", "attested")
        assert db.execute(
            "SELECT form, reconstruction_status::text FROM lexeme WHERE id = %s",
            (wid("ine-pro", "h₂ster"),),
        ).fetchone() == ("*h₂ster", "reconstructed")
        protos = dict(db.execute("SELECT id, is_proto FROM language WHERE id LIKE 'wkt-%'"))
        assert protos == {"wkt-oc-pro": False, "wkt-ine-pro": True}
    finally:
        db.rollback()


def test_residue_in_forms_is_cleaned_and_placeholders_are_skipped(db, tmp_path):
    lines = [
        {
            "word": "ficken",
            "lang": "German",
            "lang_code": "de",
            "senses": [{"glosses": ["x"]}],
            "etymology_templates": [
                {"name": "cog", "args": {"1": "gem", "2": "adārum>>>, \u200bfoo\n>>"}},
            ],
        },
        {"word": "-", "lang": "German", "lang_code": "de", "senses": [{"glosses": ["dash"]}]},
        {
            "word": "ba\u200bd\ufffd",
            "lang": "German",
            "lang_code": "de",
            "senses": [{"glosses": ["ok"]}],
        },
    ]
    try:
        stats = _run(db, tmp_path, lines, fallback_names={"gem": "Germanic"})
        forms = {r[0] for r in db.execute("SELECT form FROM lexeme")}
        assert {"ficken", "adārum", "foo", "bad"} <= forms
        assert not any("\n" in f or ">" in f or "\u200b" in f for f in forms)
        assert "-" not in forms and stats["skipped_placeholder_form"] == 1
        assert db.execute("SELECT name FROM language WHERE id = 'wkt-gem'").fetchone() == (
            "Germanic",
        )
    finally:
        db.rollback()


def test_citations_never_show_raw_template_markup(db, tmp_path):
    lines = [
        {
            "word": "ficken",
            "lang": "German",
            "lang_code": "de",
            "senses": [{"glosses": ["x"]}],
            "etymology_templates": [
                {"name": "inh", "args": {"1": "de", "2": "gmh", "3": "ficken"}},
                {"name": "bor+", "args": {"1": "de", "2": "fr", "3": "foo"}},
                {"name": "af", "args": {"1": "de", "2": "a", "3": "b"}},
            ],
        }
    ]
    try:
        _run(db, tmp_path, lines)
        cites = {r[0] for r in db.execute("SELECT citation FROM evidence")}
        assert cites and not any("{{" in c or "}}" in c for c in cites)
        assert "Wiktionary, “ficken”, etymology (inherited)" in cites
        assert "Wiktionary, “ficken”, etymology (borrowed)" in cites
        labels = {r[0] for r in db.execute("SELECT original_label FROM relationship")}
        assert "{{inh}}" in labels  # the raw template stays where it is deliberate
    finally:
        db.rollback()


def test_ety_tree_template_and_tree_text_are_read(db, tmp_path):
    """Current Wiktionary writes {{ety|hi|:bor|pt:câmara}} and the entry text starts with an
    "Etymology tree" before the sentence "Borrowed from ..."."""
    lines = [
        {
            "word": "kamra",
            "lang": "Hindi",
            "lang_code": "hi",
            "senses": [{"glosses": ["room"]}],
            "etymology_text": "Etymology tree\nLatin camera\nPortuguese câmara\nHindi kamra\n"
            "Borrowed from Portuguese câmara.",
            "etymology_templates": [
                {"name": "ety", "args": {"1": "hi", "2": ":bor", "3": "pt:câmara", "tree": "1"}}
            ],
        },
        {
            "word": "dukaan",
            "lang": "Hindi",
            "lang_code": "hi",
            "senses": [{"glosses": ["shop"]}],
            "etymology_templates": [
                {
                    "name": "ety",
                    "args": {"1": "hi", "2": ":af<surf>", "3": "hi:duk", "4": "hi:aan"},
                },
                {"name": "ety", "args": {"1": "hi", "2": ":uder", "3": "fa:dukan"}},
                {"name": "ety", "args": {"1": "hi", "2": ":bor<unc>", "3": "ar:dukkan"}},
            ],
        },
        {  # the template-less variant: only the sentence after the tree says "Borrowed"
            "word": "mez",
            "lang": "Hindi",
            "lang_code": "hi",
            "senses": [{"glosses": ["table"]}],
            "etymology_text": "Etymology tree\nLatin mensa\nBorrowed from Portuguese mesa.",
        },
        {
            "word": "mesa",
            "lang": "Portuguese",
            "lang_code": "pt",
            "senses": [{"glosses": ["t"]}],
            "descendants": [{"lang": "Hindi", "lang_code": "hi", "word": "mez"}],
        },
    ]
    try:
        _run(db, tmp_path, lines)
        assert _types(db, wid("hi", "kamra"), wid("pt", "câmara")) == ["borrowed_from"]
        assert _types(db, wid("hi", "dukaan"), wid("hi", "duk")) == ["has_component"]
        assert _types(db, wid("hi", "dukaan"), wid("hi", "aan")) == ["has_component"]
        assert _types(db, wid("hi", "dukaan"), wid("fa", "dukan")) == ["etymon"]
        assert _types(db, wid("hi", "dukaan"), wid("ar", "dukkan")) == ["borrowed_from"]
        assert _types(db, wid("hi", "mez"), wid("pt", "mesa")) == ["borrowed_from"]
    finally:
        db.rollback()
