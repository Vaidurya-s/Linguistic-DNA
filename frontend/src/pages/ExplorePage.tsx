import { useCallback, useEffect, useMemo, useState } from 'react'
import { getGraph, getLanguages, searchLexemes } from '../api/client.ts'
import DetailsPanel from '../components/DetailsPanel.tsx'
import GraphCanvas, { type DisplayNode, type Selection } from '../components/GraphCanvas.tsx'
import GraphLegend from '../components/GraphLegend.tsx'
import { styleFor } from '../components/edgeStyles.ts'
import type { GraphEdge, GraphNode, Language, SearchMatch, SearchResponse } from '../types/api.ts'

const EXAMPLES = ['dānt', 'mā́lā', 'ಹಗಲು', 'pani']

const MATCH_LABEL: Record<string, string> = {
  exact: 'exact',
  native_exact: 'exact (native script)',
  loose: 'matched ignoring diacritics',
  spelling_candidate: 'similar spelling — candidate only',
}

function MatchButton({ m, onPick }: { m: SearchMatch; onPick: (m: SearchMatch) => void }) {
  return (
    <button
      type="button"
      onClick={() => onPick(m)}
      className="w-full rounded-md border border-slate-200 px-3 py-2 text-left hover:border-slate-400 hover:bg-slate-50"
    >
      <span className="font-medium">
        {m.native_form && m.native_form !== m.form && <>{m.native_form} · </>}
        <span className={m.reconstruction_status === 'reconstructed' ? 'italic' : ''}>{m.form}</span>
      </span>{' '}
      <span className="text-sm text-slate-600">{m.language_name}</span>
      {m.gloss && <span className="text-sm text-slate-600"> — “{m.gloss}”</span>}
      <span className="mt-0.5 block text-xs text-slate-500">
        {MATCH_LABEL[m.match_type]}
        {m.score !== null && ` (score ${m.score.toFixed(2)}, not a relatedness measure)`} ·{' '}
        {m.relationship_count} documented link{m.relationship_count === 1 ? '' : 's'}
        {m.duplicate_count > 1 && ` · ${m.duplicate_count} identical records grouped`}
      </span>
    </button>
  )
}

export default function ExplorePage() {
  const [languages, setLanguages] = useState<Language[]>([])
  const [query, setQuery] = useState('')
  const [languageId, setLanguageId] = useState('')
  const [results, setResults] = useState<SearchResponse | null>(null)
  const [rootId, setRootId] = useState<string | null>(null)
  const [nodes, setNodes] = useState<Map<string, GraphNode>>(new Map())
  const [edges, setEdges] = useState<Map<string, GraphEdge>>(new Map())
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [selection, setSelection] = useState<Selection>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [truncated, setTruncated] = useState(false)
  const [resultsOpen, setResultsOpen] = useState(true)

  useEffect(() => {
    getLanguages().then(setLanguages).catch(() => setLanguages([]))
  }, [])

  const runSearch = useCallback(async (q: string, lang: string) => {
    if (!q.trim()) return
    setBusy('Searching…')
    setError(null)
    try {
      setResults(await searchLexemes(q.trim(), lang || undefined))
      setResultsOpen(true)
    } catch (e) {
      setError(`Search failed: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }, [])

  const expand = useCallback(async (id: string, reset = false) => {
    setBusy('Loading connections…')
    setError(null)
    try {
      const g = await getGraph(id)
      setNodes((prev) => {
        const next = reset ? new Map<string, GraphNode>() : new Map(prev)
        g.nodes.forEach((n) => next.set(n.id, n))
        return next
      })
      setEdges((prev) => {
        const next = reset ? new Map<string, GraphEdge>() : new Map(prev)
        g.edges.forEach((e) => next.set(e.id, e))
        return next
      })
      setExpanded((prev) => new Set(reset ? [id] : [...prev, id]))
      setTruncated((t) => (reset ? g.truncated : t || g.truncated))
    } catch (e) {
      setError(`Could not load the graph: ${(e as Error).message}`)
    } finally {
      setBusy(null)
    }
  }, [])

  const pick = (m: SearchMatch) => {
    setResultsOpen(false)
    setRootId(m.id)
    setSelection({ kind: 'node', id: m.id })
    void expand(m.id, true)
  }

  // Identical records (same language, form and meaning, e.g. repeated dialect-survey rows)
  // are drawn as one node marked ×N. This is display-only; the records stay separate.
  const { nodeList, edgeList, alias } = useMemo(() => {
    const groups = new Map<string, DisplayNode>()
    const alias = new Map<string, string>()
    for (const n of nodes.values()) {
      const key = `${n.language_id}|${n.form.trim()}|${n.gloss ?? ''}`
      const existing = groups.get(key)
      if (existing && n.id !== rootId) {
        existing.records += 1
        alias.set(n.id, existing.id)
      } else if (existing && n.id === rootId) {
        groups.set(key, { ...n, records: existing.records + 1 })
        alias.set(existing.id, n.id)
      } else {
        groups.set(key, { ...n, records: 1 })
      }
    }
    const resolve = (id: string) => {
      let current = id
      while (alias.has(current)) current = alias.get(current)!
      return current
    }
    for (const id of alias.keys()) alias.set(id, resolve(id))
    const seenEdges = new Map<string, GraphEdge>()
    for (const e of edges.values()) {
      const source = resolve(e.source)
      const target = resolve(e.target)
      const key = `${source}|${target}|${e.type}`
      if (source !== target && !seenEdges.has(key)) seenEdges.set(key, { ...e, source, target })
    }
    return { nodeList: [...groups.values()], edgeList: [...seenEdges.values()], alias }
  }, [nodes, edges, rootId])
  const languageGroups = useMemo(() => {
    const groups = new Map<string, Language[]>()
    languages.forEach((l) => groups.set(l.role, [...(groups.get(l.role) ?? []), l]))
    return groups
  }, [languages])

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 text-slate-900">
      <header className="mb-4">
        <h1 className="text-2xl font-semibold">Language Similarity Graph</h1>
        <p className="mt-1 text-sm text-slate-600">
          Explore documented relationships between words in Indian languages. Every link shown
          here comes from a cited source; similar spellings are listed separately as candidates.
        </p>
      </header>

      <form
        className="flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault()
          void runSearch(query, languageId)
        }}
      >
        <label className="sr-only" htmlFor="q">Word</label>
        <input
          id="q"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Type a word, e.g. dānt, mālā, ಹಗಲು"
          className="min-w-0 flex-1 basis-64 rounded-md border border-slate-300 px-3 py-2"
          maxLength={64}
        />
        <label className="sr-only" htmlFor="lang">Language</label>
        <select
          id="lang"
          value={languageId}
          onChange={(e) => setLanguageId(e.target.value)}
          className="w-full max-w-full rounded-md border border-slate-300 px-2 py-2 sm:w-auto"
        >
          <option value="">Any language</option>
          {[...languageGroups.entries()].map(([role, langs]) => (
            <optgroup key={role} label={role}>
              {langs.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name} ({l.linked_count.toLocaleString()} linked)
                </option>
              ))}
            </optgroup>
          ))}
        </select>
        <button type="submit" className="rounded-md bg-blue-700 px-4 py-2 font-medium text-white">
          Search
        </button>
      </form>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-600">
        Try:
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            type="button"
            className="rounded-full border border-slate-300 px-2.5 py-0.5 hover:bg-slate-100"
            onClick={() => {
              setQuery(ex)
              void runSearch(ex, languageId)
            }}
          >
            {ex}
          </button>
        ))}
      </div>

      <p className="mt-2 h-5 text-sm text-slate-500" role="status">{busy}</p>
      {error && <p className="rounded-md bg-red-50 p-2 text-sm text-red-800">{error}</p>}

      <div className="mt-2 grid gap-6 lg:grid-cols-[22rem_1fr]">
        <aside className="space-y-4">
          {results && (
            <section aria-label="Search results">
              {results.warnings.map((w) => (
                <p key={w} className="mb-2 rounded-md bg-amber-50 p-2 text-sm text-amber-900">{w}</p>
              ))}
              {results.matches.length > 0 && (
                <details open={resultsOpen} onToggle={(e) => setResultsOpen(e.currentTarget.open)}>
                  <summary className="mb-2 cursor-pointer text-sm font-semibold">
                    Matches for “{results.query}” ({results.matches.length})
                  </summary>
                  <div className="space-y-1.5">
                    {results.matches.map((m) => <MatchButton key={m.id} m={m} onPick={pick} />)}
                  </div>
                </details>
              )}
              {results.spelling_candidates.length > 0 && (
                <details className="mt-3">
                  <summary className="cursor-pointer text-sm font-semibold">
                    Similar spellings ({results.spelling_candidates.length}) — candidates, not evidence of relation
                  </summary>
                  <div className="mt-2 space-y-1.5">
                    {results.spelling_candidates.map((m) => <MatchButton key={m.id} m={m} onPick={pick} />)}
                  </div>
                </details>
              )}
            </section>
          )}
          <section id="details" className="scroll-mt-4 rounded-lg border border-slate-200 p-3">
            <DetailsPanel
              key={selection ? `${selection.kind}:${selection.id}` : 'none'}
              selection={selection} onExpand={(id) => void expand(id)} expanded={expanded} />
          </section>
        </aside>

        <section aria-label="Graph" className="min-w-0">
          {rootId ? (
            <>
              <GraphCanvas
                nodes={nodeList}
                edges={edgeList}
                rootId={rootId}
                selection={selection}
                onSelect={setSelection}
                onExpand={(id) => void expand(id)}
              />
              <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                <GraphLegend />
                <span className="text-xs text-slate-500">
                  {nodeList.length} words ({nodes.size} records) · {edgeList.length} links
                  {truncated && ' · truncated, expand to see more'}
                </span>
              </div>
              <details className="mt-4">
                <summary className="cursor-pointer text-sm font-semibold">Links as a table</summary>
                <table className="mt-2 w-full text-left text-sm">
                  <thead className="text-slate-500">
                    <tr><th className="py-1">From</th><th>Relation</th><th>To</th><th>Source</th></tr>
                  </thead>
                  <tbody>
                    {edgeList.map((e) => {
                      const s = nodes.get(alias.get(e.source) ?? e.source)
                      const t = nodes.get(alias.get(e.target) ?? e.target)
                      return (
                        <tr key={e.id} className="border-t border-slate-100">
                          <td className="py-1">{s?.form} <span className="text-slate-500">{s?.language_name}</span></td>
                          <td>
                            <button type="button" className="underline" onClick={() => {
                                setSelection({ kind: 'edge', id: e.id })
                                document.getElementById('details')?.scrollIntoView({ block: 'start' })
                              }}>
                              {styleFor(e.type).short}
                            </button>
                          </td>
                          <td>{t?.form} <span className="text-slate-500">{t?.language_name}</span></td>
                          <td className="text-slate-600">{e.citation}</td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </details>
            </>
          ) : (
            <div className="flex h-[440px] items-center lg:h-[600px] justify-center rounded-lg border border-dashed border-slate-300 text-slate-500">
              Search for a word and pick a match to see its relationships.
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
