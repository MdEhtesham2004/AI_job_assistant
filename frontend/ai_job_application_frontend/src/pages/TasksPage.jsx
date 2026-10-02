import { FileText } from 'lucide-react'
import { useState } from 'react'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { tasksApi, taskLabel } from '@/features/tasks/api'
import { ProgressBar, TaskStatusBadge } from '@/features/tasks/components/TaskStatusBadge'
import { TaskResult } from '@/features/tasks/components/TaskResult'
import { useStartTask, useTasks } from '@/features/tasks/hooks'
import { formatDateTime } from '@/lib/format'

export default function TasksPage() {
  const [page, setPage] = useState(1)
  const tasks = useTasks(page)
  const testPdf = useStartTask(tasksApi.createTestPdf, { label: 'Test PDF' })
  const data = tasks.data
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1

  return (
    <>
      <PageHeader
        title="Tasks"
        description="Long-running work (AI analysis, PDF generation, emails) runs in the background."
        actions={
          <Button onClick={() => testPdf.mutate()} disabled={testPdf.isPending}>
            <FileText />
            Generate test PDF
          </Button>
        }
      />

      <Card>
        <CardContent className="p-0">
          <ul className="divide-y">
            {tasks.isPending && (
              <li className="px-4 py-8 text-center text-muted-foreground">Loading…</li>
            )}
            {tasks.isError && (
              <li className="px-4 py-8 text-center text-destructive">{tasks.error.message}</li>
            )}
            {data?.items.length === 0 && (
              <li className="px-4 py-8 text-center text-muted-foreground">
                No tasks yet. Try “Generate test PDF”.
              </li>
            )}
            {data?.items.map((task) => (
              <li key={task.id} className="flex flex-col gap-2 px-4 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <span className="font-medium">{taskLabel(task.type)}</span>
                    <TaskStatusBadge status={task.status} />
                    {task.attempts > 1 && (
                      <span className="text-xs text-muted-foreground">attempt {task.attempts}</span>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">
                    {formatDateTime(task.created_at)}
                  </span>
                </div>
                <ProgressBar value={task.progress} status={task.status} />
                <TaskResult task={task} />
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {data && data.total > data.page_size && (
        <div className="mt-4 flex items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </>
  )
}
