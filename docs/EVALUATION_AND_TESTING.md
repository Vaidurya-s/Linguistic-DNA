# Evaluation and Testing Plan — Language Similarity Graph

## 1. Purpose

The demo should be evaluated for both software quality and linguistic reliability. A graph can look persuasive while showing false relationships; evaluation must therefore measure relationship type, source traceability, and candidate quality separately.

## 2. Evaluation dataset

Create a manually reviewed benchmark using records that can legally be retained in the project's test suite. Each case should record:

- query form;
- language/script, where known;
- expected direct lookup result;
- candidate forms;
- expected relation type or label;
- evidence/source reference;
- ambiguity or uncertainty notes;
- split: development or held-out test.

Avoid making the benchmark entirely from the same automatic rules used by the algorithm. Human review and external source checks are needed to reduce circular evaluation.

## 3. Required case categories

1. Exact lexical matches.
2. Known aliases/transliterations of the same lexical form.
3. Documented cognates or inherited forms.
4. Documented borrowings, including direction where available.
5. Similar spelling but unrelated history.
6. Phonetically similar forms with no known historical relation.
7. Words that share a meaning but have unrelated origins.
8. Ambiguous forms shared by multiple languages.
9. Reconstructed forms.
10. Unknown words and queries absent from the indexed release.
11. Disputed or conflicting etymological accounts.
12. Forms with missing pronunciation or gloss data.

## 4. Metrics

### Lookup and language resolution

- exact-match success rate;
- alias/transliteration lookup accuracy;
- language identification accuracy where the benchmark has a clear label;
- ambiguity detection rate for genuinely ambiguous queries.

### Candidate retrieval

- Precision@5 and Precision@10;
- Recall@5 where all relevant target candidates are known;
- false-positive rate on hard negative pairs;
- mean reciprocal rank where a relevant candidate is expected.

Compute these metrics separately for orthographic and phonetic candidate retrieval. Do not combine them into a metric that hides which subsystem failed.

### Historical evidence and graph integrity

- percentage of documented historical edges with a source locator;
- percentage of reconstructed forms correctly marked;
- percentage of edges whose type matches the reviewed reference label;
- percentage of directed borrowing relationships with direction supported by a source;
- dangling-node and dangling-edge counts;
- rate of accidental merging of homonyms or separate senses.

### User experience and performance

- p50 and p95 API latency;
- graph render time for the default node limit;
- rate of queries that produce an understandable result state;
- task completion in a small qualitative usability test;
- whether users can correctly distinguish documented relations from candidates after using the UI.

## 5. Suggested initial targets

These are targets to be validated, not claims about existing performance.

| Metric | Initial target |
|---|---|
| Indexed exact lookup | >= 95% success for benchmark terms known to exist in the release dataset |
| Source-backed historical edges | 100% have a source/source-record reference |
| Candidate labelling | 100% of generated-only relations labelled `candidate` |
| Reconstruction labels | 100% of known reconstructed nodes correctly flagged |
| Hard negatives | Report and reduce false-positive rate; choose a threshold only after measuring the baseline |
| API latency | p95 < 1 second for common indexed queries on the target deployment |
| Reproducibility | Full import/validation process succeeds from versioned inputs and configuration |

Do not set an arbitrary top-k precision target before inspecting dataset quality and benchmark difficulty. Establish a baseline first, then set a defensible improvement goal.

## 6. Test layers

### Unit tests

- Unicode normalization;
- alias and transliteration matching;
- similarity normalization and score boundaries;
- candidate labels and explanation generation;
- relationship-type mapping;
- graph depth and node limits;
- reconstruction/status display logic.

### Data-validation tests

- each relationship references existing lexemes;
- each lexeme references a valid language;
- each documented edge has provenance;
- each candidate has a method;
- source licence state is valid;
- IDs remain stable across a repeat import;
- no unpermitted source is included in public seed output.

### API integration tests

- exact query returns expected records;
- ambiguous word returns language choices;
- unknown query returns a useful empty state;
- graph response contains source metadata for documented edges;
- graph filters exclude the requested relationship types;
- invalid graph depth and excessive limits are rejected or capped;
- restricted data is not exposed.

### Frontend/end-to-end tests

- search in each supported script;
- resolve language ambiguity;
- expand and collapse graph nodes;
- filter by relation type;
- select an edge and open its evidence panel;
- keyboard navigation and responsive layout;
- no-results and backend-error states;
- graph legend explains colors and edge patterns.

## 7. Manual linguistic review

For a representative sample of results, review:

- whether the source actually supports the displayed relation;
- whether the app altered the claim's meaning during normalization;
- whether the relationship direction is warranted;
- whether reconstructed forms are labelled correctly;
- whether the graph visually implies a stronger relationship than the evidence supports;
- whether the displayed score is clearly described as a similarity/ranking score, not etymological certainty.

Keep the review findings and corrections in a versioned issue log.

## 8. Usability study

Recruit a small group of people who have not worked on the code. Give them tasks such as:

1. Search for a word in a supported script.
2. Find a documented relation in another language.
3. Explain why the relationship is displayed.
4. Find a similar-sounding candidate and identify its uncertainty label.
5. Distinguish shared meaning from historical ancestry.

Record task completion, time, confusion points, and whether users mistake similarity candidates for facts. Use the result to revise edge styling, wording, and evidence-panel hierarchy.

## 9. Release checklist

- [ ] Unit and integration test suite passes.
- [ ] Data validation report has no unexplained referential integrity errors.
- [ ] Source traceability audit passes.
- [ ] Hard-negative examples tested.
- [ ] Unknown and ambiguous queries tested.
- [ ] p50/p95 latency measured on the deployment target.
- [ ] Licence manifest reviewed for the release dataset.
- [ ] Public data-source and limitations documentation published.
- [ ] Demo examples checked manually against their sources.
- [ ] Known limitations are documented in the README.
