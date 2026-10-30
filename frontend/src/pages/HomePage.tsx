import { useEffect, useState } from 'react'
import { getLanguages } from '../api/client.ts'
import { href } from '../app/router.ts'
import { EDGE_STYLES } from '../components/edgeStyles.ts'
import type { Language } from '../types/api.ts'

const SHOWCASE = [
  { q: 'पानी', note: 'Hindi “water” typed in Devanagari, matched to scholarly spellings in other sources' },
  { q: 'paani', note: 'An everyday romanisation, resolved through native-script spellings' },
  { q: 'angara', lang: 'hin', note: 'Hindi अंगारा “ember” and what Wikidata says it comes from' },
  { q: 'bidyut', note: 'Bengali বিদ্যুৎ “electricity”, borrowed from Sanskrit विद्युत्' },
  { q: 'ਪਾਣੀ', lang: 'pan', note: 'Punjabi “water”: its Prakrit source and the compounds built on it' },
  { q: 'ಹಲ್ಲು', note: 'Kannada “tooth”, found from the Kannada script' },
]

const PRINCIPLES = [
  ['Evidence first', 'Every link in the graph points to the record that states it: a dictionary page, a dataset row or a Wikidata statement.'],
  ['Resemblance is not ancestry', 'Words that look or sound alike are listed as candidates and never drawn as relationships.'],
  ['Uncertainty stays visible', 'Reconstructed forms are marked, and a link whose source does not say whether a word was inherited or borrowed is shown exactly that way.'],
  ['Every source cited', 'Scholarly dictionaries without an open licence are used for research and cited on every record; the downloadable open dataset contains only openly licensed sources.'],
]

export default function HomePage() {
  const [languages, setLanguages] = useState<Language[]>([])
  useEffect(() => {
    getLanguages().then(setLanguages).catch(() => setLanguages([]))
  }, [])
  const modern = languages.filter((l) => l.role === 'modern')
  const words = languages.reduce((n, l) => n + l.lexeme_count, 0)
  const families = new Set(modern.map((l) => l.group))

  return (
    <main>
      <section className="border-b border-slate-200 bg-gradient-to-b from-amber-50 to-white">
        <div className="mx-auto max-w-5xl px-4 py-14 sm:py-20">
          <p className="text-sm font-medium tracking-wide text-amber-800 uppercase">Language Similarity Graph</p>
          <h1 className="mt-3 text-4xl leading-tight font-semibold tracking-tight sm:text-5xl">
            How are the words of India&apos;s languages related?
          </h1>
          <p className="mt-5 max-w-2xl text-lg text-slate-700">
            Search a word in its own script or in romanisation, then follow the documented links
            between languages: what a word was inherited from, borrowed from, or built from, with
            the source for every claim.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <a href={href('/explore')} className="rounded-md bg-blue-700 px-5 py-2.5 font-medium text-white hover:bg-blue-800">
              Start exploring
            </a>
            <a href={href('/methodology')} className="rounded-md border border-slate-300 px-5 py-2.5 font-medium hover:bg-slate-50">
              How it works
            </a>
          </div>
          {languages.length > 0 && (
            <dl className="mt-10 grid max-w-xl grid-cols-3 gap-4 text-center">
              {[
                [modern.length, 'modern languages'],
                [families.size, 'language families'],
                [words.toLocaleString(), 'words indexed'],
              ].map(([value, label]) => (
                <div key={label} className="rounded-lg border border-slate-200 bg-white px-2 py-3">
                  <dt className="text-xs text-slate-500">{label}</dt>
                  <dd className="text-2xl font-semibold">{value}</dd>
                </div>
              ))}
            </dl>
          )}
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-12">
        <h2 className="text-2xl font-semibold">Try a search</h2>
        <ul className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {SHOWCASE.map((s) => (
            <li key={s.q}>
              <a
                href={href('/explore', { q: s.q, lang: s.lang })}
                className="block h-full rounded-lg border border-slate-200 p-4 hover:border-blue-400 hover:shadow-sm"
              >
                <span className="text-xl font-medium">{s.q}</span>
                <span className="mt-1 block text-sm text-slate-600">{s.note}</span>
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto grid max-w-5xl gap-8 px-4 py-12 md:grid-cols-2">
          <div>
            <h2 className="text-2xl font-semibold">What the links mean</h2>
            <ul className="mt-4 space-y-2 text-sm">
              {(['inherited_form', 'borrowed_from', 'etymon', 'derived_form', 'has_component', 'cognate'] as const).map((t) => (
                <li key={t} className="flex items-center gap-3">
                  <svg width="32" height="8" aria-hidden="true">
                    <line x1="0" y1="4" x2="32" y2="4" stroke={EDGE_STYLES[t].color} strokeWidth="3" />
                  </svg>
                  <span>
                    <strong>{EDGE_STYLES[t].short}</strong> — {LINK_TEXT[t]}
                  </span>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h2 className="text-2xl font-semibold">Principles</h2>
            <dl className="mt-4 space-y-3 text-sm">
              {PRINCIPLES.map(([title, text]) => (
                <div key={title}>
                  <dt className="font-semibold">{title}</dt>
                  <dd className="text-slate-700">{text}</dd>
                </div>
              ))}
            </dl>
          </div>
        </div>
      </section>
    </main>
  )
}

const LINK_TEXT: Record<string, string> = {
  inherited_form: 'passed down from an older stage of the language',
  borrowed_from: 'taken over from another language',
  etymon: 'comes from this word; the source does not say whether by inheritance or borrowing',
  derived_form: 'formed from another word, for example with a suffix',
  has_component: 'a compound or phrase that contains this word',
  cognate: 'shares an ancestor with this word, as judged by a cognate database or dictionary',
}
