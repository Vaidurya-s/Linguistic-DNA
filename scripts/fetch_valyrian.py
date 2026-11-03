"""Download the Valyrian pages of The Languages of David J. Peterson wiki into data/raw/valyrian/
(git-ignored), for the local research database only.

    python3 scripts/fetch_valyrian.py                 # dictionary pages and every lemma page
    python3 scripts/fetch_valyrian.py --no-pages      # dictionary pages only (words and glosses)
    python3 scripts/fetch_valyrian.py --categories    # also the Astapori / Meereenese lemma lists

The wiki's content belongs to HBO and David J. Peterson and carries no licence for reuse, so this
is run by the user on their own machine, like downloading the pages in a browser, and the result
is never committed or redistributed. The script honours robots.txt (only article pages, never
/index.php or /api.php), waits between requests (--delay, default 3 s), identifies itself, and
skips pages it already has, so it can be stopped and resumed. Uses only the standard library.

A slow or failed request is retried with a pause (HTTP 429 waits a minute); a page that still
fails is skipped and listed at the end, and the next run retries it. Five skipped pages in a row
stop the run, and HTTP 401/403 stops it at once. Progress is saved whatever ends the run.

--categories adds two requests: the wiki's lemma categories for Astapori and Meereenese Valyrian
(their prose dictionary pages are marked incomplete and are not tables). /Category: pages are
allowed by robots.txt, but the continuation of a long list is served through /index.php, which is
not, so a list of more than one page is used as far as it goes and the script says so.
"""

import argparse
import html
import http.client
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://wiki.languageinvention.com"
UA = "LinguisticDNA-fetch/0.1 (https://github.com/Vaidurya-s/Linguistic-DNA; personal research use)"
RETRIES = 4  # attempts per page before it is skipped (and retried on the next run)
GIVE_UP_AFTER = 5  # pages skipped in a row: the site is down or refusing us, so stop


class FetchError(Exception):
    """A page could not be fetched after several attempts; skip it, a later run retries."""


class Blocked(Exception):
    """The site refuses us (HTTP 401/403). Stop at once and do not keep asking."""


CATEGORIES = {
    "asta": "Category:Astapori_Valyrian_lemmas",
    "meer": "Category:Meereenese_Valyrian_lemmas",
}
DICTIONARIES = {
    "hval": "High_Valyrian_Dictionary",
    "asta": "Astapori_Valyrian_Dictionary",
    "meer": "Meereenese_Valyrian_Dictionary",
}
_MW_PAGES = re.compile(r'<div id="mw-pages">(.*?)(?:<div class="printfooter"|\Z)', re.S)
_MEMBER = re.compile(r'<li><a href="/([^"#?]+)"[^>]*>')
_ROW_LINK = re.compile(r'<td><b><a href="/([^"#?]+)(?:#[^"]*)?" title="[^"]*">')


def category_titles(category_html: str) -> tuple[list[str], bool]:
    """(page titles of the members of a category page, whether the list continues on a next
    page). Subcategories and namespace pages are not members we want."""
    m = _MW_PAGES.search(category_html)
    if not m:
        return [], False
    out = []
    for path in _MEMBER.findall(m.group(1)):
        title = urllib.parse.unquote(html.unescape(path))
        if ":" not in title and title not in out:
            out.append(title)
    return out, "pagefrom=" in m.group(1)


def page_file(dest: Path, title: str) -> Path:
    return dest / "pages" / (urllib.parse.quote(title, safe="") + ".html")


def lemma_titles(dictionary_html: str) -> list[str]:
    """Page titles of the terms in a dictionary table (first column links)."""
    out = []
    for path in _ROW_LINK.findall(dictionary_html):
        title = urllib.parse.unquote(html.unescape(path))
        if ":" not in title and title not in out:
            out.append(title)
    return out


class Fetcher:
    def __init__(self, delay: float):
        self.delay = delay
        self.robots = urllib.robotparser.RobotFileParser()
        # RobotFileParser.read() asks with Python's default user agent, which the wiki's CDN
        # answers with 403, and the parser then treats the whole site as disallowed. Read the
        # file with our own identifying user agent, and stop if it cannot be read at all.
        req = urllib.request.Request(f"{BASE}/robots.txt", headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read().decode("utf-8")
            # The stdlib parser drops a "User-agent: *" group when a blank line follows that
            # line (as in this wiki's file) and then allows everything. Blank lines are not
            # needed to separate groups, so remove them.
            self.robots.parse([line for line in body.splitlines() if line.strip()])
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"cannot read {BASE}/robots.txt ({exc}); not fetching anything without it"
            ) from exc
        self.last = 0.0

    def get(self, title: str, category: bool = False) -> str | None:
        if category:  # only the two lemma categories, nothing else with a colon
            if title not in CATEGORIES.values():
                raise RuntimeError(f"not a listed category page: {title!r}")
            url = f"{BASE}/{urllib.parse.quote(title, safe=':')}"
        elif ":" in title or "?" in title or title.lower().startswith("index.php"):
            raise RuntimeError(f"not an article page: {title!r}")  # never a namespace or script
        else:
            url = f"{BASE}/{urllib.parse.quote(title)}"
        if not self.robots.can_fetch(UA, url):
            raise RuntimeError(f"robots.txt disallows {url}")
        for attempt in range(1, RETRIES + 1):
            wait = self.last + self.delay - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self.last = time.monotonic()
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return r.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    return None
                if exc.code in (401, 403):
                    raise Blocked(f"{url}: HTTP {exc.code}; the site is refusing us") from exc
                if exc.code == 429:  # asked to slow down
                    reason, pause = "HTTP 429", max(60, self.delay * 10)
                elif exc.code >= 500:
                    reason, pause = f"HTTP {exc.code}", 10 * attempt
                else:
                    raise FetchError(f"{url}: HTTP {exc.code}") from exc
            except (OSError, http.client.HTTPException) as exc:  # timeouts, resets, DNS
                reason, pause = type(exc).__name__, 10 * attempt
            if attempt == RETRIES:
                raise FetchError(f"{url}: {reason} on {RETRIES} attempts")
            print(f"  {title}: {reason}, retrying in {pause:.0f} s", flush=True)
            time.sleep(pause)
        raise AssertionError("unreachable")


def write_atomic(path: Path, text: str) -> None:
    """A page file either exists complete or not at all, so a stop mid-write is harmless."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=ROOT / "data" / "raw" / "valyrian")
    parser.add_argument("--delay", type=float, default=3.0, help="seconds between requests")
    parser.add_argument("--no-pages", action="store_true", help="only the dictionary pages")
    parser.add_argument(
        "--categories", action="store_true", help="also the Astapori and Meereenese lemma lists"
    )
    args = parser.parse_args()
    if args.delay < 1:
        parser.error("--delay must be at least 1 second")
    args.dest.mkdir(parents=True, exist_ok=True)
    fetcher = Fetcher(args.delay)
    manifest_path = args.dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"pages": {}}
    titles: list[str] = []
    for code, title in DICTIONARIES.items():
        path = args.dest / f"{title}.html"
        if not path.exists():
            text = fetcher.get(title)
            if text is None:
                print(f"{title}: no such page (skipped)")
                continue
            write_atomic(path, text)
            manifest[title] = {"fetched": time.strftime("%Y-%m-%d"), "language": code}
        found = lemma_titles(path.read_text(encoding="utf-8"))
        print(f"{title}: {len(found)} terms")
        titles += [t for t in found if t not in titles]
    if args.categories:
        for code, title in CATEGORIES.items():
            path = args.dest / "categories" / (title.split(":", 1)[1] + ".html")
            if not path.exists():
                text = fetcher.get(title, category=True)
                if text is None:
                    print(f"{title}: no such page (skipped)")
                    continue
                path.parent.mkdir(exist_ok=True)
                write_atomic(path, text)
                manifest[title] = {"fetched": time.strftime("%Y-%m-%d"), "language": code}
            found, more = category_titles(path.read_text(encoding="utf-8"))
            print(f"{title}: {len(found)} lemma pages")
            if not found:
                print("  warning: no members found; the page layout may differ from the usual")
            if more:
                print("  warning: the list continues on a next page, which robots.txt does not")
                print("  allow us to fetch; only the members on this first page are used")
            titles += [t for t in found if t not in titles]
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    if args.no_pages:
        return 0
    todo = [t for t in titles if not page_file(args.dest, t).exists()]
    print(
        f"{len(titles)} pages, {len(todo)} to fetch (about {len(todo) * args.delay / 60:.0f} min)"
    )
    (args.dest / "pages").mkdir(exist_ok=True)
    failed: list[str] = []
    streak = 0
    try:
        for i, title in enumerate(todo, start=1):
            try:
                text = fetcher.get(title)
            except FetchError as exc:
                failed.append(title)
                streak += 1
                print(f"  skipped {title}: {exc}", flush=True)
                if streak >= GIVE_UP_AFTER:
                    print(f"{streak} pages in a row failed; stopping. Run again later.")
                    break
                continue
            streak = 0
            if text is None:
                manifest["pages"][title] = "missing"
                continue
            write_atomic(page_file(args.dest, title), text)
            manifest["pages"][title] = time.strftime("%Y-%m-%d")
            if i % 50 == 0 or i == len(todo):
                manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
                print(f"  {i}/{len(todo)}", flush=True)
    except Blocked as exc:
        print(f"stopping: {exc}", file=sys.stderr)
        return 2
    finally:  # progress is kept whatever ends the run
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    if failed:
        print(f"{len(failed)} pages could not be fetched; run again to retry them.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
