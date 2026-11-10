import { describe, expect, it } from 'vitest'
import type { GraphEdge } from '../types/api.ts'
import type { DisplayNode } from './graphModel.ts'
import { buildSvg, fileStem, graphToJson, type SvgEdge, type SvgNode } from './graphExport.ts'

const node = (id: string, form: string, language: string, extra: Partial<DisplayNode> = {}): DisplayNode => ({
  id, form, native_form: null, language_id: language.toLowerCase(), language_name: language,
  group: null, gloss: 'water', reconstruction_status: 'attested', is_proto: false, form_kind: 'word',
  degree: 1, records: 1, ...extra,
})
const edge = (id: string, source: string, target: string, type: string): GraphEdge => ({
  id, source, target, type, label: type, namespace: 'lexical', status: 'documented',
  direction: 'directed', source_id: 'wiktionary', citation: 'Wiktionary, “x”',
})

describe('graphToJson', () => {
  const nodes = [node('a', 'पानी', 'Hindi'), node('b', 'पाणीअ', 'Prakrit', { records: 2 })]
  const edges = [edge('e1', 'a', 'b', 'inherited_form')]
  const meta = { rootId: 'a', openOnly: true, pageUrl: 'http://x/#/explore?q=a', generatedAt: '2026-11-10T00:00:00Z' }

  it('lists the words and links shown, each link with its sentence and citation', () => {
    const out = JSON.parse(graphToJson(nodes, edges, meta))
    expect(out.root).toEqual({ id: 'a', form: 'पानी', language: 'Hindi' })
    expect(out.open_data_only).toBe(true)
    expect(out.nodes).toHaveLength(2)
    expect(out.nodes[1]).toMatchObject({ form: 'पाणीअ', language: 'Prakrit', records: 2 })
    expect(out.links).toHaveLength(1)
    expect(out.links[0]).toMatchObject({
      type: 'inherited_form',
      label: 'inherited',
      sentence: 'पानी (Hindi) is inherited from पाणीअ (Prakrit)',
      citation: 'Wiktionary, “x”',
      source_id: 'wiktionary',
    })
  })

  it('carries the research-use notice and the page it came from', () => {
    const out = JSON.parse(graphToJson(nodes, edges, { ...meta, openOnly: false }))
    expect(out.open_data_only).toBe(false)
    expect(out.notice).toMatch(/research-use/)
    expect(out.page).toBe(meta.pageUrl)
  })
})

describe('buildSvg', () => {
  const nodes: SvgNode[] = [
    { id: 'a', x: 100, y: 100, width: 80, height: 40, lines: ['A & B <x>', 'Hindi'], fill: '#fde68a', dashed: false, root: true },
    { id: 'b', x: 300, y: 100, width: 80, height: 40, lines: ['*pal', 'Proto-Dravidian'], fill: '#e2e8f0', dashed: true, root: false },
  ]
  const edges: SvgEdge[] = [
    { id: 'e', from: [140, 100], to: [260, 100], mid: [200, 100], color: '#2563eb', line: 'solid', label: 'inherited', arrow: true },
    { id: 'f', from: [100, 120], to: [300, 120], mid: [200, 150], color: '#be123c', line: 'dotted', label: 'cognate', arrow: false },
  ]
  const svg = buildSvg(nodes, edges, { x1: 60, y1: 80, x2: 340, y2: 160 }, 'Linguistic DNA: A & B')

  it('is a standalone SVG sized to the drawing', () => {
    expect(svg.startsWith('<svg xmlns="http://www.w3.org/2000/svg"')).toBe(true)
    expect(svg).toContain('viewBox="44 64 312 112"')
    expect(svg.trimEnd().endsWith('</svg>')).toBe(true)
  })

  it('escapes text and keeps the title', () => {
    expect(svg).toContain('<title>Linguistic DNA: A &amp; B</title>')
    expect(svg).toContain('A &amp; B &lt;x&gt;')
    expect(svg).not.toContain('<x>')
  })

  it('encodes link type by colour, pattern and label, and direction by an arrowhead', () => {
    expect(svg).toContain('stroke="#2563eb"')
    expect(svg).toContain('marker-end="url(#arrow-2563eb)"')
    expect(svg).toContain('stroke-dasharray="2 4"') // the dotted cognate link
    expect(svg).toContain('>cognate</text>')
    expect(svg.match(/marker-end/g)).toHaveLength(1) // the undirected link has no arrowhead
  })

  it('passes a curved link through its midpoint and marks reconstructed words', () => {
    // quadratic control point that makes the curve pass through (200, 150): 2*mid - (from+to)/2
    expect(svg).toContain('Q200 180')
    expect(svg).toContain('stroke-dasharray="4 3"') // reconstructed node border
    expect(svg).toContain('font-style="italic"')
  })
})

describe('fileStem', () => {
  it('keeps letters of any script and falls back when there are none', () => {
    expect(fileStem('पानी')).toBe('linguistic-dna-पानी')
    expect(fileStem('*h₂éwh₂')).toBe('linguistic-dna-h₂éwh₂') // the asterisk drops out
    expect(fileStem('ಹಲ್ಲು')).toBe('linguistic-dna-ಹಲ್ಲು') // vowel signs and virama stay
    expect(fileStem('a b/c')).toBe('linguistic-dna-a-b-c')
    expect(fileStem('???')).toBe('linguistic-dna-graph')
    expect(fileStem(undefined)).toBe('linguistic-dna-graph')
  })
})
