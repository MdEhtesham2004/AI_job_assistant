import { NavLink, Outlet } from 'react-router'

import { cn } from '@/lib/utils'

import { SECTIONS } from './sections'

/** Tabs for the pages of one sidebar area (Phase 18); the pages themselves are unchanged. */
export function SectionTabs({ section }) {
  return (
    <nav aria-label="Section" className="mb-7 flex flex-wrap gap-x-6 border-b">
      {SECTIONS[section].map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          end={tab.end}
          className={({ isActive }) =>
            cn(
              '-mb-px border-b-2 pb-2.5 pt-1 text-sm font-semibold transition-colors',
              isActive
                ? 'border-primary text-foreground'
                : 'border-transparent text-muted-foreground hover:text-foreground',
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
