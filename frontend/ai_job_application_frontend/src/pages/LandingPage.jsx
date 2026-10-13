import { Check, Mic } from 'lucide-react'
import { Link } from 'react-router'

import { cn } from '@/lib/utils'

/**
 * Phase 21: the public page at the domain root for visitors who are not signed in.
 * Every claim here maps to a feature that exists in the app. Product pictures are built
 * from the app's own visual language and labelled as examples — no invented numbers.
 */

// ---------- content ----------

const NAV = [
  ['Features', '#features'],
  ['How it works', '#how'],
  ['Questions', '#faq'],
]

const EXAMPLE_JOBS = [
  {
    score: 86,
    tone: 'text-success',
    title: 'Data Scientist',
    meta: 'Remote · posted today',
    note: 'Apply with your resume',
  },
  {
    score: 79,
    tone: 'text-success',
    title: 'Machine Learning Engineer',
    meta: 'Bengaluru · posted yesterday',
    note: 'Tailored resume ready',
    draft: true,
  },
  {
    score: 64,
    tone: 'text-warning',
    title: 'Analytics Engineer',
    meta: 'Hyderabad · 3 days ago',
    note: 'Weak match',
  },
  {
    score: 38,
    tone: 'text-destructive',
    title: 'Senior Data Engineer',
    meta: 'Pune · last week',
    note: 'Skipped for you',
  },
]

/** The feature index, by stage of a job search. */
const FEATURES = [
  {
    stage: 'Find jobs',
    items: [
      [
        'Job search across popular job boards',
        'Filter by role, place, experience, remote and date posted.',
      ],
      [
        'Scheduled searches',
        'Your searches run by themselves every day and tell you only about new jobs.',
      ],
      [
        'Recruiters from hiring posts',
        'Public LinkedIn posts that ask for resumes become jobs with the recruiter’s email — and the post as proof.',
      ],
      [
        'Add any job',
        'Paste a job description from anywhere, or import a spreadsheet of jobs you already track.',
      ],
    ],
  },
  {
    stage: 'Choose the right ones',
    items: [
      [
        'Match score from 0 to 100',
        'Every job is compared with your resume across skills, experience, technology, education and location.',
      ],
      [
        'A clear recommendation',
        'Apply as you are, tailor your resume first, or skip — with the reasons spelled out.',
      ],
      ['Daily digest', 'Your best new matches each morning, in the app and by email.'],
      [
        'Skill gaps',
        'The skills your target jobs keep asking for that your resume doesn’t show yet.',
      ],
    ],
  },
  {
    stage: 'Get your resume ready',
    items: [
      ['ATS check', 'How well applicant-tracking systems read your resume, and what to fix.'],
      [
        'Improved resume',
        'A cleaner version of your resume, plus a LinkedIn summary written from it.',
      ],
      [
        'Tailored resume per job',
        'Reordered and reworded for each job — only from facts already in your resume.',
      ],
      [
        'Cover letters',
        'Written for the job and the recruiter, checked against your resume, ready as PDF.',
      ],
    ],
  },
  {
    stage: 'Apply',
    items: [
      [
        'Emails from your own Gmail',
        'Applications go out from your address with your resume and cover letter attached.',
      ],
      [
        'Approve before anything is sent',
        'Every draft waits in your outbox; edit it, approve it, or reject it.',
      ],
      [
        'Apply pipeline',
        'Prepares applications for every job with an approved recruiter — on a click or daily.',
      ],
      [
        'Screening answers',
        'Answers to the usual application-form questions, written from your resume.',
      ],
      [
        'Safe sending',
        'Daily limits, gaps between emails, address checks and a do-not-contact list.',
      ],
    ],
  },
  {
    stage: 'Follow up',
    items: [
      [
        'Replies read for you',
        'Interview invitations, rejections and questions are recognised and update your board.',
      ],
      [
        'Polite follow-ups',
        'A follow-up drafted after the number of days you choose — cancelled if they reply.',
      ],
      [
        'Applications board',
        'Every application from to-do to offer, with notes and a full history.',
      ],
      ['What’s working', 'Response rates by job source and by resume version, and exports to CSV.'],
    ],
  },
  {
    stage: 'Win the interview',
    items: [
      [
        'Interview prep pack',
        'Likely questions, your own stories in STAR form, honest answers to gaps and questions to ask.',
      ],
      [
        'AI mock interview',
        'A short voice interview for the job you applied to, with a scored report afterwards.',
      ],
    ],
  },
]

const STEPS = [
  ['Upload your resume', 'It’s read once and becomes the source for everything that follows.'],
  ['Bring jobs in', 'Search, schedule searches, or let hiring posts bring recruiters to you.'],
  ['See what fits', 'Every job gets a match score, so the good ones rise to the top.'],
  [
    'Approve the drafts',
    'Tailored resume, cover letter and email are prepared; you approve each one.',
  ],
  ['Follow through', 'Replies, follow-ups and interview practice are handled in the same place.'],
]

const CONTROL = [
  ['Nothing is sent without you', 'Drafts wait in your outbox until you approve them.'],
  [
    'Only your own facts',
    'Documents are written from your resume; anything it can’t back up is left out.',
  ],
  ['Your Gmail, your sender', 'Replies come straight to your inbox, not to us.'],
  ['Costs stay small', 'Searches are shared and cached, and paid lookups have monthly limits.'],
]

const FAQ = [
  [
    'Will it send emails on its own?',
    'No. Every email — first application or follow-up — waits in your outbox until you approve it.',
  ],
  [
    'Do I need a Gmail account?',
    'Only to send applications by email. Searching, scoring, resumes, cover letters and interview practice work without it.',
  ],
  [
    'Where do the jobs come from?',
    'From job-board search, from public LinkedIn hiring posts, and from jobs you paste or import yourself.',
  ],
  [
    'Will it make things up on my resume?',
    'No. Tailored resumes and cover letters are checked against your resume, and claims it can’t find are removed.',
  ],
  [
    'Why does my account need approval?',
    'New accounts are reviewed so the service stays fast and costs stay under control. You’ll see a waiting page until then.',
  ],
  ['Can I use it on my phone?', 'Yes — every page works on a phone, including approving drafts.'],
]

// ---------- pieces ----------

function Wordmark({ className }) {
  return (
    <span className={cn('font-extrabold tracking-tight', className)}>
      FindMy<span className="text-primary">Jobs</span>
    </span>
  )
}

function Cta({ to, children, quiet = false, className }) {
  const style = cn(
    'inline-flex h-11 items-center rounded-md px-5 text-[0.95rem] font-semibold transition-colors',
    quiet
      ? 'border border-foreground/20 hover:border-primary/50 hover:bg-accent'
      : 'bg-primary text-primary-foreground hover:bg-primary/88',
    className,
  )
  // In-page anchors are plain links; app pages use the router.
  return to.startsWith('#') ? (
    <a href={to} className={style}>
      {children}
    </a>
  ) : (
    <Link to={to} className={style}>
      {children}
    </Link>
  )
}

function SectionTitle({ id, children, intro }) {
  return (
    <div className="max-w-[40rem]">
      <h2
        id={id}
        className="text-[1.9rem] font-bold leading-tight tracking-tight sm:text-[2.35rem]"
      >
        {children}
      </h2>
      {intro && <p className="mt-3 text-[1.05rem] text-muted-foreground">{intro}</p>}
    </div>
  )
}

/** Hero picture: the ranked list, with an email draft laid over it. */
function HeroPicture() {
  return (
    <div className="relative pb-28 sm:pb-16">
      <figure className="rounded-lg border bg-card">
        <figcaption className="flex items-center justify-between border-b px-5 py-3 text-sm">
          <span className="font-semibold">Your matches this morning</span>
          <span className="text-muted-foreground">Example</span>
        </figcaption>
        <ol>
          {EXAMPLE_JOBS.map((job) => (
            <li
              key={job.title}
              className={cn(
                'grid grid-cols-[3.25rem_minmax(0,1fr)] gap-x-4 border-b px-5 py-3.5 last:border-b-0',
                job.draft && 'bg-accent/70',
              )}
            >
              <span
                className={cn(
                  'tabular text-[1.85rem] font-bold leading-none tracking-tight',
                  job.tone,
                )}
              >
                {job.score}
              </span>
              <span className="min-w-0">
                <span className="block truncate font-semibold">{job.title}</span>
                <span className="block truncate text-sm text-muted-foreground">{job.meta}</span>
                <span
                  className={cn(
                    'block text-xs font-semibold',
                    job.draft ? 'text-primary' : job.tone,
                  )}
                >
                  {job.note}
                </span>
              </span>
            </li>
          ))}
        </ol>
      </figure>
      <div
        aria-hidden="true"
        className="absolute bottom-0 right-0 w-[88%] rounded-lg border bg-card p-4 text-sm shadow-[0_18px_40px_-24px_rgb(24_33_43/0.45)] sm:-right-6 sm:w-[78%]"
      >
        <p className="text-xs text-muted-foreground">To: priya.hr@… · Machine Learning Engineer</p>
        <p className="mt-1.5 font-semibold">Application for Machine Learning Engineer</p>
        <p className="mt-1 line-clamp-2 text-muted-foreground">
          Dear Priya, I saw your post about the ML Engineer role and I’d like to apply. My resume
          and cover letter are attached…
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="rounded-sm bg-muted px-1.5 py-0.5 text-xs">Resume.pdf</span>
          <span className="rounded-sm bg-muted px-1.5 py-0.5 text-xs">Cover Letter.pdf</span>
          <span className="ml-auto rounded-md bg-primary px-2.5 py-1 text-xs font-semibold text-primary-foreground">
            Approve &amp; send
          </span>
        </div>
      </div>
    </div>
  )
}

const BREAKDOWN = [
  ['Skills', 84],
  ['Experience', 72],
  ['Technology', 90],
  ['Education', 100],
  ['Location', 60],
]

function ScorePicture() {
  return (
    <figure className="rounded-lg border bg-card p-6" aria-label="Example match score">
      <div className="flex items-end gap-4">
        <span className="tabular text-[4.5rem] font-bold leading-[0.85] tracking-tight text-success">
          79
        </span>
        <span className="pb-1">
          <span className="block font-semibold">Tailor your resume first</span>
          <span className="block text-sm text-muted-foreground">
            Machine Learning Engineer · Example
          </span>
        </span>
      </div>
      <dl className="mt-6 space-y-2.5">
        {BREAKDOWN.map(([label, value]) => (
          <div
            key={label}
            className="grid grid-cols-[6.5rem_minmax(0,1fr)_2.5rem] items-center gap-3 text-sm"
          >
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="h-1.5 rounded-full bg-muted">
              <span
                className="block h-full rounded-full bg-foreground/80"
                style={{ width: `${value}%` }}
              />
            </dd>
            <dd className="tabular text-right font-medium">{value}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-5 border-t pt-4 text-sm text-muted-foreground">
        Missing: <span className="text-foreground">MLOps, Kubernetes</span> — shown in your skill
        gaps.
      </p>
    </figure>
  )
}

function OutboxPicture() {
  return (
    <figure className="rounded-lg border bg-card" aria-label="Example outbox">
      <figcaption className="flex flex-wrap gap-x-5 border-b px-5 pt-3 text-sm font-semibold">
        <span className="border-b-2 border-primary pb-2.5">Ready for approval 3</span>
        <span className="pb-2.5 text-muted-foreground">Scheduled 1</span>
        <span className="pb-2.5 text-muted-foreground">Sent 12</span>
      </figcaption>
      {[
        ['Data Scientist', 'hiring@northwind…', 'Approved contact'],
        ['ML Engineer', 'priya.hr@…', 'New contact from a LinkedIn post'],
        ['Analytics Engineer', 'talent@contoso…', 'Follow-up, day 7'],
      ].map(([title, to, note]) => (
        <div key={title} className="flex items-center gap-4 border-b px-5 py-3.5 last:border-b-0">
          <span className="min-w-0 flex-1">
            <span className="block truncate font-semibold">{title}</span>
            <span className="block truncate text-sm text-muted-foreground">
              {to} · {note}
            </span>
          </span>
          <span className="shrink-0 rounded-md border border-foreground/15 px-2.5 py-1 text-xs font-semibold">
            Review
          </span>
        </div>
      ))}
      <p className="border-t px-5 py-3 text-xs text-muted-foreground">
        Sent today 4 of 25 · at least 90 seconds between emails
      </p>
    </figure>
  )
}

function InterviewPicture() {
  return (
    <figure className="rounded-lg border bg-card p-6" aria-label="Example mock interview report">
      <div className="flex items-center gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-accent text-primary">
          <Mic className="size-5" aria-hidden="true" />
        </span>
        <span className="min-w-0">
          <span className="block font-semibold">Mock interview · 6 minutes</span>
          <span className="block text-sm text-muted-foreground">
            Data Scientist · first round · Example
          </span>
        </span>
        <span className="tabular ml-auto text-[2.25rem] font-bold leading-none text-warning">
          71
        </span>
      </div>
      <ul className="mt-5 space-y-2 border-t pt-4 text-sm">
        {[
          'Clear answer on your churn-model project',
          'Give numbers when you describe impact',
          'Prepare a question about the team’s data stack',
        ].map((line, index) => (
          <li key={line} className="flex gap-2">
            <Check
              className={cn(
                'mt-0.5 size-4 shrink-0',
                index === 0 ? 'text-success' : 'text-muted-foreground',
              )}
              aria-hidden="true"
            />
            {line}
          </li>
        ))}
      </ul>
    </figure>
  )
}

function Spotlight({ title, text, points, picture, flip = false }) {
  return (
    <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-2 lg:gap-16 [&>*]:min-w-0">
      <div className={cn(flip && 'lg:order-2')}>
        <h3 className="text-[1.6rem] font-bold leading-tight tracking-tight">{title}</h3>
        <p className="mt-3 max-w-[34rem] text-[1.025rem] text-muted-foreground">{text}</p>
        <ul className="mt-5 space-y-2">
          {points.map((point) => (
            <li key={point} className="flex gap-2.5 text-[0.975rem]">
              <Check className="mt-1 size-4 shrink-0 text-primary" aria-hidden="true" />
              {point}
            </li>
          ))}
        </ul>
      </div>
      <div className={cn(flip && 'lg:order-1')}>{picture}</div>
    </div>
  )
}

// ---------- page ----------

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-card focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 bg-background/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-8 px-5 sm:px-8">
          <Wordmark className="text-[1.2rem]" />
          <nav
            className="hidden gap-6 text-sm font-medium text-muted-foreground md:flex"
            aria-label="Sections"
          >
            {NAV.map(([label, href]) => (
              <a key={href} href={href} className="hover:text-foreground">
                {label}
              </a>
            ))}
          </nav>
          <nav
            className="ml-auto flex items-center gap-1.5 text-sm font-semibold"
            aria-label="Account"
          >
            <Link to="/login" className="rounded-md px-3 py-2 hover:bg-accent">
              Sign in
            </Link>
            <Link
              to="/register"
              className="rounded-md bg-primary px-3 py-2 text-primary-foreground hover:bg-primary/88"
            >
              Create account
            </Link>
          </nav>
        </div>
      </header>

      <main id="main">
        {/* Hero */}
        <section className="mx-auto grid max-w-6xl items-center gap-14 px-5 pb-24 pt-10 sm:px-8 lg:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)] lg:pt-20">
          <div>
            <h1 className="text-[2.6rem] font-bold leading-[1.03] tracking-[-0.025em] sm:text-[3.6rem] lg:text-[4.1rem]">
              Find the jobs that fit you, and apply without the busywork.
            </h1>
            <p className="mt-6 max-w-[35rem] text-[1.1rem] leading-relaxed text-muted-foreground">
              FindMyJobs finds openings and the recruiters behind them, scores every job against
              your resume, and prepares tailored applications from your own Gmail. You approve
              everything before it goes out.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Cta to="/register">Create your account</Cta>
              <Cta to="#features" quiet>
                See what it does
              </Cta>
            </div>
            <ul className="mt-8 flex flex-wrap gap-x-6 gap-y-2 text-sm text-muted-foreground">
              {[
                'Match score for every job',
                'Tailored resume and cover letter',
                'AI mock interviews',
              ].map((item) => (
                <li key={item} className="flex items-center gap-1.5">
                  <Check className="size-4 text-primary" aria-hidden="true" />
                  {item}
                </li>
              ))}
            </ul>
          </div>
          <HeroPicture />
        </section>

        {/* Feature index */}
        <section
          id="features"
          className="scroll-mt-16 border-t bg-sidebar"
          aria-labelledby="features-title"
        >
          <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
            <SectionTitle
              id="features-title"
              intro="From the first search to the final interview — one place, built around your resume."
            >
              Everything a job search needs
            </SectionTitle>
            <div className="mt-12 divide-y divide-foreground/10 border-y border-foreground/15">
              {FEATURES.map((group) => (
                <div
                  key={group.stage}
                  className="grid gap-6 py-8 lg:grid-cols-[14rem_minmax(0,1fr)] lg:gap-12"
                >
                  <h3 className="text-[1.2rem] font-bold">{group.stage}</h3>
                  <dl className="grid gap-x-10 gap-y-6 sm:grid-cols-2">
                    {group.items.map(([title, text]) => (
                      <div key={title}>
                        <dt className="font-semibold">{title}</dt>
                        <dd className="mt-1 text-[0.95rem] text-muted-foreground">{text}</dd>
                      </div>
                    ))}
                  </dl>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Spotlights */}
        <section
          className="mx-auto max-w-6xl space-y-24 px-5 py-24 sm:px-8"
          aria-label="Highlights"
        >
          <Spotlight
            title="Know which jobs are worth your time"
            text="Each job is compared with your resume and scored from 0 to 100, with the reasons behind the number."
            points={[
              'Breakdown by skills, experience, technology, education and location',
              'Apply, tailor first, or skip — a recommendation for every job',
              'Score a whole list at once; scores are reused, not recalculated',
            ]}
            picture={<ScorePicture />}
          />
          <Spotlight
            flip
            title="Applications that wait for your yes"
            text="Tailored resume, cover letter and email are prepared for you and sent from your own Gmail — only after you approve."
            points={[
              'Edit any draft before approving it',
              'Daily limits and gaps between emails keep your account safe',
              'Follow-ups are drafted for you and cancelled when someone replies',
            ]}
            picture={<OutboxPicture />}
          />
          <Spotlight
            title="Walk into the interview prepared"
            text="When an application reaches the interview stage, a prep pack is made for it. Then practise out loud."
            points={[
              'Likely questions and your own stories, written from your resume',
              'A voice mock interview tailored to the job',
              'A scored report with what went well and what to improve',
            ]}
            picture={<InterviewPicture />}
          />
        </section>

        {/* How it works — a real sequence, so it is numbered */}
        <section id="how" className="scroll-mt-16 border-y bg-sidebar" aria-labelledby="how-title">
          <div className="mx-auto max-w-6xl px-5 py-20 sm:px-8">
            <SectionTitle id="how-title">How it works</SectionTitle>
            <ol className="mt-12 grid gap-x-8 gap-y-10 sm:grid-cols-2 lg:grid-cols-5">
              {STEPS.map(([title, text], index) => (
                <li key={title} className="border-t-2 border-foreground pt-4">
                  <span className="tabular text-sm font-semibold text-muted-foreground">
                    {index + 1}
                  </span>
                  <h3 className="mt-1 text-[1.1rem] font-bold">{title}</h3>
                  <p className="mt-2 text-[0.95rem] text-muted-foreground">{text}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        {/* Control and trust */}
        <section className="mx-auto max-w-6xl px-5 py-20 sm:px-8" aria-labelledby="control">
          <div className="grid gap-12 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <h2
              id="control"
              className="max-w-[22rem] text-[1.9rem] font-bold leading-tight tracking-tight sm:text-[2.35rem]"
            >
              It does the legwork. You stay in charge.
            </h2>
            <dl className="grid gap-x-10 gap-y-8 sm:grid-cols-2">
              {CONTROL.map(([title, text]) => (
                <div key={title}>
                  <dt className="font-semibold">{title}</dt>
                  <dd className="mt-1.5 text-[0.95rem] text-muted-foreground">{text}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        {/* FAQ */}
        <section id="faq" className="scroll-mt-16 border-t" aria-labelledby="faq-title">
          <div className="mx-auto grid max-w-6xl gap-10 px-5 py-20 sm:px-8 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
            <SectionTitle id="faq-title">Questions</SectionTitle>
            <div className="divide-y border-y">
              {FAQ.map(([question, answer]) => (
                <details key={question} className="group py-4">
                  <summary className="flex cursor-pointer list-none items-center justify-between gap-4 font-semibold [&::-webkit-details-marker]:hidden">
                    {question}
                    <span
                      aria-hidden="true"
                      className="text-xl leading-none text-muted-foreground transition-transform group-open:rotate-45 motion-reduce:transition-none"
                    >
                      +
                    </span>
                  </summary>
                  <p className="mt-2 max-w-[38rem] text-[0.975rem] text-muted-foreground">
                    {answer}
                  </p>
                </details>
              ))}
            </div>
          </div>
        </section>

        {/* Closing call to action */}
        <section className="mx-auto max-w-6xl px-5 pb-20 sm:px-8">
          <div className="flex flex-col items-start justify-between gap-6 rounded-lg bg-foreground px-8 py-12 text-background sm:flex-row sm:items-center">
            <div>
              <p className="max-w-[32rem] text-[1.6rem] font-bold leading-snug tracking-tight">
                Spend your time on interviews, not on copy‑pasting applications.
              </p>
              <p className="mt-2 text-sm text-background/70">
                New accounts are reviewed before first use.
              </p>
            </div>
            <Link
              to="/register"
              className="inline-flex h-11 shrink-0 items-center rounded-md bg-background px-5 font-semibold text-foreground hover:bg-background/90"
            >
              Create your account
            </Link>
          </div>
        </section>
      </main>

      <footer className="border-t">
        <div className="mx-auto grid max-w-6xl gap-8 px-5 py-10 text-sm sm:grid-cols-[minmax(0,1fr)_auto] sm:px-8">
          <div>
            <Wordmark className="text-[1.05rem]" />
            <p className="mt-2 max-w-[24rem] text-muted-foreground">
              A job-search assistant that finds, scores and prepares — and lets you decide.
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-6 gap-y-2 font-medium" aria-label="Footer">
            <a href="#features" className="hover:text-primary">
              Features
            </a>
            <a href="#how" className="hover:text-primary">
              How it works
            </a>
            <a href="#faq" className="hover:text-primary">
              Questions
            </a>
            <Link to="/login" className="hover:text-primary">
              Sign in
            </Link>
            <Link to="/register" className="hover:text-primary">
              Create account
            </Link>
          </nav>
          <p className="text-muted-foreground sm:col-span-2">
            © {new Date().getFullYear()} FindMyJobs
          </p>
        </div>
      </footer>
    </div>
  )
}
