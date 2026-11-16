-- Source lineage: which dataset is derived from which, ONLY where a readme, a dataset
-- metadata file or a paper says so. verified = false rows are open questions, never claims.
-- Idempotent. Nothing here touches public.* rows.
create schema if not exists layers;

create table if not exists layers.source_lineage (
    dataset       text    not null,   -- a dataset id of dataset_audit, or an external resource name
    derived_from  text    not null,   -- the dataset or resource it takes its records from
    kind          text    not null
        check (kind in ('derived', 'contains', 'shared_origin', 'unknown')),
        -- derived: built from derived_from's records; contains: ingests derived_from's records
        -- (same direction); shared_origin: both come from the same project or publication;
        -- unknown: a suspected link no document confirms (always verified = false)
    evidence_note text    not null,   -- where the statement was read (file, section, paper)
    verified      boolean not null default false,
    created_at    timestamptz not null default now(),
    primary key (dataset, derived_from, kind),
    check (kind <> 'unknown' or not verified)
);
create index if not exists ix_source_lineage_from on layers.source_lineage (derived_from);
