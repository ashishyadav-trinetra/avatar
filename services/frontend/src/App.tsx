import React, { useCallback, useRef, useState } from 'react'
import { useAvatarStore } from './store/avatarStore'
import { startSession, endSession } from './utils/api'
import { useWebRTC } from './hooks/useWebRTC'
import { useLiveKit } from './hooks/useLiveKit'
import { PhotoUploader } from './components/PhotoUploader'
import { AvatarVideo } from './components/AvatarVideo'
import { StatusBadge, MicButton, EndCallButton } from './components/Controls'
import { TranscriptPanel } from './components/TranscriptPanel'

export default function App() {
  const {
    status, session, error, isMuted, isSpeaking, transcript,
    setStatus, setSession, setError, setMuted, setSpeaking, addTranscript, reset,
  } = useAvatarStore()

  const [avatarStream, setAvatarStream] = useState<MediaStream | null>(null)
  const [photoFile, setPhotoFile] = useState<File | null>(null)
  const livekitRef = useRef<ReturnType<typeof useLiveKit> | null>(null)

  // ── WebRTC hook (connected when session is ready) ─────────
  const webrtc = useWebRTC({
    offerUrl: session?.webrtcOfferUrl ?? '',
    onTrack: (stream) => {
      setAvatarStream(stream)
      setStatus('active')
    },
    onStateChange: (state) => {
      if (state === 'failed' || state === 'disconnected') {
        setError('WebRTC connection lost')
        setStatus('error')
      }
    },
  })

  // ── LiveKit hook ──────────────────────────────────────────
  const livekit = useLiveKit({
    url: session?.livekitUrl ?? '',
    token: session?.livekitToken ?? '',
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
      setStatus('initializing')

      // 2. Connect WebRTC (avatar video)
      await webrtc.connect()

      // 3. Connect LiveKit (voice pipeline)
      setStatus('connecting')
      await livekit.connect()

      // Status transitions to 'active' in onTrack callback
    } catch (e: any) {
      console.error('Session start error:', e)
      setError(e.message || 'Failed to start session')
      setStatus('error')
    }
  }, [photoFile, webrtc, livekit, setStatus, setSession, setError])

  // ── End the session ───────────────────────────────────────
  const handleEnd = useCallback(async () => {
    webrtc.disconnect()
    await livekit.disconnect()
    if (session) {
      await endSession(session.sessionId).catch(console.error)
    }
    setAvatarStream(null)
    reset()
  }, [webrtc, livekit, session, reset])

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

          {/* Avatar circle — photo uploader OR live video */}
          <div style={{ width: 220 }}>
            {!isCallActive ? (
              <PhotoUploader
                onFile={setPhotoFile}
                disabled={status !== 'idle'}
              />
            ) : (
              <AvatarVideo
                stream={avatarStream}
                isSpeaking={isSpeaking}
                status={status}
              />
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
