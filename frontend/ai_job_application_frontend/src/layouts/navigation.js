import {
  Activity,
  Radar,
  BellRing,
  Briefcase,
  ClipboardList,
  Contact,
  FileText,
  House,
  ListChecks,
  Search,
  Send,
  Settings,
  UserRound,
  Users,
} from 'lucide-react'

/**
 * Sidebar sections. Items are added as their phase is implemented (Phase 1 §8).
 * `adminOnly` sections are hidden for normal users; `badge` names a live counter.
 */
export const navigation = [
  {
    items: [
      { to: '/', label: 'Home', icon: House, end: true },
      { to: '/resumes', label: 'Resumes', icon: FileText },
      { to: '/tasks', label: 'Tasks', icon: ListChecks },
    ],
  },
  {
    title: 'Jobs',
    items: [
      { to: '/jobs/search', label: 'Find jobs', icon: Search },
      { to: '/jobs', label: 'Jobs', icon: Briefcase, end: true },
      { to: '/jobs/scan', label: 'Scan', icon: Radar },
      { to: '/jobs/saved', label: 'Saved searches', icon: BellRing },
      { to: '/applications', label: 'Applications', icon: ClipboardList },
    ],
  },
  {
    title: 'Outreach',
    items: [
      { to: '/contacts', label: 'Contacts', icon: Contact },
      { to: '/outbox', label: 'Outbox', icon: Send },
    ],
  },
  {
    title: 'Account',
    items: [
      { to: '/profile', label: 'Profile', icon: UserRound },
      { to: '/settings', label: 'Settings', icon: Settings },
    ],
  },
  {
    title: 'Admin',
    adminOnly: true,
    items: [
      { to: '/admin/users', label: 'Users', icon: Users, badge: 'pendingUsers' },
      { to: '/admin/system', label: 'System', icon: Activity },
    ],
  },
]
