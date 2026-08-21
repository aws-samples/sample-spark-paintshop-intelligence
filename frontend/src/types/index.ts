export interface TankStatus {
  tank_id: string
  line_id: string
  status: 'online' | 'degraded' | 'offline'
  current_jph: number
  fault_type: string
  if_score: number
  lstm_score: number
  xgb_confidence: number
  sensors: Record<string, number>
  last_reading_ts: string
}

export interface Anomaly {
  tank_id: string
  fault_type: string
  if_score: number
  lstm_score: number
  breached_sensors: string[]
  jph_before: number
  timestamp: string
  scorer?: string
}

export interface ScheduleAssignment {
  job_id: string
  tank_id: string
  job_type: string
  scheduled_time: string
  status: string
  original_tank?: string | null
}

export interface ScheduleUpdate {
  tank_id: string
  projected_jph: number
  assignments: ScheduleAssignment[]
  fbo_delay_mins: number
  summary: string
  timestamp: string
}

export interface AgentMessage {
  id: string
  agent: 'mps' | 'rca'
  tank_id: string
  timestamp: string
  chunks: string[]
  result: Record<string, unknown> | null
  done: boolean
  error?: string
}

export interface AppConfig {
  userPoolId: string
  userPoolClientId: string
  identityPoolId: string
  wsEndpoint: string
  restApiEndpoint: string
  agentStreamUrl: string
  region: string
}

export interface IncidentAssignment {
  job_id: string
  action?: string
  new_tank?: string | null
  to_tank?: string | null
}

export interface Incident {
  incident_id: string
  timestamp: string
  tank_id: string
  fault_type: string
  anomaly_score: number
  line_id: string
  // MPS fields
  projected_jph: number
  fbo_delay_mins: number
  mps_summary: string
  supervisor_summary: string
  cascade_warning: string | null
  at_risk_tanks: string[]
  priority_notes: string
  assignments: IncidentAssignment[]
  mps_status: 'COMPLETE' | 'FALLBACK'
  // RCA fields — optional until rca_invoker writes
  rca_status: 'COMPLETE' | 'FALLBACK' | 'PENDING'
  severity?: string
  root_cause?: string
  recurrence_risk?: string
  recommendation?: string
  report_id?: string
}
