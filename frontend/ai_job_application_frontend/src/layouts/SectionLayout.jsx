import { NavLink, Outlet } from 'react-router'

import { cn } from '@/lib/utils'

import { SECTIONS } from './sections'

/** Tabs for the pages of one sidebar area (Phase 18); the pages themselves are unchanged. */
export function SectionTabs({ section }) {
  return (
    <nav
      aria-label="Section"
      className="mb-6 inline-flex flex-wrap gap-1 rounded-lg border bg-muted/40 p-1"
    >
      {SECTIONS[section].map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) =>
            cn(
              'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
              isActive
                ? 'bg-card text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </nav>
  )
}

/** Parent route: the section's tabs above the page. */
export function SectionLayout({ section }) {
  return (
    <>
      <SectionTabs section={section} />
      <Outlet />
    </>
  )
}
