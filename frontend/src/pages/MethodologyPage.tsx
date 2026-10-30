import { useEffect, useState } from 'react'
import { getCitations, getLanguages } from '../api/client.ts'
import type { CitationsResponse, Language } from '../types/api.ts'

const SOURCES = [
  {
    name: 'Glottolog 5.3',
    licence: 'CC BY 4.0',
    use: 'Language identity and family classification',
    credit: 'Hammarström, Forkel, Haspelmath & Bank (2026), MPI for Evolutionary Anthropology',
    url: 'https://glottolog.org',
  },
  {
    name: 'Linguistic Survey of India, Comparative Vocabulary (1928)',
    licence: 'CC BY 4.0 (Lexibank CLDF edition)',
    use: 'Comparative wordlists of 168 concepts',
    credit: 'Grierson (1928); Lexibank lsi v1.1',
    url: 'https://github.com/lexibank/lsi',
  },
  {
    name: 'ASJP Database v21',
    licence: 'CC BY 4.0',
    use: '40-concept wordlists in a phonetic notation (ASJPcode)',
    credit: 'Wichmann, Holman, Brown, Dryer & Ran (eds.) 2025',
    url: 'https://asjp.clld.org',
  },
  {
    name: 'Concepticon 3.4.0',
    licence: 'CC BY 4.0',
    use: 'Shared meaning identifiers across all wordlists',
    credit: 'List, Tjuka, Blum et al.',
    url: 'https://concepticon.clld.org',
  },
  {
    name: 'Wikidata Lexemes (dump 2026-10-28)',
    licence: 'CC0',
    use: 'Words, English glosses, and “derived from” and “combines” statements with their references',
    credit: 'Wikidata contributors',
    url: 'https://www.wikidata.org/wiki/Wikidata:Lexicographical_data',
  },
  {
    name: 'Dakshina v1.0',
    licence: 'CC BY-SA 4.0',
    use: 'Native-script and romanised spellings, used only to find words',
    credit: 'Roark et al. (2020), Google Research',
    url: 'https://github.com/google-research-datasets/dakshina',
  },
  {
    name: 'Aksharantar (selected parts)',
    licence: 'CC BY (manual pairs) / CC0 (pairs from Wikidata)',
    use: 'More native-script and romanised spellings; mined web pairs are excluded',
    credit: 'Madhani et al. (2022), AI4Bharat',
    url: 'https://huggingface.co/datasets/ai4bharat/Aksharantar',
  },
  {
    name: 'Wiktionary (via wiktextract)',
    licence: 'CC BY-SA 4.0 / GFDL',
    use: 'Words, glosses and typed etymologies: inherited, borrowed, calques, compounds, cognates',
    credit: 'Wiktionary contributors; Ylonen (2022), LREC; kaikki.org',
    url: 'https://kaikki.org/dictionary/',
  },
  {
    name: 'IE-CoR, IELex, DravLex',
    licence: 'CC BY 4.0',
    use: 'Expert cognate judgments for Indo-European and Dravidian languages',
    credit: 'Heggarty, Anderson & Scarborough (2024); Dunn (2012); Kolipakam, Dunn, Jordan & Verkerk (2018)',
    url: 'https://github.com/lexibank/iecor',
  },
  {
    name: 'NorthEuraLex; Hale’s Nepal wordlists',
    licence: 'CC BY 4.0',
    use: 'Concept-aligned wordlists',
    credit: 'Dellert et al. (2020); Hale (1973), Lexibank editions',
    url: 'https://github.com/lexibank/northeuralex',
  },
  {
    name: 'Digital Corpus of Sanskrit (lexicon)',
    licence: 'CC BY 4.0',
    use: 'Sanskrit words with English meanings',
    credit: 'Hellwig (2010–2021)',
    url: 'https://github.com/OliverHellwig/sanskrit',
  },
]

// Unlicensed or in-copyright sources, used for academic research with a citation on every
// record. They are shown in this app but never included in the downloadable open dataset.
const RESEARCH_SOURCES = [
  {
    name: 'Jambu',
    use: 'Etymological database of South Asian languages; the route by which the works below enter',
    credit: 'Arora, Farris, Basu & Kolichala (2023), SIGMORPHON 2023, doi:10.18653/v1/2023.sigmorphon-1.8',
    url: 'https://github.com/moli-mandala/data',
  },
  {
    name: 'A Comparative Dictionary of the Indo-Aryan Languages (CDIAL)',
    use: 'Indo-Aryan word histories: inherited forms, borrowings, derivations',
    credit: 'Turner (1962–1966), Oxford University Press',
    url: 'https://dsal.uchicago.edu/dictionaries/soas/',
  },
  {
    name: 'A Dravidian Etymological Dictionary (DEDR)',
    use: 'Dravidian cognate sets',
    credit: 'Burrow & Emeneau (1984, 2nd edn), Clarendon Press',
    url: 'https://dsal.uchicago.edu/dictionaries/burrow/',
  },
  {
    name: 'A Sanskrit-English Dictionary (Monier-Williams)',
    use: 'Sanskrit headwords, senses and compound structure, with page and column',
    credit: 'Monier-Williams (1899); Cologne Digital Sanskrit Dictionaries (CC BY-NC-SA)',
    url: 'https://www.sanskrit-lexicon.uni-koeln.de',
  },
  {
    name: 'Digital Pāḷi Dictionary',
    use: 'Pali words, Sanskrit equivalents, derivations and compounds',
    credit: 'Bodhirasa Bhikkhu, v0.4.20261026 (CC BY-NC-SA), doi:10.5281/zenodo.22979413',
    url: 'https://www.dpdict.net/',
  },
  {
    name: 'Comparative Sino-Tibetan Wordlists',
    use: 'Bodo words and cognate sets',
    credit: 'Peiros (2004), Lexibank edition (CC BY-NC)',
    url: 'https://github.com/lexibank/peirosst',
  },
  {
    name: 'StarLing: The Tower of Babel',
    use: 'Etymological databases: Indo-European (after Walde–Pokorny, with Pokorny’s page references), Vasmer’s Russian dictionary, Germanic, Baltic, Altaic (Turkic, Mongolic, Tungusic, Korean, Japanese; a contested family), Dravidian, North Caucasian, Sino-Tibetan, Chukchee-Kamchatkan, Kartvelian and Yeniseian. Forms, short glosses and page references only',
    credit: 'Sergei A. Starostin, George S. Starostin et al.; each record also cites its own database and compilers',
    url: 'https://starlingdb.org/',
  },
]

const SECTIONS: [string, string[]][] = [
  [
    'How search works',
    [
      'A query is kept exactly as typed and also normalised (Unicode NFC). Whole words are matched first; stems, affixes, roots, phrases and compounds that share the spelling are listed separately, because they are different units.',
      'A query in an Indian script is romanised by rule (ISO 15919, with the older Hunterian spellings as a fallback) and matched only within languages written in that script. Every such match says how it was found.',
      'Everyday romanisations such as “paani” are looked up in the Dakshina and Aksharantar spelling pairs to find the native-script word first.',
      'Similar spellings are offered as candidates with a score. The score measures spelling overlap only; it is not a measure of relatedness.',
    ],
  ],
  [
    'What counts as a relationship',
    [
      'Only links stated by a source are drawn. Each one keeps the source record, the locator (page, entry or statement ID) and the source’s own wording.',
      'Wikidata’s “derived from” statements are shown as “from”, because they do not say whether a word was inherited or borrowed. Statements without a reference are marked as such.',
      'Reconstructed forms (marked *) are hypotheses, not attested words, and are drawn with a dashed outline.',
      'Language families come from Glottolog and are kept apart from word-to-word links: belonging to the same family does not make two words related.',
    ],
  ],
  [
    'Known limitations',
    [
      'Coverage is very uneven (see the table below). Malayalam and Bengali have many Wikidata entries; several languages have only a 40–200-word comparative wordlist.',
      'The richest scholarly sources on Indo-Aryan and Dravidian word history, Turner’s Comparative Dictionary and Burrow & Emeneau’s Dravidian Etymological Dictionary, are still in copyright. This research app uses them, through Jambu, with a citation on every record; they are not part of the downloadable open dataset. Tick “Open data only” in Explore to see what remains without them.',
      'Wikidata is edited by volunteers. Its claims are shown with their references, but some are doubtful and none has been reviewed for this project.',
      'Spelling-based matching ignores vowel length, so a romanised query can surface unrelated words with similar consonants. These are labelled as transliteration matches and never presented as relationships.',
    ],
  ],
]

export default function MethodologyPage() {
  const [languages, setLanguages] = useState<Language[]>([])
  const [citations, setCitations] = useState<CitationsResponse | null>(null)
  const [allWorks, setAllWorks] = useState(false)
  useEffect(() => {
    getLanguages().then(setLanguages).catch(() => setLanguages([]))
    getCitations().then(setCitations).catch(() => setCitations(null))
  }, [])
  const rows = [...languages].sort((a, b) => b.lexeme_count - a.lexeme_count)

  return (
    <main className="mx-auto max-w-4xl px-4 py-10">
      <h1 className="text-3xl font-semibold tracking-tight">Data &amp; methodology</h1>
      <p className="mt-3 text-slate-700">
        This page explains where the data comes from, what the app does with it, and where it falls
        short. The full licence audit and the data pipeline are documented in the{' '}
        <a className="text-blue-700 underline" href="https://github.com/Vaidurya-s/Linguistic-DNA/blob/main/docs/DATASET_LICENCE_AUDIT.md">
          project repository
        </a>
        .
      </p>

      {SECTIONS.map(([title, items]) => (
        <section key={title} className="mt-8">
          <h2 className="text-xl font-semibold">{title}</h2>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-slate-700">
            {items.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ))}

      <section className="mt-10">
        <h2 className="text-xl font-semibold">Sources and licences</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <thead className="text-slate-500">
              <tr><th className="py-2 pr-3">Source</th><th className="pr-3">Licence</th><th>Used for</th></tr>
            </thead>
            <tbody>
              {SOURCES.map((s) => (
                <tr key={s.name} className="border-t border-slate-200 align-top">
                  <td className="py-2 pr-3">
                    <a className="text-blue-700 underline" href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                    <div className="text-xs text-slate-500">{s.credit}</div>
                  </td>
                  <td className="pr-3">{s.licence}</td>
                  <td>{s.use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-slate-500">
          Spelling pairs adapted from Dakshina are shared under CC BY-SA 4.0, as its licence requires.
        </p>
        <h3 className="mt-6 font-semibold">Used for research only</h3>
        <p className="mt-1 text-sm text-slate-600">
          These sources have no open licence, or only a non-commercial one. They are used here for
          academic research, cited on every record, and never redistributed.
        </p>
        <div className="mt-2 overflow-x-auto">
          <table className="w-full min-w-[36rem] text-left text-sm">
            <tbody>
              {RESEARCH_SOURCES.map((s) => (
                <tr key={s.name} className="border-t border-slate-200 align-top">
                  <td className="py-2 pr-3">
                    <a className="text-blue-700 underline" href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                    <div className="text-xs text-slate-500">{s.credit}</div>
                  </td>
                  <td>{s.use}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">How to cite</h2>
        <p className="mt-1 text-sm text-slate-600">
          When you use a word or a link from this app, cite the work named on that record, and the
          dataset it was taken from. Every dataset in use, with the citation it asks for:
        </p>
        {citations ? (
          <>
            <ul className="mt-3 space-y-3 text-sm">
              {citations.datasets.map((d) => (
                <li key={d.id} className="rounded-md border border-slate-200 p-3">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <strong>{d.name}</strong>
                    <span className={`rounded px-1.5 py-0.5 text-xs ${d.decision === 'RESEARCH USE' ? 'bg-amber-100 text-amber-900' : 'bg-emerald-50 text-emerald-800'}`}>
                      {d.decision === 'RESEARCH USE' ? 'research use' : 'open licence'}
                    </span>
                  </div>
                  {d.citation && <p className="mt-1 text-slate-700">{d.citation}</p>}
                  <p className="mt-1 text-xs text-slate-500">
                    {d.lexeme_count.toLocaleString()} words, {d.relationship_count.toLocaleString()} links
                  </p>
                </li>
              ))}
            </ul>
            <h3 className="mt-6 font-semibold">
              Works cited by individual records ({citations.works.length.toLocaleString()})
            </h3>
            <ol className="mt-2 list-decimal space-y-1 pl-6 text-sm text-slate-700">
              {(allWorks ? citations.works : citations.works.slice(0, 15)).map((w) => (
                <li key={w.id}>
                  {w.url ? <a className="text-blue-700 underline" href={w.url} target="_blank" rel="noreferrer">{w.title}</a> : w.title}
                  <span className="text-xs text-slate-500"> — {w.record_count.toLocaleString()} records</span>
                </li>
              ))}
            </ol>
            {citations.works.length > 15 && (
              <button type="button" className="mt-2 text-sm text-blue-700 underline" onClick={() => setAllWorks((v) => !v)}>
                {allWorks ? 'Show fewer' : `Show all ${citations.works.length.toLocaleString()}`}
              </button>
            )}
          </>
        ) : (
          <p className="mt-2 text-sm text-slate-500">The citation list needs the API to be running.</p>
        )}
      </section>

      <section className="mt-10">
        <h2 className="text-xl font-semibold">Coverage by language</h2>
        <p className="mt-1 text-sm text-slate-600">
          Words indexed, and how many of them have at least one documented link.
        </p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full min-w-[30rem] text-left text-sm">
            <thead className="text-slate-500">
              <tr><th className="py-2">Language</th><th>Family</th><th className="text-right">Words</th><th className="text-right">With links</th></tr>
            </thead>
            <tbody>
              {rows.map((l) => (
                <tr key={l.id} className="border-t border-slate-200">
                  <td className="py-1.5">{l.name}</td>
                  <td className="text-slate-600">{l.role === 'modern' ? l.group : 'historical / reference'}</td>
                  <td className="text-right tabular-nums">{l.lexeme_count.toLocaleString()}</td>
                  <td className="text-right tabular-nums">{l.linked_count.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {rows.length === 0 && <p className="mt-2 text-sm text-slate-500">Coverage figures need the API to be running.</p>}
        </div>
      </section>
    </main>
  )
}
