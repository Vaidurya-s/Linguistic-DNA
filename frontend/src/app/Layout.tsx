import type { ReactNode } from 'react'
import { href } from './router.ts'

const NAV = [
  { path: '/', label: 'Home' },
  { path: '/explore', label: 'Explore' },
  { path: '/methodology', label: 'Data & methodology' },
]

export default function Layout({ path, children }: { path: string; children: ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-white text-slate-900">
      <header className="border-b border-slate-200">
        <nav className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3" aria-label="Main">
          <a href={href('/')} className="mr-auto text-lg font-semibold tracking-tight">
            Linguistic DNA
          </a>
          {NAV.map((item) => (
            <a
              key={item.path}
              href={href(item.path)}
              aria-current={path === item.path ? 'page' : undefined}
              className={`text-sm ${path === item.path ? 'font-semibold text-blue-800' : 'text-slate-600 hover:text-slate-900'}`}
            >
              {item.label}
            </a>
          ))}
          <a
            href="https://github.com/Vaidurya-s/Linguistic-DNA"
            className="text-sm text-slate-600 hover:text-slate-900"
            target="_blank"
            rel="noreferrer"
          >
            Source code
          </a>
        </nav>
      </header>
      <div className="flex-1">{children}</div>
      <footer className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto max-w-7xl px-4 py-5 text-xs leading-relaxed text-slate-600">
          Data: Glottolog, Concepticon, the Linguistic Survey of India and ASJP (CC BY 4.0);
          Wikidata Lexemes (CC0); Dakshina (CC BY-SA 4.0) and Aksharantar (CC BY / CC0) for
          transliteration. Full credits and licences are on the{' '}
          <a className="underline" href={href('/methodology')}>
            Data &amp; methodology
          </a>{' '}
          page. Links come from cited sources; spelling resemblance is never shown as a relationship.
        </div>
      </footer>
    </div>
  )
}
