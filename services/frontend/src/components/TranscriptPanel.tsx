import React, { useEffect, useRef } from 'react'

interface Props {
  lines: string[]
}

export function TranscriptPanel({ lines = [] }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [lines])

  if (lines.length === 0) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: 'var(--text2)',
        fontSize: 13,
      }}>
        Conversation will appear here
      </div>
    )
  }

  return (
    <div style={{
      flex: 1,
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
      padding: '4px 0',
    }}>
      {lines.map((line, i) => {
        const isAgent = line.startsWith('[Avatar]')
        const text = line.replace(/^\[(Avatar|You)\]\s*/, '')
        return (
          <div
            key={i}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: isAgent ? 'flex-start' : 'flex-end',
            }}
          >
            <span style={{
              fontSize: 11,
              color: 'var(--text2)',
              marginBottom: 2,
              paddingLeft: isAgent ? 4 : 0,
              paddingRight: isAgent ? 0 : 4,
            }}>
              {isAgent ? 'Avatar' : 'You'}
            </span>
            <div style={{
              maxWidth: '85%',
              padding: '8px 12px',
              borderRadius: isAgent ? '4px 12px 12px 12px' : '12px 4px 12px 12px',
              background: isAgent ? 'var(--surface2)' : 'rgba(108,99,255,0.2)',
              border: `1px solid ${isAgent ? 'var(--border)' : 'rgba(108,99,255,0.3)'}`,
              color: 'var(--text)',
              fontSize: 14,
              lineHeight: 1.5,
            }}>
              {text}
            </div>
          </div>
        )
      })}
      <div ref={bottomRef} />
    </div>
  )
}
