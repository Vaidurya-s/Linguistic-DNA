import { useEffect, useState } from 'react'
import { getLexeme, getRelationship } from '../api/client.ts'
import type { LexemeDetail, RelationshipDetail, Source } from '../types/api.ts'
import type { Selection } from './GraphCanvas.tsx'

const REUSE_LABEL: Record<string, string> = {
  approved: 'approved for reuse',
  attribution_required: 'reusable with attribution',
  permission_required: 'permission required — not redistributable yet',
  unknown: 'licence not yet reviewed',
  excluded: 'excluded',
}

function SourceLine({ source }: { source: Source | null }) {
  if (!source) return <span className="text-slate-500">no source recorded</span>
  return (
    <span>
      {source.url ? (
        <a className="text-blue-700 underline" href={source.url} target="_blank" rel="noreferrer">
          {source.title}
        </a>
      ) : (
        source.title
      )}{' '}
      <span className="text-xs text-slate-500">({REUSE_LABEL[source.reuse_status] ?? source.reuse_status})</span>
    </span>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[7.5rem_1fr] gap-2 py-1 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className="min-w-0 break-words">{children}</dd>
    </div>
  )
}

type Props = { selection: Selection; onExpand: (id: string) => void; expanded: Set<string> }

export default function DetailsPanel({ selection, onExpand, expanded }: Props) {
  const [lexeme, setLexeme] = useState<LexemeDetail | null>(null)
  const [rel, setRel] = useState<RelationshipDetail | null>(null)
  const [error, setError] = useState<string | null>(null)

  // The parent remounts this panel (via `key`) when the selection changes, so state starts empty.
  useEffect(() => {
    if (!selection) return
    const request =
      selection.kind === 'node'
        ? getLexeme(selection.id).then(setLexeme)
        : getRelationship(selection.id).then(setRel)
    request.catch((e: Error) => setError(e.message))
  }, [selection])

  if (!selection) {
    return (
      <p className="text-sm text-slate-600">
        Select a word or a link in the graph to see its source. Double-click a word (or use
        “Show connections”) to expand it.
      </p>
    )
  }
  if (error) return <p className="text-sm text-red-700">Could not load details: {error}</p>
  if (lexeme) {
    return (
      <section aria-label="Word details">
        <h2 className="text-xl font-semibold">
          {lexeme.native_form && lexeme.native_form !== lexeme.form && <span className="mr-2">{lexeme.native_form}</span>}
          <span className={lexeme.reconstruction_status === 'reconstructed' ? 'italic' : ''}>{lexeme.form}</span>
        </h2>
        <p className="text-sm text-slate-600">{lexeme.language_name}</p>
        <dl className="mt-3">
          <Field label="Meaning">{lexeme.gloss ?? <span className="text-slate-500">no gloss</span>}</Field>
          <Field label="Status">
            {lexeme.reconstruction_status === 'reconstructed'
              ? 'reconstructed form — not directly attested'
              : lexeme.reconstruction_status}
          </Field>
          {lexeme.phonemic && <Field label="Transcription">{lexeme.phonemic}</Field>}
          {lexeme.concepts.length > 0 && (
            <Field label="Concepts">{lexeme.concepts.map((c) => c.label.toLowerCase()).join(', ')}</Field>
          )}
          <Field label="Source"><SourceLine source={lexeme.source} /></Field>
          {lexeme.source_citation && <Field label="Citation">{lexeme.source_citation}</Field>}
          <Field label="Record">Jambu {lexeme.source_record_id}</Field>
        </dl>
        <button
          type="button"
          className="mt-3 rounded-md bg-slate-900 px-3 py-1.5 text-sm text-white disabled:opacity-40"
          onClick={() => onExpand(lexeme.id)}
          disabled={expanded.has(lexeme.id)}
        >
          {expanded.has(lexeme.id) ? 'Connections shown' : 'Show connections'}
        </button>
      </section>
    )
  }
  if (rel) {
    return (
      <section aria-label="Relationship evidence">
        <h2 className="text-xl font-semibold">{rel.label}</h2>
        <p className="mt-1 text-sm">
          <strong>{rel.source_lexeme.form}</strong> ({rel.source_lexeme.language_name}) →{' '}
          <strong>{rel.target_lexeme.form}</strong> ({rel.target_lexeme.language_name})
        </p>
        <p className="mt-1 text-sm text-slate-600">{rel.description}</p>
        <dl className="mt-3">
          <Field label="Status">
            <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-emerald-900">{rel.status}</span>
            {rel.status === 'documented' && ' — stated by a source, not computed'}
          </Field>
          <Field label="Direction">{rel.direction}</Field>
          {rel.source_confidence && <Field label="Confidence">{rel.source_confidence} (as stated by the source)</Field>}
          {rel.original_label && <Field label="Source label">{rel.original_label}</Field>}
          {rel.notes && <Field label="Note">{rel.notes}</Field>}
        </dl>
        <h3 className="mt-3 text-sm font-semibold">Evidence</h3>
        <ul className="mt-1 space-y-2">
          {rel.evidence.map((e, i) => (
            <li key={i} className="rounded border border-slate-200 p-2 text-sm">
              <div>
                <SourceLine source={e.source} />
              </div>
              <div className="text-slate-600">
                {e.citation}
                {e.locator && <> · {e.locator}</>}
              </div>
              {e.note && <div className="mt-1 text-xs text-slate-500">{e.note}</div>}
            </li>
          ))}
        </ul>
      </section>
    )
  }
  return <p className="text-sm text-slate-500">Loading…</p>
}
