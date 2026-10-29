# Dataset Audit — Jambu (`moli-mandala/data`)

First audit for the [Dataset and Licensing Plan](DATASET_AND_LICENSING_PLAN.md) (§2.1, §3, §10). It covers coverage, schema fit against the [Technical Architecture](TECHNICAL_ARCHITECTURE.md) (§5–6), and licence status. Licence findings are recorded in [`data/manifests/source_manifest.csv`](../data/manifests/source_manifest.csv).

**Status:** preliminary. This audit only read the upstream repository. Nothing from it is committed here. The licence calls below are working positions, not legal conclusions.

## 1. Snapshot audited

| Item | Value |
|---|---|
| Repository | <https://github.com/moli-mandala/data> |
| Commit | `665850cdd1451391dc939063b5ccc972e646f6f6` (2026-09-26) |
| Access date | 2026-10-29 |
| `cldf/forms.csv` | Git LFS object, 194,542,651 bytes, sha256 `b08eb1f0e04777ff8a204b013829d5a3c7cdbde4a54665fd948256ed223bfd28` (checksum verified) |
| Total forms | 991,379 rows; 578 languages; 2,166 dialect rows; 2,648 reference records; 3,321 concepts |

To reproduce the snapshot:

```bash
GIT_LFS_SKIP_SMUDGE=1 git clone https://github.com/moli-mandala/data data/raw/jambu
git -C data/raw/jambu checkout 665850cdd1451391dc939063b5ccc972e646f6f6
curl -L -o data/raw/jambu/cldf/forms.csv https://media.githubusercontent.com/media/moli-mandala/data/665850cdd1451391dc939063b5ccc972e646f6f6/cldf/forms.csv
sha256sum data/raw/jambu/cldf/forms.csv   # expect b08eb1f0…bd28
```

`data/raw/` is git-ignored. The coverage table in §3 is produced by `python scripts/jambu_coverage.py data/raw/jambu/cldf/forms.csv data/raw/jambu/cldf/form_concepts.csv`.

## 2. Headline findings

1. **The repository has no top-level licence.** No `LICENSE` file exists at the root, and `pyproject.toml` declares none. Licence files exist only for a few individual raw-data packages. The aggregate has no stated reuse terms, so it is recorded as `unknown`.
2. **Most of the historical relationships for our languages come from CDIAL (Turner 1962–66) and DEDR (Burrow & Emeneau 1984).** Both are Oxford University Press works that are still in copyright, digitised by DSAL. Their reuse terms could not be checked from this session because the network policy blocks `dsal.uchicago.edu`. Until permission is confirmed, they are `permission_required` and cannot go into a public seed.
3. **The `Etymology` column holds verbatim dictionary-entry HTML** in 232,230 rows (for example, the full CDIAL entry text). This is the most sensitive field for copyright. Never import it into a public build. Store an entry locator and a link instead.
4. **Native-script coverage is almost absent for most modern target languages.** `Form` is a scholarly romanisation (Turner/DEDR conventions). Hindi has 12 native-script forms; Bengali, Gujarati, Punjabi, Odia, Assamese, Tamil, Telugu and Malayalam have 0. Only Kannada (from KEED), Sanskrit and Prakrit (from Sheth) have substantial native script. Native-script search, a core product requirement, therefore needs a romanisation-to-script conversion step. Its outputs must be marked as derived.
5. **The published CLDF metadata does not match the data files.**
   - `Wordlist-metadata.json` lists a `Parameter_ID` column. The actual `forms.csv` header lacks it and adds `Tags`, `Etymology`, `Redirect` and `Status`.
   - The metadata references `parameters.csv`, which is not in the repository.

   An off-the-shelf `pycldf` load would fail, so the importer must read real headers and validate them itself.
6. **Relationship data is rich and directional.**
   - `edges.csv` has 463,329 edges: `reflex` 374,682; `variant` 36,193; `derived` 24,135; `component` 17,432; `borrowed` 10,887. Each edge carries a source and locator, for example `dunkel2014lipp[p. 179]`.
   - `comparisons.csv` has 29,049 comparisons with `Relation` (related/loan/influence), `Direction` and `Confidence`.

   Both map well onto our `relationship` and `evidence` tables.

## 3. Per-language coverage (Jambu snapshot, all sources)

Column definitions:

- **Forms:** rows in `forms.csv` for the language ID.
- **Concepts:** distinct concept IDs linked through `form_concepts.csv`.
- **Etymon-linked:** forms with a `Cognateset`, meaning they are linked to a CDIAL/DEDR/other etymon. This is the proxy for source-backed historical relationships.
- **Unlinked:** rows with `Status=unlinked`.
- **Native script:** forms with a non-empty `Native` field. Every form has a romanised `Form`.
- **Phonemic:** non-empty `Phonemic` field. This is source transcription, not normalised IPA.

| Language (Jambu ID) | Forms | Concepts | Etymon-linked | Unlinked | Native script | Phonemic | Main sources |
|---|---:|---:|---:|---:|---:|---:|---|
| Hindi-Urdu (`H`) | 18,475 | 1,916 | 9,789 | 6,103 | 12 | 2,611 | CDIAL 9,844; ORGI census UP 3,457; Kannauji 1,885 |
| Bengali (`B`) | 7,151 | 1,467 | 4,571 | 2,251 | 0 | 1,893 | CDIAL 4,574; Grierson LSI 1,303 |
| Marathi (`M`) | 59,541 | 1,891 | 7,811 | 51,092 | 1 | 47,893 | SDML 47,317; CDIAL 7,850 |
| Gujarati (`G`) | 7,793 | 1,519 | 6,908 | 882 | 0 | 843 | CDIAL 6,909; Grierson LSI 843 |
| Punjabi (`P`) | 9,048 | 1,593 | 7,214 | 1,414 | 0 | 799 | CDIAL 7,218; Grierson LSI 580 |
| Odia (`Or`) | 7,625 | 1,653 | 6,019 | 1,471 | 0 | 412 | CDIAL 6,016; ORGI census Orissa 1,165 |
| Assamese (`A`) | 3,721 | 1,158 | 3,486 | 233 | 0 | 209 | CDIAL 3,486; Kakati AFD 325 |
| Tamil (`Tamil`) | 13,456 | 2,050 | 12,392 | 1,086 | 0 | 576 | DEDR 12,007 |
| Telugu (`Telugu`) | 9,094 | 1,726 | 8,646 | 318 | 0 | 315 | DEDR 8,498 |
| Kannada (`Kannada`) | 56,514 | 2,389 | 11,498 | 23,990 | 41,524 | 34,331 | KEED (Učida & Rajapurohit 2018) 41,524; DEDR 31,317 |
| Malayalam (`Malayalam`) | 8,809 | 1,752 | 8,378 | 989 | 0 | 989 | DEDR 7,565; Lindgren 2023 814 |
| Sanskrit (`Sk`) | 27,321 | 141 | 69 | 21,422 | 26,191 | 275 | Sheth 1923 26,191 |
| Pali (`Pa`) | 7,076 | 1,247 | 7,028 | 48 | 0 | 0 | CDIAL 7,028 |
| Prakrit (`Pk`) | 54,529 | 1,359 | 12,384 | 34,342 | 41,670 | 356 | Sheth 1923 41,670; CDIAL 12,385 |
| Apabhramsha (`Ap`) | 632 | 80 | 181 | 377 | 443 | 0 | Sheth 1923 443; CDIAL 181 |
| Ashokan Prakrit (`As`) | 1,300 | 282 | 1,016 | 85 | 5 | 0 | CDIAL 1,016; Andersen 1990 280 |

Source counts are per-row source citations, so they can overlap when a row cites more than one source. Kannada is an example.

Coverage notes:

- **Sanskrit headwords sit mostly under the `Indo-Aryan` language ID, not `Sk`.** That ID holds 25,154 rows of CDIAL headwords, 9,107 of them starred (reconstructed). `Sk` mostly holds Sheth's Sanskrit equivalents of Prakrit words, which are rarely etymon-linked. The importer must map `Indo-Aryan` headwords to the Sanskrit/OIA reference layer and keep the asterisked rows `reconstructed`.
- **Hindi and Urdu are merged** (`H`, glottocode `hind1269`). Splitting them is not possible from this data.
- **Marathi and Kannada counts are inflated by dialect surveys** (SDML, KEED and others) that are mostly unlinked. Linked coverage is about 7–12k for each modern language.
- **Coverage after licence filtering is not yet known.** Once CDIAL and DEDR are excluded, almost all etymon links for the 11 target languages disappear. This is the main release risk.

## 4. Field mapping to our schema

| Our table.field | Jambu source | Notes |
|---|---|---|
| `language.id` / `name` | `languages.csv` `ID`, `Name` | Keep Jambu IDs as external aliases. Use our own stable IDs. |
| `language.glottocode` | `languages.csv` `Glottocode` | **Not unique.** Prakrit varieties share `maha1305`, and `Sk`/`BHSk` share `sans1269`. See §5. |
| `language.family_id` | `Clade` | Jambu clades (e.g. "Eastern", "S. Dravidian I") are subgroup labels. Take family structure from Glottolog. |
| `variety` | `dialects.csv` | Has `Source_Language_ID` and coordinates. Location and quality are present only for some rows. |
| `lexeme.form` | `Form` (romanised) | Raw source representation. |
| `lexeme.transliteration` | `Form` | Scheme is source-specific (Turner, DEDR, KEED). Record the scheme per source. |
| `lexeme.native` (new) | `Native` | Sparse. See finding 4. |
| `lexeme.ipa` | `Phonemic` | Source transcription. Do not treat it as IPA without per-source review. |
| `lexeme.gloss` | `Gloss` | Mostly filled for modern languages, sparse for `Sk`. |
| `lexeme.reconstruction_status` | `*` prefix + proto-language IDs (`PDr`, starred `Indo-Aryan`) | Derive the status explicitly. Never infer `attested` from a missing asterisk alone. |
| `lexeme.source_id` / `source_record_id` | `Source` (e.g. `CDIAL`, `dedr`) / `ID` + `form-id-aliases.csv` | `form-source-keys.csv` gives legacy row keys. |
| `concept`, `lexeme_concept` | `concepts.csv` (`ID`, `Name`, `Category`), `form_concepts.csv` | 3,321 concepts. |
| `relationship` (word-to-etymon) | `Cognateset` + `edges.csv` | `reflex` → `inherited_form`; `derived` → `derived_form`; `borrowed` → `borrowed_from`. `variant` and `component` have no type yet. See §5. |
| `relationship` (comparisons) | `comparisons.csv` | `related`/`loan`/`influence` with `Direction` and `Confidence`. |
| `evidence.citation` / `locator` | `edges.csv` `Source` (e.g. `key[p. 179]`) | Split the key from the bracketed locator. |
| `source` | `references.csv`, `sources.bib` | Has short citation, editor, OCR and provenance columns. No licence column, so licences are added from our manifest. |
| *(excluded)* | `Etymology`, `entry-texts.csv` | Verbatim entry text. Do not import into a public build. |

## 5. Recommended schema adjustments

1. **Drop the `UNIQUE` constraint on `language.glottocode`.** Several historical varieties legitimately share a glottocode. Use a plain index instead, and add a `language_alias(language_id, scheme, value)` table for Jambu, ISO and Glottolog IDs.
2. **Add `lexeme.native_form` and `lexeme.native_form_origin`** (`source` | `derived_transliteration`), separate from the romanised `form`. Generated native-script forms are search aids, not attested spellings.
3. **Add `transliteration_scheme` per source**, not per lexeme. Every Jambu row uses its source's scheme.
4. **Extend the relationship vocabulary** with `variant_of` and `component_of`. Both are documented in source data and common in CDIAL and DEDR.
5. **Add `relationship.source_confidence`** (`high` | `medium` | `low` | null) for source-asserted confidence. Keep it separate from `score`, which is reserved for algorithmic candidates.
6. **Use the direction values `entry_from_compared`, `compared_from_entry` and `undetermined`.** These are what `comparisons.csv` provides. They map to our `directed` and `unknown` values plus the source and target order.
7. **Add a `release_filter`** derived from `source.reuse_status`. The seed builder should drop every lexeme, relationship and evidence row whose source is not `approved` or `attribution_required`.

## 6. Licence status (summary)

Details and the per-source rows are in [`source_manifest.csv`](../data/manifests/source_manifest.csv).

| Source | Role for MVP | Status |
|---|---|---|
| Jambu aggregate | Container | `unknown`: no repository licence |
| CDIAL (Turner) | IA etymologies, most IA links | `permission_required` |
| DEDR (Burrow & Emeneau) | Dravidian etymologies | `permission_required` |
| DBIA (Emeneau & Burrow 1962) | Dravidian↔IA borrowings | `permission_required` |
| Sheth 1923 *Pāia-sadda-mahaṇṇavo* | Prakrit/Sanskrit forms | `unknown`: print edition probably public domain by age; DSAL digitisation terms not verified |
| KEED (Učida & Rajapurohit 2018) | Kannada | `permission_required` |
| SDML 2026 (Deccan College) | Marathi dialects | `unknown` |
| ORGI census LSI volumes | Modern forms | `unknown` |
| Grierson LSI 1928 (Lexibank CLDF) | Modern comparative vocabulary | `attribution_required` (CC-BY-4.0 per Jambu README) |
| Merriam & Fuls *Dravidian Database* v1.0 | Proto-Dravidian reconstructions | `attribution_required` (CC-BY-4.0 per Jambu README) |
| DravLex (Kolipakam et al. 2018), Lindgren 2023 | Dravidian wordlists | `unknown` until checked upstream |
| Zoller 2023 (Harrassowitz) | IA dialect data | `permission_required` |
| Glottolog | Language identity, classification | `attribution_required` (verify current release) |

## 7. Implications for the roadmap

- **Development data:** build and test importers against the local, git-ignored Jambu snapshot. This is internal research use, not redistribution.
- **Public seed:** until CDIAL/DEDR permission is resolved, the public demo can only ship source-backed links from `attribution_required` sources. Those sources give very few etymon links for the target languages. Options, in order of preference:
  1. Ask the Jambu maintainers and DSAL/the rights holders about reuse terms.
  2. Ship a tiny, hand-checked demo slice under a documented permission.
  3. Ship links and locators to the source entries instead of bundling their content.
- **Transliteration:** native-script input needs a per-language converter from source romanisation to native script, plus AI4Bharat/IndicXlit for user romanisations. Both need their own licence checks.

## 8. Open questions (need human or legal decision)

1. Will the Jambu maintainers confirm terms for the compiled CLDF, and do they hold any CDIAL/DEDR permission that extends to downstream users?
2. What are DSAL's current reuse terms for CDIAL, DEDR and Sheth? This must be checked from a network that can reach `dsal.uchicago.edu`.
3. Is a public demo that shows CDIAL/DEDR-derived links (not entry text) with citations acceptable, or must it be link-only?
4. Do we accept Hindi-Urdu as one language for MVP?
5. How many hand-verified records should the "approved small sample" (Dataset plan §10) have before bulk import?

## 9. Checklist progress (Dataset plan §10)

- [x] Inspect Jambu repository schema and version.
- [x] Write a per-language coverage report (unfiltered, §3).
- [ ] Identify the upstream source and licence for every field and record class. Started: major sources are in the manifest; long-tail sources (about 2,600 references) are not yet classified.
- [ ] Inspect Glottolog's current release and attribution terms.
- [ ] Evaluate the transliteration model and data licences separately.
- [ ] Decide which DSAL and Bharatavani materials can be cited, queried or reused.
- [ ] Build an approved small sample before bulk import.
- [ ] Add the dataset version and provenance to every imported release.
- [ ] Publish an accurate Data Sources and Limitations page.
