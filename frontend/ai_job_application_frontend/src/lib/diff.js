/**
 * Word-level diff (longest common subsequence). Returns parts like
 * [{ type: 'same' | 'added' | 'removed', text }]. Whitespace is kept with each word.
 */
export function diffWords(before = '', after = '') {
  const a = before.match(/\S+\s*/g) ?? []
  const b = after.match(/\S+\s*/g) ?? []
  const key = (word) => word.trim().toLowerCase()
  // Dynamic programming table of LCS lengths (resume texts are short).
  const table = Array.from({ length: a.length + 1 }, () => new Array(b.length + 1).fill(0))
  for (let i = a.length - 1; i >= 0; i -= 1) {
    for (let j = b.length - 1; j >= 0; j -= 1) {
      table[i][j] =
        key(a[i]) === key(b[j])
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1])
    }
  }
  const parts = []
  const push = (type, text) => {
    const last = parts[parts.length - 1]
    if (last && last.type === type) last.text += text
    else parts.push({ type, text })
  }
  let i = 0
  let j = 0
  while (i < a.length && j < b.length) {
    if (key(a[i]) === key(b[j])) {
      push('same', b[j])
      i += 1
      j += 1
    } else if (table[i + 1][j] >= table[i][j + 1]) {
      push('removed', a[i])
      i += 1
    } else {
      push('added', b[j])
      j += 1
    }
  }
  while (i < a.length) push('removed', a[i++])
  while (j < b.length) push('added', b[j++])
  return parts
}
