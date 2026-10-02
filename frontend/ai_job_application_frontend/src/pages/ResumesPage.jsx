import { ChevronRight, FileText } from 'lucide-react'
import { Link } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { KIND_LABELS } from '@/features/resumes/api'
import { ParseStatusBadge, ScoreBadge } from '@/features/resumes/components/ParseStatusBadge'
import { ResumeUploader } from '@/features/resumes/components/ResumeUploader'
import { useActivateVersion, useResumes } from '@/features/resumes/hooks'
import { formatBytes, formatDateTime } from '@/lib/format'

export default function ResumesPage() {
  const resumes = useResumes()
  const activate = useActivateVersion()
  const versions = resumes.data?.versions ?? []

  return (
    <>
      <PageHeader
        title="Resumes"
        description="Upload your resume, keep every version, and check how well it reads to ATS software."
      />

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Upload a resume</CardTitle>
          <CardDescription>
            Each upload becomes a new version — older versions are kept.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ResumeUploader />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Versions</CardTitle>
          <CardDescription>
            The active version is the one used for job matching and applications.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          <ul className="divide-y border-t">
            {resumes.isPending && (
              <li className="px-5 py-8 text-center text-muted-foreground">Loading…</li>
            )}
            {resumes.isError && (
              <li className="px-5 py-8 text-center text-destructive">{resumes.error.message}</li>
            )}
            {resumes.isSuccess && versions.length === 0 && (
              <li className="px-5 py-8 text-center text-muted-foreground">
                No resume yet. Upload one above to get started.
              </li>
            )}
            {versions.map((version) => (
              <li key={version.id} className="flex flex-wrap items-center gap-3 px-5 py-3">
                <FileText className="size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">Version {version.version_no}</span>
                    <Badge variant="outline">{KIND_LABELS[version.kind] ?? version.kind}</Badge>
                    {version.is_active && <Badge variant="success">Active</Badge>}
                    <ParseStatusBadge status={version.parse_status} />
                    <ScoreBadge score={version.ats_score} />
                  </div>
                  <p className="truncate text-xs text-muted-foreground">
                    {version.file_name} · {formatBytes(version.file_size)} ·{' '}
                    {formatDateTime(version.created_at)}
                  </p>
                </div>
                {!version.is_active && (
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={activate.isPending}
                    onClick={() => activate.mutate(version.id)}
                  >
                    Set active
                  </Button>
                )}
                <Link
                  to={`/resumes/${version.id}`}
                  className="inline-flex h-8 items-center gap-1 rounded-md px-3 text-sm font-medium hover:bg-accent"
                  aria-label={`Open version ${version.version_no}`}
                >
                  Open
                  <ChevronRight className="size-4" aria-hidden="true" />
                </Link>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </>
  )
}
