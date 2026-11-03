# Candidate datasets for thinly covered languages

Status: **a research list.** Every dataset needs an audit row in `data/manifests/dataset_audit.csv` with its licence evidence before any importer is written (see `CLAUDE.md`). Prepared 2026-11-03. **Added the same day:** MonWN, the Sindhi Open Lexicon, the Kurdish lexicons and Calfa's Classical Armenian dictionary (see "Added" below); the rest are still candidates.

## How this list was made

- Six search-only research agents (Haiku) each took a region: Indo-Aryan; Dravidian, Munda and Tibeto-Burman; Iranian, Turkic, Mongolic and Uralic; East and Southeast Asia and the Pacific; Africa, the Middle East and the Americas; and multilingual resources. They read pages only. They did not download data and did not touch starlingdb.org, DSAL, ALEW, SLIEKKAS or the OPUS API.
- Agents had to quote licences and say where they saw them. Several could not fetch Zenodo, GitHub or STEDT pages, so many licences came from search snippets. I re-checked the ones that decide whether a source can be used at all.
- **Verification column:** `P` licence seen on the owner's own page; `2` two independent sources agree; `S` a search snippet or a third-party page only; `C` sources conflict; `U` none stated or not found.
- **Decision column** is a proposal using the audit's categories. Share-alike licences are acceptable (`APPROVED WITH CONDITIONS`, as for Dakshina and Wiktionary). Non-commercial licences and sources with no stated licence can only be `RESEARCH USE`, in the local research database with a citation on every record.

## What the language counts say

Words held today, from the research database (2026-11-03). "Linked" is words with at least one documented relationship.

| Language | Words | Linked | Notes |
|---|---:|---:|---|
| Bodo | 496 | 205 | |
| Apabhramsha | 994 | 727 | |
| Dogri | 1,514 | 618 | |
| Ashokan Prakrit | 2,002 | 1,845 | |
| Bhojpuri | 2,944 | 1,475 | |
| Awadhi | 3,074 | 1,163 | |
| Marwari | 3,700 | 2,001 | |
| Konkani | 4,958 | 2,697 | |
| Maithili | 6,057 | 3,618 | |
| Somali | 1,479 | 750 | |
| Dari | 1,629 | 41 | |
| Southern Pashto | 371 | 0 | |
| Cusco Quechua | 204 | 159 | |
| Khasi | 2,046 | 513 | |
| Central Kurdish (Sorani) | 2,346 | 1,796 | |
| Samoan / Tongan / Fijian | 2,689 / 3,860 / 4,961 | 2,183 / 1,758 / 3,894 | |
| Amharic | 3,142 | 1,467 | |
| Manipuri (Meitei) | 4,890 | 837 | |
| Lao | 5,121 | 4,525 | |
| Kurukh / Santali | 6,595 / 6,708 | 2,518 / 1,650 | |

## The main finding

The gap is **links, not only words**, and most of the openly licensed sources that exist add words and definitions, not etymology. For the thinnest Indo-Aryan languages (Dogri, Bhojpuri, Awadhi, Marwari, Konkani, Maithili, Bodo) and for Pashto, Somali and Quechua, the agents found **no open dataset with etymology or cognacy**. What exists for them is mostly print, paid, or behind sites that forbid crawling. Realistic routes for those languages are:

1. other-language Wiktionary editions (Tier D below), which carry etymology text;
2. the Wikidata and wordnet routes we already use, as they grow;
3. asking maintainers of closed or unlicensed resources for permission (Tier C).

## Tier A: open licence, ready for an audit row

| Dataset | Helps | Adds | Licence | Verif. | Proposed decision | Format and effort |
|---|---|---|---|---|---|---|
| ~~**Sindhi Open Lexicon**~~ | Sindhi | **Added as research use** (see below). The Zenodo metadata field says CC BY 4.0, but the shipped `LICENSE.txt` is custom terms | | | | |
| ~~**Mongolian WordNet, MonWN**~~ | Halh Mongolian | **Added** (see below) | CC BY-SA 4.0 (repository `LICENSE.txt` and README) | P | APPROVED WITH CONDITIONS | |
| **UzWordNet-GoldCore** (Mendeley DOI 10.17632/v7m7v3jdn5.1) | Uzbek | 11,178 records, 6,506 unique words, 2,706 definitions | CC BY 4.0 (stated on the dataset page itself) | P | APPROVED WITH CONDITIONS | **Manual download:** Mendeley lists the files only through its API, which its robots.txt disallows, so the file link must be taken from a browser |
| **Odisha Government tribal-language dictionaries** (21 languages; Creative Commons announcement 2019-11-12) | Santali and other Odisha tribal languages | Bilingual dictionaries; list and sizes not confirmed | CC BY 4.0 (announcement) | S | APPROVED WITH CONDITIONS once the language list is confirmed | Hosted on the Odisha Virtual Academy portal; bulk download and format unknown |
| **TUFS Open Language Resources** (malindo.aa-ken.jp) | Thai, Lao, Khmer, Burmese, Vietnamese, Malay, Indonesian, Tagalog and 16 more | Basic vocabulary and sentences; counts unknown | CC BY 4.0 (snippet; page returned 403) | S | Needs the licence page read | PostgreSQL dump plus audio. Check the licence manually |
| **Cologne Sanskrit dictionaries (CDSL)**, beyond Monier-Williams | Sanskrit | Further dictionaries; Monier-Williams is already held | CC BY-SA 4.0 "unless noted" | P (CDSL downloads page) | APPROVED WITH CONDITIONS | XML (SLP1). We already have `cdsl.py`; extend it per dictionary |
| **Protosemitic Root Derivations** (Zenodo 14160276) | Semitic (Arabic, Hebrew, Amharic) | Root derivation hypotheses; small | CC BY 4.0 | P | APPROVED WITH CONDITIONS | CSV and GEXF. Authors say the results are not conclusive, so mark links accordingly |
| **Ugric vocabulary** (Holopainen, Zenodo 6035880) | Hungarian, Khanty, Mansi | Cognate list; very small | CC BY 4.0 | P | APPROVED WITH CONDITIONS | XLSX, 48 kB |
| **Arca Verborum** (Uppsala, Zenodo 17294682) | Many; 149 CLDF datasets, 58 with expert cognate judgments | Cognacy | not read | U | Check the Zenodo licence field, then likely approved | CLDF. Overlaps our Lexibank sets; list the new ones first |

## Tier B: usable only as research use (non-commercial) or conflicting

| Dataset | Helps | Adds | Licence | Verif. | Note |
|---|---|---|---|---|---|
| ~~**Calfa Classical Armenian lexical databases**~~ | Classical Armenian | **Added as research use** (see below): 42,235 headwords with English definitions. The etymology file is Armenian prose that the maintainers call AI-processed, so it was not read | CC BY-NC 4.0 (README) | P | RESEARCH USE |
| ~~**KurdishLexicography**~~ | Sorani, Kurmanji, Hawrami, Southern Kurdish | **Added as research use** (see below): 21,674 words | CC BY-NC-SA 4.0 (repository `LICENSE` and README) | P | RESEARCH USE |
| **Sindhi WordNet** (AMBILE, Zenodo 16976593) | Sindhi | A word list with part of speech, gender and synonym columns (about 100,000 rows), no meanings | Zenodo field CC BY 4.0; description CC BY-NC 4.0 | C | RESEARCH USE if added. **Not added:** the first download came back truncated (4.98 of 8.12 MB, checksum mismatch), and it adds little beyond the Sindhi lexicon |
| **IndoWordNet** (CFILT, IIT Bombay) | 18 Indian languages incl. Konkani, Kashmiri, Odia, Nepali, Assamese | Synsets and relations, not etymology | Secondary sites say GNU; the Hugging Face word lists say CC BY-NC-SA 4.0; Global WordNet lists "browse online only" | C | **Read the CFILT licence page before anything else.** Potentially the biggest source for the thin Indo-Aryan languages |
| **African Wordnet / South African wordnets** | Zulu, Xhosa, Setswana, Sepedi, Tshivenda | Wordnets | SADiLaR record CC BY 4.0; Zenodo record 4299515 CC BY-NC-SA 4.0 | C | Two different releases with different licences; use the stricter until the exact release is chosen |
| **PanLex** | Thousands of varieties | Translations, no etymology | Snapshot page and README: CC0 1.0. Licence page: CC BY-NC-SA 4.0 | C | Both are panlex.org pages. Ask PanLex which governs; treat as RESEARCH USE until answered |
| **Ojibwe People's Dictionary** | Ojibwe | Dictionary | CC BY-NC-SA 3.0 | P | Web only, no bulk download; community cultural-protocol terms apply |
| **Mongolic basic-vocabulary database, TUFS** | 12 Mongolic varieties | Comparative vocabulary | CC BY-NC 4.0 | P | Web search only; bulk copying would be scraping. Not usable |

## Tier C: valuable, but no open licence; permission needed

| Dataset | Helps | Why it matters | Problem |
|---|---|---|---|
| **STEDT**, Sino-Tibetan Etymological Dictionary and Thesaurus | Tibetan, Meitei, Mizo, Garo, Newar, Lepcha, Limbu and many more | The best etymological source for Tibeto-Burman | Licence unclear (a 2016 post says "generous license" without naming it). Read the licence in the repository, or ask the maintainers |
| **Bantu Lexical Reconstructions 3** (Africa Museum) | Zulu, Xhosa, Swahili and all Bantu | About 10,000 reconstructions with etymologies | No licence; written permission needed |
| **POLLEX-Online** | 67 Polynesian languages (Samoan, Tongan, Maori, Hawaiian) | 5,724 reconstructions, 77,712 reflexes | No licence, web search only; permission needed |
| **Thesaurus Linguae Aegyptiae** | Egyptian | Lemma lists | Conflicting terms (CC BY-SA 4.0 on newer pages, restrictive on an archived page) |
| **Comprehensive Coptic Lexicon** (11,263 entries) | Coptic | Lexicon | Data licence not stated |
| **Baxter-Sagart Old Chinese** | Old Chinese | About 5,000 reconstructions | No licence on the pages; contact the authors |
| **Uralonet** (UEW digitisation) | Uralic | Etymologies and protoforms | Web only, no licence stated |
| **Mon-Khmer Etymological Database** | Austroasiatic | Etymologies | No download or licence found |
| **FarsNet** | Persian | Wordnet | Registration or faculty-only terms |

## Tier D: Wiktionary-derived resources (the best route to more links)

All of these derive from Wiktionary, so they share its CC BY-SA terms and overlap one another. Pick one extraction route per language, not all of them.

| Resource | Coverage | Licence | Verif. | Note |
|---|---|---|---|---|
| **DBnary** (kaiko.getalp.org; Zenodo 21496349) | 26 Wiktionary editions, bulk Turtle files, updated 2026-06-01 | CC BY-SA 3.0 on its own site; Zenodo reportedly CC BY 4.0 | C | Use the share-alike reading. Translations and senses; etymology coverage not confirmed |
| **kaikki.org other-language editions** | French, German, Russian, Spanish and others, if the page lists them | Wiktionary's CC BY-SA and GFDL (third-party statement only) | S | We already import the English edition this way, so an importer exists. Confirm which editions kaikki.org actually publishes |
| **EtymDB 2.0** (github.com/clefourrier/EtymDB) | 1.8M lexemes, 700k+ etymological relations | CC BY-SA 4.0 and LGPL-3.0, not separated | S | Built from Wiktionary dumps; overlaps what we have |
| **Etymological WordNet** (de Melo) | Wiktionary-mined links | None stated | U | Dated (2013) |

## Added on 2026-11-03

| Dataset | Words | Decision | What it adds | Notes |
|---|---:|---|---|---|
| **MonWN** | 23,393 Halh Mongolian words, 39,423 word-to-concept links | APPROVED WITH CONDITIONS (CC BY-SA 4.0) | Mongolian words linked through the shared interlingual concepts (every one of 39,427 lemma lines mapped) | Halh Mongolian had 10,376 words |
| **Kurdish Lexicographical Resources** | 21,674 (Sorani 5,482; Kurmanji 4,020; Hawrami 1,146; Southern Kurdish 11,026) | RESEARCH USE (CC BY-NC-SA 4.0) | Southern Kurdish grows from 844 words | The files declare exactly these counts; the README's slightly higher figures are headline numbers |
| **Calfa Classical Armenian dictionary** | 42,235 headwords | RESEARCH USE (CC BY-NC 4.0) | Classical Armenian had 8,854 words | Etymology prose not read |
| **Sindhi Open Lexicon** | 103,743 | RESEARCH USE (custom terms; metadata says CC BY 4.0) | Sindhi grows from 11,151 to 114,894 words, with definitions (English where a dictionary gives one) | **Correction to the list above:** it was reported as clear CC BY 4.0, but the shipped `LICENSE.txt` is custom terms ("research, education, AI/NLP development, software development, and non-malicious public-interest use", attribution mandatory), and it is compiled from third-party dictionaries |

None of these adds word-to-word relationships: they state words and meanings only.

## Already held: do not re-add

The agents listed these as new, but they are in `data/manifests/lexibank.tsv` and the database: `leejaponic` (10,963 words), `chenhmongmien` (21,134), `castrosui` (9,459), `sidwellvietic` (3,218), `leeainu` (3,980), `savelyevturkic`, `bowernpny`, `felekesemitic`, `ratcliffearabic`, ABVD, ACD, `walworthpolynesian`, Jambu, DEDR/CDIAL and Monier-Williams. Not yet held: `hsiuhmongmien` (Zenodo 13269392) and the Kitchen et al. Semitic CLDF (Zenodo 17510140).

## Not recommended

- **BabelNet**: non-commercial, research-institution-only terms.
- **Tatoeba, HornMT, TODa**: sentences, not word links.
- **UniMorph**: inflection tables.
- **Universal Dependencies**: per-treebank licences, and no word relationships.
- **CLICS3**: colexification of concepts we already hold through Concepticon.
- **Tajik-Persian parallel lexicon** (Hugging Face, Apache-2.0, gated): 175,130 translation pairs. It would need a translation relation we do not have, and must never be drawn as descent.
- **Web-only community dictionaries** (Cherokee, Inuktut, Navajo Talking Dictionary): no licence, and community protocols apply.

## Suggested order

1. **Read the IndoWordNet licence** at CFILT. If it is usable, it is the broadest help for the thin Indo-Aryan languages.
2. **Sindhi Open Lexicon**, then **MonWN** and **UzWordNet**: clear licences, small importers, immediate word gains.
3. **Calfa Armenian** and **KurdishLexicography** as research use.
4. **Other Wiktionary editions** (DBnary or kaikki) for etymology links across many languages. This needs a decision about which editions to take and a check of the extraction format.
5. **Ask permission** from STEDT, Bantu Lexical Reconstructions and POLLEX, which hold the etymological content the open sources lack.

## Not verified

- Licences marked `S`, `C` or `U` above.
- Entry counts for most Tier A and B items are as the agents reported them.
- Nothing was found for Pashto, Dari, Somali, Quechua, Dogri, Bhojpuri, Awadhi, Marwari, Konkani or Bodo beyond what is listed. That is a finding, and it could also reflect the agents' reach.
