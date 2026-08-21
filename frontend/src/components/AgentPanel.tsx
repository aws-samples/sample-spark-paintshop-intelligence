import { useEffect, useRef } from 'react'
import type { AgentMessage } from '../types'

interface Props {
  messages: AgentMessage[]
}

interface PriorOccurrence {
  date: string
  severity: string
  root_cause: string
}

function RcaResult({ r }: { r: Record<string, unknown> }) {
  const severityColor = (s: unknown) =>
    s === 'HIGH' || s === 'CRITICAL' ? 'text-red-400' :
    s === 'MEDIUM'                    ? 'text-amber-400' : 'text-emerald-400'

  const occurrences   = (r.prior_occurrences as PriorOccurrence[] | undefined) ?? []
  const occCount      = (r.occurrence_count as number | undefined) ?? occurrences.length

  return (
    <div className="space-y-2.5 text-xs">
      {/* Severity + Recurrence Risk */}
      <div className="flex gap-4">
        <div>
          <div className="text-slate-500 uppercase tracking-wider text-[10px]">Severity</div>
          <div className={`font-semibold ${severityColor(r.severity)}`}>{String(r.severity ?? '—')}</div>
        </div>
        <div>
          <div className="text-slate-500 uppercase tracking-wider text-[10px]">Recurrence Risk</div>
          <div className={`font-semibold ${severityColor(r.recurrence_risk)}`}>{String(r.recurrence_risk ?? '—')}</div>
        </div>
        {occCount > 0 && (
          <div>
            <div className="text-slate-500 uppercase tracking-wider text-[10px]">Occurrences (30d)</div>
            <div className={`font-semibold ${occCount >= 3 ? 'text-red-400' : 'text-amber-400'}`}>{occCount}×</div>
          </div>
        )}
      </div>

      {/* Root Cause */}
      <div>
        <div className="text-slate-500 uppercase tracking-wider text-[10px] mb-0.5">Root Cause</div>
        <div className="text-slate-200 leading-relaxed">{String(r.root_cause ?? '—')}</div>
      </div>

      {/* Recommendation */}
      <div>
        <div className="text-slate-500 uppercase tracking-wider text-[10px] mb-0.5">Recommendation</div>
        <div className="text-slate-300 leading-relaxed">{String(r.recommendation ?? '—')}</div>
      </div>

      {/* Prior Occurrences */}
      {occurrences.length > 0 && (
        <div>
          <div className="text-slate-500 uppercase tracking-wider text-[10px] mb-1">Prior Occurrences</div>
          <div className="space-y-1 border-l-2 border-slate-700 pl-2">
            {occurrences.slice(0, 3).map((o, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-slate-600 shrink-0">{o.date}</span>
                <span className={`shrink-0 font-medium ${severityColor(o.severity)}`}>{o.severity}</span>
                <span className="text-slate-400 leading-snug">{o.root_cause}</span>
              </div>
            ))}
          </div>
          {occCount >= 3 && (
            <div className="mt-1 text-red-400/80 text-[10px]">
              ⚠ Recurring fault — prior remediations may be incomplete
            </div>
          )}
        </div>
      )}

      {r.report_id != null && (
        <div className="text-slate-600 text-[10px]">Report ID: {String(r.report_id)}</div>
      )}
    </div>
  )
}

function MpsResult({ r }: { r: Record<string, unknown> }) {
  const assignments = ((r.assignments as Record<string, unknown>[]) ?? [])
    .filter(a => a.to_tank != null || a.new_tank != null)
  const jph = r.projected_jph as number | null | undefined
  const fbo = r.fbo_delay_mins as number | null | undefined
  const jphColor = jph != null && jph >= 45 ? 'text-emerald-400' : 'text-amber-400'
  return (
    <div className="space-y-2 text-xs">
      <div className="flex gap-4">
        <div>
          <div className="text-slate-500 uppercase tracking-wider text-[10px]">Projected JPH</div>
          <div className={`font-semibold ${jphColor}`}>{jph ?? '—'}</div>
        </div>
        <div>
          <div className="text-slate-500 uppercase tracking-wider text-[10px]">FBO Delay</div>
          <div className={`font-semibold ${fbo != null && fbo > 0 ? 'text-amber-400' : 'text-emerald-400'}`}>
            {fbo == null ? '—' : `${fbo} min`}
          </div>
        </div>
      </div>
      {r.summary != null && (
        <div className="text-slate-300 leading-relaxed">{String(r.summary)}</div>
      )}
      {assignments.length > 0 && (
        <div>
          <div className="text-slate-500 uppercase tracking-wider text-[10px] mb-1">Rescheduled Jobs</div>
          <div className="space-y-1">
            {assignments.map((a, i) => (
              <div key={i} className="flex items-center gap-1.5 text-slate-300">
                <span className="text-slate-500">{String(a.job_id)}</span>
                <span className="text-slate-600">→</span>
                <span className="text-emerald-400">{String(a.to_tank ?? a.new_tank)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function AgentMessageCard({ msg }: { msg: AgentMessage }) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msg.chunks])

  const agentColor = msg.agent === 'mps' ? 'text-accent border-accent/30' : 'text-purple-400 border-purple-400/30'
  const agentBg    = msg.agent === 'mps' ? 'bg-accent/5' : 'bg-purple-500/5'

  return (
    <div className={`border rounded p-3 space-y-2 ${agentBg} ${agentColor.split(' ')[1]}`}>
      <div className="flex items-center justify-between">
        <span className={`text-xs font-semibold uppercase tracking-wider ${agentColor.split(' ')[0]}`}>
          {msg.agent === 'mps' ? 'MPS Agent' : 'RCA Agent'} — {msg.tank_id}
        </span>
        <div className="flex items-center gap-2">
          {!msg.done && (
            <span className="flex gap-0.5">
              <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1 h-1 bg-current rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          )}
          <span className="text-slate-500 text-xs">{new Date(msg.timestamp).toLocaleTimeString()}</span>
        </div>
      </div>

      {/* Streaming indicator (no raw text shown) */}
      {!msg.done && !msg.error && (
        <div className="text-xs text-slate-500 italic">Analysing...</div>
      )}

      {/* Error */}
      {msg.error && (
        <div className="text-red-400 text-xs">{msg.error}</div>
      )}

      {/* Rendered result */}
      {msg.done && msg.result && (
        msg.agent === 'rca'
          ? <RcaResult r={msg.result as Record<string, unknown>} />
          : <MpsResult r={msg.result as Record<string, unknown>} />
      )}
    </div>
  )
}

export default function AgentPanel({ messages }: Props) {
  return (
    <div className="panel space-y-2">
      <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-3">
        Agent Activity
      </div>

      {messages.length === 0 ? (
        <div className="text-slate-600 text-xs text-center py-6">
          Select a degraded tank and click Reschedule or Root Cause to invoke an agent
        </div>
      ) : (
        <div className="space-y-3 max-h-96 overflow-y-auto pr-1">
          {messages.map(msg => (
            <AgentMessageCard key={msg.id} msg={msg} />
          ))}
        </div>
      )}
    </div>
  )
}
