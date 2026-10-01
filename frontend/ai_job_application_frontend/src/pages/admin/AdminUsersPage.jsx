import { Search } from 'lucide-react'
import { useEffect, useState } from 'react'

import { useAuth } from '@/auth/useAuth'
import { PageHeader } from '@/components/common/PageHeader'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { ConfirmDialog, RejectDialog } from '@/features/admin/components/ActionDialogs'
import { UserRowActions } from '@/features/admin/components/UserRowActions'
import { RoleBadge, UserStatusBadge } from '@/features/admin/components/UserStatusBadge'
import { useAdminUsers, useUserAction, useUserCounts } from '@/features/admin/hooks'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

const PAGE_SIZE = 20
const TABS = [
  { key: 'pending', label: 'Pending' },
  { key: 'approved', label: 'Approved' },
  { key: 'rejected', label: 'Rejected' },
  { key: 'deactivated', label: 'Deactivated' },
  { key: 'all', label: 'All' },
]

const CONFIRM = {
  deactivate: (u) => ({
    title: `Deactivate ${u.full_name}?`,
    description: 'They are signed out immediately and cannot sign in until reactivated.',
    confirmLabel: 'Deactivate',
    danger: true,
  }),
  makeAdmin: (u) => ({
    title: `Make ${u.full_name} an admin?`,
    description: 'Admins can approve sign-ups and manage all accounts.',
    confirmLabel: 'Make admin',
  }),
  removeAdmin: (u) => ({
    title: `Remove admin rights from ${u.full_name}?`,
    description: 'They keep their account but lose access to admin pages.',
    confirmLabel: 'Remove admin',
    danger: true,
  }),
}

function useDebounced(value, delay = 300) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}

export default function AdminUsersPage() {
  const { user: me } = useAuth()
  const [tab, setTab] = useState('pending')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const [pending, setPending] = useState(null) // { action, user } awaiting confirmation
  const q = useDebounced(search.trim())

  const counts = useUserCounts()
  const users = useAdminUsers({ status: tab, q, page, page_size: PAGE_SIZE })
  const action = useUserAction()

  const run = (name, user, extra = {}) =>
    action.mutate({ action: name, id: user.id, ...extra }, { onSettled: () => setPending(null) })

  const onAction = (name, user) => {
    if (name === 'approve' || name === 'reactivate') run(name, user)
    else setPending({ action: name, user })
  }

  const data = users.data
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1
  const confirm =
    pending && pending.action !== 'reject' ? CONFIRM[pending.action](pending.user) : null

  return (
    <>
      <PageHeader title="Users" description="Approve sign-ups and manage accounts." />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label="Account status" className="flex flex-wrap gap-1">
          {TABS.map(({ key, label }) => (
            <button
              key={key}
              role="tab"
              type="button"
              aria-selected={tab === key}
              onClick={() => {
                setTab(key)
                setPage(1)
              }}
              className={cn(
                'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
                tab === key
                  ? 'bg-primary/10 text-primary'
                  : 'text-muted-foreground hover:bg-accent',
              )}
            >
              {label}
              {counts.data && (
                <span
                  className={cn(
                    'ml-1.5 rounded-full px-1.5 text-xs',
                    key === 'pending' && counts.data.pending > 0
                      ? 'bg-warning/20 text-warning'
                      : 'bg-muted',
                  )}
                >
                  {counts.data[key]}
                </span>
              )}
            </button>
          ))}
        </div>
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input
            aria-label="Search users"
            placeholder="Search name or email"
            className="pl-8"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value)
              setPage(1)
            }}
          />
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b text-left text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-4 py-3 font-medium">Name</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="hidden px-4 py-3 font-medium md:table-cell">Joined</th>
                  <th className="px-4 py-3 text-right font-medium">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {users.isPending && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                      Loading…
                    </td>
                  </tr>
                )}
                {users.isError && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-destructive">
                      {users.error.message}
                    </td>
                  </tr>
                )}
                {data?.items.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-8 text-center text-muted-foreground">
                      {tab === 'pending' && !q
                        ? 'No sign-ups are waiting for approval.'
                        : 'No accounts here.'}
                    </td>
                  </tr>
                )}
                {data?.items.map((user) => (
                  <tr key={user.id}>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 font-medium">
                        {user.full_name}
                        <RoleBadge role={user.role} />
                      </div>
                      <div className="text-muted-foreground">{user.email}</div>
                      {user.rejection_reason && (
                        <div className="text-xs text-muted-foreground">
                          Reason: {user.rejection_reason}
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <UserStatusBadge user={user} />
                    </td>
                    <td className="hidden px-4 py-3 text-muted-foreground md:table-cell">
                      {formatDateTime(user.created_at)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <UserRowActions
                        user={user}
                        currentUserId={me?.id}
                        disabled={action.isPending}
                        onAction={onAction}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {data && data.total > PAGE_SIZE && (
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

      <RejectDialog
        open={pending?.action === 'reject'}
        user={pending?.user}
        busy={action.isPending}
        onClose={() => setPending(null)}
        onConfirm={(reason) => run('reject', pending.user, { reason })}
      />
      <ConfirmDialog
        open={Boolean(confirm)}
        {...(confirm ?? {})}
        busy={action.isPending}
        onClose={() => setPending(null)}
        onConfirm={() => run(pending.action, pending.user)}
      />
    </>
  )
}
