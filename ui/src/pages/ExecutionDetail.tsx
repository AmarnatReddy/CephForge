import { useParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  ArrowLeft,
  Play,
  Pause,
  Square,
  RefreshCw,
  CheckCircle,
  XCircle,
  Clock,
  Loader2,
  Activity,
  Zap,
  Timer,
  Users,
  AlertTriangle,
  TrendingUp,
  Target,
} from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts'
import { api } from '../lib/api'

export default function ExecutionDetail() {
  const { id } = useParams<{ id: string }>()
  const queryClient = useQueryClient()

  const { data: execution, isLoading } = useQuery({
    queryKey: ['execution', id],
    queryFn: () => api.get(`/api/v1/executions/${id}/`),
    refetchInterval: (query) => {
      const data = query.state.data as any
      return data?.status === 'running' ? 2000 : false
    },
  })

  const { data: metrics } = useQuery({
    queryKey: ['metrics', id],
    queryFn: () => api.get(`/api/v1/metrics/${id}/latest/?count=120`),
    enabled: !!execution,
    refetchInterval: execution?.status === 'running' ? 2000 : false,
  })

  const { data: commandsData } = useQuery({
    queryKey: ['commands', id],
    queryFn: () => api.get(`/api/v1/executions/${id}/commands`),
    enabled: !!execution && execution?.status !== 'running',
  })

  // Use stored network baseline from execution, or fetch fresh if not available
  const { data: networkSuggestions } = useQuery({
    queryKey: ['network-suggestions', execution?.cluster_name],
    queryFn: () => api.get(`/api/v1/network/suggestions/${execution?.cluster_name}`),
    // Only fetch if no stored baseline and execution is completed
    enabled: !!execution?.cluster_name && execution?.status === 'completed' && !execution?.network_baseline,
  })
  
  // Prefer stored network baseline, fall back to fresh fetch
  const networkBaseline = execution?.network_baseline || networkSuggestions?.suggestions

  const stopMutation = useMutation({
    mutationFn: () => api.post(`/api/v1/executions/${id}/stop/`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['execution', id] }),
  })

  const pauseMutation = useMutation({
    mutationFn: () => api.post(`/api/v1/executions/${id}/pause/`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['execution', id] }),
  })

  const resumeMutation = useMutation({
    mutationFn: () => api.post(`/api/v1/executions/${id}/resume/`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['execution', id] }),
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <div className="animate-spin w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full" />
      </div>
    )
  }

  if (!execution) {
    return (
      <div className="p-8">
        <div className="card p-16 text-center">
          <AlertTriangle className="w-16 h-16 mx-auto mb-4 text-amber-400" />
          <h3 className="text-xl font-display font-semibold text-white mb-2">
            Execution not found
          </h3>
          <a href="/executions" className="text-primary-400 hover:text-primary-300">
            ← Back to executions
          </a>
        </div>
      </div>
    )
  }

  const isRunning = execution.status === 'running' || execution.status === 'paused'

  // Process metrics for charts
  const chartData = (metrics?.metrics || []).map((m: any, i: number) => ({
    time: i,
    iops: (m.iops?.r || 0) + (m.iops?.w || 0),
    readIops: m.iops?.r || 0,
    writeIops: m.iops?.w || 0,
    throughput: (m.bw_mbps?.r || 0) + (m.bw_mbps?.w || 0),
    latency: m.lat_us?.avg || 0,
  }))

  return (
    <div className="p-8">
      {/* Header */}
      <div className="flex items-center gap-4 mb-8">
        <a
          href="/executions"
          className="p-2 hover:bg-dark-800 rounded-lg transition-colors text-dark-400 hover:text-white"
        >
          <ArrowLeft className="w-5 h-5" />
        </a>
        <div className="flex-1">
          <h1 className="font-display text-2xl font-bold text-white">
            {execution.name}
          </h1>
          <p className="text-dark-400 font-mono text-sm">{id}</p>
        </div>
        {isRunning && (
          <div className="flex items-center gap-2">
            {execution.status === 'running' ? (
              <button
                onClick={() => pauseMutation.mutate()}
                disabled={pauseMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 rounded-lg font-medium transition-colors"
              >
                <Pause className="w-4 h-4" />
                Pause
              </button>
            ) : (
              <button
                onClick={() => resumeMutation.mutate()}
                disabled={resumeMutation.isPending}
                className="flex items-center gap-2 px-4 py-2 bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 rounded-lg font-medium transition-colors"
              >
                <Play className="w-4 h-4" />
                Resume
              </button>
            )}
            <button
              onClick={() => stopMutation.mutate()}
              disabled={stopMutation.isPending}
              className="flex items-center gap-2 px-4 py-2 bg-red-500/20 text-red-400 hover:bg-red-500/30 rounded-lg font-medium transition-colors"
            >
              <Square className="w-4 h-4" />
              Stop
            </button>
          </div>
        )}
      </div>

      {/* Status & Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4 mb-8">
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            {execution.status === 'running' ? (
              <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
            ) : execution.status === 'completed' ? (
              <CheckCircle className="w-4 h-4 text-emerald-400" />
            ) : execution.status === 'failed' ? (
              <XCircle className="w-4 h-4 text-red-400" />
            ) : (
              <Clock className="w-4 h-4 text-amber-400" />
            )}
            <span className="text-sm text-dark-400">Status</span>
          </div>
          <p className={`text-lg font-bold capitalize ${
            execution.status === 'failed' ? 'text-red-400' : 
            execution.status === 'completed' ? 'text-emerald-400' : 'text-white'
          }`}>{execution.status}</p>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Zap className="w-4 h-4 text-primary-400" />
            <span className="text-sm text-dark-400">IOPS</span>
          </div>
          <p className="text-lg font-bold text-white font-mono">
            {execution.total_iops?.toLocaleString() || '—'}
          </p>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-4 h-4 text-emerald-400" />
            <span className="text-sm text-dark-400">Throughput</span>
          </div>
          <p className="text-lg font-bold text-white font-mono">
            {execution.total_throughput_mbps?.toFixed(1) || '—'} MB/s
          </p>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Timer className="w-4 h-4 text-amber-400" />
            <span className="text-sm text-dark-400">Latency</span>
          </div>
          <p className="text-lg font-bold text-white font-mono">
            {execution.avg_latency_us?.toFixed(1) || '—'} µs
          </p>
        </div>

        <div className="card p-4">
          <div className="flex items-center gap-2 mb-2">
            <Users className="w-4 h-4 text-blue-400" />
            <span className="text-sm text-dark-400">Clients</span>
          </div>
          <p className="text-lg font-bold text-white font-mono">
            {execution.client_count || '—'}
          </p>
        </div>
      </div>

      {/* Performance Analysis - Compare achieved vs expected */}
      {execution.status === 'completed' && execution.total_throughput_mbps && (
        <div className="mb-8 p-5 bg-gradient-to-r from-emerald-500/10 via-cyan-500/10 to-blue-500/10 border border-emerald-500/20 rounded-xl">
          <div className="flex items-center gap-2 mb-4">
            <TrendingUp className="w-5 h-5 text-emerald-400" />
            <h3 className="text-white font-semibold">Performance Analysis</h3>
          </div>
          
          {(() => {
            const achievedMBps = execution.total_throughput_mbps || 0;
            const hasNetworkData = networkBaseline?.estimated_achievable_throughput_mbps > 0;
            const expectedMBps = hasNetworkData 
              ? networkBaseline.estimated_achievable_throughput_mbps / 8 // Convert Mbps to MB/s
              : 0;
            const maxTheoreticalMBps = hasNetworkData 
              ? networkBaseline.max_theoretical_throughput_mbps / 8
              : 0;
            const efficiency = expectedMBps > 0 ? (achievedMBps / expectedMBps) * 100 : 0;
            const networkUtilization = maxTheoreticalMBps > 0 ? (achievedMBps / maxTheoreticalMBps) * 100 : 0;
            
            const getEfficiencyColor = (eff: number) => {
              if (eff >= 90) return 'text-emerald-400';
              if (eff >= 70) return 'text-cyan-400';
              if (eff >= 50) return 'text-amber-400';
              return 'text-red-400';
            };

            const getEfficiencyBg = (eff: number) => {
              if (eff >= 90) return 'bg-emerald-500';
              if (eff >= 70) return 'bg-cyan-500';
              if (eff >= 50) return 'bg-amber-500';
              return 'bg-red-500';
            };
            
            return (
              <div className="space-y-4">
                <div className={`grid gap-4 ${hasNetworkData ? 'grid-cols-2 md:grid-cols-4' : 'grid-cols-2 md:grid-cols-3'}`}>
                  <div className="bg-dark-800/50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Activity className="w-4 h-4 text-emerald-400" />
                      <span className="text-xs text-dark-400">Achieved Throughput</span>
                    </div>
                    <p className="text-xl font-mono font-bold text-emerald-400">
                      {achievedMBps >= 1000 
                        ? `${(achievedMBps / 1000).toFixed(2)} GB/s`
                        : `${achievedMBps.toFixed(1)} MB/s`}
                    </p>
                  </div>
                  
                  {hasNetworkData ? (
                    <>
                      <div className="bg-dark-800/50 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <Target className="w-4 h-4 text-cyan-400" />
                          <span className="text-xs text-dark-400">Expected</span>
                        </div>
                        <p className="text-xl font-mono font-bold text-cyan-400">
                          {expectedMBps >= 1000 
                            ? `${(expectedMBps / 1000).toFixed(2)} GB/s`
                            : `${expectedMBps.toFixed(1)} MB/s`}
                        </p>
                      </div>
                      
                      <div className="bg-dark-800/50 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <Zap className="w-4 h-4 text-blue-400" />
                          <span className="text-xs text-dark-400">Max Theoretical</span>
                        </div>
                        <p className="text-xl font-mono font-bold text-blue-400">
                          {maxTheoreticalMBps >= 1000 
                            ? `${(maxTheoreticalMBps / 1000).toFixed(2)} GB/s`
                            : `${maxTheoreticalMBps.toFixed(1)} MB/s`}
                        </p>
                      </div>
                      
                      <div className="bg-dark-800/50 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <TrendingUp className="w-4 h-4 text-primary-400" />
                          <span className="text-xs text-dark-400">Efficiency</span>
                        </div>
                        <p className={`text-xl font-mono font-bold ${getEfficiencyColor(efficiency)}`}>
                          {efficiency.toFixed(1)}%
                        </p>
                      </div>
                    </>
                  ) : (
                    <>
                      <div className="bg-dark-800/50 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <Zap className="w-4 h-4 text-primary-400" />
                          <span className="text-xs text-dark-400">Total IOPS</span>
                        </div>
                        <p className="text-xl font-mono font-bold text-primary-400">
                          {execution.total_iops?.toLocaleString() || '—'}
                        </p>
                      </div>
                      
                      <div className="bg-dark-800/50 rounded-lg p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <Timer className="w-4 h-4 text-amber-400" />
                          <span className="text-xs text-dark-400">Avg Latency</span>
                        </div>
                        <p className="text-xl font-mono font-bold text-amber-400">
                          {execution.avg_latency_us ? 
                            (execution.avg_latency_us >= 1000 
                              ? `${(execution.avg_latency_us / 1000).toFixed(2)} ms`
                              : `${execution.avg_latency_us.toFixed(1)} µs`)
                            : '—'}
                        </p>
                      </div>
                    </>
                  )}
                </div>
                
                {/* Progress Bar - only show when we have network data */}
                {hasNetworkData && (
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs text-dark-400">
                      <span>Network Utilization</span>
                      <span className={getEfficiencyColor(networkUtilization)}>{networkUtilization.toFixed(1)}%</span>
                    </div>
                    <div className="h-3 bg-dark-800 rounded-full overflow-hidden">
                      <div 
                        className={`h-full ${getEfficiencyBg(networkUtilization)} transition-all duration-500`}
                        style={{ width: `${Math.min(networkUtilization, 100)}%` }}
                      />
                    </div>
                    <p className="text-xs text-dark-500">
                      {efficiency >= 90 
                        ? '🎉 Excellent! Performance meets or exceeds expectations.' 
                        : efficiency >= 70 
                        ? '✓ Good performance. Minor optimizations may help.' 
                        : efficiency >= 50 
                        ? '⚠️ Moderate performance. Consider tuning I/O parameters.' 
                        : '⚠️ Below expected. Check for bottlenecks or configuration issues.'}
                    </p>
                  </div>
                )}
                
                {/* Note when no network data */}
                {!hasNetworkData && (
                  <p className="text-xs text-dark-500">
                    💡 No network baseline was captured for this workload. Use "Run Full Profile" before creating workloads to see efficiency comparison.
                  </p>
                )}
              </div>
            );
          })()}
        </div>
      )}

      {/* Error Message */}
      {execution.status === 'failed' && execution.error_message && (
        <div className="mb-8 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
          <div className="flex items-start gap-3">
            <XCircle className="w-5 h-5 text-red-400 mt-0.5 flex-shrink-0" />
            <div>
              <h3 className="text-red-400 font-semibold mb-1">Execution Failed</h3>
              <p className="text-red-300 text-sm font-mono whitespace-pre-wrap">
                {execution.error_message}
              </p>
            </div>
          </div>
        </div>
      )}

      {/* No error message but failed */}
      {execution.status === 'failed' && !execution.error_message && (
        <div className="mb-8 p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 mt-0.5 flex-shrink-0" />
            <div>
              <h3 className="text-amber-400 font-semibold mb-1">Execution Failed</h3>
              <p className="text-dark-300 text-sm">
                No error details available. Check the manager logs for more information.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        {/* IOPS Chart */}
        <div className="card p-6">
          <h3 className="font-display font-semibold text-white mb-4">IOPS Over Time</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 12 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="readIops"
                  stackId="1"
                  stroke="#3b82f6"
                  fill="#3b82f6"
                  fillOpacity={0.3}
                  name="Read IOPS"
                />
                <Area
                  type="monotone"
                  dataKey="writeIops"
                  stackId="1"
                  stroke="#10b981"
                  fill="#10b981"
                  fillOpacity={0.3}
                  name="Write IOPS"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Throughput Chart */}
        <div className="card p-6">
          <h3 className="font-display font-semibold text-white mb-4">Throughput Over Time</h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 12 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="throughput"
                  stroke="#10b981"
                  strokeWidth={2}
                  dot={false}
                  name="MB/s"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Latency Chart */}
        <div className="card p-6 lg:col-span-2">
          <h3 className="font-display font-semibold text-white mb-4">Latency Over Time</h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 12 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 12 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#1e293b',
                    border: '1px solid #334155',
                    borderRadius: '8px',
                  }}
                />
                <Line
                  type="monotone"
                  dataKey="latency"
                  stroke="#f59e0b"
                  strokeWidth={2}
                  dot={false}
                  name="Latency (µs)"
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Execution Details */}
      <div className="card p-6">
        <h3 className="font-display font-semibold text-white mb-4">Execution Details</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-sm text-dark-400 mb-1">Cluster</p>
            <p className="text-white">{execution.cluster_name || '—'}</p>
          </div>
          <div>
            <p className="text-sm text-dark-400 mb-1">Workload Type</p>
            <p className="text-white">{execution.workload_type || '—'}</p>
          </div>
          <div>
            <p className="text-sm text-dark-400 mb-1">Storage Backend</p>
            <p className="text-white">{execution.storage_backend || '—'}</p>
          </div>
          <div>
            <p className="text-sm text-dark-400 mb-1">Duration</p>
            <p className="text-white">{execution.duration_seconds || '—'}s</p>
          </div>
          <div>
            <p className="text-sm text-dark-400 mb-1">Started At</p>
            <p className="text-white">
              {execution.started_at
                ? new Date(execution.started_at).toLocaleString()
                : '—'}
            </p>
          </div>
          <div>
            <p className="text-sm text-dark-400 mb-1">Completed At</p>
            <p className="text-white">
              {execution.completed_at
                ? new Date(execution.completed_at).toLocaleString()
                : '—'}
            </p>
          </div>
        </div>
      </div>

      {/* Executed Commands */}
      {commandsData?.commands?.length > 0 && (
        <div className="card p-6 mt-6">
          <h3 className="font-display font-semibold text-white mb-4">
            Executed Commands ({commandsData.total})
          </h3>
          <div className="space-y-3 max-h-96 overflow-y-auto">
            {commandsData.commands.map((cmd: any, index: number) => (
              <div 
                key={index} 
                className={`p-3 rounded-lg ${
                  cmd.command.startsWith('# FAILED') 
                    ? 'bg-red-500/10 border border-red-500/30' 
                    : cmd.command.startsWith('# SUCCESS')
                    ? 'bg-emerald-500/10 border border-emerald-500/30'
                    : 'bg-dark-800/50'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm text-primary-400 font-medium">
                    {cmd.description}
                  </span>
                  <div className="flex items-center gap-2 text-xs text-dark-500">
                    <span className="font-mono">{cmd.client_id}</span>
                    <span>•</span>
                    <span>{new Date(cmd.timestamp).toLocaleTimeString()}</span>
                  </div>
                </div>
                <pre className={`text-xs font-mono whitespace-pre-wrap break-all ${
                  cmd.command.startsWith('# FAILED') 
                    ? 'text-red-400' 
                    : cmd.command.startsWith('# SUCCESS')
                    ? 'text-emerald-400'
                    : 'text-dark-300'
                }`}>
                  {cmd.command}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
