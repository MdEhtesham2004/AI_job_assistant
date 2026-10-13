import { Badge } from '@/components/ui/badge'

import { QUALITY_LABELS, STATE_LABELS } from '../api'

// Phase 21: green is kept for match scores; a full description is the normal case.
const QUALITY_VARIANT = { complete: 'outline', partial: 'warning', missing: 'destructive' }
const STATE_VARIANT = {
  new: 'default',
  saved: 'default',
  analyzed: 'default',
  skipped: 'outline',
  archived: 'outline',
}

export function QualityBadge({ quality }) {
  return <Badge variant={QUALITY_VARIANT[quality]}>{QUALITY_LABELS[quality] ?? quality}</Badge>
}

export function JobStateBadge({ state }) {
  if (!state) return null
  return <Badge variant={STATE_VARIANT[state]}>{STATE_LABELS[state] ?? state}</Badge>
}

const RUN_STATUS = {
  queued: { variant: 'outline', label: 'Queued' },
  running: { variant: 'warning', label: 'Searching…' },
  succeeded: { variant: 'success', label: 'Done' },
  failed: { variant: 'destructive', label: 'Failed' },
}

export function RunStatusBadge({ status }) {
  const style = RUN_STATUS[status] ?? RUN_STATUS.queued
  return <Badge variant={style.variant}>{style.label}</Badge>
}
