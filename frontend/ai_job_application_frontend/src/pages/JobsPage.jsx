import { Download, Search } from 'lucide-react'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { JobRow } from '@/features/jobs/components/JobRow'
import { useExportJobs, useJobCounts, useJobs } from '@/features/jobs/hooks'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 20
const TABS = [
  { state: '', label: 'Inbox', count: (c) => c.new + c.saved + c.analyzed },
  { state: 'new', label: 'New', count: (c) => c.new },
  { state: 'saved', label: 'Saved', count: (c) => c.saved },
  { state: 'skipped', label: 'Skipped', count: (c) => c.skipped },
  { state: 'archived', label: 'Archived', count: (c) => c.archived },
]
const POSTED = [
  { value: '', label: 'Any date' },
  { value: '1', label: 'Last 24 hours' },
  { value: '3', label: 'Last 3 days' },
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
]
const SOURCES = [
  { value: '', label: 'All sources' },
  { value: 'jsearch', label: 'JSearch' },
  { value: 'manual', label: 'Added by me' },
  { value: 'legacy_sheet', label: 'Imported' },
]
const SORTS = [
  { value: 'posted', label: 'Newest posting' },
  { value: 'found', label: 'Recently found' },
  { value: 'company', label: 'Company A–Z' },
]

export default function JobsPage() {
  const [params, setParams] = useSearchParams()
  const filters = {
    state: params.get('state') ?? '',
    q: params.get('q') ?? '',
    location: params.get('location') ?? '',
    source: params.get('source') ?? '',
    posted_within_days: params.get('posted') ?? '',
    remote_only: params.get('remote') === '1',
    sort: params.get('sort') ?? 'posted',
    page: Number(params.get('page') ?? 1),
    page_size: PAGE_SIZE,
  }
  const jobs = useJobs(filters)
  const exporter = useExportJobs()
  const [withDescriptions, setWithDescriptions] = useState(false)
  const onExport = () => {
    // eslint-disable-next-line no-unused-vars -- export every page, not just this one
    const { page, page_size, ...current } = filters
    exporter.mutate({ ...current, include_description: withDescriptions })
  }
  const counts = useJobCounts().data
  const data = jobs.data
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1

  /** Change URL params; any filter change goes back to page 1. */
  const update = (changes) => {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === '' || value === null || value === false) next.delete(key)
      else next.set(key, String(value))
    }
    if (!('page' in changes)) next.delete('page')
    setParams(next)
  }

  const onSearch = (event) => {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    update({ q: form.get('q').trim(), location: form.get('location').trim() })
  }

  return (
    <>
      <PageHeader
        title="Jobs"
        description="Every job your searches found. Save the interesting ones, skip the rest."
        actions={
          <>
            <label className="flex items-center gap-2 text-sm text-muted-foreground">
              <input
                type="checkbox"
                className="size-4 accent-primary"
                checked={withDescriptions}
                onChange={(e) => setWithDescriptions(e.target.checked)}
              />
              with descriptions
            </label>
            <Button variant="outline" onClick={onExport} disabled={exporter.isPending}>
              <Download />
              {exporter.isPending ? 'Exporting…' : 'Export CSV'}
            </Button>
            <Link
              to="/jobs/search"
              className="inline-flex h-9 items-center gap-2 rounded-md bg-primary px-4 text-sm font-medium text-primary-foreground hover:bg-primary/90 [&_svg]:size-4"
            >
              <Search aria-hidden="true" />
              Find jobs
            </Link>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap gap-1 border-b" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab.label}
            type="button"
            role="tab"
            aria-selected={filters.state === tab.state}
            onClick={() => update({ state: tab.state })}
            className={cn(
              '-mb-px border-b-2 px-3 py-2 text-sm font-medium',
              filters.state === tab.state
                ? 'border-primary text-primary'
                : 'border-transparent text-muted-foreground hover:text-foreground',
            )}
          >
            {tab.label}
            {counts && <span className="ml-1.5 text-xs">{tab.count(counts)}</span>}
          </button>
        ))}
      </div>

      <form
        onSubmit={onSearch}
        className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-[2fr_1.5fr_1fr_1fr_1fr_auto]"
        key={`${filters.q}|${filters.location}`}
      >
        <Input
          name="q"
          defaultValue={filters.q}
          placeholder="Title or company"
          aria-label="Title or company"
        />
        <Input
          name="location"
          defaultValue={filters.location}
          placeholder="Location"
          aria-label="Location"
        />
        <Select
          aria-label="Posted"
          value={filters.posted_within_days}
          onChange={(e) => update({ posted: e.target.value })}
        >
          {POSTED.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Source"
          value={filters.source}
          onChange={(e) => update({ source: e.target.value })}
        >
          {SOURCES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Sort"
          value={filters.sort}
          onChange={(e) => update({ sort: e.target.value === 'posted' ? '' : e.target.value })}
        >
          {SORTS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </Select>
        <Button type="submit" variant="outline">
          Apply
        </Button>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-primary"
            checked={filters.remote_only}
            onChange={(e) => update({ remote: e.target.checked ? '1' : '' })}
          />
          Remote only
        </label>
      </form>

      <Card>
        <CardContent className="p-0">
          <ul className={cn('divide-y', jobs.isPlaceholderData && 'opacity-60')}>
            {jobs.isPending && (
              <li className="px-5 py-8 text-center text-muted-foreground">Loading…</li>
            )}
            {jobs.isError && (
              <li className="px-5 py-8 text-center text-destructive">{jobs.error.message}</li>
            )}
            {data?.items.length === 0 && (
              <li className="px-5 py-8 text-center text-muted-foreground">
                No jobs here.{' '}
                <Link to="/jobs/search" className="text-primary hover:underline">
                  Run a search
                </Link>{' '}
                or change the filters.
              </li>
            )}
            {data?.items.map((job) => (
              <JobRow key={job.id} job={job} />
            ))}
          </ul>
        </CardContent>
      </Card>

      {data && data.total > PAGE_SIZE && (
        <div className="mt-4 flex items-center justify-end gap-2 text-sm">
          <span className="text-muted-foreground">
            Page {filters.page} of {totalPages} · {data.total} jobs
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={filters.page <= 1}
            onClick={() => update({ page: filters.page - 1 })}
          >
            Previous
          </Button>
          <Button
            variant="outline"
            size="sm"
            disabled={filters.page >= totalPages}
            onClick={() => update({ page: filters.page + 1 })}
          >
            Next
          </Button>
        </div>
      )}
    </>
  )
}
