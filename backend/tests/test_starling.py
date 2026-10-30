"""StarLing importer, on synthetic archives in the real format (dBase III + .var + .inf
inside a ZIP named like the downloads). The real archives are fetched by the user's own
`make fetch-dev-data`; starlingdb.org disallows AI crawlers, so they are not used here."""

import struct
import zipfile

from app.importers.starling import (
    CONTESTED_NOTE,
    decode_starling,
    import_starling,
    parse_segment,
)
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id


def cyr(text: str) -> bytes:
    return text.encode("cp866")


def dbf(fields: list[tuple[str, str, int]], records: list[dict]) -> tuple[bytes, bytes]:
    """A StarLing .dbf and its .var: text fields are (offset, length) pointers."""
    var = bytearray(b"\0")
    rlen = 1 + sum(n for _, _, n in fields)
    hlen = 32 + 32 * len(fields) + 1
    head = struct.pack("<BBBBIHH", 3, 105, 11, 18, len(records), hlen, rlen) + b"\0" * 20
    for name, kind, n in fields:
        head += name.encode().ljust(11, b"\0") + kind.encode() + b"\0" * 4 + bytes([n])
        head += b"\0" * 15
    head += b"\r"
    body = b""
    for rec in records:
        row = b" "
        for name, kind, n in fields:
            value = rec.get(name)
            if kind == "C":
                if value:
                    row += struct.pack("<IH", len(var), len(value))
                    var += value
                else:
                    row += b" " * 6
            else:
                row += str(value or 0).rjust(n).encode()
        body += row
    return head + body + b"\x1a", bytes(var)


def inf(aliases: dict[str, str], links: dict[str, str] | None = None) -> bytes:
    lines = [f"{k} = \\data\\x\\{v}" for k, v in (links or {}).items()]
    lines += [f"field_alias[{k}] = \\1:{v}\\2:x" for k, v in aliases.items()]
    return "\r\n".join(lines).encode("cp866")


def archive(path, databases: dict[str, tuple[list, list, dict, dict | None]]) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("LEXSTAT/x.dbf", b"ignored")
        for name, (fields, records, aliases, links) in databases.items():
            d, v = dbf(fields, records)
            z.writestr(f"{name}.dbf", d)
            z.writestr(f"{name}.var", v)
            z.writestr(f"{name}.inf", inf(aliases, links))


GREEK_ARI = b"\x01\x83\xc2\x83\xa1\x83\xd3\x83\xca"  # alpha + psili, rho, iota: ἀρι


def test_decoding():
    assert decode_starling(GREEK_ARI + b" `fr\xf2h'") == "ἀρι `früh'"
    assert decode_starling(cyr("у") + b"\xb1" + cyr("тро")) == "у́тро"  # combining acute
    assert decode_starling(cyr("Где")) == "Где"  # Cyrillic Г is not a Greek escape
    assert decode_starling(b"\x1ddar \\Iital\\i") == "ðar ital"  # escape; markup removed
    assert decode_starling(b"\x01\xa4\x67") == "土"  # Big5 in double-byte mode


def test_segments():
    names = {"Oss.": "os", "Toch. B": "txb", "Other Iranian": "*"}
    assert parse_segment("Oss. ðar m. 'day'", names) == ("os", "ðar", "day")
    assert parse_segment("gen. aya n. `Tag'", names) == (None, "aya", "Tag")
    assert parse_segment("Toch. B ārwer 'ready'", names) == ("txb", "ārwer", "ready")


def build(tmp_path):
    piet = [
        ("NUMBER", "N", 4),
        ("PROTO", "C", 6),
        ("MEANING", "C", 6),
        ("REFERNUM", "N", 4),
        ("GREEK", "C", 6),
        ("IRAN", "C", 6),
        ("GERM", "C", 6),
        ("GERMNUM", "N", 6),
        ("SLAVNUM", "N", 6),
        ("MARS", "C", 6),
        ("REFER", "C", 6),
        ("COMMENT", "C", 6),
    ]
    piet_rec = {
        "NUMBER": 1,
        "PROTO": b"*ay-er/n- ",
        "MEANING": b"morning",
        "REFERNUM": 31,
        "GREEK": GREEK_ARI + b" `fr\xf2h'",
        "IRAN": b"Oss. \x1ddar 'day'; Zzz. foo 'bar'",
        "GERM": b"*air-a- 'early'",
        "GERMNUM": 1,
        "SLAVNUM": 5,
        "MARS": b"blorp",
        "REFER": b"WP I 2 f",
        "COMMENT": b"Long prose that must not be stored \\Iat all\\i",
    }
    germet = [("NUMBER", "N", 4), ("PROTO", "C", 6), ("MEANING", "C", 6), ("GOT", "C", 6)]
    pokorny = [("NUMBER", "N", 4), ("ROOT", "C", 6), ("PAGES", "C", 6), ("MATERIAL", "C", 6)]
    vasmer = [("NUMBER", "N", 5), ("WORD", "C", 6), ("GENERAL", "C", 6), ("PAGES", "C", 6)]
    archive(
        tmp_path / "IE.exe",
        {
            "piet": (
                piet,
                [piet_rec],
                {
                    "PROTO": "Proto-IE",
                    "GREEK": "Old Greek",
                    "IRAN": "Other Iranian",
                    "GERM": "Germanic",
                    "MARS": "Martian",
                    "REFER": "References",
                },
                {"refer": "pokorny", "slav": "vasmer"},
            ),
            "germet": (
                germet,
                [{"NUMBER": 1, "PROTO": b"*air-a-", "MEANING": b"early", "GOT": b"air 'early'"}],
                {"GOT": "Gothic"},
                None,
            ),
            "pokorny": (
                pokorny,
                [{"NUMBER": 31, "ROOT": b"ay-er", "PAGES": b"12-13", "MATERIAL": b"prose"}],
                {},
                None,
            ),
            "vasmer": (
                vasmer,
                [
                    {
                        "NUMBER": 5,
                        "WORD": cyr("у") + b"\xb1" + cyr("тро,"),
                        "GENERAL": cyr('"утро, рассвет", укр. долгий текст статьи'),
                        "PAGES": b"4,170",
                    }
                ],
                {},
                None,
            ),
        },
    )
    alt = [("NUMBER", "N", 4), ("PROTO", "C", 6), ("MEANING", "C", 6), ("TURCNUM", "N", 4)]
    turk = [("NUMBER", "N", 4), ("PROTO", "C", 6), ("MEANING", "C", 6), ("TUR", "C", 6)]
    archive(
        tmp_path / "ALTAIC.exe",
        {
            "altet": (
                alt,
                [{"NUMBER": 7, "PROTO": b"*ka", "MEANING": b"x", "TURCNUM": 3}],
                {},
                None,
            ),
            "turcet": (
                turk,
                [{"NUMBER": 3, "PROTO": b"*k\xb0", "MEANING": b"y", "TUR": b"ka 'y'"}],
                {"TUR": "Turkish"},
                None,
            ),
        },
    )
    return [tmp_path / "IE.exe", tmp_path / "ALTAIC.exe"]


def sid(key: str) -> str:
    return lexeme_id("starling", key)


def link(db, child: str, parent: str):
    return db.execute(
        "SELECT r.type_id, r.notes, e.citation, e.locator FROM relationship r"
        " JOIN evidence e ON e.relationship_id = r.id"
        " WHERE r.source_lexeme_id = %s AND r.target_lexeme_id = %s",
        (child, parent),
    ).fetchone()


def test_import(db, tmp_path):
    from app.importers.manifest import load_manifest

    report = tmp_path / "unmapped.csv"
    try:
        load_manifest(db)
        stats = import_starling(db, build(tmp_path), "fixture", unmapped_report=report)
        pie = sid("piet:1")
        row = db.execute(
            "SELECT language_id, form, gloss, reconstruction_status::text, source_id"
            " FROM lexeme WHERE id = %s",
            (pie,),
        ).fetchone()
        assert row == ("wkt-ine-pro", "*ay-er/n-", "morning", "reconstructed", "starling-piet")
        # reflexes: Greek (decoded), Ossetic (from the abbreviation in a mixed field),
        # Proto-Germanic; each an etymon link citing the entry, with Pokorny's pages
        greek = sid("wkt-grc:ἀρι")
        assert db.execute("SELECT gloss FROM lexeme WHERE id = %s", (greek,)).fetchone() == (
            "früh",
        )
        type_id, _, citation, locator = link(db, greek, pie)
        assert type_id == "etymon" and "no. 1" in citation and "Old Greek" in citation
        assert locator == "WP I 2 f; Pokorny IEW 12-13"
        assert link(db, sid("wkt-os:ðar"), pie)[0] == "etymon"
        assert link(db, sid("wkt-gem-pro:*air-a-"), pie)[0] == "etymon"
        # the subordinate Germanic etymology and its Gothic reflex
        assert link(db, sid("germet:1"), pie)[0] == "etymon"
        assert link(db, sid("wkt-got:air"), sid("germet:1"))[0] == "etymon"
        # Vasmer: a Russian word, stress kept only in native_form, linked to the PIE root
        ru = sid("ru:утро")
        assert db.execute(
            "SELECT language_id, form, native_form, gloss, source_citation FROM lexeme"
            " WHERE id = %s",
            (ru,),
        ).fetchone() == ("wkt-ru", "утро", "у́тро", "утро, рассвет (in Russian)", "Vasmer, 4,170")
        assert link(db, ru, pie)[0] == "etymon"
        # Altaic links carry the contested note
        assert link(db, sid("turcet:3"), sid("altet:7"))[1] == CONTESTED_NOTE
        # no prose stored anywhere
        for text in ("Long prose", "долгий текст", "prose"):
            n = db.execute(
                "SELECT count(*) FROM lexeme WHERE dataset = 'starling'"
                " AND (gloss LIKE %s OR form LIKE %s)",
                (f"%{text}%", f"%{text}%"),
            ).fetchone()[0]
            assert n == 0
        assert stats["unmapped"] >= 2
        assert "field piet.MARS (Martian)" in stats["top_unmapped"]
        assert "abbreviation Zzz. (in piet.IRAN)" in report.read_text(encoding="utf-8")
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()
