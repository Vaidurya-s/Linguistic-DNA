"""The info check oversized_cognate_component counts flagged cognate edges and blocks nothing."""

import pytest

from app.layers import hub
from app.pipeline.validate import CHECKS, run_checks

DS = "valhubtest"
NAME = "oversized_cognate_component"


def violations(db) -> int:
    check = next(c for c in run_checks(db, research=True)["checks"] if c["name"] == NAME)
    assert check["passed"] and not check["blocking"]
    return check["violations"]


def test_check_is_info_and_unique():
    named = [c for c in CHECKS if c.name == NAME]
    assert len(named) == 1 and named[0].severity == "info" and named[0].description
    assert len({c.name for c in CHECKS}) == len(CHECKS)


@pytest.fixture
def chain(db):
    """Eight words chained by seven cognate links, and one separate pair."""
    db.execute(
        "INSERT INTO language (id, name, role, is_proto, is_enabled, metadata_json)"
        " VALUES ('hbv-a', 'hbv-a', 'modern', false, true, '{}') ON CONFLICT DO NOTHING"
    )
    for i in range(10):
        db.execute(
            "INSERT INTO lexeme (id, language_id, form, normalized_form, search_key,"
            " reconstruction_status, dataset, source_id, source_record_id)"
            " VALUES (%s, 'hbv-a', %s, %s, %s, 'attested', %s, 'jambu', %s)",
            (f"vh_{i}", f"w{i}", f"w{i}", f"w{i}", DS, f"vh_{i}"),
        )
    pairs = [(i, i + 1) for i in range(7)] + [(8, 9)]
    for n, (a, b) in enumerate(pairs):
        db.execute(
            "INSERT INTO relationship (id, source_lexeme_id, target_lexeme_id, type_id, direction,"
            " status, source_id, dataset) VALUES (%s, %s, %s, 'cognate', 'undirected',"
            " 'documented', 'jambu', %s)",
            (f"vh_e{n}", f"vh_{a}", f"vh_{b}", DS),
        )
    db.commit()
    yield db
    db.execute("DROP TABLE IF EXISTS layers.edge_hub_flag CASCADE")
    db.execute("DELETE FROM lexeme WHERE dataset = %s", (DS,))
    db.execute("DELETE FROM language WHERE id = 'hbv-a'")
    db.commit()


def test_zero_without_the_layer_then_counts_flagged_edges(chain):
    chain.execute("DROP SCHEMA IF EXISTS layers CASCADE")
    chain.commit()
    assert violations(chain) == 0  # layer not built: nothing to report
    hub.build(chain, cutoff=5, datasets=[DS])
    assert violations(chain) == 7  # the 8-word component is over 5; the pair is not
    hub.build(chain, cutoff=8, datasets=[DS])
    assert violations(chain) == 0
    hub.build(chain, cutoff=5, hub_degree=1, datasets=[DS])
    assert violations(chain) == 0  # hub-flagged edges are another reason, not counted here
