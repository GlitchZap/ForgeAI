import { useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import * as THREE from 'three'

// A rolling sea of voxels: one instanced mesh, heights from two travelling sine swells.
const COLS = 56, ROWS = 20, GAP = 0.46  // ~1100 voxels: measured 31 fps at 1872 on the AMD integrated GPU
const PALETTE = { dark: { deep: new THREE.Color('#1b5a72'), crest: new THREE.Color('#e5489f'), bg: '#000000' }, light: { deep: new THREE.Color('#5f9ab5'), crest: new THREE.Color('#e5489f'), bg: '#ffffff' } }
const isLight = () => document.documentElement.classList.contains('light')
function useLight() {
  const [light, setLight] = useState(isLight)
  useEffect(() => { const on = () => setLight(isLight()); window.addEventListener('forgeai-theme', on); return () => window.removeEventListener('forgeai-theme', on) }, [])
  return light
}
const reduceMotion = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

function Voxels({ light }: { light: boolean }) {
  const { deep: DEEP, crest: CREST } = light ? PALETTE.light : PALETTE.dark
  const mesh = useRef<THREE.InstancedMesh>(null!)
  const tmp = useMemo(() => new THREE.Object3D(), [])
  const col = useMemo(() => new THREE.Color(), [])
  const draw = (t: number) => {
    let i = 0
    for (let r = 0; r < ROWS; r++) {
      for (let c = 0; c < COLS; c++) {
        const x = (c - COLS / 2) * GAP, z = -r * GAP
        const h = Math.sin(x * 0.55 + t * 0.9) * 0.45 + Math.sin(z * 0.8 - t * 0.6 + x * 0.2) * 0.35
        tmp.position.set(x, h, z)
        tmp.scale.setScalar(0.24 + Math.max(0, h) * 0.08)
        tmp.updateMatrix()
        mesh.current.setMatrixAt(i, tmp.matrix)
        mesh.current.setColorAt(i, col.copy(DEEP).lerp(CREST, THREE.MathUtils.clamp((h + 0.3) / 1.1, 0, 1) * (1 - (r / ROWS) * 0.6)))
        i++
      }
    }
    mesh.current.instanceMatrix.needsUpdate = true
    if (mesh.current.instanceColor) mesh.current.instanceColor.needsUpdate = true
  }
  const invalidate = useThree((s) => s.invalidate)
  useEffect(() => { draw(0.6); invalidate() }, [])  // eslint-disable-line react-hooks/exhaustive-deps -- static frame must be redrawn
  useFrame(({ clock }) => { if (!reduceMotion) draw(clock.elapsedTime) })
  return (
    <instancedMesh ref={mesh} args={[undefined, undefined, COLS * ROWS]}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial roughness={0.35} metalness={0.2} />
    </instancedMesh>
  )
}

/** Portrait screens see a narrow slice of the sea: back the camera off and raise it so the swell fills the frame. */
function FitCamera() {
  const { camera, size, invalidate } = useThree()
  useEffect(() => {
    const k = Math.min(2, Math.max(1, 1.5 / (size.width / size.height)))
    camera.position.set(0, 2.6 * Math.min(k, 1.5), 6.2 * k)
    camera.lookAt(0, -0.2, -3.2)
    invalidate()
  }, [camera, size.width, size.height, invalidate])
  return null
}

/** Renders only while on screen, so the landing page costs nothing once you scroll past it. */
export function VoxelSea() {
  const light = useLight()
  const bg = light ? PALETTE.light.bg : PALETTE.dark.bg
  const host = useRef<HTMLDivElement>(null)
  const [visible, setVisible] = useState(true)
  useEffect(() => {
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting))
    if (host.current) io.observe(host.current)
    return () => io.disconnect()
  }, [])
  return (
    <div ref={host} className="absolute inset-0" aria-hidden>
      <Canvas dpr={[1, 1.25]} frameloop={visible && !reduceMotion ? 'always' : 'demand'}
        camera={{ position: [0, 2.6, 6.2], fov: 42 }}>
        <FitCamera />
        <color attach="background" args={[bg]} />
        <fog attach="fog" args={[bg, light ? 11 : 8, light ? 32 : 26]} />
        <ambientLight intensity={0.9} />
        <directionalLight position={[2, 6, 4]} intensity={2.4} color="#ffd9ee" />
        <pointLight position={[0, 1.5, -2]} intensity={light ? 14 : 40} distance={14} color="#e5489f" />
        <Voxels key={String(light)} light={light} />
      </Canvas>
    </div>
  )
}
