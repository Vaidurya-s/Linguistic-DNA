import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { href } from '../app/router.ts'
import HomePage from './HomePage.tsx'
import MethodologyPage from './MethodologyPage.tsx'

const languages = [
  { id: 'hin', name: 'Hindi-Urdu', role: 'modern', group: 'Indo-Aryan', family_id: 'indo1319',
    family_name: 'Indo-European', glottocode: 'hind1269', primary_script: 'Deva',
    lexeme_count: 3404, linked_count: 1334 },
  { id: 'tam', name: 'Tamil', role: 'modern', group: 'Dravidian', family_id: 'drav1251',
    family_name: 'Dravidian', glottocode: 'tami1289', primary_script: 'Taml',
    lexeme_count: 2145, linked_count: 100 },
]

describe('router', () => {
  it('builds shareable explore links', () => {
    expect(href('/explore', { q: 'पानी', lang: undefined })).toBe(
      `#/explore?q=${encodeURIComponent('पानी')}`,
    )
  })
})

describe('pages', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('home page links example searches into the explorer and shows live counts', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve(new Response(JSON.stringify(languages)))))
    render(<HomePage />)
    const link = screen.getByRole('link', { name: /bidyut/ })
    expect(link.getAttribute('href')).toBe('#/explore?q=bidyut')
    expect(await screen.findByText('5,549')).toBeInTheDocument() // words indexed
  })

  it('methodology page credits every source, lists coverage and how to cite', async () => {
    const citations = {
      datasets: [
        { id: 'jambu', name: 'Jambu CLDF database', decision: 'RESEARCH USE', licence_name: null,
          citation: 'Arora, Aryaman, et al. 2023. Jambu.', licence_url: null, version: 'x',
          lexeme_count: 1000, relationship_count: 500 },
      ],
      works: [{ id: 'cdial', title: 'Turner, CDIAL', url: null, dataset_id: 'cdial', record_count: 42 }],
    }
    vi.stubGlobal('fetch', vi.fn((url: string) => Promise.resolve(
      new Response(JSON.stringify(url.includes('/citations') ? citations : languages)))))
    render(<MethodologyPage />)
    for (const name of [/Glottolog/, /Linguistic Survey of India/, /ASJP/, /Concepticon/,
                        /Wikidata Lexemes/, /Dakshina/, /Aksharantar/, /Jambu/, /CDIAL/, /DEDR/]) {
      expect(screen.getAllByText(name).length).toBeGreaterThan(0)
    }
    expect(await screen.findByText('Tamil')).toBeInTheDocument()
    expect(await screen.findByText('Arora, Aryaman, et al. 2023. Jambu.')).toBeInTheDocument()
    expect(screen.getByText('research use')).toBeInTheDocument()
  })
})
