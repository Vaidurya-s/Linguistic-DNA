# Presentation outline: Linguistic DNA (IKO 103)

13 slides, in the order the department asks for. Figures are from the live database and the README as of 2026-11-10. Each slide has the text to put on it, a line to say, and the image to use from `docs/media/`. References are given in full under the slide that mentions them and again on slide 13.

Items marked **[verify]** could not be fully confirmed in this session. Check them before presenting. The entries below follow APA 7. The two Nature and Science entries were also checked against the "Cite this article" and "Cite as" text on the publishers' own pages (authors, volume, article number, DOI all agree); if your department wants the publisher's own wording, copy it from those pages.

---

## Slide 1. Topic, title and group

**Linguistic DNA: an evidence-first graph of how words are related, starting from the languages of India**

- Course: IKO 103, Indian Knowledge Systems
- Professor: Dr. Tharun Kumar Reddy Bollu
- Guide: Pranjali Sathe, PhD
- Group: Vaidurya Shah, Shivansh Tiwari
- Code: github.com/Vaidurya-s/Linguistic-DNA

**Say:** We built a search tool that shows how a word is related to words in other languages, and shows the source for every claim.

**Image:** `home.png`

---

## Slide 2. Motivation and significance

- The richest record of word history for South Asia sits in printed dictionaries: Turner's *Comparative Dictionary of the Indo-Aryan Languages*, Burrow and Emeneau's *Dravidian Etymological Dictionary*, Monier-Williams for Sanskrit. They use dense abbreviations and are hard to search.
- Popular "related words" tools lean on resemblance. Words that look alike are often not related, and historical linguistics warns against treating them as such.
- Languages such as Hindi, Kannada and Punjabi have many scripts and many romanisations. A learner typing "paani" should reach पानी, ਪਾਣੀ and their source in Sanskrit and Prakrit.
- Significance for IKS: the lexical heritage of Sanskrit, Prakrit, Pāli and the Dravidian languages becomes searchable, with each claim traceable to a source.

**Say:** The question is narrow and checkable: given a word in any script, what do cited sources say it is related to, and how do we know?

**Image:** `explore-hindi-paani-chain.png`

> To do: if you want to link to the Indian etymological tradition (for example the *Nirukta*), add a citation of your own choice here. None is included because none was checked.

---

## Slide 3. Prior art, part 1: scholarly resources

- **Printed etymological dictionaries.** Turner (1962–66) for Indo-Aryan, Burrow and Emeneau (1984) for Dravidian, Monier-Williams (1899) for Sanskrit. Searchable scans exist, but each entry is a page of abbreviations, not linked data.
- **Jambu** unifies these sources in one cognate database: about 287k lemmata from 602 lects in 23k cognate sets (Arora et al., 2023). It is the closest scholarly predecessor. It does not separate inheritance, borrowing and uncertainty per link with licence tracking.
- **Standards and shared data.** CLDF (Forkel et al., 2018) and Lexibank (List et al., 2022): word lists for more than 2,000 varieties in one format. Concepticon (List et al., 2016) links concept lists, so words in different datasets share meanings.
- **Cognate databases.** IE-CoR (Heggarty et al., 2023): about 1,600 cognate sets going back to Proto-Indo-European, 160 languages, 170 meanings (as described in the dataset paper, Anderson et al., 2025).
- **Wordnets.** IndoWordNet (Bhattacharyya, 2010): linked wordnets for major Indian languages. They give meanings and relations between meanings, not word history.
- **Pāli.** The Digital Pāḷi Dictionary (Bodhirasa) is a free, regularly updated dictionary under a non-commercial licence.

**References on this slide (full):**

- Turner, R. L. (1962–1966). *A comparative dictionary of the Indo-Aryan languages*. London: Oxford University Press. Digital edition: Digital Dictionaries of South Asia, University of Chicago, https://dsal.uchicago.edu/dictionaries/soas/
- Burrow, T., & Emeneau, M. B. (1984). *A Dravidian etymological dictionary* (2nd ed.). Oxford: Clarendon Press. Digital edition: https://dsal.uchicago.edu/dictionaries/burrow/
- Monier-Williams, M. (1899). *A Sanskrit-English dictionary, etymologically and philologically arranged with special reference to cognate Indo-European languages*. Oxford: Clarendon Press. Digital edition: Cologne Digital Sanskrit Dictionaries, https://www.sanskrit-lexicon.uni-koeln.de/
- Arora, A., Farris, A., Basu, S., & Kolichala, S. (2023). Jambu: A historical linguistic database for South Asian languages. In *Proceedings of the 20th SIGMORPHON Workshop on Computational Research in Phonetics, Phonology, and Morphology* (pp. 68–77). Toronto: Association for Computational Linguistics. https://doi.org/10.18653/v1/2023.sigmorphon-1.8
- Forkel, R., List, J.-M., Greenhill, S. J., Rzymski, C., Bank, S., Cysouw, M., Hammarström, H., Haspelmath, M., Kaiping, G. A., & Gray, R. D. (2018). Cross-Linguistic Data Formats, advancing data sharing and re-use in comparative linguistics. *Scientific Data, 5*, Article 180205. https://doi.org/10.1038/sdata.2018.205
- List, J.-M., Forkel, R., Greenhill, S. J., Rzymski, C., Englisch, J., & Gray, R. D. (2022). Lexibank, a public repository of standardized wordlists with computed phonological and lexical features. *Scientific Data, 9*, 316. https://doi.org/10.1038/s41597-022-01432-0
- List, J.-M., Cysouw, M., & Forkel, R. (2016). Concepticon: A resource for the linking of concept lists. In *Proceedings of LREC 2016* (pp. 2393–2400). Portorož: European Language Resources Association. https://aclanthology.org/L16-1379/
- Heggarty, P., Anderson, C., Scarborough, M., King, B., Bouckaert, R., Jocz, L., et al. (2023). Language trees with sampled ancestors support a hybrid model for the origin of Indo-European languages. *Science, 381*(6656), eabg0818. https://doi.org/10.1126/science.abg0818 (33 authors; shortened here with "et al.")
- Anderson, C., Scarborough, M., Jocz, L., Kümmel, M. J., Jügel, T., et al. (2025). The Indo-European Cognate Relationships dataset. *Scientific Data, 12*, Article 1541. https://doi.org/10.1038/s41597-025-05445-3 (more than 80 authors; the last two are R. D. Gray and P. Heggarty; shortened here with "et al.")
- Bhattacharyya, P. (2010). IndoWordNet. In *Proceedings of LREC 2010*. Valletta: European Language Resources Association. https://aclanthology.org/L10-1635/
- Bodhirasa, B. (2022–present). *Digital Pāḷi Dictionary* [CC BY-NC 4.0]. https://docs.dpdict.net/ **[add the release date you accessed]**

**Say:** The data we need exists, but it is scattered across print dictionaries, separate formats and different licences. Jambu is the nearest prior work; we build on its open data.

---

## Slide 4. Prior art, part 2: computational work and patents

- **Etymology from Wiktionary.** Etymological Wordnet (de Melo, 2014) builds a network of word-origin links from Wiktionary: over 500,000 origin links and over 2 million derivational and compositional links. EtymDB 2.0 (Fourrier & Sagot, 2020) has 1.8 million lexemes and over 700,000 relations in 2,536 languages, and separates inheritance, borrowing and cognacy.
- **Automatic cognate detection and historical-linguistics tools.** LingPy (List & Forkel) is a Python library for sequence comparison and cognate detection. Such methods give candidates, not evidence.
- **Transliteration.** Dakshina (Roark et al., 2020): romanised and native-script text for 12 South Asian languages. Aksharantar (Madhani et al., 2023): 26 million transliteration pairs for 21 Indic languages. They support romanised search.
- **Patents.** Searched on Google Patents and the USPTO full-text pages. Nothing found that combines a cited, typed word-relationship graph with native-script and romanised search:
  - US 6,256,605 B1, *System for and method of summarizing etymological information* (MacMillan; filed 1999-11-08, granted 2001-07-03; expired). Claim 1: a dictionary and thesaurus database holding only the primary language(s) of origin per word, on one line. A summary tool, not a relationship graph with evidence.
  - US 2007/0219777 A1 (granted as US 8,185,376 B2), *Identifying language origin of words* (Chu et al., Microsoft; filed 2006-03-20). Statistical identification of a word's language of origin from letter sequences. **[claims not fully read]**
  - EA 006373 B1, *Word association method and apparatus* (Abir; filed 2003, published 2005-12-29). A cross-language association database of equivalent words. **[claims not read]**
  - Transliteration and cross-script matching: US 2014/0244238 A1, US 9,176,936, US 8,812,300 B2, WO 2012/149500 A3. Titles seen in search results only; legal status not checked.
- **Gap.** No one resource combines (1) typed relationships with a cited record for each, (2) search by native script or romanisation, (3) a licence audit that decides what may be shared.

**References on this slide (full):**

- de Melo, G. (2014). Etymological Wordnet: Tracing the history of words. In *Proceedings of LREC 2014* (pp. 1148–1154). Reykjavik: European Language Resources Association. https://aclanthology.org/L14-1063/
- Fourrier, C., & Sagot, B. (2020). Methodological aspects of developing and managing an etymological lexical resource: Introducing EtymDB-2.0. In *Proceedings of LREC 2020* (pp. 3207–3216). Marseille: European Language Resources Association. https://aclanthology.org/2020.lrec-1.392/
- List, J.-M., & Forkel, R. (2021). *LingPy: A Python library for historical linguistics* (v2.6.8) [Software]. Zenodo. https://doi.org/10.5281/zenodo.5144474
- Roark, B., Wolf-Sonkin, L., Kirov, C., Mielke, S. J., Johny, C., Demirsahin, I., & Hall, K. (2020). Processing South Asian languages written in the Latin script: The Dakshina dataset. In *Proceedings of LREC 2020* (pp. 2413–2423). Marseille: European Language Resources Association. https://aclanthology.org/2020.lrec-1.294/
- Madhani, Y., Parthan, S., Bedekar, P., NC, G., Khapra, R., Kunchukuttan, A., Kumar, P., & Khapra, M. M. (2023). Aksharantar: Open Indic-language transliteration datasets and models for the next billion users. In *Findings of the Association for Computational Linguistics: EMNLP 2023* (pp. 40–57). Singapore: Association for Computational Linguistics. https://aclanthology.org/2023.findings-emnlp.4 (extended version: arXiv:2205.03018)
- MacMillan, A. S. (2001). *System for and method of summarizing etymological information* (US Patent 6,256,605 B1). United States Patent and Trademark Office.
- Chu, M., Chen, Y., Kuo, S.-Z., He, X., Riley, M., Feige, K., & Gong, Y. (2012). *Identifying language origin of words* (US Patent 8,185,376 B2; published as US 2007/0219777 A1). United States Patent and Trademark Office.
- Abir, E. (2005). *Word association method and apparatus* (Eurasian Patent EA 006373 B1). Eurasian Patent Office.

**Say:** Automatic methods and Wiktionary-derived resources are large but do not show where each claim comes from. Our patent search found no overlapping claims, but this is a search of public sources, not a legal freedom-to-operate opinion.

---

## Slide 5. Relevance and potential impact

- **Application:** a research and teaching tool for word history across South Asian and neighbouring languages.
- **End users, for validation:**
  - students and teachers of Sanskrit, Hindi, Kannada, Punjabi and other Indian languages;
  - historical linguists and Indologists, who can check each link against its cited source;
  - lexicographers and Wikimedia editors, who can find gaps and doubtful claims.
- **Impact:** a link from any modern word to its Prakrit and Sanskrit source, or to a Dravidian root, in a few clicks, with the page or entry cited.
- **Validation plan:** a 22-case benchmark of relationships and lookups (all pass, but not yet reviewed by a linguist). Next step: ask the guide or a faculty linguist to review it, and run a short task test with students.
- **Open data:** a downloadable seed of 521,448 words and 221,594 cited relationships with openly licensed sources only.

**Say:** The first users are people who already use dictionaries like CDIAL and DEDR and want them searchable.

**Image:** `explore-kannada-niru-proto-dravidian.png`

---

## Slide 6. Proposed solution and novelty

- **Evidence first.** Every link has its dataset, a citation and, where known, a page or entry locator. The source's own label is kept next to the normalised type.
- **Resemblance is not ancestry.** Similar spellings are listed as candidates with a score that is not a measure of relatedness. They are never drawn as links.
- **Licence audit as data.** `dataset_audit.csv` has 183 rows. Code reads it to decide what enters the public seed. A validator fails the build on anything else.
- **Own romaniser.** A rule-based ISO 15919 romaniser for nine Brahmic scripts (about 300 lines, no external data) handles the language-dependent inherent vowel and the two readings of anusvara.
- **Uncertainty is shown.** Reconstructed forms carry an asterisk. When a source does not say whether a word was inherited or borrowed, the link says "from", not either.
- **One concept space.** Words from different datasets share Concepticon meanings, so they can meet without being treated as related.

**Say:** The novelty is not a new algorithm. It is the combination: typed, cited links; search in any script; and a licence rule enforced by code.

**Image:** the architecture diagram in the project README (render the Mermaid block), or `docs/WRITEUP.md` § Architecture.

---

## Slide 7. Execution 1: data and the licence audit

- 83 pinned inputs in `downloads.json`, each fixed by a git commit or a SHA-256 checksum.
- 183 audit rows: 2 approved, 142 approved with conditions, 17 research use, 22 blocked.
- Open data goes in the public seed. Research-use data (for example Jambu with CDIAL and DEDR, Monier-Williams, the Digital Pāḷi Dictionary) stays in a local research database and is cited on every record. Blocked data is not used.
- No research-use text is stored in the repository or the public seed.

**Say:** Before any dataset is imported, its licence is read and recorded. That is how we can share the open part safely.

**Image:** `research-use-badge.png`

---

## Slide 8. Execution 2: importers and schema

- One importer per source turns records into words, typed relationships and evidence rows. IDs are deterministic, so a re-import keeps them.
- PostgreSQL 16 with `pg_trgm` indexes. Tables: `lexeme`, `relationship`, `evidence`, `concept`, `source`, `dataset_audit`, `transliteration_alias`.
- 16 relationship types defined, 10 in use, for example `inherited_form`, `borrowed_from`, `cognate`, `derived_form`, `has_component`, `etymon`.
- Statuses: documented, disputed, candidate, rejected.
- `refresh-languages` merges each source's languages into one record per Glottolog language. Distinct languages and historical stages (Anglo-Norman, Middle Irish, Ottoman Turkish) stay separate.
- Importers share one cleaning step for stored text, and Wiktionary's unmarked descendant lines are never treated as proof of inheritance.

**Say:** Everything that appears in the graph is a database row with a source behind it.

---

## Slide 9. Execution 3: search and graph

- Query pipeline: detect the script → romanise a native-script query (or look up aliases for a romanised one) → exact matches → separate whole words from stems and affixes → spelling candidates with `pg_trgm`, in their own list → a bounded subgraph of documented links only.
- Front end: React and Cytoscape. A table beside the graph is the accessible view. An *Open data only* switch hides research-use records.
- Example: Hindi पानी → Prakrit पाणीअ → Sanskrit पानीय. Kannada ನೀರು reaches Proto-Dravidian *kaṇ-ṇīr.

**Say:** The search says how each match was found, for example "paani → पानी → pānī".

**Images:** `explore-hindi-paani-chain.png`, `explore-kannada-niru-proto-dravidian.png`

---

## Slide 10. Execution 4: results

| | Open seed | Research database |
|---|---:|---:|
| Words | 521,448 | 14,120,500 |
| Cited relationships | 221,594 | 7,828,053 |
| Evidence rows | 221,594 | 7,891,297 |
| Searchable languages | 25 | 3,748 |
| Transliteration pairs | 947,189 | 947,189 |

- 190 backend tests and 42 front-end tests pass. CI is green on every push.
- All validator checks pass on the open seed in public mode (32 checks run).
- Benchmark: 22 of 22 cases pass (unreviewed).

**Say:** The research database is for local study. Only the open seed can be shared.

**Image:** `coverage-by-language.svg`

---

## Slide 11. Execution 5: conclusion and limitations

- **Conclusion:** the project shows that cited, typed word relationships can be searched in native script and romanisation, with licence rules enforced by code.
- **Limitations:**
  - the richest sources (CDIAL, DEDR, Monier-Williams, StarLing databases) are non-commercial, so the open dataset is thinner;
  - coverage is uneven: Sanskrit has 448k words, Bodo 496;
  - Perso-Arabic, Ol Chiki and Meitei Mayek scripts are not yet searchable by romanisation;
  - Wikipedia-derived claims (Wikidata, Wiktionary) can be doubtful and are shown with their references;
  - the benchmark has not been reviewed by a linguist.

**Image:** `methodology-coverage.png`

---

## Slide 12. Future work and potential submissions

- Add links for thin languages (Sindhi, Kurdish, Classical Armenian and others have words but no relationships yet).
- Linguist review of the benchmark; a user study with students.
- Host the API so the public demo on GitHub Pages can go live.
- Support Perso-Arabic, Ol Chiki and Meitei Mayek scripts.
- **Possible venues (check call dates and fit before listing):** LREC; ACL workshops on computational historical linguistics, for example SIGTYP; *Journal of Open Humanities Data*; *Digital Scholarship in the Humanities*.
- Cite the dataset as an open data release (public seed with `ATTRIBUTION.md`).

---

## Slide 13. References

Paste the full reference lists from slides 3 and 4, in one style (APA, as above), sorted by author. Keep every item flagged **[verify]** until it is checked.

---

## Before you present

1. Resolve each **[verify]** item: the Digital Pāḷi Dictionary release date is the only reference one left. The CLDF, Lexibank, IE-CoR and Aksharantar entries were checked against the DOI registry's own citation data (the publisher pages blocked automated access, so I used `doi.org` content negotiation instead of a browser).
2. Read the patents US 2007/0219777 A1 and EA 006373 B1 claims yourself before saying anything about them. The transliteration patents were seen in search results only.
3. The Aksharantar paper is in *Findings of EMNLP 2023*, not in the main ACL 2023 conference.
4. The audit has 183 rows (142 "approved with conditions"). The earlier figure of 184 and 143 counted one stale duplicate Wiktionary row, which has been removed from `data/manifests/dataset_audit.csv`.
