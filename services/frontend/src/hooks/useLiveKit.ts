import { useRef, useCallback } from 'react'
import {
  Room,
  RoomEvent,
  Track,
  RemoteTrack,
  RemoteTrackPublication,
  Participant,
  RemoteParticipant,
  TrackPublication,
  DisconnectReason,
} from 'livekit-client'

interface UseLiveKitOptions {
  onAgentSpeaking?: (speaking: boolean) => void
  onTranscript?: (text: string, isAgent: boolean) => void
  onDisconnect?: () => void
}

export function useLiveKit({
  onAgentSpeaking,
  onTranscript,
  onDisconnect,
}: UseLiveKitOptions) {
  const roomRef = useRef<Room | null>(null)

  const connect = useCallback(async (url: string, token: string) => {
    const room = new Room({
      adaptiveStream: true,
      dynacast: true,
      audioCaptureDefaults: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    })
    roomRef.current = room

    // ── Room events ───────────────────────────────────────
    room.on(RoomEvent.Disconnected, (reason?: DisconnectReason) => {
      console.log('LiveKit disconnected:', reason)
      onDisconnect?.()
    })

    // Track when agent (avatar) is speaking
    room.on(RoomEvent.ActiveSpeakersChanged, (speakers: Participant[]) => {
      const agentSpeaking = speakers.some(
        (p) => p.identity !== 'user' && p.isSpeaking
      )
      onAgentSpeaking?.(agentSpeaking)
    })

    // Attach remote audio tracks so the agent's voice plays through speakers
    room.on(
      RoomEvent.TrackSubscribed,
      (track: RemoteTrack, publication: RemoteTrackPublication, participant: RemoteParticipant) => {
        if (track.kind === Track.Kind.Audio) {
          const el = track.attach()          // creates <audio> element
          el.id = `lk-audio-${participant.identity}`
          document.body.appendChild(el)       // must be in DOM to play
          console.log(`Attached audio track from ${participant.identity}`)
        }
      }
    )

    // Clean up audio elements when track unsubscribed
    room.on(
      RoomEvent.TrackUnsubscribed,
      (track: RemoteTrack) => {
        track.detach().forEach((el) => el.remove())
      }
    )

    // Data channel messages (transcript from agent)
    room.on(RoomEvent.DataReceived, (payload: Uint8Array, participant?: Participant) => {
      try {
        const msg = JSON.parse(new TextDecoder().decode(payload))
        if (msg.type === 'transcript') {
          const isAgent = participant?.identity !== 'user'
          onTranscript?.(msg.text, isAgent)
        }
      } catch {
        // ignore non-JSON
      }
    })

    // Connect to LiveKit room
    await room.connect(url, token)
    console.log('Connected to LiveKit room:', room.name)

    // Enable microphone
    await room.localParticipant.setMicrophoneEnabled(true)

    return room
  }, [onAgentSpeaking, onTranscript, onDisconnect])

  const disconnect = useCallback(async () => {
    if (roomRef.current) {
      await roomRef.current.disconnect()
      roomRef.current = null
    }
  }, [])

  const setMicEnabled = useCallback(async (enabled: boolean) => {
    await roomRef.current?.localParticipant.setMicrophoneEnabled(enabled)
  }, [])

  return { connect, disconnect, setMicEnabled, roomRef }
}
