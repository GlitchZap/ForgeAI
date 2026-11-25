import { type RefObject, useEffect, useMemo, useRef, useState } from 'react'
import { Canvas, useFrame, useThree } from '@react-three/fiber'
import { Html, Line, OrbitControls } from '@react-three/drei'
import * as THREE from 'three'
import type { Stage } from '@/lib/api'

// Chart ink. Magenta belongs to the track and the live position only.
const INK = '#e8eef1', MAGENTA = '#e5489f', PASS = '#3fd08f', FAIL = '#ff6b5e', SHOAL = '#2c4a57', SOUNDING = '#7d8a91'
const reduceMotion = typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

export type Attempt = {
  iteration: number
  kept: boolean | null            // null while running
  label: string                   // "First score" / "Fix 1: wrong refusal"
  score?: number                  // dev pass rate, when known
  results: Map<string, { passed: boolean }>
}
export type Selection = { iteration: number; caseId: string } | null
type Portal = RefObject<HTMLElement>

const ROW_GAP = 1.9, X0 = -2.4, X1 = 11, BRANCH = new THREE.Vector3(-3.6, 0, 0)

function stagePoints(n: number) {
  const curve = new THREE.CatmullRomCurve3([-12, -10.2, -8.3, -6.4, -4.6].map((x, i) => new THREE.Vector3(x, 0, Math.sin(i * 1.5) * 0.7)))
  return { curve, points: Array.from({ length: n }, (_, i) => curve.getPointAt(n === 1 ? 0 : i / (n - 1))) }
}

const rowZ = (row: number) => row * ROW_GAP
const caseX = (i: number, n: number) => (n <= 1 ? X0 : X0 + (i * (X1 - X0)) / (n - 1))

/** Back the camera off until the whole chart fits the canvas, whatever its aspect. */
function FitCamera({ depth }: { depth: number }) {
  const { camera, size } = useThree()
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera
    const half = THREE.MathUtils.degToRad(cam.fov / 2)
    const aspect = size.width / size.height
    // mostly top-down (like a chart on a table) so rows separate; just enough tilt to read as 3D
    const dist = Math.max(13.9 / (Math.tan(half) * aspect), (depth / 2 + 2.2) / Math.tan(half))  // 13.9 keeps the first stage label in frame
    const cz = depth / 2
    cam.position.set(-0.4, dist * 0.92, cz + dist * 0.4)
    cam.lookAt(-0.4, 0, cz)
    cam.updateProjectionMatrix()
  }, [camera, size.width, size.height, depth])
  return null
}

function Contours({ depth }: { depth: number }) {
  const lines = useMemo(() => [-2.6, -1.6, depth + 1.4, depth + 2.4].map((z, k) =>
    Array.from({ length: 80 }, (_, i) => {
      const x = -14 + i * (28 / 79)
      return new THREE.Vector3(x, 0, z + Math.sin(x * 0.42 + k * 1.7) * 0.45)
    })), [depth])
  return <>{lines.map((l, i) => <Line key={i} points={l} color={SHOAL} lineWidth={1} />)}</>
}

function StageMark({ p, stage, portal, above }: { p: THREE.Vector3; stage: Stage; portal: Portal; above: boolean }) {
  const color = stage.state === 'done' ? INK : stage.state === 'failed' ? FAIL : stage.state === 'active' ? MAGENTA : SHOAL
  return (
    <group position={p}>
      {/* beacon symbol: a ring, filled once the stage is passed */}
      <mesh rotation-x={-Math.PI / 2} position-y={0.01}>
        <ringGeometry args={[0.2, 0.27, 32]} />
        <meshBasicMaterial color={color} />
      </mesh>
      {stage.state === 'done' && (
        <mesh rotation-x={-Math.PI / 2} position-y={0.01}>
          <circleGeometry args={[0.12, 24]} />
          <meshBasicMaterial color={INK} />
        </mesh>
      )}
      <Html portal={portal} position={[0, 0, above ? -0.62 : 0.62]} center zIndexRange={[10, 0]}>
        <span className={`chart-label ${stage.state === 'skipped' || stage.state === 'pending' ? 'opacity-50' : ''}`}>{stage.label}</span>
      </Html>
    </group>
  )
}

/** One test result laid on the chart: a pass is a filled sounding, a fail is a hazard cross. Shape, not only colour. */
function Sounding({ pos, state, dim, selected, onClick, onHover }: {
  pos: THREE.Vector3; state: 'pass' | 'fail' | 'pending'; dim: boolean; selected: boolean
  onClick: () => void; onHover: (on: boolean) => void
}) {
  const ref = useRef<THREE.Group>(null)
  const settled = useRef(true)
  const prev = useRef(state)
  useEffect(() => {
    // a result that arrives while the page is open drops onto the chart; results already there just are
    if (prev.current === 'pending' && state !== 'pending' && ref.current && !reduceMotion) {
      ref.current.position.y = 0.9
      settled.current = false
    }
    prev.current = state
  }, [state])
  useFrame((_, delta) => {
    const g = ref.current
    if (!g || settled.current) return
    g.position.y = THREE.MathUtils.damp(g.position.y, 0, 9, delta)
    if (g.position.y < 0.002) { g.position.y = 0; settled.current = true }
  })
  const op = dim ? 0.38 : 1
  return (
    <group position={[pos.x, 0, pos.z]}>
      <group ref={ref}>
        {state === 'pass' && (
          <mesh rotation-x={-Math.PI / 2} position-y={0.02}>
            <circleGeometry args={[0.17, 20]} />
            <meshBasicMaterial color={PASS} transparent opacity={op} />
          </mesh>
        )}
        {state === 'fail' && [Math.PI / 4, -Math.PI / 4].map((r) => (
          <mesh key={r} rotation={[-Math.PI / 2, 0, r]} position-y={0.03}>
            <planeGeometry args={[0.46, 0.1]} />
            <meshBasicMaterial color={FAIL} transparent opacity={op} />
          </mesh>
        ))}
        {state === 'pending' && (
          <mesh rotation-x={-Math.PI / 2} position-y={0.01}>
            <ringGeometry args={[0.07, 0.1, 16]} />
            <meshBasicMaterial color={SHOAL} />
          </mesh>
        )}
      </group>
      {selected && (
        <mesh rotation-x={-Math.PI / 2} position-y={0.015}>
          <ringGeometry args={[0.24, 0.29, 32]} />
          <meshBasicMaterial color={MAGENTA} />
        </mesh>
      )}
      {/* generous invisible hit target */}
      <mesh rotation-x={-Math.PI / 2} visible={false}
        onClick={(e) => { e.stopPropagation(); onClick() }}
        onPointerOver={(e) => { e.stopPropagation(); onHover(true) }} onPointerOut={() => onHover(false)}>
        <circleGeometry args={[0.24, 12]} />
      </mesh>
    </group>
  )
}

function LiveLight({ target }: { target: THREE.Vector3 | null }) {
  const ref = useRef<THREE.Mesh>(null)
  useFrame(({ clock }, delta) => {
    const m = ref.current
    if (!m || !target) return
    m.position.x = reduceMotion ? target.x : THREE.MathUtils.damp(m.position.x, target.x, 6, delta)
    m.position.z = reduceMotion ? target.z : THREE.MathUtils.damp(m.position.z, target.z, 6, delta)
    m.scale.setScalar(reduceMotion ? 1 : 1 + Math.sin(clock.elapsedTime * 4) * 0.25)
  })
  if (!target) return null
  return (
    <mesh ref={ref} position={[target.x, 0.32, target.z]}>
      <sphereGeometry args={[0.11, 16, 12]} />
      <meshBasicMaterial color={MAGENTA} />
    </mesh>
  )
}

/** Attempt row: baseline and kept fixes solid ink, abandoned fixes dashed grey. */
function AttemptLeg({ row, attempt, portal }: { row: number; attempt: Attempt; portal: Portal }) {
  const z = rowZ(row)
  const pts = row === 0 ? [BRANCH, new THREE.Vector3(X1 + 0.5, 0, 0)]
    : [BRANCH, new THREE.Vector3(X0 - 0.7, 0, z), new THREE.Vector3(X1 + 0.5, 0, z)]
  const abandoned = attempt.kept === false
  return (
    <group>
      <Line points={pts} color={abandoned ? SOUNDING : INK} lineWidth={abandoned ? 1 : 1.6}
        dashed={abandoned} dashSize={0.22} gapSize={0.16} />
      <Html portal={portal} position={[X0 - 0.25, 0, z - 0.62]} zIndexRange={[10, 0]} style={{ transform: 'translateY(-50%)' }}>
        <span className={`chart-label chart-label--leg ${abandoned ? 'chart-label--abandoned' : ''}`}>
          {attempt.label}{attempt.score != null ? ` ${Math.round(attempt.score * 100)}%` : ''}
          {abandoned ? ', reverted' : attempt.kept && row > 0 ? ', kept' : ''}
        </span>
      </Html>
    </group>
  )
}

export function ChartPassage({ stages, attempts, caseOrder, live, selected, onSelect }: {
  stages: Stage[]
  attempts: Attempt[]
  caseOrder: string[]
  live: { iteration: number; caseId: string } | null
  selected: Selection
  onSelect: (s: Selection) => void
}) {
  const pre = useMemo(() => stages.filter((s) => !s.key.startsWith('iter') && s.key !== 'report'), [stages])
  const { curve, points } = useMemo(() => stagePoints(pre.length), [pre.length])
  const track = useMemo(() => [...curve.getPoints(60), BRANCH], [curve])
  const depth = rowZ(Math.max(attempts.length - 1, 0))
  const [hover, setHover] = useState<string | null>(null)
  const overlay = useRef<HTMLDivElement>(null!)
  const running = stages.some((s) => s.state === 'active')

  const liveTarget = useMemo(() => {
    if (!running) return null
    if (live) {
      const row = attempts.findIndex((a) => a.iteration === live.iteration)
      const i = caseOrder.indexOf(live.caseId)
      if (row >= 0 && i >= 0) return new THREE.Vector3(caseX(i, caseOrder.length), 0, rowZ(row))
    }
    const k = pre.findIndex((s) => s.state === 'active')
    return k >= 0 ? points[k] : null
  }, [running, live, attempts, caseOrder, pre, points])

  const hovered = hover ? (() => {
    const cut = hover.indexOf(':')
    const a = attempts.find((x) => String(x.iteration) === hover.slice(0, cut))
    const id = hover.slice(cut + 1)
    return { a, id, r: a?.results.get(id) }
  })() : null

  return (
    <div className="chart-frame relative h-[min(52vh,520px)] min-h-[300px] w-full overflow-hidden"
      role="img" aria-label={`Run chart. ${pre.map((s) => `${s.label}: ${s.state}`).join('. ')}. ${attempts.map((a) =>
        `${a.label}: ${[...a.results.values()].filter((r) => r.passed).length} of ${a.results.size} passed`).join('. ')}`}>
      <Canvas flat dpr={[1, 1.75]} frameloop={running && !reduceMotion ? 'always' : 'demand'} camera={{ fov: 32 }}
        onPointerMissed={() => onSelect(null)} style={{ cursor: hover ? 'pointer' : 'default' }}>
        <FitCamera depth={depth} />
        <color attach="background" args={['#071016']} />
        <mesh visible={attempts.length > 0} rotation-x={-Math.PI / 2} position={[(X0 + X1) / 2 - 0.4, -0.01, depth / 2]}>
          <planeGeometry args={[X1 - X0 + 2.4, depth + 1.9]} />
          <meshBasicMaterial color="#0c1c25" />
        </mesh>
        <Contours depth={depth} />
        <Line points={track} color={MAGENTA} lineWidth={1.6} dashed dashSize={0.3} gapSize={0.2} />
        {pre.map((s, i) => <StageMark key={s.key} p={points[i]} stage={s} portal={overlay} above={i % 2 === 1} />)}
        {attempts.map((a, row) => <AttemptLeg key={a.iteration} row={row} attempt={a} portal={overlay} />)}
        {attempts.map((a, row) => caseOrder.map((id, i) => {
          const r = a.results.get(id)
          return (
            <Sounding key={`${a.iteration}:${id}`} pos={new THREE.Vector3(caseX(i, caseOrder.length), 0, rowZ(row))}
              state={r ? (r.passed ? 'pass' : 'fail') : 'pending'} dim={a.kept === false}
              selected={selected?.iteration === a.iteration && selected.caseId === id}
              onClick={() => r && onSelect({ iteration: a.iteration, caseId: id })}
              onHover={(on) => setHover(on ? `${a.iteration}:${id}` : null)} />
          )
        }))}
        <LiveLight target={liveTarget} />
        <OrbitControls makeDefault enableZoom={false} enablePan={false} minPolarAngle={0.5} maxPolarAngle={0.95}
          minAzimuthAngle={-0.3} maxAzimuthAngle={0.3} target={[0.2, 0, depth / 2]} />
      </Canvas>
      <div ref={overlay} className="pointer-events-none absolute inset-0" />
      {hovered && (
        <div className="pointer-events-none absolute bottom-3 right-3 rounded-md border bg-panel px-3 py-1.5 text-sm shadow-[0_2px_8px_rgba(24,34,46,.12)]">
          <span className="font-semibold tabular-nums">{hovered.id}</span>{' '}
          <span className="text-sounding">{hovered.a?.label}:</span>{' '}
          {hovered.r ? (hovered.r.passed ? <span className="text-starboard">passed</span> : <span className="text-port">failed</span>) : 'not graded yet'}
          {hovered.r && '. Click for the trace.'}
        </div>
      )}
    </div>
  )
}
