import React, { useRef, useEffect } from 'react'

interface Props {
  stream: MediaStream | null
  isSpeaking: boolean
  status: string
}

export function AvatarVideo({ stream, isSpeaking, status }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null)

  useEffect(() => {
    if (videoRef.current && stream) {
      videoRef.current.srcObject = stream
    }
  }, [stream])

  const isActive = status === 'active'

  return (
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
      {/* Video element */}
      <video
        ref={videoRef}
        autoPlay
        playsInline
        muted
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'cover',
          display: isActive ? 'block' : 'none',
        }}
      />

      {/* Placeholder when not active */}
      {!isActive && (
        <div style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 12,
        }}>
          <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="var(--border)" strokeWidth="1">
            <circle cx="12" cy="8" r="4"/>
            <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
          </svg>
          <span style={{ color: 'var(--text2)', fontSize: 12 }}>
            {statusLabel(status)}
          </span>
        </div>
      )}

      {/* Speaking indicator ring animation */}
      {isSpeaking && isActive && (
        <div style={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          border: '2px solid var(--accent)',
          animation: 'pulse 1.5s ease-in-out infinite',
          pointerEvents: 'none',
        }} />
      )}

      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.6; transform: scale(1); }
          50%       { opacity: 0.2; transform: scale(1.04); }
        }
      `}</style>
    </div>
  )
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    idle:         'Upload a photo to start',
    uploading:    'Uploading...',
    initializing: 'Initializing avatar...',
    ready:        'Connecting...',
    connecting:   'Connecting...',
    error:        'Error — see below',
  }
  return labels[status] || status
}
