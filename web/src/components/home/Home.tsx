import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { ArrowRight, Check, FileText, Globe, Mail, Pause, Play, ShieldCheck, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, importOrReload, percent, type EvalCase, type Requirements, type RunSummary, type Scorecard } from '@/lib/api'

const VoxelSea = lazy(() => importOrReload(() => import('./VoxelSea')).then((m) => ({ default: m.VoxelSea })))

type ToolLog = { tool: string; attached: boolean; evidence_words?: string[]; why?: string }
const scrollTo = (id: string) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
/** Home sections, listed in the app sidebar while the home page is open (one navigation for the whole product). */
export const HOME_SECTIONS = [['how', 'How it works'], ['features', 'What it does'], ['tools', 'Tools'], ['latest', 'Latest run']] as const
export const scrollToSection = scrollTo

/* ------------------------------------------------------------------ hero: headline mirrored in a voxel sea */

function Hero({ go, latest }: { go: (h: string) => void; latest?: RunSummary }) {
  const reduce = useReducedMotion()
  return (
    <section className="relative flex min-h-[calc(100svh-3.5rem)] flex-col items-center justify-center overflow-hidden px-6 text-center md:min-h-[100svh]">
      <div className="absolute inset-x-0 bottom-0 h-[58%]">
        <Suspense fallback={null}><VoxelSea /></Suspense>
        <div className="pointer-events-none absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-black to-transparent" />
      </div>
      <div className="relative z-10 -mt-[18vh]">
        <motion.h1 className="display text-[clamp(4.5rem,15vw,13rem)] leading-[0.85]"
          initial={reduce ? false : { opacity: 0, y: 24 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}>
          forgeai
        </motion.h1>
        {/* the mirror: the same word, flipped, sinking into the sea */}
        <div aria-hidden className="display hero-mirror text-[clamp(4.5rem,15vw,13rem)] leading-[0.85]">forgeai</div>
        <p className="mx-auto mt-[-4vw] max-w-[46ch] text-lg text-ink/80 md:text-xl">
          Give it one paragraph and a folder of documents. It builds the chatbot, writes its own tests,
          fixes what fails, and tells you honestly what still doesn't work.
        </p>
        <div className="mt-8 flex flex-wrap justify-center gap-3">
          <button className="cta-primary" onClick={() => go('new')}><Play className="size-4 fill-current" aria-hidden /> Start a run</button>
          {latest && <button className="cta-link" onClick={() => go(`run/${latest.id}`)}>See a finished run <ArrowRight className="size-4" aria-hidden /></button>}
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ how it works: three steps, a connector that draws itself */

const STEPS = [
  { icon: FileText, title: 'You give it a brief', body: 'One paragraph saying what the assistant is for, plus the documents it may answer from: PDFs, notes, CSV catalogues.' },
  { icon: Play, title: 'It builds and tests', body: 'It asks clarifying questions, checks the documents can support each topic, drafts the agent, writes 20+ tests from the documents, grades every answer twice, and fixes the worst failure.' },
  { icon: ShieldCheck, title: 'You get the evidence', body: 'A working agent you can chat with, every test and its trace, every fix kept or reverted, and a report that says what still fails and why.' },
]

function HowItWorks() {
  const reduce = useReducedMotion()
  return (
    <section id="how" className="mx-auto max-w-[1200px] scroll-mt-20 px-6 py-28">
      <h2 className="display max-w-[18ch] text-[clamp(2.4rem,5vw,4rem)] leading-[1]">from a paragraph to a tested agent</h2>
      <div className="relative mt-16 grid gap-12 md:grid-cols-3 md:gap-8">
        <svg className="absolute left-0 top-[27px] hidden h-2 w-full md:block" preserveAspectRatio="none" viewBox="0 0 100 2" aria-hidden>
          <motion.path d="M 4 1 L 96 1" stroke="var(--color-magenta)" strokeWidth="0.25" fill="none" strokeDasharray="0.9 0.6"
            initial={{ pathLength: reduce ? 1 : 0 }} whileInView={{ pathLength: 1 }} viewport={{ once: true, amount: 0.6 }}
            transition={{ duration: 1.4, ease: [0.65, 0, 0.35, 1] }} />
        </svg>
        {STEPS.map((s, i) => (
          <motion.div key={s.title} className="relative" initial={reduce ? false : { opacity: 0, y: 14 }} whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.6 }} transition={{ delay: reduce ? 0 : 0.25 + i * 0.35, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}>
            <span className="relative z-10 flex size-14 items-center justify-center border border-white/20 bg-black">
              <s.icon className="size-6 text-magenta" aria-hidden />
            </span>
            <h3 className="mt-6 text-xl font-semibold">{s.title}</h3>
            <p className="mt-2 max-w-[38ch] text-sounding">{s.body}</p>
          </motion.div>
        ))}
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ features: timed tabs over a product window with real data */

function useLatestArtifacts(id?: string) {
  const [d, setD] = useState<{ req?: Requirements; cases?: EvalCase[]; scs?: Scorecard[] }>({})
  useEffect(() => {
    if (!id) return
    Promise.all([api.artifact<Requirements>(id, 'requirements.json'), api.artifact<EvalCase[]>(id, 'evalset.json'),
                 api.artifact<Scorecard[]>(id, 'scorecards.json')])
      .then(([req, cases, scs]) => setD({ req, cases, scs })).catch(() => {})
  }, [id])
  return d
}

const TAB_MS = 6500

function Features({ latest }: { latest?: RunSummary }) {
  const { req, cases, scs } = useLatestArtifacts(latest?.id)
  const reduce = useReducedMotion()
  const [tab, setTab] = useState(0)
  const [hover, setHover] = useState(false)
  const [held, setHeld] = useState(false)  // explicit pause button
  const paused = hover || held
  const final = scs?.[scs.length - 1]
  const tabs = [
    { title: 'Requirements', body: 'It interviews the brief and refuses to promise what the documents cannot support.' },
    { title: 'Tests', body: 'It writes its own tests from the documents and throws out any whose expected facts are not in the source.' },
    { title: 'Judging', body: 'Every answer is graded twice, in opposite orders, and only facts both passes credit count.' },
    { title: 'Report', body: 'It fixes the biggest failure, keeps the fix only if the score rises, and reports what still fails.' },
  ]
  useEffect(() => {
    if (paused || reduce) return
    const t = setTimeout(() => setTab((x) => (x + 1) % tabs.length), TAB_MS)
    return () => clearTimeout(t)
  }, [tab, paused, reduce, tabs.length])

  return (
    <section id="features" className="scroll-mt-20 border-y border-white/10 bg-[radial-gradient(120%_80%_at_50%_0%,var(--color-shallows)_0%,var(--color-water)_60%)] py-28"
      onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)} onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setHover(false) }}>
      <div className="mx-auto max-w-[1200px] px-6">
        <h2 className="display mx-auto max-w-[20ch] text-center text-[clamp(2.4rem,5vw,4rem)] leading-[1]">every step shows its working</h2>
        <p className="mx-auto mt-4 max-w-[52ch] text-center text-lg text-sounding">
          {latest ? <>Live data from the <b className="text-ink">{latest.name}</b> run.</> : 'Run the factory once to fill this with real data.'}
        </p>
        <div className="mt-8 flex justify-end">
          <Button variant="ghost" size="sm" className="text-ink" onClick={() => setHeld((h) => !h)} aria-pressed={held}>
            {held ? <><Play /> Resume tour</> : <><Pause /> Pause tour</>}
          </Button>
        </div>
        <div role="tablist" aria-label="What the factory does" className="mt-3 grid gap-px border border-white/10 bg-white/10 md:grid-cols-4"
          onKeyDown={(e) => {
            const d = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0
            if (!d) return
            const n = (tab + d + tabs.length) % tabs.length
            setTab(n); document.getElementById(`feat-tab-${n}`)?.focus()
          }}>
          {tabs.map((t, i) => (
            <button key={t.title} id={`feat-tab-${i}`} role="tab" aria-selected={tab === i} aria-controls="feat-panel"
              tabIndex={tab === i ? 0 : -1} onClick={() => setTab(i)}
              className={`relative bg-black p-5 text-left transition-colors ${tab === i ? 'text-ink' : 'text-sounding hover:text-ink'}`}>
              <span className="absolute inset-x-0 top-0 h-0.5 bg-white/10">
                {tab === i && <motion.span key={`${i}-${paused}`} className="block h-full bg-magenta" initial={{ width: reduce || paused ? '100%' : '0%' }}
                  animate={{ width: '100%' }} transition={{ duration: reduce || paused ? 0 : TAB_MS / 1000, ease: 'linear' }} />}
              </span>
              <span className="block font-semibold text-ink">{t.title}</span>
              <span className="mt-1 block text-[16.5px] leading-relaxed">{t.body}</span>
            </button>
          ))}
        </div>
        <div id="feat-panel" role="tabpanel" aria-labelledby={`feat-tab-${tab}`} className="mt-6 border border-white/15 bg-panel shadow-[0_24px_60px_-24px_rgba(0,0,0,.9)]">
          <div className="flex items-center gap-2 border-b border-white/10 px-4 py-2.5 text-[15px] text-sounding">
            <span className="size-2.5 rounded-full bg-white/15" /><span className="size-2.5 rounded-full bg-white/15" /><span className="size-2.5 rounded-full bg-white/15" />
            <span className="ml-3 truncate">forgeai / {latest?.name ?? 'no runs yet'} / {tabs[tab].title.toLowerCase()}</span>
          </div>
          <motion.div key={tab} className="min-h-[300px] p-6" initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.25 }}>
            {tab === 0 && <ReqWindow req={req} />}
            {tab === 1 && <TestsWindow cases={cases} />}
            {tab === 2 && <JudgeWindow scs={scs} cases={cases} />}
            {tab === 3 && <ReportWindow final={final} latest={latest} />}
          </motion.div>
        </div>
      </div>
    </section>
  )
}

const Empty = () => <p className="text-sounding">Data appears here after your first run.</p>

function ReqWindow({ req }: { req?: Requirements }) {
  if (!req) return <Empty />
  return (
    <ul className="divide-y divide-white/10">{req.groundability.map((g) => (
      <li key={g.topic} className="grid grid-cols-[8rem_minmax(0,1fr)] gap-4 py-3">
        <span className={g.status === 'supported' ? 'text-starboard' : g.status === 'partial' ? 'text-magenta' : 'text-port'}>
          {g.status === 'supported' ? 'Supported' : g.status === 'partial' ? 'Partly covered' : 'Not covered'}</span>
        <span><b className="font-medium">{g.topic.replace(/_/g, ' ')}</b>{g.quote ? <q className="mt-0.5 block truncate text-sounding">{g.quote}</q> : g.status === 'unsupported' && <span className="block text-sounding">The agent will refuse this instead of guessing.</span>}</span>
      </li>))}
    </ul>
  )
}

function TestsWindow({ cases }: { cases?: EvalCase[] }) {
  if (!cases) return <Empty />
  return (
    <ul className="divide-y divide-white/10">{cases.slice(0, 6).map((c) => (
      <li key={c.id} className="grid grid-cols-[5rem_minmax(0,1fr)] gap-4 py-2.5">
        <span className="tabular-nums text-sounding">{c.id}</span>
        <span className="min-w-0"><span className="block truncate">{c.question}</span>
          <span className="block truncate text-sm text-sounding">{c.should_refuse ? 'Must refuse' : c.expected_tool ? `Must use ${c.expected_tool}` : c.key_facts.map((f) => `“${f}”`).join(', ')}</span></span>
      </li>))}
      <li className="pt-3 text-sm text-sounding">{cases.length} tests in this run.</li>
    </ul>
  )
}

function JudgeWindow({ scs, cases }: { scs?: Scorecard[]; cases?: EvalCase[] }) {
  const final = scs?.[scs.length - 1]
  if (!final || !cases) return <Empty />
  const disagreed = final.results.filter((r) => r.judge_agreement === false).slice(0, 4)
  const byId = new Map(cases.map((c) => [c.id, c]))
  return (
    <div>
      <p className="text-lg">The two judge passes disagreed on <b>{percent(final.judge_disagreement_rate)}</b> of the answers they graded. In those cases only facts both credited count:</p>
      <ul className="mt-4 divide-y divide-white/10">{disagreed.map((r) => (
        <li key={r.case_id} className="flex items-baseline gap-4 py-2.5">
          <span className="tabular-nums text-sounding">{r.case_id}</span>
          <span className="min-w-0 flex-1 truncate">{byId.get(r.case_id)?.question}</span>
          <span className={r.passed ? 'text-starboard' : 'text-port'}>{r.passed ? 'passed' : 'failed'}</span>
        </li>))}
      </ul>
    </div>
  )
}

function ReportWindow({ final, latest }: { final?: Scorecard; latest?: RunSummary }) {
  if (!final || !latest?.final) return <Empty />
  const failing = final.results.filter((r) => !r.passed)
  return (
    <div className="grid gap-8 md:grid-cols-[auto_minmax(0,1fr)]">
      <div>
        <p className="display text-[5rem] leading-none">{percent(latest.final.overall_pass_rate)}</p>
        <p className="text-sounding">dev {percent(latest.final.dev_pass_rate)}, holdout {percent(latest.final.holdout_pass_rate)}</p>
      </div>
      <div>
        <p className="font-semibold">What still fails ({failing.length})</p>
        <ul className="mt-2 space-y-1.5">{failing.slice(0, 5).map((r) => (
          <li key={r.case_id} className="flex gap-3"><X className="mt-1 size-4 shrink-0 text-port" aria-hidden /><span className="truncate"><b className="tabular-nums">{r.case_id}</b> {r.failure?.replace('_', ' ')}: <span className="text-sounding">{r.notes[0]}</span></span></li>))}
        </ul>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ tools: picker + which runs attached it, and why */

const TOOL_TEXT: Record<string, string> = {
  csv_lookup: 'Exact lookups in CSV catalogues: part numbers, prices, stock.',
  calculator: 'Arithmetic for totals, discounts and pro-rating.',
  weather: 'Live weather and a 3-day forecast for a named place.',
  current_date: "Today's date, for deadlines and notice periods.",
}

function Tools({ runs }: { runs: RunSummary[] }) {
  const [pick, setPick] = useState('current_date')
  const [logs, setLogs] = useState<Record<string, ToolLog[]>>({})
  useEffect(() => {
    runs.filter((r) => r.status === 'done').forEach((r) =>
      api.artifact<ToolLog[]>(r.id, 'tool_selection.json').then((l) => setLogs((x) => ({ ...x, [r.id]: l }))).catch(() => {}))
  }, [runs])
  const rows = runs.filter((r) => logs[r.id]).map((r) => ({ run: r, t: logs[r.id].find((t) => t.tool === pick) }))
  return (
    <section id="tools" className="mx-auto max-w-[1200px] scroll-mt-20 px-6 py-28">
      <div className="grid gap-12 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div>
          <h2 className="display text-[clamp(2.4rem,5vw,4rem)] leading-[1]">only the tools a brief needs</h2>
          <p className="mt-4 max-w-[44ch] text-lg text-sounding">An HR assistant with a weather tool is a defect. A tool is attached only when a model votes for it and the brief itself shows the need.</p>
          <div className="mt-8 grid gap-px border border-white/10 bg-white/10" role="radiogroup" aria-label="Tool"
            onKeyDown={(e) => {  // roving focus, like native radios
              const keys = Object.keys(TOOL_TEXT)
              const d = e.key === 'ArrowDown' || e.key === 'ArrowRight' ? 1 : e.key === 'ArrowUp' || e.key === 'ArrowLeft' ? -1 : 0
              if (!d) return
              e.preventDefault()
              const n = keys[(keys.indexOf(pick) + d + keys.length) % keys.length]
              setPick(n); document.getElementById(`tool-${n}`)?.focus()
            }}>
            {Object.entries(TOOL_TEXT).map(([k, v]) => (
                <button key={k} id={`tool-${k}`} role="radio" aria-checked={pick === k} tabIndex={pick === k ? 0 : -1} onClick={() => setPick(k)}
                  className={`flex w-full items-start gap-3 bg-black p-4 text-left ${pick === k ? 'outline outline-1 -outline-offset-1 outline-magenta' : 'hover:bg-panel'}`}>
                  <span className={`mt-1 flex size-4 shrink-0 items-center justify-center rounded-full border ${pick === k ? 'border-magenta' : 'border-white/40'}`}>
                    {pick === k && <span className="size-2 rounded-full bg-magenta" />}</span>
                  <span><span className="block font-semibold">{k.replace(/_/g, ' ')}</span><span className="block text-[16px] text-sounding">{v}</span></span>
                </button>))}
          </div>
        </div>
        <div className="self-start border border-white/10">
          <table className="w-full text-left text-[16.5px]">
            <caption className="border-b border-white/10 p-4 text-left text-sounding">Decisions for <b className="text-ink">{pick.replace(/_/g, ' ')}</b> in your runs</caption>
            <thead className="text-sm text-sounding"><tr><th className="p-4 font-medium">Run</th><th className="p-4 font-medium">Attached</th><th className="p-4 font-medium">Evidence in the brief</th></tr></thead>
            <tbody className="divide-y divide-white/10">
              {rows.length === 0 && <tr><td colSpan={3} className="p-4 text-sounding">No finished runs yet.</td></tr>}
              {rows.map(({ run, t }) => (
                <tr key={run.id}>
                  <td className="p-4">{run.name}</td>
                  <td className="p-4">{t?.attached ? <span className="inline-flex items-center gap-1 text-starboard"><Check className="size-4" />yes</span> : <span className="text-sounding">no</span>}</td>
                  <td className="p-4 text-sounding">{t?.why ?? (t?.evidence_words?.length ? t.evidence_words.join(', ') : 'none')}</td>
                </tr>))}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  )
}

/* ------------------------------------------------------------------ latest run: a card anchored on its date */

function LatestRun({ run, go }: { run?: RunSummary; go: (h: string) => void }) {
  if (!run?.final) return null
  const d = new Date(run.updated * 1000)
  return (
    <section id="latest" className="mx-auto max-w-[1200px] scroll-mt-20 px-6 pb-28">
      <button onClick={() => go(`run/${run.id}`)} className="group grid w-full overflow-hidden border border-white/15 text-left md:grid-cols-[auto_minmax(0,1fr)_minmax(0,1fr)]">
        <div className="flex flex-col items-center justify-center border-white/15 bg-panel px-10 py-8 md:border-r">
          <span className="text-sm uppercase tracking-[0.2em] text-sounding">{d.toLocaleString('en', { month: 'short' })}</span>
          <span className="display text-[4.5rem] leading-none">{d.getDate()}</span>
          <span className="text-sounding">{d.getFullYear()}</span>
        </div>
        <div className="p-8">
          <p className="display text-[2.2rem] leading-tight">{run.name.toLowerCase()}</p>
          <p className="mt-3 text-sounding">{run.model} {run.duration_s ? `, ${Math.round(run.duration_s / 60)} min` : ''}</p>
          <span className="mt-6 inline-flex items-center gap-2 font-semibold text-magenta group-hover:gap-3">Open the run <ArrowRight className="size-4" /></span>
        </div>
        <div className="flex items-end justify-end bg-[radial-gradient(80%_90%_at_70%_100%,var(--color-shallows),var(--color-water))] p-8">
          <span className="display text-[6rem] leading-none">{percent(run.final.overall_pass_rate)}</span>
        </div>
      </button>
    </section>
  )
}

/* ------------------------------------------------------------------ page */

export function Home({ runs, go }: { runs: RunSummary[]; go: (h: string) => void }) {
  const latest = useMemo(() => runs.filter((r) => r.status === 'done' && r.final).sort((a, b) => b.updated - a.updated)[0], [runs])
  return (
    <div className="bg-black">
      <Hero go={go} latest={latest} />
      <HowItWorks />
      <Features latest={latest} />
      <Tools runs={runs} />
      <LatestRun run={latest} go={go} />
      <section className="border-t border-white/10 py-28 text-center">
        <h2 className="display mx-auto max-w-[16ch] text-[clamp(2.6rem,6vw,5rem)] leading-[0.95]">bring a brief it has never seen</h2>
        <p className="mx-auto mt-4 max-w-[44ch] text-lg text-sounding">It runs unattended and hands back a working agent with an honest report.</p>
        <button className="cta-primary mt-8" onClick={() => go('new')}><Play className="size-4" aria-hidden /> Start a run</button>
      </section>
      <Footer />
    </div>
  )
}

/* ------------------------------------------------------------------ footer: who built it, and how to reach them */

const SOCIALS: { label: string; href: string; icon: React.ReactNode }[] = [
  { label: 'Portfolio', href: 'https://aayushkr.vercel.app/', icon: <Globe className="size-4" aria-hidden /> },
  { label: 'LinkedIn', href: 'https://www.linkedin.com/in/aayush-kumar-30019728a/',
    icon: <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden><path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM3 9h4v12H3V9Zm7 0h3.8v1.7h.05c.53-1 1.83-2.05 3.77-2.05C21.6 8.65 22 11.2 22 14.5V21h-4v-5.8c0-1.4-.03-3.2-1.95-3.2-1.95 0-2.25 1.52-2.25 3.1V21H10V9Z" /></svg> },
  { label: 'X', href: 'https://x.com/AayushKumar666',
    icon: <svg viewBox="0 0 24 24" className="size-4" fill="currentColor" aria-hidden><path d="M17.75 3h3.07l-6.7 7.66L22 21h-6.17l-4.83-6.32L5.47 21H2.4l7.17-8.2L2 3h6.33l4.37 5.78L17.75 3Zm-1.08 16.2h1.7L7.4 4.73H5.58L16.67 19.2Z" /></svg> },
  { label: 'aayushkripl@gmail.com', href: 'mailto:aayushkripl@gmail.com', icon: <Mail className="size-4" aria-hidden /> },
]

function Footer() {
  return (
    <footer className="border-t border-white/10 px-6 py-14">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-8 md:flex-row md:items-end md:justify-between">
        <div>
          <p className="display text-[2rem] leading-none">forgeai</p>
          <p className="mt-3 max-w-[46ch] text-sounding">Built by <b className="font-semibold text-ink">Aayush Kumar</b>. Runs on local open models through Ollama; the demo documents are fictional.</p>
        </div>
        <nav aria-label="Contact">
          <ul className="flex flex-wrap gap-x-6 gap-y-3">{SOCIALS.map((s) => (
            <li key={s.label}>
              <a href={s.href} target={s.href.startsWith('http') ? '_blank' : undefined} rel="noreferrer"
                className="inline-flex items-center gap-2 text-[16px] text-sounding hover:text-ink">{s.icon}{s.label}</a>
            </li>))}
          </ul>
        </nav>
      </div>
    </footer>
  )
}

