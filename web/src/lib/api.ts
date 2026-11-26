import { useEffect, useState } from 'react'

export type RunSummary = {
  id: string
  name: string
  status: 'running' | 'done' | 'failed' | 'incomplete' | 'awaiting_approval' | 'stopped'
  error?: string | null
  final?: { dev_pass_rate: number; holdout_pass_rate: number; overall_pass_rate: number } | null
  stop_reason?: string
  duration_s?: number
  tokens?: number
  model?: string
  provider?: 'ollama' | 'groq'
  archived?: boolean
  updated: number
}

export type InputSet = { id: string; group: string; brief: string; docs: string[] }

export type ForgeEvent = { ts: number; stage: string; status: string; [k: string]: unknown }

export type CaseResult = {
  case_id: string; kind: string; split: string; passed: boolean; refused: boolean; failure: string | null
  notes: string[]; answer: string; fact_recall_det: number | null; fact_recall_llm: number | null
  grounded: boolean | null; judge_agreement: boolean | null; retrieval_hit?: boolean | null
  trace?: { retrieved: { id: string; text: string }[]; tool_calls: { tool: string; args: Record<string, unknown>; result: string }[];
            citations: string[]; refusal_reason: string } | null
  judge_passes?: { order: string; facts_present: boolean[]; unsupported_claims: string[] }[]
}
export type Scorecard = {
  iteration: number; dev_pass_rate: number; holdout_pass_rate: number; overall_pass_rate: number
  by_kind: Record<string, number>; failures: Record<string, number>; judge_disagreement_rate: number
  tokens: number; seconds: number; results: CaseResult[]
}
export type EvalCase = {
  id: string; kind: string; question: string; should_refuse: boolean; expected_sources: string[]
  key_facts: string[]; expected_tool: string | null; split: string
}
export type ChangeLog = {
  iteration: number; category: string; target: string; before: string; after: string; rationale: string
  addressed_cases: string[]; score_before: number; score_after: number | null; kept: boolean | null
}
export type Topic = { name: string; description: string; source_hint: string }
export type Requirements = {
  title: string; scope: string; audience: string; tone: string; must_answer: Topic[]; must_refuse: string[]
  clarifications: { question: string; answer: string; assumed: boolean }[]
  groundability: { topic: string; status: string; evidence: string[]; quote: string; note: string }[]
  flags: string[]
}
export type Trace = {
  question: string; retrieved: string[]; retrieved_docs: string[]
  tool_calls: { tool: string; args: Record<string, unknown>; result: string }[]
  reply: { answer: string; citations: string[]; refused: boolean; refusal_reason: string }
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init)
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`
    try { msg = (await r.json()).detail ?? msg } catch { /* not json */ }
    throw new Error(msg)
  }
  const ct = r.headers.get('content-type') ?? ''
  return (ct.includes('json') ? r.json() : r.text()) as Promise<T>
}

export const api = {
  health: () => req<{ ok: boolean; error?: string; missing?: Record<string, string>; provider?: string }>('/api/health'),
  inputs: () => req<InputSet[]>('/api/inputs'),
  runs: () => req<RunSummary[]>('/api/runs'),
  start: (body: object) => req<{ id: string }>('/api/runs', {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }),
  upload: (form: FormData) => req<{ id: string }>('/api/runs/upload', { method: 'POST', body: form }),
  artifact: <T,>(id: string, name: string) => req<T>(`/api/runs/${id}/artifacts/${name}`),
  pending: (id: string) => req<Requirements>(`/api/runs/${id}/checkpoint`),
  approve: (id: string, r: Requirements) => req(`/api/runs/${id}/checkpoint`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(r) }),
  startChat: (id: string, question: string, history: object[]) => req<{ job: string }>(`/api/chat/${id}/jobs`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ question, history }) }),
  chatJob: (job: string) => req<{ status: 'running' | 'done' | 'error'; trace?: Trace; error?: string; started: number }>(`/api/chat/jobs/${job}`),
  archive: (id: string, archived: boolean) => req(`/api/runs/${id}/archive`, {
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ archived }) }),
  remove: (id: string) => req(`/api/runs/${id}`, { method: 'DELETE' }),
  stop: (id: string) => req(`/api/runs/${id}/stop`, { method: 'POST' }),
  chat: (id: string, question: string, history: object[], signal?: AbortSignal) => req<Trace>(`/api/chat/${id}`, { signal,
    method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ question, history }) }),
}

/** Streams events.jsonl over SSE; for finished runs the stream replays everything and ends. */
export function useRunEvents(id: string) {
  const [events, setEvents] = useState<ForgeEvent[]>([])
  const [live, setLive] = useState(true)
  useEffect(() => {
    setEvents([]); setLive(true)
    const es = new EventSource(`/api/runs/${id}/events`)
    const buf: ForgeEvent[] = []
    let raf = 0
    es.onmessage = (m) => {
      buf.push(JSON.parse(m.data))
      if (!raf) raf = requestAnimationFrame(() => { raf = 0; setEvents([...buf]) })
    }
    es.addEventListener('end', () => { setLive(false); es.close() })
    es.onerror = () => { setLive(false); es.close() }
    return () => { es.close(); cancelAnimationFrame(raf) }
  }, [id])
  return { events, live }
}

export type StageState = 'pending' | 'active' | 'done' | 'reverted' | 'failed' | 'skipped'
export type Stage = { key: string; label: string; state: StageState; detail?: string }

const pct = (x: unknown) => (typeof x === 'number' ? `${Math.round(x * 100)}%` : '')

/** Folds the event stream into the factory's stages, in order. */
export function stagesFrom(events: ForgeEvent[]): Stage[] {
  const s: Stage[] = [
    { key: 'ingest', label: 'Read documents', state: 'pending' },
    { key: 'intake', label: 'Requirements', state: 'pending' },
    { key: 'generate', label: 'Draft agent', state: 'pending' },
    { key: 'evalgen', label: 'Write tests', state: 'pending' },
    { key: 'tournament', label: 'Prompt tournament', state: 'pending' },
    { key: 'iter0', label: 'First score', state: 'pending' },
    { key: 'iter1', label: 'Fix 1', state: 'pending' },
    { key: 'iter2', label: 'Fix 2', state: 'pending' },
    { key: 'iter3', label: 'Fix 3', state: 'pending' },
    { key: 'report', label: 'Report', state: 'pending' },
  ]
  const byKey = (k: string) => s.find((x) => x.key === k)
  for (const e of events) {
    if (e.stage === 'error') {
      const a = s.find((x) => x.state === 'active')
      if (a) { a.state = 'failed'; a.detail = String(e.error) }
      continue
    }
    if (e.stage === 'evaluate' && String(e.label ?? '').startsWith('candidate')) {
      const t = byKey('tournament')!
      t.state = 'active'
      t.detail = `${e.label}: ${e.done}/${e.total}`
      continue
    }
    const key = ['iteration', 'evaluate', 'fix', 'diagnose'].includes(e.stage) ? `iter${e.iteration ?? 0}`
      : e.stage === 'checkpoint' ? 'intake' : e.stage
    const st = byKey(key)
    if (!st) continue
    if (['start', 'progress', 'waiting'].includes(e.status)) st.state = 'active'
    if (e.status === 'waiting') st.detail = 'Waiting for your approval'
    if (e.stage === 'evaluate') st.detail = `Testing ${e.done}/${e.total}`
    if (e.stage === 'fix') st.detail = `${e.category} → ${e.target}`
    if (e.status === 'done' && e.stage !== 'fix' && e.stage !== 'diagnose') {
      st.state = e.kept === false ? 'reverted' : 'done'
      if (e.stage === 'iteration') st.detail = `dev ${pct(e.dev)}, holdout ${pct(e.holdout)}${e.kept === false ? ', reverted' : ''}`
      if (e.stage === 'ingest') st.detail = `${e.documents} files, ${e.chunks} chunks, ${e.mode}`
      if (e.stage === 'intake') {
        const n = (e.unsupported as string[] | undefined)?.length ?? 0
        st.detail = `${e.topics} topics${n ? `, ${n} not covered by documents` : ''}`
      }
      if (e.stage === 'generate') st.detail = `tools: ${(e.tools as string[]).join(', ') || 'none'}`
      if (e.stage === 'evalgen') st.detail = `${e.cases} test cases`
      if (e.stage === 'tournament') st.detail = `candidate ${e.winner} won, dev ${pct(e.dev)}`
    }
  }
  if (events.some((e) => e.stage === 'report' && e.status === 'done')) {
    for (const x of s) if (x.state === 'pending') x.state = 'skipped'
  }
  return s
}

export const percent = (x: number | null | undefined) => (x == null ? '–' : `${Math.round(x * 100)}%`)

export type Mark = { caseId: string; passed: boolean; failure?: string | null; kind?: string }
export type Live = {
  marks: Map<number, Map<string, Mark>>    // attempt -> case -> result, from the event stream (not candidates)
  kept: Record<number, boolean>            // attempt -> kept? (attempt 0 is always the baseline)
  current: { iteration: number; label: string; caseId: string; question: string; done: number; total: number } | null
  waiting: { model: string; stage: string; since: number } | null
  startedAt: number | null
  lastAt: number | null
  etaS: number | null                      // rough: mean seconds per case in this attempt x cases left
  milestone: number                        // bumps when a stage finishes: the signal to refetch artifacts
  finished: boolean
}

/** Folds the event stream into what the chart and the "now" line need. */
export function liveFrom(events: ForgeEvent[]): Live {
  const marks = new Map<number, Map<string, Mark>>()
  const kept: Record<number, boolean> = { 0: true }
  let current: Live['current'] = null
  let waiting: Live['waiting'] = null
  let milestone = 0
  let lastQuestion = ''
  const caseTimes: number[] = []
  for (const e of events) {
    if (e.stage === 'llm') {
      waiting = e.status === 'start' ? { model: String(e.model), stage: String(e.llm_stage), since: e.ts } : null
      continue
    }
    if (e.status === 'done') milestone++
    if (e.stage === 'evaluate') {
      const it = Number(e.iteration ?? 0)
      const label = String(e.label ?? '')
      if (e.question) lastQuestion = String(e.question)
      current = { iteration: it, label, caseId: String(e.case), question: lastQuestion,
                  done: Number(e.done), total: Number(e.total) }
      if (e.status === 'progress') {
        caseTimes.push(e.ts)
        if (!label) {
          if (!marks.has(it)) marks.set(it, new Map())
          marks.get(it)!.set(String(e.case), { caseId: String(e.case), passed: Boolean(e.passed),
                                              failure: e.failure as string | null, kind: e.kind as string })
        }
      }
    }
    if (e.stage === 'iteration' && e.status === 'done' && typeof e.kept === 'boolean') kept[Number(e.iteration)] = e.kept
  }
  const finished = events.some((e) => e.stage === 'report' && e.status === 'done') || events.some((e) => e.stage === 'error')
  let etaS: number | null = null
  if (current && !finished && caseTimes.length > 3) {
    const recent = caseTimes.slice(-8)
    const per = (recent[recent.length - 1] - recent[0]) / (recent.length - 1)
    etaS = Math.max(0, Math.round(per * (current.total - current.done)))
  }
  return { marks, kept, current: finished ? null : current, waiting: finished ? null : waiting,
           startedAt: events[0]?.ts ?? null, lastAt: events[events.length - 1]?.ts ?? null, etaS, milestone, finished }
}

export const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`

/** Lazy chunks vanish when the app is rebuilt while a tab is open: reload once to fetch the new ones. */
export function importOrReload<T>(load: () => Promise<T>): Promise<T> {
  return load().then((m) => { sessionStorage.removeItem('forgeai.reloaded'); return m }).catch((e) => {
    if (!sessionStorage.getItem('forgeai.reloaded')) { sessionStorage.setItem('forgeai.reloaded', '1'); location.reload() }
    throw e
  })
}
