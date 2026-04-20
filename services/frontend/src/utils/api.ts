const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WEBRTC_URL = import.meta.env.VITE_WEBRTC_URL || 'http://localhost:8002'

export interface StartSessionResponse {
  session_id: string
  livekit_token: string
  livekit_url: string
  webrtc_offer_url: string
  status: string
}

export interface WebRTCAnswer {
  sdp: string
  type: string
}

// ── Session management ────────────────────────────────────────

export async function startSession(photoFile: File): Promise<StartSessionResponse> {
  const form = new FormData()
  form.append('photo', photoFile)
  const res = await fetch(`${API_URL}/api/session/start`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Session start failed: ${err}`)
  }
  return res.json()
}

export async function endSession(sessionId: string): Promise<void> {
  await fetch(`${API_URL}/api/session/${sessionId}`, { method: 'DELETE' })
}

// ── WebRTC signaling ──────────────────────────────────────────

export async function sendWebRTCOffer(
  offerUrl: string,
  offer: RTCSessionDescriptionInit
): Promise<WebRTCAnswer> {
  const res = await fetch(offerUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ sdp: offer.sdp, type: offer.type }),
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`WebRTC offer failed: ${err}`)
  }
  return res.json()
}
