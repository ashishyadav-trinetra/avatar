import { create } from 'zustand'

export type SessionStatus =
  | 'idle'
  | 'uploading'
  | 'initializing'
  | 'ready'
  | 'connecting'
  | 'active'
  | 'error'

export interface SessionData {
  sessionId: string
  livekitToken: string
  livekitUrl: string
  glbUrl: string
  coefficientWsUrl: string
  model: string
  reconstructionTimeMs: number
}

interface AvatarStore {
  status: SessionStatus
  session: SessionData | null
  error: string | null
  isMuted: boolean
  isSpeaking: boolean     // avatar is speaking
  transcript: string[]    // recent conversation lines

  setStatus:   (s: SessionStatus) => void
  setSession:  (s: SessionData | null) => void
  setError:    (e: string | null) => void
  setMuted:    (m: boolean) => void
  setSpeaking: (s: boolean) => void
  addTranscript: (line: string) => void
  reset:       () => void
}

export const useAvatarStore = create<AvatarStore>((set) => ({
  status:     'idle',
  session:    null,
  error:      null,
  isMuted:    false,
  isSpeaking: false,
  transcript: [],

  setStatus:   (status)   => set({ status }),
  setSession:  (session)  => set({ session }),
  setError:    (error)    => set({ error }),
  setMuted:    (isMuted)  => set({ isMuted }),
  setSpeaking: (isSpeaking) => set({ isSpeaking }),
  addTranscript: (line)   => set((s) => ({
    transcript: [...s.transcript.slice(-30), line]  // keep last 30 lines
  })),
  reset: () => set({
    status: 'idle', session: null, error: null,
    isMuted: false, isSpeaking: false, transcript: [],
  }),
}))
