import { Suspense, lazy, useEffect, useMemo, useState } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { Check, Flag, Minus, X } from 'lucide-react'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import type { Attempt, Selection } from './ChartPassage'
import { ChatPanel } from './ChatPanel'
import {
  api, clock, importOrReload, liveFrom, percent, stagesFrom, useRunEvents,
  type CaseResult, type ChangeLog, type EvalCase, type Requirements, type RunSummary, type Scorecard,
} from '@/lib/api'

const ChartPassage = lazy(() => importOrReload(() => import('./ChartPassage')).then((m) => ({ default: m.ChartPassage })))  // three.js ~1 MB

const FAILURE_TEXT: Record<string, string> = {
  retrieval_miss: 'retrieval miss', hallucination: 'hallucination', wrong_refusal: 'wrong refusal', prompt_defect: 'prompt defect',
}
const failureText = (f?: string | null) => (f ? FAILURE_TEXT[f] ?? f.replace('_', ' ') : '')

function useArtifact<T>(id: string, name: string, version: unknown) {
  const [data, setData] = useState<T | null>(null)
  useEffect(() => {
    let live = true
    api.artifact<T>(id, name).then((d) => live && setData(d)).catch(() => {})
    return () => { live = false }
  }, [id, name, version])
  return data
}

/** 95% Wilson interval, the same formula the report uses. */
function wilson(k: number, n: number): [number, number] {
  if (!n) return [0, 0]
  const z = 1.96, p = k / n, d = 1 + (z * z) / n
  const c = (p + (z * z) / (2 * n)) / d
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d
  return [Math.max(0, c - h), Math.min(1, c + h)]
}

type RunMeta = { model?: string; judge_model?: string; stop_reason?: string; duration_s?: number; retrieval_mode?: string }

export function RunView({ run, section }: { run: RunSummary; section: string }) {
  const { events } = useRunEvents(run.id)
  const stages = useMemo(() => stagesFrom(events), [events])
  const live = useMemo(() => liveFrom(events), [events])
  const v = live.milestone  // artifacts are refetched each time a stage finishes: never stale at the end of a run

  const scorecards = useArtifact<Scorecard[]>(run.id, 'scorecards.json', v)
  const evalset = useArtifact<EvalCase[]>(run.id, 'evalset.json', v)
  const log = useArtifact<ChangeLog[]>(run.id, 'iteration_log.json', v)
  const req = useArtifact<Requirements>(run.id, 'requirements.json', v)
  const meta = useArtifact<RunMeta>(run.id, 'run.json', v)
  const genlog = useArtifact<Record<string, string>[]>(run.id, 'evalgen_log.json', v)

  const [selected, setSelected] = useState<Selection>(null)
  const waiting = events.some((e) => e.stage === 'checkpoint' && e.status === 'waiting') &&
    !events.some((e) => e.stage === 'checkpoint' && e.status === 'approved')
  useEffect(() => { if (waiting && section !== 'requirements') location.hash = `run/${run.id}/requirements` }, [waiting, section, run.id])

  const caseOrder = useMemo(() => evalset?.map((c) => c.id) ?? [], [evalset])
  const caseById = useMemo(() => new Map(evalset?.map((c) => [c.id, c]) ?? []), [evalset])

  // attempts = saved scorecards, overlaid with results streaming in for the attempt still running
  const attempts: Attempt[] = useMemo(() => {
    const its = new Set<number>([...(scorecards ?? []).map((s) => s.iteration), ...live.marks.keys()])
    return [...its].sort((a, b) => a - b).map((it) => {
      const sc = scorecards?.find((s) => s.iteration === it)
      const results = new Map<string, { passed: boolean }>(sc?.results.map((r) => [r.case_id, { passed: r.passed }]) ?? [])
      for (const [id, m] of live.marks.get(it) ?? []) results.set(id, { passed: m.passed })
      const fix = log?.find((c) => c.iteration === it)
      const kept = it === 0 ? true : fix?.kept ?? live.kept[it] ?? null
      return { iteration: it, kept, score: sc?.dev_pass_rate,
               label: it === 0 ? 'First score' : `Fix ${it}: ${failureText(fix?.category) || 'running'}`, results }
    })
  }, [scorecards, live, log])

  const bestIt = Math.max(0, ...(log ?? []).filter((c) => c.kept).map((c) => c.iteration))
  const final = scorecards?.find((s) => s.iteration === bestIt) ?? null
  const sel = selected ? {
    case: caseById.get(selected.caseId),
    result: scorecards?.find((s) => s.iteration === selected.iteration)?.results.find((r) => r.case_id === selected.caseId),
    attempt: attempts.find((a) => a.iteration === selected.iteration),
  } : null

  const sections: [string, string][] = [
    ['overview', 'Overview'], ['tests', `Tests${evalset ? ` ${evalset.length}` : ''}`], ['fixes', `Fixes${log?.length ? ` ${log.length}` : ''}`],
    ['requirements', waiting ? 'Requirements (needs approval)' : 'Requirements'], ['report', 'Report'], ['chat', 'Ask the agent'],
  ]
  const trace = <CaseTrace sel={sel} selected={selected} onClose={() => setSelected(null)} />
  return (
    <div className="mx-auto flex max-w-[1400px] flex-col gap-5 px-6 py-6">
      <TitleBlock run={run} final={final} meta={meta} req={req} />
      <nav aria-label="Run sections" className="sticky top-14 z-20 -mx-6 overflow-x-auto border-b border-white/10 bg-black/85 px-6 backdrop-blur md:top-0">
        <ul className="flex gap-1">{sections.map(([k, label]) => (
          <li key={k}>
            <a href={`#run/${run.id}/${k}`} aria-current={section === k ? 'page' : undefined}
              className={`block whitespace-nowrap border-b-2 px-3 py-3 text-[15px] font-medium ${section === k ? 'border-magenta text-ink' : 'border-transparent text-sounding hover:text-ink'}`}>
              {label}
            </a>
          </li>))}
        </ul>
      </nav>

      {section === 'overview' && <>
        <section aria-label="Run chart">
          <Suspense fallback={<div className="chart-frame h-[min(52vh,520px)] min-h-[300px]" />}>
            <ChartPassage stages={stages} attempts={attempts} caseOrder={caseOrder} selected={selected} onSelect={setSelected}
              live={live.current && !live.current.label ? { iteration: live.current.iteration, caseId: live.current.caseId } : null} />
          </Suspense>
          <NowLine live={live} run={run} meta={meta} stages={stages} />
        </section>
        {live.finished && final && <Verdict name={run.name} final={final} req={req} log={log} />}
        <div className="grid gap-6 lg:grid-cols-[minmax(0,6fr)_minmax(0,7fr)]">
          <Legend final={final} req={req} genlog={genlog} evalTotal={evalset?.length ?? 0}
            onPick={(id) => setSelected({ iteration: bestIt, caseId: id })} />
          {trace}
        </div>
      </>}
      {section === 'tests' && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
          <TestsTab cases={evalset} final={final} onPick={(id) => setSelected({ iteration: bestIt, caseId: id })} />
          <div className="xl:sticky xl:top-16 xl:self-start">{trace}</div>
        </div>
      )}
      {section === 'fixes' && <FixesTab log={log} />}
      {section === 'requirements' && <RequirementsTab id={run.id} saved={req} waiting={waiting} />}
      {section === 'report' && <ReportTab id={run.id} version={v} />}
      {section === 'chat' && <ChatPanel id={run.id} name={run.name} model={meta?.model} cases={evalset} ready={live.finished && !!final} />}
    </div>
  )
}

/* ------------------------------------------------------------------ verdict: one honest sentence, revealed word by word once */

function Verdict({ name, final, req, log }: { name: string; final: Scorecard; req: Requirements | null; log: ChangeLog[] | null }) {
  const reduce = useReducedMotion()
  const n = final.results.length
  const k = final.results.filter((r) => r.passed).length
  const [lo, hi] = wilson(k, n)
  const gaps = req?.groundability.filter((g) => g.status === 'unsupported').map((g) => g.topic.replace(/_/g, ' ')) ?? []
  const kept = log?.filter((c) => c.kept).length ?? 0
  const sentence = [
    `the ${name.toLowerCase()} passes ${k} of ${n} tests,`,
    `so its true score is probably between ${percent(lo)} and ${percent(hi)}.`,
    gaps.length ? `it refuses ${gaps.join(' and ')} because the documents never cover it.` : '',
    log?.length ? `${log.length} fix${log.length > 1 ? 'es were' : ' was'} tried and ${kept || 'none'} kept.` : '',
  ].filter(Boolean).join(' ')
  const words = sentence.split(' ')
  return (
    <motion.p className="display max-w-[min(100%,46rem)] py-6 text-[clamp(1.7rem,2.6vw,2.5rem)] leading-[1.12]"
      initial="dim" whileInView="lit" viewport={{ once: true, amount: 0.6 }}
      variants={{ lit: { transition: { staggerChildren: reduce ? 0 : 0.045 } } }}>
      <span className="sr-only">{sentence}</span>
      {words.map((w, i) => (
        <motion.span key={i} aria-hidden className="inline-block whitespace-pre"
          variants={{ dim: { opacity: reduce ? 1 : 0.5 }, lit: { opacity: 1, transition: { duration: 0.35, ease: [0.16, 1, 0.3, 1] } } }}>
          {w}{i < words.length - 1 ? ' ' : ''}
        </motion.span>
      ))}
    </motion.p>
  )
}

/* ------------------------------------------------------------------ title block: the chart's cartouche */

function TitleBlock({ run, final, meta, req }: { run: RunSummary; final: Scorecard | null; meta: RunMeta | null; req: Requirements | null }) {
  const all = final?.results ?? []
  const passed = all.filter((r) => r.passed).length
  const [lo, hi] = wilson(passed, all.length)
  const gaps = req?.groundability.filter((g) => g.status === 'unsupported').length ?? 0
  const cells: [string, string, string][] = final ? [
    ['Score', percent(final.overall_pass_rate), `likely ${percent(lo)} to ${percent(hi)}`],
    ['Dev', percent(final.dev_pass_rate), 'cases used to tune'],
    ['Holdout', percent(final.holdout_pass_rate), 'never used to tune'],
    ['Judge split', percent(final.judge_disagreement_rate), 'passes disagreed'],
  ] : []
  return (
    <header className="cartouche grid gap-x-8 gap-y-3 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
      <div className="min-w-0">
        <h1 className="display pb-1 text-[clamp(2.1rem,3.2vw,3.2rem)] leading-[1.05]">{run.name}</h1>
        <p className="mt-1 text-[15px] text-sounding">
          {meta?.model ? <>Agent <b className="font-medium text-ink">{meta.model}</b>, judge <b className="font-medium text-ink">{meta.judge_model}</b></> : 'Waiting for the first results'}
          {gaps > 0 && <span className="ml-3 inline-flex items-center gap-1 text-port"><Flag className="size-3.5" aria-hidden />{gaps} topic{gaps > 1 ? 's' : ''} not covered by the documents</span>}
        </p>
      </div>
      {cells.length > 0 && (
        <dl className="grid grid-cols-2 border-t border-l border-ink/20 sm:grid-cols-4">
          {cells.map(([k, val, sub], i) => (
            <div key={k} className={`border-r border-b border-ink/20 px-4 py-2 ${i === 0 ? 'bg-panel' : ''}`}>
              <dt className="text-[13px] text-sounding">{k}</dt>
              <dd className={`display tabular-nums leading-none ${i === 0 ? 'text-[2.4rem]' : 'text-[1.9rem]'}`}>{val}</dd>
              <dd className="mt-1 text-[12.5px] text-sounding">{sub}</dd>
            </div>
          ))}
        </dl>
      )}
    </header>
  )
}

/* ------------------------------------------------------------------ the "now" line under the chart */

function NowLine({ live, run, meta, stages }: { live: ReturnType<typeof liveFrom>; run: RunSummary; meta: RunMeta | null; stages: ReturnType<typeof stagesFrom> }) {
  const [now, setNow] = useState(() => Date.now() / 1000)
  const running = !live.finished && run.status !== 'done' && run.status !== 'failed' &&
    (run.status === 'running' || run.status === 'awaiting_approval' || (live.lastAt != null && now - live.lastAt < 300))
  useEffect(() => {
    if (!running) return
    const t = setInterval(() => setNow(Date.now() / 1000), 1000)
    return () => clearInterval(t)
  }, [running])
  const failed = stages.find((s) => s.state === 'failed')
  if (failed) return <p className="now-line text-port" role="status">Stopped with an error: {failed.detail}</p>
  if (!running) {
    const dur = meta?.duration_s ?? (live.lastAt && live.startedAt ? live.lastAt - live.startedAt : null)
    return (
      <p className="now-line" role="status">
        <span className="font-semibold">Finished{dur ? ` in ${clock(dur)}` : ''}.</span>{' '}
        {meta?.stop_reason ? <span className="text-sounding">Stopped because: {meta.stop_reason.replace(/^early stop - /, '')}.</span> : null}
      </p>
    )
  }
  const active = stages.find((s) => s.state === 'active')
  const c = live.current
  const elapsed = live.startedAt ? now - live.startedAt : 0
  return (
    <div className="now-line grid gap-1 md:grid-cols-[auto_minmax(0,1fr)_auto] md:items-baseline md:gap-6" role="status" aria-live="polite">
      <span className="font-semibold text-magenta">{active?.label ?? 'Working'}</span>
      <span className="min-w-0 truncate">
        {c ? <>Case <b className="tabular-nums">{c.done + 1}</b> of {c.total}{c.label ? ` (${c.label})` : ''}: <q>{c.question}</q></> : active?.detail}
      </span>
      <span className="tabular-nums text-sounding">
        {live.waiting && <>waiting on {live.waiting.model} for {Math.max(0, Math.round(now - live.waiting.since))} s, </>}
        {clock(elapsed)} elapsed{live.etaS != null ? `, about ${Math.max(1, Math.round(live.etaS / 60))} min left in this step` : ''}
      </span>
    </div>
  )
}

/* ------------------------------------------------------------------ legend = trust panel */

function Legend({ final, req, genlog, evalTotal, onPick }: {
  final: Scorecard | null; req: Requirements | null; genlog: Record<string, string>[] | null; evalTotal: number; onPick: (id: string) => void
}) {
  const graded = final?.results.filter((r) => r.retrieval_hit != null) ?? []
  const hits = graded.filter((r) => r.retrieval_hit).length
  const rejected = genlog?.filter((g) => g.rejected).length ?? 0
  const assumed = req?.clarifications.filter((c) => c.assumed).length ?? 0
  const failing = final?.results.filter((r) => !r.passed) ?? []
  return (
    <aside className="legend" aria-label="Legend and trust">
      <h2 className="display text-[1.45rem] leading-tight">Legend</h2>
      <ul className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-[15px]">
        <li className="flex items-center gap-2"><span className="sym-pass" aria-hidden />Passed test</li>
        <li className="flex items-center gap-2"><X className="size-4 text-port" strokeWidth={3} aria-hidden />Failed test</li>
        <li className="flex items-center gap-2"><span className="sym-pending" aria-hidden />Not graded yet</li>
        <li className="flex items-center gap-2"><span className="sym-dashed" aria-hidden />Fix that was reverted</li>
      </ul>
      <h2 className="display mt-6 text-[1.45rem] leading-tight">How far to trust the score</h2>
      <dl className="trust mt-2">
        <div><dt>Retrieval found the right document</dt><dd>{graded.length ? `${hits} of ${graded.length}` : '–'}</dd></div>
        <div><dt>Generated tests thrown out by checks</dt><dd>{evalTotal ? `${rejected}, kept ${evalTotal}` : '–'}</dd></div>
        <div><dt>Questions nobody answered, defaults assumed</dt><dd>{req ? assumed : '–'}</dd></div>
        <div><dt>Topics the documents cannot support</dt><dd>{req ? req.groundability.filter((g) => g.status === 'unsupported').map((g) => g.topic.replace(/_/g, ' ')).join(', ') || 'none' : '–'}</dd></div>
      </dl>
      <h2 className="display mt-6 text-[1.45rem] leading-tight">What still fails {final ? `(${failing.length})` : ''}</h2>
      {!final && <p className="mt-1 text-sounding">Appears after the first full test pass.</p>}
      <ul className="mt-1 divide-y divide-ink/10">
        {failing.map((r) => (
          <li key={r.case_id}>
            <button className="flex w-full items-baseline gap-3 py-1.5 text-left hover:bg-shallows/40" onClick={() => onPick(r.case_id)}>
              <span className="shrink-0 whitespace-nowrap tabular-nums font-semibold">{r.case_id}</span>
              <span className="shrink-0 whitespace-nowrap text-port">{failureText(r.failure)}</span>
              <span className="min-w-0 text-sounding">{r.notes[0]}</span>
            </button>
          </li>
        ))}
      </ul>
    </aside>
  )
}

/* ------------------------------------------------------------------ case trace */

function CaseTrace({ sel, selected, onClose }: {
  sel: { case?: EvalCase; result?: CaseResult; attempt?: Attempt } | null; selected: Selection; onClose: () => void
}) {
  const reduce = useReducedMotion()
  return (
    <section className="trace" aria-label="Case trace" aria-live="polite">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.div key={selected ? `${selected.iteration}:${selected.caseId}` : 'none'}
          initial={reduce ? false : { opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}>
          {!sel?.case || !sel.result ? (
            <div className="py-6">
              <h2 className="display text-[1.45rem] leading-tight">Case trace</h2>
              <p className="mt-1 max-w-[60ch] text-sounding">Click any mark on the chart, a failing case in the list, or a row under Tests to see what the agent retrieved, what it answered, and how each judge pass graded it.</p>
            </div>
          ) : <TraceBody c={sel.case} r={sel.result} attempt={sel.attempt} onClose={onClose} />}
        </motion.div>
      </AnimatePresence>
    </section>
  )
}

function TraceBody({ c, r, attempt, onClose }: { c: EvalCase; r: CaseResult; attempt?: Attempt; onClose: () => void }) {
  const passes = r.judge_passes ?? []
  return (
    <div>
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <h2 className="display text-[1.45rem] leading-tight tabular-nums">{c.id}</h2>
        <Badge variant="outline">{c.kind.replace('_', ' ')}</Badge>
        <Badge variant="outline">{c.split}</Badge>
        <span className="text-sounding">{attempt?.label}</span>
        <span className={`ml-auto inline-flex items-center gap-1 font-semibold ${r.passed ? 'text-starboard' : 'text-port'}`}>
          {r.passed ? <Check className="size-4" strokeWidth={3} /> : <X className="size-4" strokeWidth={3} />}
          {r.passed ? 'Passed' : `Failed: ${failureText(r.failure)}`}
        </span>
        <Button size="sm" variant="ghost" onClick={onClose} aria-label="Close case trace"><X /></Button>
      </div>
      <p className="mt-2 text-[17px] font-medium leading-7">{c.question}</p>

      <ol className="trace-steps mt-3">
        <li><h3>Expected</h3>
          {c.should_refuse ? <p>Must refuse.</p> : c.expected_tool ? <p>Must use the <b>{c.expected_tool}</b> tool.</p> : (
            <ul>{c.key_facts.map((f, i) => (
              <li key={f} className="flex items-baseline gap-2">
                <JudgeMarks marks={passes.map((p) => p.facts_present[i])} />
                <q>{f}</q>
              </li>))}
            </ul>)}
          {c.expected_sources.length > 0 && <p className="text-sounding">from {c.expected_sources.join(' and ')}</p>}
        </li>
        <li><h3>Retrieved</h3>
          {!r.trace ? <p className="text-sounding">Not recorded for this run (made before traces were stored).</p> : (
            <ul className="space-y-1">{r.trace.retrieved.map((ch) => (
              <li key={ch.id}>
                <details><summary><span className="tabular-nums">{ch.id}</span>{r.trace!.citations.includes(ch.id) && <span className="ml-2 text-starboard">cited</span>}</summary>
                  <p className="mt-1 whitespace-pre-wrap text-[14px] text-sounding">{ch.text}</p></details>
              </li>))}
            </ul>)}
          {r.trace?.tool_calls.map((t, i) => (
            <p key={i} className="mt-1 text-[14px]">Tool <b>{t.tool}</b>({JSON.stringify(t.args)}) returned <span className="text-sounding">{t.result.slice(0, 160)}</span></p>))}
        </li>
        <li><h3>Answer</h3>
          <p className="whitespace-pre-wrap">{r.answer || <span className="text-sounding">(empty)</span>}</p>
          {r.refused && <p className="text-sounding">Declined{r.trace?.refusal_reason ? `: ${r.trace.refusal_reason}` : ''}.</p>}
        </li>
        <li><h3>Judged</h3>
          {passes.length === 0 ? (
            <p>{r.notes.includes('passed on deterministic checks') ? 'Every expected fact appears verbatim and the right source is cited, so the LLM judge was not needed.'
              : r.trace ? 'Decided by deterministic checks (refusal, tool or numbers).' : 'Judge passes not recorded for this run.'}</p>
          ) : (
            <p>Two passes, the second with facts and context in reversed order.
              {r.judge_agreement === false ? <span className="text-port"> They disagreed, so only facts both credited count.</span> : ' They agreed.'}</p>
          )}
          {passes.flatMap((p) => p.unsupported_claims).length > 0 && (
            <p className="mt-1">Claims not found in the context: {[...new Set(passes.flatMap((p) => p.unsupported_claims))].map((x) => <q key={x} className="mr-2">{x}</q>)}</p>)}
          {r.notes.filter((n) => n !== 'passed on deterministic checks').map((n) => <p key={n} className="text-sounding">{n}</p>)}
        </li>
      </ol>
    </div>
  )
}

function JudgeMarks({ marks }: { marks: (boolean | undefined)[] }) {
  if (!marks.length) return null
  return (
    <span className="inline-flex shrink-0 gap-0.5" aria-label={`judge passes: ${marks.map((m) => (m ? 'found' : 'not found')).join(', ')}`}>
      {marks.map((m, i) => m ? <Check key={i} className="size-3.5 text-starboard" strokeWidth={3} /> : m === false
        ? <X key={i} className="size-3.5 text-port" strokeWidth={3} /> : <Minus key={i} className="size-3.5 text-sounding" />)}
    </span>
  )
}

/* ------------------------------------------------------------------ tabs */

function TestsTab({ cases, final, onPick }: { cases: EvalCase[] | null; final: Scorecard | null; onPick: (id: string) => void }) {
  const [kind, setKind] = useState('all')
  const [onlyFailing, setOnlyFailing] = useState(false)
  if (!cases) return <p className="py-8 text-sounding">Tests appear once they are generated from the documents.</p>
  const res = new Map(final?.results.map((r) => [r.case_id, r]))
  const kinds = ['all', ...new Set(cases.map((c) => c.kind))]
  const rows = cases.filter((c) => (kind === 'all' || c.kind === kind) && (!onlyFailing || res.get(c.id)?.passed === false))
  return (
    <div className="py-3">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {kinds.map((k) => <Button key={k} size="sm" variant={k === kind ? 'default' : 'outline'} onClick={() => setKind(k)}>{k.replace('_', ' ')}</Button>)}
        <label className="ml-auto flex items-center gap-2 text-sm">
          <input type="checkbox" checked={onlyFailing} onChange={(e) => setOnlyFailing(e.target.checked)} className="accent-magenta" /> Failing only
        </label>
      </div>
      <Table>
        <TableHeader><TableRow>
          <TableHead className="w-20">Case</TableHead><TableHead>Question and what a correct answer needs</TableHead>
          <TableHead className="w-20">Split</TableHead><TableHead className="w-44">Final result</TableHead>
        </TableRow></TableHeader>
        <TableBody>{rows.map((c) => {
          const r = res.get(c.id)
          return (
            <TableRow key={c.id} className="cursor-pointer align-top" onClick={() => onPick(c.id)}>
              <TableCell className="tabular-nums text-sounding">{c.id}</TableCell>
              <TableCell className="whitespace-normal">
                <div className="font-medium">{c.question}</div>
                <div className="text-sm text-sounding">{c.should_refuse ? 'Must refuse' : c.expected_tool ? `Must use ${c.expected_tool}` : c.key_facts.map((f) => `“${f}”`).join(', ')}</div>
              </TableCell>
              <TableCell>{c.split}</TableCell>
              <TableCell>{!r ? '–' : r.passed
                ? <span className="inline-flex items-center gap-1 text-starboard"><Check className="size-4" strokeWidth={3} />passed</span>
                : <span className="inline-flex items-center gap-1 text-port"><X className="size-4" strokeWidth={3} />{failureText(r.failure)}</span>}</TableCell>
            </TableRow>)
        })}</TableBody>
      </Table>
    </div>
  )
}

function FixesTab({ log }: { log: ChangeLog[] | null }) {
  if (!log?.length) return <p className="py-8 text-sounding">No fixes yet. After the first full test pass, each failure category gets one targeted fix, kept only if the dev score rises.</p>
  return (
    <ol className="divide-y divide-white/10 py-2">{log.map((c) => {
      const [why, ...rest] = c.rationale.split(' | ')
      const ids = (label: string) => (rest.find((r) => r.startsWith(label))?.match(/[a-z]{3}-\d{2}/g) ?? [])
      const fixed = ids('fixed'), broke = ids('newly failing')
      return (
        <li key={c.iteration} className="py-10 first:pt-4">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <h3 className="display text-[1.7rem] leading-tight">fix {c.iteration}: {failureText(c.category)}</h3>
            <span className={`font-semibold ${c.kept ? 'text-starboard' : 'text-port'}`}>{c.kept ? 'kept' : 'reverted'}</span>
            <span className="tabular-nums text-sounding">dev score {percent(c.score_before)} to {percent(c.score_after)}</span>
          </div>
          <p className="mt-1 text-[15px] text-sounding">Changed <code className="text-ink">{c.target}</code></p>
          <p className="mt-4 max-w-[68ch] text-[17px] leading-relaxed">{why}</p>
          {(fixed.length > 0 || broke.length > 0) && (
            <dl className="mt-4 grid gap-x-6 gap-y-2 text-[15px] sm:grid-cols-[auto_1fr]">
              <dt className="text-sounding">Fixed</dt>
              <dd className="flex flex-wrap gap-1.5">{fixed.length ? fixed.map((x) => <span key={x} className="rounded-full bg-starboard/12 px-2.5 py-0.5 tabular-nums text-starboard">{x}</span>) : 'none'}</dd>
              <dt className="text-sounding">Newly failing</dt>
              <dd className="flex flex-wrap gap-1.5">{broke.length ? broke.map((x) => <span key={x} className="rounded-full bg-port/12 px-2.5 py-0.5 tabular-nums text-port">{x}</span>) : 'none'}</dd>
            </dl>
          )}
          <div className="mt-6 grid gap-8 md:grid-cols-2 md:gap-12">
            <section aria-label="Before"><h4 className="text-[15px] font-semibold text-sounding">Before</h4>
              <p className="diff-text mt-2">{c.before}</p></section>
            <section aria-label="After" className="md:border-l md:border-white/10 md:pl-12"><h4 className="text-[15px] font-semibold text-magenta">After</h4>
              <p className="diff-text mt-2">{c.after}</p></section>
          </div>
        </li>
      )
    })}
    </ol>
  )
}

function ReportTab({ id, version }: { id: string; version: unknown }) {
  const md = useArtifact<string>(id, 'report.md', version)
  const baseline = useArtifact<string>(id, 'baseline_comparison.md', version)
  const regression = useArtifact<string>(id, 'regression.md', version)
  if (!md) return <p className="py-8 text-sounding">The written report appears when the run finishes.</p>
  const parts: [string, string, string | null][] = [
    ['report', 'Run report', md],
    ['baseline', 'Factory vs a hand-written agent', baseline],
    ['regression', 'After the documents changed', regression],
  ]
  const present = parts.filter(([, , text]) => text)
  return (
    <div className={`grid gap-10 py-4 ${present.length > 1 ? 'lg:grid-cols-[13rem_minmax(0,1fr)]' : ''}`}>
      {present.length > 1 && (
        <nav aria-label="Report parts" className="lg:sticky lg:top-20 lg:self-start">
          <ul className="space-y-1 border-l border-white/15">{present.map(([k, label]) => (
            <li key={k}><button onClick={() => document.getElementById(`part-${k}`)?.scrollIntoView({ behavior: 'smooth' })}
              className="block py-1 pl-4 text-left text-[15px] text-sounding hover:text-ink">{label}</button></li>))}
          </ul>
        </nav>
      )}
      <div className="min-w-0 space-y-14">
        {present.map(([k, , text]) => (
          <article key={k} id={`part-${k}`} className="prose-report scroll-mt-20"><Markdown remarkPlugins={[remarkGfm]}>{text!}</Markdown></article>))}
      </div>
    </div>
  )
}

function RequirementsTab({ id, saved, waiting }: { id: string; saved: Requirements | null; waiting: boolean }) {
  const [draft, setDraft] = useState<Requirements | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  useEffect(() => { if (waiting) api.pending(id).then(setDraft).catch((e) => setErr(e.message)) }, [id, waiting])
  const r = waiting ? draft : saved
  if (!r) return <p className="py-8 text-sounding">Requirements are written after the intake interview.</p>
  return (
    <div className="grid gap-8 py-4 lg:grid-cols-[1.3fr_1fr]">
      <section className="space-y-5">
        <div>
          <h2 className="display text-[1.7rem] leading-tight">{r.title}</h2>
          <p className="mt-1 max-w-[70ch]">{r.scope}</p>
          <p className="mt-1 text-sm text-sounding">For {r.audience}. Tone: {r.tone}.</p>
        </div>
        <div><h3 className="font-semibold">Must answer</h3>
          <ul className="mt-1 space-y-1">{r.must_answer.map((t) => <li key={t.name}><span className="font-medium">{t.name.replace(/_/g, ' ')}</span> <span className="text-sounding">{t.description}</span></li>)}</ul>
        </div>
        <div><h3 className="font-semibold">Must refuse</h3>
          {waiting ? (
            <>
              <Textarea className="mt-1 min-h-32" value={r.must_refuse.join('\n')} aria-label="Must refuse, one per line"
                onChange={(e) => setDraft({ ...r, must_refuse: e.target.value.split('\n').filter((x) => x.trim()) })} />
              <p className="mt-1 text-xs text-sounding">One per line. Your edits go into the agent's refusal policy.</p>
            </>
          ) : <ul className="mt-1 list-disc pl-5">{r.must_refuse.map((x) => <li key={x}>{x}</li>)}</ul>}
        </div>
        {waiting && (
          <div className="flex items-center gap-3">
            <Button disabled={busy} onClick={async () => {
              setBusy(true); setErr(null)
              try { await api.approve(id, r) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
            }}><Check /> Approve and build the agent</Button>
            {err && <span className="text-sm text-port">{err}</span>}
          </div>
        )}
      </section>
      <aside className="space-y-5">
        <div><h3 className="font-semibold">Can the documents support it?</h3>
          <ul className="mt-2 space-y-2">{r.groundability.map((g) => (
            <li key={g.topic} className="text-sm">
              <span className={g.status === 'supported' ? 'text-starboard' : g.status === 'partial' ? 'text-magenta' : 'text-port'}>
                {g.status === 'supported' ? 'Supported' : g.status === 'partial' ? 'Partly' : 'Not covered'}</span>{' '}
              <span className="font-medium">{g.topic.replace(/_/g, ' ')}</span>
              {g.quote ? <q className="mt-0.5 block text-sounding">{g.quote}</q> : g.note && <span className="block text-sounding">{g.note}</span>}
            </li>))}
          </ul>
        </div>
        <div><h3 className="font-semibold">Clarifying questions</h3>
          <dl className="mt-2 space-y-2 text-sm">{r.clarifications.map((c) => (
            <div key={c.question}><dt className="font-medium">{c.question}</dt><dd className="text-sounding">{c.answer}{c.assumed && ' (assumed, nobody answered)'}</dd></div>))}
          </dl>
        </div>
      </aside>
    </div>
  )
}
