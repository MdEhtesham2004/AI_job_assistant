/**
 * Phase 18: one sidebar item per area; its pages become tabs (no feature removed).
 * `end`: only exact matches count (so /jobs is not active on /jobs/search).
 */
export const SECTIONS = {
  jobs: [
    { to: '/jobs', label: 'My jobs', end: true },
    { to: '/jobs/search', label: 'Find jobs' },
  ],
  // Phase 20: every automation in one place.
  automations: [
    { to: '/automations/searches', label: 'Scheduled searches' },
    { to: '/automations/pipeline', label: 'Apply pipeline' },
    { to: '/automations/digest', label: 'Daily digest' },
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
