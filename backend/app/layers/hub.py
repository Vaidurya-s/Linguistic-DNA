"""Cognate components and hub gating.

Documented ``cognate`` links form connected components over words. One component in the live graph
holds 262,841 words (homograph chaining) and produced 260 of the 294 false connections of the
baseline. This layer measures components and marks the oversized ones. It deletes and changes
nothing in ``public``: the documented links stay as they are, and a reader decides whether to use
the gated view.

A word is a ``(language_id, normalized_form)`` key, the identity the project uses to merge a word
across datasets; every lexeme row of a key carries the key's component.

Tables (see hub.sql): ``layers.cognate_component`` (one row per lexeme), ``layers.edge_hub_flag``
(documented cognate relationships whose component is oversized, or that touch a hub word),
``layers.cognate_component_build`` (the parameters of the last build).

Gated connection, used by ``is_connected_documented``: two lexemes are connected when they are in
the same component (hub words removed first, when the build used a hub rule) and that component has
at most ``cutoff`` words.

CLI: ``python -m app.layers.hub build [--cutoff N] [--hub-degree K] [--datasets a,b]
[--exclude a,b]`` and ``python -m app.layers.hub stats``.
"""

import argparse
import hashlib
from array import array
from collections import Counter
from collections.abc import Iterable, Sequence
from pathlib import Path

import psycopg

from app.importers.common import connect

COGNATE_TYPE = "cognate"
# chosen on the dev half of the gold: a cutoff of 50 lost 11.7% of the true links
DEFAULT_CUTOFF = 5000
SQL_FILE = Path(__file__).with_name("hub.sql")
COPY_BATCH = 100_000


def init_schema(conn: psycopg.Connection) -> None:
    """Create schema ``layers`` and the hub tables (idempotent)."""
    conn.execute(SQL_FILE.read_text(encoding="utf-8"))
    conn.commit()


# ---------------------------------------------------------------- pure graph logic (no database)


class UnionFind:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        p = self.p
        r = x
        while p[r] != r:
            r = p[r]
        while p[x] != r:
            p[x], x = r, p[x]
        return r

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


def cognate_degrees(n: int, a: Sequence[int], b: Sequence[int]) -> list[int]:
    """Number of distinct cognate neighbours of each of ``n`` words, for edges a[i] - b[i]."""
    seen = set()
    deg = [0] * n
    for x, y in zip(a, b, strict=True):
        if x == y:
            continue
        pair = (x, y) if x < y else (y, x)
        if pair in seen:
            continue
        seen.add(pair)
        deg[x] += 1
        deg[y] += 1
    return deg


def components(
    n: int, a: Sequence[int], b: Sequence[int], hub_degree: int | None = None
) -> dict[str, list]:
    """Union-find over edges a[i] - b[i] on ``n`` words.

    Returns per word: ``raw_root`` and ``raw_size`` (all edges), ``degree``, ``is_hub`` (degree
    above ``hub_degree``; never when None), ``root`` and ``size`` (after removing every edge that
    touches a hub word; hub words are singletons there, with size 1). Words with no edge have
    size 1.
    """
    deg = cognate_degrees(n, a, b)
    is_hub = [hub_degree is not None and d > hub_degree for d in deg]
    raw = UnionFind(n)
    gated = UnionFind(n)
    for x, y in zip(a, b, strict=True):
        raw.union(x, y)
        if not is_hub[x] and not is_hub[y]:
            gated.union(x, y)
    raw_root = [raw.find(i) for i in range(n)]
    root = [gated.find(i) for i in range(n)]
    raw_count = Counter(raw_root)
    count = Counter(root)
    return {
        "raw_root": raw_root,
        "raw_size": [raw_count[r] for r in raw_root],
        "degree": deg,
        "is_hub": is_hub,
        "root": root,
        "size": [count[r] for r in root],
    }


def edge_reasons(
    a: Sequence[int], b: Sequence[int], comp: dict[str, list], cutoff: int
) -> list[str | None]:
    """Per edge: 'hub_lexeme', 'oversized_component' or None (kept)."""
    out: list[str | None] = []
    for x, y in zip(a, b, strict=True):
        if comp["is_hub"][x] or comp["is_hub"][y]:
            out.append("hub_lexeme")
        elif comp["size"][x] > cutoff:
            out.append("oversized_component")
        else:
            out.append(None)
    return out


def component_id(min_key: str) -> str:
    """Stable id of a component, from its smallest word key."""
    return "cc_" + hashlib.sha1(min_key.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------- database build


def _csv(values: Iterable[str] | None) -> str | None:
    vals = sorted(values) if values else []
    return ",".join(vals) if vals else None


def build(
    conn: psycopg.Connection,
    cutoff: int = DEFAULT_CUTOFF,
    hub_degree: int | None = None,
    datasets: Sequence[str] | None = None,
    exclude_datasets: Sequence[str] = (),
    relationship_type: str = COGNATE_TYPE,
) -> dict:
    """(Re)build both tables from the documented cognate relationships. Idempotent.

    Streams the edges once (server-side cursor), runs union-find in memory (a few million edges),
    then writes the tables in COPY batches inside one transaction, so a failure leaves the old
    tables intact. ``datasets`` limits the source datasets, ``exclude_datasets`` removes some.
    """
    init_schema(conn)
    key_ix: dict[tuple[str, str], int] = {}
    keys: list[tuple[str, str]] = []
    ea, eb = array("i"), array("i")
    rel_ids: list[str] = []
    where = ["r.type_id = %s", "r.status = 'documented'"]
    params: list = [relationship_type]
    if datasets:
        where.append("r.dataset = any(%s)")
        params.append(list(datasets))
    if exclude_datasets:
        where.append("r.dataset <> all(%s)")
        params.append(list(exclude_datasets))
    sql = (
        "select r.id, ls.language_id, ls.normalized_form, lt.language_id, lt.normalized_form"
        " from relationship r join lexeme ls on ls.id = r.source_lexeme_id"
        " join lexeme lt on lt.id = r.target_lexeme_id where " + " and ".join(where)
    )
    with conn.cursor(name="hub_edges") as cur:
        cur.itersize = 200_000
        cur.execute(sql, params)
        for rid, la, fa, lb, fb in cur:
            ids = []
            for k in ((la, fa), (lb, fb)):
                i = key_ix.get(k)
                if i is None:
                    i = key_ix[k] = len(keys)
                    keys.append(k)
                ids.append(i)
            if ids[0] == ids[1]:
                continue  # two lexemes of one word key: not an edge between words
            ea.append(ids[0])
            eb.append(ids[1])
            rel_ids.append(rid)
    conn.rollback()  # close the cursor's transaction; nothing was written
    n = len(keys)
    comp = components(n, ea, eb, hub_degree)

    # component ids: smallest key of the raw component (raw ids) and of the gated component
    raw_min: dict[int, str] = {}
    gated_min: dict[int, str] = {}
    for i, (lang, form) in enumerate(keys):
        s = lang + "|" + form
        r, g = comp["raw_root"][i], comp["root"][i]
        if r not in raw_min or s < raw_min[r]:
            raw_min[r] = s
        if g not in gated_min or s < gated_min[g]:
            gated_min[g] = s
    raw_cid = {r: component_id(m) for r, m in raw_min.items()}
    gated_cid = {g: component_id(m) for g, m in gated_min.items()}

    reasons = edge_reasons(ea, eb, comp, cutoff)
    flagged = sum(1 for r in reasons if r)

    with conn.transaction():
        conn.execute("truncate layers.cognate_component, layers.edge_hub_flag")
        conn.execute(
            "create temp table tmp_hub_node (language_id text, normalized_form text,"
            " component_id text, component_size int, degree int, is_hub boolean,"
            " gated_component_id text,"
            " gated_component_size int) on commit drop"
        )
        with conn.cursor() as cur:
            for start in range(0, n, COPY_BATCH):
                with cur.copy("copy tmp_hub_node from stdin") as cp:
                    for i in range(start, min(n, start + COPY_BATCH)):
                        lang, form = keys[i]
                        cp.write_row(
                            (
                                lang,
                                form,
                                raw_cid[comp["raw_root"][i]],
                                comp["raw_size"][i],
                                comp["degree"][i],
                                comp["is_hub"][i],
                                gated_cid[comp["root"][i]],
                                comp["size"][i],
                            )
                        )
            cur.execute("create index on tmp_hub_node (language_id, normalized_form)")
            cur.execute(
                "insert into layers.cognate_component (lexeme_id, component_id, component_size,"
                " degree, is_hub, gated_component_id, gated_component_size)"
                " select l.id, t.component_id, t.component_size, t.degree, t.is_hub,"
                " t.gated_component_id, t.gated_component_size"
                " from tmp_hub_node t join lexeme l on l.language_id = t.language_id"
                " and l.normalized_form = t.normalized_form"
            )
            for start in range(0, len(rel_ids), COPY_BATCH):
                with cur.copy(
                    "copy layers.edge_hub_flag (relationship_id, component_id, reason) from stdin"
                ) as cp:
                    for j in range(start, min(len(rel_ids), start + COPY_BATCH)):
                        if reasons[j]:
                            cp.write_row((rel_ids[j], raw_cid[comp["raw_root"][ea[j]]], reasons[j]))
            cur.execute("select count(*) from layers.cognate_component")
            lexeme_rows = cur.fetchone()[0]
        conn.execute("delete from layers.cognate_component_build")
        conn.execute(
            "insert into layers.cognate_component_build (id, cutoff, hub_degree, datasets,"
            " exclude_datasets, relationship_type, edges, word_keys, components, flagged_edges)"
            " values (1, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                cutoff,
                hub_degree,
                _csv(datasets),
                _csv(exclude_datasets),
                relationship_type,
                len(rel_ids),
                n,
                len(raw_cid),
                flagged,
            ),
        )
    conn.commit()
    return {
        "edges": len(rel_ids),
        "word_keys": n,
        "lexeme_rows": lexeme_rows,
        "components": len(raw_cid),
        "gated_components": len(gated_cid),
        "flagged_edges": flagged,
        "largest_components": sorted((comp["raw_size"][r] for r in raw_cid), reverse=True)[:5],
    }


# ---------------------------------------------------------------- readers


def build_params(conn: psycopg.Connection) -> dict | None:
    row = conn.execute(
        "select cutoff, hub_degree, datasets, exclude_datasets, relationship_type, edges,"
        " word_keys, components, flagged_edges, built_at from layers.cognate_component_build"
    ).fetchone()
    if row is None:
        return None
    names = [
        "cutoff", "hub_degree", "datasets", "exclude_datasets", "relationship_type", "edges",
        "word_keys", "components", "flagged_edges", "built_at",
    ]  # fmt: skip
    return dict(zip(names, row, strict=True))


def is_connected_documented(
    conn: psycopg.Connection,
    a: str,
    b: str,
    gated: bool = True,
    ancestry: bool = False,
    max_depth: int = 8,
    datasets: Sequence[str] | None = None,
) -> bool:
    """Are lexemes ``a`` and ``b`` connected through documented links?

    Cognate leg only (``ancestry=False``). ``gated=False``: same raw component, whatever its size.
    ``gated=True``: same component after the build's hub rule, that component has at most the
    build's ``cutoff`` words, and neither lexeme is a hub. A lexeme with no cognate link is
    connected to nothing, and a lexeme is not connected to itself.

    ``ancestry=True`` is the R2 rule of the diagnosis: components (the small ones, when gated) are
    contracted to one node, and documented inherited_form / etymon / derived_form links are followed
    upward, up to ``max_depth`` steps from each side. The two are connected when the climbs meet.
    Oversized components are not contracted, so a homograph hub cannot join unrelated words.
    ``datasets`` limits the ancestry links followed to those datasets (default: all).
    """
    if a == b:
        return False
    if ancestry:
        return _connected_by_ancestry(conn, a, b, gated, max_depth, datasets)
    rows = conn.execute(
        "select lexeme_id, component_id, component_size, is_hub, gated_component_id,"
        " gated_component_size from layers.cognate_component where lexeme_id = any(%s)",
        ([a, b],),
    ).fetchall()
    got = {r[0]: r for r in rows}
    if a not in got or b not in got:
        return False
    ra, rb = got[a], got[b]
    if not gated:
        return ra[1] == rb[1]
    params = build_params(conn)
    cutoff = params["cutoff"] if params else DEFAULT_CUTOFF
    if ra[3] or rb[3]:
        return False
    return ra[4] == rb[4] and ra[5] <= cutoff


ANCESTRY_TYPES = ("inherited_form", "etymon", "derived_form")  # borrowed_from is never followed


def _supers(conn, ids: list[str], gated: bool, cutoff: int) -> set[tuple]:
    """Contracted node of each lexeme: its component when contractible, else its own word key."""
    rows = conn.execute(
        "select l.language_id, l.normalized_form, c.component_id, c.gated_component_id,"
        " c.gated_component_size, c.is_hub from lexeme l"
        " left join layers.cognate_component c on c.lexeme_id = l.id where l.id = any(%s)",
        (ids,),
    ).fetchall()
    out = set()
    for lang, form, raw_id, gated_id, size, is_hub in rows:
        if raw_id is not None and not gated:
            out.add(("raw", raw_id))
        elif gated_id is not None and not is_hub and size <= cutoff:
            out.add(("gated", gated_id))
        else:
            out.add(("key", lang, form))
    return out


def _members(conn, sup: tuple) -> list[str]:
    if sup[0] == "key":
        sql, args = "select id from lexeme where language_id = %s and normalized_form = %s", sup[1:]
    else:
        col = "component_id" if sup[0] == "raw" else "gated_component_id"
        sql, args = f"select lexeme_id from layers.cognate_component where {col} = %s", sup[1:]
    return [r[0] for r in conn.execute(sql, args).fetchall()]


def _climb(
    conn, start: tuple, gated: bool, cutoff: int, max_depth: int, datasets
) -> dict[tuple, int]:
    seen = {start: 0}
    frontier = [start]
    for depth in range(1, max_depth + 1):
        nxt = []
        for sup in frontier:
            members = _members(conn, sup)
            if not members:
                continue
            parents = [
                r[0]
                for r in conn.execute(
                    "select distinct target_lexeme_id from relationship where source_lexeme_id"
                    " = any(%s) and type_id = any(%s) and status = 'documented'"
                    " and (%s::text[] is null or dataset = any(%s))",
                    (members, list(ANCESTRY_TYPES), datasets, datasets),
                ).fetchall()
            ]
            if not parents:
                continue
            for p in _supers(conn, parents, gated, cutoff):
                if p not in seen:
                    seen[p] = depth
                    nxt.append(p)
        if not nxt:
            break
        frontier = nxt
    return seen


def _connected_by_ancestry(
    conn, a: str, b: str, gated: bool, max_depth: int, datasets=None
) -> bool:
    params = build_params(conn)
    cutoff = params["cutoff"] if params else DEFAULT_CUTOFF
    sa, sb = _supers(conn, [a], gated, cutoff), _supers(conn, [b], gated, cutoff)
    if not sa or not sb:
        return False  # a lexeme that does not exist
    (start_a,), (start_b,) = sa, sb
    if start_a == start_b:
        return start_a[0] != "key"  # one contracted component; one word key is one word
    datasets = list(datasets) if datasets else None
    la = _climb(conn, start_a, gated, cutoff, max_depth, datasets)
    lb = _climb(conn, start_b, gated, cutoff, max_depth, datasets)
    return bool(la.keys() & lb.keys())


def stats(conn: psycopg.Connection) -> dict:
    """Size distribution of the components and flagged edges per dataset, from the built tables."""
    params = build_params(conn)
    if params is None:
        return {"built": False}
    sizes = conn.execute(
        "select width_bucket(component_size, array[2,3,6,11,21,51,101,501,1001]) b,"
        " count(*) lexemes"
        " from layers.cognate_component group by 1 order by 1"
    ).fetchall()
    labels = ["1", "2", "3-5", "6-10", "11-20", "21-50", "51-100", "101-500", "501-1000", "1001+"]
    per_ds = conn.execute(
        "select r.dataset, count(*) flagged,"
        " count(*) filter (where f.reason = 'hub_lexeme') hub,"
        " count(*) filter (where f.reason = 'oversized_component') oversized"
        " from layers.edge_hub_flag f join relationship r on r.id = f.relationship_id"
        " group by 1 order by 2 desc"
    ).fetchall()
    largest = conn.execute(
        "select component_id, component_size from layers.cognate_component"
        " group by 1, 2 order by 2 desc limit 5"
    ).fetchall()
    return {
        "built": True,
        "params": params,
        "lexemes_by_component_size": [(labels[b], n) for b, n in sizes],
        "largest_components": largest,
        "flagged_edges_by_dataset": [
            {"dataset": d, "flagged": f, "hub_lexeme": h, "oversized_component": o}
            for d, f, h, o in per_ds
        ],
    }


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.layers.hub")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build layers.cognate_component and layers.edge_hub_flag")
    b.add_argument("--cutoff", type=int, default=DEFAULT_CUTOFF)
    b.add_argument("--hub-degree", type=int, default=None)
    b.add_argument("--datasets", default="")
    b.add_argument("--exclude", default="")
    sub.add_parser("stats", help="print the size distribution and flagged edges per dataset")
    ap.add_argument("--database-url", default=None)
    args = ap.parse_args(argv)
    with connect(args.database_url) as conn:
        if args.cmd == "build":
            result = build(
                conn,
                cutoff=args.cutoff,
                hub_degree=args.hub_degree,
                datasets=[d for d in args.datasets.split(",") if d] or None,
                exclude_datasets=[d for d in args.exclude.split(",") if d],
            )
            print(result)
        else:
            import json

            print(json.dumps(stats(conn), indent=1, default=str))


if __name__ == "__main__":
    main()
