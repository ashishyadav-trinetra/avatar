/**
 * useCoefficientStream — WebSocket hook for receiving coefficient frames.
 *
 * Connects to the coefficient engine, receives 258-byte binary frames,
 * decodes them, applies delta decompression, and manages a jitter buffer.
 * Provides the current frame's coefficients at render time.
 */

import { useCallback, useRef, useState } from 'react'
import {
  decodeFrame,
  applyDelta,
  FrameFlags,
  JITTER_BUFFER_MIN,
  JITTER_BUFFER_MAX,
  NUM_TOTAL_FLOATS,
  FRAME_TOTAL_SIZE,
  type CoefficientFrame,
} from '../lib/avatarSpec'

interface UseCoefficientStreamOptions {
  onFirstFrame?: () => void
  onDisconnect?: () => void
}

interface UseCoefficientStreamReturn {
  connect: (wsUrl: string) => void
  disconnect: () => void
  /** Get current interpolated coefficients. Call in render loop. */
  getCurrentCoefficients: () => Float32Array
  isConnected: boolean
  isSpeaking: boolean
}

export function useCoefficientStream(
  options: UseCoefficientStreamOptions = {}
): UseCoefficientStreamReturn {
  const wsRef = useRef<WebSocket | null>(null)
  const [isConnected, setIsConnected] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const firstFrameRef = useRef(false)

  // Jitter buffer: sorted queue of frames by timestamp
  const bufferRef = useRef<CoefficientFrame[]>([])

  // Last fully decoded (absolute) coefficients
  const lastAbsoluteRef = useRef(new Float32Array(NUM_TOTAL_FLOATS))

  // Current output coefficients (smoothed)
  const currentRef = useRef(new Float32Array(NUM_TOTAL_FLOATS))

  const connect = useCallback((wsUrl: string) => {
    if (wsRef.current) {
      wsRef.current.close()
    }

    firstFrameRef.current = false
    bufferRef.current = []
    lastAbsoluteRef.current.fill(0)
    currentRef.current.fill(0)

    const ws = new WebSocket(wsUrl)
    ws.binaryType = 'arraybuffer'
    wsRef.current = ws

    ws.onopen = () => {
      console.log('[CoefficientStream] Connected')
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      if (!(event.data instanceof ArrayBuffer)) return
      if (event.data.byteLength !== FRAME_TOTAL_SIZE) return

      try {
        const frame = decodeFrame(event.data)

        // Decode: if delta, reconstruct absolute values
        let absoluteCoeffs: Float32Array
        if (frame.flags & FrameFlags.IS_DELTA) {
          absoluteCoeffs = applyDelta(frame, lastAbsoluteRef.current)
        } else {
          absoluteCoeffs = new Float32Array(frame.coefficients)
        }

        // Store as last absolute
        lastAbsoluteRef.current.set(absoluteCoeffs)

        // Update speaking state
        const speaking = !!(frame.flags & FrameFlags.IS_SPEAKING)
        setIsSpeaking(speaking)

        // Add to jitter buffer
        const decodedFrame: CoefficientFrame = {
          ...frame,
          coefficients: absoluteCoeffs,
        }
        const buffer = bufferRef.current
        buffer.push(decodedFrame)

        // Sort by timestamp
        buffer.sort((a, b) => a.timestampMs - b.timestampMs)

        // Trim buffer if too large
        while (buffer.length > JITTER_BUFFER_MAX + 2) {
          buffer.shift()
        }

        // First frame callback
        if (!firstFrameRef.current) {
          firstFrameRef.current = true
          options.onFirstFrame?.()
        }
      } catch (e) {
        console.error('[CoefficientStream] Frame decode error:', e)
      }
    }

    ws.onclose = () => {
      console.log('[CoefficientStream] Disconnected')
      setIsConnected(false)
      options.onDisconnect?.()
    }

    ws.onerror = (err) => {
      console.error('[CoefficientStream] Error:', err)
    }
  }, [options])

  const disconnect = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setIsConnected(false)
    setIsSpeaking(false)
  }, [])

  /**
   * Get the current coefficients to apply to the 3D model.
   * Called every frame in the render loop.
   * Consumes from jitter buffer and applies smoothing.
   */
  const getCurrentCoefficients = useCallback((): Float32Array => {
    const buffer = bufferRef.current
    const current = currentRef.current

    if (buffer.length >= JITTER_BUFFER_MIN) {
      // Consume the oldest frame from the buffer
      const frame = buffer.shift()!
      const target = frame.coefficients

      // Smooth transition (exponential moving average)
      const alpha = 0.6  // Higher = more responsive, lower = smoother
      for (let i = 0; i < NUM_TOTAL_FLOATS; i++) {
        current[i] = current[i] + alpha * (target[i] - current[i])
      }
    }
    // If buffer is depleted, hold last known values (they're in currentRef)

    return current
  }, [])

  return {
    connect,
    disconnect,
    getCurrentCoefficients,
    isConnected,
    isSpeaking,
  }
}
