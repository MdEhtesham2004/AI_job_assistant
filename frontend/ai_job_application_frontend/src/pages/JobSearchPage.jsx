import { zodResolver } from '@hookform/resolvers/zod'
import { BellPlus, Search, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { useForm } from 'react-hook-form'
import { Link } from 'react-router'

import { CheckboxField } from '@/components/common/CheckboxField'
import { FormError } from '@/components/common/FormError'
import { FormField } from '@/components/common/FormField'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Label } from '@/components/ui/label'
import { Select } from '@/components/ui/select'
import {
  DATE_POSTED_OPTIONS,
  describeQuery,
  EXPERIENCE_OPTIONS,
  PAGE_OPTIONS,
} from '@/features/jobs/api'
import { RunStatusBadge } from '@/features/jobs/components/JobBadges'
import { SavedSearchDialog } from '@/features/jobs/components/SavedSearchDialog'
import { SearchRunResults } from '@/features/jobs/components/SearchRunResults'
import { useRecentSearches, useStartSearch, useSuggestedRoles } from '@/features/jobs/hooks'
import { searchSchema, toSearchBody } from '@/features/jobs/schemas'
import { applyServerErrors } from '@/lib/forms'
import { formatRelative } from '@/lib/format'

export default function JobSearchPage() {
  const [runId, setRunId] = useState(null)
  const [prefill, setPrefill] = useState(null)
  const start = useStartSearch()
  const roles = useSuggestedRoles()
  const recent = useRecentSearches()
  const {
    register,
    handleSubmit,
    setValue,
    getValues,
    setError,
    formState: { errors, isSubmitting },
  } = useForm({
    resolver: zodResolver(searchSchema),
    defaultValues: {
      keywords: '',
      location: '',
      experience: '',
      date_posted: 'week',
      num_pages: 1,
      remote_only: false,
      country: 'in',
    },
  })

  const onSubmit = async (values) => {
    try {
      const started = await start.mutateAsync({
        ...toSearchBody(values),
        date_posted: values.date_posted,
        num_pages: values.num_pages,
      })
      setRunId(started.run_id)
    } catch (error) {
      applyServerErrors(error, setError, ['keywords', 'location', 'country'])
    }
  }

  const pickRole = (role) => {
    setValue('keywords', role, { shouldValidate: true })
    if (!getValues('location') && roles.data?.location) setValue('location', roles.data.location)
  }

  return (
    <>
      <PageHeader
        title="Find jobs"
        description="Searches JSearch (Google for Jobs, LinkedIn, Naukri, Indeed …). Every result is stored once and added to your jobs."
      />

      <div className="grid gap-6 xl:grid-cols-[minmax(0,3fr)_minmax(0,1fr)]">
        <div className="flex flex-col gap-6">
          <Card>
            <CardContent className="pt-5">
              <form
                className="grid gap-4 sm:grid-cols-2"
                onSubmit={handleSubmit(onSubmit)}
                noValidate
              >
                <FormError message={errors.root?.server?.message} />
                <FormField
                  label="Job title or keywords"
                  placeholder="e.g. React Native Developer"
                  registration={register('keywords')}
                  error={errors.keywords}
                />
                <FormField
                  label="Location"
                  placeholder="e.g. Hyderabad"
                  registration={register('location')}
                  error={errors.location}
                />
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="search-experience">Experience</Label>
                  <Select id="search-experience" {...register('experience')}>
                    {EXPERIENCE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="search-date">Posted</Label>
                  <Select id="search-date" {...register('date_posted')}>
                    {DATE_POSTED_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="search-pages">Results</Label>
                  <Select id="search-pages" {...register('num_pages', { valueAsNumber: true })}>
                    {PAGE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </Select>
                  <p className="text-xs text-muted-foreground">
                    More pages use more of your JSearch quota.
                  </p>
                </div>
                <FormField
                  label="Country"
                  hint="2-letter code"
                  registration={register('country')}
                  error={errors.country}
                />
                <div className="flex items-end pb-2">
                  <CheckboxField label="Remote jobs only" registration={register('remote_only')} />
                </div>
                <div className="flex flex-wrap gap-2 sm:col-span-2">
                  <Button type="submit" disabled={isSubmitting}>
                    <Search />
                    {isSubmitting ? 'Starting…' : 'Search jobs'}
                  </Button>
                  <Button variant="outline" onClick={() => setPrefill(getValues())}>
                    <BellPlus />
                    Save as scheduled search
                  </Button>
                </div>
              </form>
            </CardContent>
          </Card>

          {runId && <SearchRunResults runId={runId} />}
        </div>

        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Sparkles className="size-4 text-primary" aria-hidden="true" />
                Suggested from your resume
              </CardTitle>
              <CardDescription>Best-fit roles from your latest ATS report.</CardDescription>
            </CardHeader>
            <CardContent>
              {roles.data?.roles.length ? (
                <div className="flex flex-wrap gap-2">
                  {roles.data.roles.map((role) => (
                    <button
                      key={role}
                      type="button"
                      onClick={() => pickRole(role)}
                      className="rounded-full bg-primary/10 px-3 py-1 text-sm text-primary hover:bg-primary/20"
                    >
                      {role}
                    </button>
                  ))}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  {roles.data?.hint ?? 'Loading…'}{' '}
                  {roles.data?.hint && (
                    <Link to="/resumes" className="text-primary hover:underline">
                      Go to Resumes
                    </Link>
                  )}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Recent searches</CardTitle>
            </CardHeader>
            <CardContent className="p-0">
              <ul className="divide-y border-t">
                {recent.data?.length === 0 && (
                  <li className="px-5 py-4 text-sm text-muted-foreground">No searches yet.</li>
                )}
                {recent.data?.map((run) => (
                  <li key={run.id} className="px-5 py-3">
                    <Link
                      to={`/jobs/searches/${run.id}`}
                      className="text-sm font-medium hover:text-primary hover:underline"
                    >
                      {describeQuery(run.query)}
                    </Link>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <RunStatusBadge status={run.status} />
                      {run.status === 'succeeded' &&
                        `${run.results_count} found · ${run.new_jobs_count} new`}
                      <span>{formatRelative(run.created_at)}</span>
                      {run.saved_search_id && <span>· scheduled</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>

      {prefill && <SavedSearchDialog open onClose={() => setPrefill(null)} prefill={prefill} />}
    </>
  )
}
