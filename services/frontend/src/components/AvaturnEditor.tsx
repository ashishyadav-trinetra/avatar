/**
 * Avaturn SDK editor — opens an iframe for avatar creation/customization.
 * User scans QR with phone, takes photos, and gets a 3D avatar.
 */
import React, { useRef, useCallback, useState } from 'react'
import { useAvaturn } from '../hooks/useAvaturn'

interface AvaturnEditorProps {
  onAvatarReady: (glbUrl: string) => void
}

// Default sample avatar for quick testing (Avaturn demo GLB)
const DEFAULT_AVATAR_URL =
  'https://models.readyplayer.me/64b3d8e8f35f4a0008e8e8e8.glb'

export function AvaturnEditor({ onAvatarReady }: AvaturnEditorProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [isOpen, setIsOpen] = useState(false)

  const avaturn = useAvaturn({
    onExport: (glbUrl) => {
      setIsOpen(false)
      onAvatarReady(glbUrl)
    },
  })

  const handleCreate = useCallback(() => {
    if (containerRef.current) {
      setIsOpen(true)
      avaturn.openEditor(containerRef.current)
    }
  }, [avaturn])

  const handleUseDefault = useCallback(() => {
    // For quick testing — use a sample avatar
    onAvatarReady(DEFAULT_AVATAR_URL)
  }, [onAvatarReady])

  if (isOpen) {
    return (
      <div style={{ width: '100%', position: 'relative' }}>
        <div
          ref={containerRef}
          style={{
            width: '100%',
            height: 400,
            borderRadius: 12,
            overflow: 'hidden',
            border: '1px solid var(--border)',
          }}
        />
        <button
          onClick={() => {
            avaturn.closeEditor()
            setIsOpen(false)
          }}
          style={{
            position: 'absolute',
            top: 8,
            right: 8,
            padding: '6px 12px',
            borderRadius: 8,
            background: 'rgba(0,0,0,0.6)',
            color: 'white',
            border: 'none',
            fontSize: 12,
            cursor: 'pointer',
          }}
        >
          Close
        </button>
      </div>
    )
  }

  return (
    <div style={{
      width: '100%',
      aspectRatio: '1',
      borderRadius: '50%',
      background: 'var(--surface2, #2a2a3e)',
      border: '2px dashed var(--border)',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: 12,
      cursor: 'pointer',
      transition: 'border-color 0.2s, background 0.2s',
    }}>
      {/* Hidden container for Avaturn iframe */}
      <div ref={containerRef} style={{ display: 'none' }} />

      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--text2)" strokeWidth="1.5">
        <circle cx="12" cy="8" r="4"/>
        <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
        <line x1="12" y1="16" x2="12" y2="22" strokeDasharray="2 2"/>
      </svg>

      <button
        onClick={handleCreate}
        style={{
          padding: '10px 20px',
          borderRadius: 50,
          background: 'linear-gradient(135deg, var(--accent), var(--accent2))',
          color: 'white',
          fontSize: 13,
          fontWeight: 600,
          border: 'none',
          cursor: 'pointer',
          transition: 'opacity 0.2s',
        }}
      >
        Create Avatar
      </button>

      <button
        onClick={handleUseDefault}
        style={{
          padding: '6px 14px',
          borderRadius: 50,
          background: 'transparent',
          color: 'var(--text2)',
          fontSize: 11,
          fontWeight: 500,
          border: '1px solid var(--border)',
          cursor: 'pointer',
          transition: 'opacity 0.2s',
        }}
      >
        Use Sample Avatar
      </button>
    </div>
  )
}
