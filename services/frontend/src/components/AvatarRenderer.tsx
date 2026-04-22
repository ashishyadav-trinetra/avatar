/**
 * AvatarRenderer — Three.js component that loads a GLB avatar
 * and drives its morph targets from coefficient stream data.
 *
 * Uses React Three Fiber for declarative Three.js rendering.
 */

import React, { useRef, useEffect, Suspense } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { useGLTF, Environment } from '@react-three/drei'
import * as THREE from 'three'
import { getExpression, getJaw, getHeadPose, getEyeGaze, NUM_TOTAL_FLOATS } from '../lib/avatarSpec'

// ── Inner component: the animated avatar mesh ───────────────

interface AvatarMeshProps {
  glbUrl: string
  getCoefficients: () => Float32Array
  isSpeaking: boolean
}

function AvatarMesh({ glbUrl, getCoefficients, isSpeaking }: AvatarMeshProps) {
  const gltf = useGLTF(glbUrl)
  const groupRef = useRef<THREE.Group>(null)
  const meshRef = useRef<THREE.Mesh | null>(null)

  // Find the mesh with morph targets
  useEffect(() => {
    gltf.scene.traverse((child) => {
      if (child instanceof THREE.Mesh && child.morphTargetInfluences) {
        meshRef.current = child
        console.log(
          `[AvatarRenderer] Found mesh with ${child.morphTargetInfluences.length} morph targets`,
          child.morphTargetDictionary
        )
      }
    })
  }, [gltf])

  // Per-frame animation: apply coefficients to morph targets + transforms
  useFrame(() => {
    const mesh = meshRef.current
    if (!mesh || !mesh.morphTargetInfluences) return

    const coeffs = getCoefficients()
    if (!coeffs || coeffs.length < NUM_TOTAL_FLOATS) return

    const expression = getExpression(coeffs)
    const jaw = getJaw(coeffs)
    const headPose = getHeadPose(coeffs)

    // Apply expression blendshapes (exp_0 through exp_49)
    const dict = mesh.morphTargetDictionary
    if (dict) {
      // Map by name if available
      for (let i = 0; i < 50; i++) {
        const name = `exp_${i}`
        if (name in dict) {
          const idx = dict[name]
          // Morph target influences are 0-1, but FLAME params can be -3 to 3
          // Normalize: clamp and scale
          mesh.morphTargetInfluences![idx] = Math.max(0, Math.min(1, expression[i] / 2))
        }
      }

      // Apply jaw blendshapes (jaw_0 through jaw_5)
      for (let i = 0; i < 6; i++) {
        const name = `jaw_${i}`
        if (name in dict) {
          const idx = dict[name]
          mesh.morphTargetInfluences![idx] = Math.max(0, Math.min(1, jaw[i] / 2))
        }
      }
    } else {
      // Fallback: apply by index directly
      const numTargets = mesh.morphTargetInfluences.length
      for (let i = 0; i < Math.min(56, numTargets); i++) {
        const value = i < 50 ? expression[i] : jaw[i - 50]
        mesh.morphTargetInfluences[i] = Math.max(0, Math.min(1, value / 2))
      }
    }

    // Apply head pose rotation to the group
    if (groupRef.current) {
      const [pitch, yaw, roll] = headPose
      groupRef.current.rotation.x = pitch   // pitch
      groupRef.current.rotation.y = yaw     // yaw
      groupRef.current.rotation.z = roll    // roll
    }
  })

  return (
    <group ref={groupRef}>
      <primitive object={gltf.scene} />
    </group>
  )
}

// ── Camera setup ────────────────────────────────────────────

function CameraSetup() {
  const { camera } = useThree()

  useEffect(() => {
    // Position camera for head/bust view
    camera.position.set(0, 0.08, 0.35)
    camera.lookAt(0, 0.05, 0)
  }, [camera])

  return null
}

// ── Main exported component ─────────────────────────────────

interface AvatarRendererProps {
  glbUrl: string
  getCoefficients: () => Float32Array
  isSpeaking: boolean
  size?: number
  style?: React.CSSProperties
}

export function AvatarRenderer({
  glbUrl,
  getCoefficients,
  isSpeaking,
  size = 220,
  style,
}: AvatarRendererProps) {
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        overflow: 'hidden',
        background: '#1a1a2e',
        boxShadow: isSpeaking
          ? '0 0 0 3px var(--accent, #6c63ff), 0 0 32px rgba(108,99,255,0.4)'
          : '0 0 0 2px var(--border, #333)',
        transition: 'box-shadow 0.3s ease',
        ...style,
      }}
    >
      <Canvas
        gl={{
          antialias: true,
          alpha: true,
          powerPreference: 'high-performance',
        }}
        dpr={[1, 2]}
      >
        <CameraSetup />

        {/* Lighting */}
        <ambientLight intensity={0.6} />
        <directionalLight position={[2, 3, 5]} intensity={1.0} />
        <directionalLight position={[-2, 1, -3]} intensity={0.3} />

        {/* Avatar */}
        <Suspense fallback={null}>
          <AvatarMesh
            glbUrl={glbUrl}
            getCoefficients={getCoefficients}
            isSpeaking={isSpeaking}
          />
        </Suspense>

        {/* Subtle environment reflections */}
        <Environment preset="apartment" />
      </Canvas>
    </div>
  )
}
