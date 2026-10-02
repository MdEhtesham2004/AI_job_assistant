import { Badge } from '@/components/ui/badge'

import { scoreTone } from '../score'

const STYLES = {
  pending: { variant: 'warning', label: 'Reading…' },
  parsed: { variant: 'success', label: 'Parsed' },
  failed: { variant: 'destructive', label: 'Parse failed' },
}

export function ParseStatusBadge({ status }) {
  const style = STYLES[status] ?? STYLES.pending
  return <Badge variant={style.variant}>{style.label}</Badge>
}

export function ScoreBadge({ score }) {
  if (score === null || score === undefined) return null
  return <Badge variant={scoreTone(score)}>ATS {score}</Badge>
}
