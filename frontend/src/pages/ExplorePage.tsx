import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { getGraph, getLanguages, searchLexemes } from '../api/client.ts'
import { parse, replaceParams } from '../app/router.ts'
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
import {
  downloadFile,
  downloadText,
  fileStem,
  graphToJson,
  type GraphExporter,
} from '../components/graphExport.ts'
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
  const [languageFilter, setLanguageFilter] = useState('')
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

  // Every search and every graph load gets a number; a response that is no longer the latest is
  // dropped, so a slow earlier request cannot overwrite a later one.
  const searchSeq = useRef(0)
  const graphSeq = useRef(0)
  const exporter = useRef<GraphExporter | null>(null) // the canvas's SVG and PNG download functions
  // The URL query this page last ran, so following the URL does not repeat a search that is
  // already running or shown.
  const loadedRef = useRef('')

  // Remove the graph, its selection and its details, and drop any graph load still in flight.
  const clearGraph = useCallback(() => {
    graphSeq.current += 1
    setRootId(null)
    setNodes(new Map())
    setEdges(new Map())
    setExpanded(new Set())
    setTruncated(false)
    setSelection(null)
    setShowAll(new Set())
    setHiddenTypes(new Set())
    setHiddenGroups(new Set())
  }, [])

  const runSearch = useCallback(async (q: string, lang: string): Promise<SearchResponse | null> => {
    if (!q.trim()) return null
    const id = ++searchSeq.current
    loadedRef.current = `${q.trim()}\n${lang}`
    replaceParams('/explore', { q: q.trim(), lang: lang || undefined }) // shareable URL
    clearGraph() // the old word's graph and details do not belong to the new query
    setResults(null) // nor do its matches; the list returns with the new ones
    setBusy('Searching…')
    setError(null)
    try {
      const res = await searchLexemes(q.trim(), lang || undefined, openOnlyRef.current)
      if (id !== searchSeq.current) return null // a newer search replaced this one
      setResults(res)
      setResultsOpen(true)
      return res
    } catch (e) {
      if (id !== searchSeq.current) return null
      setError(`Search failed: ${(e as Error).message}`)
      return null
    } finally {
      if (id === searchSeq.current) setBusy(null)
    }
  }, [clearGraph])

  const expand = useCallback(async (id: string, reset = false) => {
    const seq = graphSeq.current
    setBusy('Loading connections…')
    setError(null)
    try {
      const g = await getGraph(id, openOnlyRef.current)
      if (seq !== graphSeq.current) return // the graph was replaced or cleared meanwhile
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
      if (seq !== graphSeq.current) return
      setError(`Could not load the graph: ${(e as Error).message}`)
    } finally {
      if (seq === graphSeq.current) setBusy(null)
    }
  }, [])

  const pick = useCallback((m: SearchMatch) => {
    clearGraph() // the previous word's graph must not stay if this one fails to load
    setResultsOpen(false)
    setRootId(m.id)
    setSelection({ kind: 'node', id: m.id })
    void expand(m.id, true)
  }, [clearGraph, expand])

  // Make the page show what the URL says: the input and language follow the query, and the
  // search runs, opening the first match that has documented links so a shared link, a "Try"
  // link or Back/Forward lands on a graph. A URL without a query empties the page.
  const followUrl = useCallback(async (q: string, lang: string) => {
    const key = q.trim() ? `${q.trim()}\n${lang}` : ''
    if (key === loadedRef.current) return
    setQuery(q)
    setLanguageId(lang)
    if (!key) {
      loadedRef.current = ''
      searchSeq.current += 1
      setResults(null)
      setError(null)
      setBusy(null)
      clearGraph()
      return
    }
    const res = await runSearch(q, lang)
    const first = res?.matches.find((m) => m.relationship_count > 0)
    if (first) pick(first)
  }, [runSearch, pick, clearGraph])

  // Props change when the route changes; the listener also catches a link to the query the
  // props already hold, because the page rewrites the URL itself when you search.
  const propsUsed = useRef(false)
  useEffect(() => {
    if (!initialQuery && !propsUsed.current) return // a plain #/explore needs nothing on mount
    propsUsed.current = true
    const id = window.setTimeout(() => void followUrl(initialQuery, initialLanguage), 0)
    return () => window.clearTimeout(id)
  }, [initialQuery, initialLanguage, followUrl])
  useEffect(() => {
    const onHash = () => {
      const route = parse(window.location.hash)
      if (route.path === '/explore') void followUrl(route.params.get('q') ?? '', route.params.get('lang') ?? '')
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [followUrl])

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
    // Languages grouped by family (alphabetically), historical layers last. With hundreds of
    // languages, the filter box narrows the list by language or family name.
    const groups = new Map<string, Language[]>()
    const label = (l: Language) =>
      l.role === 'modern'
        ? (l.group ?? 'Other')
        : l.role === 'other'
          ? (l.family_name ?? l.group ?? 'Other')
          : 'Historical and reference'
    const needle = languageFilter.trim().toLowerCase()
    const shown = languages.filter(
      (l) =>
        !needle ||
        l.id === languageId ||
        l.name.toLowerCase().includes(needle) ||
        label(l).toLowerCase().includes(needle),
    )
    const sorted = [...shown].sort((a, b) => a.name.localeCompare(b.name))
    sorted.forEach((l) => groups.set(label(l), [...(groups.get(label(l)) ?? []), l]))
    const order = [...groups.keys()].sort((a, b) =>
      a === 'Historical and reference' ? 1 : b === 'Historical and reference' ? -1 : a.localeCompare(b),
    )
    return new Map(order.map((k) => [k, groups.get(k)!]))
  }, [languages, languageFilter, languageId])
  const wordCount = (l: Language) =>
    (openOnly ? (l.open_lexeme_count ?? l.lexeme_count) : l.lexeme_count).toLocaleString()

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
        <label className="sr-only" htmlFor="lang-filter">Filter languages</label>
        <input
          id="lang-filter"
          value={languageFilter}
          onChange={(e) => setLanguageFilter(e.target.value)}
          placeholder={`Filter ${languages.length.toLocaleString()} languages`}
          className="w-40 rounded-md border border-slate-300 px-2 py-2 text-sm"
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
                  {l.name} ({wordCount(l)} words)
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
              clearGraph()
              if (query.trim()) void runSearch(query, languageId)
              else {
                searchSeq.current += 1
                setResults(null) // matches found with the other setting no longer apply
                setBusy(null)
              }
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
              <div
                role="group"
                aria-label="Download the graph shown"
                className="mb-2 flex flex-wrap items-center justify-end gap-2 text-xs text-slate-700"
              >
                <span className="font-semibold">Download:</span>
                {[
                  ['JSON', 'Download the words and links shown as JSON'],
                  ['SVG', 'Download the graph shown as an SVG drawing'],
                  ['PNG', 'Download the graph shown as a PNG image'],
                ].map(([kind, label]) => (
                  <button
                    key={kind}
                    type="button"
                    aria-label={label}
                    className="rounded border border-slate-300 px-2 py-1 font-medium hover:bg-slate-50"
                    onClick={() => {
                      const stem = fileStem(byId.get(rootId)?.form)
                      if (kind === 'JSON') {
                        const meta = {
                          rootId,
                          openOnly,
                          pageUrl: window.location.href,
                          generatedAt: new Date().toISOString(),
                        }
                        downloadText(`${stem}.json`, graphToJson(nodeList, edgeList, meta), 'application/json')
                      } else if (kind === 'SVG' && exporter.current) {
                        const title = `Linguistic DNA: ${byId.get(rootId)?.form ?? 'graph'}`
                        downloadText(`${stem}.svg`, exporter.current.svg(title), 'image/svg+xml')
                      } else if (kind === 'PNG' && exporter.current) {
                        downloadFile(`${stem}.png`, exporter.current.png())
                      }
                    }}
                  >
                    {kind}
                  </button>
                ))}
              </div>
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
                exporter={exporter}
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
