-- Word-identity keys. Idempotent. Only keys that DIFFER from lexeme.normalized_form are stored.
create schema if not exists layers;

create table if not exists layers.word_key (
    lexeme_id   varchar(32) not null,
    language_id varchar(64) not null,
    key_kind    text        not null,   -- 'fold' | 'translit' | 'translit_rule'
    key         text        not null,
    primary key (lexeme_id, key_kind)
);
create index if not exists ix_word_key_lookup on layers.word_key (language_id, key_kind, key);

-- One row per language the keys were built for (rules_version says which rules produced them).
create table if not exists layers.word_key_build (
    language_id   varchar(64) primary key,
    rules_version text        not null,
    lexemes       integer     not null,
    fold_rows     integer     not null,
    translit_rows integer     not null,
    built_at      timestamptz not null default now()
);

alter table layers.word_key_build add column if not exists rule_rows integer not null default 0;
