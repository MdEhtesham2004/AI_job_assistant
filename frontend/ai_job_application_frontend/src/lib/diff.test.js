import { describe, expect, it } from 'vitest'

import { diffWords } from './diff'

describe('diffWords', () => {
  it('marks added and removed words', () => {
    expect(diffWords('Built a payments app', 'Built and shipped a payments app')).toEqual([
      { type: 'same', text: 'Built ' },
      { type: 'added', text: 'and shipped ' },
      { type: 'same', text: 'a payments app' },
    ])
    expect(diffWords('Mobile developer', 'React Native developer')).toEqual([
      { type: 'removed', text: 'Mobile ' },
      { type: 'added', text: 'React Native ' },
      { type: 'same', text: 'developer' },
    ])
  })

  it('handles empty text', () => {
    expect(diffWords('', 'New text')).toEqual([{ type: 'added', text: 'New text' }])
    expect(diffWords(undefined, undefined)).toEqual([])
  })
})
