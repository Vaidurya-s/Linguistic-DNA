import { describe, expect, it } from 'vitest'
import type { GraphEdge, GraphNode } from '../types/api.ts'
import { applyFilters, capNeighbours, describeEdge, mergeDuplicates } from './graphModel.ts'

const node = (id: string, over: Partial<GraphNode> = {}): GraphNode => ({
  id, form: id, native_form: null, language_id: 'hin', language_name: 'Hindi-Urdu',
  group: 'Indo-Aryan', gloss: 'tooth', reconstruction_status: 'attested', is_proto: false,
  form_kind: 'word', degree: 1, ...over,
})
const edge = (id: string, source: string, target: string, type = 'inherited_form'): GraphEdge => ({
  id, source, target, type, label: type, namespace: 'lexical', status: 'documented',
  direction: 'directed', source_id: 'cdial', citation: 'CDIAL',
})

describe('describeEdge', () => {
  it('reads in the direction of the arrow', () => {
    const child = node('a', { form: 'dānt', language_name: 'Punjabi' })
    const parent = node('b', { form: 'dánta', language_name: 'Old Indo-Aryan' })
    expect(describeEdge('inherited_form', child, parent)).toBe(
      'dānt (Punjabi) is inherited from dánta (Old Indo-Aryan)',
    )
    expect(describeEdge('borrowed_from', child, parent)).toContain('was borrowed from')
    expect(describeEdge('has_component', child, parent)).toContain('contains')
  })
})

describe('mergeDuplicates', () => {
  it('draws identical records as one node and keeps the root as representative', () => {
    const nodes = [node('x1', { form: 'dāt' }), node('root', { form: 'dāt' }), node('p', { form: 'dánta' })]
    const g = mergeDuplicates(nodes, [edge('e1', 'x1', 'p'), edge('e2', 'root', 'p')], 'root')
    expect(g.nodes.map((n) => [n.id, n.records])).toEqual([['root', 2], ['p', 1]])
    expect(g.edges).toHaveLength(1)
    expect(g.alias.get('x1')).toBe('root')
  })
})

describe('applyFilters', () => {
  const g = mergeDuplicates(
    [node('r'), node('p'), node('t', { group: 'Dravidian', form: 'pal' })],
    [edge('e1', 'r', 'p'), edge('e2', 'r', 't', 'borrowed_from')],
    'r',
  )
  it('hides edge types that are switched off', () => {
    const f = applyFilters(g, 'r', new Set(['inherited_form']), new Set(['Indo-Aryan', 'Dravidian']))
    expect(f.edges.map((e) => e.id)).toEqual(['e1'])
    expect(f.nodes.map((n) => n.id).sort()).toEqual(['p', 'r'])
  })
  it('hides language groups but always keeps the root', () => {
    const f = applyFilters(g, 'r', new Set(['inherited_form', 'borrowed_from']), new Set(['Dravidian']))
    expect(f.nodes.map((n) => n.id).sort()).toEqual(['r', 't'])
  })
})

describe('capNeighbours', () => {
  const leaves = Array.from({ length: 30 }, (_, i) =>
    node(`l${i}`, { form: `f${i}`, group: i < 5 ? null : 'Indo-Aryan', degree: i }))
  const g = mergeDuplicates([node('hub'), ...leaves], leaves.map((l, i) => edge(`e${i}`, l.id, 'hub')), 'hub')
  it('keeps the most informative neighbours and reports how many were hidden', () => {
    const { graph, hidden } = capNeighbours(g, 'hub', ['hub'], 10, new Set())
    expect(graph.nodes).toHaveLength(11)
    expect(hidden.get('hub')).toBe(20)
    expect(graph.nodes.some((n) => n.group === null)).toBe(false) // 'other' group goes last
  })
  it('keeps the hub\'s ancestors and cognates before the words that contain it', () => {
    const parts = Array.from({ length: 12 }, (_, i) => node(`c${i}`, { degree: 50 }))
    const ancestors = [node('proto', { group: null, degree: 1 }), node('cog', { group: null })]
    const h = mergeDuplicates(
      [node('hub'), ...parts, ...ancestors],
      [
        ...parts.map((c, i) => edge(`k${i}`, c.id, 'hub', 'has_component')),
        edge('a', 'hub', 'proto', 'etymon'),
        edge('b', 'cog', 'hub', 'cognate'),
      ],
      'hub',
    )
    const { graph } = capNeighbours(h, 'hub', ['hub'], 5, new Set())
    const ids = graph.nodes.map((n) => n.id)
    expect(ids).toContain('proto')
    expect(ids).toContain('cog')
    expect(ids).toHaveLength(6)
  })
  it('shows everything once the user asks', () => {
    const { graph, hidden } = capNeighbours(g, 'hub', ['hub'], 10, new Set(['hub']))
    expect(graph.nodes).toHaveLength(31)
    expect(hidden.size).toBe(0)
  })
})
