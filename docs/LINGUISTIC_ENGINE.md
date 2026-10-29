# Linguistic Engine — Language Similarity Graph

## 1. Design objective

The linguistic engine retrieves and explains relations between lexical forms while preventing a common failure mode: treating words that look or sound alike as historically related without evidence.

The MVP should combine a source-backed relationship layer with separate computational candidate-retrieval layers.

## 2. Core distinction: different questions require different relations

| Question | Evidence or method | Safe output label |
|---|---|---|
| Do these forms share a documented historical origin? | Etymological reference / cognate dataset | Documented cognate, inherited form, derived form, etc. |
| Was one form borrowed from another? | Etymological source with direction or borrowing analysis | Borrowed from / source language, where documented |
| Do the written forms resemble one another? | Normalized spelling and string similarity | Orthographic similarity candidate |
| Do the pronunciations resemble one another? | IPA/phonetic representation and phonological distance | Phonetic similarity candidate |
| Do the words mean the same or related things? | Dictionary gloss, concept database, or semantic model | Equivalent concept / semantic relation |
| Does a word occur in an historical text? | Citable corpus passage and edition metadata | Attestation in a specified source |

These outputs must remain distinguishable in the UI and API.

## 3. Query processing pipeline

### Step 1 — Preserve and normalize input

- Store the raw query exactly as entered.
- Apply Unicode normalization (normally NFC) to a separate normalized query.
- Trim surrounding whitespace and reject empty or excessively long inputs.
- Do not remove diacritics or punctuation globally without language-specific justification.
- Normalize whitespace carefully, but preserve meaningful orthographic distinctions.

### Step 2 — Identify script and candidate language

- Detect the Unicode script where possible.
- If a language identifier is provided, use it as a search hint rather than an unquestionable fact.
- If several languages use the script or the spelling is shared, show plausible choices.
- Romanized input may need language inference because many Latin transliterations overlap.
- Never force a low-confidence language guess without showing ambiguity.

### Step 3 — Resolve lexical forms

Search in this order:

1. exact normalized form;
2. exact known transliteration or alias;
3. lemma and known inflected-form mappings, if available;
4. language-filtered fuzzy spelling candidates;
5. phonetic candidates when pronunciation data is available;
6. semantic candidates from definitions/concepts, as a separate section.

### Step 4 — Retrieve documented relations

Load source-backed relationships from the data store. Preserve the source record and original relationship label where possible. Normalize labels into the application's controlled vocabulary without discarding the source's wording.

### Step 5 — Generate computational candidates

Run only the retrieval methods supported by the available data. Record method and score. Do not promote candidates to documented historical edges automatically.

### Step 6 — Build a bounded graph

- Start from the selected lexical node.
- Use depth 1 by default, with optional expansion to depth 2.
- Deduplicate records by stable identifiers, not just spelling.
- Preserve separate homonyms and senses.
- Cap nodes/edges and report when the graph is truncated.
- Distinguish the language-family hierarchy from the word-relationship graph.

### Step 7 — Return explanation and uncertainty

Return separate lists or fields for documented relations, spelling candidates, phonetic candidates, and semantic relations. Include the evidence metadata that the frontend needs to make the status clear.

## 4. Suggested algorithms

### 4.1 Exact and normalized matching

Use indexed lookups over the normalized form, language, aliases, and transliteration. Exact matching should be the most reliable result class.

### 4.2 Orthographic similarity

Baseline methods:

- normalized Levenshtein/edit distance;
- normalized Damerau–Levenshtein distance if transpositions matter;
- character-trigram similarity (e.g., PostgreSQL `pg_trgm`);
- language/script-specific normalization only when linguistically justified.

Do not compare raw Unicode code-point sequences across unrelated scripts and interpret the distance as phonetic similarity. Scripts encode sounds differently and may have different conventions for vowels, consonants, and diacritics.

### 4.3 Phonetic similarity

When IPA or an equivalent pronunciation representation is available:

1. tokenize the transcription into phonemes or segments;
2. compare sequences with edit distance;
3. optionally apply feature-weighted substitution costs for place, manner, voicing, vowel height/backness, length, and other relevant distinctions;
4. normalize scores for sequence length;
5. identify the representation and method in the result metadata.

Missing pronunciation data must result in “not available,” not a score of zero or an invented transcription. Grapheme-to-phoneme models can be considered later and must be evaluated by language.

### 4.4 Semantic similarity

Start with source-provided glosses, concept IDs, and explicit translation relations. Only add multilingual embedding-based candidate search if the MVP requires it and enough reviewed data exists to evaluate the results.

Semantic models may find related concepts, but they do not establish etymology. Similar meanings can be expressed by words from entirely different origins.

### 4.5 Historical and cognate relationships

Prefer structured source records, manually reviewed relations, and trusted etymological references. The algorithm may retrieve and traverse these edges, but it should not independently assert historical ancestry from string/phonetic scores alone.

## 5. Relationship status model

Recommended statuses:

- `documented` — explicit source supports the relationship;
- `disputed` — credible sources disagree or the source marks the analysis uncertain;
- `candidate` — generated by a computational method, not yet accepted as historical fact;
- `rejected` — reviewed and found not to represent the proposed relationship;
- `unknown` — insufficient evidence to decide.

Recommended display rules:

- documented: solid edge with source citation;
- disputed: visually distinct edge plus explicit uncertainty label;
- candidate: dashed edge, algorithm label, and score/method;
- rejected: normally hidden from the main graph, but available in evaluation/debugging tools;
- unknown: show as a state or note rather than inventing a relationship edge.

## 6. Score interpretation

Do not show one aggregate number such as “87% historically related.”

Keep separate, method-specific values such as:

- `orthographic_score`;
- `phonetic_score`;
- `semantic_score`;
- optionally, an internal `retrieval_rank_score`.

A score is a ranking signal, not a probability of shared ancestry unless it has been explicitly calibrated and validated for that interpretation—which is out of scope for the MVP.

Example response fragment (illustrative only):

```json
{
  "candidate_type": "phonetic_similarity_candidate",
  "score": 0.76,
  "method": "weighted_phoneme_edit_distance_v1",
  "status": "candidate",
  "historical_relationship": "unknown",
  "explanation": "The available phonetic representations are similar under the selected metric; this does not establish a common origin."
}
```

## 7. Evidence and provenance requirements

Each documented relation must retain:

- source identifier;
- source record identifier or locator;
- source name and URL where permitted;
- citation or source note;
- original relationship wording when available;
- import version and transformation trace;
- direction and uncertainty where documented.

If sources disagree, preserve both claims and their sources. Do not silently collapse them into a consensus claim. If a source is restricted, store only information permitted by its terms and link to the source when appropriate.

## 8. Illustrative examples and cautions

- Hindi and Bengali are both Indo-Aryan; their shared family membership does not mean every similar-looking pair is a cognate.
- Tamil belongs to the Dravidian family; its many historical contacts with Indo-Aryan languages do not make Tamil an Indo-Aryan language.
- A word in two languages may be a loan even when the languages are not in the same family.
- Two languages can have synonymous words with unrelated histories.
- Similar sound sequences can occur by chance.

The system should show precisely which of these relationships the available evidence supports.

## 9. Performance strategy

- Index normalized forms and language IDs.
- Use database-side limits for candidate searches.
- Cache frequent queries and small graph responses if needed.
- Retrieve a bounded graph rather than materializing a whole language network per request.
- Avoid an external graph database for the MVP unless relational queries become a measured bottleneck.
- Record p50/p95 latency and candidate counts during evaluation.

## 10. Later extensions

- morphology-aware form resolution;
- language-specific grapheme-to-phoneme processing;
- phonological feature models;
- semantically informed candidate ranking;
- calibrated ranking models trained on reviewed positive and negative pairs;
- source-linked historical corpus attestations;
- sentence-level tokenization and contextual disambiguation.
