import { useState } from 'react'
import type { Incident } from '../types'

const SEV_COLOR: Record<string, string> = {
  HIGH:    'text-red-400 bg-red-900/20 border-red-800',
  MEDIUM:  'text-amber-400 bg-amber-900/20 border-amber-800',
  LOW:     'text-slate-400 bg-slate-800 border-slate-700',
  UNKNOWN: 'text-slate-500 bg-slate-800 border-slate-700',
}

function StatusPill({ label, status }: { label: string; status: string }) {
  if (status === 'COMPLETE') return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border border-emerald-800 text-emerald-400">
      {label} ✓
    </span>
  )
  if (status === 'FALLBACK') return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border border-amber-800 text-amber-400">
      {label} !
    </span>
  )
  // PENDING
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded border border-slate-700 text-slate-500 animate-pulse">
      {label} …
    </span>
  )
}

export default function IncidentCard({ incident }: { incident: Incident }) {
  const [expanded, setExpanded] = useState(false)

  // Agent may return {action:'reroute'} or legacy {to_tank:'...'} without action field
  const rerouted = incident.assignments?.filter(
    a => a.action === 'reroute' || (!a.action && (a.to_tank || a.new_tank))
  ).length ?? 0
  // Held jobs aren't always in assignments — fall back to parsing mps_summary
  const heldFromAssignments = incident.assignments?.filter(a => a.action === 'hold_for_inspection').length ?? 0
  const heldMatch = incident.mps_summary?.match(/(\d+)\s+(?:IN_PROGRESS\s+)?job.*?held/i)
  const held = heldFromAssignments || (heldMatch ? parseInt(heldMatch[1]) : 0)
  const sevClass = SEV_COLOR[incident.severity ?? 'UNKNOWN'] ?? SEV_COLOR.UNKNOWN

  return (
    <div
      className="panel cursor-pointer hover:border-slate-600 transition"
      onClick={() => setExpanded(e => !e)}
    >
      {/* Collapsed header — always visible */}
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-slate-100 font-semibold font-mono">{incident.tank_id}</span>
          <span className="text-slate-400 text-xs truncate">{incident.fault_type}</span>
          <span className="text-slate-600 text-xs">
            {new Date(incident.timestamp).toLocaleTimeString()}
          </span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {incident.projected_jph != null && (
            <span className="text-xs text-slate-400">JPH {incident.projected_jph}</span>
          )}
          {incident.severity && incident.rca_status !== 'PENDING' && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded border ${sevClass}`}>
              {incident.severity}
            </span>
          )}
          <StatusPill label="MPS" status={incident.mps_status ?? 'PENDING'} />
          <StatusPill label="RCA" status={incident.rca_status ?? 'PENDING'} />
          <span className="text-slate-600 text-xs ml-1">{expanded ? '▲' : '▼'}</span>
        </div>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div className="mt-4 grid grid-cols-1 md:grid-cols-2 gap-4 border-t border-border pt-4">

          {/* MPS section */}
          <div className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-widest text-emerald-500">
              MPS Response
            </div>
            {incident.supervisor_summary && (
              <p className="text-xs text-slate-300 leading-relaxed">
                {incident.supervisor_summary}
              </p>
            )}
            {incident.cascade_warning && (
              <div className="text-xs text-amber-300 bg-amber-900/20 border border-amber-800/50 rounded px-2 py-1.5">
                {incident.cascade_warning}
              </div>
            )}
            {incident.at_risk_tanks && incident.at_risk_tanks.length > 0 && (
              <div className="flex items-center gap-1 flex-wrap">
                <span className="text-xs text-slate-500">At risk:</span>
                {incident.at_risk_tanks.map(t => (
                  <span key={t} className="text-[10px] px-1.5 py-0.5 rounded border border-amber-800 text-amber-400">
                    {t}
                  </span>
                ))}
              </div>
            )}
            {incident.priority_notes && (
              <p className="text-xs text-slate-500 italic">{incident.priority_notes}</p>
            )}
            <div className="text-xs text-slate-500">
              {rerouted} rerouted · {held} held for inspection
            </div>
          </div>

          {/* RCA section */}
          <div className="space-y-2">
            <div className="text-xs font-semibold uppercase tracking-widest text-purple-400">
              RCA Analysis
            </div>
            {incident.rca_status === 'PENDING' ? (
              <p className="text-xs text-slate-500 animate-pulse">RCA analysis in progress...</p>
            ) : (
              <>
                {incident.root_cause && (
                  <p className="text-xs text-slate-300 leading-relaxed">{incident.root_cause}</p>
                )}
                {incident.recurrence_risk && (
                  <div className="text-xs text-slate-400">
                    Recurrence risk: <span className="text-slate-200">{incident.recurrence_risk}</span>
                  </div>
                )}
                {incident.recommendation && (
                  <p className="text-xs text-slate-400 leading-relaxed">{incident.recommendation}</p>
                )}
                {incident.report_id && incident.report_id !== 'fallback' && (
                  <div className="text-xs text-accent/70">
                    Report: {incident.report_id}
                  </div>
                )}
              </>
            )}
          </div>

        </div>
      )}
    </div>
  )
}
