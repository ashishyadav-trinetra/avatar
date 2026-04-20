import React, { useCallback, useState } from 'react'

interface Props {
  onFile: (file: File) => void
  disabled?: boolean
}

export function PhotoUploader({ onFile, disabled }: Props) {
  const [preview, setPreview] = useState<string | null>(null)
  const [dragging, setDragging] = useState(false)

  const handleFile = useCallback((file: File) => {
    if (!file.type.startsWith('image/')) return
    const url = URL.createObjectURL(file)
    setPreview(url)
    onFile(file)
  }, [onFile])

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }, [handleFile])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16 }}>
      <div
        onDrop={onDrop}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        style={{
          width: 220,
          height: 220,
          borderRadius: '50%',
          border: `2px dashed ${dragging ? 'var(--accent)' : 'var(--border)'}`,
          background: dragging ? 'rgba(108,99,255,0.08)' : 'var(--surface)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: disabled ? 'not-allowed' : 'pointer',
          overflow: 'hidden',
          transition: 'border-color 0.2s, background 0.2s',
          position: 'relative',
        }}
        onClick={() => {
          if (!disabled) document.getElementById('photo-input')?.click()
        }}
      >
        {preview ? (
          <img
            src={preview}
            alt="Avatar preview"
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        ) : (
          <>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--text2)" strokeWidth="1.5">
              <circle cx="12" cy="8" r="4"/>
              <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/>
            </svg>
            <span style={{ color: 'var(--text2)', fontSize: 13, marginTop: 8, textAlign: 'center', padding: '0 16px' }}>
              Drop photo or click
            </span>
            <span style={{ color: 'var(--text2)', fontSize: 11, marginTop: 4 }}>
              Front-facing, good lighting
            </span>
          </>
        )}
      </div>
      <input
        id="photo-input"
        type="file"
        accept="image/*"
        onChange={onInputChange}
        disabled={disabled}
        style={{ display: 'none' }}
      />
    </div>
  )
}
