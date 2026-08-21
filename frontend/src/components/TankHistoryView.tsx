import { useState, useEffect, useCallback } from 'react'
import { fetchAuthSession } from 'aws-amplify/auth'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, Legend, ResponsiveContainer, ReferenceLine,
} from 'recharts'
import { getConfig } from '../aws-config'
import type { TankStatus } from '../types'

const TANK_NAMES: Record<string, string> = {
  'PT-01': 'Hot Pre-Clean',     'PT-02': 'Main Cleaner',
  'PT-03': 'Rinse 1',           'PT-04': 'Rinse 2',
  'PT-05': 'Activation',        'PT-06': 'Zinc Phosphate',
  'PT-07': 'Post-Rinse',        'PT-08': 'Nano-Seal',
  'ED-01': 'E-Coat Bath',       'ED-02': 'UF Rinse 1',
  'ED-03': 'UF Rinse 2',        'ED-04': 'DI Water Final Rinse',
}

const ALL_TANKS = [
  'PT-01','PT-02','PT-03','PT-04','PT-05','PT-06','PT-07','PT-08',
  'ED-01','ED-02','ED-03','ED-04',
]

// ML score metrics shown separately (right y-axis, 0–1 scale)
const ML_METRICS = new Set(['if_score', 'lstm_score', 'xgb_confidence'])

// Colour palette for up to 12 lines
const LINE_COLOURS = [
  '#58a6ff', '#3fb950', '#f0883e', '#bc8cff', '#ff7b72',
  '#e3b341', '#39d353', '#79c0ff', '#ffa657', '#d2a8ff',
  '#ff9bce', '#56d364',
]

interface Reading {
  time: string
  metric: string
  value: number
}

interface ChartPoint {
  t: string
  [metric: string]: number | string
}

interface Props {
  tanks: Record<string, TankStatus>
}

function useHistoryApi() {
  return useCallback(async (tankId: string, hours: number): Promise<Reading[]> => {
    const cfg     = getConfig()
    const session = await fetchAuthSession()
    const token   = session.tokens?.idToken?.toString() ?? ''
    const resp    = await fetch(
      `${cfg.restApiEndpoint}/tanks/${tankId}/history?hours=${hours}`,
      { headers: { Authorization: `Bearer ${token}` } },
    )
    const data = await resp.json()
    return data.readings ?? []
  }, [])
}

function pivot(readings: Reading[]): ChartPoint[] {
  // Group by timestamp, merge all metrics into one row
  const map = new Map<string, ChartPoint>()
  for (const r of readings) {
    const t = new Date(r.time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    if (!map.has(t)) map.set(t, { t })
    map.get(t)![r.metric] = r.value
  }
  // Sort ascending
  return Array.from(map.values()).sort((a, b) =>
    new Date(`1970/01/01 ${a.t}`).getTime() - new Date(`1970/01/01 ${b.t}`).getTime()
  )
}

export default function TankHistoryView({ tanks }: Props) {
  const [selectedTank, setSelectedTank] = useState('PT-06')
  const [hours, setHours]               = useState(6)
  const [readings, setReadings]         = useState<Reading[]>([])
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState('')
  const [visibleMetrics, setVisibleMetrics] = useState<Set<string>>(new Set())

  const fetchHistory = useHistoryApi()

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await fetchHistory(selectedTank, hours)
      setReadings(data)
      // Default: show sensor metrics only (hide ML scores initially)
      const metrics = Array.from(new Set(data.map(r => r.metric)))
        .filter(m => !ML_METRICS.has(m))
      setVisibleMetrics(new Set(metrics))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load history')
    } finally {
      setLoading(false)
    }
  }, [selectedTank, hours, fetchHistory])

  useEffect(() => { load() }, [load])

  const chartData = pivot(readings)
  const allMetrics = Array.from(new Set(readings.map(r => r.metric)))
  const sensorMetrics = allMetrics.filter(m => !ML_METRICS.has(m))
  const mlMetrics     = allMetrics.filter(m => ML_METRICS.has(m))

  const toggleMetric = (m: string) => {
    setVisibleMetrics(prev => {
      const next = new Set(prev)
      next.has(m) ? next.delete(m) : next.add(m)
      return next
    })
  }

  const currentTank = tanks[selectedTank]
  const statusColor =
    currentTank?.status === 'degraded' ? 'text-amber-400' :
    currentTank?.status === 'offline'  ? 'text-red-400'   : 'text-emerald-400'

  return (
    <div className="space-y-4">
      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Tank selector */}
        <div className="flex flex-wrap gap-1.5">
          {ALL_TANKS.map(tid => {
            const t = tanks[tid]
            const dot =
              t?.status === 'degraded' ? 'bg-amber-400' :
              t?.status === 'offline'  ? 'bg-red-400'   : 'bg-emerald-500'
            return (
              <button
                key={tid}
                onClick={() => setSelectedTank(tid)}
                className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-xs border transition ${
                  selectedTank === tid
                    ? 'border-accent bg-accent/10 text-accent font-semibold'
                    : 'border-border text-slate-400 hover:border-slate-500 hover:text-slate-200'
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
                {tid}
              </button>
            )
          })}
        </div>

        {/* Hour range */}
        <div className="flex items-center gap-1 ml-auto">
          {[1, 3, 6, 12, 24].map(h => (
            <button
              key={h}
              onClick={() => setHours(h)}
              className={`px-2.5 py-1 rounded text-xs border transition ${
                hours === h
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'border-border text-slate-500 hover:text-slate-300'
              }`}
            >
              {h}h
            </button>
          ))}
        </div>

        <button
          onClick={load}
          disabled={loading}
          className="px-3 py-1 rounded text-xs border border-border text-slate-400 hover:text-slate-200 disabled:opacity-40 transition"
        >
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Tank info banner */}
      <div className="bg-panel border border-border rounded px-4 py-2.5 flex items-center gap-4">
        <div>
          <span className="text-slate-200 font-semibold">{selectedTank}</span>
          <span className="text-slate-500 text-xs ml-2">{TANK_NAMES[selectedTank]}</span>
        </div>
        {currentTank && (
          <>
            <span className={`text-xs font-medium ${statusColor}`}>{currentTank.status}</span>
            {currentTank.fault_type && currentTank.fault_type !== 'normal' && (
              <span className="text-xs bg-amber-900/20 border border-amber-800 text-amber-400 rounded px-2 py-0.5">
                {currentTank.fault_type}
              </span>
            )}
            <span className="text-xs text-slate-500 ml-auto">
              Last reading: {currentTank.last_reading_ts
                ? new Date(currentTank.last_reading_ts).toLocaleTimeString()
                : '—'}
            </span>
          </>
        )}
      </div>

      {error && (
        <div className="bg-red-900/20 border border-red-800 text-red-400 rounded px-4 py-2 text-sm">{error}</div>
      )}

      {chartData.length === 0 && !loading && (
        <div className="bg-panel border border-border rounded flex items-center justify-center h-48 text-slate-500 text-sm">
          No history data yet — sensor readings accumulate in Timestream as telemetry runs.
        </div>
      )}

      {chartData.length > 0 && (
        <>
          {/* Sensor chart */}
          <div className="bg-panel border border-border rounded p-4">
            <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-3">
              Sensor Readings — last {hours}h
            </div>
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
                <XAxis
                  dataKey="t"
                  tick={{ fill: '#6e7681', fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: '#30363d' }}
                />
                <YAxis
                  tick={{ fill: '#6e7681', fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: '#30363d' }}
                  width={50}
                />
                <Tooltip
                  contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }}
                  labelStyle={{ color: '#8b949e' }}
                  itemStyle={{ color: '#c9d1d9' }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 11, color: '#8b949e', paddingTop: 8 }}
                />
                {sensorMetrics.map((m, i) =>
                  visibleMetrics.has(m) ? (
                    <Line
                      key={m}
                      type="monotone"
                      dataKey={m}
                      stroke={LINE_COLOURS[i % LINE_COLOURS.length]}
                      dot={false}
                      strokeWidth={1.8}
                      connectNulls
                    />
                  ) : null
                )}
                {/* Mark anomaly events with a reference line if status is degraded */}
                {currentTank?.status === 'degraded' && (
                  <ReferenceLine
                    x={chartData[chartData.length - 1]?.t}
                    stroke="#f0883e"
                    strokeDasharray="4 2"
                    label={{ value: 'Fault', fill: '#f0883e', fontSize: 10 }}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>

          {/* ML scores chart */}
          {mlMetrics.length > 0 && (
            <div className="bg-panel border border-border rounded p-4">
              <div className="text-xs text-slate-400 font-semibold uppercase tracking-wider mb-3">
                ML Anomaly Scores (0 – 1)
              </div>
              <ResponsiveContainer width="100%" height={160}>
                <LineChart data={chartData} margin={{ top: 4, right: 16, left: 0, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#21262d" />
                  <XAxis
                    dataKey="t"
                    tick={{ fill: '#6e7681', fontSize: 11 }}
                    tickLine={false}
                    axisLine={{ stroke: '#30363d' }}
                  />
                  <YAxis
                    domain={[0, 1]}
                    tick={{ fill: '#6e7681', fontSize: 11 }}
                    tickLine={false}
                    axisLine={{ stroke: '#30363d' }}
                    width={35}
                  />
                  <Tooltip
                    contentStyle={{ background: '#161b22', border: '1px solid #30363d', borderRadius: 6, fontSize: 12 }}
                    labelStyle={{ color: '#8b949e' }}
                    itemStyle={{ color: '#c9d1d9' }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11, color: '#8b949e', paddingTop: 8 }} />
                  <ReferenceLine y={0.5} stroke="#e3b341" strokeDasharray="4 2"
                    label={{ value: 'threshold', fill: '#e3b341', fontSize: 10, position: 'right' }} />
                  <Line key="if_score"       type="monotone" dataKey="if_score"       stroke="#58a6ff" dot={false} strokeWidth={1.8} connectNulls />
                  <Line key="lstm_score"     type="monotone" dataKey="lstm_score"     stroke="#bc8cff" dot={false} strokeWidth={1.8} connectNulls />
                  <Line key="xgb_confidence" type="monotone" dataKey="xgb_confidence" stroke="#f0883e" dot={false} strokeWidth={1.8} connectNulls />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}

          {/* Metric toggles */}
          <div className="bg-panel border border-border rounded px-4 py-3">
            <div className="text-xs text-slate-500 uppercase tracking-wider mb-2">Toggle Sensors</div>
            <div className="flex flex-wrap gap-2">
              {sensorMetrics.map((m, i) => (
                <button
                  key={m}
                  onClick={() => toggleMetric(m)}
                  className={`px-2.5 py-1 rounded text-xs border transition ${
                    visibleMetrics.has(m)
                      ? 'text-slate-100 border-transparent'
                      : 'text-slate-600 border-border'
                  }`}
                  style={visibleMetrics.has(m)
                    ? { borderColor: LINE_COLOURS[i % LINE_COLOURS.length], background: LINE_COLOURS[i % LINE_COLOURS.length] + '22' }
                    : {}}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  )
}
