import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ExplorePage from './ExplorePage.tsx'

// Cytoscape needs a real canvas, which jsdom lacks; these tests only check the data flow.
vi.mock('../components/GraphCanvas.tsx', () => ({ default: () => null }))

const json = (body: unknown) => Promise.resolve(new Response(JSON.stringify(body)))

const searchResponse = {
  query: 'dānt',
  normalized_query: 'dānt',
  detected_script: 'Latin',
  language_hints: ['pan'],
  matches: [
    {
      id: 'lx_1', form: 'dānt', native_form: null, language_id: 'pan', language_name: 'Punjabi',
      group: 'Indo-Aryan', gloss: 'tooth', reconstruction_status: 'attested', is_proto: false,
      form_kind: 'word',
      match_type: 'exact', score: null, relationship_count: 1, duplicate_count: 1,
    },
  ],
  related_forms: [
    {
      id: 'lx_3', form: 'dānta-', native_form: null, language_id: 'oia', language_name: 'Old Indo-Aryan',
      group: 'Indo-Aryan', gloss: null, reconstruction_status: 'attested', is_proto: false,
      form_kind: 'stem', match_type: 'loose', score: null, relationship_count: 0, duplicate_count: 1,
    },
  ],
  compounds: [],
  spelling_candidates: [
    {
      id: 'lx_2', form: 'dānti', native_form: null, language_id: 'mar', language_name: 'Marathi',
      group: 'Indo-Aryan', gloss: null, reconstruction_status: 'attested', is_proto: false,
      form_kind: 'word',
      match_type: 'spelling_candidate', score: 0.57, relationship_count: 0, duplicate_count: 1,
    },
  ],
  warnings: [],
}

describe('ExplorePage', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('shows the empty graph state before a search', () => {
    vi.stubGlobal('fetch', vi.fn(() => json([])))
    render(<ExplorePage />)
    expect(screen.getByText(/Search for a word and pick a match/)).toBeInTheDocument()
  })

  it('lists exact matches separately from spelling candidates', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) => json(url.includes('/search') ? searchResponse : [])))
    render(<ExplorePage />)
    fireEvent.change(screen.getByLabelText('Word'), { target: { value: 'dānt' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText(/Matches for/)).toBeInTheDocument()
    expect(screen.getByText(/1 documented link/)).toBeInTheDocument()
    expect(screen.getByText(/candidates, not evidence of relation/)).toBeInTheDocument()
    expect(screen.getByText(/Stems, affixes and other forms/)).toBeInTheDocument()
    expect(screen.getByText(/stem \(combining form\)/)).toBeInTheDocument()
  })

  it('runs a shared link search and opens the first match with links', async () => {
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('/search')) return json(searchResponse)
      if (url.includes('/graph/')) return json({ root_id: 'lx_1', nodes: [], edges: [], truncated: false })
      // the details panel loads the opened word too; answer with a full detail record
      if (url.includes('/lexemes/')) return json({ ...searchResponse.matches[0], concepts: [], source: null })
      return json([])
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ExplorePage initialQuery="dānt" initialLanguage="pan" />)
    expect(await screen.findByText(/Matches for/)).toBeInTheDocument()
    await vi.waitFor(
      () => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/graph/lx_1'))).toBe(true),
      { timeout: 5000 }, // search, then pick, then the graph fetch: slow on a loaded runner
    )
    expect(await screen.findByText('no source recorded', {}, { timeout: 5000 })).toBeInTheDocument()
  })

  it('shows an error when search fails', async () => {
    vi.stubGlobal('fetch', vi.fn((url: string) =>
      url.includes('/search') ? Promise.reject(new Error('offline')) : json([])))
    render(<ExplorePage />)
    fireEvent.change(screen.getByLabelText('Word'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Search' }))
    expect(await screen.findByText(/Search failed: offline/)).toBeInTheDocument()
  })
})

describe('language picker', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('filters hundreds of languages by name or family', async () => {
    const lang = (id: string, name: string, role: string, group: string, family_name: string) => ({
      id, name, role, group, family_id: null, family_name, glottocode: null, primary_script: null,
      lexeme_count: 10, linked_count: 1, open_lexeme_count: 4, open_linked_count: 0,
    })
    const languages = [
      lang('hin', 'Hindi-Urdu', 'modern', 'Indo-Aryan', 'Indo-European'),
      lang('gl-dutc1256', 'Dutch', 'other', 'Indo-European', 'Germanic'),
      lang('gl-tagu1234', 'Tagalog', 'other', 'Austronesian', 'Austronesian'),
    ]
    vi.stubGlobal('fetch', vi.fn(() => json(languages)))
    render(<ExplorePage />)
    expect(await screen.findByRole('option', { name: /Tagalog/ })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Filter languages'), { target: { value: 'germ' } })
    expect(screen.getByRole('option', { name: /Dutch/ })).toBeInTheDocument()
    expect(screen.queryByRole('option', { name: /Tagalog/ })).toBeNull()
    expect(screen.queryByRole('option', { name: /Hindi/ })).toBeNull()
  })
})

// ---- following the URL, stale responses and stale graphs ----

type Match = (typeof searchResponse.matches)[number]
const match = (id: string, form: string, links = 1): Match => ({
  ...searchResponse.matches[0], id, form, relationship_count: links,
})
const searchFor = (query: string, matches: Match[]) => ({
  ...searchResponse, query, matches, related_forms: [], spelling_candidates: [],
})
const graphOf = (...matches: Match[]) => ({
  root_lexeme_id: matches[0].id,
  nodes: matches.map((m) => ({ ...m, degree: 1 })),
  edges: matches.slice(1).map((m) => ({
    id: `e_${m.id}`, source: matches[0].id, target: m.id, type: 'cognate', label: 'cognate',
    namespace: 'x', status: 'attested', direction: 'undirected', source_id: null, citation: 'Test 2024',
  })),
  truncated: false,
  warnings: [],
})
const deferred = <T,>() => {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}
const reply = (body: unknown) => new Response(JSON.stringify(body))
const goTo = (hash: string) => {
  window.history.replaceState(null, '', hash)
  act(() => { window.dispatchEvent(new HashChangeEvent('hashchange')) })
}
const panjabi = [{
  id: 'pan', name: 'Punjabi', role: 'modern', group: 'Indo-Aryan', family_id: null, family_name: null,
  glottocode: null, primary_script: null, lexeme_count: 10, linked_count: 1,
}]
const emptyState = /Search for a word and pick a match/
const searchWord = (word: string) => {
  fireEvent.change(screen.getByLabelText('Word'), { target: { value: word } })
  fireEvent.click(screen.getByRole('button', { name: 'Search' }))
}

describe('ExplorePage follows the URL and drops stale data', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    window.history.replaceState(null, '', '#/')
  })

  const routes = (extra: Record<string, (url: string) => unknown> = {}) => vi.fn((url: string) => {
    for (const [part, fn] of Object.entries(extra)) if (url.includes(part)) return Promise.resolve(fn(url))
    if (url.includes('/lexemes/')) return json({ ...searchResponse.matches[0], concepts: [], source: null })
    return json(url.includes('/languages') ? panjabi : [])
  })

  it('shows the new query in the search box when the URL hash changes', async () => {
    vi.stubGlobal('fetch', routes({
      '/search': (url) => reply(searchFor(new URL(url, 'http://x').searchParams.get('q') ?? '', [])),
    }))
    render(<ExplorePage initialQuery="old" initialLanguage="" />)
    expect(await screen.findByText(/Matches for|No whole-word match for “old”/)).toBeInTheDocument()
    goTo('#/explore?q=new&lang=pan')
    expect(screen.getByLabelText('Word')).toHaveValue('new')
    expect(await screen.findByText(/No whole-word match for “new”/)).toBeInTheDocument()
    expect(screen.getByLabelText('Language')).toHaveValue('pan')
  })

  it('follows changed props too, and a link to the query the props already hold', async () => {
    vi.stubGlobal('fetch', routes({
      '/search': (url) => reply(searchFor(new URL(url, 'http://x').searchParams.get('q') ?? '', [])),
    }))
    const { rerender } = render(<ExplorePage initialQuery="a" initialLanguage="" />)
    expect(await screen.findByText(/No whole-word match for “a”/)).toBeInTheDocument()
    rerender(<ExplorePage initialQuery="b" initialLanguage="" />)
    await vi.waitFor(() => expect(screen.getByLabelText('Word')).toHaveValue('b'))
    expect(await screen.findByText(/No whole-word match for “b”/)).toBeInTheDocument()
    // the user searches "c" (the page rewrites the URL without a route change), then follows a
    // link back to "b", the query the props still hold
    searchWord('c')
    expect(await screen.findByText(/No whole-word match for “c”/)).toBeInTheDocument()
    goTo('#/explore?q=b')
    expect(screen.getByLabelText('Word')).toHaveValue('b')
    expect(await screen.findByText(/No whole-word match for “b”/)).toBeInTheDocument()
  })

  it('does not run the same URL search twice when both the props and the hash change', async () => {
    const fetchMock = routes({ '/search': () => reply(searchFor('x', [])) })
    vi.stubGlobal('fetch', fetchMock)
    const { rerender } = render(<ExplorePage />)
    goTo('#/explore?q=x')
    rerender(<ExplorePage initialQuery="x" initialLanguage="" />)
    expect(await screen.findByText(/No whole-word match for “x”/)).toBeInTheDocument()
    await new Promise((r) => setTimeout(r, 20))
    expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/search')).length).toBe(1)
  })

  it('empties the page when the URL loses its query', async () => {
    vi.stubGlobal('fetch', routes({
      '/search': () => reply(searchFor('dānt', [match('lx_1', 'dānt')])),
      '/graph/': () => reply(graphOf(match('lx_1', 'dānt'))),
    }))
    render(<ExplorePage initialQuery="dānt" initialLanguage="" />)
    expect(await screen.findByText(/1 words \(1 records\)/, {}, { timeout: 5000 })).toBeInTheDocument()
    goTo('#/explore')
    expect(screen.getByLabelText('Word')).toHaveValue('')
    expect(screen.getByText(emptyState)).toBeInTheDocument()
    expect(screen.queryByText(/Matches for/)).toBeNull()
  })

  it('clears the old graph and details as soon as a new search starts', async () => {
    const second = deferred<Response>()
    vi.stubGlobal('fetch', routes({
      '/search': () => reply(searchFor('dānt', [match('lx_1', 'dānt', 0), match('lx_2', 'dānti')])),
      '/graph/': () => reply(graphOf(match('lx_2', 'dānti'))),
    }))
    render(<ExplorePage />)
    searchWord('dānt')
    fireEvent.click(await screen.findByRole('button', { name: /dānti/ }))
    expect(await screen.findByText(/1 words \(1 records\)/)).toBeInTheDocument()
    expect(await screen.findByText('no source recorded')).toBeInTheDocument() // details panel
    vi.stubGlobal('fetch', vi.fn(() => second.promise))
    searchWord('other')
    expect(screen.getByText(emptyState)).toBeInTheDocument()
    expect(screen.queryByText('no source recorded')).toBeNull()
    expect(screen.queryByText(/Matches for/)).toBeNull()
    await act(async () => { second.resolve(reply(searchFor('other', [match('lx_9', 'other', 0)]))) })
    expect(await screen.findByText(/Matches for “other”/)).toBeInTheDocument()
    expect(screen.getByText(emptyState)).toBeInTheDocument() // nothing with links, nothing opened
  })

  it('ignores a slow earlier search that answers after a later one', async () => {
    const slow = deferred<Response>()
    const fetchMock = vi.fn((url: string) => {
      if (url.includes('q=slow')) return slow.promise
      if (url.includes('/search')) return json(searchFor('fast', [match('lx_5', 'fast', 0)]))
      return json([])
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ExplorePage />)
    searchWord('slow')
    searchWord('fast')
    expect(await screen.findByText(/Matches for “fast”/)).toBeInTheDocument()
    await act(async () => { slow.resolve(reply(searchFor('slow', [match('lx_4', 'slow', 0)]))) })
    expect(screen.getByText(/Matches for “fast”/)).toBeInTheDocument()
    expect(screen.queryByText(/Matches for “slow”/)).toBeNull()
    expect(screen.getByRole('status')).toBeEmptyDOMElement() // the stale answer left no busy text
  })

  it('does not let a slow graph for an earlier pick replace the later one', async () => {
    const slowGraph = deferred<Response>()
    vi.stubGlobal('fetch', routes({
      '/search': () => reply(searchFor('dānt', [match('lx_1', 'dānt'), match('lx_2', 'dānti')])),
    }))
    render(<ExplorePage />)
    searchWord('dānt')
    const first = await screen.findByRole('button', { name: /dānt .*Punjabi/ })
    const fetchWith = (graphs: Record<string, () => Promise<Response>>) => vi.stubGlobal('fetch', vi.fn((url: string) => {
      for (const [id, fn] of Object.entries(graphs)) if (url.includes(`/graph/${id}`)) return fn()
      return json({ ...searchResponse.matches[0], concepts: [], source: null })
    }))
    fetchWith({
      lx_1: () => slowGraph.promise,
      lx_2: () => json(graphOf(match('lx_2', 'dānti'), match('lx_7', 'seven'))),
    })
    fireEvent.click(first)
    fireEvent.click(screen.getByText('Matches for “dānt” (2)')) // reopen the list
    fireEvent.click(await screen.findByRole('button', { name: /dānti/ }))
    expect(await screen.findByText(/2 words \(2 records\)/)).toBeInTheDocument()
    await act(async () => { slowGraph.resolve(reply(graphOf(match('lx_1', 'dānt')))) })
    expect(screen.getByText(/2 words \(2 records\)/)).toBeInTheDocument()
  })

  it('shows no graph from a previous word when the new graph fails to load', async () => {
    vi.stubGlobal('fetch', routes({
      '/search': () => reply(searchFor('dānt', [match('lx_1', 'dānt'), match('lx_2', 'dānti')])),
      '/graph/lx_1': () => reply(graphOf(match('lx_1', 'dānt'), match('lx_7', 'seven'))),
      '/graph/lx_2': () => { throw new Error('boom') },
    }))
    render(<ExplorePage />)
    searchWord('dānt')
    fireEvent.click(await screen.findByRole('button', { name: /dānt .*Punjabi/ }))
    expect(await screen.findByText(/2 words \(2 records\)/)).toBeInTheDocument()
    fireEvent.click(screen.getByText('Matches for “dānt” (2)'))
    fireEvent.click(await screen.findByRole('button', { name: /dānti/ }))
    expect(await screen.findByText(/Could not load the graph: boom/)).toBeInTheDocument()
    expect(screen.getByText(/0 words \(0 records\)/)).toBeInTheDocument()
  })

  it('removes the old matches when a search fails', async () => {
    let fail = false
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (!url.includes('/search')) return json([])
      return fail ? Promise.reject(new Error('offline')) : json(searchFor('dānt', [match('lx_1', 'dānt', 0)]))
    }))
    render(<ExplorePage />)
    searchWord('dānt')
    expect(await screen.findByText(/Matches for “dānt”/)).toBeInTheDocument()
    fail = true
    searchWord('next')
    expect(await screen.findByText(/Search failed: offline/)).toBeInTheDocument()
    expect(screen.queryByText(/Matches for/)).toBeNull()
  })

  it('"Open data only" clears the graph and searches again with open_only', async () => {
    const fetchMock = routes({
      '/search': () => reply(searchFor('dānt', [match('lx_1', 'dānt')])),
      '/graph/': () => reply(graphOf(match('lx_1', 'dānt'))),
    })
    vi.stubGlobal('fetch', fetchMock)
    render(<ExplorePage />)
    searchWord('dānt')
    fireEvent.click(await screen.findByRole('button', { name: /dānt .*Punjabi/ }))
    expect(await screen.findByText(/1 words \(1 records\)/)).toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('Open data only'))
    expect(screen.getByText(emptyState)).toBeInTheDocument()
    expect(await screen.findByText(/Matches for “dānt”/)).toBeInTheDocument()
    const searches = fetchMock.mock.calls.map(([u]) => String(u)).filter((u) => u.includes('/search'))
    expect(searches.length).toBe(2)
    expect(searches[1]).toContain('open_only=true')
  })

  it('"Open data only" drops the old matches and a late graph when there is no query', async () => {
    const slowGraph = deferred<Response>()
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/search')) return json(searchFor('dānt', [match('lx_1', 'dānt')]))
      if (url.includes('/graph/')) return slowGraph.promise
      if (url.includes('/languages')) return json([])
      return json({ ...searchResponse.matches[0], concepts: [], source: null })
    }))
    render(<ExplorePage />)
    searchWord('dānt')
    fireEvent.click(await screen.findByRole('button', { name: /dānt .*Punjabi/ }))
    fireEvent.change(screen.getByLabelText('Word'), { target: { value: '' } })
    fireEvent.click(screen.getByLabelText('Open data only'))
    expect(screen.queryByText(/Matches for/)).toBeNull()
    await act(async () => { slowGraph.resolve(reply(graphOf(match('lx_1', 'dānt')))) })
    expect(screen.getByText(emptyState)).toBeInTheDocument()
  })
})

describe('graph downloads', () => {
  const urlApi = URL as unknown as Record<string, unknown>
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    delete urlApi.createObjectURL
    delete urlApi.revokeObjectURL
  })

  it('offers JSON, SVG and PNG above the graph, and the JSON holds the links shown', async () => {
    const graph = {
      root_lexeme_id: 'lx_1',
      nodes: [
        { ...searchResponse.matches[0], degree: 1 },
        {
          id: 'lx_9', form: 'dānta', native_form: null, language_id: 'oia', language_name: 'Old Indo-Aryan',
          group: 'Indo-Aryan', gloss: 'tooth', reconstruction_status: 'attested', is_proto: false,
          form_kind: 'word', degree: 1,
        },
      ],
      edges: [
        {
          id: 'rel_1', source: 'lx_1', target: 'lx_9', type: 'inherited_form', label: 'Inherited form',
          namespace: 'lexical', status: 'documented', direction: 'directed', source_id: 'wiktionary',
          citation: 'Wiktionary, “dānt”',
        },
      ],
      truncated: false,
      warnings: [],
    }
    vi.stubGlobal('fetch', vi.fn((url: string) => {
      if (url.includes('/search')) return json(searchResponse)
      if (url.includes('/graph/')) return json(graph)
      if (url.includes('/lexemes/')) return json({ ...searchResponse.matches[0], concepts: [], source: null })
      return json([])
    }))
    const blobs: Blob[] = []
    urlApi.createObjectURL = vi.fn((b: Blob) => (blobs.push(b), 'blob:test'))
    urlApi.revokeObjectURL = vi.fn()
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})

    render(<ExplorePage initialQuery="dānt" initialLanguage="pan" />)
    const jsonButton = await screen.findByRole('button', { name: /as JSON/ }, { timeout: 5000 })
    expect(screen.getByRole('button', { name: /as an SVG drawing/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /as a PNG image/ })).toBeInTheDocument()
    await vi.waitFor(() => expect(screen.getByText(/1 links/)).toBeInTheDocument(), { timeout: 5000 })

    fireEvent.click(jsonButton)
    expect(click).toHaveBeenCalledTimes(1)
    expect(blobs).toHaveLength(1)
    const out = JSON.parse(await blobs[0].text())
    expect(out.root.form).toBe('dānt')
    expect(out.open_data_only).toBe(false)
    expect(out.links).toHaveLength(1)
    expect(out.links[0].sentence).toBe('dānt (Punjabi) is inherited from dānta (Old Indo-Aryan)')
    expect(out.links[0].citation).toBe('Wiktionary, “dānt”')
  })

  it('has no download buttons before a graph is shown', () => {
    vi.stubGlobal('fetch', vi.fn(() => json([])))
    render(<ExplorePage />)
    expect(screen.queryByRole('button', { name: /Download/ })).toBeNull()
  })
})
