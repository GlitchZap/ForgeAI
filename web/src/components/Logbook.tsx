import { useState } from 'react'
import { Archive, ArchiveRestore, ArrowRight, Trash2 } from 'lucide-react'
import { api, percent, type RunSummary } from '@/lib/api'

const STATUS: Record<RunSummary['status'], [string, string]> = {
  running: ['running', 'text-magenta'], awaiting_approval: ['needs approval', 'text-magenta'],
  done: ['finished', 'text-starboard'], failed: ['failed', 'text-port'], incomplete: ['incomplete', 'text-sounding'],
  stopped: ['stopped', 'text-sounding'],
}

export const providerName = (p?: string) => (p === 'groq' ? 'Groq' : 'Ollama')

const act = 'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-sm text-sounding hover:bg-white/[.08] hover:text-ink disabled:opacity-40 disabled:hover:bg-transparent'

/** Every run in one table: open any of them to see its sections, or file it away / delete it. */
export function Logbook({ runs, onChanged }: { runs: RunSummary[]; onChanged: () => void }) {
  const [showArchived, setShowArchived] = useState(false)
  const [confirming, setConfirming] = useState<string | null>(null)
  const [error, setError] = useState('')
  const archivedCount = runs.filter((r) => r.archived).length
  const shown = runs.filter((r) => !!r.archived === showArchived)
  const busy = (r: RunSummary) => r.status === 'running' || r.status === 'awaiting_approval'

  const run = (p: Promise<unknown>) => p.then(() => { setError(''); setConfirming(null); onChanged() }).catch((e) => setError(e.message))

  return (
    <div className="mx-auto max-w-[1200px] px-6 py-10">
      <h1 className="display text-[clamp(2.6rem,5vw,4.2rem)] leading-[1]">logbook</h1>
      <p className="mt-2 text-lg text-sounding">Every factory run, newest first. Open one to see its chart, tests, fixes, requirements, report and agent.</p>
      <div role="tablist" aria-label="Which runs" className="mt-6 flex gap-1">
        {[false, true].map((a) => (
          <button key={String(a)} role="tab" aria-selected={showArchived === a} onClick={() => { setShowArchived(a); setConfirming(null) }}
            className={`rounded-full px-4 py-1.5 text-sm font-medium ${showArchived === a ? 'bg-white/[.12] text-ink' : 'text-sounding hover:text-ink'}`}>
            {a ? `Archived (${archivedCount})` : `Active (${runs.length - archivedCount})`}
          </button>))}
      </div>
      {error && <p role="alert" className="mt-3 text-port">{error}</p>}
      <div className="mt-4 overflow-x-auto border border-white/10">
        <table className="w-full min-w-[900px] text-left">
          <thead className="border-b border-white/10 text-sm text-sounding">
            <tr><th className="p-4 font-medium">Run</th><th className="p-4 font-medium">Status</th><th className="p-4 text-right font-medium">Score</th>
              <th className="p-4 text-right font-medium">Dev</th><th className="p-4 text-right font-medium">Holdout</th>
              <th className="p-4 font-medium">Model</th><th className="p-4 font-medium">Date</th><th className="p-4 text-right font-medium">Actions</th></tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {shown.length === 0 && <tr><td colSpan={8} className="p-6 text-sounding">{showArchived ? 'No archived runs.' : 'No runs yet. Start one from New run.'}</td></tr>}
            {shown.map((r) => (
              <tr key={r.id} className="group cursor-pointer hover:bg-panel" onClick={() => { location.hash = `run/${r.id}` }}>
                <td className="p-4"><a href={`#run/${r.id}`} className="font-medium">{r.name}</a></td>
                <td className={`p-4 ${STATUS[r.status][1]}`}>{STATUS[r.status][0]}</td>
                <td className="display p-4 text-right text-2xl tabular-nums">{percent(r.final?.overall_pass_rate)}</td>
                <td className="p-4 text-right tabular-nums">{percent(r.final?.dev_pass_rate)}</td>
                <td className="p-4 text-right tabular-nums">{percent(r.final?.holdout_pass_rate)}</td>
                <td className="p-4 text-sounding">
                  <span className="mr-2 rounded-md bg-white/[.08] px-1.5 py-0.5 text-xs font-semibold text-ink">{providerName(r.provider)}</span>{r.model ?? '–'}
                </td>
                <td className="p-4 text-sounding">{new Date(r.updated * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</td>
                <td className="p-4" onClick={(e) => e.stopPropagation()}>
                  <div className="flex items-center justify-end gap-1">
                    {confirming === r.id ? <>
                      <span className="text-sm text-port">Delete for good?</span>
                      <button className={`${act} text-port hover:text-port`} onClick={() => run(api.remove(r.id))}>Delete</button>
                      <button className={act} onClick={() => setConfirming(null)}>Cancel</button>
                    </> : <>
                      <button className={act} disabled={busy(r)} title={busy(r) ? 'Wait for the run to finish' : undefined}
                        onClick={() => run(api.archive(r.id, !r.archived))}>
                        {r.archived ? <ArchiveRestore className="size-4" aria-hidden /> : <Archive className="size-4" aria-hidden />}
                        {r.archived ? 'Restore' : 'Archive'}<span className="sr-only"> {r.name}</span>
                      </button>
                      <button className={act} disabled={busy(r)} title={busy(r) ? 'Wait for the run to finish' : undefined} onClick={() => setConfirming(r.id)}>
                        <Trash2 className="size-4" aria-hidden />Delete<span className="sr-only"> {r.name}</span>
                      </button>
                      <ArrowRight className="ml-1 size-4 text-sounding group-hover:text-magenta" aria-hidden />
                    </>}
                  </div>
                </td>
              </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
