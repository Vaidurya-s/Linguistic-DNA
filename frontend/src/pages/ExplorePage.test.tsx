import { render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ExplorePage from './ExplorePage.tsx'

describe('ExplorePage', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('reports the API as reachable when /health answers', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{"status":"ok"}')))
    render(<ExplorePage />)
    expect(await screen.findByText('ok')).toBeInTheDocument()
  })

  it('reports the API as unavailable when the request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    render(<ExplorePage />)
    expect(await screen.findByText('unavailable')).toBeInTheDocument()
  })
})
