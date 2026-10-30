from pathlib import Path

from app.importers.cldf_structure import import_cldf_structure

FIXTURE = Path(__file__).parent / "fixtures" / "structure_mini"


def test_structure_values_become_language_profiles(db):
    try:
        stats = import_cldf_structure(db, FIXTURE, "lsi")  # any audited dataset id
        assert stats == {"profile_rows": 2, "languages": 1, "doculects_unmapped": 1}
        rows = set(
            db.execute(
                "SELECT feature_name, value, citation FROM language_profile"
                " WHERE language_id = 'hin'"
            ).fetchall()
        )
        assert rows == {
            ("Consonant Inventories", "Average", "Maddieson 2013"),
            ("Order of Subject Object and Verb", "SOV", "Dryer 2013"),
        }
    finally:
        db.rollback()


def test_profile_endpoint(client):
    body = client.get("/api/v1/languages/hin/profile").json()
    assert body["language_id"] == "hin" and isinstance(body["values"], list)
    assert client.get("/api/v1/languages/nope/profile").status_code == 404
