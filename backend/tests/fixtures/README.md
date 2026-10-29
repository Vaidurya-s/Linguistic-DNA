# Test fixtures

## `jambu_mini/` — pending permission, not for deployment

29 forms, 24 edges and their concepts/references, extracted from Jambu
(`moli-mandala/data` commit `665850cdd1451391dc939063b5ccc972e646f6f6`) by
`scripts/build_fixture.py`. Records come mainly from CDIAL (Turner), DEDR (Burrow & Emeneau)
and KEED (Učida & Rajapurohit), which are `permission_required` in
`data/manifests/source_manifest.csv`.

- Used only to test the import pipeline. It must not be loaded into a public deployment or
  seed, and the `public_seed` validation mode reports it as blocked.
- It holds forms, glosses, bibliography entries and citation locators only. The `Etymology`
  column (verbatim dictionary entries) and the comparisons `Evidence` text are replaced with a
  synthetic sentinel, so tests can prove neither is ever stored.
- Remove it if the rights holders object.

## `glottolog_mini/`

Classification rows for the fixture's glottocodes from Glottolog CLDF (`glottolog-cldf` v5.3,
commit `072ca0d`), CC-BY-4.0. Hammarström, Harald & Forkel, Robert & Haspelmath, Martin & Bank,
Sebastian. 2025. Glottolog 5.2.1. Leipzig: Max Planck Institute for Evolutionary Anthropology.
(Available online at https://glottolog.org)

## `lsi_mini/`

A few rows (Tamil, Western Hindi and Japanese; concepts one, two, five) from the
Linguistic Survey of India CLDF dataset (`lexibank/lsi` v1.1, commit `133bcfc`), CC-BY-4.0.
Grierson, George Abraham (1928): Linguistic Survey of India. Comparative Vocabulary.
Calcutta. Japanese is included to test that unmapped doculects are skipped.
