from pathlib import Path

from app.importers.cldf_wordlist import import_cldf_wordlist
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id

FIXTURE = Path(__file__).parent / "fixtures" / "lsi_mini"


def test_lsi_import_maps_doculects_and_concepts(db):
    stats = import_cldf_wordlist(db, FIXTURE, "lsi", "fixture")
    assert stats["doculects"] == 9  # 2 + 7 Tier 1 languages; Japanese is not configured
    rows = db.execute(
        """SELECT l.language_id, l.variety_id, l.form, c.label FROM lexeme l
           JOIN lexeme_concept lc ON lc.lexeme_id = l.id JOIN concept c ON c.id = lc.concept_id
           WHERE l.dataset = 'lsi' AND l.language_id = 'tam' ORDER BY c.label, l.form"""
    ).fetchall()
    assert ("tam", "lsi:TAMIL", "eindu", "FIVE") in rows
    assert (
        db.execute("SELECT count(*) FROM relationship WHERE dataset = 'lsi'").fetchone()[0] == 0
    )  # no cognate judgments in LSI: no invented links
    source = db.execute("SELECT reuse_status, dataset_id FROM source WHERE id = 'lsi'").fetchone()
    assert source == ("attribution_required", "lsi")


def test_lsi_rows_pass_public_seed_checks_on_their_own(db):
    import_cldf_wordlist(db, FIXTURE, "lsi", "fixture")
    blocked = db.execute(
        """SELECT count(*) FROM lexeme l JOIN dataset_audit d ON d.id = l.dataset
           WHERE l.dataset = 'lsi' AND d.decision = 'BLOCKED'"""
    ).fetchone()[0]
    assert blocked == 0
    assert run_checks(db)["passed"]


def test_cognate_sets_link_forms_across_languages(db):
    cognate = Path(__file__).parent / "fixtures" / "cognate_mini"
    try:
        configured_only = import_cldf_wordlist(db, cognate, "lsi", "fixture")
        assert configured_only["lexemes"] == 2 and configured_only["cognate_relationships"] == 1
        full = import_cldf_wordlist(db, cognate, "lsi", "fixture", all_languages=True)
        assert full["lexemes"] == 3 and full["cognate_relationships"] == 3
        english = db.execute(
            "SELECT g.id, g.is_enabled FROM lexeme l JOIN language g ON g.id = l.language_id"
            " WHERE l.form = 'tooth' AND l.dataset = 'lsi'"
        ).fetchone()
        assert english == ("gl-stan1293", False)
        cite = db.execute(
            "SELECT r.direction::text, e.citation FROM relationship r JOIN evidence e"
            " ON e.relationship_id = r.id WHERE r.dataset = 'lsi' LIMIT 1"
        ).fetchone()
        assert cite == ("undirected", "lsi, cognate set tooth-1")
    finally:
        db.rollback()


def test_spellings_from_each_cldf_layout():
    from app.importers.cldf_wordlist import spellings

    # NorthEuraLex: Value is the native spelling, Form is IPA
    assert spellings({"Value": "आँख", "Form": "ãːkʰ"}, None) == ("आँख", "आँख", "ãːkʰ")
    # IE-CoR: romanised Form with native_script and phon_form columns
    row = {"Value": "chāi", "Form": "chāi", "native_script": "ছাই", "phon_form": "tʃʰai"}
    assert spellings(row, None) == ("chāi", "ছাই", "tʃʰai")
    # LSI: romanised only; ASJP: a phonetic code kept as the form
    assert spellings({"Value": "pani", "Form": "pani"}, None) == ("pani", None, None)
    assert spellings({"Value": "pani", "Form": "p a n i"}, "ASJPcode") == ("pani", None, None)


def test_starred_forms_are_reconstructed(db, tmp_path):
    import shutil

    data = tmp_path / "cldf"
    shutil.copytree(Path(__file__).parent / "fixtures" / "cognate_mini", data)
    forms = (data / "forms.csv").read_text(encoding="utf-8").replace(",dā̃t,dā̃t,", ",*dā̃t,*dā̃t,")
    (data / "forms.csv").write_text(forms, encoding="utf-8")
    try:
        import_cldf_wordlist(db, data, "lsi", "fixture")
        status = db.execute(
            "SELECT reconstruction_status::text FROM lexeme WHERE form = '*dā̃t'"
        ).fetchone()
        assert status == ("reconstructed",)
    finally:
        db.rollback()


def test_large_cognate_sets_are_a_star_not_all_pairs(tmp_path):
    from app.importers.cldf_wordlist import cognate_rows
    from app.services.ids import lexeme_id

    path = tmp_path / "cognates.csv"
    path.write_text(
        "ID,Form_ID,Cognateset_ID\n" + "".join(f"c{i},f{i},s1\n" for i in range(8)),
        encoding="utf-8",
    )
    language_of = {lexeme_id("x", f"f{i}"): f"lang{i}" for i in range(8)}
    language_of[lexeme_id("x", "f5")] = "hin"
    language_of[lexeme_id("x", "f6")] = "ben"
    rels, evidence = cognate_rows(path, language_of, {"hin", "ben"}, "x", 1)
    # star of 7 spokes around a configured member, the hin-ben pair being one of them
    assert len(rels) == 7 and len(evidence) == 7
    hub = {r[1] for r in rels} & {r[2] for r in rels}
    ends = [m for r in rels for m in (r[1], r[2])]
    assert max(ends.count(m) for m in set(ends)) == 7  # one member touches every link
    assert len({(r[1], r[2]) for r in rels}) == 7 and hub is not None


def test_borrowing_table_gives_directed_borrowings(db, tmp_path):
    import shutil

    data = tmp_path / "cldf"
    shutil.copytree(Path(__file__).parent / "fixtures" / "cognate_mini", data)
    (data / "borrowings.csv").write_text(
        "ID,Target_Form_ID,Source_Form_ID,Source_word,Source_languoid_glottocode,Source_certain\n"
        "b1,Bengali-tooth,Hindi-tooth,,,true\n"  # source form in the dataset
        "b2,Hindi-tooth,,dantaḥ,sans1269,false\n"  # source named by word and glottocode
        "b3,Hindi-tooth,,x,zzzz9999,true\n",  # unknown language: skipped
        encoding="utf-8",
    )
    try:
        stats = import_cldf_wordlist(db, data, "lsi", "fixture")
        assert stats["borrowings"] == 2 and stats["borrowing_source_words"] == 1
        rows = set(
            db.execute(
                "SELECT s.form, t.form, t.language_id, r.notes FROM relationship r"
                " JOIN lexeme s ON s.id = r.source_lexeme_id"
                " JOIN lexeme t ON t.id = r.target_lexeme_id"
                " WHERE r.dataset = 'lsi' AND r.type_id = 'borrowed_from'"
            ).fetchall()
        )
        assert rows == {
            ("dãt", "dā̃t", "hin", None),
            ("dā̃t", "dantaḥ", "san", "source marked uncertain"),
        }
        status = db.execute(
            "SELECT reconstruction_status::text FROM lexeme WHERE form = 'dantaḥ'"
        ).fetchone()
        assert status == ("unknown",)  # named by the table, not attested by it
    finally:
        db.rollback()


def _cognate_copy(tmp_path):
    import shutil

    data = tmp_path / "cldf"
    shutil.copytree(Path(__file__).parent / "fixtures" / "cognate_mini", data)
    return data


def test_markup_entities_control_characters_and_placeholders_are_cleaned(db, tmp_path):
    data = _cognate_copy(tmp_path)
    (data / "forms.csv").write_text(
        "ID,Language_ID,Parameter_ID,Value,Form,Source,Loan\n"
        "Hindi-tooth,Hindi,tooth,&amp;quot;dā̃t&amp;quot;,,fixture,\n"
        "Bengali-tooth,Bengali,tooth,d\x07ãt​,,fixture,\n"
        "Hindi-dash,Hindi,tooth,-,,fixture,\n",
        encoding="utf-8",
    )
    (data / "cognates.csv").write_text(
        "ID,Form_ID,Cognateset_ID\nc1,Hindi-tooth,t1\nc2,Bengali-tooth,t1\nc3,Hindi-dash,t1\n",
        encoding="utf-8",
    )
    (data / "parameters.csv").write_text(
        "ID,Name,Concepticon_ID,Concepticon_Gloss\ntooth,<i>tooth</i> &amp;amp; fang,1380,TOOTH\n",
        encoding="utf-8",
    )
    try:
        stats = import_cldf_wordlist(db, data, "lsi", "fixture")
        assert stats["skipped_placeholder_form"] == 1 and stats["lexemes"] == 2
        rows = {
            r[0]: r[1:]
            for r in db.execute(
                "SELECT source_record_id, form, gloss FROM lexeme WHERE dataset = 'lsi'"
            )
        }
        assert rows == {
            "Hindi-tooth": ('"dā̃t"', "tooth & fang"),
            "Bengali-tooth": ("dãt", "tooth & fang"),
        }
        # the skipped form takes no cognate link with it
        assert stats["cognate_relationships"] == 1
        assert db.execute(
            "SELECT count(*) FROM relationship WHERE dataset = 'lsi' AND"
            " (source_lexeme_id = %s OR target_lexeme_id = %s)",
            (lexeme_id("lsi", "Hindi-dash"),) * 2,
        ).fetchone() == (0,)
    finally:
        db.rollback()


def test_infix_notation_is_kept(db, tmp_path):
    data = _cognate_copy(tmp_path)
    (data / "forms.csv").write_text(
        "ID,Language_ID,Parameter_ID,Value,Form,Source,Loan\n"
        "Hindi-tooth,Hindi,tooth,l<əm>idiʔ,,fixture,\n",
        encoding="utf-8",
    )
    try:
        import_cldf_wordlist(db, data, "lsi", "fixture")
        assert db.execute(
            "SELECT form FROM lexeme WHERE source_record_id = 'Hindi-tooth'"
        ).fetchone() == ("l<əm>idiʔ",)
    finally:
        db.rollback()


def test_placeholder_borrowing_source_words_are_skipped(db, tmp_path):
    data = _cognate_copy(tmp_path)
    (data / "borrowings.csv").write_text(
        "ID,Target_Form_ID,Source_Form_ID,Source_word,Source_languoid_glottocode,Source_certain\n"
        "b1,Hindi-tooth,,?,sans1269,true\n"
        "b2,Bengali-tooth,,&amp;quot;dantaḥ&amp;quot;,sans1269,true\n",
        encoding="utf-8",
    )
    try:
        stats = import_cldf_wordlist(db, data, "lsi", "fixture")
        assert stats["borrowings"] == 1 and stats["borrowing_source_words"] == 1
        assert stats["skipped_placeholder_form"] == 1
        assert db.execute(
            "SELECT form FROM lexeme WHERE language_id = 'san' AND dataset = 'lsi'"
        ).fetchall() == [('"dantaḥ"',)]
    finally:
        db.rollback()
