/**
 * Three.js avatar renderer — loads an Avaturn GLB and exposes
 * morph target (blendshape) controls for lip-sync and expressions.
 */
import { useRef, useCallback } from 'react'
import * as THREE from 'three'
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js'

export interface ThreeAvatarControls {
  mountScene: (canvas: HTMLCanvasElement) => void
  loadAvatar: (glbUrl: string) => Promise<void>
  setMorphTarget: (name: string, weight: number) => void
  getMorphTargetNames: () => string[]
  dispose: () => void
}

export function useThreeAvatar(): ThreeAvatarControls {
  const sceneRef = useRef<THREE.Scene | null>(null)
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null)
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null)
  const meshesRef = useRef<THREE.SkinnedMesh[]>([])
  const animFrameRef = useRef<number>(0)
  const clockRef = useRef(new THREE.Clock())
  const mixerRef = useRef<THREE.AnimationMixer | null>(null)

  const mountScene = useCallback((canvas: HTMLCanvasElement) => {
    // Scene
    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x1a1a2e)
    sceneRef.current = scene

    // Camera — framing for head/shoulders
    const camera = new THREE.PerspectiveCamera(
      30,
      canvas.clientWidth / canvas.clientHeight,
      0.1,
      100
    )
    camera.position.set(0, 1.55, 0.7)  // eye-level, close to face
    camera.lookAt(0, 1.55, 0)
    cameraRef.current = camera

    // Renderer
    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: true,
    })
    renderer.setSize(canvas.clientWidth, canvas.clientHeight)
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
    renderer.outputColorSpace = THREE.SRGBColorSpace
    renderer.toneMapping = THREE.ACESFilmicToneMapping
    renderer.toneMappingExposure = 1.0
    rendererRef.current = renderer

    // Lighting
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.6)
    scene.add(ambientLight)

    const keyLight = new THREE.DirectionalLight(0xffffff, 1.2)
    keyLight.position.set(1, 2, 2)
    scene.add(keyLight)

    const fillLight = new THREE.DirectionalLight(0x8888ff, 0.4)
    fillLight.position.set(-1, 1, 1)
    scene.add(fillLight)

    const rimLight = new THREE.DirectionalLight(0xffffff, 0.3)
    rimLight.position.set(0, 1, -2)
    scene.add(rimLight)

    // Animation loop
    clockRef.current.start()
    const animate = () => {
      animFrameRef.current = requestAnimationFrame(animate)
      const delta = clockRef.current.getDelta()
      if (mixerRef.current) {
        mixerRef.current.update(delta)
      }
      renderer.render(scene, camera)
    }
    animate()

    // Handle resize
    const onResize = () => {
      const w = canvas.clientWidth
      const h = canvas.clientHeight
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h)
    }
    window.addEventListener('resize', onResize)
    ;(canvas as any)._resizeHandler = onResize
  }, [])

  const loadAvatar = useCallback(async (glbUrl: string) => {
    const scene = sceneRef.current
    if (!scene) throw new Error('Scene not mounted — call mountScene first')

    // Remove existing avatar
    meshesRef.current = []
    const toRemove: THREE.Object3D[] = []
    scene.traverse((child) => {
      if (child.userData._isAvatar) toRemove.push(child)
    })
    toRemove.forEach((obj) => scene.remove(obj))

    // Load GLB
    const loader = new GLTFLoader()
    const gltf = await new Promise<any>((resolve, reject) => {
      loader.load(glbUrl, resolve, undefined, reject)
    })

    const model = gltf.scene
    model.userData._isAvatar = true
    scene.add(model)

    // Find all skinned meshes with morph targets
    const skinned: THREE.SkinnedMesh[] = []
    model.traverse((child: THREE.Object3D) => {
      if (
        (child as THREE.SkinnedMesh).isSkinnedMesh &&
        (child as THREE.SkinnedMesh).morphTargetDictionary
      ) {
        skinned.push(child as THREE.SkinnedMesh)
      }
    })
    meshesRef.current = skinned

    console.log(
      'Avatar loaded — skinned meshes:',
      skinned.length,
      'morph targets:',
      skinned.length > 0
        ? Object.keys(skinned[0].morphTargetDictionary || {}).slice(0, 20)
        : 'none'
    )

    // Set up animation mixer if GLB contains animations
    if (gltf.animations && gltf.animations.length > 0) {
      const mixer = new THREE.AnimationMixer(model)
      mixerRef.current = mixer
      // Play idle animation if there is one
      const idleClip = gltf.animations.find(
        (a: THREE.AnimationClip) => /idle/i.test(a.name)
      ) || gltf.animations[0]
      if (idleClip) {
        mixer.clipAction(idleClip).play()
      }
    }

    // Auto-frame the head: find the head bone or estimate from bounding box
    const box = new THREE.Box3().setFromObject(model)
    const height = box.max.y - box.min.y
    const headY = box.min.y + height * 0.85  // ~85% up is head level

    if (cameraRef.current) {
      cameraRef.current.position.set(0, headY, 0.65)
      cameraRef.current.lookAt(0, headY - 0.02, 0)
    }
  }, [])

  const setMorphTarget = useCallback((name: string, weight: number) => {
    for (const mesh of meshesRef.current) {
      const dict = mesh.morphTargetDictionary
      const influences = mesh.morphTargetInfluences
      if (dict && influences && name in dict) {
        influences[dict[name]] = weight
      }
    }
  }, [])

  const getMorphTargetNames = useCallback((): string[] => {
    if (meshesRef.current.length === 0) return []
    return Object.keys(meshesRef.current[0].morphTargetDictionary || {})
  }, [])

  const dispose = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current)
    }
    if (rendererRef.current) {
      rendererRef.current.dispose()
    }
    const canvas = rendererRef.current?.domElement
    if (canvas && (canvas as any)._resizeHandler) {
      window.removeEventListener('resize', (canvas as any)._resizeHandler)
    }
    meshesRef.current = []
    mixerRef.current = null
  }, [])

  return { mountScene, loadAvatar, setMorphTarget, getMorphTargetNames, dispose }
}
