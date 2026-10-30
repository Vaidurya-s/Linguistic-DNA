from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id
from tests.conftest import run_fixture_import

SENTINEL = "FIXTURE_SENTINEL_ETYMOLOGY_MUST_NOT_BE_STORED"


def scalar(db, sql, *params):
    return db.execute(sql, params).fetchone()[0]


def test_counts(db):
    assert scalar(db, "SELECT count(*) FROM lexeme") == 29
    assert scalar(db, "SELECT count(*) FROM relationship") == 24
    assert scalar(db, "SELECT count(*) FROM relationship WHERE type_id = 'inherited_form'") == 22


def test_verbatim_text_is_never_stored(db):
    for table in ("lexeme", "relationship", "evidence", "source", "concept", "import_batch"):
        hits = scalar(db, f"SELECT count(*) FROM {table} t WHERE t::text LIKE %s", f"%{SENTINEL}%")
        assert hits == 0, table


def test_raw_form_kept_alongside_normalized(db):
    form, normalized = db.execute(
        "SELECT form, normalized_form FROM lexeme WHERE source_record_id = 'f_44lgs3q4625bk'"
    ).fetchone()
    assert form == "dāt̃ "  # trailing space as in the source
    assert normalized == "dāt̃"


def test_borrowing_direction_child_to_donor(db):
    row = db.execute(
        """SELECT s.form, t.form, r.direction, r.original_label FROM relationship r
           JOIN lexeme s ON s.id = r.source_lexeme_id JOIN lexeme t ON t.id = r.target_lexeme_id
           WHERE r.type_id = 'borrowed_from'"""
    ).fetchall()
    assert row == [("sottu", "svatva-", "directed", "borrowed")]


def test_reconstruction_flags(db):
    status = dict(db.execute("SELECT form, reconstruction_status FROM lexeme").fetchall())
    assert status["*ōṭu"] == "reconstructed"
    assert status["Hdántas"] == "reconstructed"  # Proto-Indo-Iranian
    assert status["dánta"] == "attested"


def test_evidence_keeps_locator_or_marks_inheritance(db):
    own = db.execute(
        """SELECT e.citation, e.locator, e.evidence_note FROM evidence e
           JOIN relationship r ON r.id = e.relationship_id
           JOIN lexeme c ON c.id = r.source_lexeme_id
           WHERE c.source_record_id = 'f_k6wca7tdsaloe'"""
    ).fetchall()
    assert own == [("CDIAL", "6152", None)]
    inherited = db.execute(
        """SELECT e.source_id, e.evidence_note FROM evidence e
           JOIN relationship r ON r.id = e.relationship_id
           JOIN lexeme c ON c.id = r.source_lexeme_id
           WHERE c.source_record_id = 'f_7wvogd6uksgji'"""
    ).fetchall()
    assert inherited and all(note and "child form" in note for _, note in inherited)


def test_sources_map_to_manifest(db):
    assert scalar(db, "SELECT source_id FROM lexeme WHERE source_record_id = '6152'") == "cdial"
    assert scalar(db, "SELECT reuse_status FROM source WHERE id = 'cdial'") == "permission_required"


def test_glottocode_shared_by_two_languages_and_classified(db):
    assert scalar(db, "SELECT count(*) FROM language WHERE glottocode = 'sans1269'") == 2
    assert scalar(db, "SELECT family_id FROM language WHERE id = 'tam'") == "drav1251"
    assert scalar(db, "SELECT family_id FROM language WHERE id = 'hin'") == "indo1319"


def test_ids_stable_across_reimport(imported_db, db):
    before = {r[0] for r in db.execute("SELECT id FROM lexeme UNION SELECT id FROM relationship")}
    run_fixture_import(imported_db)
    after = {r[0] for r in db.execute("SELECT id FROM lexeme UNION SELECT id FROM relationship")}
    assert before == after
    assert lexeme_id("jambu", "6152") in after


def test_validation_passes_for_research_but_blocks_public_seed(db):
    dev = run_checks(db)
    assert dev["passed"], [c for c in dev["checks"] if not c["passed"]]
    research = run_checks(db, research=True)  # Jambu is RESEARCH USE: allowed, cited
    assert research["passed"], [c for c in research["checks"] if not c["passed"]]
    public = run_checks(db, public_seed=True)
    failed = {c["name"] for c in public["checks"] if not c["passed"]}
    assert {"lexemes_not_redistributable", "relationships_not_redistributable"} <= failed


def test_research_validation_fails_on_blocked_data(db):
    db.execute("UPDATE dataset_audit SET decision = 'BLOCKED' WHERE id = 'jambu'")
    try:
        result = run_checks(db, research=True)
        failed = {c["name"] for c in result["checks"] if not c["passed"]}
        assert "lexemes_from_blocked_datasets" in failed
    finally:
        db.rollback()


def test_all_languages_keeps_unconfigured_forms_as_disabled_languages(imported_db, db):
    sindhi = lexeme_id("jambu", "f_fixturesindhi1")
    assert scalar(db, "SELECT count(*) FROM lexeme WHERE id = %s", sindhi) == 0  # default scope
    try:
        run_fixture_import(imported_db, all_languages=True)
        db.rollback()  # fresh snapshot
        lang = db.execute(
            "SELECT g.id, g.role, g.is_enabled FROM lexeme l JOIN language g"
            " ON g.id = l.language_id WHERE l.id = %s",
            (sindhi,),
        ).fetchone()
        assert lang == ("jb-s", "other", False)
        assert (
            scalar(
                db,
                "SELECT count(*) FROM relationship WHERE source_lexeme_id = %s"
                " AND target_lexeme_id = %s",
                sindhi,
                lexeme_id("jambu", "6152"),
            )
            == 1
        )
        assert run_checks(db, research=True)["passed"]
    finally:
        run_fixture_import(imported_db)
