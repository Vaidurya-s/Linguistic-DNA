import { describe, expect, it } from 'vitest'
import { plainCitation, plainSourceLabel } from './sourceLabels.ts'

describe('plainSourceLabel', () => {
  it('turns known Wiktionary templates into plain English', () => {
    expect(plainSourceLabel('{{desc}}')).toBe('Wiktionary descendants list')
    expect(plainSourceLabel('{{inh}}')).toBe('Wiktionary: inherited')
    expect(plainSourceLabel('{{inh+}}')).toBe('Wiktionary: inherited')
    expect(plainSourceLabel('{{bor+}}')).toBe('Wiktionary: borrowed')
    expect(plainSourceLabel('{{ubor}}')).toBe('Wiktionary: borrowed')
    expect(plainSourceLabel('{{der+}}')).toBe('Wiktionary: derived')
    expect(plainSourceLabel('{{cog}}')).toBe('Wiktionary: cognate')
    expect(plainSourceLabel('{{calque}}')).toBe('Wiktionary: calque')
    expect(plainSourceLabel('{{sl}}')).toBe('Wiktionary: calque')
    expect(plainSourceLabel('{{confix}}')).toBe('Wiktionary: word formation')
    expect(plainSourceLabel('{{etymon}}')).toBe('Wiktionary: etymology note')
  })
  it('keeps a trailing variety', () => {
    expect(plainSourceLabel('{{inh}} (Old Church Slavonic)')).toBe(
      'Wiktionary: inherited (Old Church Slavonic)',
    )
  })
  it('passes unknown templates through unchanged', () => {
    expect(plainSourceLabel('{{mystery}}')).toBe('{{mystery}}')
  })
  it('passes labels from other datasets through unchanged', () => {
    for (const label of ['DPD derived_from', 'P5191 derived from lexeme', 'CDIAL 1234', '']) {
      expect(plainSourceLabel(label)).toBe(label)
    }
  })
})

describe('plainCitation', () => {
  it('replaces the template in a citation and keeps the rest', () => {
    expect(plainCitation('Wiktionary, “вдова”, descendants ({{desc}})')).toBe(
      'Wiktionary, “вдова”, descendants',
    )
    expect(plainCitation('Wiktionary, “x”, etymology ({{bor+}}) https://en.wiktionary.org/wiki/x')).toBe(
      'Wiktionary, “x”, etymology (borrowed) https://en.wiktionary.org/wiki/x',
    )
  })
  it('leaves unknown templates and other citations unchanged', () => {
    expect(plainCitation('etymology ({{nope}})')).toBe('etymology ({{nope}})')
    expect(plainCitation('Turner, CDIAL (1962-1966), entry 5678')).toBe(
      'Turner, CDIAL (1962-1966), entry 5678',
    )
  })
})
