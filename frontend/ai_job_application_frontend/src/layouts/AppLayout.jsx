import { Menu, Moon, Sun, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router'

import { useAuth } from '@/auth/useAuth'
import { Button } from '@/components/ui/button'
import { useSettings } from '@/features/account/hooks'
import { useUserCounts } from '@/features/admin/hooks'
import { NotificationBell } from '@/features/notifications/NotificationBell'
import { useGmailStatus } from '@/features/outreach/hooks'
import { cn } from '@/lib/utils'
import { useTheme } from '@/theme/useTheme'

import { navigation } from './navigation'
import { UserMenu } from './UserMenu'

function SidebarNav({ onNavigate }) {
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'
  const counts = useUserCounts({ enabled: isAdmin })
  const badges = { pendingUsers: counts.data?.pending ?? 0 }
  const { pathname } = useLocation()
  // Phase 18: Outreach (Contacts, Outbox) only once Gmail or LinkedIn posts are in use.
  const settings = useSettings().data
  const gmail = useGmailStatus().data
  const show = {
    outreach: Boolean(settings?.linkedin_source_enabled || gmail?.connected),
  }
  const onAlso = (also = []) =>
    also.some((path) => pathname === path || pathname.startsWith(`${path}/`))

  return (
    <nav className="flex flex-col gap-6 px-3 py-4" aria-label="Main">
      {navigation
        .filter((section) => !section.adminOnly || isAdmin)
        .map((section, index) => (
          <div key={section.title ?? index} className="flex flex-col gap-0.5">
            {section.title && (
              <p className="px-3 pb-1.5 text-xs font-semibold text-muted-foreground">
                {section.title}
              </p>
            )}
            {section.items
              .filter((item) => !item.when || show[item.when])
              .map(({ to, label, icon: Icon, end, badge, also }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  onClick={onNavigate}
                  className={({ isActive }) =>
                    cn(
                      // Active page: an ink bar on the left edge, like a tab in a ledger.
                      'relative flex items-center gap-3 rounded-md px-3 py-[0.45rem] text-[0.9rem] font-medium transition-colors',
                      'before:absolute before:inset-y-1.5 before:left-0 before:w-[3px] before:rounded-full',
                      isActive || onAlso(also)
                        ? 'bg-card text-foreground before:bg-primary'
                        : 'text-muted-foreground hover:bg-card/60 hover:text-foreground',
                    )
                  }
                >
                  <Icon className="size-4 opacity-80" aria-hidden="true" />
                  <span className="flex-1">{label}</span>
                  {badge && badges[badge] > 0 && (
                    <span
                      className="tabular rounded-sm bg-warning/15 px-1.5 text-xs font-semibold text-warning"
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
    <div className="flex h-16 items-center px-6">
      <span className="text-[1.15rem] font-extrabold tracking-tight">
        FindMy<span className="text-primary">Jobs</span>
      </span>
    </div>
  )
}

export function AppLayout() {
  const { theme, toggleTheme } = useTheme()
  const [mobileOpen, setMobileOpen] = useState(false)

  return (
    <div className="flex min-h-screen">
      {/* Desktop sidebar */}
      <div className="hidden w-60 shrink-0 bg-sidebar md:block">
        <aside className="sticky top-0 h-screen overflow-y-auto">
          <Brand />
          <SidebarNav />
        </aside>
      </div>

      {/* Mobile sidebar */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <div className="absolute inset-0 bg-black/40" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64 overflow-y-auto bg-sidebar shadow-xl">
            <Brand />
            <SidebarNav onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 items-center justify-between px-4 md:px-8">
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
            <NotificationBell />
            <UserMenu />
          </div>
        </header>

        <main className="flex-1 px-4 pb-12 pt-2 md:px-10">
          <div className="mx-auto w-full max-w-6xl">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  )
}
