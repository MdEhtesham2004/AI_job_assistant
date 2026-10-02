import { Download } from 'lucide-react'

import { formatBytes } from '@/lib/format'

/** What a finished task produced: a file link, an AI answer, or an error. */
export function TaskResult({ task }) {
  if (task.status === 'failed' || (task.error && task.status === 'queued')) {
    return <p className="text-xs text-destructive">{task.error}</p>
  }
  const file = task.result?.file
  if (file) {
    return (
      <a
        href={file.download_url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
      >
        <Download className="size-4" aria-hidden="true" />
        {file.name} {file.size ? `(${formatBytes(file.size)})` : ''}
      </a>
    )
  }
  if (task.result?.answer) {
    return (
      <p className="text-xs text-muted-foreground">
        {task.result.model}: “{task.result.answer.message}” · ${task.result.cost_usd} ·{' '}
        {task.result.latency_ms} ms
      </p>
    )
  }
  return null
}
