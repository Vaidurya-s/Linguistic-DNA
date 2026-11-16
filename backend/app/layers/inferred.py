"""Inferred layer: evidence chains over documented ancestry.

Two words are *inferred related* when documented relationships put them under one ancestor, or
make one the ancestor of the other. The chain is the ordered list of documented relationship ids
(each has its dataset and evidence row), so an inferred pair is never uncited: it is a short
proof over cited steps. Nothing here is created from spelling similarity.

Rules (version `RULE_VERSION`):
  * Steps follow inherited_form, etymon and derived_form from descendant (source) to ancestor
    (target). reconstructed_ancestor_of is followed in the opposite direction. borrowed_from,
    calque_or_loan_translation, contact_influence, variant_of, related_form and has_component are
    never followed (a loan does not put two words under a common ancestor).
  * A word is identified as the project does: same language and same normalised form (the same
    spelling in two datasets is one node). Pass `exclude_datasets` to hold datasets out.
  * Optionally (`cognate_hops=True`) a documented cognate relationship moves along a cognate
    component of at most `cognate_component_max` words at no depth cost. Larger components are
    homograph hubs and are never contracted.
  * Depth is counted per side in ancestry steps; the stored depth is the larger of the two.
  * The search is bounded: at most `max_frontier` nodes per level and side and `max_nodes`
    nodes per side. When a cap is hit the result says so (`capped`), because a missing chain
    can then be a missing search rather than a missing link.

The functions take a psycopg connection (as the importers and the tests do).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

RULE_VERSION = "ancestry-v1"
ANCESTRY_UP = ("inherited_form", "etymon", "derived_form")  # source descends from target
ANCESTRY_DOWN = ("reconstructed_ancestor_of",)  # source is an ancestor of target
NEVER_FOLLOWED = (
    "borrowed_from",
    "calque_or_loan_translation",
    "contact_influence",
    "variant_of",
    "related_form",
    "has_component",
)
COGNATE = "cognate"
SQL_FILE = Path(__file__).with_name("inferred.sql")


def rule_version_for(cognate_hops: bool = False, cognate_component_max: int = 50) -> str:
    """Rows made with different rules live side by side: the version names the rule."""
    return f"{RULE_VERSION}+cognate{cognate_component_max}" if cognate_hops else RULE_VERSION


Node = tuple[str, str]  # (language_id, normalized_form)
Step = tuple[str, str, str]  # (relationship id, type, dataset)


def ensure_schema(conn) -> None:
    """Create the layer tables if they do not exist (idempotent)."""
    conn.execute(SQL_FILE.read_text(encoding="utf-8"))


@dataclass
class InferredChain:
    lexeme_a: str
    lexeme_b: str
    kind: str  # common_ancestor | a_ancestor_of_b | b_ancestor_of_a | cognate_component
    depth: int
    depth_a: int
    depth_b: int
    ancestor_id: str | None
    relationship_ids: list[str]
    types: list[str]
    datasets: list[str]
    capped: bool = False
    rule_version: str = RULE_VERSION
    params: dict = field(default_factory=dict)


@dataclass
class _Reach:
    depth: int
    path: tuple[Step, ...]
    lexeme_id: str | None  # a lexeme of this node reached by the last ancestry step


class AncestryWalker:
    """Bounded walks over documented ancestry, with a cache of parent lookups.

    One walker can serve many pairs (batch materialisation); the cache is what makes that cheap.
    `stats` counts how often a search cap was hit."""

    def __init__(
        self,
        conn,
        max_depth: int = 8,
        *,
        ancestry_types: Sequence[str] = ANCESTRY_UP,
        reverse_types: Sequence[str] = ANCESTRY_DOWN,
        datasets: Sequence[str] | None = None,
        exclude_datasets: Sequence[str] = (),
        cognate_hops: bool = False,
        cognate_component_max: int = 50,
        max_frontier: int = 500,
        max_nodes: int = 5000,
    ) -> None:
        banned = set(NEVER_FOLLOWED) | {COGNATE}
        if banned & set(ancestry_types) or banned & set(reverse_types):
            raise ValueError("loan and non-ancestry types can never be ancestry steps")
        self.conn = conn
        self.max_depth = max_depth
        self.up = list(ancestry_types)
        self.down = list(reverse_types)
        self.datasets = list(datasets) if datasets is not None else None
        self.exclude = list(exclude_datasets)
        self.cognate_hops = cognate_hops
        self.cognate_component_max = cognate_component_max
        self.max_frontier = max_frontier
        self.max_nodes = max_nodes
        self._parents: dict[Node, list[tuple[Step, Node, str]]] = {}
        self._cog: dict[Node, list[tuple[Step, Node]]] = {}
        self.rule_version = rule_version_for(cognate_hops, cognate_component_max)
        self.stats = {"frontier_capped": 0, "node_cap": 0, "cognate_hub_skipped": 0, "sql": 0}

    # ---- parameters recorded with every row
    @property
    def params(self) -> dict:
        return {
            "max_depth": self.max_depth,
            "ancestry_types": self.up,
            "reverse_types": self.down,
            "cognate_hops": self.cognate_hops,
            "cognate_component_max": self.cognate_component_max,
            "max_frontier": self.max_frontier,
            "max_nodes": self.max_nodes,
            "datasets": self.datasets,
            "exclude_datasets": self.exclude,
        }

    # ---- SQL
    def _ds_clause(self) -> tuple[str, list]:
        sql, args = "", []
        if self.datasets is not None:
            sql += " and r.dataset = any(%s)"
            args.append(self.datasets)
        if self.exclude:
            sql += " and r.dataset <> all(%s)"
            args.append(self.exclude)
        return sql, args

    def _fetch_parents(self, nodes: Iterable[Node]) -> None:
        todo = sorted(n for n in set(nodes) if n not in self._parents)
        for i in range(0, len(todo), 5000):
            chunk = todo[i : i + 5000]
            langs, forms = [n[0] for n in chunk], [n[1] for n in chunk]
            found: dict[Node, list[tuple[Step, Node, str]]] = {n: [] for n in chunk}
            ds_sql, ds_args = self._ds_clause()
            queries = []
            if self.up:
                queries.append(
                    (
                        "select ls.language_id, ls.normalized_form, r.id, r.type_id, r.dataset,"
                        " lt.language_id, lt.normalized_form, lt.id"
                        " from unnest(%s::text[], %s::text[]) as t(l, f)"
                        " join lexeme ls on ls.language_id = t.l and ls.normalized_form = t.f"
                        " join relationship r on r.source_lexeme_id = ls.id"
                        " join lexeme lt on lt.id = r.target_lexeme_id"
                        " where r.type_id = any(%s) and r.direction = 'directed'" + ds_sql,
                        [langs, forms, self.up, *ds_args],
                    )
                )
            if self.down:
                queries.append(
                    (
                        "select ls.language_id, ls.normalized_form, r.id, r.type_id, r.dataset,"
                        " lt.language_id, lt.normalized_form, lt.id"
                        " from unnest(%s::text[], %s::text[]) as t(l, f)"
                        " join lexeme ls on ls.language_id = t.l and ls.normalized_form = t.f"
                        " join relationship r on r.target_lexeme_id = ls.id"
                        " join lexeme lt on lt.id = r.source_lexeme_id"
                        " where r.type_id = any(%s) and r.direction = 'directed'" + ds_sql,
                        [langs, forms, self.down, *ds_args],
                    )
                )
            for sql, args in queries:
                self.stats["sql"] += 1
                with self.conn.cursor() as cur:
                    cur.execute(sql, args)
                    for sl, sf, rid, ty, ds, tl, tf, tid in cur.fetchall():
                        if (sl, sf) != (tl, tf):
                            found[(sl, sf)].append(((rid, ty, ds), (tl, tf), tid))
            for n, lst in found.items():
                self._parents[n] = sorted(set(lst))

    def _fetch_cognate(self, nodes: Iterable[Node]) -> None:
        todo = sorted(n for n in set(nodes) if n not in self._cog)
        for i in range(0, len(todo), 5000):
            chunk = todo[i : i + 5000]
            langs, forms = [n[0] for n in chunk], [n[1] for n in chunk]
            found: dict[Node, list[tuple[Step, Node]]] = {n: [] for n in chunk}
            ds_sql, ds_args = self._ds_clause()
            for near, far in (("source", "target"), ("target", "source")):
                sql = (
                    "select ln.language_id, ln.normalized_form, r.id, r.type_id, r.dataset,"
                    " lf.language_id, lf.normalized_form"
                    " from unnest(%s::text[], %s::text[]) as t(l, f)"
                    f" join lexeme ln on ln.language_id = t.l and ln.normalized_form = t.f"
                    f" join relationship r on r.{near}_lexeme_id = ln.id"
                    f" join lexeme lf on lf.id = r.{far}_lexeme_id"
                    " where r.type_id = 'cognate'" + ds_sql
                )
                self.stats["sql"] += 1
                with self.conn.cursor() as cur:
                    cur.execute(sql, [langs, forms, *ds_args])
                    for nl, nf, rid, ty, ds, fl, ff in cur.fetchall():
                        if (nl, nf) != (fl, ff):
                            found[(nl, nf)].append(((rid, ty, ds), (fl, ff)))
            for n, lst in found.items():
                self._cog[n] = sorted(set(lst))

    # ---- cognate contraction (bounded)
    def _component(self, start: Node) -> dict[Node, tuple[Step, ...]]:
        """Nodes reachable from `start` over cognate relationships with the path to each; just
        {start} when the component has more than `cognate_component_max` nodes."""
        paths: dict[Node, tuple[Step, ...]] = {start: ()}
        frontier = [start]
        while frontier:
            self._fetch_cognate(frontier)
            nxt = []
            for n in frontier:
                for step, m in self._cog.get(n, ()):
                    if m not in paths:
                        paths[m] = paths[n] + (step,)
                        nxt.append(m)
                if len(paths) > self.cognate_component_max:
                    self.stats["cognate_hub_skipped"] += 1
                    return {start: ()}
            frontier = nxt
        return paths

    # ---- one side of the search
    def _climb(self, start: Node, start_lexeme: str) -> tuple[dict[Node, _Reach], bool]:
        capped = False
        reach: dict[Node, _Reach] = {}

        def add(node: Node, depth: int, path: tuple[Step, ...], lex: str | None) -> list[Node]:
            """Add a node (and, with cognate hops, its component); returns the new nodes."""
            new = []
            members = {node: ()}
            if self.cognate_hops:
                members = self._component(node)
            for m, cpath in members.items():
                if m not in reach:
                    reach[m] = _Reach(depth, path + cpath, lex if m == node else None)
                    new.append(m)
            return new

        frontier = add(start, 0, (), start_lexeme)
        for depth in range(1, self.max_depth + 1):
            if not frontier:
                break
            if len(frontier) > self.max_frontier:
                frontier = sorted(frontier)[: self.max_frontier]
                self.stats["frontier_capped"] += 1
                capped = True
            self._fetch_parents(frontier)
            nxt: list[Node] = []
            for n in frontier:
                for step, parent, plex in self._parents.get(n, ()):
                    if parent in reach:
                        continue
                    nxt.extend(add(parent, depth, reach[n].path + (step,), plex))
                if len(reach) >= self.max_nodes:
                    self.stats["node_cap"] += 1
                    return reach, True
            frontier = nxt
        return reach, capped

    # ---- public
    def _node_of(self, lexeme_id: str) -> Node:
        with self.conn.cursor() as cur:
            cur.execute(
                "select language_id, normalized_form from lexeme where id = %s", (lexeme_id,)
            )
            row = cur.fetchone()
        if row is None:
            raise ValueError(f"unknown lexeme id {lexeme_id!r}")
        return (row[0], row[1])

    def chain(self, lexeme_a: str, lexeme_b: str) -> tuple[InferredChain | None, dict]:
        """The chain between two lexemes (canonical order: smaller id first) and a report
        {'capped': bool, 'nodes_a': int, 'nodes_b': int}."""
        a, b = sorted((lexeme_a, lexeme_b))
        na, nb = self._node_of(a), self._node_of(b)
        if na == nb:
            return None, {
                "capped": False,
                "nodes_a": 0,
                "nodes_b": 0,
                "same_word": True,
                "shared_ancestor": False,
            }
        ra, cap_a = self._climb(na, a)
        rb, cap_b = self._climb(nb, b)
        report = {"capped": cap_a or cap_b, "nodes_a": len(ra), "nodes_b": len(rb)}
        common = ra.keys() & rb.keys()
        # a common ancestor strictly above both words (not one word itself), for callers that
        # need the documented baseline 'shares an ancestor'
        report["shared_ancestor"] = any(ra[n].depth > 0 and rb[n].depth > 0 for n in common)
        if not common:
            return None, report
        best = min(
            common,
            key=lambda n: (
                max(ra[n].depth, rb[n].depth),
                ra[n].depth + rb[n].depth,
                len(ra[n].path) + len(rb[n].path),
                n,
            ),
        )
        x, y = ra[best], rb[best]
        if x.depth == 0 and y.depth == 0:
            kind = "cognate_component"  # joined only through a documented cognate component
        elif x.depth == 0:
            kind = "a_ancestor_of_b"
        elif y.depth == 0:
            kind = "b_ancestor_of_a"
        else:
            kind = "common_ancestor"
        steps = list(x.path) + list(reversed(y.path))
        ancestor = x.lexeme_id or y.lexeme_id
        out = InferredChain(
            lexeme_a=a,
            lexeme_b=b,
            kind=kind,
            depth=max(x.depth, y.depth),
            depth_a=x.depth,
            depth_b=y.depth,
            ancestor_id=ancestor,
            relationship_ids=[s[0] for s in steps],
            types=[s[1] for s in steps],
            datasets=sorted({s[2] for s in steps}),
            capped=report["capped"],
            rule_version=self.rule_version,
            params=self.params,
        )
        return out, report


def inferred_chain(
    conn,
    lexeme_a: str,
    lexeme_b: str,
    max_depth: int = 8,
    *,
    report: dict | None = None,
    **options,
) -> InferredChain | None:
    """The documented chain that makes two words descendants of a common ancestor, or one the
    ancestor of the other; None when there is none within the bounds.

    `report`, if given, is filled with {'capped': bool, ...}: when capped is True a None result
    may be a search that was cut short on a hub, not proof that no chain exists.
    `options` are the AncestryWalker options (datasets, exclude_datasets, cognate_hops, ...)."""
    walker = AncestryWalker(conn, max_depth, **options)
    result, rep = walker.chain(lexeme_a, lexeme_b)
    rep["stats"] = dict(walker.stats)
    if report is not None:
        report.update(rep)
    return result


def _insert(conn, c: InferredChain) -> None:
    conn.execute(
        "insert into layers.inferred_pair (a, b, kind, depth, depth_a, depth_b, ancestor_id,"
        " chain_relationship_ids, chain_types, chain_datasets, capped, rule_version, params)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        " on conflict (a, b, rule_version) do update set kind = excluded.kind,"
        " depth = excluded.depth, depth_a = excluded.depth_a, depth_b = excluded.depth_b,"
        " ancestor_id = excluded.ancestor_id,"
        " chain_relationship_ids = excluded.chain_relationship_ids,"
        " chain_types = excluded.chain_types, chain_datasets = excluded.chain_datasets,"
        " capped = excluded.capped, params = excluded.params, created_at = now()",
        (
            c.lexeme_a,
            c.lexeme_b,
            c.kind,
            c.depth,
            c.depth_a,
            c.depth_b,
            c.ancestor_id,
            c.relationship_ids,
            c.types,
            c.datasets,
            c.capped,
            c.rule_version,
            json.dumps(c.params),
        ),
    )


def materialise_inferred(
    conn, pairs: Iterable[tuple[str, str]], walker: AncestryWalker | None = None, **options
) -> dict:
    """Compute and store the chains of the given pairs only (never all pairs).

    Pairs without a chain get no row. Returns counts: found, none, capped_none (no chain found
    while a cap was hit), so a reader can tell 'no link' from 'search cut short'."""
    walker = walker or AncestryWalker(conn, **options)
    counts = {"pairs": 0, "found": 0, "none": 0, "capped_none": 0}
    for a, b in pairs:
        counts["pairs"] += 1
        chain, rep = walker.chain(a, b)
        if chain is None:
            counts["none"] += 1
            counts["capped_none"] += bool(rep.get("capped"))
        else:
            counts["found"] += 1
            _insert(conn, chain)
    return counts


def stored_inferred(conn, lexeme_a: str, lexeme_b: str, rule_version: str | None = None):
    """The stored row of a pair as a dict, or None."""
    a, b = sorted((lexeme_a, lexeme_b))
    rule_version = rule_version or RULE_VERSION
    with conn.cursor() as cur:
        cur.execute(
            "select a, b, kind, depth, depth_a, depth_b, ancestor_id, chain_relationship_ids,"
            " chain_types, chain_datasets, capped, rule_version from layers.inferred_pair"
            " where a = %s and b = %s and rule_version = %s",
            (a, b, rule_version),
        )
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d.name for d in cur.description]
    return dict(zip(cols, row, strict=True))


def get_inferred(conn, lexeme_a: str, lexeme_b: str, max_depth: int = 8, **options):
    """Stored row if present; else compute, store when found, and return it (a pair the
    retrieval service asks about gets materialised on first request)."""
    version = rule_version_for(
        options.get("cognate_hops", False), options.get("cognate_component_max", 50)
    )
    row = stored_inferred(conn, lexeme_a, lexeme_b, version)
    if row is not None:
        return row
    chain = inferred_chain(conn, lexeme_a, lexeme_b, max_depth, **options)
    if chain is None:
        return None
    _insert(conn, chain)
    return stored_inferred(conn, lexeme_a, lexeme_b, version)
