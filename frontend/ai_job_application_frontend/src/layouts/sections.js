/**
 * Phase 18: one sidebar item per area; its pages become tabs (no feature removed).
 * `end`: only exact matches count (so /jobs is not active on /jobs/search).
 */
export const SECTIONS = {
  jobs: [
    { to: '/jobs', label: 'My jobs', end: true },
    { to: '/jobs/search', label: 'Find jobs' },
    { to: '/jobs/saved', label: 'Saved searches' },
  ],
  prepare: [
    { to: '/interviews', label: 'Mock interviews', end: true },
    { to: '/skills', label: 'Skill gaps' },
  ],
  outreach: [
    { to: '/contacts', label: 'Contacts' },
    { to: '/outbox', label: 'Outbox' },
  ],
  settings: [
    { to: '/profile', label: 'Profile' },
    { to: '/settings', label: 'Settings' },
  ],
}
