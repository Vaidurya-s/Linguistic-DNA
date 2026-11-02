"""Valyrian importer on synthetic pages in the wiki's HTML structure (the real pages are
downloaded by the user's own `make fetch-valyrian` and never committed)."""

import importlib.util
import urllib.parse

from app.config import REPO_ROOT
from app.importers.valyrian import import_valyrian, parse_page
from app.pipeline.validate import run_checks
from app.services.ids import lexeme_id


def row(title: str, anchor: str, definition: str) -> str:
    return (
        f'<tr>\n<td><b><a href="/{title}#High_Valyrian" title="{title}">{title}</a></b>'
        f'<span id="{anchor}"></span></td>\n<td>{definition}\n</td></tr>\n'
    )


DICTIONARY = (
    '<table class="wikitable sortable plainrowheaders"><tbody>\n'
    "<tr><th>Term</th><th>Definition</th></tr>\n"
    + row("Hepagon", "hepagon", "to climb")
    + row("Hepvos", "hepvos", "ladder")
    + row("-vos", "-vos", "<i>Used to form nouns for tools.</i>")
    + row("Valyria", "valyria", "Valyria (a city)")
    + "</tbody></table>"
)


def heading(level: int, hid: str, label: str) -> str:
    tag = f"h{level}"
    return f'<div class="mw-heading mw-heading{level}"><{tag} id="{hid}">{label}</{tag}></div>'


def mention(lang: str, title: str, form: str, gloss: str = "") -> str:
    link = f'<a href="/{title}#X" title="{title}">{form}</a>'
    out = f'<i class="Latn mention" lang="{lang}">{link}</i>'
    if gloss:
        out += (
            ' <span class="mention-gloss-paren annotation-paren">(</span>'
            '<span class="mention-gloss-double-quote">“</span>'
            f'<span class="mention-gloss">{gloss}</span>'
            '<span class="mention-gloss-double-quote">”</span>'
            '<span class="mention-gloss-paren annotation-paren">)</span>'
        )
    return out


def page(*sections: str, oldid: int = 777) -> str:
    return (
        "<html><body>"
        + "".join(sections)
        + f'<div class="printfooter">Retrieved from "{"https://wiki.languageinvention.com"}'
        f'/index.php?title=X&amp;oldid={oldid}"</div></body></html>'
    )


def hval_section(headword: str, gloss: str, etymology: str = "", descendants: str = "") -> str:
    out = heading(2, "High_Valyrian", '<a href="/High_Valyrian_language">High Valyrian</a>')
    out += heading(3, "Etymology", "Etymology") + f"<p>{etymology}\n</p>"
    out += heading(4, "Noun", "Noun")
    out += f'<p><strong class="Latn headword" lang="hval">{headword}</strong> (<i>noun</i>)\n</p>'
    out += f"<ol><li>{gloss}\n<dl><dd>an example sentence</dd></dl></li></ol>"
    if descendants:
        out += heading(5, "Descendants", "Descendants") + f"<ul>{descendants}</ul>"
    return out


PAGES = {
    "Hepvos": page(
        hval_section(
            "hepvos",
            "ladder",
            "From "
            + mention("hval", "Hepagon", "hepagon", "to climb")
            + " +&#8206; "
            + mention("hval", "-vos", "-vos")
            + ".",
        )
    ),
    "-vos": page(
        hval_section(
            "-vos",
            "Used to form nouns for tools.",
            "From an invisible proto-language.",
            '<li><a href="/Astapori_Valyrian_language">Astapori Valyrian</a>: '
            '<span class="Latn" lang="asta"><a href="/index.php?title=-vo&amp;action=edit'
            '&amp;redlink=1" class="new" title="-vo (page does not exist)">-vo</a></span></li>'
            '<li><a href="/Meereenese_Valyrian_language">Meereenese Valyrian</a>: '
            '<span class="Latn" lang="meer"><a href="/-wa#Etymology_2" title="-wa">-wa</a>'
            "</span></li>",
        ),
        oldid=1239704,
    ),
    "Valyria": page(hval_section("Valyria", "Valyria (a city)", "Coined by the author.")),
    # an Astapori page: inherited from High Valyrian
    "Ēza": page(
        heading(2, "Astapori_Valyrian", "Astapori Valyrian")
        + heading(3, "Etymology", "Etymology")
        + "<p>From High Valyrian "
        + mention("hval", "Hepvos", "hepvos")
        + ".\n</p>"
        + heading(4, "Noun", "Noun")
        + '<p><strong class="Latn headword" lang="asta">ēza</strong>\n</p>'
        + "<ol><li>stair</li></ol>"
    ),
}


def write(raw):
    (raw / "pages").mkdir(parents=True)
    (raw / "High_Valyrian_Dictionary.html").write_text(DICTIONARY, encoding="utf-8")
    for title, text in PAGES.items():
        name = urllib.parse.quote(title, safe="") + ".html"
        (raw / "pages" / name).write_text(text, encoding="utf-8")


def vid(code: str, form: str) -> str:
    return lexeme_id("valyrian", f"{code}:{form}")


def edge(db, child: str, parent: str):
    return db.execute(
        "SELECT r.type_id, e.citation, e.locator FROM relationship r JOIN evidence e"
        " ON e.relationship_id = r.id WHERE r.source_lexeme_id = %s AND r.target_lexeme_id = %s",
        (child, parent),
    ).fetchone()


def test_parse_page():
    [entry] = parse_page(PAGES["Hepvos"])
    assert entry["code"] == "hval" and entry["headword"] == "hepvos"
    assert entry["glosses"] == ["ladder"]
    etext, mentions = entry["etymology"][0]
    assert "+" in etext
    assert mentions == [("hval", "Hepagon", "hepagon", "to climb"), ("hval", "-vos", "-vos", "")]
    [suffix] = parse_page(PAGES["-vos"])
    assert suffix["descendants"] == [("asta", "-vo", "-vo", False), ("meer", "-wa", "-wa", False)]


def test_import(db, tmp_path):
    from app.importers.manifest import load_manifest

    write(tmp_path)
    try:
        load_manifest(db)
        stats = import_valyrian(db, tmp_path, "fixture")
        hv = db.execute(
            "SELECT g.name, f.name, g.metadata_json->>'fictional', g.metadata_json->>'group'"
            " FROM language g JOIN language_family f ON f.id = g.family_id"
            " WHERE g.id = 'conlang-hval'"
        ).fetchone()
        assert hv == (
            "High Valyrian",
            "Valyrian languages (constructed, fictional)",
            "true",
            "Valyrian (constructed)",
        )
        # dictionary terms with glosses; the page's headword keeps a proper noun's capital
        row = db.execute(
            "SELECT form, gloss, reconstruction_status::text FROM lexeme WHERE id = %s",
            (vid("hval", "valyria"),),
        ).fetchone()
        assert row == ("Valyria", "Valyria (a city)", "attested")
        hepvos = vid("hval", "hepvos")
        assert edge(db, hepvos, vid("hval", "hepagon"))[0] == "has_component"
        assert edge(db, hepvos, vid("hval", "-vos"))[0] == "has_component"
        # descendants in the Low Valyrian languages, citing the page revision
        type_id, citation, locator = edge(db, vid("asta", "-vo"), vid("hval", "-vos"))
        assert type_id == "inherited_form"
        assert "constructed language, fictional" in citation
        assert locator.endswith("title=-vos&oldid=1239704")
        assert edge(db, vid("meer", "-wa"), vid("hval", "-vos"))[0] == "inherited_form"
        assert edge(db, vid("asta", "ēza"), hepvos)[0] == "inherited_form"
        # never linked to a natural language
        foreign = db.execute(
            "SELECT count(*) FROM relationship r JOIN lexeme t ON t.id = r.target_lexeme_id"
            " JOIN lexeme s ON s.id = r.source_lexeme_id WHERE r.dataset = 'valyrian'"
            " AND NOT (s.language_id LIKE 'conlang-%%' AND t.language_id LIKE 'conlang-%%')"
        ).fetchone()[0]
        assert foreign == 0
        assert stats["relationships"] == 5
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()


def test_other_languages_are_never_imported_or_linked(db, tmp_path):
    """A page may cite a Latin word, or another invented language: it must not become a
    "Valyrian (la)" language, a word of the Valyrian family, or the end of a link."""
    from app.importers.manifest import load_manifest

    ety = (
        "Inspired by "
        + mention("la", "vallum", "vallum", "wall")
        + " and "
        + mention("dth", "Zhor", "zhor", "man")
        + ", from "
        + mention("hval", "Hepagon", "hepagon", "to climb")
        + "."
    )
    latin = (
        heading(2, "Latin", "Latin")
        + heading(4, "Noun", "Noun")
        + '<p><strong class="Latn headword" lang="la">murus</strong> (<i>noun</i>)\n</p>'
        + "<ol><li>wall</li></ol>"
    )
    descendants = (
        '<li><a href="/Latin">Latin</a>: <span class="Latn" lang="la">'
        '<a href="/castra" title="castra">castra</a></span></li>'
        '<li><a href="/Astapori_Valyrian_language">Astapori Valyrian</a>: '
        '<span class="Latn" lang="asta"><a href="/-vo" title="-vo">-vo</a></span></li>'
    )
    raw = tmp_path
    (raw / "pages").mkdir(parents=True)
    (raw / "High_Valyrian_Dictionary.html").write_text(DICTIONARY, encoding="utf-8")
    pages = {
        "Hepvos": page(hval_section("hepvos", "ladder", ety, descendants) + latin),
        "Murus": page(latin),
    }
    for title, text in pages.items():
        (raw / "pages" / (urllib.parse.quote(title, safe="") + ".html")).write_text(
            text, encoding="utf-8"
        )
    # a Latin or English section is not an entry, whatever its headword's language
    assert parse_page(pages["Murus"]) == []
    try:
        load_manifest(db)
        stats = import_valyrian(db, raw, "fixture")
        assert db.execute(
            "SELECT id FROM language WHERE id LIKE 'conlang-%%' ORDER BY 1"
        ).fetchall() == [("conlang-asta",), ("conlang-hval",)]
        assert db.execute(
            "SELECT count(*) FROM lexeme WHERE dataset = 'valyrian'"
            " AND form IN ('vallum', 'zhor', 'murus', 'castra')"
        ).fetchone() == (0,)
        assert stats["skipped:la"] >= 2 and stats["skipped:dth"] == 1
        # the Valyrian parts of the same page are still imported and linked
        hepvos = vid("hval", "hepvos")
        assert edge(db, hepvos, vid("hval", "hepagon"))[0] == "derived_form"
        assert edge(db, vid("asta", "-vo"), hepvos)[0] == "inherited_form"
        assert db.execute(
            "SELECT count(*) FROM relationship r JOIN lexeme s ON s.id = r.source_lexeme_id"
            " JOIN lexeme t ON t.id = r.target_lexeme_id WHERE r.dataset = 'valyrian'"
            " AND (s.language_id NOT IN ('conlang-hval', 'conlang-asta', 'conlang-meer')"
            " OR t.language_id NOT IN ('conlang-hval', 'conlang-asta', 'conlang-meer'))"
        ).fetchone() == (0,)
        assert run_checks(db, research=True)["passed"]
    finally:
        db.rollback()


def test_fetch_lists_dictionary_terms():
    spec = importlib.util.spec_from_file_location(
        "fetch_valyrian", REPO_ROOT / "scripts" / "fetch_valyrian.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.lemma_titles(DICTIONARY) == ["Hepagon", "Hepvos", "-vos", "Valyria"]


def _fetch_module():
    spec = importlib.util.spec_from_file_location(
        "fetch_valyrian", REPO_ROOT / "scripts" / "fetch_valyrian.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# Shaped like the wiki's file: a blank line and comments after "User-agent: *" (the stdlib
# parser then drops the group and allows everything), then rules, then bot-specific groups.
ROBOTS = (
    "User-agent: *\n\n# 1. Block scripts\nDisallow: /index.php?\nDisallow: /Special:\n"
    "Disallow: /User:\nAllow: /Category:\nAllow: /\n\nUser-agent: ClaudeBot\nDisallow: /\n"
)


def test_fetch_reads_robots_with_its_own_user_agent(monkeypatch):
    """robots.txt must be requested with our identifying user agent: with Python's default one
    the wiki's CDN answers 403, which the stdlib parser reads as 'everything is disallowed'."""
    import io
    import urllib.error

    mod = _fetch_module()
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["ua"] = req.get_header("User-agent")
        seen["url"] = req.full_url
        return io.BytesIO(ROBOTS.encode())

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    f = mod.Fetcher(delay=3)
    assert seen["url"].endswith("/robots.txt") and seen["ua"] == mod.UA
    assert f.robots.can_fetch(mod.UA, f"{mod.BASE}/High_Valyrian_Dictionary")
    assert not f.robots.can_fetch(mod.UA, f"{mod.BASE}/Special:Search")
    assert not f.robots.can_fetch(mod.UA, f"{mod.BASE}/User:Someone")
    assert not f.robots.can_fetch("ClaudeBot", f"{mod.BASE}/Hepagon")
    # and never a namespace page or script, whatever robots.txt says
    for bad in ("Special:Search", "index.php?title=x", "Talk:Foo"):
        try:
            f.get(bad)
        except RuntimeError as exc:
            assert "not an article page" in str(exc)
        else:
            raise AssertionError(bad)

    # unreadable robots.txt: stop, do not guess
    def refuse(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(mod.urllib.request, "urlopen", refuse)
    try:
        mod.Fetcher(delay=3)
    except RuntimeError as exc:
        assert "robots.txt" in str(exc)
    else:
        raise AssertionError("a Fetcher was built without a readable robots.txt")


def _scripted_urlopen(mod, monkeypatch, handler):
    """Replace the network: robots.txt is answered, every other URL goes to handler(url)."""
    import io

    log = []

    def fake(req, timeout=None):
        log.append(req.full_url)
        if req.full_url.endswith("/robots.txt"):
            return io.BytesIO(ROBOTS.encode())
        result = handler(req.full_url)
        if isinstance(result, BaseException):
            raise result
        return io.BytesIO(result.encode())

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake)
    monkeypatch.setattr(mod.time, "sleep", lambda s: None)
    return log


def _http_error(mod, url, code):
    import urllib.error

    return urllib.error.HTTPError(url, code, "x", {}, None)


def test_fetch_retries_transient_errors_and_skips_persistent_ones(monkeypatch):
    mod = _fetch_module()
    calls = {}

    def handler(url):
        calls[url] = calls.get(url, 0) + 1
        if url.endswith("/Slow"):  # times out once, then answers
            return TimeoutError("The read operation timed out") if calls[url] == 1 else "ok"
        if url.endswith("/Throttled"):  # 429 once
            return _http_error(mod, url, 429) if calls[url] == 1 else "ok"
        if url.endswith("/Down"):
            return _http_error(mod, url, 503)
        if url.endswith("/Gone"):
            return _http_error(mod, url, 404)
        return "ok"

    log = _scripted_urlopen(mod, monkeypatch, handler)
    f = mod.Fetcher(delay=3)
    assert f.get("Slow") == "ok" and f.get("Throttled") == "ok"
    assert f.get("Gone") is None  # a missing page is not an error
    try:
        f.get("Down")
    except mod.FetchError as exc:
        assert "503" in str(exc)
    else:
        raise AssertionError("a page that always fails must raise FetchError")
    assert calls[f"{mod.BASE}/Down"] == mod.RETRIES
    assert calls[f"{mod.BASE}/Slow"] == 2 and len(log) == 1 + 2 + 2 + 1 + mod.RETRIES


def test_fetch_stops_at_once_when_blocked(monkeypatch):
    mod = _fetch_module()
    log = _scripted_urlopen(mod, monkeypatch, lambda url: _http_error(mod, url, 403))
    f = mod.Fetcher(delay=3)
    try:
        f.get("Hepagon")
    except mod.Blocked:
        pass
    else:
        raise AssertionError("HTTP 403 must raise Blocked")
    assert len(log) == 2  # robots.txt and one attempt: no retries against a refusal


def test_fetch_run_survives_a_failing_page_and_keeps_progress(monkeypatch, tmp_path):
    import json
    import sys

    mod = _fetch_module()
    (tmp_path / "High_Valyrian_Dictionary.html").write_text(DICTIONARY, encoding="utf-8")

    def handler(url):
        if url.endswith("/Hepvos"):
            return TimeoutError("The read operation timed out")  # never answers
        if "Dictionary" in url:
            return _http_error(mod, url, 404)  # Astapori / Meereenese: no such page
        return "<html>page</html>"

    _scripted_urlopen(mod, monkeypatch, handler)
    monkeypatch.setattr(sys, "argv", ["fetch_valyrian.py", "--dest", str(tmp_path), "--delay", "1"])
    assert mod.main() == 1  # one page could not be fetched: run again
    pages = {p.name for p in (tmp_path / "pages").iterdir()}
    assert pages == {"Hepagon.html", "-vos.html", "Valyria.html"}  # no Hepvos, no .tmp files
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert set(manifest["pages"]) == {"Hepagon", "-vos", "Valyria"}
    # the next run fetches only what is missing
    _scripted_urlopen(mod, monkeypatch, lambda url: "<html>again</html>")
    assert mod.main() == 0
    assert (tmp_path / "pages" / "Hepvos.html").read_text() == "<html>again</html>"
    assert (tmp_path / "pages" / "Hepagon.html").read_text() == "<html>page</html>"
