import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FileUp, LoaderCircle } from 'lucide-react'
import { useRef } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'

import { api } from '@/api/client'
import { queryKeys } from '@/api/queryKeys'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

/** Jobs › Import: CSV exports of the old n8n Google Sheets (Phase 14). */
export default function ImportPage() {
  const input = useRef(null)
  const queryClient = useQueryClient()
  const upload = useMutation({
    mutationFn: (file) => {
      const form = new FormData()
      form.append('file', file)
      return api.post('/imports/legacy', form)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: queryKeys.jobs.all() })
      queryClient.invalidateQueries({ queryKey: queryKeys.contacts.all() })
    },
    onError: (error) => toast.error(error.message),
  })
  const result = upload.data

  return (
    <>
      <PageHeader
        title="Import"
        description="Bring jobs and LinkedIn leads over from the old Discord / n8n system."
      />
      <div className="flex max-w-3xl flex-col gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Import a Google Sheet</CardTitle>
            <CardDescription>
              In Google Sheets: <b>File › Download › Comma-separated values (.csv)</b>, then choose
              the file here. Both old sheets work — the job list (
              <i>Job Title, Company, Apply Link…</i>) and <i>LinkedIn Leads</i> (
              <i>email, post_url, post_text…</i>). Importing the same file again adds nothing twice.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <input
              ref={input}
              type="file"
              accept=".csv,text/csv"
              className="hidden"
              data-testid="import-file"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) upload.mutate(file)
                e.target.value = ''
              }}
            />
            <Button onClick={() => input.current?.click()} disabled={upload.isPending}>
              {upload.isPending ? <LoaderCircle className="animate-spin" /> : <FileUp />}
              Choose CSV file
            </Button>
            <ul className="list-disc pl-5 text-muted-foreground">
              <li>
                Jobs are added to your list as <b>Saved</b> (private to you).
              </li>
              <li>
                Lead emails become contacts that <b>wait for your approval</b>, with the post as
                evidence. Leads the old system already emailed are marked so.
              </li>
              <li>Your resume: upload it again on the Resumes page.</li>
            </ul>
          </CardContent>
        </Card>

        {result && (
          <Card>
            <CardHeader>
              <CardTitle>
                Imported {result.kind === 'leads' ? 'LinkedIn leads' : 'job list'} ({result.rows}{' '}
                rows)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p>
                <b>{result.jobs_created}</b> new jobs · {result.jobs_existing} already there
                {result.kind === 'leads' && (
                  <>
                    {' '}
                    · <b>{result.contacts_created}</b> new contacts · {result.contacts_existing}{' '}
                    already there · {result.already_emailed} emailed by the old system
                  </>
                )}
              </p>
              {result.skipped_count > 0 && (
                <details>
                  <summary className="cursor-pointer text-muted-foreground">
                    {result.skipped_count} rows skipped
                  </summary>
                  <ul className="mt-1 list-disc pl-5 text-xs text-muted-foreground">
                    {result.skipped.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </details>
              )}
              <div className="flex gap-3">
                <Link to="/jobs" className="text-primary hover:underline">
                  Open Jobs
                </Link>
                {result.kind === 'leads' && (
                  <Link to="/contacts?approval=pending" className="text-primary hover:underline">
                    Review contacts
                  </Link>
                )}
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    </>
  )
}
