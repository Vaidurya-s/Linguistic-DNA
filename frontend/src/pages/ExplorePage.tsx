import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getGraph, getLanguages, searchLexemes } from '../api/client.ts'
import { replaceParams } from '../app/router.ts'
import DetailsPanel from '../components/DetailsPanel.tsx'
import GraphCanvas, { type Selection } from '../components/GraphCanvas.tsx'
import {
  applyFilters,
  capNeighbours,
  describeEdge,
  groupOf,
  mergeDuplicates,
} from '../components/graphModel.ts'
import GraphLegend from '../components/GraphLegend.tsx'
import { styleFor } from '../components/edgeStyles.ts'
import type { GraphEdge, GraphNode, Language, SearchMatch, SearchResponse } from '../types/api.ts'

const EXAMPLES = ['पानी', 'paani', 'angara', 'bidyut', 'ಹಲ್ಲು']
const NEIGHBOUR_LIMIT = 24

const MATCH_LABEL: Record<string, string> = {
  exact: 'exact',
  native_exact: 'exact (native script)',
  loose: 'matched ignoring diacritics',
  transliteration: 'matched through transliteration',
  spelling_candidate: 'similar spelling — candidate only',
  compound_of_match: 'documented compound containing a match',
}

const KIND_LABEL: Record<string, string> = {
  stem: 'stem (combining form)',
  affix: 'affix',
  root: 'root',
  compound: 'compound',
  phrase: 'multi-word phrase',
}

function ResultGroup({ title, items, onPick, open = false }: {
  title: string
  items: SearchMatch[]
  onPick: (m: SearchMatch) => void
  open?: boolean
}) {
  if (items.length === 0) return null
  return (
    <details className="mt-3" open={open}>
      <summary className="cursor-pointer text-sm font-semibold">
        {title} ({items.length})
      </summary>
      <div className="mt-2 space-y-1.5">
        {items.map((m) => <MatchButton key={m.id} m={m} onPick={onPick} />)}
      </div>
    </details>
  )
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
        {m.form_kind !== 'word' && `${KIND_LABEL[m.form_kind] ?? m.form_kind} · `}
        {MATCH_LABEL[m.match_type]}
        {m.via && <span title="How this match was found"> ({m.via})</span>}
        {m.score !== null && ` (score ${m.score.toFixed(2)}, not a relatedness measure)`} ·{' '}
        {m.relationship_count} documented link{m.relationship_count === 1 ? '' : 's'}
        {m.duplicate_count > 1 && ` · ${m.duplicate_count} identical records grouped`}
      </span>
    </button>
  )
}

type Props = { initialQuery?: string; initialLanguage?: string }

export default function ExplorePage({ initialQuery = '', initialLanguage = '' }: Props) {
  const [languages, setLanguages] = useState<Language[]>([])
  const [query, setQuery] = useState(initialQuery)
  const [languageId, setLanguageId] = useState(initialLanguage)
  // Hide research-use data (unlicensed sources such as Jambu, CDIAL, DEDR). A ref keeps the
  // search and graph callbacks stable; the state drives the checkbox.
  const [openOnly, setOpenOnly] = useState(false)
  const openOnlyRef = useRef(false)
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
  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set())
  const [hiddenGroups, setHiddenGroups] = useState<Set<string>>(new Set())
  const [showAll, setShowAll] = useState<Set<string>>(new Set())

  useEffect(() => {
    getLanguages().then(setLanguages).catch(() => setLanguages([]))
  }, [])

  const runSearch = useCallback(async (q: string, lang: string): Promise<SearchResponse | null> => {
    if (!q.trim()) return null
    replaceParams('/explore', { q: q.trim(), lang: lang || undefined }) // shareable URL
    setBusy('Searching…')
    setError(null)
    try {
      const res = await searchLexemes(q.trim(), lang || undefined, openOnlyRef.current)
      setResults(res)
      setResultsOpen(true)
      setSelection(null) // the old word's details no longer match the new results
      return res
    } catch (e) {
      setError(`Search failed: ${(e as Error).message}`)
      return null
    } finally {
      setBusy(null)
    }
  }, [])

  const expand = useCallback(async (id: string, reset = false) => {
    setBusy('Loading connections…')
    setError(null)
    try {
      const g = await getGraph(id, openOnlyRef.current)
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

  const pick = useCallback((m: SearchMatch) => {
    setResultsOpen(false)
    setShowAll(new Set())
    setRootId(m.id)
    setSelection({ kind: 'node', id: m.id })
    void expand(m.id, true)
  }, [expand])

  // Opening a shared link (#/explore?q=…) runs that search once the page is mounted, and
  // opens the first match that has documented links so the link lands on a graph.
  useEffect(() => {
    if (!initialQuery) return
    const id = window.setTimeout(async () => {
      const res = await runSearch(initialQuery, initialLanguage)
      const first = res?.matches.find((m) => m.relationship_count > 0)
      if (first) pick(first)
    }, 0)
    return () => window.clearTimeout(id)
  }, [initialQuery, initialLanguage, runSearch, pick])

  const merged = useMemo(() => mergeDuplicates(nodes.values(), edges.values(), rootId), [nodes, edges, rootId])
  const presentTypes = useMemo(() => [...new Set(merged.edges.map((e) => e.type))].sort(), [merged])
  const presentGroups = useMemo(() => [...new Set(merged.nodes.map(groupOf))].sort(), [merged])
  const { graph: shown, hidden } = useMemo(() => {
    if (!rootId) return { graph: merged, hidden: new Map<string, number>() }
    const filtered = applyFilters(
      merged,
      rootId,
      new Set(presentTypes.filter((t) => !hiddenTypes.has(t))),
      new Set(presentGroups.filter((g) => !hiddenGroups.has(g))),
    )
    return capNeighbours(filtered, rootId, expanded, NEIGHBOUR_LIMIT, showAll)
  }, [merged, rootId, presentTypes, presentGroups, hiddenTypes, hiddenGroups, expanded, showAll])
  const nodeList = shown.nodes
  const edgeList = shown.edges
  const byId = useMemo(() => new Map(merged.nodes.map((n) => [n.id, n])), [merged])
  const toggle = (set: Set<string>, value: string) => {
    const next = new Set(set)
    if (next.has(value)) next.delete(value)
    else next.add(value)
    return next
  }
  const languageGroups = useMemo(() => {
    // Modern languages grouped by family (alphabetically), historical layers last.
    const groups = new Map<string, Language[]>()
    const label = (l: Language) => (l.role === 'modern' ? (l.group ?? 'Other') : 'Historical and reference')
    const sorted = [...languages].sort((a, b) => a.name.localeCompare(b.name))
    sorted.forEach((l) => groups.set(label(l), [...(groups.get(label(l)) ?? []), l]))
    const order = [...groups.keys()].sort((a, b) =>
      a === 'Historical and reference' ? 1 : b === 'Historical and reference' ? -1 : a.localeCompare(b),
    )
    return new Map(order.map((k) => [k, groups.get(k)!]))
  }, [languages])

  return (
    <main className="mx-auto max-w-7xl px-4 py-6 text-slate-900">
      <header className="mb-4">
        <h1 className="text-2xl font-semibold">Explore</h1>
        <p className="mt-1 text-sm text-slate-600">
          Every link shown comes from a cited source. Similar spellings are listed separately, as
          candidates.
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
          {[...languageGroups.entries()].map(([family, langs]) => (
            <optgroup key={family} label={family}>
              {langs.map((l) => (
                <option key={l.id} value={l.id}>
                  {l.name} ({l.lexeme_count.toLocaleString()} words)
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
        <label className="mr-3 flex items-center gap-1.5" title="Hide data from sources used for research only (Jambu, CDIAL, DEDR)">
          <input
            type="checkbox"
            checked={openOnly}
            onChange={(e) => {
              openOnlyRef.current = e.target.checked
              setOpenOnly(e.target.checked)
              setRootId(null)
              setNodes(new Map())
              setEdges(new Map())
              setSelection(null)
              if (query.trim()) void runSearch(query, languageId)
            }}
          />
          Open data only
        </label>
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
              {results.matches.length === 0 && (
                <p className="mb-2 text-sm text-slate-600">No whole-word match for “{results.query}”.</p>
              )}
              <ResultGroup
                title="Stems, affixes and other forms with this spelling"
                items={results.related_forms}
                onPick={pick}
                open={results.matches.length === 0}
              />
              <ResultGroup title="Compounds containing a match" items={results.compounds} onPick={pick} />
              <ResultGroup
                title="Similar spellings — candidates, not evidence of relation"
                items={results.spelling_candidates}
                onPick={pick}
              />
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
              <fieldset className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-700">
                <legend className="sr-only">Filter the graph</legend>
                <span className="font-semibold">Show:</span>
                {presentTypes.map((type) => (
                  <label key={type} className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={!hiddenTypes.has(type)}
                      onChange={() => setHiddenTypes((s) => toggle(s, type))}
                    />
                    {styleFor(type).short}
                  </label>
                ))}
                <span className="ml-2 font-semibold">Languages:</span>
                {presentGroups.map((group) => (
                  <label key={group} className="flex items-center gap-1">
                    <input
                      type="checkbox"
                      checked={!hiddenGroups.has(group)}
                      onChange={() => setHiddenGroups((s) => toggle(s, group))}
                    />
                    {group === 'other' ? 'other / proto' : group}
                  </label>
                ))}
              </fieldset>
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
              {[...hidden.entries()].map(([hub, count]) => (
                <p key={hub} className="mt-1 text-xs text-slate-600">
                  {count} more links around <strong>{byId.get(hub)?.form}</strong> are hidden to keep the
                  graph readable.{' '}
                  <button type="button" className="underline" onClick={() => setShowAll((s) => toggle(s, hub))}>
                    Show all
                  </button>
                </p>
              ))}
              <details className="mt-4">
                <summary className="cursor-pointer text-sm font-semibold">Links as a table</summary>
                <table className="mt-2 w-full text-left text-sm">
                  <thead className="text-slate-500">
                    <tr><th className="py-1">Relation</th><th>Type</th><th>Source</th></tr>
                  </thead>
                  <tbody>
                    {edgeList.map((e) => {
                      const selected = selection?.kind === 'edge' && selection.id === e.id
                      return (
                        <tr
                          key={e.id}
                          className={`border-t border-slate-100 ${selected ? 'bg-blue-50' : ''}`}
                          aria-selected={selected}
                        >
                          <td className="py-1">{describeEdge(e.type, byId.get(e.source), byId.get(e.target))}</td>
                          <td>
                            <button
                              type="button"
                              className="underline"
                              onClick={() => {
                                setSelection({ kind: 'edge', id: e.id })
                                document.getElementById('details')?.scrollIntoView({ block: 'start' })
                              }}
                            >
                              {styleFor(e.type).short}
                            </button>
                          </td>
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
