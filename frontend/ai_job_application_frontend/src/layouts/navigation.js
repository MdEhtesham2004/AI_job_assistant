import { Activity, House, Settings, UserRound, Users } from 'lucide-react'

/**
 * Sidebar sections. Items are added as their phase is implemented (Phase 1 §8).
 * `adminOnly` sections are hidden for normal users; `badge` names a live counter.
 */
export const navigation = [
  {
    items: [{ to: '/', label: 'Home', icon: House, end: true }],
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
      { to: '/admin/system', label: 'System Status', icon: Activity },
    ],
  },
]
