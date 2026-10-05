import { Mic, MicOff, PhoneOff, RefreshCw } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { cn } from '@/lib/utils'

import { formatClock } from '../api'
import { useRealtimeCall } from '../useRealtimeCall'

/** Microphone level meter before joining: proves the mic works without starting a call. */
function MicCheck() {
  const [level, setLevel] = useState(0)
  const [state, setState] = useState('idle') // idle | on | blocked
  const stop = useRef(null)

  const check = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const context = new AudioContext()
      const analyser = context.createAnalyser()
      context.createMediaStreamSource(stream).connect(analyser)
      const data = new Uint8Array(analyser.frequencyBinCount)
      let frame
      const tick = () => {
        analyser.getByteFrequencyData(data)
        setLevel(Math.min(1, data.reduce((a, b) => a + b, 0) / data.length / 60))
        frame = requestAnimationFrame(tick)
      }
      tick()
      setState('on')
      stop.current = () => {
        cancelAnimationFrame(frame)
        stream.getTracks().forEach((t) => t.stop())
        context.close()
      }
    } catch {
      setState('blocked')
    }
  }

  useEffect(() => () => stop.current?.(), [])

  return (
    <div className="space-y-2">
      {state === 'idle' && (
        <Button type="button" variant="outline" onClick={check}>
          <Mic />
          Test microphone
        </Button>
      )}
      {state === 'on' && (
        <div className="flex items-center gap-3 text-sm">
          <Mic className="size-4 text-success" aria-hidden="true" />
          <div className="h-2 w-40 rounded-full bg-muted" aria-label="Microphone level">
            <div
              className="h-full rounded-full bg-success transition-[width]"
              style={{ width: `${Math.round(level * 100)}%` }}
            />
          </div>
          <span className="text-muted-foreground">Say something — the bar should move.</span>
        </div>
      )}
      {state === 'blocked' && (
        <p role="alert" className="text-sm text-destructive">
          Microphone access is blocked. Allow it for this site in the browser&apos;s address bar.
        </p>
      )}
    </div>
  )
}

export function PreJoin({ interview, onJoin }) {
  return (
    <Card className="max-w-2xl">
      <CardHeader>
        <CardTitle>Before you join</CardTitle>
        <CardDescription>
          Maya will run a {interview.minutes}-minute screening interview for{' '}
          <strong>{interview.job.title}</strong> at {interview.job.company}: a short introduction,
          three questions and time for your questions.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
          <li>Find a quiet place; headphones avoid echo.</li>
          <li>Answer in English, about a minute per answer. You can interrupt Maya by speaking.</li>
          <li>
            Your voice is processed by OpenAI to run the interview. We keep only the text transcript
            — no recording.
          </li>
          <li>The call ends automatically at {interview.minutes}:00.</li>
        </ul>
        {interview.thin_description && (
          <p className="text-warning">
            The job description is short, so the questions may be more general.
          </p>
        )}
        <MicCheck />
        <Button onClick={onJoin} size="default">
          <Mic />
          Start interview
        </Button>
      </CardContent>
    </Card>
  )
}

function Tile({ name, subtitle, active, initials, muted }) {
  return (
    <div
      className={cn(
        'flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border bg-card p-6 transition-shadow',
        active && 'shadow-[0_0_0_3px] shadow-primary/60',
      )}
    >
      <div
        className={cn(
          'flex size-20 items-center justify-center rounded-full bg-primary/10 text-2xl font-semibold text-primary',
          active && 'animate-pulse',
        )}
        aria-hidden="true"
      >
        {initials}
      </div>
      <div className="text-center">
        <p className="font-medium">{name}</p>
        <p className="text-xs text-muted-foreground">
          {muted ? 'Muted' : active ? 'Speaking…' : subtitle}
        </p>
      </div>
    </div>
  )
}

/** The live call. `autoStart` joins immediately (the user just clicked "Start"). */
export function LiveRoom({ interview, onEnded, autoStart = true }) {
  const firstSeq = interview.turns.length ? Math.max(...interview.turns.map((t) => t.seq)) + 1 : 0
  const call = useRealtimeCall(interview.id, { firstSeq, onEnded })
  const started = useRef(false)
  const captionsEnd = useRef(null)

  useEffect(() => {
    if (autoStart && !started.current) {
      started.current = true
      call.start()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- once
  }, [])

  useEffect(() => {
    captionsEnd.current?.scrollIntoView?.({ block: 'nearest' })
  }, [call.captions])

  const low = call.secondsLeft != null && call.secondsLeft <= 30

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground" aria-live="polite">
          {call.phase === 'connecting' && 'Connecting…'}
          {call.phase === 'live' && 'Live — speak naturally.'}
          {call.phase === 'ending' && 'Ending the call and saving the transcript…'}
          {call.phase === 'dropped' && 'The connection dropped.'}
        </p>
        <p
          className={cn('font-mono text-2xl tabular-nums', low && 'text-destructive')}
          role="timer"
          aria-label="Time left"
        >
          {call.secondsLeft == null
            ? formatClock(interview.minutes * 60)
            : formatClock(call.secondsLeft)}
        </p>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        <Tile
          name="Maya"
          subtitle="Interviewer"
          initials="M"
          active={call.speaking === 'interviewer'}
        />
        <Tile
          name="You"
          subtitle="Candidate"
          initials="You"
          active={call.speaking === 'candidate'}
          muted={call.muted}
        />
      </div>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm">Live captions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="max-h-56 space-y-2 overflow-y-auto text-sm" aria-live="polite">
            {call.captions.length === 0 && (
              <p className="text-muted-foreground">Captions appear here as you talk.</p>
            )}
            {call.captions.map((c) => (
              <p key={c.key} className={cn(!c.final && 'text-muted-foreground')}>
                <span className="font-medium">{c.speaker === 'interviewer' ? 'Maya' : 'You'}:</span>{' '}
                {c.text}
              </p>
            ))}
            <div ref={captionsEnd} />
          </div>
        </CardContent>
      </Card>

      {call.error && (
        <p role="alert" className="text-sm text-destructive">
          {call.error}
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        {call.phase === 'live' && (
          <>
            <Button variant="outline" onClick={call.toggleMute}>
              {call.muted ? <MicOff /> : <Mic />}
              {call.muted ? 'Unmute' : 'Mute'}
            </Button>
            <Button variant="destructive" onClick={() => call.stop('user')}>
              <PhoneOff />
              End interview
            </Button>
          </>
        )}
        {(call.phase === 'dropped' || call.phase === 'error' || call.phase === 'idle') && (
          <>
            <Button onClick={call.start}>
              <RefreshCw />
              {call.phase === 'idle' ? 'Join' : 'Reconnect'}
            </Button>
            <Button variant="outline" onClick={() => onEnded?.('user', true)}>
              <PhoneOff />
              End and review
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
