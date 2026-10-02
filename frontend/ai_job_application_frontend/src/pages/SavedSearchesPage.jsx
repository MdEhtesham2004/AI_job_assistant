import { Pause, Pencil, Play, Plus, Trash, Zap } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Dialog } from '@/components/ui/dialog'
import { describeQuery, describeSchedule } from '@/features/jobs/api'
import { SavedSearchDialog } from '@/features/jobs/components/SavedSearchDialog'
import {
  useDeleteSavedSearch,
  useRunSavedSearch,
  useSavedSearches,
  useUpdateSavedSearch,
} from '@/features/jobs/hooks'
import { formatDateTime, formatRelative } from '@/lib/format'

export default function SavedSearchesPage() {
  const searches = useSavedSearches()
  const update = useUpdateSavedSearch()
  const run = useRunSavedSearch()
  const remove = useDeleteSavedSearch()
  const [editing, setEditing] = useState(null) // saved search, or {} for a new one
  const [deleting, setDeleting] = useState(null)

  const toggle = (saved) =>
    update.mutate(
      { id: saved.id, changes: { is_active: !saved.is_active } },
      { onError: (error) => toast.error(error.message) },
    )

  return (
    <>
      <PageHeader
        title="Saved searches"
        description="Searches that run on a schedule and notify you when they find new jobs."
        actions={
          <Button onClick={() => setEditing({})}>
            <Plus />
            New saved search
          </Button>
        }
      />

      <Card>
        <CardContent className="p-0">
          <ul className="divide-y">
            {searches.isPending && (
              <li className="px-5 py-8 text-center text-muted-foreground">Loading…</li>
            )}
            {searches.isError && (
              <li className="px-5 py-8 text-center text-destructive">{searches.error.message}</li>
            )}
            {searches.data?.length === 0 && (
              <li className="px-5 py-8 text-center text-muted-foreground">
                No saved searches yet. Create one, or use “Save as scheduled search” on Find jobs.
              </li>
            )}
            {searches.data?.map((saved) => (
              <li
                key={saved.id}
                className="flex flex-col gap-3 px-5 py-4 md:flex-row md:items-center"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{saved.name}</span>
                    <Badge variant={saved.is_active ? 'success' : 'outline'}>
                      {saved.is_active ? 'Active' : 'Paused'}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">{describeQuery(saved)}</p>
                  <p className="text-xs text-muted-foreground">
                    {describeSchedule(saved.schedule_cron)}
                    {saved.next_run_at && ` · next ${formatRelative(saved.next_run_at)}`}
                    {saved.last_run_at && ` · last run ${formatDateTime(saved.last_run_at)}`}
                  </p>
                </div>
                <div className="flex flex-wrap gap-1">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => run.mutate(saved.id)}
                    disabled={run.isPending}
                  >
                    <Zap />
                    Run now
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => toggle(saved)}
                    aria-label={saved.is_active ? `Pause ${saved.name}` : `Resume ${saved.name}`}
                  >
                    {saved.is_active ? <Pause /> : <Play />}
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setEditing(saved)}
                    aria-label={`Edit ${saved.name}`}
                  >
                    <Pencil />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setDeleting(saved)}
                    aria-label={`Delete ${saved.name}`}
                  >
                    <Trash />
                  </Button>
                </div>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>

      {editing && (
        <SavedSearchDialog
          open
          saved={editing.id ? editing : undefined}
          onClose={() => setEditing(null)}
        />
      )}
      <Dialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        title={`Delete “${deleting?.name}”?`}
        description="It stops running. Jobs it already found stay in your list."
      >
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setDeleting(null)}>
            Cancel
          </Button>
          <Button
            variant="destructive"
            disabled={remove.isPending}
            onClick={() => remove.mutate(deleting.id, { onSuccess: () => setDeleting(null) })}
          >
            Delete
          </Button>
        </div>
      </Dialog>
    </>
  )
}
