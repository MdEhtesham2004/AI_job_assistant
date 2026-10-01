import { KeyRound, LogOut } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'

function initials(name = '') {
  return (
    name
      .split(/\s+/)
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0].toUpperCase())
      .join('') || '?'
  )
}

export function UserMenu() {
  const { user, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const containerRef = useRef(null)

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

  if (!user) return null

  return (
    <div className="relative" ref={containerRef}>
      <Button
        variant="ghost"
        className="gap-2 px-2"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className="flex size-7 items-center justify-center rounded-full bg-primary/15 text-xs font-semibold text-primary">
          {initials(user.full_name)}
        </span>
        <span className="hidden text-sm sm:inline">{user.full_name}</span>
      </Button>

      {open && (
        <div
          role="menu"
          className="absolute right-0 z-50 mt-2 w-64 rounded-lg border bg-card p-1 shadow-lg"
        >
          <div className="px-3 py-2">
            <p className="truncate text-sm font-medium">{user.full_name}</p>
            <p className="truncate text-xs text-muted-foreground">{user.email}</p>
            <Badge className="mt-2" variant={user.role === 'admin' ? 'success' : 'outline'}>
              {user.role}
            </Badge>
          </div>
          <div className="my-1 border-t" />
          <Link
            role="menuitem"
            to="/account/password"
            onClick={() => setOpen(false)}
            className="flex items-center gap-2 rounded-md px-3 py-2 text-sm hover:bg-accent"
          >
            <KeyRound className="size-4" aria-hidden="true" />
            Change password
          </Link>
          <button
            role="menuitem"
            type="button"
            onClick={logout}
            className="flex w-full items-center gap-2 rounded-md px-3 py-2 text-sm text-destructive hover:bg-destructive/10"
          >
            <LogOut className="size-4" aria-hidden="true" />
            Log out
          </button>
        </div>
      )}
    </div>
  )
}
