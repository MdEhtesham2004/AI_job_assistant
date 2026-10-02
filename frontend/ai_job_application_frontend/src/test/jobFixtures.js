export function makeJob(overrides = {}) {
  return {
    id: 'j1',
    title: 'React Native Developer',
    company: 'ABC Technologies',
    location: 'Hyderabad, Telangana',
    is_remote: false,
    employment_type: 'FULLTIME',
    posted_at: '2026-09-30T10:00:00Z',
    apply_url: 'https://abctech.com/careers/1',
    source: 'jsearch',
    description_quality: 'complete',
    state: 'new',
    first_found_at: '2026-10-01T10:00:00Z',
    ...overrides,
  }
}

export function makeJobDetail(overrides = {}) {
  return {
    ...makeJob(),
    description: 'Responsibilities: build apps.',
    has_own_description: false,
    notes: null,
    company_domain: 'abctech.com',
    salary_min: null,
    salary_max: null,
    salary_currency: null,
    first_seen_at: '2026-10-01T10:00:00Z',
    last_seen_at: '2026-10-02T10:00:00Z',
    active_tasks: [],
    ...overrides,
  }
}

export function makeRun(overrides = {}) {
  return {
    id: 'r1',
    saved_search_id: null,
    task_id: 't1',
    status: 'succeeded',
    query: { keywords: 'React Native', location: 'Hyderabad', remote_only: false },
    results_count: 1,
    new_jobs_count: 1,
    error: null,
    created_at: '2026-10-02T10:00:00Z',
    finished_at: '2026-10-02T10:00:05Z',
    pages_loaded: 1,
    can_load_more: false,
    ...overrides,
  }
}

export const COUNTS = { new: 2, saved: 1, analyzed: 0, skipped: 3, archived: 0 }

export function makeSaved(overrides = {}) {
  return {
    id: 's1',
    name: 'RN Hyderabad',
    keywords: 'React Native',
    location: 'Hyderabad',
    experience: null,
    remote_only: false,
    country: 'in',
    schedule_cron: '0 8 * * *',
    is_active: true,
    last_run_at: null,
    next_run_at: '2026-10-03T02:30:00Z',
    created_at: '2026-10-02T10:00:00Z',
    ...overrides,
  }
}
