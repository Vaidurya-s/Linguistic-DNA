// Edge encoding combines colour, line pattern and a text label, so meaning never depends on
// colour alone (PROJECT_SPECIFICATION FR-08). Dashed lines are reserved for computed candidates.
export type EdgeStyle = { color: string; line: 'solid' | 'dotted' | 'dashed'; short: string }

export const EDGE_STYLES: Record<string, EdgeStyle> = {
  inherited_form: { color: '#2563eb', line: 'solid', short: 'inherited' },
  derived_form: { color: '#059669', line: 'solid', short: 'derived' },
  borrowed_from: { color: '#ea580c', line: 'solid', short: 'borrowed' },
  has_component: { color: '#7c3aed', line: 'solid', short: 'component' },
  variant_of: { color: '#64748b', line: 'dotted', short: 'variant' },
  related_form: { color: '#0891b2', line: 'dotted', short: 'related' },
  contact_influence: { color: '#db2777', line: 'dotted', short: 'influence' },
  orthographic_similarity_candidate: { color: '#a16207', line: 'dashed', short: 'spelling?' },
  phonetic_similarity_candidate: { color: '#a16207', line: 'dashed', short: 'sound?' },
}

export const FALLBACK_STYLE: EdgeStyle = { color: '#475569', line: 'solid', short: 'related' }

export const styleFor = (type: string) => EDGE_STYLES[type] ?? FALLBACK_STYLE

export const GROUP_COLORS: Record<string, string> = {
  'Indo-Aryan': '#fde68a',
  Dravidian: '#a7f3d0',
}
export const OTHER_GROUP_COLOR = '#e2e8f0'
