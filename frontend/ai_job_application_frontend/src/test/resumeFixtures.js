export function makeVersion(overrides = {}) {
  return {
    id: 'v1',
    version_no: 1,
    kind: 'master',
    file_name: 'asha.pdf',
    mime_type: 'application/pdf',
    file_size: 20480,
    parse_status: 'parsed',
    parse_error: null,
    derived_from_id: null,
    is_active: true,
    ats_score: 72,
    created_at: '2026-10-02T10:00:00Z',
    ...overrides,
  }
}

export const PARSED = {
  name: 'Asha Verma',
  email: 'asha@example.com',
  phone: null,
  location: 'Pune',
  links: [],
  headline: 'React Native Developer',
  summary: 'Mobile developer with 4 years of experience.',
  skills: ['React Native', 'TypeScript'],
  experience: [
    {
      title: 'Senior Mobile Developer',
      company: 'Acme Apps',
      location: null,
      start: 'Jan 2022',
      end: 'Present',
      highlights: ['Built a payments app'],
    },
  ],
  education: [
    {
      degree: 'B.Tech Computer Science',
      institution: 'Pune University',
      start: '2016',
      end: '2020',
      details: null,
    },
  ],
  projects: [],
  certifications: [],
}

export function makeReport(overrides = {}) {
  return {
    id: 'rep',
    ats_score: 72,
    section_scores: { structure: 80, content: 70, keywords: 65, formatting: 75 },
    strengths: ['Quantified results'],
    missing_skills: ['GraphQL'],
    top_roles: ['Mobile Engineer'],
    suggestions: ['Add a projects section'],
    linkedin_summary: null,
    model: 'test/model',
    prompt_version: 'resume_ats.v1',
    created_at: '2026-10-02T10:00:00Z',
    updated_at: '2026-10-02T10:00:00Z',
    ...overrides,
  }
}
