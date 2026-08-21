import { useEffect, useState, useCallback } from 'react'
import { fetchAuthSession } from 'aws-amplify/auth'
import { getConfig } from '../aws-config'
import type { Incident } from '../types'
import IncidentCard from './IncidentCard'

export default function IncidentsList() {
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading]     = useState(true)
  const [error, setError]         = useState<string | null>(null)

  const fetchIncidents = useCallback(async () => {
    try {
      const cfg     = getConfig()
      const session = await fetchAuthSession()
      const token   = session.tokens?.idToken?.toString() ?? ''
      const resp    = await fetch(`${cfg.restApiEndpoint}/incidents?days=7`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`)
      const data = await resp.json()
      setIncidents(data.incidents ?? [])
      setError(null)
    } catch (e) {
      console.error('[IncidentsList] fetch failed:', e)
      setError('Failed to load incidents')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchIncidents()
    const id = setInterval(fetchIncidents, 30_000)
    return () => clearInterval(id)
  }, [fetchIncidents])

  if (loading) {
    return (
      <div className="panel flex items-center justify-center h-40 text-slate-500 text-sm">
        Loading incidents...
      </div>
    )
  }

  if (error && incidents.length === 0) {
    return (
      <div className="panel flex items-center justify-center h-40 text-red-400 text-sm">
        {error}
      </div>
    )
  }

  if (incidents.length === 0) {
    return (
      <div className="panel flex items-center justify-center h-40 text-slate-500 text-sm">
        No incidents in the last 7 days
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
          Incidents · Last 7 days
        </span>
        <span className="text-xs text-slate-600">{incidents.length} total</span>
      </div>
      {incidents.map(incident => (
        <IncidentCard key={incident.incident_id} incident={incident} />
      ))}
    </div>
  )
}
