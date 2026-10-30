import { cleanup, fireEvent, render, screen } from '@testing-library/react'
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
