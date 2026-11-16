-- Candidate layer: same-meaning words of other languages ranked by a sound-aware similarity score.
-- COMPUTED, never documented: no citation, only method, parameters, score, gate and a calibrated
-- precision. Rows never feed the documented relationship table.
create schema if not exists layers;

-- Precision of a score bin, fitted on the DEV half of the expert cognate gold (split by concept).
-- precision_dev is for the natural mix of same-meaning cross-language pairs (stratum-reweighted),
-- precision_dev_balanced for the balanced gold. `domain` says where the calibration is valid.
create table if not exists layers.candidate_calibration (
    method                  text   not null,
    gate                    text   not null,     -- oracle | gloss | concept
    stratum                 text   not null default 'all',
    score_bin               real   not null,     -- lower edge of a 0.05-wide bin
    precision_dev           real,
    precision_dev_balanced  real,
    n_dev                   integer not null,
    n_pos_dev               integer not null,
    domain                  text   not null default 'indo-european basic vocabulary',
    fitted_at               timestamptz not null default now(),
    primary key (method, gate, stratum, score_bin)
);

create table if not exists layers.candidate_pair (
    a                    text   not null,        -- lexeme id; a < b (python string order)
    b                    text   not null,
    method               text   not null,
    params               jsonb  not null default '{}'::jsonb,
    score                real   not null,
    gate                 text   not null,
    gate_via             text   not null,        -- concept | gloss
    calibrated_precision real,                   -- null where the calibration domain does not apply
    evidence_kind        text   not null default 'computed' check (evidence_kind = 'computed'),
    created_at           timestamptz not null default now(),
    primary key (a, b, method, gate)
);
create index if not exists ix_candidate_pair_b on layers.candidate_pair (b);

-- Content words of glosses and concept labels, for the gloss gate. Built by build_gloss_tokens().
create table if not exists layers.gloss_token (
    token     text     not null,
    lexeme_id text     not null,
    n_tokens  smallint not null
);
