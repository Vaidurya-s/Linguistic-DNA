"""Fill layers.candidate_calibration from the expert cognate judgements of IE-CoR.

The candidate layer shows a precision for a score. That precision is measured here, on held-out
expert judgements, and stored per (method, gate, clade stratum) in layers.candidate_calibration.

Gold pairs (read from the IE-CoR CLDF files, which the importer uses too): positives are two forms
of different languages in the same expert cognate set; negatives are two forms of one concept and
different languages that share no cognate set. Forms flagged as loans are left out. A seeded sample
of up to ``n_pairs`` of each is drawn. The pairs are split by concept: the parity of
``int(md5(concept_id)[:8], 16)`` (even = dev, odd = test). The calibration is fitted on the dev half
only, so the test half stays untouched for checking.

Every gold word is looked up in the database by (language, normalised form) among the lexemes of the
audit-approved datasets, without the held-out datasets (IE-CoR itself and DunniLex), so a word is
never scored against its own source. A pair is scored exactly as ``candidates_for`` scores a
candidate: the two words must pass a gate (a shared concept link; or, for the gloss gate, a shared
content word of the glosses) and the pair carries the best blend score over the lexeme pairs that
pass. The scores of the pairs that pass a gate are binned and fitted with ``fit_calibration``:
overall (stratum ``all``) and per clade stratum of the two languages (same sub-branch, same branch,
different branches, from the Glottolog classification path). Precision is weighted to the natural
mix of positive and negative pairs of each stratum, counted in the same IE-CoR files.

CLI: ``python -m app.cli calibrate-candidates [--raw DIR] [--dry-run]``.
"""

from __future__ import annotations

import csv
import hashlib
import random
from collections import defaultdict
from collections.abc import Iterable
from itertools import combinations
from pathlib import Path

from app.layers import candidate as cand

METHOD = cand.DEFAULT_METHOD
GATES = ("gloss", "concept")
HELD_OUT = ("iecor", "dunnielex")
DATASET = "iecor"
SEED = 20261110
N_PAIRS = 20000
FORM_KINDS = ("word", "compound", "root", "stem")
CHUNK = 20000
REPO_ROOT = Path(__file__).resolve().parents[3]
RAW_ROOT = REPO_ROOT / "data" / "raw"


def half_of(concept_id: str) -> str:
    """'dev' or 'test' by the parity of the concept's md5 (fixed before any result was seen)."""
    return (
        "dev" if int(hashlib.md5(str(concept_id).encode()).hexdigest()[:8], 16) % 2 == 0 else "test"
    )


def _read(path: Path) -> Iterable[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        yield from csv.DictReader(fh)


def _loan(row: dict) -> bool:
    return (row.get("Loan") or "").strip().lower() in ("true", "1", "yes")


def read_cldf(cldf: Path) -> tuple[dict, dict, dict, dict]:
    """(forms by id, cognate sets of each non-loan form, member forms of each set, cognate sets of
    every form including loans). The gold leaves loans out; the natural mix counts every form."""
    forms = {r["ID"]: r for r in _read(cldf / "forms.csv")}
    loans = {f for f, r in forms.items() if _loan(r)}
    sets_of: dict[str, set] = defaultdict(set)
    sets_all: dict[str, set] = defaultdict(set)
    members: dict[str, set] = defaultdict(set)
    for r in _read(cldf / "cognates.csv"):
        f, s = r["Form_ID"], r["Cognateset_ID"]
        if s and f in forms:
            sets_all[f].add(s)
            if f not in loans:
                sets_of[f].add(s)
                members[s].add(f)
    return forms, sets_of, members, sets_all


def gold_pairs(
    forms: dict,
    sets_of: dict,
    members: dict,
    key: dict[str, tuple[str, str]],
    n_pos: int = N_PAIRS,
    n_neg: int = N_PAIRS,
    seed: int = SEED,
) -> list[dict]:
    """Seeded positive and negative pairs of forms. ``key`` maps a form id to its database word,
    (language_id, normalised_form); a form with no database word is never drawn."""
    rng = random.Random(seed)
    pos = []
    for sid in sorted(members):
        have = sorted(f for f in members[sid] if f in key)
        cross = [(a, b) for a, b in combinations(have, 2) if key[a][0] != key[b][0]]
        for a, b in rng.sample(cross, min(50, len(cross))):
            pos.append((a, b, forms[a]["Parameter_ID"]))
    rng.shuffle(pos)
    pos = pos[:n_pos]
    by_concept = defaultdict(list)
    for f in sets_of:
        if f in key:
            by_concept[forms[f]["Parameter_ID"]].append(f)
    neg, seen = [], set()
    concepts = sorted(c for c, v in by_concept.items() if len(v) >= 2)
    guard = 0
    while concepts and len(neg) < n_neg and guard < n_neg * 50:
        guard += 1
        c = rng.choice(concepts)
        a, b = rng.sample(by_concept[c], 2)
        if key[a][0] == key[b][0] or sets_of[a] & sets_of[b] or key[a] == key[b]:
            continue
        if (a, b) in seen or (b, a) in seen:
            continue
        seen.add((a, b))
        neg.append((a, b, c))
    return [
        {"label": label, "id_a": a, "id_b": b, "concept": c, "half": half_of(c)}
        for label, items in ((1, pos), (0, neg))
        for a, b, c in items
    ]


def natural_counts(forms: dict, sets_of: dict, stratum_of_forms) -> dict:
    """{half: {stratum: [pairs, cognate pairs]}}: every same-concept pair of forms of different
    languages in the IE-CoR files, as they occur naturally. ``stratum_of_forms(a, b)`` names the
    stratum of two forms."""
    by_concept = defaultdict(list)
    for f in sets_of:
        by_concept[forms[f]["Parameter_ID"]].append(f)
    out: dict[str, dict[str, list[int]]] = {"dev": {}, "test": {}}
    for concept, fs in by_concept.items():
        half = half_of(concept)
        for a, b in combinations(fs, 2):
            if forms[a]["Language_ID"] == forms[b]["Language_ID"]:
                continue
            cell = out[half].setdefault(stratum_of_forms(a, b), [0, 0])
            cell[0] += 1
            cell[1] += bool(sets_of[a] & sets_of[b])
    return out


def natural_weights(rows: list[dict], natural: dict) -> list[float]:
    """Weights that re-weight the gold of each (half, stratum) to the natural mix: a positive
    weighs (natural cognate pairs / gold positives), a negative (natural other pairs / gold
    negatives)."""
    count = defaultdict(lambda: [0, 0])
    for r in rows:
        count[(r["half"], r["stratum"])][r["label"]] += 1
    weights = []
    for r in rows:
        total, cognate = natural[r["half"]].get(r["stratum"], [0, 0])
        n_neg, n_pos = count[(r["half"], r["stratum"])]
        if r["label"]:
            weights.append(cognate / n_pos if n_pos else 0.0)
        else:
            weights.append((total - cognate) / n_neg if n_neg else 0.0)
    return weights


def _open_datasets(conn) -> list[str]:
    rows = conn.execute("SELECT id FROM dataset_audit WHERE decision::text LIKE 'APPROVED%'")
    return sorted(r[0] for r in rows.fetchall() if r[0] not in HELD_OUT)


def _word_keys(conn, form_ids: list[str]) -> dict[str, tuple[str, str]]:
    key = {}
    for i in range(0, len(form_ids), CHUNK):
        cur = conn.execute(
            "SELECT source_record_id, language_id, normalized_form FROM lexeme"
            " WHERE dataset = %s AND source_record_id = ANY(%s)",
            (DATASET, form_ids[i : i + CHUNK]),
        )
        for sid, lang, nf in cur.fetchall():
            key[sid] = (lang, nf)
    return key


def _lexemes_by_key(conn, keys: list[tuple[str, str]], datasets: list[str]) -> dict:
    """{(language, normalised form): [{'text', 'tokens', 'concepts'}]} for the scorable lexemes of
    the given datasets."""
    out: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_id: dict[str, dict] = {}
    for i in range(0, len(keys), CHUNK):
        chunk = keys[i : i + CHUNK]
        cur = conn.execute(
            "SELECT x.id, x.language_id, x.normalized_form, x.form, x.transliteration,"
            " x.search_key, left(x.gloss, 300)"
            " FROM unnest(%s::text[], %s::text[]) AS t(l, f)"
            " JOIN lexeme x ON x.language_id = t.l AND x.normalized_form = t.f"
            " WHERE x.dataset = ANY(%s) AND x.form_kind::text = ANY(%s)",
            ([k[0] for k in chunk], [k[1] for k in chunk], datasets, list(FORM_KINDS)),
        )
        for lid, lang, nf, form, translit, search_key, gloss in cur.fetchall():
            d = {
                "text": cand.scoring_text(form, translit, search_key),
                "tokens": set(cand.gloss_tokens(gloss)),
                "concepts": set(),
            }
            out[(lang, nf)].append(d)
            by_id[lid] = d
    ids = sorted(by_id)
    for i in range(0, len(ids), CHUNK):
        cur = conn.execute(
            "SELECT lc.lexeme_id, lc.concept_id, c.label FROM lexeme_concept lc"
            " JOIN concept c ON c.id = lc.concept_id WHERE lc.lexeme_id = ANY(%s)",
            (ids[i : i + CHUNK],),
        )
        for lid, cid, label in cur.fetchall():
            by_id[lid]["concepts"].add(cid)
            by_id[lid]["tokens"].update(cand.concept_tokens(label))
    return out


def _best_scores(la: list[dict], lb: list[dict], method: str) -> dict[str, float | None]:
    """Best score per gate over the lexeme pairs of two words that pass the gate."""
    best: dict[str, float | None] = dict.fromkeys(GATES)
    scores: dict[tuple[str, str], float] = {}
    for x in la:
        for y in lb:
            via = cand.gate_passes("gloss", x["tokens"], y["tokens"], x["concepts"], y["concepts"])
            if via is None:
                continue
            pair = (x["text"], y["text"])
            if pair not in scores:
                scores[pair] = cand.score(method, *pair)
            s = scores[pair]
            for gate in GATES:
                if (via == "concept" or gate == "gloss") and (best[gate] is None or s > best[gate]):
                    best[gate] = s
    return best


def calibrate(
    conn,
    raw_root: Path = RAW_ROOT,
    *,
    method: str = METHOD,
    n_pairs: int = N_PAIRS,
    seed: int = SEED,
    store: bool = True,
    log=lambda msg: None,
) -> dict:
    """Build the gold, score it on the database words, fit the dev half and store the calibration.

    Returns the counts: gold pairs per half, pairs that pass each gate, and the bins stored per
    (gate, stratum). With ``store=False`` nothing is written. Needs the IE-CoR files of the
    importer (``<raw_root>/iecor/cldf``) and the IE-CoR lexemes in the database."""
    cldf = Path(raw_root) / DATASET / "cldf"
    if not (cldf / "forms.csv").exists():
        raise FileNotFoundError(f"IE-CoR CLDF files not found in {cldf}")
    forms, sets_of, members, sets_all = read_cldf(cldf)
    key = _word_keys(conn, sorted(forms))
    rows = gold_pairs(forms, sets_of, members, key, n_pairs, n_pairs, seed)
    log(f"gold pairs: {len(rows)}")

    # Glottolog classification path of every database language the gold touches
    langs = {key[r[k]][0] for r in rows for k in ("id_a", "id_b")}
    form_lang = {}  # IE-CoR language id -> database language id, through the IE-CoR lexemes
    for f, (lang, _nf) in key.items():
        form_lang.setdefault(forms[f]["Language_ID"], lang)
    langs |= set(form_lang.values())
    path = {}
    for lid, p in conn.execute(
        "SELECT id, metadata_json->'classification_path' FROM language WHERE id = ANY(%s)",
        (sorted(langs),),
    ).fetchall():
        path[lid] = p

    def stratum_of_langs(a: str | None, b: str | None) -> str:
        return cand.clade_stratum(path.get(a), path.get(b))

    natural = natural_counts(
        forms,
        sets_all,
        lambda a, b: stratum_of_langs(
            form_lang.get(forms[a]["Language_ID"]), form_lang.get(forms[b]["Language_ID"])
        ),
    )

    keys = sorted({key[r[k]] for r in rows for k in ("id_a", "id_b")})
    lex = _lexemes_by_key(conn, keys, _open_datasets(conn))
    log(f"database words of the gold: {len(keys)}; with a usable lexeme: {len(lex)}")
    for r in rows:
        ka, kb = key[r["id_a"]], key[r["id_b"]]
        r["stratum"] = stratum_of_langs(ka[0], kb[0])
        r["score"] = _best_scores(lex.get(ka, []), lex.get(kb, []), method)

    dev = [r for r in rows if r["half"] == "dev"]
    weight = dict(zip(map(id, dev), natural_weights(dev, natural), strict=True))
    summary = {
        "method": method,
        "pairs": {h: sum(r["half"] == h for r in rows) for h in ("dev", "test")},
        "pass_gate": {g: sum(r["score"][g] is not None for r in rows) for g in GATES},
        "bins": {},
    }
    for gate in GATES:
        for stratum in ("all", *cand.STRATA):
            sub = [
                r
                for r in dev
                if r["score"][gate] is not None and (stratum == "all" or r["stratum"] == stratum)
            ]
            if not sub:
                continue
            fitted = cand.fit_calibration(
                [r["score"][gate] for r in sub],
                [r["label"] for r in sub],
                [weight[id(r)] for r in sub],
            )
            summary["bins"][f"{gate}/{stratum}"] = len(fitted)
            if store:
                cand.store_calibration(conn, method, gate, fitted, stratum=stratum)
    log(f"calibration {'stored' if store else 'computed (dry run)'}: {summary['bins']}")
    return summary
