import type {
  GraphResponse,
  Language,
  LexemeDetail,
  RelationshipDetail,
  SearchResponse,
} from '../types/api.ts'

const API_BASE = import.meta.env.VITE_API_BASE ?? '/api/v1'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

export async function getJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    throw new ApiError(response.status, `${response.status} ${response.statusText}`)
  }
  return (await response.json()) as T
}

const qs = (params: Record<string, string | number | undefined>) => {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.set(key, String(value))
  }
  return search.toString()
}

export type Health = { status: string }

export const getHealth = () => getJson<Health>('/health')

export const getLanguages = () => getJson<Language[]>('/languages')

export const searchLexemes = (q: string, languageId?: string) =>
  getJson<SearchResponse>(`/search?${qs({ q, language_id: languageId, limit: 20 })}`)

export const getLexeme = (id: string) => getJson<LexemeDetail>(`/lexemes/${encodeURIComponent(id)}`)

export const getGraph = (id: string) =>
  getJson<GraphResponse>(`/graph/${encodeURIComponent(id)}?${qs({ depth: 1, limit_nodes: 60 })}`)

export const getRelationship = (id: string) =>
  getJson<RelationshipDetail>(`/relationships/${encodeURIComponent(id)}`)
