import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Server, Plus, CheckCircle, AlertTriangle, Settings, Trash2, Loader2, Eye, EyeOff, XCircle, Activity, Wifi, TrendingUp, Terminal, Send } from 'lucide-react'
import { api } from '../lib/api'
import Modal from '../components/Modal'

export default function Clusters() {
  const queryClient = useQueryClient()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [discoveryStatus, setDiscoveryStatus] = useState<'idle' | 'discovering' | 'success' | 'error'>('idle')
  const [discoveryError, setDiscoveryError] = useState('')
  const [discoveredInfo, setDiscoveredInfo] = useState<any>(null)
  const [healthModalCluster, setHealthModalCluster] = useState<string | null>(null)
  const [editModalCluster, setEditModalCluster] = useState<any>(null)
  const [networkModalCluster, setNetworkModalCluster] = useState<string | null>(null)
  const [networkProfilingStatus, setNetworkProfilingStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [networkResults, setNetworkResults] = useState<any>(null)
  
  // CLI Terminal state
  const [terminalCluster, setTerminalCluster] = useState<string | null>(null)
  const [terminalCommand, setTerminalCommand] = useState('')
  const [terminalHistory, setTerminalHistory] = useState<Array<{command: string, output: string, error?: boolean, timestamp: Date}>>([])
  const [terminalRunning, setTerminalRunning] = useState(false)
  const terminalOutputRef = useRef<HTMLDivElement>(null)
  
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    storage_type: 'block',
    installer_ip: '',
    ssh_user: 'root',
    ssh_password: '',
    ssh_key_path: '',
    auth_method: 'password', // 'password' or 'key'
    ceph_repo_url: '', // For installing ceph-common on clients
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ['clusters'],
    queryFn: () => api.get('/api/v1/clusters/'),
  })

  const createMutation = useMutation({
    mutationFn: (cluster: any) => api.post('/api/v1/clusters/', cluster),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clusters'] })
      setIsModalOpen(false)
      resetForm()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (name: string) => api.delete(`/api/v1/clusters/${name}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['clusters'] })
    },
  })

  // Health query - only runs when healthModalCluster is set
  const { data: healthData, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['cluster-health', healthModalCluster],
    queryFn: () => api.get(`/api/v1/clusters/${healthModalCluster}/health`),
    enabled: !!healthModalCluster,
  })

  // Run full network profiling
  const runNetworkProfile = async (clusterName: string) => {
    setNetworkModalCluster(clusterName)
    setNetworkProfilingStatus('running')
    setNetworkResults(null)
    
    try {
      const result = await api.get(`/api/v1/network/profile/${clusterName}?duration=5`)
      setNetworkResults(result)
      setNetworkProfilingStatus('done')
    } catch (err: any) {
      setNetworkResults({ error: err.message || 'Network profiling failed' })
      setNetworkProfilingStatus('error')
    }
  }

  // Open terminal for cluster
  const openTerminal = (clusterName: string) => {
    setTerminalCluster(clusterName)
    setTerminalHistory([])
    setTerminalCommand('')
  }

  // Run command on cluster
  const runTerminalCommand = async () => {
    if (!terminalCluster || !terminalCommand.trim() || terminalRunning) return
    
    const cmd = terminalCommand.trim()
    setTerminalCommand('')
    setTerminalRunning(true)
    
    // Add command to history immediately
    setTerminalHistory(prev => [...prev, { command: cmd, output: '...', timestamp: new Date() }])
    
    try {
      const result = await api.post(`/api/v1/clusters/${terminalCluster}/run-command`, {
        command: cmd,
        timeout: 60,
      })
      
      // Update the last history entry with result
      setTerminalHistory(prev => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          command: cmd,
          output: result.stdout || result.stderr || '(no output)',
          error: !result.success,
          timestamp: new Date(),
        }
        return updated
      })
    } catch (err: any) {
      setTerminalHistory(prev => {
        const updated = [...prev]
        updated[updated.length - 1] = {
          command: cmd,
          output: err.message || 'Command failed',
          error: true,
          timestamp: new Date(),
        }
        return updated
      })
    } finally {
      setTerminalRunning(false)
    }
  }

  // Scroll terminal to bottom when history changes
  useEffect(() => {
    if (terminalOutputRef.current) {
      terminalOutputRef.current.scrollTop = terminalOutputRef.current.scrollHeight
    }
  }, [terminalHistory])

  // Common Ceph commands for quick access
  const quickCommands = [
    { label: 'Status', cmd: 'ceph status' },
    { label: 'Health', cmd: 'ceph health detail' },
    { label: 'OSD Tree', cmd: 'ceph osd tree' },
    { label: 'Pool List', cmd: 'ceph osd pool ls detail' },
    { label: 'DF', cmd: 'ceph df' },
    { label: 'Mon Stat', cmd: 'ceph mon stat' },
    { label: 'PG Stat', cmd: 'ceph pg stat' },
    { label: 'FS List', cmd: 'ceph fs ls' },
  ]

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      storage_type: 'block',
      installer_ip: '',
      ssh_user: 'root',
      ssh_password: '',
      ssh_key_path: '',
      auth_method: 'password',
      ceph_repo_url: '',
    })
    setDiscoveryStatus('idle')
    setDiscoveryError('')
    setDiscoveredInfo(null)
  }

  const discoverCluster = async () => {
    setDiscoveryStatus('discovering')
    setDiscoveryError('')
    setDiscoveredInfo(null)

    try {
      const response = await api.post('/api/v1/clusters/discover/', {
        host: formData.installer_ip,
        username: formData.ssh_user,
        password: formData.auth_method === 'password' ? formData.ssh_password : undefined,
        key_path: formData.auth_method === 'key' ? formData.ssh_key_path : undefined,
      })
      
      setDiscoveredInfo(response)
      setDiscoveryStatus('success')
    } catch (err: any) {
      setDiscoveryError(err.message || 'Failed to discover cluster')
      setDiscoveryStatus('error')
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!discoveredInfo) {
      setDiscoveryError('Please discover cluster configuration first')
      return
    }

    // Build cluster from discovered info
    const cluster: any = {
      name: formData.name,
      description: formData.description,
      storage_type: formData.storage_type,
      backend: formData.storage_type === 'block' ? 'ceph_rbd' : 
               formData.storage_type === 'file' ? 'cephfs' : 's3',
      ceph: {
        monitors: discoveredInfo.monitors || [],
        user: discoveredInfo.user || 'admin',
        keyring_path: discoveredInfo.keyring_path || '/etc/ceph/ceph.client.admin.keyring',
        conf_path: discoveredInfo.conf_path || '/etc/ceph/ceph.conf',
        pool: discoveredInfo.pools?.[0] || 'rbd',
        repo_url: formData.ceph_repo_url || undefined, // For installing ceph-common on clients
      },
      // Store installer node info for future connections
      installer_node: {
        host: formData.installer_ip,
        username: formData.ssh_user,
        password: formData.auth_method === 'password' ? formData.ssh_password : undefined,
        key_path: formData.auth_method === 'key' ? formData.ssh_key_path : undefined,
        port: 22,
      },
    }

    createMutation.mutate(cluster)
  }

  const canDiscover = formData.installer_ip && formData.ssh_user && 
    (formData.auth_method === 'password' ? formData.ssh_password : formData.ssh_key_path)

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold text-white mb-2">
            Clusters
          </h1>
          <p className="text-dark-400">
            Manage storage clusters for testing
          </p>
        </div>
        <button 
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Add Cluster
        </button>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full" />
        </div>
      ) : error ? (
        <div className="card p-8 text-center text-red-400">
          <AlertTriangle className="w-12 h-12 mx-auto mb-4" />
          <p>Failed to load clusters</p>
        </div>
      ) : data?.clusters?.length === 0 ? (
        <div className="card p-16 text-center">
          <Server className="w-16 h-16 mx-auto mb-4 text-dark-500" />
          <h3 className="text-xl font-display font-semibold text-white mb-2">
            No clusters configured
          </h3>
          <p className="text-dark-400 mb-6">
            Add a storage cluster to start running tests
          </p>
          <button 
            onClick={() => setIsModalOpen(true)}
            className="px-6 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors"
          >
            Add Your First Cluster
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {data.clusters.map((cluster: any) => (
            <div key={cluster.name} className="card card-hover p-6">
              <div className="flex items-start justify-between mb-4">
                <div className="w-12 h-12 rounded-xl bg-purple-500/20 flex items-center justify-center">
                  <Server className="w-6 h-6 text-purple-400" />
                </div>
                <div className="flex gap-1">
                  <button 
                    onClick={() => setEditModalCluster(cluster)}
                    className="p-2 hover:bg-dark-800 rounded-lg transition-colors text-dark-400 hover:text-white"
                    title="Edit cluster settings"
                  >
                    <Settings className="w-4 h-4" />
                  </button>
                  <button 
                    onClick={() => deleteMutation.mutate(cluster.name)}
                    className="p-2 hover:bg-red-500/20 rounded-lg transition-colors text-dark-400 hover:text-red-400"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>

              <h3 className="font-display font-semibold text-lg text-white mb-1">
                {cluster.name}
              </h3>
              <p className="text-sm text-dark-400 mb-4">
                {cluster.description || 'No description'}
              </p>

              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-dark-400">Type</span>
                  <span className="text-white capitalize">{cluster.storage_type}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-dark-400">Backend</span>
                  <span className="text-white">{cluster.backend}</span>
                </div>
                {cluster.ceph?.monitors && (
                  <div className="flex justify-between">
                    <span className="text-dark-400">Monitors</span>
                    <span className="text-white">{cluster.ceph.monitors.length}</span>
                  </div>
                )}
              </div>

              <div className="mt-4 pt-4 border-t border-dark-700/50 flex items-center justify-between">
                <div className="flex items-center gap-2 text-sm">
                  <CheckCircle className="w-4 h-4 text-emerald-400" />
                  <span className="text-emerald-400">Connected</span>
                </div>
                <div className="flex gap-3">
                  <button 
                    onClick={() => setHealthModalCluster(cluster.name)}
                    className="text-sm text-primary-400 hover:text-primary-300"
                  >
                    View Health →
                  </button>
                  <button 
                    onClick={() => runNetworkProfile(cluster.name)}
                    className="text-sm text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
                  >
                    <Wifi className="w-3 h-3" />
                    Network
                  </button>
                  <button 
                    onClick={() => openTerminal(cluster.name)}
                    className="text-sm text-amber-400 hover:text-amber-300 flex items-center gap-1"
                  >
                    <Terminal className="w-3 h-3" />
                    CLI
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Add Cluster Modal */}
      <Modal isOpen={isModalOpen} onClose={() => { setIsModalOpen(false); resetForm(); }} title="Add Cluster" size="lg">
        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Basic Info */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-dark-400 mb-1">Cluster Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                placeholder="my_ceph_cluster"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-dark-400 mb-1">Storage Type</label>
              <select
                value={formData.storage_type}
                onChange={(e) => setFormData({ ...formData, storage_type: e.target.value })}
                className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
              >
                <option value="block">Block (RBD)</option>
                <option value="file">File (CephFS)</option>
                <option value="object">Object (RGW)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-sm text-dark-400 mb-1">Description</label>
            <input
              type="text"
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
              placeholder="Production Ceph cluster"
            />
          </div>

          {/* SSH Connection */}
          <div className="border-t border-dark-700/50 pt-4 mt-4">
            <h4 className="text-sm font-medium text-white mb-3">Installer Node Connection</h4>
            
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-dark-400 mb-1">Installer Node IP *</label>
                <input
                  type="text"
                  value={formData.installer_ip}
                  onChange={(e) => setFormData({ ...formData, installer_ip: e.target.value })}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  placeholder="192.168.1.100"
                  required
                />
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">SSH Username *</label>
                <input
                  type="text"
                  value={formData.ssh_user}
                  onChange={(e) => setFormData({ ...formData, ssh_user: e.target.value })}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  placeholder="root"
                  required
                />
              </div>
            </div>

            <div className="mt-4">
              <label className="block text-sm text-dark-400 mb-2">Authentication Method</label>
              <div className="flex gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="auth_method"
                    value="password"
                    checked={formData.auth_method === 'password'}
                    onChange={() => setFormData({ ...formData, auth_method: 'password' })}
                    className="text-primary-500"
                  />
                  <span className="text-sm text-white">Password</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="auth_method"
                    value="key"
                    checked={formData.auth_method === 'key'}
                    onChange={() => setFormData({ ...formData, auth_method: 'key' })}
                    className="text-primary-500"
                  />
                  <span className="text-sm text-white">SSH Key</span>
                </label>
              </div>
            </div>

            {formData.auth_method === 'password' ? (
              <div className="mt-3 relative">
                <label className="block text-sm text-dark-400 mb-1">SSH Password *</label>
                <div className="relative">
                  <input
                    type={showPassword ? 'text' : 'password'}
                    value={formData.ssh_password}
                    onChange={(e) => setFormData({ ...formData, ssh_password: e.target.value })}
                    className="w-full px-3 py-2 pr-10 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    placeholder="Enter password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-dark-400 hover:text-white"
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
              </div>
            ) : (
              <div className="mt-3">
                <label className="block text-sm text-dark-400 mb-1">SSH Key Path *</label>
                <input
                  type="text"
                  value={formData.ssh_key_path}
                  onChange={(e) => setFormData({ ...formData, ssh_key_path: e.target.value })}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  placeholder="/root/.ssh/id_rsa"
                />
              </div>
            )}
          </div>

          {/* Discover Button */}
          <div className="mt-4">
            <button
              type="button"
              onClick={discoverCluster}
              disabled={!canDiscover || discoveryStatus === 'discovering'}
              className="w-full py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {discoveryStatus === 'discovering' ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Discovering Cluster Configuration...
                </>
              ) : (
                <>
                  <Server className="w-4 h-4" />
                  Discover Cluster Configuration
                </>
              )}
            </button>
          </div>

          {/* Discovery Error */}
          {discoveryStatus === 'error' && (
            <div className="p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
              {discoveryError}
            </div>
          )}

          {/* Discovered Info */}
          {discoveryStatus === 'success' && discoveredInfo && (
            <div className="p-4 bg-emerald-500/10 border border-emerald-500/30 rounded-lg space-y-2">
              <div className="flex items-center gap-2 text-emerald-400 font-medium mb-3">
                <CheckCircle className="w-4 h-4" />
                Cluster Configuration Discovered
              </div>
              
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div>
                  <span className="text-dark-400">Cluster FSID:</span>
                  <p className="text-white font-mono text-xs mt-1">{discoveredInfo.fsid || 'N/A'}</p>
                </div>
                <div>
                  <span className="text-dark-400">Ceph Version:</span>
                  <p className="text-white mt-1">{discoveredInfo.version || 'N/A'}</p>
                </div>
                <div>
                  <span className="text-dark-400">Monitors:</span>
                  <p className="text-white mt-1">{discoveredInfo.monitors?.length || 0} found</p>
                </div>
                <div>
                  <span className="text-dark-400">Health:</span>
                  <p className={`mt-1 ${discoveredInfo.health === 'HEALTH_OK' ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {discoveredInfo.health || 'N/A'}
                  </p>
                </div>
              </div>

              {discoveredInfo.pools?.length > 0 && (
                <div className="mt-3 pt-3 border-t border-emerald-500/20">
                  <span className="text-dark-400 text-sm">Available Pools:</span>
                  <div className="flex flex-wrap gap-2 mt-2">
                    {discoveredInfo.pools.slice(0, 8).map((pool: string) => (
                      <span key={pool} className="px-2 py-1 bg-dark-800 rounded text-xs text-white">
                        {pool}
                      </span>
                    ))}
                    {discoveredInfo.pools.length > 8 && (
                      <span className="px-2 py-1 text-xs text-dark-400">
                        +{discoveredInfo.pools.length - 8} more
                      </span>
                    )}
                  </div>
                </div>
              )}

              {/* Ceph Repo URL for client installation */}
              <div className="mt-3 pt-3 border-t border-emerald-500/20">
                <label className="block text-sm text-dark-400 mb-1">
                  Ceph Repo URL (for installing ceph-common on clients)
                </label>
                <input
                  type="text"
                  value={formData.ceph_repo_url}
                  onChange={(e) => setFormData({ ...formData, ceph_repo_url: e.target.value })}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500 text-sm"
                  placeholder="http://mirror.example.com/ceph/rpm-reef/el8/x86_64/"
                />
                <p className="text-xs text-dark-500 mt-1">
                  Optional. If provided, this repo will be added to /etc/yum.repos.d/ on clients before installing ceph-common.
                </p>
              </div>
            </div>
          )}

          <div className="flex justify-end gap-3 pt-4 border-t border-dark-700/50">
            <button
              type="button"
              onClick={() => { setIsModalOpen(false); resetForm(); }}
              className="px-4 py-2 text-dark-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={createMutation.isPending || discoveryStatus !== 'success'}
              className="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {createMutation.isPending ? 'Adding...' : 'Add Cluster'}
            </button>
          </div>

          {createMutation.isError && (
            <p className="text-red-400 text-sm">
              Failed to add cluster: {(createMutation.error as Error).message}
            </p>
          )}
        </form>
      </Modal>

      {/* Health Modal */}
      <Modal 
        isOpen={!!healthModalCluster} 
        onClose={() => setHealthModalCluster(null)} 
        title={`Cluster Health: ${healthModalCluster}`}
        size="lg"
      >
        <div className="space-y-4">
          {healthLoading ? (
            <div className="flex items-center justify-center p-8">
              <Loader2 className="w-8 h-8 animate-spin text-primary-400" />
              <span className="ml-3 text-dark-400">Checking cluster health...</span>
            </div>
          ) : healthData ? (
            <>
              {/* Health Status Banner */}
              <div className={`p-4 rounded-lg flex items-center gap-3 ${
                healthData.health === 'HEALTH_OK' ? 'bg-emerald-500/10 border border-emerald-500/30' :
                healthData.health === 'HEALTH_WARN' ? 'bg-amber-500/10 border border-amber-500/30' :
                'bg-red-500/10 border border-red-500/30'
              }`}>
                {healthData.health === 'HEALTH_OK' ? (
                  <CheckCircle className="w-6 h-6 text-emerald-400" />
                ) : healthData.health === 'HEALTH_WARN' ? (
                  <AlertTriangle className="w-6 h-6 text-amber-400" />
                ) : (
                  <XCircle className="w-6 h-6 text-red-400" />
                )}
                <div>
                  <p className={`font-medium ${
                    healthData.health === 'HEALTH_OK' ? 'text-emerald-400' :
                    healthData.health === 'HEALTH_WARN' ? 'text-amber-400' : 'text-red-400'
                  }`}>
                    {healthData.health || 'Unknown'}
                  </p>
                  <p className="text-sm text-dark-400">
                    Cluster: {healthData.cluster}
                  </p>
                </div>
              </div>

              {/* Health Checks */}
              {healthData.checks && healthData.checks.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-white mb-2">Health Checks</h4>
                  <div className="space-y-2">
                    {healthData.checks.map((check: any, i: number) => (
                      <div 
                        key={i} 
                        className={`p-3 rounded-lg ${
                          check.status === 'passed' ? 'bg-emerald-500/10' :
                          check.status === 'warning' ? 'bg-amber-500/10' : 'bg-red-500/10'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-white font-medium">{check.name}</span>
                          <span className={`text-xs px-2 py-1 rounded ${
                            check.status === 'passed' ? 'bg-emerald-500/20 text-emerald-400' :
                            check.status === 'warning' ? 'bg-amber-500/20 text-amber-400' : 'bg-red-500/20 text-red-400'
                          }`}>
                            {check.status}
                          </span>
                        </div>
                        {check.message && (
                          <p className="text-sm text-dark-400 mt-1">{check.message}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Cluster State */}
              {healthData.state && (
                <div>
                  <h4 className="text-sm font-medium text-white mb-2">Cluster State</h4>
                  <div className="grid grid-cols-3 gap-4">
                    {healthData.state.osd_count !== undefined && (
                      <div className="p-3 bg-dark-800/50 rounded-lg text-center">
                        <p className="text-2xl font-mono text-white">{healthData.state.osd_count}</p>
                        <p className="text-xs text-dark-400">OSDs</p>
                      </div>
                    )}
                    {healthData.state.mon_count !== undefined && (
                      <div className="p-3 bg-dark-800/50 rounded-lg text-center">
                        <p className="text-2xl font-mono text-white">{healthData.state.mon_count}</p>
                        <p className="text-xs text-dark-400">Monitors</p>
                      </div>
                    )}
                    {healthData.state.pg_count !== undefined && (
                      <div className="p-3 bg-dark-800/50 rounded-lg text-center">
                        <p className="text-2xl font-mono text-white">{healthData.state.pg_count}</p>
                        <p className="text-xs text-dark-400">PGs</p>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Error message if any */}
              {healthData.error && (
                <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
                  <p className="text-red-400">{healthData.error}</p>
                </div>
              )}
            </>
          ) : (
            <div className="text-center text-dark-400 p-8">
              No health data available
            </div>
          )}

          <div className="flex justify-end gap-2 pt-4 border-t border-dark-700">
            <button
              onClick={() => refetchHealth()}
              disabled={healthLoading}
              className="px-4 py-2 bg-dark-700 hover:bg-dark-600 text-white rounded-lg transition-colors flex items-center gap-2"
            >
              <Activity className="w-4 h-4" />
              Refresh
            </button>
            <button
              onClick={() => setHealthModalCluster(null)}
              className="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </Modal>

      {/* Edit Cluster Modal */}
      <Modal 
        isOpen={!!editModalCluster} 
        onClose={() => setEditModalCluster(null)} 
        title={`Edit Cluster: ${editModalCluster?.name}`}
        size="md"
      >
        {editModalCluster && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-dark-400 mb-1">Name</label>
                <p className="text-white font-medium">{editModalCluster.name}</p>
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">Type</label>
                <p className="text-white capitalize">{editModalCluster.storage_type}</p>
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">Backend</label>
                <p className="text-white">{editModalCluster.backend}</p>
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">Monitors</label>
                <p className="text-white">{editModalCluster.ceph?.monitors?.length || 0}</p>
              </div>
            </div>

            {editModalCluster.ceph && (
              <div>
                <label className="block text-sm text-dark-400 mb-1">Monitor Addresses</label>
                <div className="p-3 bg-dark-800/50 rounded-lg font-mono text-sm text-white">
                  {editModalCluster.ceph.monitors?.map((mon: string, i: number) => (
                    <p key={i}>{mon}</p>
                  ))}
                </div>
              </div>
            )}

            {editModalCluster.installer_node && (
              <div>
                <label className="block text-sm text-dark-400 mb-1">Installer Node</label>
                <p className="text-white font-mono">
                  {editModalCluster.installer_node.username}@{editModalCluster.installer_node.host}
                </p>
              </div>
            )}

            <div className="flex justify-end gap-2 pt-4 border-t border-dark-700">
              <button
                onClick={() => {
                  if (confirm(`Are you sure you want to delete cluster "${editModalCluster.name}"?`)) {
                    deleteMutation.mutate(editModalCluster.name)
                    setEditModalCluster(null)
                  }
                }}
                className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-colors"
              >
                Delete Cluster
              </button>
              <button
                onClick={() => setEditModalCluster(null)}
                className="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        )}
      </Modal>

      {/* Network Profile Modal */}
      <Modal 
        isOpen={!!networkModalCluster} 
        onClose={() => { setNetworkModalCluster(null); setNetworkProfilingStatus('idle'); setNetworkResults(null); }} 
        title={`Network Profile: ${networkModalCluster}`}
        size="lg"
      >
        <div className="space-y-4">
          {networkProfilingStatus === 'running' ? (
            <div className="flex flex-col items-center justify-center p-8">
              <Loader2 className="w-8 h-8 animate-spin text-cyan-400 mb-4" />
              <span className="text-dark-400">Running network profiling...</span>
              <span className="text-xs text-dark-500 mt-2">Testing bandwidth between clients and cluster</span>
            </div>
          ) : networkProfilingStatus === 'error' ? (
            <div className="p-4 bg-red-500/10 border border-red-500/30 rounded-lg">
              <div className="flex items-center gap-2 text-red-400">
                <XCircle className="w-5 h-5" />
                <span>{networkResults?.error || 'Network profiling failed'}</span>
              </div>
            </div>
          ) : networkResults ? (
            <>
              {/* Summary Banner */}
              <div className="p-4 rounded-lg bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border border-cyan-500/30">
                <div className="grid grid-cols-3 gap-4 text-center">
                  <div>
                    <p className="text-xs text-dark-400 mb-1">Aggregate Bandwidth</p>
                    <p className="text-2xl font-mono font-bold text-cyan-400">
                      {networkResults.aggregate_bandwidth_gbps?.toFixed(1) || 0} Gbps
                    </p>
                    <p className="text-sm text-dark-500">
                      ({((networkResults.aggregate_bandwidth_gbps || 0) / 8 * 1000).toFixed(0)} MB/s)
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-dark-400 mb-1">Avg Latency</p>
                    <p className="text-2xl font-mono font-bold text-emerald-400">
                      {networkResults.avg_latency_ms?.toFixed(2) || 0} ms
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-dark-400 mb-1">Clients Tested</p>
                    <p className="text-2xl font-mono font-bold text-primary-400">
                      {networkResults.clients?.length || 0}
                    </p>
                  </div>
                </div>
              </div>

              {/* Suggestions */}
              {networkResults.suggestions && (
                <div className="p-4 bg-dark-800/50 rounded-lg">
                  <h4 className="text-white font-medium mb-3 flex items-center gap-2">
                    <TrendingUp className="w-4 h-4 text-emerald-400" />
                    I/O Recommendations
                  </h4>
                  <div className="grid grid-cols-3 gap-4 mb-3">
                    <div className="text-center p-2 bg-dark-900/50 rounded">
                      <p className="text-xs text-dark-400">I/O Depth</p>
                      <p className="text-lg font-mono text-white">{networkResults.suggestions.recommended_io_depth}</p>
                    </div>
                    <div className="text-center p-2 bg-dark-900/50 rounded">
                      <p className="text-xs text-dark-400">Num Jobs</p>
                      <p className="text-lg font-mono text-white">{networkResults.suggestions.recommended_num_jobs}</p>
                    </div>
                    <div className="text-center p-2 bg-dark-900/50 rounded">
                      <p className="text-xs text-dark-400">Block Size</p>
                      <p className="text-lg font-mono text-white">{networkResults.suggestions.recommended_block_size}</p>
                    </div>
                  </div>
                  <div className="text-sm">
                    <p className="text-dark-400 mb-1">Expected Throughput:</p>
                    <p className="text-emerald-400 font-mono">
                      {((networkResults.suggestions.estimated_achievable_throughput_mbps || 0) / 8 / 1000).toFixed(2)} GB/s
                      <span className="text-dark-500 ml-2">
                        (max: {((networkResults.suggestions.max_theoretical_throughput_mbps || 0) / 8 / 1000).toFixed(2)} GB/s)
                      </span>
                    </p>
                  </div>
                  {networkResults.suggestions.notes?.length > 0 && (
                    <ul className="mt-3 text-xs text-dark-400 space-y-1">
                      {networkResults.suggestions.notes.map((note: string, i: number) => (
                        <li key={i}>• {note}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}

              {/* Per-client results */}
              {networkResults.clients?.length > 0 && (
                <div>
                  <h4 className="text-white font-medium mb-3">Per-Client Results</h4>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {networkResults.clients.map((client: any) => (
                      <div 
                        key={client.client_id} 
                        className={`p-3 rounded-lg ${
                          client.status === 'success' ? 'bg-dark-800/50' : 
                          client.status === 'partial' ? 'bg-amber-500/10' : 'bg-red-500/10'
                        }`}
                      >
                        <div className="flex justify-between items-center">
                          <div>
                            <span className="text-white font-mono text-sm">{client.client_id}</span>
                            <span className="text-dark-500 text-xs ml-2">({client.client_hostname})</span>
                          </div>
                          <div className="text-right">
                            <span className="text-cyan-400 font-mono">
                              {client.bandwidth_gbps?.toFixed(1) || 0} Gbps
                            </span>
                            <span className="text-dark-500 text-xs ml-2">
                              {client.latency_ms?.toFixed(2) || 0} ms
                            </span>
                          </div>
                        </div>
                        {client.error && (
                          <p className="text-xs text-amber-400 mt-1">{client.error}</p>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <button
                  onClick={() => runNetworkProfile(networkModalCluster!)}
                  className="px-4 py-2 text-sm bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 rounded-lg transition-colors flex items-center gap-2"
                >
                  <Wifi className="w-4 h-4" />
                  Re-run Test
                </button>
                <button
                  onClick={() => { setNetworkModalCluster(null); setNetworkProfilingStatus('idle'); setNetworkResults(null); }}
                  className="px-4 py-2 text-sm bg-dark-700 text-white hover:bg-dark-600 rounded-lg transition-colors"
                >
                  Close
                </button>
              </div>
            </>
          ) : null}
        </div>
      </Modal>

      {/* CLI Terminal Modal */}
      <Modal 
        isOpen={!!terminalCluster} 
        onClose={() => { setTerminalCluster(null); setTerminalHistory([]); setTerminalCommand(''); }} 
        title={`CLI Terminal: ${terminalCluster}`}
        size="xl"
      >
        <div className="space-y-4">
          {/* Quick Commands */}
          <div className="flex flex-wrap gap-2">
            {quickCommands.map((qc) => (
              <button
                key={qc.cmd}
                onClick={() => {
                  setTerminalCommand(qc.cmd)
                }}
                className="px-2 py-1 text-xs bg-dark-800 hover:bg-dark-700 text-dark-300 hover:text-white rounded transition-colors"
              >
                {qc.label}
              </button>
            ))}
          </div>

          {/* Terminal Output */}
          <div 
            ref={terminalOutputRef}
            className="bg-dark-900 rounded-lg p-4 h-80 overflow-y-auto font-mono text-sm"
          >
            {terminalHistory.length === 0 ? (
              <p className="text-dark-500">
                Enter a command below or click a quick command button above.
                <br />
                Commands are executed on the cluster's installer node via SSH.
              </p>
            ) : (
              <div className="space-y-4">
                {terminalHistory.map((entry, i) => (
                  <div key={i}>
                    <div className="flex items-center gap-2 text-emerald-400">
                      <span className="text-dark-500">$</span>
                      <span>{entry.command}</span>
                    </div>
                    <pre className={`mt-1 whitespace-pre-wrap break-all text-xs ${
                      entry.error ? 'text-red-400' : 'text-dark-300'
                    }`}>
                      {entry.output}
                    </pre>
                  </div>
                ))}
                {terminalRunning && (
                  <div className="flex items-center gap-2 text-dark-400">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Running...</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Command Input */}
          <form 
            onSubmit={(e) => { e.preventDefault(); runTerminalCommand(); }}
            className="flex gap-2"
          >
            <div className="flex-1 flex items-center bg-dark-800 rounded-lg border border-dark-700 focus-within:border-amber-500/50">
              <span className="pl-3 text-dark-500 font-mono">$</span>
              <input
                type="text"
                value={terminalCommand}
                onChange={(e) => setTerminalCommand(e.target.value)}
                placeholder="Enter command (e.g., ceph status)"
                className="flex-1 px-2 py-3 bg-transparent text-white font-mono focus:outline-none"
                disabled={terminalRunning}
                autoFocus
              />
            </div>
            <button
              type="submit"
              disabled={terminalRunning || !terminalCommand.trim()}
              className="px-4 py-2 bg-amber-500 hover:bg-amber-600 disabled:bg-dark-700 disabled:text-dark-500 text-white rounded-lg transition-colors flex items-center gap-2"
            >
              <Send className="w-4 h-4" />
              Run
            </button>
          </form>

          {/* Warning */}
          <p className="text-xs text-dark-500">
            ⚠️ Commands are executed directly on the cluster. Some dangerous commands are blocked for safety.
          </p>
        </div>
      </Modal>
    </div>
  )
}
