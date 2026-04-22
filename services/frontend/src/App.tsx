import React, { useCallback } from 'react'
import { useAvatarStore } from './store/avatarStore'
import { startSession, endSession, type CalibrationPhotos } from './utils/api'
import { useLiveKit } from './hooks/useLiveKit'
import { useCoefficientStream } from './hooks/useCoefficientStream'
import { PhotoCapture } from './components/PhotoCapture'
import { AvatarRenderer } from './components/AvatarRenderer'
import { StatusBadge, MicButton, EndCallButton } from './components/Controls'
import { TranscriptPanel } from './components/TranscriptPanel'

export default function App() {
  const {
    status, session, error, isMuted, isSpeaking, transcript,
    setStatus, setSession, setError, setMuted, setSpeaking, addTranscript, reset,
  } = useAvatarStore()

  // ── Coefficient stream (replaces old JPEG WebSocket) ──────
  const coeffStream = useCoefficientStream({
    onFirstFrame: () => {
      setStatus('active')
    },
    onDisconnect: () => {
      console.warn('Coefficient stream disconnected')
    },
  })

  // ── LiveKit hook ──────────────────────────────────────────
  const livekit = useLiveKit({
    onAgentSpeaking: setSpeaking,
    onTranscript: (text, isAgent) => {
      addTranscript(`${isAgent ? '[Avatar]' : '[You]'} ${text}`)
    },
    onDisconnect: () => {
      setStatus('idle')
    },
  })

  // ── Start the full session ────────────────────────────────
  const handleStart = useCallback(async (photos: CalibrationPhotos) => {
    try {
      setStatus('uploading')
      setError(null)

      // 1. Upload photos → reconstruct → get session data
      const data = await startSession(photos)
      setSession({
        sessionId: data.session_id,
        livekitToken: data.livekit_token,
        livekitUrl: data.livekit_url,
        glbUrl: data.glb_url,
        coefficientWsUrl: data.coefficient_ws_url,
        model: data.model,
        reconstructionTimeMs: data.reconstruction_time_ms,
      })
      setStatus('connecting')

      // 2. Connect coefficient stream (replaces JPEG frames)
      coeffStream.connect(data.coefficient_ws_url)

      // 3. Connect LiveKit (voice pipeline)
      await livekit.connect(data.livekit_url, data.livekit_token)

      // Status transitions to 'active' when first coefficient frame arrives
    } catch (e: any) {
      console.error('Session start error:', e)
      setError(e.message || 'Failed to start session')
      setStatus('error')
    }
  }, [coeffStream, livekit, setStatus, setSession, setError])

  // ── End the session ───────────────────────────────────────
  const handleEnd = useCallback(async () => {
    coeffStream.disconnect()
    await livekit.disconnect()
    if (session) {
      await endSession(session.sessionId).catch(console.error)
    }
    reset()
  }, [coeffStream, livekit, session, reset])

  // ── Mic toggle ────────────────────────────────────────────
  const handleMicToggle = useCallback(async () => {
    const next = !isMuted
    setMuted(next)
    await livekit.setMicEnabled(!next)
  }, [isMuted, livekit, setMuted])

  const isCallActive = status === 'active' || status === 'connecting'
  const showAvatar = isCallActive && session?.glbUrl

  // ── Layout ────────────────────────────────────────────────
  return (
    <div style={{
      height: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'var(--bg)',
      padding: 20,
    }}>
      <div style={{
        width: '100%',
        maxWidth: 900,
        display: 'grid',
        gridTemplateColumns: '340px 1fr',
        gap: 24,
        alignItems: 'stretch',
      }}>

        {/* ── Left panel: avatar / photo capture ─────────── */}
        <div style={{
          background: 'var(--surface)',
          borderRadius: 20,
          border: '1px solid var(--border)',
          padding: 28,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 20,
        }}>
          {/* Logo / title */}
          <div style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 32, height: 32, borderRadius: 8,
              background: 'linear-gradient(135deg, var(--accent), var(--accent2))',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-2 14.5v-9l6 4.5-6 4.5z"/>
              </svg>
            </div>
            <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--text)' }}>
              AI Avatar
            </span>
            <StatusBadge status={status} />
          </div>

          {/* Avatar or photo capture */}
          <div style={{ width: 220 }}>
            {showAvatar ? (
              <AvatarRenderer
                glbUrl={session.glbUrl}
                getCoefficients={coeffStream.getCurrentCoefficients}
                isSpeaking={isSpeaking || coeffStream.isSpeaking}
              />
            ) : !isCallActive ? (
              <PhotoCapture
                onComplete={handleStart}
                disabled={status !== 'idle'}
              />
            ) : (
              <div style={{
                width: '100%',
                aspectRatio: '1',
                borderRadius: '50%',
                background: 'var(--surface2)',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 12,
                border: '2px solid var(--border)',
              }}>
                <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="var(--border)" strokeWidth="1">
                  <circle cx="12" cy="8" r="4"/>
                  <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
                </svg>
                <span style={{ color: 'var(--text2)', fontSize: 12 }}>
                  {status === 'uploading' ? 'Reconstructing avatar...' : 'Connecting...'}
                </span>
              </div>
            )}
          </div>

          {/* Error message */}
          {error && (
            <div style={{
              width: '100%',
              padding: '10px 14px',
              borderRadius: 8,
              background: 'rgba(248,113,113,0.1)',
              border: '1px solid rgba(248,113,113,0.3)',
              color: 'var(--red)',
              fontSize: 13,
              textAlign: 'center',
            }}>
              {error}
            </div>
          )}

          {/* Call controls (shown during active call) */}
          {isCallActive && (
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <MicButton
                muted={isMuted}
                onToggle={handleMicToggle}
                disabled={status !== 'active'}
              />
              <EndCallButton onEnd={handleEnd} />
            </div>
          )}

          {/* Reconstruction info */}
          {session && status === 'active' && (
            <p style={{ color: 'var(--text2)', fontSize: 11, textAlign: 'center' }}>
              Model: {session.model} | Reconstructed in {session.reconstructionTimeMs}ms
            </p>
          )}
        </div>

        {/* ── Right panel: transcript ─────────────────────── */}
        <div style={{
          background: 'var(--surface)',
          borderRadius: 20,
          border: '1px solid var(--border)',
          padding: 24,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          minHeight: 480,
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}>
            <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--text)' }}>
              Conversation
            </span>
            {isCallActive && (
              <span style={{
                fontSize: 11,
                color: 'var(--text2)',
                background: 'var(--surface2)',
                padding: '4px 10px',
                borderRadius: 50,
              }}>
                {coeffStream.isConnected ? 'Streaming' : 'Buffering...'}
              </span>
            )}
          </div>
          <TranscriptPanel lines={transcript} />
        </div>
      </div>
    </div>
  )
}
