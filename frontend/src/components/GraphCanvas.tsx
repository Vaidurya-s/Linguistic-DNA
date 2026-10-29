import cytoscape, { type Core, type ElementDefinition } from 'cytoscape'
import { useEffect, useRef } from 'react'
import type { GraphEdge } from '../types/api.ts'
import type { DisplayNode } from './graphModel.ts'
import { GROUP_COLORS, OTHER_GROUP_COLOR, styleFor } from './edgeStyles.ts'

export type Selection = { kind: 'node' | 'edge'; id: string } | null

type Props = {
  nodes: DisplayNode[]
  edges: GraphEdge[]
  rootId: string
  selection: Selection
  onSelect: (selection: Selection) => void
  onExpand: (nodeId: string) => void
}


const nodeLabel = (n: DisplayNode) =>
  `${n.native_form && n.native_form !== n.form ? `${n.native_form} · ` : ''}${n.form}` +
  `${n.records > 1 ? ` ×${n.records}` : ''}\n${n.language_name}`

function toElements(nodes: DisplayNode[], edges: GraphEdge[], rootId: string): ElementDefinition[] {
  return [
    ...nodes.map((n) => ({
      group: 'nodes' as const,
      data: {
        id: n.id,
        label: nodeLabel(n),
        color: (n.group && GROUP_COLORS[n.group]) || OTHER_GROUP_COLOR,
        reconstructed: n.reconstruction_status === 'reconstructed' ? 1 : 0,
        root: n.id === rootId ? 1 : 0,
      },
    })),
    ...edges.map((e) => {
      const s = styleFor(e.type)
      return {
        group: 'edges' as const,
        data: {
          id: e.id,
          source: e.source,
          target: e.target,
          label: s.short,
          color: s.color,
          line: s.line,
          arrow: e.direction === 'directed' ? 'triangle' : 'none',
        },
      }
    }),
  ]
}

export default function GraphCanvas({ nodes, edges, rootId, selection, onSelect, onExpand }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const cy = useRef<Core | null>(null)
  const handlers = useRef({ onSelect, onExpand })
  useEffect(() => {
    handlers.current = { onSelect, onExpand }
  }, [onSelect, onExpand])

  useEffect(() => {
    if (!container.current) return
    const instance = cytoscape({
      container: container.current,
      wheelSensitivity: 0.3,
      style: [
        {
          selector: 'node',
          style: {
            label: 'data(label)',
            'text-wrap': 'wrap',
            'text-valign': 'center',
            'font-size': 13,
            'background-color': 'data(color)',
            'border-width': 1,
            'border-color': '#334155',
            shape: 'round-rectangle',
            width: 'label',
            height: 'label',
            padding: '8px',
          },
        },
        { selector: 'node[reconstructed = 1]', style: { 'border-style': 'dashed', 'font-style': 'italic' } },
        { selector: 'node[root = 1]', style: { 'border-width': 3, 'border-color': '#0f172a' } },
        {
          selector: 'edge',
          style: {
            width: 2,
            'line-color': 'data(color)',
            'line-style': 'data(line)' as never,
            'target-arrow-color': 'data(color)',
            'target-arrow-shape': 'data(arrow)' as never,
            'curve-style': 'bezier',
            label: 'data(label)',
            'font-size': 10,
            color: '#334155',
            'text-background-color': '#ffffff',
            'text-background-opacity': 0.85,
            'text-background-padding': '2px',
          },
        },
        { selector: ':selected', style: { 'overlay-color': '#2563eb', 'overlay-opacity': 0.15 } },
      ],
    })
    instance.on('tap', 'node', (evt) => handlers.current.onSelect({ kind: 'node', id: evt.target.id() }))
    instance.on('tap', 'edge', (evt) => handlers.current.onSelect({ kind: 'edge', id: evt.target.id() }))
    instance.on('dbltap', 'node', (evt) => handlers.current.onExpand(evt.target.id()))
    instance.on('tap', (evt) => {
      if (evt.target === instance) handlers.current.onSelect(null)
    })
    cy.current = instance
    const observer = new ResizeObserver(() => {
      instance.resize()
      instance.fit(undefined, 16)
      if (instance.zoom() < 0.6) {
        instance.zoom(0.6)
        instance.center()
      }
    })
    observer.observe(container.current)
    if (import.meta.env.DEV) {
      // Lets browser automation (screenshots, e2e) find node positions on the canvas.
      ;(window as unknown as { __lsgCy?: Core }).__lsgCy = instance
    }
    return () => {
      observer.disconnect()
      instance.destroy()
    }
  }, [])

  useEffect(() => {
    const instance = cy.current
    if (!instance) return
    instance.batch(() => {
      instance.elements().remove()
      instance.add(toElements(nodes, edges, rootId))
    })
    // Concentric rings: hubs (usually the etymon) in the middle; leaves are spread over three
    // outer rings so labels stay readable.
    const order = new Map(nodes.map((n, i) => [n.id, i]))
    instance
      .layout({
        name: 'concentric',
        concentric: (n: cytoscape.NodeSingular) => {
          const degree = n.degree(false)
          if (n.id() === rootId || degree > 1) return 10 + degree
          return 3 - ((order.get(n.id()) ?? 0) % 3)
        },
        levelWidth: () => 1,
        minNodeSpacing: 10,
        avoidOverlap: true,
        padding: 16,
        animate: false,
      } as cytoscape.LayoutOptions)
      .run()
    if (instance.zoom() < 0.6) {
      instance.zoom(0.6)
      instance.center()
    } else if (instance.zoom() > 1.3) {
      instance.zoom(1.3)
      instance.center()
    }
  }, [nodes, edges, rootId])

  useEffect(() => {
    const instance = cy.current
    if (!instance) return
    instance.elements().unselect()
    if (selection) instance.getElementById(selection.id).select()
  }, [selection, nodes, edges])

  return (
    <div
      ref={container}
      className="h-[440px] w-full lg:h-[600px] rounded-lg border border-slate-300 bg-white"
      role="img"
      aria-label="Relationship graph. The table below lists the same relationships."
      data-testid="graph-canvas"
    />
  )
}
