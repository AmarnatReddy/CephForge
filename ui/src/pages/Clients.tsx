import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Monitor, Plus, RefreshCw, CheckCircle, XCircle, AlertTriangle, Wifi, Trash2, Play, Square, Loader2, Upload, FileKey, Info, Minus } from 'lucide-react'
import { api } from '../lib/api'
import Modal from '../components/Modal'

interface ClientEntry {
  id: string
  hostname: string
  ssh_user: string
  ssh_password: string
}

const emptyClient = (): ClientEntry => ({
  id: '',
  hostname: '',
  ssh_user: 'root',
  ssh_password: '',
})

export default function Clients() {
  const queryClient = useQueryClient()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [clientEntries, setClientEntries] = useState<ClientEntry[]>([emptyClient()])
  const [sshUser, setSshUser] = useState('root')
  const [sshKeyPath, setSshKeyPath] = useState('')
  const [sshPassword, setSshPassword] = useState('')
  const [useSameCredentials, setUseSameCredentials] = useState(true)
  const [deployAgent, setDeployAgent] = useState(true)
  const [pushCephConfig, setPushCephConfig] = useState(true)
  const [selectedCluster, setSelectedCluster] = useState('')
  const [deployingClients, setDeployingClients] = useState<Set<string>>(new Set())
  const [errorModalClient, setErrorModalClient] = useState<any>(null)

  // Client entry management
  const addClientEntry = () => {
    setClientEntries([...clientEntries, emptyClient()])
  }

  const removeClientEntry = (index: number) => {
    if (clientEntries.length > 1) {
      setClientEntries(clientEntries.filter((_, i) => i !== index))
    }
  }

  const updateClientEntry = (index: number, field: keyof ClientEntry, value: string) => {
    const updated = [...clientEntries]
    updated[index] = { ...updated[index], [field]: value }
    // Auto-generate ID if hostname is set but ID is empty
    if (field === 'hostname' && !updated[index].id && value) {
      updated[index].id = `client-${String(index + 1).padStart(2, '0')}`
    }
    setClientEntries(updated)
  }

  
  const { data, isLoading, error } = useQuery({
    queryKey: ['clients'],
    queryFn: () => api.get('/api/v1/clients/'),
    refetchInterval: 5000, // Refresh every 5s to show deployment status
  })

  const { data: clusters } = useQuery({
    queryKey: ['clusters'],
    queryFn: () => api.get('/api/v1/clusters/'),
  })

  const pushCephConfigMutation = useMutation({
    mutationFn: (clusterName: string) => api.post(`/api/v1/clients/push-ceph-config/${clusterName}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })

  const healthCheck = useMutation({
    mutationFn: () => api.post('/api/v1/clients/health/all'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })

  const addClientsMutation = useMutation({
    mutationFn: (payload: any) => api.post('/api/v1/clients/', payload),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
      setIsModalOpen(false)
      resetForm()
      // Track deploying clients
      if (data.deployment) {
        const newDeploying = new Set(deployingClients)
        data.deployment.forEach((d: any) => newDeploying.add(d.client_id))
        setDeployingClients(newDeploying)
      }
    },
  })

  const deployAllMutation = useMutation({
    mutationFn: () => api.post('/api/v1/clients/deploy/all'),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })

  const deployClientMutation = useMutation({
    mutationFn: (clientId: string) => api.post(`/api/v1/clients/${clientId}/deploy`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })

  const stopClientMutation = useMutation({
    mutationFn: (clientId: string) => api.post(`/api/v1/clients/${clientId}/stop-agent`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })

  const deleteClientMutation = useMutation({
    mutationFn: (clientId: string) => api.delete(`/api/v1/clients/${clientId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clients'] })
    },
  })

  const resetForm = () => {
    setClientEntries([emptyClient()])
    setSshUser('root')
    setSshKeyPath('')
    setSshPassword('')
    setUseSameCredentials(true)
    setDeployAgent(true)
    setPushCephConfig(true)
    setSelectedCluster(clusters?.clusters?.[0]?.name || '')
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    // Build clients from entries
    const clients = clientEntries
      .filter(entry => entry.hostname.trim()) // Only include entries with hostname
      .map((entry, index) => ({
        id: entry.id.trim() || `client-${String(index + 1).padStart(2, '0')}`,
        hostname: entry.hostname.trim(),
        ssh_user: useSameCredentials ? sshUser : (entry.ssh_user || sshUser),
        ssh_password: useSameCredentials ? (sshPassword || undefined) : (entry.ssh_password || sshPassword || undefined),
        ssh_key_path: sshKeyPath || undefined,
      }))

    if (clients.length === 0) {
      return
    }

    const payload: any = {
      clients,
      deploy_agent: deployAgent,
      push_ceph_config: pushCephConfig && selectedCluster ? true : false,
      cluster_name: pushCephConfig && selectedCluster ? selectedCluster : undefined,
    }

    if (sshUser || sshKeyPath || sshPassword) {
      payload.defaults = {
        ssh_user: sshUser,
        ssh_key_path: sshKeyPath || undefined,
        ssh_password: sshPassword || undefined,
      }
    }

    addClientsMutation.mutate(payload)
  }

  const getStatusIcon = (status: string, deploymentStatus?: string) => {
    // Show deploying spinner if deployment is in progress
    if (deploymentStatus && !['success', 'failed'].includes(deploymentStatus)) {
      return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
    }
    switch (status) {
      case 'online':
        return <CheckCircle className="w-4 h-4 text-emerald-400" />
      case 'offline':
      case 'unreachable':
        return <XCircle className="w-4 h-4 text-red-400" />
      case 'error':
        return <AlertTriangle className="w-4 h-4 text-amber-400" />
      case 'deploying':
        return <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
      default:
        return <Wifi className="w-4 h-4 text-dark-400" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online':
        return 'text-emerald-400 bg-emerald-500/20'
      case 'offline':
      case 'unreachable':
        return 'text-red-400 bg-red-500/20'
      case 'error':
        return 'text-amber-400 bg-amber-500/20'
      case 'deploying':
        return 'text-blue-400 bg-blue-500/20'
      default:
        return 'text-dark-400 bg-dark-500/20'
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold text-white mb-2">
            Clients
          </h1>
          <p className="text-dark-400">
            {data?.online ?? 0} of {data?.total ?? 0} clients online
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* Push Ceph Config dropdown */}
          {clusters?.clusters?.length > 0 && data?.clients?.length > 0 && (
            <div className="relative group">
              <button
                className="flex items-center gap-2 px-4 py-2 bg-dark-800 hover:bg-dark-700 text-white rounded-lg font-medium transition-colors"
                title="Push Ceph config to all clients"
              >
                <FileKey className="w-4 h-4" />
                Push Ceph Config
              </button>
              <div className="absolute right-0 mt-1 w-48 bg-dark-800 border border-dark-700 rounded-lg shadow-xl opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                {clusters.clusters.map((cluster: any) => (
                  <button
                    key={cluster.name}
                    onClick={() => pushCephConfigMutation.mutate(cluster.name)}
                    disabled={pushCephConfigMutation.isPending}
                    className="w-full px-4 py-2 text-left text-sm text-white hover:bg-dark-700 first:rounded-t-lg last:rounded-b-lg"
                  >
                    {cluster.name}
                  </button>
                ))}
              </div>
            </div>
          )}
          <button
            onClick={() => deployAllMutation.mutate()}
            disabled={deployAllMutation.isPending || !data?.clients?.length}
            className="flex items-center gap-2 px-4 py-2 bg-dark-800 hover:bg-dark-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
            title="Deploy agent to all clients"
          >
            <Upload className={`w-4 h-4 ${deployAllMutation.isPending ? 'animate-pulse' : ''}`} />
            Deploy All
          </button>
          <button
            onClick={() => healthCheck.mutate()}
            disabled={healthCheck.isPending}
            className="flex items-center gap-2 px-4 py-2 bg-dark-800 hover:bg-dark-700 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 ${healthCheck.isPending ? 'animate-spin' : ''}`} />
            Check Health
          </button>
          <button 
            onClick={() => setIsModalOpen(true)}
            className="flex items-center gap-2 px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Clients
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-8">
        <div className="card p-4">
          <p className="text-sm text-dark-400 mb-1">Total</p>
          <p className="text-2xl font-bold text-white">{data?.total ?? 0}</p>
        </div>
        <div className="card p-4">
          <p className="text-sm text-dark-400 mb-1">Online</p>
          <p className="text-2xl font-bold text-emerald-400">{data?.online ?? 0}</p>
        </div>
        <div className="card p-4">
          <p className="text-sm text-dark-400 mb-1">Offline</p>
          <p className="text-2xl font-bold text-red-400">{data?.offline ?? 0}</p>
        </div>
        <div className="card p-4">
          <p className="text-sm text-dark-400 mb-1">Available</p>
          <p className="text-2xl font-bold text-blue-400">
            {data?.clients?.filter((c: any) => c.status === 'online' && !c.current_execution_id).length ?? 0}
          </p>
        </div>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full" />
        </div>
      ) : error ? (
        <div className="card p-8 text-center text-red-400">
          <AlertTriangle className="w-12 h-12 mx-auto mb-4" />
          <p>Failed to load clients</p>
        </div>
      ) : data?.clients?.length === 0 ? (
        <div className="card p-16 text-center">
          <Monitor className="w-16 h-16 mx-auto mb-4 text-dark-500" />
          <h3 className="text-xl font-display font-semibold text-white mb-2">
            No clients configured
          </h3>
          <p className="text-dark-400 mb-6">
            Add client nodes to run workloads
          </p>
          <button 
            onClick={() => setIsModalOpen(true)}
            className="px-6 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors"
          >
            Add Your First Client
          </button>
        </div>
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-dark-700/50">
                <th className="text-left p-4 text-sm font-medium text-dark-400">Status</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Client ID</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Hostname</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Agent</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Last Heartbeat</th>
                <th className="text-left p-4 text-sm font-medium text-dark-400">Actions</th>
              </tr>
            </thead>
            <tbody>
              {data.clients.map((client: any) => (
                <tr
                  key={client.id}
                  className="border-b border-dark-700/30 hover:bg-dark-800/30 transition-colors"
                >
                  <td className="p-4">
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        {getStatusIcon(client.status, client.deployment_status)}
                        <span className={`px-2 py-0.5 rounded text-xs ${getStatusColor(client.status)}`}>
                          {client.deployment_status && !['success', 'failed'].includes(client.deployment_status) 
                            ? 'deploying' 
                            : (client.status || 'unknown')}
                        </span>
                      </div>
                      {/* Show deployment progress */}
                      {client.deployment_status && !['success', 'failed'].includes(client.deployment_status) && (
                        <div className="flex items-center gap-2 text-xs text-blue-400">
                          <Loader2 className="w-3 h-3 animate-spin" />
                          <span className="capitalize">{client.deployment_status}</span>
                          {client.deployment_step && (
                            <span className="text-dark-400">- {client.deployment_step}</span>
                          )}
                        </div>
                      )}
                      {client.status === 'error' && client.error_message && (
                        <button
                          onClick={() => setErrorModalClient(client)}
                          className="flex items-center gap-1 text-xs text-red-400 hover:text-red-300 transition-colors truncate max-w-xs"
                          title="Click to view full error"
                        >
                          <Info className="w-3 h-3 flex-shrink-0" />
                          <span className="truncate">
                            {client.error_message.length > 35 
                              ? client.error_message.slice(0, 35) + '...' 
                              : client.error_message}
                          </span>
                        </button>
                      )}
                    </div>
                  </td>
                  <td className="p-4">
                    <span className="font-mono text-white">{client.id}</span>
                  </td>
                  <td className="p-4">
                    <span className="text-dark-300">{client.hostname}</span>
                  </td>
                  <td className="p-4">
                    <span className="text-dark-400 text-sm">
                      {client.agent_version || '—'}
                    </span>
                  </td>
                  <td className="p-4">
                    <span className="text-dark-400 text-sm">
                      {client.last_heartbeat
                        ? new Date(client.last_heartbeat).toLocaleString()
                        : '—'}
                    </span>
                  </td>
                  <td className="p-4">
                    <div className="flex items-center gap-1">
                      {client.status !== 'online' ? (
                        <button
                          onClick={() => deployClientMutation.mutate(client.id)}
                          disabled={deployClientMutation.isPending}
                          className="p-2 hover:bg-emerald-500/20 rounded-lg transition-colors text-dark-400 hover:text-emerald-400"
                          title="Deploy & Start Agent"
                        >
                          <Play className="w-4 h-4" />
                        </button>
                      ) : (
                        <button
                          onClick={() => stopClientMutation.mutate(client.id)}
                          disabled={stopClientMutation.isPending}
                          className="p-2 hover:bg-amber-500/20 rounded-lg transition-colors text-dark-400 hover:text-amber-400"
                          title="Stop Agent"
                        >
                          <Square className="w-4 h-4" />
                        </button>
                      )}
                      <button
                        onClick={() => deleteClientMutation.mutate(client.id)}
                        className="p-2 hover:bg-red-500/20 rounded-lg transition-colors text-dark-400 hover:text-red-400"
                        title="Remove Client"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Add Clients Modal */}
      <Modal isOpen={isModalOpen} onClose={() => setIsModalOpen(false)} title="Add Clients" size="lg">
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Same credentials checkbox */}
          <div className="flex items-center gap-3 p-3 bg-dark-800/50 rounded-lg border border-dark-700">
            <input
              type="checkbox"
              id="useSameCredentials"
              checked={useSameCredentials}
              onChange={(e) => setUseSameCredentials(e.target.checked)}
              className="w-4 h-4 rounded border-dark-600 bg-dark-700 text-primary-500 focus:ring-primary-500"
            />
            <label htmlFor="useSameCredentials" className="cursor-pointer">
              <span className="text-white font-medium">Use same credentials for all clients</span>
              <p className="text-xs text-dark-400">Apply the SSH settings below to all clients</p>
            </label>
          </div>

          {/* Global SSH credentials - shown when useSameCredentials is checked */}
          {useSameCredentials && (
            <div className="grid grid-cols-3 gap-4 p-3 bg-primary-500/5 rounded-lg border border-primary-500/20">
              <div>
                <label className="block text-sm text-dark-400 mb-1">SSH User</label>
                <input
                  type="text"
                  value={sshUser}
                  onChange={(e) => setSshUser(e.target.value)}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                />
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">SSH Key Path</label>
                <input
                  type="text"
                  value={sshKeyPath}
                  onChange={(e) => setSshKeyPath(e.target.value)}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  placeholder="/root/.ssh/id_rsa"
                />
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">SSH Password</label>
                <input
                  type="password"
                  value={sshPassword}
                  onChange={(e) => setSshPassword(e.target.value)}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  placeholder="Optional"
                />
              </div>
            </div>
          )}

          {/* Client entries */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-sm text-dark-400">Clients</label>
              <span className="text-xs text-dark-500">{clientEntries.filter(e => e.hostname).length} client(s)</span>
            </div>

            {/* Header row */}
            <div className={`grid gap-2 mb-2 text-xs text-dark-500 ${useSameCredentials ? 'grid-cols-[1fr_1.5fr_auto]' : 'grid-cols-[1fr_1.5fr_1fr_1fr_auto]'}`}>
              <span>Client ID</span>
              <span>IP / Hostname *</span>
              {!useSameCredentials && (
                <>
                  <span>SSH User</span>
                  <span>Password</span>
                </>
              )}
              <span className="w-8"></span>
            </div>

            {/* Client rows */}
            <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
              {clientEntries.map((entry, index) => (
                <div 
                  key={index} 
                  className={`grid gap-2 ${useSameCredentials ? 'grid-cols-[1fr_1.5fr_auto]' : 'grid-cols-[1fr_1.5fr_1fr_1fr_auto]'}`}
                >
                  <input
                    type="text"
                    value={entry.id}
                    onChange={(e) => updateClientEntry(index, 'id', e.target.value)}
                    className="px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white text-sm focus:outline-none focus:border-primary-500"
                    placeholder={`client-${String(index + 1).padStart(2, '0')}`}
                  />
                  <input
                    type="text"
                    value={entry.hostname}
                    onChange={(e) => updateClientEntry(index, 'hostname', e.target.value)}
                    className="px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white text-sm focus:outline-none focus:border-primary-500"
                    placeholder="192.168.1.101"
                    required={index === 0}
                  />
                  {!useSameCredentials && (
                    <>
                      <input
                        type="text"
                        value={entry.ssh_user}
                        onChange={(e) => updateClientEntry(index, 'ssh_user', e.target.value)}
                        className="px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white text-sm focus:outline-none focus:border-primary-500"
                        placeholder="root"
                      />
                      <input
                        type="password"
                        value={entry.ssh_password}
                        onChange={(e) => updateClientEntry(index, 'ssh_password', e.target.value)}
                        className="px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white text-sm focus:outline-none focus:border-primary-500"
                        placeholder="password"
                      />
                    </>
                  )}
                  <button
                    type="button"
                    onClick={() => removeClientEntry(index)}
                    disabled={clientEntries.length === 1}
                    className="p-2 hover:bg-red-500/20 rounded-lg transition-colors text-dark-400 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed"
                    title="Remove client"
                  >
                    <Minus className="w-4 h-4" />
                  </button>
                </div>
              ))}
            </div>

            {/* Add client button */}
            <button
              type="button"
              onClick={addClientEntry}
              className="mt-3 w-full py-2 border-2 border-dashed border-dark-600 hover:border-primary-500 rounded-lg text-dark-400 hover:text-primary-400 transition-colors flex items-center justify-center gap-2"
            >
              <Plus className="w-4 h-4" />
              Add Client
            </button>
          </div>

          <div className="flex items-center gap-3 p-3 bg-dark-800/50 rounded-lg">
            <input
              type="checkbox"
              id="deployAgent"
              checked={deployAgent}
              onChange={(e) => setDeployAgent(e.target.checked)}
              className="w-4 h-4 rounded border-dark-600 text-primary-500 focus:ring-primary-500"
            />
            <div>
              <label htmlFor="deployAgent" className="text-sm text-white font-medium cursor-pointer">
                Deploy and start agent automatically
              </label>
              <p className="text-xs text-dark-400">
                SSH into each client, install dependencies, and start the agent service
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 p-3 bg-dark-800/50 rounded-lg">
            <input
              type="checkbox"
              id="pushCephConfig"
              checked={pushCephConfig}
              onChange={(e) => setPushCephConfig(e.target.checked)}
              className="w-4 h-4 rounded border-dark-600 text-primary-500 focus:ring-primary-500"
            />
            <div className="flex-1">
              <label htmlFor="pushCephConfig" className="text-sm text-white font-medium cursor-pointer">
                Push Ceph config files to clients
              </label>
              <p className="text-xs text-dark-400">
                Copy /etc/ceph/ceph.conf and keyring from cluster installer node to clients
              </p>
            </div>
          </div>

          {pushCephConfig && (
            <div>
              <label className="block text-sm text-dark-400 mb-1">
                Select Cluster (for Ceph config)
              </label>
              <select
                value={selectedCluster}
                onChange={(e) => setSelectedCluster(e.target.value)}
                className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
              >
                <option value="">-- Select Cluster --</option>
                {clusters?.clusters?.map((cluster: any) => (
                  <option key={cluster.name} value={cluster.name}>
                    {cluster.name} ({cluster.backend})
                  </option>
                ))}
              </select>
              {clusters?.clusters?.length === 0 && (
                <p className="text-xs text-amber-400 mt-1">
                  No clusters configured. Add a cluster first to push Ceph config.
                </p>
              )}
            </div>
          )}

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
              disabled={addClientsMutation.isPending}
              className="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              {addClientsMutation.isPending ? 'Adding...' : 'Add Clients'}
            </button>
          </div>

          {addClientsMutation.isError && (
            <p className="text-red-400 text-sm">
              Failed to add clients: {(addClientsMutation.error as Error).message}
            </p>
          )}
        </form>
      </Modal>

      {/* Error Details Modal */}
      <Modal 
        isOpen={!!errorModalClient} 
        onClose={() => setErrorModalClient(null)} 
        title={`Error Details: ${errorModalClient?.id || ''}`}
        size="lg"
      >
        {errorModalClient && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-dark-400 mb-1">Client ID</label>
                <p className="text-white font-mono">{errorModalClient.id}</p>
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">Hostname</label>
                <p className="text-white">{errorModalClient.hostname}</p>
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">Status</label>
                <span className="px-2 py-1 rounded text-xs bg-red-500/20 text-red-400">
                  {errorModalClient.status}
                </span>
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">Last Heartbeat</label>
                <p className="text-dark-300 text-sm">
                  {errorModalClient.last_heartbeat
                    ? new Date(errorModalClient.last_heartbeat).toLocaleString()
                    : 'Never'}
                </p>
              </div>
            </div>

            <div>
              <label className="block text-sm text-dark-400 mb-1">Error Message</label>
              <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                <pre className="text-red-300 text-sm whitespace-pre-wrap font-mono break-all">
                  {errorModalClient.error_message || 'No error message available'}
                </pre>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-4 border-t border-dark-700">
              <button
                onClick={() => {
                  setErrorModalClient(null)
                  deployClientMutation.mutate(errorModalClient.id)
                }}
                className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-medium transition-colors flex items-center gap-2"
              >
                <Play className="w-4 h-4" />
                Retry Deployment
              </button>
              <button
                onClick={() => setErrorModalClient(null)}
                className="px-4 py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}
