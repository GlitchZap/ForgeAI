import { useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { ArrowRight, ArrowUp, ChevronDown, MessageSquare, Plus, RotateCcw, Square, Trash2, Wrench } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { api, type EvalCase, type Trace } from '@/lib/api'

// `job` marks an answer still being written on the server: saved with the chat, so a refresh re-attaches to it
type Msg = { role: 'user' | 'assistant'; content: string; trace?: Trace; error?: boolean; seconds?: number; job?: string; started?: number }
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
type Chat = { id: string; title: string; updated: number; msgs: Msg[] }

// shortcut: history lives in this browser's localStorage, per run; move it server-side if several people share a deployment
const key = (runId: string) => `forgeai.chats.${runId}`
const load = (runId: string): Chat[] => { try { return JSON.parse(localStorage.getItem(key(runId)) ?? '[]') } catch { return [] } }
const save = (runId: string, chats: Chat[]) => localStorage.setItem(key(runId), JSON.stringify(chats.slice(0, 50)))
const newId = () => `${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
const when = (t: number) => new Date(t).toLocaleString('en-GB', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })

/** Chat with the run's final agent: the same generic runner the CLI uses, with its sources shown and history kept. */
export function ChatPanel({ id, name, model, cases, ready }: {
  id: string; name: string; model?: string; cases: EvalCase[] | null; ready: boolean
}) {
  const reduce = useReducedMotion()
  const [chats, setChats] = useState<Chat[]>(() => load(id))
  // after a refresh, reopen the conversation whose answer is still being written
  const [active, setActive] = useState<string | null>(() => load(id).find((c) => c.msgs.some((m) => m.job))?.id ?? null)
  const [q, setQ] = useState('')
  const [now, setNow] = useState(Date.now())
  const end = useRef<HTMLDivElement>(null)
  const box = useRef<HTMLTextAreaElement>(null)
  const stopped = useRef(new Set<string>())
  const polling = useRef(new Set<string>())
  const msgs = useMemo(() => chats.find((c) => c.id === active)?.msgs ?? [], [chats, active])
  const pending = msgs.find((m) => m.job)
  const busy = !!pending
  const started = pending?.started ?? now

  const settle = (chatId: string, job: string, m: Msg) =>
    setChats((cs) => cs.map((c) => (c.id === chatId ? { ...c, msgs: c.msgs.map((x) => (x.job === job ? m : x)), updated: Date.now() } : c)))

  /** Wait for a server-side answer; safe to call again after a refresh (each job is polled once per page). */
  const follow = async (chatId: string, job: string, t0: number) => {
    if (polling.current.has(job)) return
    polling.current.add(job)
    for (;;) {
      if (stopped.current.has(job)) return
      try {
        const r = await api.chatJob(job)
        if (r.status === 'running') { await sleep(1500); continue }
        settle(chatId, job, r.status === 'done' && r.trace
          ? { role: 'assistant', content: r.trace.reply.answer, trace: r.trace, seconds: Math.round((Date.now() - t0) / 1000) }
          : { role: 'assistant', error: true, content: r.error ?? 'unknown error' })
      } catch (e) {
        settle(chatId, job, { role: 'assistant', error: true, content: (e as Error).message })
      }
      return
    }
  }
  // after a refresh: pick up every answer that was still being written
  useEffect(() => {
    for (const c of chats) for (const m of c.msgs) if (m.job) follow(c.id, m.job, m.started ?? Date.now())
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { save(id, chats) }, [id, chats])
  useEffect(() => { if (!busy) box.current?.focus() }, [busy, active])  // after the textarea is enabled again
  useEffect(() => { end.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'end' }) }, [msgs, busy, reduce])
  useEffect(() => {
    if (!busy) return
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [busy])

  // suggested openers: real questions from this run's own tests, one per kind, plus one it should refuse
  const suggestions = [...new Map((cases ?? []).filter((c) => !c.should_refuse).map((c) => [c.kind, c.question])).values()].slice(0, 3)
  if (cases?.some((c) => c.should_refuse)) suggestions.push(cases.find((c) => c.should_refuse)!.question)

  const append = (chatId: string, m: Msg) =>
    setChats((cs) => cs.map((c) => (c.id === chatId ? { ...c, msgs: [...c.msgs, m], updated: Date.now() } : c)).sort((a, b) => b.updated - a.updated))

  const send = async (text: string) => {
    const question = text.trim()
    if (!question || busy) return
    let chatId = active
    if (!chatId) {
      chatId = newId()
      const fresh: Chat = { id: chatId, title: question.slice(0, 80), updated: Date.now(), msgs: [] }
      setChats((cs) => [fresh, ...cs])
      setActive(chatId)
    }
    const history = msgs.filter((m) => !m.error && !m.job).map(({ role, content }) => ({ role, content }))
    setQ(''); setNow(Date.now())
    append(chatId, { role: 'user', content: question })
    const t0 = Date.now()
    try {
      const { job } = await api.startChat(id, question, history)
      append(chatId, { role: 'assistant', content: '', job, started: t0 })
      follow(chatId, job, t0)
    } catch (e) {
      append(chatId, { role: 'assistant', error: true, content: (e as Error).message })
    }
  }

  const stop = () => {
    if (!pending?.job || !active) return
    stopped.current.add(pending.job)  // the server finishes the job on its own; we just stop waiting for it
    settle(active, pending.job, { role: 'assistant', error: true, content: 'you stopped this answer' })
  }

  if (!ready) return <p className="py-10 text-sounding">You can question the agent once the run has finished and saved its final definition.</p>

  return (
    <div className="grid gap-8 lg:grid-cols-[15rem_minmax(0,1fr)]">
      {/* history: every conversation with this run's agent, kept in this browser */}
      <aside aria-label="Saved conversations" className="lg:border-r lg:border-white/10 lg:pr-6">
        <Button variant="ghost" className="-ml-3 w-[calc(100%+0.75rem)] justify-start" onClick={() => setActive(null)} disabled={busy}><Plus /> New conversation</Button>
        <h2 className="mt-5 text-[15px] font-semibold text-sounding">History</h2>
        {chats.length === 0 && <p className="mt-2 text-[15px] text-sounding">Your conversations are saved here.</p>}
        <ul className="mt-2 space-y-0.5">{chats.map((c) => (
          <li key={c.id} className="group flex items-start">
            <button onClick={() => setActive(c.id)} disabled={busy} aria-current={active === c.id ? 'true' : undefined}
              className={`min-w-0 flex-1 px-2 py-2 text-left ${active === c.id ? 'bg-white/[.07]' : 'hover:bg-white/[.04]'}`}>
              <span className="flex items-start gap-2"><MessageSquare className="mt-1 size-3.5 shrink-0 text-sounding" aria-hidden />
                <span className="line-clamp-2 text-[15px] leading-snug">{c.title}</span></span>
              <span className="mt-0.5 block pl-5.5 text-xs text-sounding">{when(c.updated)}, {c.msgs.filter((m) => m.role === 'user').length} question{c.msgs.filter((m) => m.role === 'user').length === 1 ? '' : 's'}</span>
            </button>
            <button onClick={() => { setChats((cs) => cs.filter((x) => x.id !== c.id)); if (active === c.id) setActive(null) }}
              aria-label={`Delete conversation: ${c.title}`} className="mt-1.5 p-1.5 text-sounding opacity-0 hover:text-port focus:opacity-100 group-hover:opacity-100">
              <Trash2 className="size-4" /></button>
          </li>))}
        </ul>
      </aside>

      <section aria-label="Ask the agent" className="flex min-h-[560px] min-w-0 flex-col">
        <header className="flex items-center gap-3 border-b border-white/10 pb-4">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-magenta/15 font-display text-lg text-magenta" aria-hidden>f</span>
          <div className="min-w-0">
            <p className="font-semibold leading-snug">{name}</p>
            <p className="text-[15px] text-sounding">Answers only from its documents{model ? `, running on ${model}` : ''}</p>
          </div>
        </header>

        <div className="flex-1 py-8" aria-live="polite">
          {msgs.length === 0 && (
            <div className="max-w-[60ch]">
              <p className="display text-[2.1rem] leading-tight">ask it something</p>
              <p className="mt-2 text-sounding">Start with a question from the run's own tests, including one it should refuse.</p>
              <ul className="mt-6 divide-y divide-white/10 border-y border-white/10">
                {suggestions.map((s) => (
                  <li key={s}><button onClick={() => send(s)} className="group flex w-full items-start gap-3 py-3.5 text-left hover:text-magenta">
                    <ArrowRight className="mt-1.5 size-4 shrink-0 text-sounding group-hover:text-magenta" aria-hidden />
                    <span className="leading-relaxed">{s}</span></button></li>))}
              </ul>
            </div>
          )}
          <ol className="space-y-7">
            <AnimatePresence initial={false}>
              {msgs.filter((m) => !m.job).map((m, i) => (
                <motion.li key={`${active}-${i}`} initial={reduce ? false : { opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
                  className={m.role === 'user' ? 'flex justify-end' : 'flex gap-3'}>
                  {m.role === 'assistant' && <span className="mt-1 flex size-7 shrink-0 items-center justify-center rounded-full bg-magenta/15 font-display text-magenta" aria-hidden>f</span>}
                  {m.role === 'user'
                    ? <p className="max-w-[75%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-white/[.09] px-4 py-2.5 leading-7">{m.content}</p>
                    : <AgentMessage m={m} onRetry={() => { const lastQ = msgs.slice(0, i).reverse().find((x) => x.role === 'user'); if (lastQ) send(lastQ.content) }} />}
                </motion.li>
              ))}
            </AnimatePresence>
            {busy && (
              <li className="flex items-center gap-3" aria-label="The agent is answering">
                <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-magenta/15 font-display text-magenta" aria-hidden>f</span>
                <span className="typing" aria-hidden><i /><i /><i /></span>
                <span className="text-[15px] text-sounding">searching the documents, {Math.round((now - started) / 1000)} s</span>
              </li>
            )}
          </ol>
          <div ref={end} />
        </div>

        <form className="sticky bottom-4" onSubmit={(e) => { e.preventDefault(); send(q) }}>
          <div className="glass flex items-end gap-2 rounded-2xl border border-white/15 px-4 py-2.5 focus-within:border-magenta/70">
            <textarea ref={box} value={q} onChange={(e) => setQ(e.target.value)} rows={1} disabled={busy}
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(q) } }}
              placeholder="Ask about the policies in this run's documents" aria-label="Your question"
              className="max-h-40 min-h-[2.25rem] flex-1 resize-none bg-transparent py-1.5 leading-7 outline-none placeholder:text-sounding [field-sizing:content]" />
            {busy
              ? <Button type="button" size="icon" variant="outline" className="rounded-full" onClick={stop} aria-label="Stop answering"><Square /></Button>
              : <Button type="submit" size="icon" className="rounded-full" disabled={!q.trim()} aria-label="Send"><ArrowUp /></Button>}
          </div>
          <p className="mt-2 px-1 text-[13px] text-sounding">Enter to send, Shift+Enter for a new line. Conversations are saved in this browser.</p>
        </form>
      </section>
    </div>
  )
}

function AgentMessage({ m, onRetry }: { m: Msg; onRetry: () => void }) {
  const [open, setOpen] = useState(false)
  if (m.error) return (
    <div className="max-w-[85%]">
      <p className="text-port">The agent could not answer: {m.content}</p>
      <Button variant="ghost" size="sm" className="mt-1 -ml-2" onClick={onRetry}><RotateCcw /> Try again</Button>
    </div>
  )
  const t = m.trace!
  return (
    <div className="min-w-0 max-w-[85%]">
      <p className={`whitespace-pre-wrap leading-7 ${t.reply.refused ? 'text-sounding' : ''}`}>{m.content}</p>
      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px]">
        {t.reply.refused && <span className="text-sounding">declined{t.reply.refusal_reason ? `: ${t.reply.refusal_reason}` : ''}</span>}
        {t.reply.citations.map((c) => <span key={c} className="rounded-full bg-starboard/12 px-2.5 py-0.5 text-starboard">{c}</span>)}
        {t.tool_calls.map((c, i) => <span key={i} className="inline-flex items-center gap-1 rounded-full bg-magenta/12 px-2.5 py-0.5 text-magenta"><Wrench className="size-3" />{c.tool}</span>)}
        {!t.reply.refused && t.reply.citations.length === 0 && t.tool_calls.length === 0 && <span className="text-port">no source cited</span>}
        <span className="text-sounding">{m.seconds} s</span>
        <button className="inline-flex items-center gap-0.5 text-sounding hover:text-ink" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
          what it read <ChevronDown className={`size-3 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      </div>
      {open && <p className="mt-2 text-[13px] text-sounding">Retrieved {t.retrieved.join(', ') || 'nothing'}{t.tool_calls.map((c) => `; ${c.tool} returned ${c.result.length > 120 ? `${c.result.slice(0, 120)}…` : c.result}`).join('')}</p>}
    </div>
  )
}
