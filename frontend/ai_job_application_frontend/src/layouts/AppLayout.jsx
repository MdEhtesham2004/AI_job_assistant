import { BriefcaseBusiness, Menu, Moon, Sun, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { useUserCounts } from '@/features/admin/hooks'
import { cn } from '@/lib/utils'
import { useTheme } from '@/theme/useTheme'

import { navigation } from './navigation'
import { UserMenu } from './UserMenu'

function SidebarNav({ onNavigate }) {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const counts = useUserCounts({ enabled: isAdmin })
  const badges = { pendingUsers: counts.data?.pending ?? 0 }

  return (
    <nav className="flex flex-col gap-4 p-3" aria-label="Main">
      {navigation
        .filter((section) => !section.adminOnly || isAdmin)
        .map((section, index) => (
          <div key={section.title ?? index} className="flex flex-col gap-1">
            {section.title && (
              <p className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {section.title}
              </p>
            )}
            {section.items.map(({ to, label, icon: Icon, end, badge }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                onClick={onNavigate}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-primary/10 text-primary'
                      : 'text-muted-foreground hover:bg-accent hover:text-foreground',
                  )
                }
              >
                <Icon className="size-4" aria-hidden="true" />
                <span className="flex-1">{label}</span>
                {badge && badges[badge] > 0 && (
                  <span
                    className="rounded-full bg-warning/20 px-2 text-xs font-semibold text-warning"
                    aria-label={`${badges[badge]} pending`}
                  >
                    {badges[badge]}
                  </span>
                )}
              </NavLink>
            ))}
          </div>
        ))}
    </nav>
  )
}

function Brand() {
  return (
    <div className="flex h-14 items-center gap-2 border-b px-5 font-semibold">
      <BriefcaseBusiness className="size-5 text-primary" aria-hidden="true" />
      AI Job Assistant
    </div>
  )
}

export function AppLayout() {
  const { theme, toggleTheme } = useTheme()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <aside className="hidden w-60 shrink-0 border-r bg-sidebar md:block">
        <Brand />
        <SidebarNav />
      </aside>

      {/* Mobile sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 border-r bg-sidebar">
            <Brand />
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between border-b bg-card px-4 md:px-6">
          <Button
            variant="ghost"
            size="icon"
            className="md:hidden"
            onClick={() => setMobileOpen((open) => !open)}
            aria-label={mobileOpen ? 'Close menu' : 'Open menu'}
          >
            {mobileOpen ? <X /> : <Menu />}
          </Button>
          <div className="ml-auto flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
            >
              {theme === 'dark' ? <Sun /> : <Moon />}
            </Button>
            <UserMenu />
          </div>
        </header>

        <main className="flex-1 p-4 md:p-8">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
