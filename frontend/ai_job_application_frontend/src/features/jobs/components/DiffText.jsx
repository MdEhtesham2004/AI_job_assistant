import { diffWords } from '@/lib/diff'

/** `after` with words added since `before` highlighted (removed words shown struck out). */
export function DiffText({ before, after, showRemoved = false }) {
  return (
    <>
      {diffWords(before ?? '', after ?? '').map((part, index) => {
        if (part.type === 'added') {
          return (
            <mark key={index} className="rounded bg-success/20 px-0.5 text-foreground">
              {part.text}
            </mark>
          )
        }
        if (part.type === 'removed') {
          return showRemoved ? (
            <del key={index} className="text-muted-foreground">
              {part.text}
            </del>
          ) : null
        }
        return <span key={index}>{part.text}</span>
      })}
    </>
  )
}
