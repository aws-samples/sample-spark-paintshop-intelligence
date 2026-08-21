import { useState, useEffect, useCallback } from 'react'
import { fetchAuthSession } from 'aws-amplify/auth'
import type { TankStatus, ScheduleAssignment } from '../types'
import { getConfig } from '../aws-config'

async function apiFetch<T>(path: string): Promise<T> {
  const cfg = getConfig()
  const session = await fetchAuthSession()
  const token = session.tokens?.idToken?.toString() ?? ''
  const resp = await fetch(`${cfg.restApiEndpoint}${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!resp.ok) throw new Error(`API error ${resp.status}`)
  return resp.json()
}

export function useTanks() {
  const [tanks, setTanks]     = useState<TankStatus[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await apiFetch<{ tanks: TankStatus[] }>('/tanks')
      setTanks(data.tanks ?? [])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])
  return { tanks, loading, refresh }
}

export function useSchedule() {
  const [jobs, setJobs]       = useState<ScheduleAssignment[]>([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const data = await apiFetch<{ jobs: ScheduleAssignment[] }>('/schedule')
      setJobs(data.jobs ?? [])
    } catch (err) {
      console.error('useSchedule fetch error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 30_000)
    return () => clearInterval(id)
  }, [refresh])
  return { jobs, loading, refresh }
}
