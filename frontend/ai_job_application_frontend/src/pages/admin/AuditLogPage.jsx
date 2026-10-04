import { useState } from 'react'

import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Select } from '@/components/ui/select'
import { useAudit } from '@/features/admin/insights'
import { formatDateTime } from '@/lib/format'

const ACTIONS = [
  ['', 'All actions'],
  ['auth.', 'Sign-in & passwords'],
  ['user.', 'Users (approve, roles, delete)'],
  ['platform.', 'Platform settings'],
]

export default function AuditLogPage() {
  const [action, setAction] = useState('')
  const [actorType, setActorType] = useState('')
  const [q, setQ] = useState('')
  const [page, setPage] = useState(1)
  const audit = useAudit({ action, actorType, q, page })
  const data = audit.data
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1
  const reset = (setter) => (e) => {
    setter(e.target.value)
    setPage(1)
  }

  return (
    <>
      <PageHeader
        title="Audit log"
        description="Who did what and when — sign-ins, approvals, role changes, platform settings, deleted accounts."
      />
      <div className="mb-4 grid gap-2 sm:grid-cols-[1fr_1fr_2fr]">
        <Select aria-label="Action" value={action} onChange={reset(setAction)}>
          {ACTIONS.map(([value, label]) => (
            <option key={value || 'all'} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Select aria-label="Actor" value={actorType} onChange={reset(setActorType)}>
          <option value="">Anyone</option>
          <option value="user">User</option>
          <option value="admin">Admin</option>
          <option value="system">System</option>
        </Select>
        <Input aria-label="User email" placeholder="User email" value={q} onChange={reset(setQ)} />
      </div>
      <Card>
        <CardContent className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-4 py-2 font-medium">When</th>
                <th className="px-4 py-2 font-medium">Who</th>
                <th className="px-4 py-2 font-medium">Action</th>
                <th className="px-4 py-2 font-medium">Details</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data?.items.map((entry) => (
                <tr key={entry.id} className="align-top">
                  <td className="whitespace-nowrap px-4 py-2">
                    {formatDateTime(entry.created_at)}
                  </td>
                  <td className="px-4 py-2">
                    {entry.user_email ?? (
                      <span className="text-muted-foreground">deleted user</span>
                    )}
                    <div className="text-xs text-muted-foreground">{entry.actor_type}</div>
                  </td>
                  <td className="px-4 py-2 font-mono text-xs">{entry.action}</td>
                  <td className="px-4 py-2 text-xs text-muted-foreground">
                    {entry.data ? JSON.stringify(entry.data) : ''}
                    {entry.ip_address ? ` · ${entry.ip_address}` : ''}
                  </td>
                </tr>
              ))}
              {data?.items.length === 0 && (
                <tr>
                  <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                    No entries.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>
      {pages > 1 && (
        <div className="mt-4 flex items-center gap-2 text-sm">
          <Button
            size="sm"
            variant="outline"
            disabled={page <= 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <span className="text-muted-foreground">
            Page {page} of {pages}
          </span>
          <Button
            size="sm"
            variant="outline"
            disabled={page >= pages}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </>
  )
}
