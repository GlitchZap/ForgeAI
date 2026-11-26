import { useCallback, useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { BookOpen, Home as HomeIcon, Moon, PanelLeftClose, PanelLeftOpen, Plus, Sun } from 'lucide-react'
import { Sidebar, SidebarBody, SidebarLink, useSidebar } from '@/components/ui/sidebar'
import { Home, HOME_SECTIONS, scrollToSection } from '@/components/home/Home'
import { NewRun } from '@/components/NewRun'
import { RunView } from '@/components/RunView'
import { Logbook } from '@/components/Logbook'
import { api, percent, type RunSummary } from '@/lib/api'

function useHashRoute(): [string, (h: string) => void] {
  const [hash, setHash] = useState(() => location.hash.slice(1))
  useEffect(() => {
    const on = () => { setHash(location.hash.slice(1)); window.scrollTo(0, 0) }
    window.addEventListener('hashchange', on)
    return () => window.removeEventListener('hashchange', on)
  }, [])
  return [hash, (h) => { location.hash = h }]
}

type Health = { ok: boolean; error?: string; missing?: Record<string, string>; provider?: string } | null

/** Light / dark switch: a class on <html> swaps the colour tokens; the choice is remembered. */
export function ThemeSwitch() {
  const [light, setLight] = useState(() => localStorage.getItem('forgeai.theme') === 'light')
  useEffect(() => {
    document.documentElement.classList.toggle('light', light)
    localStorage.setItem('forgeai.theme', light ? 'light' : 'dark')
    window.dispatchEvent(new Event('forgeai-theme'))
  }, [light])
  return (
    <button role="switch" aria-checked={light} onClick={() => setLight((l) => !l)} aria-label="Light theme"
      className="relative inline-flex h-7 w-[52px] shrink-0 items-center rounded-full border border-white/20 bg-white/[.06] px-1 transition-colors hover:border-white/40">
      <Moon className="absolute left-1.5 size-3.5 text-sounding" aria-hidden />
      <Sun className="absolute right-1.5 size-3.5 text-sounding" aria-hidden />
      <span className={`relative z-10 size-5 rounded-full bg-ink shadow transition-transform duration-300 ${light ? 'translate-x-[23px]' : ''}`} />
    </button>
  )
}

/** Shows its children only while the floating sidebar is expanded (hover on desktop, always in the phone drawer). */
function WhenOpen({ children, className }: { children: React.ReactNode; className?: string }) {
  const { open } = useSidebar()
  return <motion.div className={className} animate={{ opacity: open ? 1 : 0, display: open ? 'block' : 'none' }}>{children}</motion.div>
}

const icon = 'size-5 shrink-0 text-ink'

function NavContent({ runs, route, health }: { runs: RunSummary[]; route: string; health: Health }) {
  const { open, setOpen } = useSidebar()
  const current = route.startsWith('run/') ? route.split('/')[1] : null
  const pill = (active: boolean) => `rounded-xl px-2 ${active ? 'bg-white/[.09]' : 'hover:bg-white/[.05]'}`
  return (
    <>
      <div className="no-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto overflow-x-hidden">
        <div className={`flex items-center gap-2 ${open ? 'justify-between' : 'flex-col'}`}>
          <a href="#" className="flex items-center gap-2 px-1 py-1" aria-label="forgeai home">
            <img src="/favicon.svg" alt="" className="size-7 shrink-0 rounded-md" />
            <WhenOpen><span className="display whitespace-pre text-[1.6rem] leading-none">forgeai</span></WhenOpen>
          </a>
          <button onClick={() => setOpen(!open)} aria-label={open ? 'Collapse sidebar' : 'Expand sidebar'} aria-expanded={open}
            className="hidden size-8 items-center justify-center rounded-lg text-sounding hover:bg-white/[.08] hover:text-ink md:flex">
            {open ? <PanelLeftClose className="size-4.5" /> : <PanelLeftOpen className="size-4.5" />}
          </button>
        </div>
        <nav aria-label="App" className="mt-6 flex flex-col gap-1">
          <SidebarLink className={pill(route === '')} link={{ label: 'Home', href: '#', icon: <HomeIcon className={icon} /> }} />
          {route === '' && open && (
            <ul className="mb-1 ml-4 border-l border-white/10" aria-label="On this page">{HOME_SECTIONS.map(([id, label]) => (
              <li key={id}><button onClick={() => setTimeout(() => scrollToSection(id), 60)}
                className="block w-full whitespace-nowrap px-4 py-1.5 text-left text-[15px] text-sounding hover:text-ink">{label}</button></li>))}
            </ul>
          )}
          <SidebarLink className={pill(route === 'new')} link={{ label: 'New run', href: '#new', icon: <Plus className={icon} /> }} />
          <SidebarLink className={pill(route === 'runs')} link={{ label: 'Logbook', href: '#runs', icon: <BookOpen className={icon} /> }} />
        </nav>
        <WhenOpen className="mt-6"><h2 className="whitespace-nowrap px-2 text-[13px] font-semibold text-sounding">Recent runs</h2></WhenOpen>
        <ul aria-label="Runs" className="mt-2 flex flex-col gap-1">{runs.filter((r) => !r.archived).map((r) => (
          <li key={r.id}>
            <a href={`#run/${r.id}`} aria-current={current === r.id ? 'page' : undefined} title={r.name}
              className={`flex items-start gap-2 py-1.5 ${pill(current === r.id)}`}>
              {/* collapsed rail: the score is the icon */}
              <span className={`mt-0.5 flex size-7 shrink-0 items-center justify-center rounded-lg text-[11px] font-bold tabular-nums ${r.status === 'running' || r.status === 'awaiting_approval' ? 'bg-magenta/20 text-magenta' : 'bg-white/[.08]'}`}>
                {r.final ? Math.round(r.final.overall_pass_rate * 100) : '…'}
              </span>
              <WhenOpen className="min-w-0">
                <span className="block text-[15px] font-medium leading-snug">{r.name}</span>
                <span className="block text-xs text-sounding">{r.status === 'done' ? 'finished' : r.status.replace('_', ' ')}{r.final ? `, ${percent(r.final.overall_pass_rate)}` : ''}, {r.provider === 'groq' ? 'Groq' : 'Ollama'}</span>
              </WhenOpen>
            </a>
          </li>))}
        </ul>
      </div>
      <div className="flex items-center justify-between gap-3 border-t border-white/10 pt-3">
        <span title={health?.ok ? 'Models ready' : health?.error ?? 'Models not ready'} className={`ml-2 size-2.5 shrink-0 rounded-full ${health === null ? 'bg-white/30' : health.ok ? 'bg-starboard' : 'bg-port'}`} />
        <WhenOpen className="min-w-0 flex-1 truncate text-xs text-sounding">{health === null ? 'Checking…' : `${health.provider === 'groq' ? 'Groq' : 'Ollama'} ${health.ok ? 'ready' : 'not ready'}`}</WhenOpen>
        <WhenOpen><ThemeSwitch /></WhenOpen>
      </div>
    </>
  )
}

export default function App() {
  const [runs, setRuns] = useState<RunSummary[]>([])
  const [health, setHealth] = useState<Health>(null)
  const [route, go] = useHashRoute()
  const [open, setOpen] = useState(() => window.innerWidth >= 768 && localStorage.getItem('forgeai.sidebar') !== 'closed')
  const refresh = useCallback(() => api.runs().then(setRuns).catch(() => {}), [])

  useEffect(() => {
    refresh()
    api.health().then(setHealth).catch(() => setHealth({ ok: false, error: 'API not reachable' }))
    const t = setInterval(refresh, 4000)
    return () => clearInterval(t)
  }, [refresh])
  useEffect(() => { document.documentElement.classList.toggle('light', localStorage.getItem('forgeai.theme') === 'light') }, [])
  useEffect(() => { if (window.innerWidth < 768) setOpen(false) }, [route])  // phones: close the drawer after navigating
  useEffect(() => {  // crossing into phone width must not leave the full-screen drawer open
    const mq = window.matchMedia('(max-width: 767px)')
    const on = () => { if (mq.matches) setOpen(false) }
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [])
  useEffect(() => { if (window.innerWidth >= 768) localStorage.setItem('forgeai.sidebar', open ? 'open' : 'closed') }, [open])

  const [, runId, section] = route.split('/')
  const current = route.startsWith('run/') ? runs.find((r) => r.id === runId) : undefined

  return (
    <div className="md:flex">
      {/* floating sidebar: an icon rail that expands on hover, inset from the window on glass */}
      <div className="sticky top-0 z-40 md:h-dvh md:p-3">
        <Sidebar open={open} setOpen={setOpen}>
          <SidebarBody className="glass justify-between gap-6 rounded-2xl border border-white/10 bg-panel/70 shadow-[0_20px_50px_-20px_rgba(0,0,0,.6)] dark:bg-panel/70">
            <NavContent runs={runs} route={route} health={health} />
          </SidebarBody>
        </Sidebar>
      </div>
      <main className="min-w-0 flex-1">
        {route === '' ? <Home runs={runs} go={go} />
          : route === 'new' ? <NewRun modelsOk={!!health?.ok} modelsError={health?.ok ? undefined : health?.error} onStarted={(id) => { refresh(); go(`run/${id}`) }} />
          : route === 'runs' ? <Logbook runs={runs} onChanged={refresh} />
          : current ? <RunView key={current.id} run={current} section={section ?? 'overview'} />
          : <p className="p-10 text-sounding">{runs.length ? 'That run does not exist.' : 'Loading run…'}</p>}
      </main>
    </div>
  )
}
