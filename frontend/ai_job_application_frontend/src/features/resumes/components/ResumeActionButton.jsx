import { LoaderCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ProgressBar } from '@/features/tasks/components/TaskStatusBadge'

/** A button that starts an AI task and shows its progress / error underneath. */
export function ResumeActionButton({ action, icon: Icon, children, variant = 'outline' }) {
  const { task, running } = action
  return (
    <div className="flex min-w-48 flex-col gap-1.5">
      <Button variant={variant} onClick={action.start} disabled={running}>
        {running ? <LoaderCircle className="animate-spin" /> : <Icon />}
        {children}
      </Button>
      {running && task && <ProgressBar value={task.progress} status={task.status} />}
      {task?.status === 'failed' && (
        <p role="alert" className="max-w-xs text-xs text-destructive">
          {task.error}
        </p>
      )}
    </div>
  )
}
