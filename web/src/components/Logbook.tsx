import { ArrowRight } from 'lucide-react'
import { percent, type RunSummary } from '@/lib/api'

const STATUS: Record<RunSummary['status'], [string, string]> = {
  running: ['running', 'text-magenta'], awaiting_approval: ['needs approval', 'text-magenta'],
  done: ['finished', 'text-starboard'], failed: ['failed', 'text-port'], incomplete: ['incomplete', 'text-sounding'],
}

/** Every run in one table: open any of them to see its sections. */
export function Logbook({ runs }: { runs: RunSummary[] }) {
  return (
    <div className="mx-auto max-w-[1200px] px-6 py-10">
      <h1 className="display text-[clamp(2.6rem,5vw,4.2rem)] leading-[1]">logbook</h1>
      <p className="mt-2 text-lg text-sounding">Every factory run, newest first. Open one to see its chart, tests, fixes, requirements, report and agent.</p>
      <div className="mt-8 overflow-x-auto border border-white/10">
        <table className="w-full min-w-[720px] text-left">
          <thead className="border-b border-white/10 text-sm text-sounding">
            <tr><th className="p-4 font-medium">Run</th><th className="p-4 font-medium">Status</th><th className="p-4 text-right font-medium">Score</th>
              <th className="p-4 text-right font-medium">Dev</th><th className="p-4 text-right font-medium">Holdout</th>
              <th className="p-4 font-medium">Model</th><th className="p-4 font-medium">Date</th><th className="p-4"><span className="sr-only">Open</span></th></tr>
          </thead>
          <tbody className="divide-y divide-white/10">
            {runs.length === 0 && <tr><td colSpan={8} className="p-6 text-sounding">No runs yet. Start one from New run.</td></tr>}
            {runs.map((r) => (
              <tr key={r.id} className="group cursor-pointer hover:bg-panel" onClick={() => { location.hash = `run/${r.id}` }}>
                <td className="p-4"><a href={`#run/${r.id}`} className="font-medium">{r.name}</a></td>
                <td className={`p-4 ${STATUS[r.status][1]}`}>{STATUS[r.status][0]}</td>
                <td className="display p-4 text-right text-2xl tabular-nums">{percent(r.final?.overall_pass_rate)}</td>
                <td className="p-4 text-right tabular-nums">{percent(r.final?.dev_pass_rate)}</td>
                <td className="p-4 text-right tabular-nums">{percent(r.final?.holdout_pass_rate)}</td>
                <td className="p-4 text-sounding">{r.model ?? '–'}</td>
                <td className="p-4 text-sounding">{new Date(r.updated * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}</td>
                <td className="p-4 text-right"><ArrowRight className="ml-auto size-4 text-sounding group-hover:text-magenta" aria-hidden /></td>
              </tr>))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
