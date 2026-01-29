import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Activity, Plus, CheckCircle, XCircle, Clock, Loader2, AlertCircle, AlertTriangle } from 'lucide-react'
import { api } from '../lib/api'
import Modal from '../components/Modal'

const statusConfig = {
  completed: { icon: CheckCircle, color: 'text-emerald-400', bg: 'bg-emerald-500/20' },
  failed: { icon: XCircle, color: 'text-red-400', bg: 'bg-red-500/20' },
  running: { icon: Loader2, color: 'text-blue-400', bg: 'bg-blue-500/20', animate: true },
  pending: { icon: Clock, color: 'text-amber-400', bg: 'bg-amber-500/20' },
  cancelled: { icon: AlertCircle, color: 'text-dark-400', bg: 'bg-dark-500/20' },
  prechecks: { icon: Loader2, color: 'text-purple-400', bg: 'bg-purple-500/20', animate: true },
  preparing: { icon: Loader2, color: 'text-cyan-400', bg: 'bg-cyan-500/20', animate: true },
}

function formatDuration(seconds: number): string {
  if (!seconds) return '—'
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
  const hours = Math.floor(seconds / 3600)
  const mins = Math.floor((seconds % 3600) / 60)
  return `${hours}h ${mins}m`
}

export default function Executions() {
  const queryClient = useQueryClient()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [selectedWorkload, setSelectedWorkload] = useState('')
  const [executionName, setExecutionName] = useState('')
  const [runPrechecks, setRunPrechecks] = useState(true)

  const { data, isLoading, error } = useQuery({
    queryKey: ['executions'],
    queryFn: () => api.get('/api/v1/executions/?limit=50'),
  })

  const { data: workloads } = useQuery({
    queryKey: ['workloads'],
    queryFn: () => api.get('/api/v1/workloads/'),
  })

  const startMutation = useMutation({
    mutationFn: (payload: any) => api.post('/api/v1/executions/', payload),
    onSuccess: (response) => {
      queryClient.invalidateQueries({ queryKey: ['executions'] })
      setIsModalOpen(false)
      window.location.href = `/executions/${response.execution_id}`
    },
  })

  const handleStartExecution = (e: React.FormEvent) => {
    e.preventDefault()
    startMutation.mutate({
      workload_name: selectedWorkload,
      name: executionName || undefined,
      run_prechecks: runPrechecks,
    })
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold text-white mb-2">
            Executions
          </h1>
          <p className="text-dark-400">
            View and manage test executions
          </p>
        </div>
        <button 
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Execution
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full" />
        </div>
      ) : error ? (
        <div className="card p-8 text-center text-red-400">
          <AlertTriangle className="w-12 h-12 mx-auto mb-4" />
          <p>Failed to load executions</p>
        </div>
      ) : data?.executions?.length === 0 ? (
        <div className="card p-16 text-center">
          <Activity className="w-16 h-16 mx-auto mb-4 text-dark-500" />
          <h3 className="text-xl font-display font-semibold text-white mb-2">
            No executions yet
          </h3>
          <p className="text-dark-400 mb-6">
            Start your first test execution
          </p>
          <button 
            onClick={() => setIsModalOpen(true)}
            className="px-6 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors"
          >
            Start First Execution
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-dark-700/50">
                <th className="text-left p-4 text-sm font-medium text-dark-400">Status</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Name</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Workload</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Clients</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">IOPS</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Throughput</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Latency</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Duration</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Started</th>
              </tr>
            </thead>
            <tbody>
              {data.executions.map((exec: any) => {
                const status = statusConfig[exec.status as keyof typeof statusConfig] || statusConfig.pending
                const StatusIcon = status.icon

                return (
                  <tr
                    key={exec.id}
                    className="border-b border-dark-700/30 hover:bg-dark-800/30 transition-colors cursor-pointer"
                    onClick={() => window.location.href = `/executions/${exec.id}`}
                  >
                    <td className="p-4">
                      <div className="flex items-center gap-2">
                        <StatusIcon
                          className={`w-4 h-4 ${status.color} ${(status as any).animate ? 'animate-spin' : ''}`}
                        />
                        <span className={`px-2 py-0.5 rounded text-xs ${status.bg} ${status.color}`}>
                          {exec.status}
                        </span>
                      </div>
                    </td>
                    <td className="p-4">
                      <div>
                        <p className="font-medium text-white">{exec.name}</p>
                        <p className="text-xs text-dark-500 font-mono">{exec.id}</p>
                        {exec.status === 'failed' && exec.error_message && (
                          <p className="text-xs text-red-400 mt-1 truncate max-w-xs" title={exec.error_message}>
                            Error: {exec.error_message.slice(0, 50)}...
                          </p>
                        )}
                      </div>
                    </td>
                    <td className="p-4 text-dark-300">{exec.workload_type || '—'}</td>
                    <td className="p-4 text-white">{exec.client_count || '—'}</td>
                    <td className="p-4 text-white font-mono">
                      {exec.total_iops?.toLocaleString() || '—'}
                    </td>
                    <td className="p-4 text-white font-mono">
                      {exec.total_throughput_mbps?.toFixed(1) || '—'} MB/s
                    </td>
                    <td className="p-4 text-white font-mono">
                      {exec.avg_latency_us?.toFixed(1) || '—'} µs
                    </td>
                    <td className="p-4 text-dark-300">
                      {formatDuration(exec.duration_seconds)}
                    </td>
                    <td className="p-4 text-dark-400 text-sm">
                      {exec.started_at
                        ? new Date(exec.started_at).toLocaleString()
                        : '—'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* New Execution Modal */}
      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title="Start New Execution" size="md">
        <form onSubmit={handleStartExecution} className="space-y-4">
          <div>
            <label className="block text-sm text-dark-400 mb-1">Select Workload *</label>
            <select
              value={selectedWorkload}
              onChange={(e) => setSelectedWorkload(e.target.value)}
              className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
              required
            >
              <option value="">Choose a workload...</option>
              {workloads?.workloads?.map((w: any) => (
                <option key={w.name} value={w.name}>
                  {w.name} {w._is_template ? '(template)' : ''}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-sm text-dark-400 mb-1">Execution Name (optional)</label>
            <input
              type="text"
              value={executionName}
              onChange={(e) => setExecutionName(e.target.value)}
              className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
              placeholder="Leave empty to auto-generate"
            />
          </div>

          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={runPrechecks}
                onChange={(e) => setRunPrechecks(e.target.checked)}
                className="w-4 h-4 rounded border-dark-700 bg-dark-800 text-primary-500 focus:ring-primary-500"
              />
              <span className="text-sm text-white">Run prechecks before starting</span>
            </label>
          </div>

          <div className="flex justify-end gap-3 pt-4 border-t border-dark-700/50">
            <button
              type="button"
              onClick={() => setIsModalOpen(false)}
              className="px-4 py-2 text-dark-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={startMutation.isPending || !selectedWorkload}
              className="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              {startMutation.isPending ? 'Starting...' : 'Start Execution'}
            </button>
          </div>

          {startMutation.isError && (
            <p className="text-red-400 text-sm">
              Failed to start execution: {(startMutation.error as Error).message}
            </p>
          )}
        </form>
      </Modal>
    </div>
  )
}
