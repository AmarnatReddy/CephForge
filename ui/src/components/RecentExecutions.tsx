import { CheckCircle, XCircle, Clock, Loader2, AlertCircle } from 'lucide-react'

interface Execution {
  id: string
  name: string
  status: string
  started_at: string
  completed_at: string
  duration_seconds: number
  client_count: number
  total_iops: number
  avg_latency_us: number
  total_throughput_mbps: number
}

interface RecentExecutionsProps {
  executions: Execution[]
}

const statusConfig = {
  completed: {
    icon: CheckCircle,
    color: 'text-emerald-400',
    bg: 'bg-emerald-500/20',
    label: 'Completed',
  },
  failed: {
    icon: XCircle,
    color: 'text-red-400',
    bg: 'bg-red-500/20',
    label: 'Failed',
  },
  running: {
    icon: Loader2,
    color: 'text-blue-400',
    bg: 'bg-blue-500/20',
    label: 'Running',
    animate: true,
  },
  pending: {
    icon: Clock,
    color: 'text-amber-400',
    bg: 'bg-amber-500/20',
    label: 'Pending',
  },
  cancelled: {
    icon: AlertCircle,
    color: 'text-dark-400',
    bg: 'bg-dark-500/20',
    label: 'Cancelled',
  },
}

function formatDuration(seconds: number): string {
  if (!seconds) return '—'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m`
}

function formatNumber(num: number): string {
  if (!num) return '—'
  if (num >= 1000000) return `${(num / 1000000).toFixed(1)}M`
  if (num >= 1000) return `${(num / 1000).toFixed(1)}K`
  return num.toString()
}

export default function RecentExecutions({ executions }: RecentExecutionsProps) {
  return (
    <div className="card p-6">
      <div className="flex items-center justify-between mb-6">
        <h3 className="font-display font-semibold text-lg text-white">
          Recent Executions
        </h3>
        <a
          href="/executions"
          className="text-sm text-primary-400 hover:text-primary-300 transition-colors"
        >
          View all →
        </a>
      </div>

      {(!executions || executions.length === 0) ? (
        <div className="text-center py-8 text-dark-400">
          <Clock className="w-12 h-12 mx-auto mb-3 opacity-50" />
          <p>No executions yet</p>
          <p className="text-sm">Start a new execution to see results here</p>
        </div>
      ) : (
        <div className="space-y-3">
          {executions.map((exec) => {
            const status = statusConfig[exec.status as keyof typeof statusConfig] || statusConfig.pending
            const StatusIcon = status.icon

            return (
              <a
                key={exec.id}
                href={`/executions/${exec.id}`}
                className="flex items-center gap-4 p-4 rounded-lg bg-dark-800/50 hover:bg-dark-800 transition-colors group"
              >
                <div className={`w-10 h-10 rounded-lg ${status.bg} flex items-center justify-center`}>
                  <StatusIcon
                    className={`w-5 h-5 ${status.color} ${(status as any).animate ? 'animate-spin' : ''}`}
                  />
                </div>

                <div className="flex-1 min-w-0">
                  <p className="font-medium text-white truncate group-hover:text-primary-400 transition-colors">
                    {exec.name}
                  </p>
                  <p className="text-sm text-dark-400 truncate">
                    {exec.id}
                  </p>
                </div>

                <div className="hidden md:flex items-center gap-6 text-sm">
                  <div className="text-center">
                    <p className="text-white font-medium">{formatNumber(exec.total_iops)}</p>
                    <p className="text-dark-500 text-xs">IOPS</p>
                  </div>
                  <div className="text-center">
                    <p className="text-white font-medium">
                      {exec.total_throughput_mbps?.toFixed(1) || '—'}
                    </p>
                    <p className="text-dark-500 text-xs">MB/s</p>
                  </div>
                  <div className="text-center">
                    <p className="text-white font-medium">{exec.client_count || '—'}</p>
                    <p className="text-dark-500 text-xs">Clients</p>
                  </div>
                  <div className="text-center min-w-[60px]">
                    <p className="text-white font-medium">
                      {formatDuration(exec.duration_seconds)}
                    </p>
                    <p className="text-dark-500 text-xs">Duration</p>
                  </div>
                </div>

                <div className={`px-3 py-1 rounded-full ${status.bg} ${status.color} text-xs font-medium`}>
                  {status.label}
                </div>
              </a>
            )
          })}
        </div>
      )}
    </div>
  )
}
