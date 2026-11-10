// Display-only helpers: the importer stores Wiktionary template markup such as "{{desc}}" as the
// source label and in citations. The data stays as it is; readers see plain English.

const WIKTIONARY_LABEL: Record<string, string> = {
  desc: 'Wiktionary descendants list',
  inh: 'Wiktionary: inherited',
  'inh+': 'Wiktionary: inherited',
  bor: 'Wiktionary: borrowed',
  'bor+': 'Wiktionary: borrowed',
  lbor: 'Wiktionary: borrowed',
  obor: 'Wiktionary: borrowed',
  ubor: 'Wiktionary: borrowed',
  der: 'Wiktionary: derived',
  'der+': 'Wiktionary: derived',
  cog: 'Wiktionary: cognate',
  clq: 'Wiktionary: calque',
  cal: 'Wiktionary: calque',
  calque: 'Wiktionary: calque',
  sl: 'Wiktionary: calque',
  af: 'Wiktionary: word formation',
  affix: 'Wiktionary: word formation',
  compound: 'Wiktionary: word formation',
  prefix: 'Wiktionary: word formation',
  suffix: 'Wiktionary: word formation',
  confix: 'Wiktionary: word formation',
  etymon: 'Wiktionary: etymology note',
}

// "{{name}}", optionally followed by a variety such as " (Old Church Slavonic)".
const LABEL_RE = /^\{\{\s*([^{}|]+?)\s*\}\}(\s*\(.*\))?$/
// "({{name}})" inside a citation sentence.
const CITATION_RE = /\s*\(\{\{\s*([^{}|]+?)\s*\}\}\)/g

/** Plain-English phrase for a raw Wiktionary template label; anything else is returned unchanged. */
export function plainSourceLabel(raw: string): string {
  const m = LABEL_RE.exec(raw.trim())
  const phrase = m ? WIKTIONARY_LABEL[m[1].toLowerCase()] : undefined
  return m && phrase ? phrase + (m[2] ?? '') : raw
}

/** Replaces each "({{name}})" in a citation with the plain phrase; the rest (URL, locator) is kept. */
export function plainCitation(raw: string): string {
  return raw.replace(CITATION_RE, (whole, name: string) => {
    const phrase = WIKTIONARY_LABEL[name.toLowerCase()]
    if (!phrase) return whole
    // the citation already says "descendants", so the template adds nothing there
    if (name.toLowerCase() === 'desc') return ''
    return ` (${phrase.slice('Wiktionary: '.length)})`
  })
}
