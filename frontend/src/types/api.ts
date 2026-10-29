export type Language = {
  id: string
  name: string
  role: string
  group: string | null
  family_id: string | null
  family_name: string | null
  glottocode: string | null
  primary_script: string | null
  lexeme_count: number
  linked_count: number
}

export type LexemeSummary = {
  id: string
  form: string
  native_form: string | null
  language_id: string
  language_name: string
  group: string | null
  gloss: string | null
  reconstruction_status: 'attested' | 'reconstructed' | 'uncertain' | 'unknown'
  is_proto: boolean
}

export type SearchMatch = LexemeSummary & {
  match_type: 'exact' | 'native_exact' | 'loose' | 'spelling_candidate'
  score: number | null
  relationship_count: number
  duplicate_count: number
}

export type SearchResponse = {
  query: string
  normalized_query: string
  detected_script: string
  language_hints: string[]
  matches: SearchMatch[]
  spelling_candidates: SearchMatch[]
  warnings: string[]
}

export type Source = {
  id: string
  title: string
  reuse_status: string
  licence_name: string | null
  url: string | null
}

export type LexemeDetail = LexemeSummary & {
  transliteration: string | null
  phonemic: string | null
  source_status: string | null
  source_record_id: string
  source_citation: string | null
  source: Source | null
  concepts: { id: string; label: string }[]
}

export type GraphNode = LexemeSummary & { degree: number }

export type GraphEdge = {
  id: string
  source: string
  target: string
  type: string
  label: string
  namespace: string
  status: string
  direction: string
  source_id: string | null
  citation: string | null
}

export type GraphResponse = {
  root_lexeme_id: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  truncated: boolean
  warnings: string[]
}

export type RelationshipDetail = GraphEdge & {
  description: string
  original_label: string | null
  source_confidence: string | null
  method: string | null
  score: number | null
  notes: string | null
  source_lexeme: LexemeSummary
  target_lexeme: LexemeSummary
  evidence: { citation: string; locator: string | null; note: string | null; source: Source }[]
}
