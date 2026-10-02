import { Bell, CheckCheck } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router'

import { Button } from '@/components/ui/button'
import { formatDateTime } from '@/lib/format'
import { cn } from '@/lib/utils'

import { useMarkAllRead, useMarkRead, useNotificationList, useUnreadCount } from './hooks'

const DOT = {
  info: 'bg-primary',
  success: 'bg-success',
  warning: 'bg-warning',
  error: 'bg-destructive',
}

export function NotificationBell() {
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)
  const navigate = useNavigate()
  const unread = useUnreadCount()
  const list = useNotificationList({ enabled: open })
  const markRead = useMarkRead()
  const markAllRead = useMarkAllRead()
  const count = unread.data?.unread ?? 0

  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (event) => {
      if (!containerRef.current?.contains(event.target)) setOpen(false)
    }
    const onKeyDown = (event) => event.key === 'Escape' && setOpen(false)
    document.addEventListener('pointerdown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('pointerdown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const openNotification = (notification) => {
    if (!notification.read_at) markRead.mutate(notification.id)
    setOpen(false)
    if (notification.link) navigate(notification.link)
  }

  return (
    <div className="relative" ref={containerRef}>
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setOpen((value) => !value)}
        aria-label={count ? `Notifications, ${count} unread` : 'Notifications'}
        aria-expanded={open}
      >
        <Bell />
        {count > 0 && (
          <span className="absolute right-1 top-1 flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-semibold leading-4 text-white">
            {count > 9 ? '9+' : count}
          </span>
        )}
      </Button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-lg border bg-card shadow-lg">
          <div className="flex items-center justify-between border-b px-3 py-2">
            <p className="text-sm font-semibold">Notifications</p>
            <Button
              variant="ghost"
              size="sm"
              disabled={count === 0 || markAllRead.isPending}
              onClick={() => markAllRead.mutate()}
            >
              <CheckCheck />
              Mark all read
            </Button>
          </div>
          <ul className="max-h-96 divide-y overflow-y-auto">
            {list.isPending && (
              <li className="px-3 py-6 text-center text-sm text-muted-foreground">Loading…</li>
            )}
            {list.data?.items.length === 0 && (
              <li className="px-3 py-6 text-center text-sm text-muted-foreground">
                You're all caught up.
              </li>
            )}
            {list.data?.items.map((notification) => (
              <li key={notification.id}>
                <button
                  type="button"
                  onClick={() => openNotification(notification)}
                  className={cn(
                    'flex w-full gap-3 px-3 py-2.5 text-left hover:bg-accent',
                    !notification.read_at && 'bg-primary/5',
                  )}
                >
                  <span
                    className={cn(
                      'mt-1.5 size-2 shrink-0 rounded-full',
                      DOT[notification.severity],
                    )}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1">
                    <span className={cn('block text-sm', !notification.read_at && 'font-semibold')}>
                      {notification.title}
                    </span>
                    {notification.body && (
                      <span className="block truncate text-xs text-muted-foreground">
                        {notification.body}
                      </span>
                    )}
                    <span className="block text-xs text-muted-foreground">
                      {formatDateTime(notification.created_at)}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
