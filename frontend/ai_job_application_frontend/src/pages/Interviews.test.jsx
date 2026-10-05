import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Route, Routes } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { MockInterviewButton } from '@/features/interviews/components/MockInterviewButton'
import { createTurnTracker } from '@/features/interviews/voice/gemini'
import { jsonResponse, mockApi, renderWithProviders } from '@/test/utils'

import InterviewPage from './InterviewPage'

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const JOB = { id: 'j1', title: 'React Native Developer', company: 'Acme' }
const USAGE = {
  interviews_month: { used: 2, limit: 10, left: 8 },
  interview_minutes: 6,
  interviews_available: true,
}

const base = {
  id: 'i1',
  round: 'mixed',
  difficulty: 'mid',
  minutes: 6,
  job: JOB,
  application_id: null,
  retry_of_id: null,
  verdict: null,
  overall_score: null,
  started_at: null,
  seconds_used: 0,
  created_at: '2026-10-04T10:00:00Z',
  error: null,
  deadline_at: null,
  ended_at: null,
  plan_task_id: 't1',
  report_task_id: null,
  thin_description: false,
  questions: [],
  turns: [],
  report: null,
  estimated_cost_usd: '0',
}

const TURNS = [
  {
    seq: 0,
    speaker: 'interviewer',
    text: 'How did you cut the crash rate?',
    original_text: null,
    offset_ms: 0,
    edited: false,
  },
  {
    seq: 1,
    speaker: 'candidate',
    text: 'I added better error handing',
    original_text: null,
    offset_ms: 4000,
    edited: false,
  },
]

function renderPage() {
  return renderWithProviders(
    <Routes>
      <Route path="/interviews/:interviewId" element={<InterviewPage />} />
      <Route path="/interviews" element={<p>All interviews</p>} />
    </Routes>,
    { route: '/interviews/i1' },
  )
}

/** Browser voice APIs: microphone, peer connection and the OpenAI data channel. */
function fakeVoice() {
  const track = { enabled: true, stop: vi.fn() }
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] }
  vi.stubGlobal('navigator', {
    ...navigator,
    mediaDevices: { getUserMedia: vi.fn(async () => stream) },
  })
  const sent = []
  class FakePeer {
    constructor() {
      FakePeer.last = this
      this.connectionState = 'new'
    }
    addTrack() {}
    createDataChannel() {
      this.dc = {
        readyState: 'open',
        send: (data) => sent.push(JSON.parse(data)),
        close: () => {},
      }
      setTimeout(() => this.dc.onopen?.(), 0)
      return this.dc
    }
    async createOffer() {
      return { type: 'offer', sdp: 'v=0 offer' }
    }
    async setLocalDescription() {}
    async setRemoteDescription(answer) {
      this.answer = answer
    }
    close() {}
    emit(event) {
      this.dc.onmessage?.({ data: JSON.stringify(event) })
    }
  }
  vi.stubGlobal('RTCPeerConnection', FakePeer)
  return { FakePeer, sent, track }
}

describe('Mock interview button', () => {
  it('plans an interview with the chosen round and opens the room', async () => {
    const fetchMock = mockApi({
      'GET /usage': USAGE,
      'POST /jobs/j1/interviews': () =>
        jsonResponse({ interview_id: 'i1', task_id: 't1' }, { status: 202 }),
    })
    renderWithProviders(
      <Routes>
        <Route
          path="/"
          element={<MockInterviewButton job={{ ...JOB, title: 'Senior React Native Developer' }} />}
        />
        <Route path="/interviews/:id" element={<p>Room opened</p>} />
      </Routes>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Mock interview' }))
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByLabelText('Level')).toHaveValue('senior') // from the title
    expect(await within(dialog).findByText(/8 of 10 interviews left/)).toBeInTheDocument()
    await userEvent.selectOptions(within(dialog).getByLabelText('Round'), 'technical')
    await userEvent.click(within(dialog).getByRole('button', { name: 'Prepare interview' }))

    expect(await screen.findByText('Room opened')).toBeInTheDocument()
    const post = fetchMock.mock.calls.find(([url]) => String(url).endsWith('/jobs/j1/interviews'))
    expect(JSON.parse(post[1].body)).toEqual({ round: 'technical', difficulty: 'senior' })
  })

  it('is disabled when no interviews are left this month', async () => {
    mockApi({ 'GET /usage': { ...USAGE, interviews_month: { used: 10, limit: 10, left: 0 } } })
    renderWithProviders(<MockInterviewButton job={JOB} />)

    await userEvent.click(screen.getByRole('button', { name: 'Mock interview' }))
    expect(await screen.findByText(/0 of 10 interviews left/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Prepare interview' })).toBeDisabled()
  })
})

describe('Interview room', () => {
  it('runs the call: token, SDP with OpenAI, transcript saved, hang-up at the deadline', async () => {
    const { FakePeer, sent } = fakeVoice()
    let ended = false
    const turnsPosted = []
    const fetchMock = mockApi({
      'GET /interviews/i1': () =>
        jsonResponse(
          ended
            ? {
                ...base,
                status: 'ended',
                turns: TURNS,
                questions: [
                  {
                    id: 'q1',
                    kind: 'skill',
                    topic: 'RN',
                    question: 'How did you cut the crash rate?',
                  },
                ],
              }
            : { ...base, status: 'ready' },
        ),
      'POST /interviews/i1/session': {
        client_secret: 'ek_test',
        expires_at: '2026-10-04T10:02:00Z',
        deadline_at: '2026-10-04T10:06:00Z',
        seconds_left: 2,
        model: 'gpt-realtime-mini',
        connect_url: 'https://rt.test/v1/realtime/calls',
        wrap_up: 'Time is almost up.',
        reconnect: false,
      },
      'POST https://rt.test/v1/realtime/calls': () => new Response('v=0 answer', { status: 201 }),
      'POST /interviews/i1/turns': (_url, init) => {
        turnsPosted.push(...JSON.parse(init.body).turns)
        return jsonResponse({ saved: 1 })
      },
      'POST /interviews/i1/finish': () => {
        ended = true
        return new Response(null, { status: 204 })
      },
    })
    renderPage()

    expect(await screen.findByText(/no recording/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Start interview' }))

    expect(await screen.findByText(/Live — speak naturally/)).toBeInTheDocument()
    const sdp = fetchMock.mock.calls.find(([url]) => String(url).includes('rt.test'))
    expect(sdp[1].headers.Authorization).toBe('Bearer ek_test')
    expect(sdp[1].body).toBe('v=0 offer')
    expect(FakePeer.last.answer.sdp).toBe('v=0 answer')
    await vi.waitFor(() => expect(sent[0]).toEqual({ type: 'response.create' }))
    // With 2 s left the wrap-up instruction is sent right away.
    await vi.waitFor(() =>
      expect(sent.some((e) => e.item?.content?.[0]?.text === 'Time is almost up.')).toBe(true),
    )

    // Conversation order comes from item events; transcripts may arrive in any order.
    FakePeer.last.emit({ type: 'conversation.item.added', item: { id: 'a1', type: 'message' } })
    FakePeer.last.emit({ type: 'conversation.item.added', item: { id: 'u1', type: 'message' } })
    FakePeer.last.emit({
      type: 'conversation.item.input_audio_transcription.completed',
      item_id: 'u1',
      transcript: 'I added better error handing',
    })
    FakePeer.last.emit({
      type: 'response.output_audio_transcript.done',
      item_id: 'a1',
      transcript: 'How did you cut the crash rate?',
    })
    expect(await screen.findByText('I added better error handing')).toBeInTheDocument()

    // At the deadline the room hangs up, saves the transcript and shows the review.
    expect(await screen.findByText('Transcript', {}, { timeout: 9000 })).toBeInTheDocument()
    expect(turnsPosted.map((t) => [t.seq, t.speaker])).toEqual([
      [1, 'candidate'],
      [0, 'interviewer'],
    ])
    expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/finish'))).toBe(true)
  }, 15000)

  it('lets the user correct an answer and ask for the report', async () => {
    const fetchMock = mockApi({
      'GET /interviews/i1': { ...base, status: 'ended', turns: TURNS },
      'PATCH /interviews/i1/turns/1': (_url, init) =>
        jsonResponse({ ...TURNS[1], text: JSON.parse(init.body).text, edited: true }),
      'POST /interviews/i1/report': () =>
        jsonResponse({ interview_id: 'i1', task_id: 't2' }, { status: 202 }),
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Correct answer 1' }))
    const box = screen.getByRole('textbox', { name: 'Correct answer 1' })
    await userEvent.clear(box)
    await userEvent.type(box, 'I added better error handling')
    await userEvent.click(screen.getByRole('button', { name: 'Save' }))
    await userEvent.click(screen.getByRole('button', { name: 'Get my report' }))

    await vi.waitFor(() => {
      const patch = fetchMock.mock.calls.find(([, init]) => init?.method === 'PATCH')
      expect(JSON.parse(patch[1].body)).toEqual({ text: 'I added better error handling' })
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith('/i1/report'))).toBe(true)
    })
    // Only the candidate's own lines can be corrected.
    expect(screen.queryByRole('button', { name: 'Correct answer 0' })).not.toBeInTheDocument()
  })

  it('shows the report with quotes, a stronger answer and practice options', async () => {
    mockApi({
      'GET /usage': USAGE,
      'GET /interviews/i1': {
        ...base,
        status: 'completed',
        verdict: 'almost',
        overall_score: 68,
        turns: TURNS,
        report: {
          verdict: 'almost',
          overall_score: 68,
          pdf_url: '/api/v1/files/abc',
          report: {
            summary: 'A good start with a concrete result.',
            questions: [
              {
                question_id: 'q1',
                question: 'How did you cut the crash rate?',
                score: 4,
                quote: 'I added better error handing',
                went_well: 'Concrete.',
                missing: 'A number.',
                better_answer: 'At Acme I cut crashes by 30%.',
              },
            ],
            strengths: ['Specific'],
            improvements: ['Use STAR'],
            skills_shown: ['React Native'],
            skills_not_shown: ['GraphQL'],
            communication: { clarity: 4, structure: 3, notes: 'Clear.' },
            practice_plan: ['Write one STAR story'],
            metrics: { average_answer_words: 5, filler_words: 1, top_fillers: ['um'] },
          },
        },
      },
    })
    renderPage()

    expect(await screen.findByText('68')).toBeInTheDocument()
    expect(screen.getByText('Almost there')).toBeInTheDocument()
    expect(screen.getByText('“I added better error handing”')).toBeInTheDocument()
    expect(screen.getByLabelText('4 out of 5')).toBeInTheDocument()
    expect(screen.getByText('Write one STAR story')).toBeInTheDocument()
    expect(screen.getByText('1 (um)')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Retry weak questions' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Practice again' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'PDF' })).toBeInTheDocument()
  })
})

/** Gemini Live in the browser: WebSocket + Web Audio, all faked. */
function fakeGemini() {
  const track = { enabled: true, stop: vi.fn() }
  const stream = { getTracks: () => [track], getAudioTracks: () => [track] }
  vi.stubGlobal('navigator', {
    ...navigator,
    mediaDevices: { getUserMedia: vi.fn(async () => stream) },
  })
  const node = () => ({ connect: vi.fn(), disconnect: vi.fn() })
  class FakeAudioContext {
    constructor(options) {
      this.sampleRate = options?.sampleRate ?? 48000
      this.currentTime = 0
      this.destination = {}
      this.audioWorklet = { addModule: vi.fn(async () => {}) }
      FakeAudioContext.made.push(this)
    }
    resume() {}
    close() {}
    createMediaStreamSource() {
      return node()
    }
    createGain() {
      return { ...node(), gain: { value: 1 } }
    }
    createBuffer(_channels, length, rate) {
      const data = new Float32Array(length)
      return { duration: length / rate, getChannelData: () => data }
    }
    createBufferSource() {
      const source = { ...node(), start: vi.fn(), stop: vi.fn() }
      FakeAudioContext.played.push(source)
      return source
    }
  }
  FakeAudioContext.made = []
  FakeAudioContext.played = []
  class FakeWorkletNode {
    constructor() {
      this.port = {}
      FakeWorkletNode.last = this
      Object.assign(this, node())
    }
  }
  class FakeSocket {
    static OPEN = 1
    constructor(url) {
      this.url = url
      this.readyState = 0
      this.sent = []
      FakeSocket.last = this
      setTimeout(() => {
        this.readyState = 1
        this.onopen?.()
      }, 0)
    }
    send(data) {
      this.sent.push(JSON.parse(data))
    }
    close() {
      this.readyState = 3
    }
    serve(message) {
      this.onmessage?.({ data: JSON.stringify(message) })
    }
  }
  vi.stubGlobal('AudioContext', FakeAudioContext)
  vi.stubGlobal('AudioWorkletNode', FakeWorkletNode)
  vi.stubGlobal('WebSocket', FakeSocket)
  URL.createObjectURL = vi.fn(() => 'blob:worklet')
  URL.revokeObjectURL = vi.fn()
  return { FakeSocket, FakeWorkletNode, FakeAudioContext, track }
}

describe('Gemini Live call', () => {
  it('groups streamed transcript pieces into turns in conversation order', () => {
    const order = []
    const turns = []
    const tracker = createTurnTracker({
      order: (key) => order.push(key),
      caption: () => {},
      turn: (key, speaker, text) => turns.push([key, speaker, text]),
    })
    tracker.interviewer('Hi! Tell me ')
    tracker.interviewer('about yourself.')
    tracker.endInterviewer()
    tracker.candidate('I build ')
    tracker.candidate('mobile apps.')
    tracker.interviewer('Great.') // the candidate's turn ends when the interviewer replies
    tracker.candidate(' Mostly React Native.') // late piece: still the same answer
    tracker.endInterviewer()

    expect(order).toEqual(['g-out-0', 'g-in-1', 'g-out-2'])
    expect(turns).toEqual([
      ['g-out-0', 'interviewer', 'Hi! Tell me about yourself.'],
      ['g-in-1', 'candidate', 'I build mobile apps.'],
      ['g-in-1', 'candidate', 'I build mobile apps. Mostly React Native.'],
      ['g-out-2', 'interviewer', 'Great.'],
    ])
  })

  it('connects with the token, streams 16 kHz audio, plays replies and saves the transcript', async () => {
    const { FakeSocket, FakeWorkletNode, FakeAudioContext } = fakeGemini()
    let ended = false
    const turnsPosted = []
    mockApi({
      'GET /interviews/i1': () =>
        jsonResponse(
          ended ? { ...base, status: 'ended', turns: TURNS } : { ...base, status: 'ready' },
        ),
      'POST /interviews/i1/session': {
        client_secret: 'auth_tokens/abc',
        expires_at: '2026-10-04T10:02:00Z',
        deadline_at: '2026-10-04T10:06:00Z',
        seconds_left: 3,
        model: 'gemini-2.5-flash-native-audio-latest',
        connect_url: 'wss://live.test/ws/Constrained',
        provider: 'gemini',
        wrap_up: 'Time is almost up.',
        reconnect: false,
      },
      'POST /interviews/i1/turns': (_url, init) => {
        turnsPosted.push(...JSON.parse(init.body).turns)
        return jsonResponse({ saved: 1 })
      },
      'POST /interviews/i1/finish': () => {
        ended = true
        return new Response(null, { status: 204 })
      },
    })
    renderPage()

    await userEvent.click(await screen.findByRole('button', { name: 'Start interview' }))
    await vi.waitFor(() => expect(FakeSocket.last?.sent.length).toBeGreaterThan(0))
    const socket = FakeSocket.last
    expect(socket.url).toBe('wss://live.test/ws/Constrained?access_token=auth_tokens%2Fabc')
    expect(socket.sent[0]).toEqual({
      setup: { model: 'models/gemini-2.5-flash-native-audio-latest' },
    })

    socket.serve({ setupComplete: {} })
    expect(await screen.findByText(/Live — speak naturally/)).toBeInTheDocument()
    // The interviewer is asked to start; with 3 s left the wrap-up note follows (no forced turn).
    expect(socket.sent[1].clientContent.turnComplete).toBe(true)
    await vi.waitFor(() =>
      expect(socket.sent.some((m) => m.clientContent?.turnComplete === false)).toBe(true),
    )

    // Microphone chunks go out as base64 16 kHz PCM.
    FakeWorkletNode.last.port.onmessage({
      data: { pcm: new Int16Array([1, 2, 3]).buffer, peak: 0.5 },
    })
    const audio = socket.sent.find((m) => m.realtimeInput)
    expect(audio.realtimeInput.audio.mimeType).toBe('audio/pcm;rate=16000')
    expect(audio.realtimeInput.audio.data).toBe(btoa(String.fromCharCode(1, 0, 2, 0, 3, 0)))

    // Interviewer audio is played; transcripts become captions and saved turns.
    socket.serve({
      serverContent: {
        modelTurn: {
          parts: [
            { inlineData: { mimeType: 'audio/pcm;rate=24000', data: btoa('\u0000\u0010\u0000 ') } },
          ],
        },
        outputTranscription: { text: 'How did you cut the crash rate?' },
      },
    })
    socket.serve({ serverContent: { turnComplete: true } })
    socket.serve({
      serverContent: { inputTranscription: { text: 'I added better error handing' } },
    })
    expect(await screen.findByText('How did you cut the crash rate?')).toBeInTheDocument()
    expect(FakeAudioContext.played.length).toBe(1)
    expect(FakeAudioContext.made.some((c) => c.sampleRate === 24000)).toBe(true)

    expect(await screen.findByText('Transcript', {}, { timeout: 9000 })).toBeInTheDocument()
    expect(turnsPosted.map((t) => [t.seq, t.speaker, t.text])).toEqual([
      [0, 'interviewer', 'How did you cut the crash rate?'],
      [1, 'candidate', 'I added better error handing'],
    ])
    expect(socket.readyState).toBe(3) // hung up
  }, 15000)
})
