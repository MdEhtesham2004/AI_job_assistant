import { Bot, FileText, RefreshCw, TriangleAlert } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ServiceRow } from '@/features/system/components/ServiceRow'
import { SERVICE_ORDER, describeCheck } from '@/features/system/describeCheck'
import { HEALTH_REFRESH_MS, useSystemStatus } from '@/features/system/hooks/useHealth'
import { tasksApi, taskLabel } from '@/features/tasks/api'
import { ProgressBar, TaskStatusBadge } from '@/features/tasks/components/TaskStatusBadge'
import { TaskResult } from '@/features/tasks/components/TaskResult'
import { useStartTask, useTaskPolling } from '@/features/tasks/hooks'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const DIAGNOSTICS = [
  {
    key: 'pdf',
    label: 'Generate test PDF',
    icon: FileText,
    start: tasksApi.createTestPdf,
    hint: 'Worker → Gotenberg → storage → download link',
  },
  {
    key: 'failure',
    label: 'Run failing task',
    icon: TriangleAlert,
    start: tasksApi.createTestFailure,
    hint: 'Retries after 10 s, 30 s, 90 s, then fails',
  },
  {
    key: 'ai',
    label: 'Test AI connection',
    icon: Bot,
    start: tasksApi.createTestAi,
    hint: 'One tiny request; cost is recorded',
  },
]

function DiagnosticRow({ diagnostic }) {
  const [taskId, setTaskId] = useState(null)
  const start = useStartTask(diagnostic.start, { label: diagnostic.label })
  const task = useTaskPolling(taskId).data
  const Icon = diagnostic.icon

  return (
    <li className="flex flex-col gap-2 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{diagnostic.label}</p>
          <p className="text-xs text-muted-foreground">{diagnostic.hint}</p>
        </div>
        <Button
          variant="outline"
          size="sm"
          disabled={start.isPending}
          onClick={() => start.mutate(undefined, { onSuccess: (r) => setTaskId(r.task_id) })}
        >
          <Icon />
          Run
        </Button>
      </div>
      {task && (
        <div className="flex flex-col gap-1.5 rounded-md bg-muted/50 p-2">
          <div className="flex items-center gap-2 text-xs">
            <span>{taskLabel(task.type)}</span>
            <TaskStatusBadge status={task.status} />
            {task.attempts > 0 && (
              <span className="text-muted-foreground">attempt {task.attempts}</span>
            )}
          </div>
          <ProgressBar value={task.progress} status={task.status} />
          <TaskResult task={task} />
        </div>
      )}
    </li>
  )
}

export default function SystemStatusPage() {
  const { data, error, isPending, isFetching, refetch, dataUpdatedAt, errorUpdatedAt } =
    useSystemStatus()
  const lastChecked = Math.max(dataUpdatedAt, errorUpdatedAt) || null

  return (
    <>
      <PageHeader
        title="System"
        description={`Health of every platform service. Refreshes every ${HEALTH_REFRESH_MS / 1000} seconds.`}
        actions={
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={cn(isFetching && 'animate-spin')} />
            Refresh
          </Button>
        }
      />

      <div className="grid max-w-5xl gap-6 lg:grid-cols-[3fr_2fr]">
        <Card>
          <CardHeader>
            <CardTitle>Services</CardTitle>
            <CardDescription>Last check: {formatDateTime(lastChecked)}</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {isPending && (
                <ServiceRow name="Backend API" status="checking" statusLabel="checking" />
              )}
              {error && (
                <ServiceRow
                  name="Backend API"
                  status="unreachable"
                  statusLabel="unreachable"
                  detail={error.message}
                />
              )}
              {data &&
                !error &&
                SERVICE_ORDER.filter((key) => data.services[key]).map((key) => (
                  <ServiceRow key={key} {...describeCheck(key, data.services[key])} />
                ))}
            </ul>
            {data && (
              <p className="mt-3 text-xs text-muted-foreground">
                Tasks — queued {data.tasks.queued} · running {data.tasks.running} · done{' '}
                {data.tasks.succeeded} · failed {data.tasks.failed}
              </p>
            )}
            {error?.requestId && (
              <p className="mt-3 text-xs text-muted-foreground">Request ID: {error.requestId}</p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Diagnostics</CardTitle>
            <CardDescription>Run a real background task to test the pipeline.</CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y">
              {DIAGNOSTICS.map((diagnostic) => (
                <DiagnosticRow key={diagnostic.key} diagnostic={diagnostic} />
              ))}
            </ul>
          </CardContent>
        </Card>
      </div>
    </>
  )
}
