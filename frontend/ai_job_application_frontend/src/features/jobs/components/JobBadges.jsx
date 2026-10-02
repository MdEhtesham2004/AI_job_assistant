import { Badge } from '@/components/ui/badge'

import { QUALITY_LABELS, STATE_LABELS } from '../api'

const QUALITY_VARIANT = { complete: 'success', partial: 'warning', missing: 'destructive' }
const STATE_VARIANT = {
  new: 'default',
  saved: 'success',
  analyzed: 'success',
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
