// Downloads of the graph that is on screen: JSON (the words and links with their citations),
// SVG (a vector drawing built from the canvas geometry) and PNG (a bitmap from the canvas).
// The builders are pure so they can be tested without a browser canvas.
import type { GraphEdge } from '../types/api.ts'
import { styleFor } from './edgeStyles.ts'
import { describeEdge, type DisplayNode } from './graphModel.ts'

export type ExportMeta = {
  rootId: string
  openOnly: boolean
  pageUrl: string
  generatedAt: string
}

const NOTICE =
  'Every link comes from the source named in its citation. Records from research-use sources ' +
  'are for research and must be cited, not redistributed; turn on "Open data only" on the site ' +
  'to export only openly licensed records. Licences and how to cite: the Data & methodology page.'

/** The words and links shown, as JSON text: one entry per drawn word and link, with the
 * sentence the site shows for each link and its citation. */
export function graphToJson(nodes: DisplayNode[], edges: GraphEdge[], meta: ExportMeta): string {
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const root = byId.get(meta.rootId)
  return JSON.stringify(
    {
      generated_at: meta.generatedAt,
      page: meta.pageUrl,
      root: root ? { id: root.id, form: root.form, language: root.language_name } : { id: meta.rootId },
      open_data_only: meta.openOnly,
      notice: NOTICE,
      nodes: nodes.map((n) => ({
        id: n.id,
        form: n.form,
        native_form: n.native_form,
        language_id: n.language_id,
        language: n.language_name,
        gloss: n.gloss,
        reconstruction_status: n.reconstruction_status,
        form_kind: n.form_kind,
        records: n.records,
      })),
      links: edges.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        type: e.type,
        label: styleFor(e.type).short,
        direction: e.direction,
        status: e.status,
        sentence: describeEdge(e.type, byId.get(e.source), byId.get(e.target)),
        source_id: e.source_id,
        citation: e.citation,
      })),
    },
    null,
    2,
  )
}

type Point = [number, number]

export type SvgNode = {
  id: string
  x: number // centre, in the canvas's own coordinates
  y: number
  width: number
  height: number
  lines: string[]
  fill: string
  dashed: boolean // reconstructed forms
  root: boolean
}

export type SvgEdge = {
  id: string
  from: Point
  to: Point
  mid: Point // the point the drawn curve passes through at its middle
  color: string
  line: 'solid' | 'dotted' | 'dashed'
  label: string
  arrow: boolean
}

export type SvgBounds = { x1: number; y1: number; x2: number; y2: number }

const FONT = 'ui-sans-serif, system-ui, sans-serif'
const PAD = 16

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
const num = (n: number) => String(Math.round(n * 10) / 10)

const DASH: Record<SvgEdge['line'], string> = { solid: '', dotted: ' stroke-dasharray="2 4"', dashed: ' stroke-dasharray="6 4"' }

/** A standalone SVG of the graph. Curves are drawn as quadratic Béziers through each link's
 * midpoint, which matches the canvas for both straight and curved links. */
export function buildSvg(nodes: SvgNode[], edges: SvgEdge[], bounds: SvgBounds, title: string): string {
  const x = bounds.x1 - PAD
  const y = bounds.y1 - PAD
  const w = bounds.x2 - bounds.x1 + 2 * PAD
  const h = bounds.y2 - bounds.y1 + 2 * PAD
  const colors = [...new Set(edges.filter((e) => e.arrow).map((e) => e.color))]
  const markerId = (c: string) => `arrow-${c.replace(/[^0-9a-z]/gi, '')}`
  const out: string[] = []
  out.push(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${num(x)} ${num(y)} ${num(w)} ${num(h)}" ` +
      `width="${num(w)}" height="${num(h)}" font-family="${FONT}">`,
    `<title>${esc(title)}</title>`,
    '<desc>Linguistic DNA relationship graph. Every link is drawn from a cited source.</desc>',
    `<rect x="${num(x)}" y="${num(y)}" width="${num(w)}" height="${num(h)}" fill="#ffffff"/>`,
  )
  if (colors.length) {
    out.push('<defs>')
    for (const c of colors) {
      out.push(
        `<marker id="${markerId(c)}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" ` +
          `markerHeight="5" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 z" fill="${esc(c)}"/></marker>`,
      )
    }
    out.push('</defs>')
  }
  for (const e of edges) {
    const cx = 2 * e.mid[0] - (e.from[0] + e.to[0]) / 2
    const cy = 2 * e.mid[1] - (e.from[1] + e.to[1]) / 2
    out.push(
      `<path d="M${num(e.from[0])} ${num(e.from[1])} Q${num(cx)} ${num(cy)} ${num(e.to[0])} ${num(e.to[1])}" ` +
        `fill="none" stroke="${esc(e.color)}" stroke-width="2"${DASH[e.line]}` +
        `${e.arrow ? ` marker-end="url(#${markerId(e.color)})"` : ''}/>`,
    )
  }
  for (const e of edges) {
    out.push(
      `<text x="${num(e.mid[0])}" y="${num(e.mid[1])}" font-size="10" fill="#334155" text-anchor="middle" ` +
        `dominant-baseline="central" stroke="#ffffff" stroke-width="4" paint-order="stroke">${esc(e.label)}</text>`,
    )
  }
  for (const n of nodes) {
    const stroke = n.root ? '#0f172a' : '#334155'
    out.push(
      `<rect x="${num(n.x - n.width / 2)}" y="${num(n.y - n.height / 2)}" width="${num(n.width)}" ` +
        `height="${num(n.height)}" rx="6" fill="${esc(n.fill)}" stroke="${stroke}" stroke-width="${n.root ? 3 : 1}"` +
        `${n.dashed ? ' stroke-dasharray="4 3"' : ''}/>`,
    )
    const lineHeight = 15
    const top = n.y - ((n.lines.length - 1) * lineHeight) / 2
    n.lines.forEach((line, i) => {
      out.push(
        `<text x="${num(n.x)}" y="${num(top + i * lineHeight)}" font-size="13" fill="#0f172a" ` +
          `text-anchor="middle" dominant-baseline="central"${n.dashed && i === 0 ? ' font-style="italic"' : ''}>${esc(line)}</text>`,
      )
    })
  }
  out.push('</svg>')
  return out.join('\n')
}

/** A file name stem from the root word: letters, combining marks (vowel signs) and digits of
 * any script, else the fallback. */
export function fileStem(form: string | undefined): string {
  const slug = (form ?? '')
    .normalize('NFC')
    .replace(/[^\p{L}\p{M}\p{N}]+/gu, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)
  return `linguistic-dna-${slug || 'graph'}`
}

/** Offer a file to the browser's download. */
export function downloadFile(name: string, href: string): void {
  const a = document.createElement('a')
  a.href = href
  a.download = name
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export function downloadText(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }))
  downloadFile(name, url)
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

/** What the canvas can hand over; set by GraphCanvas while it is mounted. */
export type GraphExporter = { svg: (title: string) => string; png: () => string }
