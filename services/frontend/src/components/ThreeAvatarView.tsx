/**
 * Three.js canvas that renders the 3D Avaturn avatar.
 * Handles loading, scene setup, and the lip-sync connection.
 */
import React, { useRef, useEffect } from 'react'
import { useThreeAvatar } from '../hooks/useThreeAvatar'
import { useLipSync } from '../hooks/useLipSync'

interface ThreeAvatarViewProps {
  glbUrl: string
  audioTrack: MediaStreamTrack | null
  isSpeaking: boolean
  onLoaded?: () => void
}

export function ThreeAvatarView({
  glbUrl,
  audioTrack,
  isSpeaking,
  onLoaded,
}: ThreeAvatarViewProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const mountedRef = useRef(false)
  const avatar = useThreeAvatar()
  const lipSync = useLipSync()

  // Mount Three.js scene on first render
  useEffect(() => {
    if (canvasRef.current && !mountedRef.current) {
      avatar.mountScene(canvasRef.current)
      mountedRef.current = true
    }
    return () => {
      avatar.dispose()
      lipSync.stop()
      mountedRef.current = false
    }
  }, [])

  // Load avatar when GLB URL changes
  useEffect(() => {
    if (mountedRef.current && glbUrl) {
      avatar.loadAvatar(glbUrl).then(() => {
        console.log('Avatar morph targets:', avatar.getMorphTargetNames())
        onLoaded?.()
      }).catch((err) => {
        console.error('Failed to load avatar GLB:', err)
      })
    }
  }, [glbUrl])

  // Start/stop lip-sync when audio track arrives
  useEffect(() => {
    if (audioTrack) {
      lipSync.start(audioTrack, avatar.setMorphTarget)
    }
    return () => {
      lipSync.stop()
    }
  }, [audioTrack])

  return (
    <div style={{
      position: 'relative',
      width: '100%',
      aspectRatio: '1',
      borderRadius: '50%',
      overflow: 'hidden',
      background: '#1a1a2e',
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
          display: 'block',
        }}
      />
    </div>
  )
}
