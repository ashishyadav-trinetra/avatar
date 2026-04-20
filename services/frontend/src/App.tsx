import React, { useCallback, useRef, useState } from 'react'
import { useAvatarStore } from './store/avatarStore'
import { startSession, endSession } from './utils/api'
import { useAvatarWS } from './hooks/useAvatarWS'
import { useLiveKit } from './hooks/useLiveKit'
import { PhotoUploader } from './components/PhotoUploader'
import { StatusBadge, MicButton, EndCallButton } from './components/Controls'
import { TranscriptPanel } from './components/TranscriptPanel'

export default function App() {
  const {
    status, session, error, isMuted, isSpeaking, transcript,
    setStatus, setSession, setError, setMuted, setSpeaking, addTranscript, reset,
  } = useAvatarStore()

  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  // ── Avatar video via direct WebSocket (replaces flaky WebRTC) ──
  // Pass canvasRef so the hook resolves the canvas at frame-render time,
  // not at connect time — avoids null ref when canvas isn't mounted yet.
  const avatarWS = useAvatarWS({
    canvasRef,
    onFirstFrame: () => {
      setStatus('active')
    },
    onDisconnect: () => {
      console.warn('Avatar frames WS disconnected')
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
  const handleStart = useCallback(async () => {
    if (!photoFile) return
    try {
      setStatus('uploading')
      setError(null)

      // 1. Upload photo → get session data
      const data = await startSession(photoFile)
      setSession({
        sessionId: data.session_id,
        livekitToken: data.livekit_token,
        livekitUrl: data.livekit_url,
        webrtcOfferUrl: data.webrtc_offer_url,
      })
      setStatus('connecting')

      // 2. Connect avatar video via direct WebSocket
      //    canvasRef is resolved at frame-render time by the hook,
      //    so it's fine that the visible canvas may not be mounted yet.
      avatarWS.connect(data.session_id)

      // 3. Connect LiveKit (voice pipeline)
      await livekit.connect(data.livekit_url, data.livekit_token)

      // Status transitions to 'active' when first frame arrives
    } catch (e: any) {
      console.error('Session start error:', e)
      setError(e.message || 'Failed to start session')
      setStatus('error')
    }
  }, [photoFile, avatarWS, livekit, setStatus, setSession, setError])

  // ── End the session ───────────────────────────────────────
  const handleEnd = useCallback(async () => {
    avatarWS.disconnect()
    await livekit.disconnect()
    if (session) {
      await endSession(session.sessionId).catch(console.error)
    }
    reset()
  }, [avatarWS, livekit, session, reset])

  // ── Mic toggle ────────────────────────────────────────────
  const handleMicToggle = useCallback(async () => {
    const next = !isMuted
    setMuted(next)
    await livekit.setMicEnabled(!next)
  }, [isMuted, livekit, setMuted])

  const isCallActive = status === 'active' || status === 'connecting'
  const canStart = !!photoFile && status === 'idle'

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

        {/* ── Left panel: avatar video ────────────────────── */}
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

          {/* Avatar circle */}
          <div style={{ width: 220 }}>
            {!isCallActive ? (
              <PhotoUploader
                onFile={setPhotoFile}
                disabled={status !== 'idle'}
              />
            ) : (
              <div style={{
                position: 'relative',
                width: '100%',
                aspectRatio: '1',
                borderRadius: '50%',
                overflow: 'hidden',
                background: 'var(--surface)',
                boxShadow: isSpeaking
                  ? '0 0 0 3px var(--accent), 0 0 32px rgba(108,99,255,0.4)'
                  : '0 0 0 2px var(--border)',
                transition: 'box-shadow 0.3s ease',
              }}>
                <canvas
                  ref={canvasRef}
                  style={{
                    width: '100%',
                    height: '100%',
                    objectFit: 'cover',
                    display: status === 'active' ? 'block' : 'none',
                  }}
                />
                {status !== 'active' && (
                  <div style={{
                    width: '100%', height: '100%',
                    display: 'flex', flexDirection: 'column',
                    alignItems: 'center', justifyContent: 'center', gap: 12,
                  }}>
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="var(--border)" strokeWidth="1">
                      <circle cx="12" cy="8" r="4"/>
                      <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
                    </svg>
                    <span style={{ color: 'var(--text2)', fontSize: 12 }}>Connecting...</span>
                  </div>
                )}
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

          {/* Call controls */}
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            {!isCallActive ? (
              <button
                onClick={handleStart}
                disabled={!canStart}
                style={{
                  padding: '12px 28px',
                  borderRadius: 50,
                  background: canStart
                    ? 'linear-gradient(135deg, var(--accent), var(--accent2))'
                    : 'var(--surface2)',
                  color: canStart ? 'white' : 'var(--text2)',
                  fontSize: 15,
                  fontWeight: 600,
                  border: 'none',
                  cursor: canStart ? 'pointer' : 'not-allowed',
                  transition: 'all 0.2s',
                  opacity: ['uploading', 'initializing', 'connecting'].includes(status) ? 0.7 : 1,
                }}
              >
                {['uploading', 'initializing', 'connecting'].includes(status)
                  ? 'Starting…'
                  : 'Start Call'
                }
              </button>
            ) : (
              <>
                <MicButton
                  muted={isMuted}
                  onToggle={handleMicToggle}
                  disabled={status !== 'active'}
                />
                <EndCallButton onEnd={handleEnd} />
              </>
            )}
          </div>

          {/* Setup hint */}
          {status === 'idle' && !photoFile && (
            <p style={{ color: 'var(--text2)', fontSize: 12, textAlign: 'center', lineHeight: 1.6 }}>
              Upload a front-facing photo to create your AI avatar
            </p>
          )}
          {status === 'idle' && photoFile && (
            <p style={{ color: 'var(--green)', fontSize: 12, textAlign: 'center' }}>
              ✓ Photo ready — click Start Call
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
            <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text)' }}>
              Conversation
            </span>
            {isSpeaking && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                color: 'var(--accent2)',
                fontSize: 12,
              }}>
                <SoundWaveIcon />
                Avatar speaking
              </div>
            )}
          </div>

          <div style={{
            flex: 1,
            display: 'flex',
            flexDirection: 'column',
            overflow: 'hidden',
          }}>
            <TranscriptPanel lines={transcript} />
          </div>
        </div>
      </div>
    </div>
  )
}

function SoundWaveIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
    </svg>
  )
}
