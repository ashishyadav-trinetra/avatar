import { useRef, useCallback, useEffect } from 'react'
import { sendWebRTCOffer } from '../utils/api'

interface UseWebRTCOptions {
  offerUrl: string
  onTrack?: (stream: MediaStream) => void
  onStateChange?: (state: RTCPeerConnectionState) => void
}

export function useWebRTC({ offerUrl, onTrack, onStateChange }: UseWebRTCOptions) {
  const pcRef = useRef<RTCPeerConnection | null>(null)

  const connect = useCallback(async () => {
    // Tear down any existing connection
    if (pcRef.current) {
      pcRef.current.close()
    }

    const pc = new RTCPeerConnection({
      iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
    })
    pcRef.current = pc

    // When avatar video track arrives
    pc.ontrack = (event) => {
      if (event.streams && event.streams[0]) {
        onTrack?.(event.streams[0])
      }
    }

    pc.onconnectionstatechange = () => {
      onStateChange?.(pc.connectionState)
    }

    // Add a recvonly transceiver so the server knows we want video
    pc.addTransceiver('video', { direction: 'recvonly' })

    // Create + send offer
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    // Wait for ICE gathering to complete for cleaner offer
    await new Promise<void>((resolve) => {
      if (pc.iceGatheringState === 'complete') {
        resolve()
        return
      }
      const check = () => {
        if (pc.iceGatheringState === 'complete') {
          pc.removeEventListener('icegatheringstatechange', check)
          resolve()
        }
      }
      pc.addEventListener('icegatheringstatechange', check)
      // Timeout fallback after 4s
      setTimeout(resolve, 4000)
    })

    // Send offer to WebRTC bridge, get answer
    const answer = await sendWebRTCOffer(offerUrl, {
      sdp: pc.localDescription!.sdp,
      type: pc.localDescription!.type,
    })

    await pc.setRemoteDescription(new RTCSessionDescription(answer))
  }, [offerUrl, onTrack, onStateChange])

  const disconnect = useCallback(() => {
    pcRef.current?.close()
    pcRef.current = null
  }, [])

  useEffect(() => {
    return () => {
      pcRef.current?.close()
    }
  }, [])

  return { connect, disconnect }
}
