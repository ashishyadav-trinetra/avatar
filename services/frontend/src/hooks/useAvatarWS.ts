/**
 * Direct WebSocket connection to avatar-engine for video frames.
 * Receives JPEG frames and renders them on a canvas.
 * Much more reliable than WebRTC through Docker for dev mode.
 *
 * The canvas ref is resolved at frame-render time, so the canvas
 * element does NOT need to be in the DOM when connect() is called.
 */
import { useRef, useCallback, type RefObject } from 'react'

const AVATAR_ENGINE_WS = import.meta.env.VITE_AVATAR_ENGINE_WS || 'ws://localhost:8001'

interface UseAvatarWSOptions {
  canvasRef: RefObject<HTMLCanvasElement | null>
  onFirstFrame?: () => void
  onDisconnect?: () => void
}

export function useAvatarWS({ canvasRef, onFirstFrame, onDisconnect }: UseAvatarWSOptions) {
  const wsRef = useRef<WebSocket | null>(null)
  const gotFirstFrame = useRef(false)

  const connect = useCallback((sessionId: string) => {
    gotFirstFrame.current = false

    const url = `${AVATAR_ENGINE_WS}/frames/ws/${sessionId}`
    console.log('Connecting to avatar frames WS:', url)
    const ws = new WebSocket(url)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      console.log('Avatar frames WS connected')
    }

    ws.onmessage = (event) => {
      const blob = new Blob([event.data], { type: 'image/jpeg' })
      const imgUrl = URL.createObjectURL(blob)
      const img = new Image()
      img.onload = () => {
        // Resolve canvas at render time — it may not exist at connect time
        const canvas = canvasRef.current
        const ctx = canvas?.getContext('2d')
        if (ctx && canvas) {
          canvas.width = img.width
          canvas.height = img.height
          ctx.drawImage(img, 0, 0)

          if (!gotFirstFrame.current) {
            gotFirstFrame.current = true
            onFirstFrame?.()
          }
        }
        URL.revokeObjectURL(imgUrl)
      }
      img.src = imgUrl
    }

    ws.onclose = () => {
      console.log('Avatar frames WS closed')
      onDisconnect?.()
    }

    ws.onerror = (err) => {
      console.error('Avatar frames WS error:', err)
    }
  }, [canvasRef, onFirstFrame, onDisconnect])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
  }, [])

  return { connect, disconnect }
}
