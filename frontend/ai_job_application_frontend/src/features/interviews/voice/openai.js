/**
 * OpenAI Realtime over WebRTC: the browser plays the AI's audio track and sends the
 * microphone track; events (transcripts, speaking) come over the "oai-events" data channel.
 */

// GA Realtime API event names, with the older beta names as fallback.
const ITEM_ADDED = ['conversation.item.added', 'conversation.item.created']
const AI_DELTA = ['response.output_audio_transcript.delta', 'response.audio_transcript.delta']
const AI_DONE = ['response.output_audio_transcript.done', 'response.audio_transcript.done']
const USER_DONE = 'conversation.item.input_audio_transcription.completed'

export async function connectOpenAI({ grant, stream, on }) {
  const pc = new RTCPeerConnection()
  const audio = new Audio()
  audio.autoplay = true
  pc.ontrack = (e) => (audio.srcObject = e.streams[0])
  pc.addTrack(stream.getAudioTracks()[0], stream)
  const dc = pc.createDataChannel('oai-events')
  const partial = {}
  const send = (event) => dc.readyState === 'open' && dc.send(JSON.stringify(event))

  dc.onopen = () => send({ type: 'response.create' }) // the interviewer speaks first
  dc.onmessage = (message) => {
    let event
    try {
      event = JSON.parse(message.data)
    } catch {
      return
    }
    const type = event.type
    if (ITEM_ADDED.includes(type) && event.item?.type === 'message') {
      on.order(event.item.id) // conversation order, not the order transcripts arrive in
    } else if (AI_DELTA.includes(type)) {
      partial[event.item_id] = (partial[event.item_id] ?? '') + (event.delta ?? '')
      on.caption(event.item_id, 'interviewer', partial[event.item_id])
    } else if (AI_DONE.includes(type)) {
      on.turn(event.item_id, 'interviewer', event.transcript ?? partial[event.item_id])
    } else if (type === USER_DONE) {
      on.turn(event.item_id, 'candidate', event.transcript)
    } else if (type === 'input_audio_buffer.speech_started') {
      on.speaking('candidate')
    } else if (type === 'input_audio_buffer.speech_stopped') {
      on.speaking(null)
    } else if (type === 'response.created' || type === 'output_audio_buffer.started') {
      on.speaking('interviewer')
    } else if (type === 'response.done' || type === 'output_audio_buffer.stopped') {
      on.speaking(null, 'interviewer')
    }
  }
  pc.onconnectionstatechange = () => {
    if (['failed', 'disconnected'].includes(pc.connectionState)) on.dropped()
  }

  const offer = await pc.createOffer()
  await pc.setLocalDescription(offer)
  const answer = await fetch(grant.connect_url, {
    method: 'POST',
    body: offer.sdp,
    headers: { Authorization: `Bearer ${grant.client_secret}`, 'Content-Type': 'application/sdp' },
  })
  if (!answer.ok) {
    pc.close()
    throw new Error('The voice service did not accept the call.')
  }
  await pc.setRemoteDescription({ type: 'answer', sdp: await answer.text() })

  return {
    wrapUp: (text) =>
      send({
        type: 'conversation.item.create',
        item: { type: 'message', role: 'system', content: [{ type: 'input_text', text }] },
      }),
    close: () => {
      pc.onconnectionstatechange = null
      dc.close()
      pc.close()
      audio.srcObject = null
    },
  }
}
