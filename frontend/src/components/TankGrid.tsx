import type { TankStatus } from '../types'
import TankCard from './TankCard'

interface Props {
  tanks: Record<string, TankStatus>
  onAnalyse: (agent: 'mps' | 'rca', tankId: string, faultType: string, score: number) => void
  detailed?: boolean
}

function TankSection({ title, subtitle, tanks, onAnalyse, detailed }: {
  title: string; subtitle: string; tanks: TankStatus[]
  onAnalyse: Props['onAnalyse']
  detailed?: boolean
}) {
  if (tanks.length === 0) return null
  return (
    <div className="space-y-2">
      <div className="flex items-baseline gap-2">
        <span className="text-slate-300 text-xs font-semibold uppercase tracking-widest">{title}</span>
        <span className="text-slate-600 text-xs">{subtitle}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-4 gap-3">
        {tanks.map(tank => (
          <TankCard
            key={tank.tank_id}
            tank={tank}
            detailed={detailed}
            onAnalyse={(agent) =>
              onAnalyse(agent, tank.tank_id, tank.fault_type ?? '', Math.max(tank.if_score ?? 0, tank.lstm_score ?? 0))
            }
          />
        ))}
      </div>
    </div>
  )
}

export default function TankGrid({ tanks, onAnalyse, detailed = false }: Props) {
  const sorted = Object.values(tanks).sort((a, b) => {
    const order = { offline: 0, degraded: 1, online: 2 }
    return (order[a.status] ?? 3) - (order[b.status] ?? 3)
  })

  if (sorted.length === 0) {
    return (
      <div className="panel flex items-center justify-center h-40 text-slate-500">
        Waiting for tank telemetry...
      </div>
    )
  }

  const ptTanks = sorted.filter(t => t.tank_id.startsWith('PT'))
  const edTanks = sorted.filter(t => t.tank_id.startsWith('ED'))

  return (
    <div className="space-y-5">
      <TankSection
        title="Pre-Treatment"
        subtitle="PT-01 – PT-08 · Cleaning & Phosphating"
        tanks={ptTanks}
        onAnalyse={onAnalyse}
        detailed={detailed}
      />
      <TankSection
        title="ElectroDeposition"
        subtitle="ED-01 – ED-04 · E-Coat Priming"
        tanks={edTanks}
        onAnalyse={onAnalyse}
        detailed={detailed}
      />
    </div>
  )
}
