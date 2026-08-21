import { useState, useCallback, useEffect, useRef } from 'react'
import { fetchAuthSession } from 'aws-amplify/auth'
import type { TankStatus } from '../types'
import { getConfig } from '../aws-config'

const TANK_NAMES: Record<string, string> = {
  'PT-01': 'Hot Pre-Clean',     'PT-02': 'Main Cleaner',
  'PT-03': 'Rinse 1',           'PT-04': 'Rinse 2',
  'PT-05': 'Activation',        'PT-06': 'Zinc Phosphate',
  'PT-07': 'Post-Rinse',        'PT-08': 'Nano-Seal',
  'ED-01': 'E-Coat Bath',       'ED-02': 'UF Rinse 1',
  'ED-03': 'UF Rinse 2',        'ED-04': 'DI Water Final Rinse',
}

const FAULT_MAP: Record<string, string> = {
  'PT-01': 'alkalinity_depletion', 'PT-02': 'alkalinity_depletion',
  'PT-03': 'rinse_contamination',  'PT-04': 'rinse_contamination',
  'PT-05': 'titanium_depletion',   'PT-06': 'acid_drift',
  'PT-07': 'rinse_contamination',  'PT-08': 'ph_drift',
  'ED-01': 'temperature_creep',    'ED-02': 'rinse_contamination',
  'ED-03': 'rinse_contamination',  'ED-04': 'rinse_contamination',
}

interface Props {
  tanks: Record<string, TankStatus>
}

function useDemoApi() {
  const call = useCallback(async (path: string, body?: object) => {
    const cfg     = getConfig()
    const session = await fetchAuthSession()
    const token   = session.tokens?.idToken?.toString() ?? ''
    const resp = await fetch(`${cfg.restApiEndpoint}${path}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    })
    return resp.json()
  }, [])
  return call
}

function TelemetryCard({ tank }: { tank: TankStatus }) {
  const call      = useDemoApi()
  const [busy, setBusy] = useState('')
  const prevSensors = useRef<Record<string, number>>({})
  const [flashing, setFlashing] = useState<Record<string, boolean>>({})

  // pending persisted in sessionStorage so tab switches don't reset it
  const pendingKey = `demo_pending_${tank.tank_id}`
  const [pending, setPendingState] = useState<'inject' | 'reset' | null>(
    () => (sessionStorage.getItem(pendingKey) as 'inject' | 'reset' | null) ?? null
  )
  const setPending = (v: 'inject' | 'reset' | null) => {
    setPendingState(v)
    if (v) sessionStorage.setItem(pendingKey, v)
    else   sessionStorage.removeItem(pendingKey)
  }

  // Clear pending once tank.status reflects the expected outcome
  useEffect(() => {
    if (pending === 'inject' && tank.status !== 'online') setPending(null)
    if (pending === 'reset'  && tank.status === 'online') setPending(null)
  }, [tank.status, pending])

  // Flash sensors that changed value
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
    prevSensors.current = { ...tank.sensors }
  }, [tank.sensors])

  const inject = async () => {
    setBusy('inject')
    await call('/demo/inject', { tank_id: tank.tank_id, fault_type: FAULT_MAP[tank.tank_id] })
    setBusy('')
    setPending('inject')
  }

  const reset = async () => {
    setBusy('reset')
    await call('/demo/reset', { tank_id: tank.tank_id })
    setBusy('')
    setPending('reset')
  }

  const statusColor =
    tank.status === 'online'   ? 'text-emerald-400 border-emerald-800' :
    tank.status === 'degraded' ? 'text-amber-400 border-amber-700'     : 'text-red-400 border-red-800'

  const sensors = Object.entries(tank.sensors ?? {})

  return (
    <div className={`bg-panel border rounded p-3 space-y-2 ${statusColor.split(' ')[1]}`}>
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-slate-200 font-semibold text-sm">{tank.tank_id}</span>
              <span className={`text-xs font-medium ${statusColor.split(' ')[0]}`}>{tank.status}</span>
            </div>
            {TANK_NAMES[tank.tank_id] && (
              <div className="text-slate-500 text-[10px] leading-tight">{TANK_NAMES[tank.tank_id]}</div>
            )}
          </div>
          {tank.fault_type && tank.fault_type !== 'normal' && (
            <span className="text-amber-400 text-xs bg-amber-900/20 border border-amber-800 rounded px-1.5 py-0.5">
              {tank.fault_type}
            </span>
          )}
        </div>
        <span className="text-slate-600 text-[10px]">
          {tank.last_reading_ts ? new Date(tank.last_reading_ts).toLocaleTimeString() : '—'}
        </span>
      </div>

      {/* Sensor readings */}
      {sensors.length > 0 ? (
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-xs">
          {sensors.map(([k, v]) => (
            <div
              key={k}
              className={`flex justify-between transition-colors duration-300 rounded px-1 ${flashing[k] ? 'bg-blue-500/20 text-blue-300' : 'text-slate-400'}`}
            >
              <span className="truncate">{k}</span>
              <span className={`font-mono ml-1 ${flashing[k] ? 'text-blue-300' : 'text-slate-300'}`}>
                {typeof v === 'number' ? v.toFixed(2) : String(v)}
              </span>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-slate-600 text-xs text-center py-2">Waiting for reading...</div>
      )}

      {/* JPH + ML model scores */}
      <div className="flex gap-3 text-xs text-slate-500 border-t border-border pt-1">
        <span>JPH <span className="text-slate-300">{tank.current_jph ?? 0}</span></span>
        <span title="XGBoost Classifier">XGB <span className="text-slate-300">{(tank.fault_type && tank.fault_type !== 'normal' ? (tank.xgb_confidence ?? 0) : 0).toFixed(2)}</span></span>
        <span title="Isolation Forest Anomaly Score">IF <span className="text-slate-300">{(tank.if_score ?? 0).toFixed(2)}</span></span>
        <span title="LSTM Autoencoder Reconstruction Score">LSTM <span className="text-slate-300">{(tank.lstm_score ?? 0).toFixed(2)}</span></span>
      </div>

      {/* Action buttons */}
      <div className="flex gap-2 pt-1">
        {tank.status === 'online' && pending == null ? (
          <button
            onClick={inject}
            disabled={!!busy}
            className="flex-1 text-xs border border-amber-600/40 text-amber-400/80 rounded py-1 hover:bg-amber-600/10 disabled:opacity-40 transition"
          >
            {busy === 'inject' ? 'Injecting...' : `Inject ${FAULT_MAP[tank.tank_id] ?? 'Fault'}`}
          </button>
        ) : (
          <button
            onClick={tank.status !== 'online' && pending == null ? reset : undefined}
            disabled={!!busy || pending != null || tank.status === 'online'}
            className="flex-1 text-xs border border-emerald-600/40 text-emerald-400/80 rounded py-1 hover:bg-emerald-600/10 disabled:opacity-40 transition"
          >
            {busy === 'reset'        ? 'Resetting...'       :
             pending === 'inject'    ? 'Detecting fault...' :
             pending === 'reset'     ? 'Restoring...'       : 'Reset to Normal'}
          </button>
        )}
      </div>
    </div>
  )
}

function TelemetrySection({ title, subtitle, tanks }: {
  title: string; subtitle: string; tanks: TankStatus[]
}) {
  if (tanks.length === 0) return null
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <span className="text-slate-300 text-xs font-semibold uppercase tracking-widest">{title}</span>
        <span className="text-slate-600 text-xs">{subtitle}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
        {tanks.map(t => <TelemetryCard key={t.tank_id} tank={t} />)}
      </div>
    </div>
  )
}

export default function TelemetryView({ tanks }: Props) {
  const sorted = Object.values(tanks).sort((a, b) => a.tank_id.localeCompare(b.tank_id))
  const ptTanks = sorted.filter(t => t.tank_id.startsWith('PT'))
  const edTanks = sorted.filter(t => t.tank_id.startsWith('ED'))

  if (sorted.length === 0) {
    return (
      <div className="panel flex items-center justify-center h-40 text-slate-500">
        Waiting for tank telemetry...
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <TelemetrySection
        title="Pre-Treatment"
        subtitle="PT-01 – PT-08 · Cleaning & Phosphating"
        tanks={ptTanks}
      />
      <TelemetrySection
        title="ElectroDeposition"
        subtitle="ED-01 – ED-04 · E-Coat Priming"
        tanks={edTanks}
      />
    </div>
  )
}
