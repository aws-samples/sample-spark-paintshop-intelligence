import type { Anomaly } from '../types'

interface Props {
  anomalies: Anomaly[]
}

export default function AnomalyFeed({ anomalies }: Props) {
  return (
    <div className="panel space-y-2">
      <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold mb-3">
        Anomaly Feed
        {anomalies.length > 0 && (
          <span className="ml-2 bg-red-900/50 text-red-400 border border-red-700 rounded-full px-2 py-0.5">
            {anomalies.length}
          </span>
        )}
      </div>

      {anomalies.length === 0 ? (
        <div className="text-slate-600 text-xs text-center py-6">No anomalies detected</div>
      ) : (
        <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
          {anomalies.map((a, i) => (
            <div
              key={`${a.tank_id}-${a.timestamp}-${i}`}
              className="bg-red-950/30 border border-red-900/50 rounded p-2 space-y-1"
            >
              <div className="flex items-center justify-between">
                <span className="text-red-400 font-semibold text-xs">{a.tank_id}</span>
                <span className="text-slate-500 text-xs">
                  {new Date(a.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div className="text-slate-300 text-xs">{a.fault_type}</div>
              <div className="flex gap-3 text-xs text-slate-400">
                <span>IF: <span className="text-amber-400">{a.if_score.toFixed(3)}</span></span>
                <span>LSTM: <span className="text-amber-400">{a.lstm_score.toFixed(3)}</span></span>
                <span>JPH before: <span className="text-slate-300">{a.jph_before}</span></span>
              </div>
              {a.scorer && (
                <div className="text-[10px]">
                  <span className={`px-1.5 py-0.5 rounded border ${
                    a.scorer === 'sagemaker_mce_v1'
                      ? 'bg-emerald-900/30 border-emerald-700 text-emerald-400'
                      : 'bg-slate-800 border-slate-600 text-slate-400'
                  }`}>
                    {a.scorer}
                  </span>
                </div>
              )}
              {a.breached_sensors?.length > 0 && (
                <div className="flex flex-wrap gap-1">
                  {a.breached_sensors.map((s, si) => {
                    const name = typeof s === 'string' ? s : (s as Record<string, unknown>).sensor as string
                    const dir  = typeof s === 'object' ? (s as Record<string, unknown>).direction as string : ''
                    return (
                      <span key={si} className={`text-xs px-1.5 py-0.5 rounded ${dir === 'high' ? 'bg-red-900/40 text-red-300' : dir === 'low' ? 'bg-amber-900/40 text-amber-300' : 'bg-slate-800 text-slate-300'}`}>
                        {name} {dir ? `(${dir})` : ''}
                      </span>
                    )
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
