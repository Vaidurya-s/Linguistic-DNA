// Pure functions that turn the API's graph records into what the canvas and table show.
import type { GraphEdge, GraphNode, LexemeSummary } from '../types/api.ts'

export type DisplayNode = GraphNode & { records: number }
export type DisplayGraph = {
  nodes: DisplayNode[]
  edges: GraphEdge[]
  alias: Map<string, string> // merged record id -> representative id
}

// Edges point from source to target, so each sentence reads "source <verb> target".
const VERBS: Record<string, string> = {
  inherited_form: 'is inherited from',
  derived_form: 'is derived from',
  borrowed_from: 'was borrowed from',
  has_component: 'contains',
  variant_of: 'is a variant of',
  etymon: 'comes from',
  related_form: 'is related to',
  contact_influence: 'was influenced by',
  cognate: 'is cognate with',
  calque_or_loan_translation: 'is a calque of',
  semantic_equivalent: 'has the same meaning as',
}

export function describeEdge(type: string, source?: LexemeSummary, target?: LexemeSummary): string {
  const name = (l?: LexemeSummary) => (l ? `${l.form.trim()} (${l.language_name})` : '?')
  return `${name(source)} ${VERBS[type] ?? 'is linked to'} ${name(target)}`
}

export const groupOf = (n: { group: string | null }) => n.group ?? 'other'

/** Identical records (same language, form and meaning, e.g. repeated dialect-survey rows)
 * are drawn as one node marked ×N. Display only: the records stay separate. */
export function mergeDuplicates(
  nodes: Iterable<GraphNode>,
  edges: Iterable<GraphEdge>,
  rootId: string | null,
): DisplayGraph {
  const groups = new Map<string, DisplayNode>()
  const alias = new Map<string, string>()
  for (const n of nodes) {
    const key = `${n.language_id}|${n.form.trim()}|${n.gloss ?? ''}`
    const existing = groups.get(key)
    if (existing && n.id !== rootId) {
      existing.records += 1
      alias.set(n.id, existing.id)
    } else if (existing) {
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
  const seen = new Map<string, GraphEdge>()
  for (const e of edges) {
    const source = resolve(e.source)
    const target = resolve(e.target)
    const key = `${source}|${target}|${e.type}`
    if (source !== target && !seen.has(key)) seen.set(key, { ...e, source, target })
  }
  return { nodes: [...groups.values()], edges: [...seen.values()], alias }
}

/** Keep only edges of the chosen types whose far end is in a chosen language group.
 * The root is always kept; nodes left without an edge disappear. */
export function applyFilters(
  graph: DisplayGraph,
  rootId: string,
  types: Set<string>,
  groups: Set<string>,
): DisplayGraph {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]))
  const visible = (id: string) => {
    const n = byId.get(id)
    return id === rootId || (n !== undefined && groups.has(groupOf(n)))
  }
  const edges = graph.edges.filter((e) => types.has(e.type) && visible(e.source) && visible(e.target))
  const keep = new Set([rootId, ...edges.flatMap((e) => [e.source, e.target])])
  return { ...graph, nodes: graph.nodes.filter((n) => keep.has(n.id)), edges }
}

/** Dense neighbourhoods: around each expanded node show at most `limit` neighbours (those in
 * a configured language group first, then the best connected), unless the user asked for all.
 * Returns the reduced graph and, per node, how many neighbours were hidden. */
export function capNeighbours(
  graph: DisplayGraph,
  rootId: string,
  expanded: Iterable<string>,
  limit: number,
  showAll: Set<string>,
): { graph: DisplayGraph; hidden: Map<string, number> } {
  const byId = new Map(graph.nodes.map((n) => [n.id, n]))
  const hidden = new Map<string, number>()
  const dropped = new Set<string>()
  const protectedIds = new Set([rootId, ...expanded])
  for (const hub of expanded) {
    if (showAll.has(hub)) continue
    const neighbours = graph.edges
      .filter((e) => e.source === hub || e.target === hub)
      .map((e) => (e.source === hub ? e.target : e.source))
      .filter((id, i, all) => all.indexOf(id) === i && !protectedIds.has(id))
      .map((id) => byId.get(id)!)
      .filter(Boolean)
    if (neighbours.length <= limit) continue
    neighbours.sort(
      (a, b) =>
        Number(groupOf(b) !== 'other') - Number(groupOf(a) !== 'other') ||
        b.degree - a.degree ||
        a.language_name.localeCompare(b.language_name),
    )
    const extra = neighbours.slice(limit)
    extra.forEach((n) => dropped.add(n.id))
    hidden.set(hub, extra.length)
  }
  if (dropped.size === 0) return { graph, hidden }
  const nodes = graph.nodes.filter((n) => !dropped.has(n.id))
  const edges = graph.edges.filter((e) => !dropped.has(e.source) && !dropped.has(e.target))
  return { graph: { ...graph, nodes, edges }, hidden }
}
