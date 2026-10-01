import { Activity, House } from 'lucide-react'

/** Sidebar items. New entries are added as their phase is implemented (Phase 1 §8). */
export const navigation = [
  { to: '/', label: 'Home', icon: House, end: true },
  { to: '/system', label: 'System Status', icon: Activity },
]
