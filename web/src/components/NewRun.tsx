import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'motion/react'
import { ArrowLeft, ArrowRight, Check, Play, Upload } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Switch } from '@/components/ui/switch'
import { api, type InputSet } from '@/lib/api'

const STEPS = [
  { title: 'Documents', body: 'A demo set, a held-out set, or your own files.' },
  { title: 'Brief', body: 'Who the assistant serves and what it must answer.' },
  { title: 'Options and start', body: 'Approval, prompt candidates, budget.' },
]
const UPLOAD = 'upload'

/** A choice row: a radio mark and text on the page itself, separated by hairlines, never a box in a box. */
function Choice({ on, onClick, title, detail, icon }: { on: boolean; onClick: () => void; title: string; detail?: string; icon?: React.ReactNode }) {
  return (
    <button role="radio" aria-checked={on} onClick={onClick}
      className="flex w-full items-start gap-4 border-b border-white/10 py-4 text-left last:border-b-0 hover:bg-white/[.03]">
      <span className={`mt-1 flex size-5 shrink-0 items-center justify-center rounded-full border ${on ? 'border-magenta' : 'border-white/35'}`}>
        {on && <span className="size-2.5 rounded-full bg-magenta" />}
      </span>
      <span className="min-w-0">
        <span className="flex items-center gap-2 font-medium">{icon}{title}</span>
        {detail && <span className="mt-0.5 block break-words text-[15px] text-sounding">{detail}</span>}
      </span>
    </button>
  )
}

export function NewRun({ onStarted, modelsOk, modelsError }: { onStarted: (id: string) => void; modelsOk: boolean; modelsError?: string }) {
  const reduce = useReducedMotion()
  const [step, setStep] = useState(0)
  const [inputs, setInputs] = useState<InputSet[]>([])
  const [pick, setPick] = useState<string | null>(null)
  const [brief, setBrief] = useState('')
  const [name, setName] = useState('')
  const [files, setFiles] = useState<FileList | null>(null)
  const [checkpoint, setCheckpoint] = useState(false)
  const [candidates, setCandidates] = useState(2)
  const [budget, setBudget] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  useEffect(() => { api.inputs().then(setInputs).catch((e) => setErr(e.message)) }, [])
  // clicking the chosen option again clears it, so nothing is ever locked in
  const choose = (s: InputSet | null) => {
    const id = s ? s.id : UPLOAD
    if (pick === id) { setPick(null); setBrief(''); setName(''); return }
    setPick(id)
    setBrief(s?.brief ?? '')
    setName(s ? s.id.split('/').pop()!.replace(/_/g, ' ') : '')
  }
  const done = [pick !== null && (pick !== UPLOAD || !!files?.length), brief.trim().length > 20, false]

  const start = async () => {
    setBusy(true); setErr(null)
    try {
      let id: string
      if (pick === UPLOAD) {
        if (!files?.length) throw new Error('Add at least one document (PDF, Markdown, text or CSV).')
        const f = new FormData()
        f.append('name', name || 'uploaded brief'); f.append('brief', brief)
        f.append('checkpoint', String(checkpoint)); f.append('candidates', String(candidates))
        for (const file of Array.from(files)) f.append('files', file)
        id = (await api.upload(f)).id
      } else {
        id = (await api.start({ name: name || pick, input_id: pick, brief, checkpoint, candidates,
          budget_tokens: budget ? Number(budget) : null })).id
      }
      onStarted(id)
    } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }

  const groups = [['demos', 'Demo sets'], ['holdout', 'Held-out sets, never used while building']] as const
  return (
    <div className="mx-auto max-w-[1040px] px-6 py-12">
      <h1 className="display text-[clamp(2.6rem,4.6vw,4.25rem)] leading-[1]">build an agent from a brief</h1>
      <p className="mt-4 max-w-[58ch] text-lg leading-relaxed text-sounding">
        Three steps. The run then goes unattended for about 15 to 25 minutes on this machine, with every step visible on its chart.
      </p>

      {/* stepper: titles on the page, a hairline that fills as each step is completed */}
      <ol role="tablist" aria-label="Steps" className="mt-12 grid gap-6 md:grid-cols-3">
        {STEPS.map((s, i) => (
          <li key={s.title}>
            <button role="tab" aria-selected={step === i} onClick={() => setStep(i)} className="group w-full text-left">
              <span className="block h-0.5 w-full bg-white/12">
                <motion.span className="block h-full bg-magenta" initial={false}
                  animate={{ width: done[i] ? '100%' : step === i ? '35%' : '0%' }} transition={{ duration: reduce ? 0 : 0.4, ease: [0.16, 1, 0.3, 1] }} />
              </span>
              <span className={`mt-3 flex items-center gap-2 font-semibold ${step === i ? 'text-ink' : 'text-sounding group-hover:text-ink'}`}>
                {done[i] ? <Check className="size-4 text-starboard" aria-label="done" /> : <span className="tabular-nums">{i + 1}</span>}{s.title}
              </span>
              <span className="mt-1 block text-[15px] text-sounding">{s.body}</span>
            </button>
          </li>
        ))}
      </ol>

      <motion.section key={step} role="tabpanel" aria-label={STEPS[step].title} className="mt-12 min-h-[340px]"
        initial={reduce ? false : { opacity: 0, x: 10 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}>
        {step === 0 && (
          <div role="radiogroup" aria-label="Documents" className="grid gap-x-14 gap-y-10 md:grid-cols-2">
            {groups.map(([g, label]) => (
              <div key={g}>
                <h2 className="text-[15px] font-semibold text-sounding">{label}</h2>
                <div className="mt-1">{inputs.filter((s) => s.group === g).map((s) => (
                  <Choice key={s.id} on={pick === s.id} onClick={() => choose(s)} title={s.id.split('/').pop()!.replace(/_/g, ' ')} detail={s.docs.join(', ')} />))}
                </div>
              </div>
            ))}
            <div className="md:col-span-2">
              <Choice on={pick === UPLOAD} onClick={() => choose(null)} icon={<Upload className="size-4" aria-hidden />}
                title="Your own brief and documents" detail="PDF, Markdown, text or CSV, up to 20 files of 20 MB each." />
              {pick === UPLOAD && <Input className="mt-3" type="file" multiple accept=".pdf,.md,.txt,.csv" aria-label="Documents to upload" onChange={(e) => setFiles(e.target.files)} />}
            </div>
            <p className="text-[15px] text-sounding md:col-span-2">Click a selected set again to clear it.</p>
          </div>
        )}
        {step === 1 && (
          <div className="max-w-[68ch] space-y-7">
            <label className="block">
              <span className="font-semibold">Run name</span>
              <Input className="mt-2" value={name} onChange={(e) => setName(e.target.value)} placeholder="HR policy assistant" />
            </label>
            <label className="block">
              <span className="font-semibold">Brief</span>
              <Textarea className="mt-2 min-h-48 text-[17px] leading-7" value={brief} onChange={(e) => setBrief(e.target.value)}
                placeholder="I need an assistant that answers HR policy questions for shore staff…" />
              <span className="mt-2 block text-[15px] text-sounding">Mention anything it must refuse. Ask for something the documents don't cover and the factory will flag it.</span>
            </label>
          </div>
        )}
        {step === 2 && (
          <div className="max-w-[68ch] space-y-8">
            <label className="flex items-start gap-4">
              <Switch checked={checkpoint} onCheckedChange={setCheckpoint} className="mt-1" />
              <span><span className="font-medium">Let me approve the requirements first</span>
                <span className="block text-[15px] text-sounding">The run pauses after intake so you can edit what the agent must refuse.</span></span>
            </label>
            <div className="grid gap-6 sm:grid-cols-2">
              <label className="block"><span className="text-[15px] font-medium">Prompt candidates (1 to 3)</span>
                <Input type="number" min={1} max={3} value={candidates} onChange={(e) => setCandidates(Number(e.target.value))} className="mt-2" /></label>
              {pick !== UPLOAD && (
                <label className="block"><span className="text-[15px] font-medium">Token budget (optional)</span>
                  <Input type="number" min={10000} step={10000} value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="No limit" className="mt-2" /></label>)}
            </div>
            <dl className="grid gap-x-8 gap-y-2 border-t border-white/10 pt-6 sm:grid-cols-[auto_1fr]">
              <dt className="text-sounding">Documents</dt><dd>{pick === UPLOAD ? `${files?.length ?? 0} uploaded file(s)` : pick ?? <span className="text-port">none chosen</span>}</dd>
              <dt className="text-sounding">Brief</dt><dd>{brief || <span className="text-port">missing</span>}</dd>
            </dl>
            {!modelsOk && <p className="text-port">No model server is ready{modelsError ? ` (${modelsError})` : ''}, so new runs can't start. Saved runs still open.</p>}
            {err && <p className="text-port">{err}</p>}
          </div>
        )}
      </motion.section>

      <div className="mt-10 flex items-center justify-between border-t border-white/10 pt-6">
        <Button variant="ghost" onClick={() => (step === 0 ? history.back() : setStep((s) => s - 1))}><ArrowLeft /> Back</Button>
        {step < 2
          ? <Button onClick={() => setStep((s) => s + 1)} disabled={!done[step]}>Next <ArrowRight /></Button>
          : <button className="glass-btn glass-btn--tint disabled:opacity-40" onClick={start} disabled={busy || !modelsOk || !brief.trim() || !done[0]}>
              <Play className="size-4" aria-hidden /> {busy ? 'Starting…' : 'Start the run'}</button>}
      </div>
    </div>
  )
}
