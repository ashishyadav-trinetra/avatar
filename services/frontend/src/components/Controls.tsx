import React from 'react'
import type { SessionStatus } from '../store/avatarStore'

// ── Status Badge ──────────────────────────────────────────────
interface BadgeProps { status: SessionStatus }

const STATUS_CONFIG: Record<SessionStatus, { label: string; color: string }> = {
  idle:         { label: 'Idle',          color: 'var(--text2)' },
  uploading:    { label: 'Uploading…',    color: 'var(--accent2)' },
  initializing: { label: 'Initializing…', color: 'var(--accent2)' },
  ready:        { label: 'Ready',         color: 'var(--green)' },
  connecting:   { label: 'Connecting…',   color: 'var(--accent2)' },
  active:       { label: 'Live',          color: 'var(--green)' },
  error:        { label: 'Error',         color: 'var(--red)' },
}

export function StatusBadge({ status }: BadgeProps) {
  const { label, color } = STATUS_CONFIG[status]
  const isAnimated = ['uploading', 'initializing', 'connecting'].includes(status)

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{
        width: 8, height: 8,
        borderRadius: '50%',
        background: color,
        display: 'inline-block',
        animation: isAnimated ? 'blink 1.2s ease-in-out infinite' : undefined,
      }} />
      <span style={{ fontSize: 13, color, fontWeight: 500 }}>{label}</span>
      <style>{`
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.3; }
        }
      `}</style>
    </div>
  )
}

// ── Mic Button ────────────────────────────────────────────────
interface MicProps {
  muted: boolean
  disabled?: boolean
  onToggle: () => void
}

export function MicButton({ muted, disabled, onToggle }: MicProps) {
  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      title={muted ? 'Unmute microphone' : 'Mute microphone'}
      style={{
        width: 52,
        height: 52,
        borderRadius: '50%',
        background: muted ? 'rgba(248,113,113,0.15)' : 'var(--surface2)',
        border: `1.5px solid ${muted ? 'var(--red)' : 'var(--border)'}`,
        color: muted ? 'var(--red)' : 'var(--text)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 0.2s',
        opacity: disabled ? 0.4 : 1,
      }}
    >
      {muted ? (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <line x1="1" y1="1" x2="23" y2="23"/>
          <path d="M9 9v3a3 3 0 0 0 5.12 2.12M15 9.34V4a3 3 0 0 0-5.94-.6"/>
          <path d="M17 16.95A7 7 0 0 1 5 12v-2m14 0v2a7 7 0 0 1-.11 1.23"/>
          <line x1="12" y1="19" x2="12" y2="23"/>
          <line x1="8" y1="23" x2="16" y2="23"/>
        </svg>
      ) : (
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
          <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
          <line x1="12" y1="19" x2="12" y2="23"/>
          <line x1="8" y1="23" x2="16" y2="23"/>
        </svg>
      )}
    </button>
  )
}

// ── End Call Button ───────────────────────────────────────────
interface EndCallProps { onEnd: () => void; disabled?: boolean }

export function EndCallButton({ onEnd, disabled }: EndCallProps) {
  return (
    <button
      onClick={onEnd}
      disabled={disabled}
      title="End call"
      style={{
        width: 52,
        height: 52,
        borderRadius: '50%',
        background: 'rgba(248,113,113,0.15)',
        border: '1.5px solid var(--red)',
        color: 'var(--red)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        transition: 'all 0.2s',
        opacity: disabled ? 0.4 : 1,
      }}
    >
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
        <path d="M6.6 10.8c1.4 2.8 3.8 5.1 6.6 6.6l2.2-2.2c.27-.27.67-.36 1.02-.24 1.12.37 2.33.57 3.57.57.55 0 1 .45 1 1V20c0 .55-.45 1-1 1-9.39 0-17-7.61-17-17 0-.55.45-1 1-1h3.5c.55 0 1 .45 1 1 0 1.25.2 2.45.57 3.57.11.35.03.74-.25 1.02L6.6 10.8z"/>
      </svg>
    </button>
  )
}
