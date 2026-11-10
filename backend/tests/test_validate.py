"""The informational data-quality checks: each flags its violation and blocks nothing."""

import pytest

from app.pipeline.validate import CHECKS, run_checks

NEW_CHECKS = [
    "mutual_ancestry_pairs",
    "conflicting_ancestry_types",
    "searchable_language_empty_search_key",
    "markup_in_forms_and_glosses",
    "markup_in_citations",
    "citation_is_bare_source_key",
    "ancestor_inherited_from_descendant",
]


def violations(db, name: str) -> int:
    check = next(c for c in run_checks(db, research=True)["checks"] if c["name"] == name)
    return check["violations"]


def add_language(db, lid: str, name: str, role: str = "modern", enabled: bool = True) -> None:
    db.execute(
        "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
        " VALUES (%s, %s, %s, false, %s, '{}')",
        (lid, name, role, enabled),
    )


def add_lexeme(
    db, lid: str, lang: str, form: str = "word", gloss: str | None = "a word", key: str = "word"
) -> None:
    db.execute(
        "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key, gloss,"
        " reconstruction_status, dataset, source_id, source_record_id)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'attested', 'jambu', 'jambu', %s)",
        (lid, lang, form, form, key, gloss, lid),
    )


def add_edge(db, rid: str, src: str, tgt: str, type_id: str, citation: str = "Smith 1990, p. 3"):
    db.execute(
        "INSERT INTO relationship (id, source_lexeme_id, target_lexeme_id, type_id, direction,"
        " status, source_id, dataset) VALUES (%s, %s, %s, %s, 'directed', 'documented', 'jambu',"
        " 'jambu')",
        (rid, src, tgt, type_id),
    )
    db.execute(
        "INSERT INTO evidence (relationship_id, source_id, citation) VALUES (%s, 'jambu', %s)",
        (rid, citation),
    )


@pytest.fixture
def rows(db):
    """Two modern languages and a few lexemes, rolled back after the test."""
    add_language(db, "vt-a", "Testish")
    add_language(db, "vt-b", "Otherish")
    add_lexeme(db, "vt_a1", "vt-a")
    add_lexeme(db, "vt_a2", "vt-a")
    add_lexeme(db, "vt_b1", "vt-b")
    yield db
    db.rollback()


def test_new_checks_are_info_and_unique():
    names = [c.name for c in CHECKS]
    assert len(names) == len(set(names))
    by_name = {c.name: c for c in CHECKS}
    for name in NEW_CHECKS:
        assert by_name[name].severity == "info"
        assert by_name[name].description


def test_clean_fixture_data_has_no_violations(db):
    for name in NEW_CHECKS:
        assert violations(db, name) == 0, name


@pytest.mark.parametrize("type_id", ["inherited_form", "borrowed_from", "etymon"])
def test_mutual_ancestry_pairs(rows, type_id):
    add_edge(rows, "vt_e1", "vt_a1", "vt_b1", type_id)
    assert violations(rows, "mutual_ancestry_pairs") == 0
    add_edge(rows, "vt_e2", "vt_b1", "vt_a1", type_id)
    assert violations(rows, "mutual_ancestry_pairs") == 1  # one cycle, counted once


def test_mutual_pair_of_different_types_is_not_a_cycle(rows):
    add_edge(rows, "vt_e1", "vt_a1", "vt_b1", "inherited_form")
    add_edge(rows, "vt_e2", "vt_b1", "vt_a1", "borrowed_from")
    assert violations(rows, "mutual_ancestry_pairs") == 0


def test_mutual_pair_of_non_ancestry_type_is_ignored(rows):
    add_edge(rows, "vt_e1", "vt_a1", "vt_b1", "derived_form")
    add_edge(rows, "vt_e2", "vt_b1", "vt_a1", "derived_form")
    assert violations(rows, "mutual_ancestry_pairs") == 0


@pytest.mark.parametrize("other", ["borrowed_from", "calque_or_loan_translation"])
def test_conflicting_ancestry_types(rows, other):
    add_edge(rows, "vt_e1", "vt_a1", "vt_b1", "inherited_form")
    assert violations(rows, "conflicting_ancestry_types") == 0
    add_edge(rows, "vt_e2", "vt_a1", "vt_b1", other)
    assert violations(rows, "conflicting_ancestry_types") == 1


def test_same_type_twice_or_other_pair_is_not_a_conflict(rows):
    add_edge(rows, "vt_e1", "vt_a1", "vt_b1", "inherited_form")
    add_edge(rows, "vt_e2", "vt_a2", "vt_b1", "borrowed_from")  # different pair
    add_edge(rows, "vt_e3", "vt_a1", "vt_b1", "etymon")  # not a conflicting type
    assert violations(rows, "conflicting_ancestry_types") == 0


def test_searchable_language_empty_search_key(rows):
    add_language(rows, "vt-off", "Hiddenish", enabled=False)
    add_lexeme(rows, "vt_off1", "vt-off", key="")  # not searchable: ignored
    assert violations(rows, "searchable_language_empty_search_key") == 0
    add_lexeme(rows, "vt_empty", "vt-a", key="")
    assert violations(rows, "searchable_language_empty_search_key") == 1


@pytest.mark.parametrize(
    "form, gloss",
    [
        ("{{l|en|word}}", "ok"),
        ("word", "see [[water]]"),
        ("word", "a {{gloss}} b"),
        ("fish &amp; chips", "ok"),
        ("word", "less &lt; more"),
        ("word", "&#233;"),
        ("wor]]d", None),
    ],
)
def test_markup_in_forms_and_glosses(rows, form, gloss):
    assert violations(rows, "markup_in_forms_and_glosses") == 0
    add_lexeme(rows, "vt_markup", "vt-a", form=form, gloss=gloss, key="x")
    assert violations(rows, "markup_in_forms_and_glosses") == 1


def test_infix_notation_and_plain_ampersand_are_not_markup(rows):
    add_lexeme(rows, "vt_infix", "vt-a", form="k<um>ain", gloss="eat <v.> R&D", key="kain")
    add_lexeme(rows, "vt_amp", "vt-a", form="a&b", gloss="x & y", key="ab")
    assert violations(rows, "markup_in_forms_and_glosses") == 0


def test_markup_in_citations(rows):
    add_edge(rows, "vt_e1", "vt_a1", "vt_b1", "inherited_form")
    assert violations(rows, "markup_in_citations") == 0
    add_edge(rows, "vt_e2", "vt_a2", "vt_b1", "inherited_form", citation="{{cite book|x}} p. 4")
    assert violations(rows, "markup_in_citations") == 1


@pytest.mark.parametrize("citation", ["dedr", "CDIAL", "strand", "jambu", "x"])
def test_citation_is_bare_source_key(rows, citation):
    add_edge(rows, "vt_e1", "vt_a1", "vt_b1", "inherited_form")
    assert violations(rows, "citation_is_bare_source_key") == 0
    add_edge(rows, "vt_e2", "vt_a2", "vt_b1", "inherited_form", citation=citation)
    assert violations(rows, "citation_is_bare_source_key") == 1


def test_real_citations_are_not_bare(rows):
    add_edge(rows, "vt_e1", "vt_a1", "vt_b1", "inherited_form", citation="Burrow 1984")
    add_edge(rows, "vt_e2", "vt_a2", "vt_b1", "inherited_form", citation="Turner-CDIAL-no-space")
    assert violations(rows, "citation_is_bare_source_key") == 0


def test_ancestor_inherited_from_descendant(rows):
    add_language(rows, "vt-pro", "Proto-Testish", role="reference")
    add_language(rows, "vt-old", "Old Testish", role="historical")
    add_lexeme(rows, "vt_p1", "vt-pro")
    add_lexeme(rows, "vt_o1", "vt-old")
    # entry -> ancestor, the normal direction: not flagged
    add_edge(rows, "vt_e1", "vt_a1", "vt_p1", "inherited_form")
    add_edge(rows, "vt_e2", "vt_o1", "vt_p1", "inherited_form")  # Old -> Proto: historical both
    assert violations(rows, "ancestor_inherited_from_descendant") == 0
    add_edge(rows, "vt_e3", "vt_p1", "vt_a1", "inherited_form")  # Proto -> modern
    assert violations(rows, "ancestor_inherited_from_descendant") == 1
    add_edge(rows, "vt_e4", "vt_o1", "vt_a2", "inherited_form")  # Old -> modern
    assert violations(rows, "ancestor_inherited_from_descendant") == 2
    add_edge(rows, "vt_e5", "vt_o1", "vt_b1", "borrowed_from")  # not inherited_form
    assert violations(rows, "ancestor_inherited_from_descendant") == 2


def test_new_checks_never_block(rows):
    add_language(rows, "vt-pro", "Proto-Testish", role="reference")
    add_lexeme(rows, "vt_p1", "vt-pro")
    add_lexeme(rows, "vt_bad", "vt-a", form="{{x}}", key="")
    add_edge(rows, "vt_e1", "vt_a1", "vt_b1", "inherited_form", citation="dedr")
    add_edge(rows, "vt_e2", "vt_b1", "vt_a1", "inherited_form", citation="{{c}}")
    add_edge(rows, "vt_e3", "vt_a1", "vt_b1", "borrowed_from")
    add_edge(rows, "vt_e4", "vt_p1", "vt_a2", "inherited_form")
    for kwargs in ({}, {"research": True}, {"public_seed": True}):
        result = run_checks(rows, **kwargs)
        by_name = {c["name"]: c for c in result["checks"]}
        for name in NEW_CHECKS:
            assert by_name[name]["violations"] >= 1, name
            assert by_name[name]["blocking"] is False, name
            assert by_name[name]["passed"] is True, name
    assert run_checks(rows, research=True)["passed"]
