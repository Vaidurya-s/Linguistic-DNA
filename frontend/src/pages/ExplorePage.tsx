import { useEffect, useState } from 'react'
import { getHealth } from '../api/client.ts'

type ApiState = 'checking' | 'ok' | 'unavailable'

export default function ExplorePage() {
  const [api, setApi] = useState<ApiState>('checking')

  useEffect(() => {
    getHealth()
      .then(() => setApi('ok'))
      .catch(() => setApi('unavailable'))
  }, [])

  return (
    <main className="mx-auto max-w-3xl px-4 py-12 text-slate-900 dark:text-slate-100">
      <h1 className="text-3xl font-semibold">Language Similarity Graph</h1>
      <p className="mt-3 text-slate-600 dark:text-slate-300">
        Explore documented relationships between words across Indian languages. Search and the
        graph view arrive in the next milestones.
      </p>
      <p className="mt-6 text-sm" role="status">
        API: <span data-testid="api-status">{api}</span>
      </p>
    </main>
  )
}
