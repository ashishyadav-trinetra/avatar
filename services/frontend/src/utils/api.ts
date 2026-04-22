const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const COEFF_WS_BASE = import.meta.env.VITE_COEFF_WS_URL || 'ws://localhost:8003'

export interface StartSessionResponse {
  session_id: string
  livekit_token: string
  livekit_url: string
  glb_url: string
  coefficient_ws_url: string
  reconstruction_time_ms: number
  model: string
  status: string
}

export interface ValidateResponse {
  all_passed: boolean
  results: Record<string, {
    passed: boolean
    score: number
    gates: Array<{
      name: string
      status: 'pass' | 'warn' | 'fail'
      message: string
      score: number
    }>
    recommendations: string[]
  }>
}

// ── Session management ────────────────────────────────────────

export interface CalibrationPhotos {
  front_neutral: File
  left_quarter?: File
  right_quarter?: File
  front_mouth_open?: File
  front_smile?: File
}

export async function startSession(photos: CalibrationPhotos): Promise<StartSessionResponse> {
  const form = new FormData()
  form.append('front_neutral', photos.front_neutral)
  if (photos.left_quarter) form.append('left_quarter', photos.left_quarter)
  if (photos.right_quarter) form.append('right_quarter', photos.right_quarter)
  if (photos.front_mouth_open) form.append('front_mouth_open', photos.front_mouth_open)
  if (photos.front_smile) form.append('front_smile', photos.front_smile)
  form.append('skip_quality_check', 'true')  // Skip in dev — quality gate runs separately via /validate

  const res = await fetch(`${API_URL}/api/session/start`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Session start failed: ${err}`)
  }
  const data: StartSessionResponse = await res.json()

  // Rewrite internal URLs to browser-accessible addresses
  data.glb_url = `${API_URL}${data.glb_url}`
  data.coefficient_ws_url = `${COEFF_WS_BASE}/coefficients/ws/${data.session_id}`

  return data
}

export async function validatePhotos(photos: Partial<CalibrationPhotos>): Promise<ValidateResponse> {
  const form = new FormData()
  for (const [name, file] of Object.entries(photos)) {
    if (file) form.append(name, file)
  }

  const res = await fetch(`${API_URL}/api/session/validate`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    const err = await res.text()
    throw new Error(`Validation failed: ${err}`)
  }
  return res.json()
}

export async function endSession(sessionId: string): Promise<void> {
  await fetch(`${API_URL}/api/session/${sessionId}`, {
    method: 'DELETE',
  }).catch(() => {})
}
