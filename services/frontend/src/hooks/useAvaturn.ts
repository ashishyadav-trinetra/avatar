/**
 * Avaturn SDK integration hook.
 * Opens an iframe for 3D avatar creation/customization.
 * On export, provides the GLB URL for Three.js rendering.
 */
import { useRef, useCallback, useState } from 'react'

const AVATURN_SUBDOMAIN = import.meta.env.VITE_AVATURN_SUBDOMAIN || 'demo'

interface UseAvaturnOptions {
  onExport?: (glbUrl: string) => void
}

export function useAvaturn({ onExport }: UseAvaturnOptions) {
  const sdkRef = useRef<any>(null)
  const [isEditorOpen, setEditorOpen] = useState(false)

  const openEditor = useCallback(async (container: HTMLDivElement) => {
    // Dynamically import to avoid SSR issues and reduce initial bundle
    const { AvaturnSDK } = await import('@avaturn/sdk')

    const sdk = new AvaturnSDK()
    sdkRef.current = sdk

    const url = `https://${AVATURN_SUBDOMAIN}.avaturn.dev`

    await sdk.init(container, { url })
    setEditorOpen(true)

    sdk.on('export', (data: any) => {
      console.log('Avaturn export:', data)
      // data contains the GLB URL or blob
      const glbUrl = data.url || data.avatarUrl || ''
      if (glbUrl) {
        onExport?.(glbUrl)
      } else if (data.data) {
        // If we get raw blob data, create a blob URL
        const blob = new Blob([data.data], { type: 'model/gltf-binary' })
        const blobUrl = URL.createObjectURL(blob)
        onExport?.(blobUrl)
      }
      setEditorOpen(false)
    })
  }, [onExport])

  const closeEditor = useCallback(() => {
    sdkRef.current = null
    setEditorOpen(false)
  }, [])

  return { openEditor, closeEditor, isEditorOpen }
}
