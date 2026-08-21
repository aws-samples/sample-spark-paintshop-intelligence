import { useEffect, useRef, useState } from 'react'
import type { TankStatus } from '../types'

const TANK_NAMES: Record<string, string> = {
  'PT-01': 'Hot Pre-Clean',     'PT-02': 'Main Cleaner',
  'PT-03': 'Rinse 1',           'PT-04': 'Rinse 2',
  'PT-05': 'Activation',        'PT-06': 'Zinc Phosphate',
  'PT-07': 'Post-Rinse',        'PT-08': 'Nano-Seal',
  'ED-01': 'E-Coat Bath',       'ED-02': 'UF Rinse 1',
  'ED-03': 'UF Rinse 2',        'ED-04': 'DI Water Final Rinse',
}

interface Props {
  tank: TankStatus
  onAnalyse: (agent: 'mps' | 'rca') => void
  detailed?: boolean
}

function ModelScore({ label, sublabel, value }: { label: string; sublabel: string; value: number }) {
  const pct = Math.min(value * 100, 100)
  const color = pct > 70 ? 'bg-red-500' : pct > 40 ? 'bg-amber-500' : 'bg-emerald-500'
  return (
    <div>
      <div className="flex justify-between text-xs mb-0.5">
        <span className="text-slate-400">{label} <span className="text-slate-600 text-[10px]">{sublabel}</span></span>
        <span className="text-slate-400">{value.toFixed(2)}</span>
      </div>
      <div className="h-1 bg-slate-700 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function AnomalyRiskBar({ tank }: { tank: TankStatus }) {
  const risk = tank.status === 'degraded'
    ? 1
    : Math.max(tank.if_score ?? 0, tank.lstm_score ?? 0)
  const pct  = Math.min(risk * 100, 100)
  const color = pct > 70 ? 'bg-red-500' : pct > 40 ? 'bg-amber-500' : 'bg-emerald-500'
  const label = pct > 70 ? 'High' : pct > 40 ? 'Elevated' : 'Normal'
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-slate-400">Anomaly Risk</span>
        <span className={pct > 70 ? 'text-red-400' : pct > 40 ? 'text-amber-400' : 'text-emerald-400'}>
          {label} · {pct.toFixed(0)}%
        </span>
      </div>
      <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export default function TankCard({ tank, onAnalyse, detailed = false }: Props) {
  const prevSensors = useRef<Record<string, number>>({})
  const [flashing, setFlashing] = useState<Record<string, boolean>>({})

  useEffect(() => {
    const changed: Record<string, boolean> = {}
    for (const [k, v] of Object.entries(tank.sensors ?? {})) {
      if (prevSensors.current[k] !== undefined && prevSensors.current[k] !== v) {
        changed[k] = true
      }
    }
    if (Object.keys(changed).length > 0) {
      setFlashing(changed)
      setTimeout(() => setFlashing({}), 1200)
    }
    prevSensors.current = { ...(tank.sensors ?? {}) }
  }, [tank.sensors])

  const statusClass =
    tank.status === 'online'   ? 'badge-online'   :
    tank.status === 'degraded' ? 'badge-degraded' : 'badge-offline'

  const borderColor =
    tank.status === 'online'   ? 'border-emerald-800' :
    tank.status === 'degraded' ? 'border-amber-700'   : 'border-red-800'

  const jph = tank.current_jph ?? 0
  const jphColor =
    jph >= 48 ? 'text-emerald-400' :
    jph >= 45 ? 'text-amber-400'   : 'text-red-400'

  return (
    <div className={`panel border ${borderColor} space-y-3 relative`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-baseline gap-2">
            <span className="text-slate-100 font-semibold">{tank.tank_id}</span>
            <span className="text-slate-500 text-xs">{tank.line_id}</span>
          </div>
          {TANK_NAMES[tank.tank_id] && (
            <div className="text-slate-400 text-xs mt-0.5">{TANK_NAMES[tank.tank_id]}</div>
          )}
        </div>
        <span className={statusClass}>{tank.status}</span>
      </div>

      {/* JPH */}
      <div className="flex items-baseline gap-1">
        <span className={`text-3xl font-semibold ${jphColor}`}>{jph}</span>
        <span className="text-slate-500 text-xs">JPH</span>
        <span className="text-slate-500 text-xs ml-auto">target ≥ 45</span>
      </div>

      {detailed ? (
        /* ML Diagnostics view — three individual model scores */
        <div className="space-y-1.5">
          <ModelScore label="XGBoost"          sublabel="classifier"     value={tank.fault_type && tank.fault_type !== 'normal' ? (tank.xgb_confidence ?? 0) : 0} />
          <ModelScore label="Isolation Forest" sublabel="anomaly"        value={tank.if_score   ?? 0} />
          <ModelScore label="LSTM AE"          sublabel="reconstruction" value={tank.lstm_score ?? 0} />
        </div>
      ) : (
        /* Control Center view — single combined anomaly risk bar */
        <AnomalyRiskBar tank={tank} />
      )}

      {/* Fault classification result */}
      {tank.fault_type && tank.fault_type !== 'normal' && (
        <div className="text-xs text-amber-400 bg-amber-900/20 border border-amber-800 rounded px-2 py-1">
          Detected: <span className="font-medium">{tank.fault_type}</span>
        </div>
      )}

      {/* Sensor snapshot — detailed view only */}
      {detailed && Object.keys(tank.sensors ?? {}).length > 0 && (
        <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
          {Object.entries(tank.sensors).slice(0, 6).map(([k, v]) => (
            <div
              key={k}
              className={`flex justify-between rounded px-1 transition-colors duration-300 ${
                flashing[k] ? 'bg-blue-500/20 text-blue-300' : 'text-slate-400'
              }`}
            >
              <span className="truncate">{k}</span>
              <span className={`font-mono ml-1 ${flashing[k] ? 'text-blue-300' : 'text-slate-300'}`}>
                {(v as number).toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Action buttons — only for degraded/offline */}
      {tank.status !== 'online' && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => onAnalyse('mps')}
            className="flex-1 text-xs border border-accent/40 text-accent/80 rounded py-1 hover:bg-accent/10 transition"
          >
            Reschedule (MPS)
          </button>
          <button
            onClick={() => onAnalyse('rca')}
            className="flex-1 text-xs border border-purple-500/40 text-purple-400/80 rounded py-1 hover:bg-purple-500/10 transition"
          >
            Root Cause (RCA)
          </button>
        </div>
      )}

      {/* Last reading */}
      <div className="text-xs text-slate-600 text-right">
        {tank.last_reading_ts ? new Date(tank.last_reading_ts).toLocaleTimeString() : '—'}
      </div>
    </div>
  )
}
