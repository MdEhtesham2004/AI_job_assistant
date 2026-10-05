import { useCallback, useEffect, useRef, useState } from 'react'

import { interviewsApi } from './api'
import { connectGemini } from './voice/gemini'
import { connectOpenAI } from './voice/openai'

const WRAP_UP_AT = 30 // seconds left: the interviewer closes the conversation
const FLUSH_MS = 3000
const TAIL_MS = 2500 // after hanging up, wait for the last transcription events
const CANDIDATE_QUIET_MS = 700

const CONNECTORS = { openai: connectOpenAI, gemini: connectGemini }

/**
 * One voice call with the AI interviewer. The backend hands out a short-lived token for the
 * configured service (OpenAI Realtime over WebRTC, or Gemini Live over a WebSocket); audio
 * goes between the browser and that service only and is never stored. Transcript lines are
 * saved to the backend in small batches as they arrive.
 */
export function useRealtimeCall(interviewId, { firstSeq = 0, onEnded } = {}) {
  const [phase, setPhase] = useState('idle') // idle | connecting | live | ending | ended | dropped | error
  const [error, setError] = useState(null)
  const [secondsLeft, setSecondsLeft] = useState(null)
  const [captions, setCaptions] = useState([]) // [{ key, speaker, text, final }]
  const [speaking, setSpeaking] = useState(null) // 'interviewer' | 'candidate' | null
  const [muted, setMuted] = useState(false)

  const refs = useRef({})
  const r = refs.current

  const caption = useCallback((key, speaker, text, final) => {
    setCaptions((list) => {
      const index = list.findIndex((c) => c.key === key)
      const next = { key, speaker, text, final }
      if (index === -1) return [...list, next]
      const copy = [...list]
      copy[index] = { ...copy[index], ...next }
      return copy
    })
  }, [])

  const seqFor = (key) => {
    if (!r.seqs.has(key)) r.seqs.set(key, r.nextSeq++)
    return r.seqs.get(key)
  }

  const flush = useCallback(async () => {
    if (!r.queue?.length || r.flushing) return
    r.flushing = true
    const batch = r.queue.splice(0, 50)
    try {
      await interviewsApi.turns(interviewId, batch)
    } catch {
      r.queue.unshift(...batch) // try again with the next flush
    } finally {
      r.flushing = false
    }
  }, [interviewId, r])

  // Callbacks the connectors use.
  const on = {
    order: (key) => seqFor(key),
    caption: (key, speaker, text) => caption(key, speaker, text, false),
    turn: (key, speaker, text) => {
      const clean = (text ?? '').trim()
      if (!clean) return
      const seq = seqFor(key)
      r.queue = r.queue.filter((t) => t.seq !== seq) // a longer version replaces a shorter one
      r.queue.push({ seq, speaker, text: clean, offset_ms: Date.now() - r.startedAt })
      caption(key, speaker, clean, true)
    },
    speaking: (who, onlyIf) => {
      if (onlyIf) {
        setSpeaking((current) => (current === onlyIf ? who : current))
        return
      }
      setSpeaking(who)
      clearTimeout(r.quiet)
      if (who === 'candidate') {
        r.quiet = setTimeout(
          () => setSpeaking((current) => (current === 'candidate' ? null : current)),
          CANDIDATE_QUIET_MS,
        )
      }
    },
    dropped: () => {
      if (r.stopping) return
      teardown()
      setPhase('dropped')
    },
  }

  const teardown = () => {
    clearInterval(r.timer)
    clearInterval(r.flusher)
    clearTimeout(r.quiet)
    r.conn?.close()
    r.stream?.getTracks().forEach((t) => t.stop())
    r.conn = r.stream = null
  }

  const stop = useCallback(
    async (reason = 'user') => {
      if (!r.conn || r.stopping) return
      r.stopping = true
      setPhase('ending')
      r.stream?.getTracks().forEach((t) => (t.enabled = false)) // nothing more is heard
      await new Promise((resolve) => setTimeout(resolve, TAIL_MS))
      teardown()
      await flush()
      await flush()
      try {
        await interviewsApi.finish(interviewId)
      } catch {
        // the server ends the call on its own after the deadline
      }
      setSpeaking(null)
      setPhase('ended')
      onEnded?.(reason)
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refs are stable
    [interviewId, flush, onEnded],
  )

  const start = useCallback(async () => {
    setError(null)
    setPhase('connecting')
    r.stopping = false
    r.seqs = r.seqs ?? new Map()
    r.nextSeq = r.nextSeq ?? firstSeq
    r.queue = r.queue ?? []
    try {
      // Microphone first: no session (and no cost) if the browser refuses it.
      r.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      })
      const grant = await interviewsApi.session(interviewId)
      const connect = CONNECTORS[grant.provider] ?? connectOpenAI
      r.startedAt = r.startedAt ?? Date.now()
      r.conn = await connect({ grant, stream: r.stream, on, reconnect: grant.reconnect })

      r.endAt = Date.now() + grant.seconds_left * 1000
      // A reconnect with little time left still tells the new session to wrap up.
      r.wrapSent = false
      setSecondsLeft(grant.seconds_left)
      setPhase('live')
      r.flusher = setInterval(flush, FLUSH_MS)
      r.timer = setInterval(() => {
        const left = Math.max(0, Math.round((r.endAt - Date.now()) / 1000))
        setSecondsLeft(left)
        if (left <= WRAP_UP_AT && !r.wrapSent) {
          r.wrapSent = true
          r.conn?.wrapUp(grant.wrap_up)
        }
        if (left <= 0) stop('time')
      }, 250)
    } catch (err) {
      teardown()
      const denied = err?.name === 'NotAllowedError' || err?.name === 'SecurityError'
      setError(
        denied
          ? 'Microphone access was blocked. Allow it in the browser and try again.'
          : (err?.message ?? 'Could not start the call.'),
      )
      setPhase('error')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- refs are stable
  }, [interviewId, firstSeq, flush, stop])

  const toggleMute = () => {
    const track = r.stream?.getAudioTracks()[0]
    if (!track) return
    track.enabled = !track.enabled
    setMuted(!track.enabled)
  }

  // Leaving the page hangs up (the server ends the interview after the deadline).
  // eslint-disable-next-line react-hooks/exhaustive-deps -- unmount only
  useEffect(() => () => teardown(), [])

  return { phase, error, secondsLeft, captions, speaking, muted, start, stop, toggleMute }
}
