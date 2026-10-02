import { CircleCheck, Lightbulb, Target, TriangleAlert } from 'lucide-react'

import { cn } from '@/lib/utils'

import { scoreTone, TONE_BG, TONE_TEXT } from '../score'

const SECTIONS = [
  ['structure', 'Structure'],
  ['content', 'Content'],
  ['keywords', 'Keywords'],
  ['formatting', 'Formatting'],
]

export function ScoreGauge({ score, size = 132 }) {
  const stroke = 12
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const tone = scoreTone(score)
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden="true">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          className="fill-none stroke-muted"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - score / 100)}
          className={cn('fill-none transition-all', TONE_TEXT[tone])}
          stroke="currentColor"
        />
      </svg>
      <div
        className="absolute inset-0 flex flex-col items-center justify-center"
        role="img"
        aria-label={`ATS score ${score} out of 100`}
      >
        <span className={cn('text-3xl font-bold', TONE_TEXT[tone])}>{score}</span>
        <span className="text-xs text-muted-foreground">of 100</span>
      </div>
    </div>
  )
}

function SectionBar({ label, value }) {
  const tone = scoreTone(value)
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm">
        <span>{label}</span>
        <span className="font-medium">{value}</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-muted">
        <div className={cn('h-full rounded-full', TONE_BG[tone])} style={{ width: `${value}%` }} />
      </div>
    </div>
  )
}

function ItemList({ title, icon: Icon, items, tone, empty }) {
  return (
    <div>
      <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Icon className={cn('size-4', tone)} aria-hidden="true" />
        {title}
      </h3>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{empty}</p>
      ) : (
        <ul className="space-y-1.5 text-sm">
          {items.map((item) => (
            <li key={item} className="flex gap-2">
              <span className="text-muted-foreground">•</span>
              <span>{item}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function AtsReport({ report }) {
  return (
    <div className="space-y-6">
      <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
        <ScoreGauge score={report.ats_score} />
        <div className="w-full flex-1 space-y-3">
          {SECTIONS.map(([key, label]) => (
            <SectionBar key={key} label={label} value={report.section_scores[key] ?? 0} />
          ))}
        </div>
      </div>

      {report.top_roles.length > 0 && (
        <div>
          <h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Target className="size-4 text-primary" aria-hidden="true" />
            Best-fit roles
          </h3>
          <div className="flex flex-wrap gap-2">
            {report.top_roles.map((role) => (
              <span
                key={role}
                className="rounded-full bg-primary/10 px-3 py-1 text-sm text-primary"
              >
                {role}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <ItemList
          title="Strengths"
          icon={CircleCheck}
          tone="text-success"
          items={report.strengths}
          empty="None listed."
        />
        <ItemList
          title="Missing skills"
          icon={TriangleAlert}
          tone="text-warning"
          items={report.missing_skills}
          empty="No obvious gaps."
        />
      </div>
      <ItemList
        title="Suggestions"
        icon={Lightbulb}
        tone="text-primary"
        items={report.suggestions}
        empty="No suggestions."
      />
    </div>
  )
}
