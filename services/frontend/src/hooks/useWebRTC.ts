import { useRef, useCallback, useEffect } from 'react'
import { sendWebRTCOffer } from '../utils/api'

interface UseWebRTCOptions {
  onTrack?: (stream: MediaStream) => void
  onStateChange?: (state: RTCPeerConnectionState) => void
}

export function useWebRTC({ onTrack, onStateChange }: UseWebRTCOptions) {
  const pcRef = useRef<RTCPeerConnection | null>(null)

  const connect = useCallback(async (offerUrl: string) => {
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
      // aiortc doesn't associate tracks with MediaStreams,
      // so event.streams may be empty. Create one from the track.
      const stream = (event.streams && event.streams[0])
        ? event.streams[0]
        : new MediaStream([event.track])
      console.log('WebRTC ontrack:', event.track.kind, 'stream tracks:', stream.getTracks().length)
      onTrack?.(stream)
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
  }, [onTrack, onStateChange])

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
