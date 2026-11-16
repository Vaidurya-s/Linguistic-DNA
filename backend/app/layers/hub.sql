-- cognate components and hub gating. Idempotent. Nothing here touches public.* rows.
-- A word is a (language_id, normalized_form) key, the identity the project uses across datasets;
-- every lexeme row of a key carries the key's component.
create schema if not exists layers;

create table if not exists layers.cognate_component (
    lexeme_id text primary key,
    component_id text not null,          -- id of the connected component over documented cognate links
    component_size integer not null,     -- number of word keys in that component
    degree integer not null,             -- distinct cognate neighbours of the word key
    is_hub boolean not null default false,        -- degree > hub_degree of the build (never when no hub rule)
    gated_component_id text not null,    -- component after removing hub words (= component_id without a hub rule)
    gated_component_size integer not null
);
create index if not exists ix_cognate_component_comp on layers.cognate_component (component_id);
create index if not exists ix_cognate_component_gated on layers.cognate_component (gated_component_id);

create table if not exists layers.edge_hub_flag (
    relationship_id text primary key,    -- a documented cognate relationship (public.relationship.id)
    component_id text not null,
    reason text not null                 -- oversized_component | hub_lexeme
);
create index if not exists ix_edge_hub_flag_comp on layers.edge_hub_flag (component_id);

create table if not exists layers.cognate_component_build (
    id integer primary key default 1 check (id = 1),
    cutoff integer not null,
    hub_degree integer,
    datasets text,                       -- comma list when the build was limited, else null (all datasets)
    exclude_datasets text,
    relationship_type text not null,
    edges bigint not null,
    word_keys bigint not null,
    components bigint not null,
    flagged_edges bigint not null,
    built_at timestamptz not null default now()
);
