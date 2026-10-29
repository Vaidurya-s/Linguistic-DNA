// A minimal hash router: the app stays a static bundle that any static host can serve.
import { useEffect, useState } from 'react'

export type Route = { path: string; params: URLSearchParams }

function parse(hash: string): Route {
  const raw = hash.replace(/^#/, '') || '/'
  const [path, query = ''] = raw.split('?')
  return { path: path || '/', params: new URLSearchParams(query) }
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parse(window.location.hash))
  useEffect(() => {
    const onChange = () => {
      setRoute(parse(window.location.hash))
      window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', onChange)
    return () => window.removeEventListener('hashchange', onChange)
  }, [])
  return route
}

export function href(path: string, params?: Record<string, string | undefined>): string {
  const search = new URLSearchParams()
  Object.entries(params ?? {}).forEach(([k, v]) => v && search.set(k, v))
  const qs = search.toString()
  return `#${path}${qs ? `?${qs}` : ''}`
}

/** Update the query part of the current route without adding a history entry per keystroke. */
export function replaceParams(path: string, params: Record<string, string | undefined>) {
  window.history.replaceState(null, '', href(path, params))
}
