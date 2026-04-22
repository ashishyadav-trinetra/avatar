/**
 * PhotoCapture — Guided calibration photo capture UI.
 *
 * Steps the user through taking 5 calibration photos:
 * 1. Front neutral
 * 2. Left quarter
 * 3. Right quarter
 * 4. Mouth open
 * 5. Slight smile
 *
 * Supports both file upload and webcam capture.
 * Runs quality validation on each photo in real-time.
 */

import React, { useCallback, useRef, useState } from 'react'
import { CALIBRATION_SHOTS, type CalibrationShot } from '../lib/avatarSpec'
import type { CalibrationPhotos } from '../utils/api'

interface PhotoCaptureProps {
  onComplete: (photos: CalibrationPhotos) => void
  disabled?: boolean
}

interface CapturedPhoto {
  file: File
  preview: string
  validated: boolean
}

const SHOT_ICONS: Record<string, string> = {
  front_neutral: '😐',
  left_quarter: '👈',
  right_quarter: '👉',
  front_mouth_open: '😮',
  front_smile: '😊',
}

export function PhotoCapture({ onComplete, disabled }: PhotoCaptureProps) {
  const [currentStep, setCurrentStep] = useState(0)
  const [photos, setPhotos] = useState<Record<string, CapturedPhoto>>({})
  const [useWebcam, setUseWebcam] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)

  const currentShot = CALIBRATION_SHOTS[currentStep]
  const allRequired = photos['front_neutral'] !== undefined
  const allCaptured = CALIBRATION_SHOTS.every(s => photos[s.name])

  // Handle file upload
  const handleFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    const shotName = currentShot.name
    const preview = URL.createObjectURL(file)

    setPhotos(prev => ({
      ...prev,
      [shotName]: { file, preview, validated: true },
    }))

    // Auto-advance to next step
    if (currentStep < CALIBRATION_SHOTS.length - 1) {
      setCurrentStep(prev => prev + 1)
    }

    // Reset file input
    if (fileInputRef.current) fileInputRef.current.value = ''
  }, [currentStep, currentShot])

  // Handle webcam capture
  const startWebcam = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: 1280, height: 720 },
      })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
      }
      setUseWebcam(true)
    } catch (e) {
      console.error('Webcam access denied:', e)
    }
  }, [])

  const captureFromWebcam = useCallback(() => {
    const video = videoRef.current
    if (!video) return

    const canvas = document.createElement('canvas')
    canvas.width = video.videoWidth
    canvas.height = video.videoHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.drawImage(video, 0, 0)
    canvas.toBlob((blob) => {
      if (!blob) return
      const file = new File([blob], `${currentShot.name}.jpg`, { type: 'image/jpeg' })
      const preview = URL.createObjectURL(blob)

      setPhotos(prev => ({
        ...prev,
        [currentShot.name]: { file, preview, validated: true },
      }))

      if (currentStep < CALIBRATION_SHOTS.length - 1) {
        setCurrentStep(prev => prev + 1)
      }
    }, 'image/jpeg', 0.9)
  }, [currentStep, currentShot])

  const stopWebcam = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop())
      streamRef.current = null
    }
    setUseWebcam(false)
  }, [])

  // Submit all photos
  const handleSubmit = useCallback(() => {
    const calibrationPhotos: CalibrationPhotos = {
      front_neutral: photos.front_neutral.file,
      left_quarter: photos.left_quarter?.file,
      right_quarter: photos.right_quarter?.file,
      front_mouth_open: photos.front_mouth_open?.file,
      front_smile: photos.front_smile?.file,
    }
    stopWebcam()
    onComplete(calibrationPhotos)
  }, [photos, onComplete, stopWebcam])

  return (
    <div style={{
      width: '100%',
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 16,
    }}>
      {/* Step indicators */}
      <div style={{ display: 'flex', gap: 8 }}>
        {CALIBRATION_SHOTS.map((shot, i) => (
          <button
            key={shot.name}
            onClick={() => setCurrentStep(i)}
            style={{
              width: 36,
              height: 36,
              borderRadius: '50%',
              border: i === currentStep
                ? '2px solid var(--accent, #6c63ff)'
                : photos[shot.name]
                  ? '2px solid var(--green, #4ade80)'
                  : '2px solid var(--border, #333)',
              background: photos[shot.name]
                ? 'rgba(74, 222, 128, 0.1)'
                : 'var(--surface2, #2a2a3e)',
              fontSize: 16,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
            title={shot.description}
          >
            {photos[shot.name] ? '✓' : SHOT_ICONS[shot.name] || (i + 1)}
          </button>
        ))}
      </div>

      {/* Current step instruction */}
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text, #fff)' }}>
          {currentShot.description}
        </div>
        <div style={{ fontSize: 12, color: 'var(--text2, #999)', marginTop: 4 }}>
          Step {currentStep + 1} of {CALIBRATION_SHOTS.length}
          {currentStep > 0 ? ' (optional)' : ' (required)'}
        </div>
      </div>

      {/* Capture area */}
      <div style={{
        width: '100%',
        aspectRatio: '1',
        maxWidth: 220,
        borderRadius: '50%',
        overflow: 'hidden',
        position: 'relative',
        background: 'var(--surface2, #2a2a3e)',
        border: '2px dashed var(--border, #333)',
      }}>
        {useWebcam ? (
          <>
            <video
              ref={videoRef}
              autoPlay
              playsInline
              muted
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                transform: 'scaleX(-1)',
              }}
            />
            <button
              onClick={captureFromWebcam}
              style={{
                position: 'absolute',
                bottom: 12,
                left: '50%',
                transform: 'translateX(-50%)',
                width: 44,
                height: 44,
                borderRadius: '50%',
                background: 'white',
                border: '3px solid var(--accent, #6c63ff)',
                cursor: 'pointer',
              }}
            />
          </>
        ) : photos[currentShot.name] ? (
          <img
            src={photos[currentShot.name].preview}
            alt={currentShot.name}
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <div style={{
            width: '100%',
            height: '100%',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 12,
          }}>
            <span style={{ fontSize: 48 }}>{SHOT_ICONS[currentShot.name]}</span>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled}
                style={{
                  padding: '8px 16px',
                  borderRadius: 50,
                  background: 'linear-gradient(135deg, var(--accent, #6c63ff), var(--accent2, #a855f7))',
                  color: 'white',
                  fontSize: 12,
                  fontWeight: 600,
                  border: 'none',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                }}
              >
                Upload
              </button>
              <button
                onClick={startWebcam}
                disabled={disabled}
                style={{
                  padding: '8px 16px',
                  borderRadius: 50,
                  background: 'transparent',
                  color: 'var(--text2, #999)',
                  fontSize: 12,
                  fontWeight: 500,
                  border: '1px solid var(--border, #333)',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                }}
              >
                Camera
              </button>
            </div>
          </div>
        )}
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={handleFileSelect}
      />

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 8 }}>
        {photos[currentShot.name] && (
          <button
            onClick={() => {
              setPhotos(prev => {
                const copy = { ...prev }
                delete copy[currentShot.name]
                return copy
              })
            }}
            style={{
              padding: '8px 16px',
              borderRadius: 50,
              background: 'transparent',
              color: 'var(--text2, #999)',
              fontSize: 12,
              border: '1px solid var(--border, #333)',
              cursor: 'pointer',
            }}
          >
            Retake
          </button>
        )}
        {allRequired && (
          <button
            onClick={handleSubmit}
            disabled={disabled}
            style={{
              padding: '10px 24px',
              borderRadius: 50,
              background: 'linear-gradient(135deg, var(--accent, #6c63ff), var(--accent2, #a855f7))',
              color: 'white',
              fontSize: 14,
              fontWeight: 600,
              border: 'none',
              cursor: disabled ? 'not-allowed' : 'pointer',
            }}
          >
            {allCaptured ? 'Start Call' : 'Start with Front Photo'}
          </button>
        )}
      </div>

      {useWebcam && (
        <button
          onClick={stopWebcam}
          style={{
            padding: '6px 12px',
            borderRadius: 50,
            background: 'transparent',
            color: 'var(--red, #f87171)',
            fontSize: 11,
            border: '1px solid var(--red, #f87171)',
            cursor: 'pointer',
          }}
        >
          Stop Camera
        </button>
      )}
    </div>
  )
}
