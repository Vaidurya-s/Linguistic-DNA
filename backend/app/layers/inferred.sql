-- Inferred layer: pairs of words put under a common ancestor by a chain of DOCUMENTED ancestry
-- relationships (inherited_form, etymon, derived_form; never borrowed_from or calques).
-- Rows exist only for pairs that were asked for or batch-materialised, not for all pairs.
-- No foreign keys: the layer is derived and can be rebuilt; a row whose lexeme or relationship
-- was deleted by a re-import is stale and is removed by `delete from layers.inferred_pair`
-- (or by re-materialising with the new rule_version).
create schema if not exists layers;

create table if not exists layers.inferred_pair (
    a                      text    not null,   -- lexeme id; a < b (python string order)
    b                      text    not null,
    kind                   text    not null
        check (kind in ('common_ancestor', 'a_ancestor_of_b', 'b_ancestor_of_a', 'cognate_component')),
    depth                  integer not null,   -- max of depth_a and depth_b
    depth_a                integer not null,
    depth_b                integer not null,
    ancestor_id            text,               -- lexeme id of the ancestor, as reached from a
    chain_relationship_ids text[]  not null,   -- documented relationship ids, a up to ancestor, then ancestor down to b
    chain_types            text[]  not null,   -- relationship type of each step, same order
    chain_datasets         text[]  not null,   -- datasets the chain rests on (licence: the strictest applies)
    capped                 boolean not null default false,  -- a search cap hit while looking for this chain
    rule_version           text    not null,
    params                 jsonb   not null default '{}'::jsonb,
    created_at             timestamptz not null default now(),
    primary key (a, b, rule_version)
);
create index if not exists ix_inferred_pair_b on layers.inferred_pair (b);
create index if not exists ix_inferred_pair_ancestor on layers.inferred_pair (ancestor_id);

-- One row per step of every stored chain, joined to the documented relationship and its evidence.
create or replace view layers.inferred_chain_step as
select p.a, p.b, p.rule_version, s.ord as step, s.rid as relationship_id,
       r.type_id, r.dataset, r.source_lexeme_id, r.target_lexeme_id,
       e.citation, e.locator
from layers.inferred_pair p
cross join lateral unnest(p.chain_relationship_ids) with ordinality as s(rid, ord)
join public.relationship r on r.id = s.rid
left join public.evidence e on e.relationship_id = r.id;
