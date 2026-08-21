import { useState } from 'react'
import type { ScheduleAssignment, ScheduleUpdate } from '../types'

interface Props {
  jobs: ScheduleAssignment[]
  latestUpdate: ScheduleUpdate | null
  onRefresh: () => Promise<void>
}

const STATUS_COLORS: Record<string, string> = {
  IN_PROGRESS: 'text-emerald-400',
  QUEUED:      'text-amber-400',
  RESCHEDULED: 'text-accent',
  COMPLETED:   'text-slate-500',
}

export default function ScheduleTable({ jobs, latestUpdate, onRefresh }: Props) {
  const [refreshing, setRefreshing] = useState(false)

  async function handleRefresh() {
    setRefreshing(true)
    await onRefresh()
    setRefreshing(false)
  }

  return (
    <div className="panel space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="text-xs text-slate-400 uppercase tracking-wider font-semibold">
            Production Schedule
          </div>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            title="Refresh schedule"
            className="text-slate-500 hover:text-slate-300 disabled:opacity-40 transition-colors"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              viewBox="0 0 20 20"
              fill="currentColor"
              className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`}
            >
              <path fillRule="evenodd" d="M15.312 11.424a5.5 5.5 0 0 1-9.201 2.466l-.312-.311h2.433a.75.75 0 0 0 0-1.5H3.989a.75.75 0 0 0-.75.75v4.242a.75.75 0 0 0 1.5 0v-2.43l.31.31a7 7 0 0 0 11.712-3.138.75.75 0 0 0-1.449-.39Zm1.23-3.723a.75.75 0 0 0 .219-.53V2.929a.75.75 0 0 0-1.5 0V5.36l-.31-.31A7 7 0 0 0 3.239 8.188a.75.75 0 1 0 1.448.389A5.5 5.5 0 0 1 13.89 6.11l.311.31h-2.432a.75.75 0 0 0 0 1.5h4.243a.75.75 0 0 0 .53-.219Z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
        {latestUpdate && (
          <div className="text-xs text-slate-500">
            Last updated: {new Date(latestUpdate.timestamp).toLocaleTimeString()}
            {' · '}
            <span className="text-accent">{latestUpdate.projected_jph} JPH</span>
          </div>
        )}
      </div>

      {latestUpdate?.summary && (
        <div className="text-xs text-amber-300 bg-amber-900/20 border border-amber-800/50 rounded px-2 py-1.5">
          {latestUpdate.summary}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-slate-500 border-b border-border">
              <th className="text-left py-1.5 pr-3">Job ID</th>
              <th className="text-left py-1.5 pr-3">Tank</th>
              <th className="text-left py-1.5 pr-3">Type</th>
              <th className="text-left py-1.5 pr-3">Scheduled</th>
              <th className="text-left py-1.5 pr-3">Status</th>
              <th className="text-left py-1.5">Moved From</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {jobs.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-slate-600 text-center py-6">No active jobs</td>
              </tr>
            ) : (
              jobs.map(job => (
                <tr key={job.job_id + job.status}
                    className={`hover:bg-slate-800/30 ${job.status === 'RESCHEDULED' ? 'bg-amber-900/10' : ''}`}>
                  <td className="py-1.5 pr-3 text-slate-300 font-mono">{job.job_id}</td>
                  <td className="py-1.5 pr-3 text-slate-300">{job.tank_id}</td>
                  <td className="py-1.5 pr-3 text-slate-400">{job.job_type}</td>
                  <td className="py-1.5 pr-3 text-slate-400">
                    {new Date(job.scheduled_time).toLocaleTimeString()}
                  </td>
                  <td className={`py-1.5 pr-3 ${STATUS_COLORS[job.status] ?? 'text-slate-400'}`}>
                    {job.status}
                  </td>
                  <td className="py-1.5">
                    {job.original_tank ? (
                      <span className="text-amber-400 font-mono">
                        {job.original_tank} → {job.tank_id}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
