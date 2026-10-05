/**
 * Gemini Live over a WebSocket (single-use token, session locked by the backend).
 *
 * Microphone → AudioWorklet → 16 kHz 16-bit PCM chunks (~100 ms) → `realtimeInput`.
 * Server audio (24 kHz PCM) is scheduled gap-free on an AudioContext; `interrupted`
 * (the candidate talked over the interviewer) stops what is still queued.
 * Transcripts arrive in pieces: they are grouped into turns here.
 */

const IN_RATE = 16000
const OUT_RATE = 24000
const SPEAKING_LEVEL = 0.06

// Runs on the audio thread: average-downsample to 16 kHz, send 100 ms Int16 chunks.
const WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  constructor() {
    super()
    this.step = sampleRate / ${IN_RATE}
    this.pos = 0; this.sum = 0; this.count = 0; this.out = []
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0]
    if (!channel) return true
    for (let i = 0; i < channel.length; i++) {
      this.sum += channel[i]; this.count++; this.pos++
      if (this.pos >= this.step) {
        this.out.push(this.sum / this.count)
        this.pos -= this.step; this.sum = 0; this.count = 0
      }
    }
    if (this.out.length >= ${IN_RATE / 10}) {
      const pcm = new Int16Array(this.out.length)
      let peak = 0
      for (let i = 0; i < this.out.length; i++) {
        const s = Math.max(-1, Math.min(1, this.out[i]))
        peak = Math.max(peak, Math.abs(s))
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff
      }
      this.out = []
      this.port.postMessage({ pcm: pcm.buffer, peak }, [pcm.buffer])
    }
    return true
  }
}
registerProcessor('pcm-capture', PcmCapture)
`

export function toBase64(buffer) {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000))
  }
  return btoa(binary)
}

function fromBase64Pcm(data) {
  const binary = atob(data)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  const pcm = new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2))
  const samples = new Float32Array(pcm.length)
  for (let i = 0; i < pcm.length; i++) samples[i] = pcm[i] / 0x8000
  return samples
}

/** Group streamed transcript pieces into conversation turns (in conversation order). */
export function createTurnTracker(on) {
  let n = 0
  let input = null // current candidate turn: { key, text }
  let output = null // current interviewer turn
  let lastInput = null
  const start = (speaker) => {
    const key = `g-${speaker === 'candidate' ? 'in' : 'out'}-${n++}`
    on.order(key)
    return { key, text: '' }
  }
  return {
    candidate(text) {
      if (!text) return
      // A late piece of the answer while the interviewer already replies: same turn.
      const target = !input && output && lastInput ? lastInput : (input ??= start('candidate'))
      target.text += text
      if (target === lastInput) on.turn(target.key, 'candidate', target.text)
      else on.caption(target.key, 'candidate', target.text)
    },
    interviewer(text) {
      if (input) {
        on.turn(input.key, 'candidate', input.text)
        lastInput = input
        input = null
      }
      output ??= start('interviewer')
      if (text) {
        output.text += text
        on.caption(output.key, 'interviewer', output.text)
      }
    },
    endInterviewer() {
      if (output?.text) on.turn(output.key, 'interviewer', output.text)
      output = null
    },
    flush() {
      if (input?.text) on.turn(input.key, 'candidate', input.text)
      if (output?.text) on.turn(output.key, 'interviewer', output.text)
      input = output = null
    },
  }
}

export async function connectGemini({ grant, stream, on, reconnect = false }) {
  // --- playback (24 kHz) ---
  const player = new AudioContext({ sampleRate: OUT_RATE })
  await player.resume?.()
  let playAt = 0
  const playing = new Set()
  const play = (data) => {
    const samples = fromBase64Pcm(data)
    if (!samples.length) return
    const buffer = player.createBuffer(1, samples.length, OUT_RATE)
    buffer.getChannelData(0).set(samples)
    const source = player.createBufferSource()
    source.buffer = buffer
    source.connect(player.destination)
    playAt = Math.max(playAt, player.currentTime + 0.04)
    source.start(playAt)
    playAt += buffer.duration
    playing.add(source)
    on.speaking('interviewer')
    source.onended = () => {
      playing.delete(source)
      if (!playing.size) on.speaking(null, 'interviewer')
    }
  }
  const silence = () => {
    playing.forEach((s) => {
      try {
        s.stop()
      } catch {
        // already stopped
      }
    })
    playing.clear()
    playAt = 0
    on.speaking(null, 'interviewer')
  }

  // --- WebSocket ---
  const ws = new WebSocket(
    `${grant.connect_url}?access_token=${encodeURIComponent(grant.client_secret)}`,
  )
  ws.binaryType = 'arraybuffer'
  const send = (message) => ws.readyState === WebSocket.OPEN && ws.send(JSON.stringify(message))
  const say = (text, turnComplete) =>
    send({ clientContent: { turns: [{ role: 'user', parts: [{ text }] }], turnComplete } })
  const turns = createTurnTracker(on)
  let ready = false
  let closing = false

  const opened = new Promise((resolve, reject) => {
    ws.onopen = () => send({ setup: { model: `models/${grant.model}` } })
    ws.onerror = () => !ready && reject(new Error('Could not connect to the voice service.'))
    ws.onclose = (event) => {
      if (!ready) reject(new Error(event.reason || 'The voice service closed the connection.'))
      else if (!closing) on.dropped()
    }
    ws.onmessage = (event) => {
      let message
      try {
        const text =
          typeof event.data === 'string' ? event.data : new TextDecoder().decode(event.data)
        message = JSON.parse(text)
      } catch {
        return
      }
      if (message.setupComplete) {
        ready = true
        // The interviewer speaks first (or picks up where a dropped call stopped).
        say(
          reconnect
            ? '(The call was reconnected. Continue the interview from where it stopped.)'
            : '(The candidate has joined the call. Start the interview.)',
          true,
        )
        resolve()
        return
      }
      const content = message.serverContent
      if (!content) return
      if (content.inputTranscription?.text) turns.candidate(content.inputTranscription.text)
      for (const part of content.modelTurn?.parts ?? []) {
        if (part.inlineData?.data) {
          turns.interviewer('')
          play(part.inlineData.data)
        }
      }
      if (content.outputTranscription?.text) turns.interviewer(content.outputTranscription.text)
      if (content.interrupted) {
        silence()
        turns.endInterviewer()
      }
      if (content.turnComplete) turns.endInterviewer()
    }
  })

  // --- microphone capture (16 kHz) ---
  const mic = new AudioContext()
  const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }))
  await mic.audioWorklet.addModule(url)
  URL.revokeObjectURL?.(url)
  const source = mic.createMediaStreamSource(stream)
  const capture = new AudioWorkletNode(mic, 'pcm-capture')
  const sink = mic.createGain()
  sink.gain.value = 0 // keeps the worklet running without playing the mic back
  source.connect(capture)
  capture.connect(sink)
  sink.connect(mic.destination)
  capture.port.onmessage = ({ data }) => {
    if (!ready) return
    const track = stream.getAudioTracks()[0]
    if (track && !track.enabled) return // muted
    if (data.peak > SPEAKING_LEVEL) on.speaking('candidate')
    send({
      realtimeInput: { audio: { data: toBase64(data.pcm), mimeType: `audio/pcm;rate=${IN_RATE}` } },
    })
  }

  try {
    await opened
  } catch (error) {
    mic.close?.()
    player.close?.()
    throw error
  }

  return {
    // Added to the conversation without forcing an answer now (the candidate may be talking).
    wrapUp: (text) => say(`(Note from the system: ${text})`, false),
    close: () => {
      closing = true
      turns.flush()
      silence()
      capture.port.onmessage = null
      try {
        source.disconnect()
      } catch {
        // already disconnected
      }
      mic.close?.()
      player.close?.()
      if (ws.readyState <= WebSocket.OPEN) ws.close()
    },
  }
}
