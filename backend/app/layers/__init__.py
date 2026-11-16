"""Derived layers on top of the documented graph.

Two layers, kept in the `layers` schema and never merged into the documented relationships:

* `inferred` (inferred.py): a pair of words that a chain of documented ancestry relationships
  puts under one ancestor. Every row lists the documented relationship ids it rests on.
* `candidate` (candidate.py): same-meaning words of other languages ranked by a sound-aware
  similarity score. Computed, not documented: no citation, only a method, parameters, a score
  and a precision calibrated on held-out expert cognate judgements.

Neither layer writes to `public`.
"""

# The SQL files of the layers that ship, in the order they are applied. Migration 0007 and
# `init-layers` apply exactly these: a SQL file that is not listed here creates no table there.
SHIPPED_SQL = (
    "candidate.sql",
    "hub.sql",
    "inferred.sql",
    "keys.sql",
    "lineage.sql",
    "sound_key.sql",
)
