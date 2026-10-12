import {
  Activity,
  BarChart3,
  Briefcase,
  ClipboardList,
  FileText,
  GraduationCap,
  House,
  ScrollText,
  Send,
  Settings,
  Users,
} from 'lucide-react'

/**
 * Sidebar (Phase 18: grouped from 16 items to a short menu — every page is still reachable
 * through the section tabs, buttons or the bell).
 * - `also`: other paths that keep the item highlighted (pages shown as tabs of this item)
 * - `when`: shown only when the condition holds (see AppLayout)
 * - `adminOnly` sections are hidden for normal users; `badge` names a live counter.
 */
export const navigation = [
  {
    items: [
      { to: '/', label: 'Home', icon: House, end: true },
      { to: '/jobs', label: 'Jobs', icon: Briefcase },
      { to: '/applications', label: 'Applications', icon: ClipboardList },
      { to: '/interviews', label: 'Prepare', icon: GraduationCap, also: ['/skills'] },
      { to: '/contacts', label: 'Outreach', icon: Send, also: ['/outbox'], when: 'outreach' },
      { to: '/resumes', label: 'Resume', icon: FileText },
      { to: '/settings', label: 'Settings', icon: Settings, also: ['/profile'] },
    ],
  },
  {
    title: 'Admin',
    adminOnly: true,
    items: [
      { to: '/admin/users', label: 'Users', icon: Users, badge: 'pendingUsers' },
      { to: '/admin/analytics', label: 'Analytics', icon: BarChart3 },
      { to: '/admin/audit', label: 'Audit log', icon: ScrollText },
      { to: '/admin/system', label: 'System', icon: Activity },
    ],
  },
]
