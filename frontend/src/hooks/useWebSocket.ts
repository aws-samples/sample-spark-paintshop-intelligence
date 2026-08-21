import { useEffect, useRef, useCallback, useState } from 'react'
import { fetchAuthSession } from 'aws-amplify/auth'
import type { TankStatus, Anomaly, ScheduleUpdate, AgentMessage } from '../types'
import { getConfig } from '../aws-config'

export interface WsState {
  connected: boolean
  tanks: Record<string, TankStatus>
  anomalies: Anomaly[]
  scheduleUpdate: ScheduleUpdate | null
  agentMessages: AgentMessage[]
  sendStreamAgent: (agent: 'mps' | 'rca', tankId: string, faultType: string, score: number) => void
}

export function useWebSocket(): WsState {
  const wsRef = useRef<WebSocket | null>(null)
  const [connected, setConnected]           = useState(false)
  const [tanks, setTanks]                   = useState<Record<string, TankStatus>>({})
  const [anomalies, setAnomalies]           = useState<Anomaly[]>([])
  const [scheduleUpdate, setScheduleUpdate] = useState<ScheduleUpdate | null>(null)
  const [agentMessages, setAgentMessages]   = useState<AgentMessage[]>([])

  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  const connect = useCallback(async () => {
    try {
      const cfg = getConfig()
      const session = await fetchAuthSession()
      const token = session.tokens?.accessToken?.toString() ?? ''
      const url = `${cfg.wsEndpoint}?token=${encodeURIComponent(token)}`

      const ws = new WebSocket(url)
      wsRef.current = ws

      ws.onopen = async () => {
        setConnected(true)
        // Seed initial tank state from REST so grid shows immediately
        try {
          const cfg = getConfig()
          const sess = await fetchAuthSession()
          const tok = sess.tokens?.idToken?.toString() ?? ''
          const r = await fetch(`${cfg.restApiEndpoint}/tanks`, {
            headers: { Authorization: `Bearer ${tok}` },
          })
          if (r.ok) {
            const data = await r.json()
            const initial: Record<string, TankStatus> = {}
            for (const t of (data.tanks ?? [])) initial[t.tank_id] = t
            setTanks(initial)
          }
        } catch { /* non-fatal */ }
      }

      ws.onclose = () => {
        setConnected(false)
        reconnectTimer.current = setTimeout(connect, 3000)
      }

      ws.onerror = () => ws.close()

      ws.onmessage = (evt) => {
        let msg: Record<string, unknown>
        try { msg = JSON.parse(evt.data) } catch { return }

        switch (msg.type) {
          case 'TANK_UPDATE':
            setTanks(prev => ({
              ...prev,
              [msg.tank_id as string]: msg as unknown as TankStatus,
            }))
            break

          case 'ANOMALY_ALERT':
            setAnomalies(prev => [msg as unknown as Anomaly, ...prev].slice(0, 50))
            break

          case 'SCHEDULE_UPDATE':
            setScheduleUpdate(msg as unknown as ScheduleUpdate)
            break

          case 'AGENT_STREAM_START': {
            const start: AgentMessage = {
              id:        `${msg.agent}-${msg.tank_id}-${msg.timestamp}`,
              agent:     msg.agent as 'mps' | 'rca',
              tank_id:   msg.tank_id as string,
              timestamp: msg.timestamp as string,
              chunks:    [],
              result:    null,
              done:      false,
            }
            setAgentMessages(prev => [start, ...prev].slice(0, 10))
            break
          }

          case 'AGENT_CHUNK':
            setAgentMessages(prev =>
              prev.map((m, i) =>
                i === 0 ? { ...m, chunks: [...m.chunks, msg.text as string] } : m
              )
            )
            break

          case 'AGENT_STREAM_DONE':
            setAgentMessages(prev =>
              prev.map((m, i) =>
                i === 0 ? { ...m, done: true, result: msg.result as Record<string, unknown> } : m
              )
            )
            break

          case 'AGENT_STREAM_ERROR':
            setAgentMessages(prev =>
              prev.map((m, i) =>
                i === 0 ? { ...m, done: true, error: msg.error as string } : m
              )
            )
            break
        }
      }
    } catch (err) {
      console.error('WS connect error', err)
      reconnectTimer.current = setTimeout(connect, 5000)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      reconnectTimer.current && clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const sendStreamAgent = useCallback(
    (agent: 'mps' | 'rca', tankId: string, faultType: string, score: number) => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({
          action:        'stream-agent',
          agent,
          tank_id:       tankId,
          fault_type:    faultType,
          anomaly_score: score,
        }))
      }
    },
    []
  )

  return { connected, tanks, anomalies, scheduleUpdate, agentMessages, sendStreamAgent }
}
