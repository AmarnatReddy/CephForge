import { useQuery } from '@tanstack/react-query'
import {
  Server,
  Monitor,
  Activity,
  CheckCircle,
  AlertTriangle,
  XCircle,
  TrendingUp,
  Zap,
  Clock,
} from 'lucide-react'
import { api } from '../lib/api'
import MetricCard from '../components/MetricCard'
import RecentExecutions from '../components/RecentExecutions'

export default function Dashboard() {
  const { data: system } = useQuery({
    queryKey: ['system', 'health'],
    queryFn: () => api.get('/api/v1/system/health'),
  })

  const { data: clients } = useQuery({
    queryKey: ['clients'],
    queryFn: () => api.get('/api/v1/clients/'),
  })

  const { data: executions } = useQuery({
    queryKey: ['executions'],
    queryFn: () => api.get('/api/v1/executions/?limit=5'),
  })

  const { data: clusters } = useQuery({
    queryKey: ['clusters'],
    queryFn: () => api.get('/api/v1/clusters/'),
  })

  const activeExecution = executions?.executions?.find(
    (e: any) => e.status === 'running'
  )

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="font-display text-3xl font-bold text-white mb-2">
          Dashboard
        </h1>
        <p className="text-dark-400">
          Scale Testing Framework - Overview
        </p>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <MetricCard
          title="Clusters"
          value={clusters?.total ?? 0}
          icon={Server}
          color="purple"
          subtitle="Storage clusters"
        />
        <MetricCard
          title="Clients"
          value={clients?.online ?? 0}
          total={clients?.total ?? 0}
          icon={Monitor}
          color="blue"
          subtitle="Online clients"
        />
        <MetricCard
          title="Executions"
          value={executions?.executions?.filter((e: any) => e.status === 'completed').length ?? 0}
          total={executions?.total ?? 0}
          icon={Activity}
          color="emerald"
          subtitle="Completed runs"
        />
        <MetricCard
          title="System"
          value={system?.status === 'healthy' ? 'Healthy' : 'Degraded'}
          icon={system?.status === 'healthy' ? CheckCircle : AlertTriangle}
          color={system?.status === 'healthy' ? 'emerald' : 'amber'}
          subtitle="System status"
        />
      </div>

      {/* Active Execution Banner */}
      {activeExecution && (
        <div className="mb-8 card p-6 border-primary-500/30 animate-pulse-glow">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <div className="w-12 h-12 rounded-xl bg-primary-500/20 flex items-center justify-center">
                <Zap className="w-6 h-6 text-primary-400 animate-pulse" />
              </div>
              <div>
                <h3 className="font-display font-semibold text-lg text-white">
                  Execution Running
                </h3>
                <p className="text-dark-400 text-sm">
                  {activeExecution.name} • {activeExecution.id}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-8">
              <div className="text-center">
                <p className="text-2xl font-bold text-primary-400">
                  {activeExecution.total_iops?.toLocaleString() ?? '—'}
                </p>
                <p className="text-xs text-dark-400">IOPS</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-emerald-400">
                  {activeExecution.total_throughput_mbps?.toFixed(1) ?? '—'} MB/s
                </p>
                <p className="text-xs text-dark-400">Throughput</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold text-amber-400">
                  {activeExecution.avg_latency_us?.toFixed(1) ?? '—'} µs
                </p>
                <p className="text-xs text-dark-400">Latency</p>
              </div>
              <a
                href={`/executions/${activeExecution.id}`}
                className="px-6 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors"
              >
                View Details
              </a>
            </div>
          </div>
        </div>
      )}

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Executions */}
        <div className="lg:col-span-2">
          <RecentExecutions executions={executions?.executions ?? []} />
        </div>

        {/* Quick Actions */}
        <div className="card p-6">
          <h3 className="font-display font-semibold text-lg text-white mb-4">
            Quick Actions
          </h3>
          <div className="space-y-3">
            <a
              href="/executions"
              className="flex items-center gap-3 p-4 rounded-lg bg-dark-800/50 hover:bg-dark-800 transition-colors"
            >
              <div className="w-10 h-10 rounded-lg bg-primary-500/20 flex items-center justify-center">
                <Activity className="w-5 h-5 text-primary-400" />
              </div>
              <div>
                <p className="font-medium text-white">New Execution</p>
                <p className="text-sm text-dark-400">Start a new test run</p>
              </div>
            </a>
            <a
              href="/clients"
              className="flex items-center gap-3 p-4 rounded-lg bg-dark-800/50 hover:bg-dark-800 transition-colors"
            >
              <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                <Monitor className="w-5 h-5 text-blue-400" />
              </div>
              <div>
                <p className="font-medium text-white">Check Clients</p>
                <p className="text-sm text-dark-400">View client health</p>
              </div>
            </a>
            <a
              href="/workloads"
              className="flex items-center gap-3 p-4 rounded-lg bg-dark-800/50 hover:bg-dark-800 transition-colors"
            >
              <div className="w-10 h-10 rounded-lg bg-emerald-500/20 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-emerald-400" />
              </div>
              <div>
                <p className="font-medium text-white">Workload Templates</p>
                <p className="text-sm text-dark-400">Browse & create workloads</p>
              </div>
            </a>
          </div>
        </div>
      </div>
    </div>
  )
}
