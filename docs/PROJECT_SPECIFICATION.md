# Project Specification — Language Similarity Graph

## 1. Executive summary

Language Similarity Graph is a search-first linguistic exploration platform for discovering how words relate across Indian languages. It displays a local interactive graph of lexical forms and typed relationships, with an evidence panel explaining the source and status of each connection.

The aim is not to assert that all similar words are related. The system separates established historical evidence from algorithmic observations and shared meanings.

## 2. Project goals

### Primary goal

Deliver a polished, publicly demonstrable portfolio application combining:

- multilingual word search;
- interactive relationship graph;
- source-backed historical relationships;
- spelling and pronunciation similarity discovery;
- semantic/translation links;
- transparent evidence and uncertainty display.

### Secondary goals

- demonstrate ingestion and normalization of heterogeneous linguistic data;
- build a reproducible pipeline using structured data formats where possible;
- evaluate candidate retrieval against a manually reviewed benchmark;
- leave a clear technical path for later sentence search and historical text corpus integration.

## 3. Non-goals for the MVP

The first release will **not** attempt to:

- support every language or dialect in India;
- automatically prove etymology with a machine-learning model;
- accept and linguistically parse full sentences;
- claim to find the earliest historical use of a word;
- provide full-text historical corpus search;
- infer geographical history from a word alone;
- reproduce third-party dictionary entries without confirmed reuse permission;
- generate unsupported reconstructed ancestral forms.

## 4. Target users

1. **Language enthusiasts:** want to explore surprising word relationships.
2. **Students:** need an approachable visual explanation of language families and lexical change.
3. **Researchers and technically curious users:** want evidence, sources, IDs, and data provenance.
4. **Portfolio reviewers / recruiters:** need a clear demonstration of frontend, backend, data processing, and evaluation quality.

## 5. Initial coverage

Suggested modern languages:

| Family | Languages |
|---|---|
| Indo-Aryan | Hindi, Bengali, Marathi, Gujarati, Punjabi, Odia, Assamese |
| Dravidian | Tamil, Telugu, Kannada, Malayalam |

Historical/reference forms may include Sanskrit and documented Prakrit forms when reliable, reusable data is available. Do not force all records into a single linear family tree. Indo-Aryan and Dravidian are distinct language families, with extensive historical contact and borrowing between languages.

Language, dialect/variety, script, and lexical form must be modeled separately. A language can have more than one script or spelling convention; a dialect may have distinct pronunciation or vocabulary.

## 6. Product principles

1. **Typed relationships:** every graph edge has a specific relation type.
2. **Evidence first:** documented historical claims link to a source record.
3. **Clear uncertainty:** unknown and disputed origins remain unknown or disputed.
4. **Separate metrics:** orthographic, phonetic, and semantic scores are not collapsed into a single misleading “historical similarity” score.
5. **Preserve raw input:** normalized data must not replace the user's original query.
6. **Respect data licences:** only data with a documented reuse basis may be bundled into the deployed dataset.
7. **Progressive graph disclosure:** show a manageable local graph first; expand on demand.

## 7. Functional requirements

### FR-01 — Word search

- Accept a single word or lexical form.
- Support the native scripts included in the deployed dataset.
- Accept romanized/transliterated forms where aliases or supported transliteration are available.
- Preserve the raw query and store a normalized search representation separately.
- Allow a user to choose a language when language identification is ambiguous.
- Show a clear not-found or ambiguous-result state.

### FR-02 — Language/lexeme identity

- Display the language name, script, lemma or lexical form, gloss, and dialect label where available.
- Distinguish an attested form from a reconstructed form.
- Keep language-family classification distinct from word etymology.

### FR-03 — Historical relationship graph

- Show sourced relationships such as cognate, inherited form, derived form, borrowing, and reconstructed ancestor where available.
- Keep directionality explicit where the evidence supports a direction.
- Do not infer a historical relationship solely from spelling or sound resemblance.
- Allow node selection, edge selection, zooming, panning, expansion, and collapse.

### FR-04 — Surface similarity retrieval

- Retrieve spelling-similar candidates using exact normalized matching and fuzzy string similarity.
- Retrieve phonetic candidates when comparable pronunciation representations are available.
- Explain which method generated the candidate.
- Mark algorithmic results as candidates unless independently supported by a source.

### FR-05 — Semantic relations

- Display definitions, glosses, translations, and shared-concept links when supplied by a source.
- Keep semantic equivalence separate from historical cognacy.
- Do not treat embedding similarity alone as proof of identical sense or common origin.

### FR-06 — Evidence panel

For each selected edge or lexical record, display available fields:

- source and citation;
- source-record identifier or locator;
- relationship type;
- direction, if documented;
- source note or etymological explanation;
- evidence status;
- algorithmic score and method, where applicable;
- data-source licence/attribution metadata where useful.

### FR-07 — Filters

- relationship type;
- language family;
- language / variety;
- evidence status;
- graph depth;
- optionally region if the source documents it.

### FR-08 — Responsive UI and accessibility

- Support desktop and mobile layouts.
- Include a visible graph legend.
- Do not rely on color alone to encode edge types; combine color with labels or line patterns.
- Provide keyboard-accessible controls and readable text alternatives for graph details.

## 8. Suggested acceptance criteria

These are initial engineering targets and must be validated against the actual data slice:

| Area | Target |
|---|---|
| Query latency | p95 below 1 second for indexed/cached word lookup on the agreed deployment tier |
| Direct lookup | At least 95% of exact-match benchmark queries resolved when the term exists in the indexed release dataset |
| Provenance | 100% of documented historical edges carry a source or explicit source-record reference |
| Uncertainty | 100% of algorithm-only candidates labelled as candidates |
| Reconstruction | Reconstructed lexical forms marked as reconstructed and visually distinguishable |
| Reproducibility | Import pipeline can be rerun from versioned input data and configuration |
| UI | Graph controls and evidence panel usable on current desktop and mobile browsers |

The direct-lookup target is conditional on the input being represented in the actual indexed dataset. It does not imply comprehensive coverage of a language.

## 9. Main user journey

1. User enters a word, e.g. in Devanagari, Bengali, Tamil, or a supported romanization.
2. System normalizes the query while retaining the original string.
3. System returns exact matches and any language ambiguity for user resolution.
4. System retrieves documented lexical relationships.
5. System adds separate spelling, phonetic, and semantic candidates.
6. UI displays the central form and a bounded local graph.
7. User filters by relation type or language family and expands a branch.
8. User selects an edge to inspect its source and relationship status.
9. User can open a source link and understand whether the result is a documented claim or a computational suggestion.

## 10. MVP deliverables

- deployed frontend and API;
- versioned database seed/import process;
- one to two-page explanation of the data and source policy;
- architecture diagram;
- manually reviewed evaluation benchmark;
- measured evaluation report;
- demo word list covering different scripts and relationship categories;
- public README explaining limitations and how to run the application.

## 11. Deferred features

### Release 2: historical-text evidence

Add specific, licensed corpora and show dated attestations with edition and passage information. A first-found occurrence in a corpus must not be presented as the origin or necessarily the earliest attestation.

### Release 3: sentence input

Tokenize and resolve inflected forms, then show per-token results. Add context-sensitive meaning only when the system has appropriate lexical/morphological resources.

### Release 4: deeper phonetic and dialect support

Add better phonological distance, audio where legally available, richer dialect data, and calibrated candidate-ranking models.
