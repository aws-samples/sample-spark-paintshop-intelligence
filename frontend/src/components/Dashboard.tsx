import { useEffect, useState, useCallback, useRef } from 'react'
import { signOut, fetchUserAttributes, fetchAuthSession } from 'aws-amplify/auth'
import TankGrid from './TankGrid'
import AnomalyFeed from './AnomalyFeed'
import AgentPanel from './AgentPanel'
import ScheduleTable from './ScheduleTable'
import TelemetryView from './TelemetryView'
import TankHistoryView from './TankHistoryView'
import IncidentsList from './IncidentsList'
import { useWebSocket } from '../hooks/useWebSocket'
import { useSchedule } from '../hooks/useApi'
import { getConfig } from '../aws-config'

type Tab = 'control' | 'diagnostics' | 'incidents' | 'telemetry' | 'history'

function MetricBadge({ label, value, unit, alert }: {
  label: string; value: string | number; unit?: string; alert?: boolean
}) {
  return (
    <div className="bg-panel border border-border rounded px-3 py-2">
      <div className="text-slate-500 text-xs uppercase tracking-wider">{label}</div>
      <div className={`text-lg font-semibold mt-0.5 ${alert ? 'text-amber-400' : 'text-slate-100'}`}>
        {value}<span className="text-xs text-slate-500 ml-1">{unit}</span>
      </div>
    </div>
  )
}

// Veltros Motors SVG logo
function VeltrosLogo() {
  return (
    <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
      <circle cx="14" cy="14" r="13" stroke="#3b82f6" strokeWidth="1.5" />
      <path d="M7 9 L14 20 L21 9" stroke="#3b82f6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
      <path d="M10.5 9 L14 15.5 L17.5 9" stroke="#60a5fa" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

function DemoControls() {
  const [telemetry, setTelemetry]   = useState<boolean | null>(null)
  const [busy, setBusy]             = useState('')

  const apiFetch = useCallback(async (path: string, method = 'GET', body?: object) => {
    const cfg     = getConfig()
    const session = await fetchAuthSession()
    const token   = session.tokens?.idToken?.toString() ?? ''
    const resp = await fetch(`${cfg.restApiEndpoint}${path}`, {
      method,
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      body: body ? JSON.stringify(body) : undefined,
    })
    return resp.json()
  }, [])

  // Load telemetry state on mount
  useEffect(() => {
    apiFetch('/demo/status').then(d => setTelemetry(d.kinesis_enabled ?? false))
  }, [apiFetch])

  const toggleTelemetry = async () => {
    const action = telemetry ? 'stop' : 'start'
    setBusy('telemetry')
    await apiFetch('/demo/telemetry', 'POST', { action })
    setTelemetry(!telemetry)
    setBusy('')
  }

  return (
    <div className="bg-panel border border-border rounded px-4 py-3 space-y-2">
      <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Demo Controls</div>
      <div className="flex flex-wrap gap-2">
        <button
          onClick={toggleTelemetry}
          disabled={busy === 'telemetry' || telemetry === null}
          className={`text-xs px-3 py-1.5 rounded border transition disabled:opacity-40 ${
            telemetry
              ? 'border-red-600/50 text-red-400 hover:bg-red-600/10'
              : 'border-slate-600/50 text-slate-400 hover:bg-slate-600/10'
          }`}
        >
          {busy === 'telemetry' ? 'Updating...' : telemetry ? 'Stop Telemetry' : 'Start Telemetry'}
        </button>
        {telemetry !== null && (
          <span className={`self-center text-xs ${telemetry ? 'text-emerald-400' : 'text-slate-500'}`}>
            {telemetry ? '● Live telemetry running' : '○ Telemetry paused'}
          </span>
        )}
      </div>
    </div>
  )
}

export default function Dashboard({ onSignOut }: { onSignOut: () => void }) {
  const ws = useWebSocket()
  const { jobs, refresh: refreshJobs } = useSchedule()
  const [username, setUsername] = useState('')
  const [tab, setTab] = useState<Tab>('control')

  useEffect(() => {
    fetchUserAttributes().then(a => setUsername(a.email ?? a.preferred_username ?? ''))
  }, [])

  useEffect(() => {
    if (ws.scheduleUpdate) refreshJobs()
  }, [ws.scheduleUpdate, refreshJobs])

  const [countdown, setCountdown] = useState(10)
  const lastUpdateRef = useRef<number>(Date.now())

  // Reset countdown whenever tanks data updates
  useEffect(() => {
    lastUpdateRef.current = Date.now()
    setCountdown(10)
  }, [ws.tanks])

  // Tick every second
  useEffect(() => {
    const id = setInterval(() => {
      const elapsed = Math.floor((Date.now() - lastUpdateRef.current) / 1000)
      setCountdown(Math.max(0, 10 - elapsed))
    }, 1000)
    return () => clearInterval(id)
  }, [])

  const tankList        = Object.values(ws.tanks)
  const degraded        = tankList.filter(t => t.status !== 'online').length
  const avgJph          = tankList.length > 0
    ? Math.round(tankList.reduce((s, t) => s + (t.current_jph ?? 0), 0) / tankList.length)
    : 0
  const activeAnomalies = ws.anomalies.length

  return (
    <div className="min-h-screen bg-surface">
      {/* Top bar */}
      <header className="bg-panel border-b border-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <VeltrosLogo />
          <div>
            <div className="flex items-center gap-2">
              <span className="text-slate-200 font-bold tracking-wide text-sm">Veltros Motors</span>
              <span className="text-slate-600 text-xs">|</span>
              <span className="text-accent font-semibold tracking-widest uppercase text-sm">SPARK</span>
            </div>
            <div className="text-slate-500 text-[10px] tracking-wider">Smart Paint-shop Anomaly Response & Knowledge</div>
          </div>
          <span className={`flex items-center gap-1.5 text-xs ml-4 ${ws.connected ? 'text-emerald-400' : 'text-red-400'}`}>
            <span className={`w-1.5 h-1.5 rounded-full ${ws.connected ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
            {ws.connected ? 'Live' : 'Reconnecting...'}
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <span>{username}</span>
          <button
            onClick={() => signOut().then(onSignOut)}
            className="text-slate-500 hover:text-slate-200 transition"
          >
            Sign out
          </button>
        </div>
      </header>

      <main className="px-6 py-5 space-y-5">
        {/* Tab bar */}
        <div className="flex items-center justify-between border-b border-border pb-0">
          <div className="flex items-center gap-1">
            {(['control', 'diagnostics', 'incidents', 'history', 'telemetry'] as Tab[]).map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`px-4 py-2 text-xs font-medium uppercase tracking-wider transition border-b-2 -mb-px ${
                  t === 'telemetry'
                    ? tab === t
                      ? 'border-amber-500 text-amber-400'
                      : 'border-transparent text-amber-600/60 hover:text-amber-400'
                    : tab === t
                      ? 'border-accent text-accent'
                      : 'border-transparent text-slate-500 hover:text-slate-300'
                }`}
              >
                {t === 'control'     ? 'Control Center'  :
                 t === 'diagnostics' ? 'ML Diagnostics'  :
                 t === 'incidents'   ? 'Incidents'       :
                 t === 'history'     ? 'Sensor History'  :
                 '⚙ Live Telemetry'}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-2 pb-1 text-xs text-slate-500">
            <span>Next update in</span>
            <span className="font-mono text-slate-300 bg-slate-800 border border-border rounded px-2 py-0.5 w-8 text-center">
              {countdown}s
            </span>
            <div className="w-24 h-1 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-all duration-1000"
                style={{ width: `${(countdown / 10) * 100}%` }}
              />
            </div>
          </div>
        </div>

        {/* KPI row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricBadge label="Tanks Online"       value={tankList.length - degraded} unit={`/ ${tankList.length}`} />
          <MetricBadge label="Degraded / Offline" value={degraded} alert={degraded > 0} />
          <MetricBadge label="Avg JPH"            value={avgJph} unit="jobs/hr" alert={avgJph < 45 && avgJph > 0} />
          <MetricBadge label="Active Anomalies"   value={activeAnomalies} alert={activeAnomalies > 0} />
        </div>

        {tab === 'control' ? (
          <>
            {/* Tank grid (single health bar) + right panel */}
            <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
              <div className="xl:col-span-2 space-y-5">
                <TankGrid tanks={ws.tanks} onAnalyse={ws.sendStreamAgent} />
              </div>
              <div className="space-y-5">
                <AnomalyFeed anomalies={ws.anomalies} />
                <AgentPanel messages={ws.agentMessages} />
              </div>
            </div>
            {/* Schedule table */}
            <ScheduleTable jobs={jobs} latestUpdate={ws.scheduleUpdate} onRefresh={refreshJobs} />
          </>
        ) : tab === 'diagnostics' ? (
          /* ML Diagnostics — full 3-algorithm scores + sensor readings per tank */
          <TankGrid tanks={ws.tanks} onAnalyse={ws.sendStreamAgent} detailed />
        ) : tab === 'incidents' ? (
          <IncidentsList />
        ) : tab === 'telemetry' ? (
          <div className="space-y-5">
            <div className="bg-amber-950/30 border border-amber-800/40 rounded px-4 py-2 text-xs text-amber-500/80">
              ⚠ Demo simulation environment — this tab is not part of the production system
            </div>
            <DemoControls />
            <TelemetryView tanks={ws.tanks} />
          </div>
        ) : (
          <TankHistoryView tanks={ws.tanks} />
        )}
      </main>
    </div>
  )
}
