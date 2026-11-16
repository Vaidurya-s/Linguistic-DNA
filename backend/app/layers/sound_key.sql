-- Sound-class blocking keys. Idempotent. One row per lexeme of an enabled language whose
-- form reduces to at least one consonant class. skey = consonant skeleton + ':' + first-vowel class
-- (see sound_key.py). COMPUTED, never documented: used only to find candidates cheaply.
create schema if not exists layers;

create table if not exists layers.sound_key (
    lexeme_id   varchar(32) primary key,
    language_id varchar(64) not null,
    skey        text        not null
);
-- text_pattern_ops makes both exact and prefix lookups ('PTR:%' = same consonants, any vowel)
-- use the index whatever the database collation is.
create index if not exists ix_sound_key_skey on layers.sound_key (skey text_pattern_ops);
create index if not exists ix_sound_key_lang_skey on layers.sound_key (language_id, skey text_pattern_ops);

create table if not exists layers.sound_key_build (
    language_id   varchar(64) primary key,
    rules_version text        not null,
    lexemes       integer     not null,
    keyed         integer     not null,
    built_at      timestamptz not null default now()
);
