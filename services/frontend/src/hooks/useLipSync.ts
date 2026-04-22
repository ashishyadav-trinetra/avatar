/**
 * Audio-driven lip-sync using Web Audio API.
 * Analyzes the agent's audio track in real-time and maps
 * frequency bands to viseme blendshape weights.
 *
 * Approach: frequency-band mapping (Approach B from research):
 *  - Low frequencies  → rounded mouth (viseme_O, viseme_U)
 *  - Mid frequencies   → open mouth (jawOpen, viseme_aa)
 *  - High frequencies  → fricatives (viseme_SS, viseme_FF)
 *  - Overall amplitude → jaw openness
 */
import { useRef, useCallback } from 'react'

interface LipSyncControls {
  start: (
    audioTrack: MediaStreamTrack,
    setMorphTarget: (name: string, weight: number) => void
  ) => void
  stop: () => void
}

// Smoothing factor — higher = smoother but more lag
const SMOOTHING = 0.65

// Viseme mapping: which morph targets to drive and from which frequency bands
const VISEME_MAP = {
  jawOpen:     { band: 'overall', scale: 1.0 },
  viseme_aa:   { band: 'mid',     scale: 0.9 },
  viseme_O:    { band: 'low',     scale: 0.7 },
  viseme_E:    { band: 'midHigh', scale: 0.6 },
  viseme_I:    { band: 'midHigh', scale: 0.5 },
  viseme_U:    { band: 'low',     scale: 0.5 },
  viseme_SS:   { band: 'high',    scale: 0.6 },
  viseme_FF:   { band: 'high',    scale: 0.5 },
  viseme_TH:   { band: 'high',    scale: 0.4 },
  viseme_PP:   { band: 'overall', scale: 0.3 },
  viseme_kk:   { band: 'mid',     scale: 0.4 },
  viseme_nn:   { band: 'mid',     scale: 0.4 },
  viseme_RR:   { band: 'midLow',  scale: 0.5 },
  viseme_CH:   { band: 'high',    scale: 0.5 },
  viseme_DD:   { band: 'mid',     scale: 0.4 },
  viseme_sil:  { band: 'silence', scale: 1.0 },
} as const

type BandName = 'overall' | 'low' | 'midLow' | 'mid' | 'midHigh' | 'high' | 'silence'

export function useLipSync(): LipSyncControls {
  const audioCtxRef = useRef<AudioContext | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const sourceRef = useRef<MediaStreamAudioSourceNode | null>(null)
  const rafRef = useRef<number>(0)
  const smoothedRef = useRef<Record<string, number>>({})

  const start = useCallback((
    audioTrack: MediaStreamTrack,
    setMorphTarget: (name: string, weight: number) => void
  ) => {
    // Create audio context
    const ctx = new AudioContext()
    audioCtxRef.current = ctx

    // Create source from the agent's audio track
    const stream = new MediaStream([audioTrack])
    const source = ctx.createMediaStreamSource(stream)
    sourceRef.current = source

    // Analyser node
    const analyser = ctx.createAnalyser()
    analyser.fftSize = 256
    analyser.smoothingTimeConstant = 0.6
    source.connect(analyser)
    analyserRef.current = analyser

    const bufferLength = analyser.frequencyBinCount  // 128 bins
    const dataArray = new Uint8Array(bufferLength)

    // Frequency band boundaries (for 128 bins at 48kHz, each bin = ~187.5Hz)
    // Low: 0-500Hz (bins 0-2), MidLow: 500-1kHz (bins 3-5),
    // Mid: 1-3kHz (bins 6-15), MidHigh: 3-6kHz (bins 16-31), High: 6kHz+ (bins 32+)
    const bandRanges: Record<string, [number, number]> = {
      low:     [0, 2],
      midLow:  [3, 5],
      mid:     [6, 15],
      midHigh: [16, 31],
      high:    [32, bufferLength - 1],
    }

    function getBandEnergy(data: Uint8Array, start: number, end: number): number {
      let sum = 0
      const count = end - start + 1
      for (let i = start; i <= Math.min(end, data.length - 1); i++) {
        sum += data[i]
      }
      return (sum / count) / 255  // normalize to 0-1
    }

    const loop = () => {
      rafRef.current = requestAnimationFrame(loop)
      analyser.getByteFrequencyData(dataArray)

      // Compute band energies
      const bands: Record<string, number> = {
        overall: 0,
        silence: 0,
      }

      let totalEnergy = 0
      for (const [name, [start, end]] of Object.entries(bandRanges)) {
        bands[name] = getBandEnergy(dataArray, start, end)
        totalEnergy += bands[name]
      }
      bands.overall = totalEnergy / Object.keys(bandRanges).length

      // Silence is inverse of overall (for viseme_sil — closed mouth when quiet)
      bands.silence = Math.max(0, 1.0 - bands.overall * 3)

      // Map bands to viseme weights
      for (const [viseme, config] of Object.entries(VISEME_MAP)) {
        const band = config.band as BandName
        const raw = (bands[band] || 0) * config.scale

        // Exponential smoothing
        const prev = smoothedRef.current[viseme] || 0
        const smoothed = prev * SMOOTHING + raw * (1 - SMOOTHING)
        smoothedRef.current[viseme] = smoothed

        // Clamp and apply
        setMorphTarget(viseme, Math.min(Math.max(smoothed, 0), 1))
      }
    }

    loop()
    console.log('Lip-sync started')
  }, [])

  const stop = useCallback(() => {
    if (rafRef.current) {
      cancelAnimationFrame(rafRef.current)
      rafRef.current = 0
    }
    if (sourceRef.current) {
      sourceRef.current.disconnect()
      sourceRef.current = null
    }
    if (audioCtxRef.current) {
      audioCtxRef.current.close()
      audioCtxRef.current = null
    }
    smoothedRef.current = {}
    console.log('Lip-sync stopped')
  }, [])

  return { start, stop }
}
