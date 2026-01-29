import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { FileCode, Plus, Play, Copy, Trash2, AlertTriangle, HardDrive, FolderOpen, Cloud, Wifi, Loader2, XCircle, TrendingUp, Settings } from 'lucide-react'
import { api } from '../lib/api'
import Modal from '../components/Modal'

export default function Workloads() {
  const queryClient = useQueryClient()
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingWorkload, setEditingWorkload] = useState<any>(null)
  const [networkModalOpen, setNetworkModalOpen] = useState(false)
  const [networkProfilingStatus, setNetworkProfilingStatus] = useState<'idle' | 'running' | 'done' | 'error'>('idle')
  const [networkResults, setNetworkResults] = useState<any>(null)
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    cluster_name: '',
    storage_type: 'block',
    // Mount config for file workloads
    filesystem_type: 'cephfs',
    mount_point: '/mnt/scale_test',
    cephfs_path: '/',
    cephfs_user: 'admin',
    cephfs_mount_method: 'kernel',
    nfs_server: '',
    nfs_export: '',
    nfs_version: '4.1',
    gluster_volume: '',
    gluster_servers: '',
    mount_options: '',
    // I/O config
    tool: 'fio',
    pattern: 'random',
    block_size: '4k',
    read_percent: 100,
    io_depth: 32,
    num_jobs: 8,
    duration: 60,
    file_size: '10G',
    direct_io: true,
    // Client selection
    client_mode: 'all',
    client_count: 1,
    client_ids: '',
    // Fill cluster config
    fill_storage_type: 'cephfs',
    fill_target_percent: 50,
    fill_filesystem_name: '',
    fill_pool_name: '',
    fill_bucket_name: '',
    fill_file_size: '1G',
    fill_parallel_writes: 4,
  })

  // Get available clients for selection
  const { data: clientsData } = useQuery({
    queryKey: ['clients'],
    queryFn: () => api.get('/api/v1/clients/'),
  })

  const { data, isLoading, error } = useQuery({
    queryKey: ['workloads'],
    queryFn: () => api.get('/api/v1/workloads/'),
  })

  const { data: clusters } = useQuery({
    queryKey: ['clusters'],
    queryFn: () => api.get('/api/v1/clusters/'),
  })

  // Get selected cluster details for auto-filling mount info
  const selectedCluster = clusters?.clusters?.find((c: any) => c.name === formData.cluster_name)

  // Get filesystems and pools for fill cluster workload
  const { data: filesystems } = useQuery({
    queryKey: ['filesystems', formData.cluster_name],
    queryFn: () => api.get(`/api/v1/clusters/${formData.cluster_name}/filesystems`),
    enabled: !!formData.cluster_name && formData.tool === 'fill_cluster',
  })

  const { data: pools } = useQuery({
    queryKey: ['pools', formData.cluster_name],
    queryFn: () => api.get(`/api/v1/clusters/${formData.cluster_name}/pools`),
    enabled: !!formData.cluster_name && formData.tool === 'fill_cluster',
  })

  // Get network suggestions for the cluster
  const { data: networkSuggestions, isLoading: networkLoading, refetch: refetchNetwork } = useQuery({
    queryKey: ['network-suggestions', formData.cluster_name, formData.storage_type],
    queryFn: () => api.get(`/api/v1/network/suggestions/${formData.cluster_name}?storage_type=${formData.storage_type}`),
    enabled: !!formData.cluster_name && formData.tool !== 'fill_cluster',
    staleTime: 60000, // Cache for 1 minute
  })

  const { data: capacity } = useQuery({
    queryKey: ['capacity', formData.cluster_name],
    queryFn: () => api.get(`/api/v1/clusters/${formData.cluster_name}/capacity`),
    enabled: !!formData.cluster_name && formData.tool === 'fill_cluster',
  })

  // Run full network profiling
  const runNetworkProfile = async () => {
    if (!formData.cluster_name) return
    
    setNetworkModalOpen(true)
    setNetworkProfilingStatus('running')
    setNetworkResults(null)
    
    try {
      const result = await api.get(`/api/v1/network/profile/${formData.cluster_name}?duration=5`)
      setNetworkResults(result)
      setNetworkProfilingStatus('done')
    } catch (err: any) {
      setNetworkResults({ error: err.message || 'Network profiling failed' })
      setNetworkProfilingStatus('error')
    }
  }

  // Auto-fill NFS server from cluster if available
  useEffect(() => {
    if (selectedCluster?.nfs) {
      setFormData(prev => ({
        ...prev,
        nfs_server: selectedCluster.nfs.server || '',
        nfs_export: selectedCluster.nfs.export_path || '',
      }))
    }
  }, [selectedCluster])

  const createMutation = useMutation({
    mutationFn: (workload: any) => api.post('/api/v1/workloads/', workload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workloads'] })
      setIsModalOpen(false)
      resetForm()
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (name: string) => api.delete(`/api/v1/workloads/${name}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workloads'] })
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ name, workload }: { name: string; workload: any }) => 
      api.put(`/api/v1/workloads/${name}`, workload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['workloads'] })
      setEditingWorkload(null)
      resetForm()
    },
  })

  const resetForm = () => {
    setFormData({
      name: '',
      description: '',
      cluster_name: clusters?.clusters?.[0]?.name || '',
      storage_type: 'block',
    filesystem_type: 'cephfs',
    mount_point: '/mnt/scale_test',
    cephfs_path: '/',
    cephfs_user: 'admin',
    cephfs_mount_method: 'kernel',
    nfs_server: '',
      nfs_export: '',
      nfs_version: '4.1',
      gluster_volume: '',
      gluster_servers: '',
      mount_options: '',
      tool: 'fio',
      pattern: 'random',
      block_size: '4k',
      read_percent: 100,
      io_depth: 32,
      num_jobs: 8,
      duration: 60,
      file_size: '10G',
      direct_io: true,
      // Client selection
      client_mode: 'all',
      client_count: 1,
      client_ids: '',
    })
  }

  // Apply network suggestions to form
  const applyNetworkSuggestions = () => {
    if (networkSuggestions?.suggestions) {
      const s = networkSuggestions.suggestions
      setFormData(prev => ({
        ...prev,
        io_depth: s.recommended_io_depth,
        num_jobs: s.recommended_num_jobs,
        block_size: s.recommended_block_size,
      }))
    }
  }

  // Start editing a workload
  const startEditing = (workload: any) => {
    const io = workload.io || {}
    const test = workload.test || {}
    const mount = workload.mount || {}
    const clients = workload.clients || {}
    const fillCluster = workload.fill_cluster || {}
    
    setFormData({
      name: workload.name || '',
      description: workload.description || '',
      cluster_name: workload.cluster_name || '',
      storage_type: workload.storage_type || 'block',
      filesystem_type: mount.filesystem_type || 'cephfs',
      mount_point: mount.mount_point || '/mnt/scale_test',
      cephfs_path: mount.cephfs_path || '/',
      cephfs_user: mount.cephfs_user || 'admin',
      cephfs_mount_method: mount.mount_method || 'kernel',
      nfs_server: mount.nfs_server || '',
      nfs_export: mount.nfs_export || '',
      nfs_version: mount.nfs_version || '4.1',
      gluster_volume: mount.gluster_volume || '',
      gluster_servers: mount.gluster_servers || '',
      mount_options: mount.mount_options || '',
      tool: workload.tool || 'fio',
      pattern: io.pattern || 'random',
      block_size: io.block_size || '4k',
      read_percent: io.read_percent ?? 100,
      io_depth: io.io_depth || 32,
      num_jobs: io.num_jobs || 8,
      duration: test.duration || 60,
      file_size: test.file_size || '10G',
      direct_io: io.direct_io !== false,
      client_mode: clients.mode || 'all',
      client_count: clients.count || 1,
      client_ids: clients.client_ids?.join(', ') || '',
      fill_storage_type: fillCluster.storage_type || 'cephfs',
      fill_target_percent: fillCluster.target_percent || 50,
      fill_filesystem_name: fillCluster.filesystem_name || '',
      fill_pool_name: fillCluster.pool_name || '',
      fill_bucket_name: fillCluster.bucket_name || '',
      fill_file_size: fillCluster.file_size || '1G',
      fill_parallel_writes: fillCluster.num_parallel_writes || 4,
    })
    setEditingWorkload(workload)
    setIsModalOpen(true)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    
    const workload: any = {
      name: formData.name,
      description: formData.description,
      cluster_name: formData.cluster_name,
      storage_type: formData.storage_type,
      tool: formData.tool,
      io: {
        pattern: formData.pattern,
        block_size: formData.block_size,
        read_percent: formData.read_percent,
        write_percent: 100 - formData.read_percent,
        io_depth: formData.io_depth,
        num_jobs: formData.num_jobs,
        direct_io: formData.direct_io,
      },
      test: {
        duration: formData.duration,
        file_size: formData.file_size,
      },
      clients: {
        mode: formData.client_mode,
        count: formData.client_mode === 'count' ? formData.client_count : undefined,
        client_ids: formData.client_mode === 'specific' 
          ? formData.client_ids.split(',').map((id: string) => id.trim()).filter(Boolean)
          : undefined,
      },
      prechecks: {
        enabled: true,
        cluster_health: true,
        client_health: true,
      },
    }

    // Add mount configuration for file workloads
    if (formData.storage_type === 'file') {
      workload.mount = {
        filesystem_type: formData.filesystem_type,
        mount_point: formData.mount_point,
        mount_options: formData.mount_options || undefined,
        auto_unmount: true,
      }

      // Add filesystem-specific options
      if (formData.filesystem_type === 'cephfs') {
        workload.mount.cephfs_path = formData.cephfs_path
        workload.mount.cephfs_user = formData.cephfs_user
        workload.mount.mount_method = formData.cephfs_mount_method
      } else if (formData.filesystem_type === 'nfs') {
        workload.mount.nfs_server = formData.nfs_server
        workload.mount.nfs_export = formData.nfs_export
        workload.mount.nfs_version = formData.nfs_version
      } else if (formData.filesystem_type === 'glusterfs') {
        workload.mount.gluster_volume = formData.gluster_volume
        workload.mount.gluster_servers = formData.gluster_servers.split(',').map((s: string) => s.trim()).filter(Boolean)
      }
    }

    // Add fill cluster configuration
    if (formData.tool === 'fill_cluster') {
      // Find replication factor from selected pool
      let replicationFactor = 3
      if (pools?.pools) {
        const selectedPool = pools.pools.find((p: any) => 
          p.name === formData.fill_pool_name || 
          p.name === formData.fill_filesystem_name + '_data' ||
          p.name === 'cephfs.cephfs.data'
        )
        if (selectedPool) {
          replicationFactor = selectedPool.size || 3
        }
      }

      workload.fill_cluster = {
        storage_type: formData.fill_storage_type,
        target_fill_percent: formData.fill_target_percent,
        filesystem_name: formData.fill_filesystem_name || undefined,
        pool_name: formData.fill_pool_name || undefined,
        bucket_name: formData.fill_bucket_name || undefined,
        file_size: formData.fill_file_size,
        num_parallel_writes: formData.fill_parallel_writes,
        replication_factor: replicationFactor,
        mount_point: '/mnt/scale_test',
      }
    }

    // Include network baseline if we have profiling data
    // Prefer full profile results, fall back to quick suggestions
    if (networkResults?.suggestions) {
      workload.network_baseline = {
        max_theoretical_throughput_mbps: networkResults.suggestions.max_theoretical_throughput_mbps,
        estimated_achievable_throughput_mbps: networkResults.suggestions.estimated_achievable_throughput_mbps,
        recommended_io_depth: networkResults.suggestions.recommended_io_depth,
        recommended_num_jobs: networkResults.suggestions.recommended_num_jobs,
        recommended_block_size: networkResults.suggestions.recommended_block_size,
        bottleneck: networkResults.suggestions.bottleneck,
        aggregate_bandwidth_gbps: networkResults.aggregate_bandwidth_gbps,
        avg_latency_ms: networkResults.avg_latency_ms,
        client_count: networkResults.clients?.length || 0,
      }
    } else if (networkSuggestions?.suggestions) {
      workload.network_baseline = {
        max_theoretical_throughput_mbps: networkSuggestions.suggestions.max_theoretical_throughput_mbps,
        estimated_achievable_throughput_mbps: networkSuggestions.suggestions.estimated_achievable_throughput_mbps,
        recommended_io_depth: networkSuggestions.suggestions.recommended_io_depth,
        recommended_num_jobs: networkSuggestions.suggestions.recommended_num_jobs,
        recommended_block_size: networkSuggestions.suggestions.recommended_block_size,
        bottleneck: networkSuggestions.suggestions.bottleneck,
        client_count: networkSuggestions.client_count || 0,
      }
    }

    if (editingWorkload) {
      // Update existing workload
      updateMutation.mutate({ name: editingWorkload.name, workload })
    } else {
      // Create new workload
      createMutation.mutate(workload)
    }
  }

  const getStorageTypeIcon = (type: string) => {
    switch (type) {
      case 'block': return <HardDrive className="w-5 h-5" />
      case 'file': return <FolderOpen className="w-5 h-5" />
      case 'object': return <Cloud className="w-5 h-5" />
      default: return <HardDrive className="w-5 h-5" />
    }
  }

  return (
    <div className="p-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-bold text-white mb-2">
            Workloads
          </h1>
          <p className="text-dark-400">
            {data?.templates ?? 0} templates, {data?.custom ?? 0} custom workloads
          </p>
        </div>
        <button 
          onClick={() => setIsModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          Create Workload
        </button>
      </div>

      {/* Templates Section */}
      <div className="mb-8">
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          Templates
        </h2>
        {isLoading ? (
          <div className="flex items-center justify-center h-32">
            <div className="animate-spin w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full" />
          </div>
        ) : error ? (
          <div className="card p-8 text-center text-red-400">
            <AlertTriangle className="w-12 h-12 mx-auto mb-4" />
            <p>Failed to load workloads</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data?.workloads
              ?.filter((w: any) => w._is_template)
              .map((workload: any) => (
                <WorkloadCard 
                  key={workload.name} 
                  workload={workload} 
                  isTemplate 
                  onDelete={() => {}}
                  onEdit={() => {}}
                />
              ))}
            {data?.workloads?.filter((w: any) => w._is_template).length === 0 && (
              <p className="text-dark-400 col-span-3">No templates available</p>
            )}
          </div>
        )}
      </div>

      {/* Custom Workloads Section */}
      <div>
        <h2 className="font-display font-semibold text-lg text-white mb-4">
          Custom Workloads
        </h2>
        {data?.workloads?.filter((w: any) => !w._is_template).length === 0 ? (
          <div className="card p-8 text-center">
            <FileCode className="w-12 h-12 mx-auto mb-4 text-dark-500" />
            <p className="text-dark-400">No custom workloads yet</p>
            <p className="text-sm text-dark-500">
              Create a custom workload or clone from a template
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {data?.workloads
              ?.filter((w: any) => !w._is_template)
              .map((workload: any) => (
                <WorkloadCard 
                  key={workload.name} 
                  workload={workload} 
                  isTemplate={false}
                  onDelete={() => deleteMutation.mutate(workload.name)}
                  onEdit={() => startEditing(workload)}
                />
              ))}
          </div>
        )}
      </div>

      {/* Create/Edit Workload Modal */}
      <Modal 
        isOpen={isModalOpen} 
        onClose={() => { setIsModalOpen(false); setEditingWorkload(null); resetForm(); }} 
        title={editingWorkload ? `Edit Workload: ${editingWorkload.name}` : "Create Workload"} 
        size="xl"
      >
        <form onSubmit={handleSubmit} className="space-y-4 max-h-[70vh] overflow-y-auto pr-2">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm text-dark-400 mb-1">Workload Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                placeholder="my_workload"
                required
              />
            </div>
            <div>
              <label className="block text-sm text-dark-400 mb-1">Target Cluster *</label>
              <select
                value={formData.cluster_name}
                onChange={(e) => setFormData({ ...formData, cluster_name: e.target.value })}
                className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                required
              >
                <option value="">Select a cluster</option>
                {clusters?.clusters?.map((c: any) => (
                  <option key={c.name} value={c.name}>{c.name}</option>
                ))}
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
              placeholder="Workload description"
            />
          </div>

          {/* Storage Type Selection */}
          <div className="border-t border-dark-700/50 pt-4">
            <h3 className="text-white font-medium mb-3">Storage Type</h3>
            <div className="grid grid-cols-3 gap-3">
              {[
                { value: 'block', label: 'Block', desc: 'RBD, iSCSI, NVMe', icon: HardDrive },
                { value: 'file', label: 'File', desc: 'CephFS, NFS, GlusterFS', icon: FolderOpen },
                { value: 'object', label: 'Object', desc: 'S3, Swift, RGW', icon: Cloud },
              ].map(({ value, label, desc, icon: Icon }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFormData({ ...formData, storage_type: value })}
                  className={`p-4 rounded-lg border-2 transition-all text-left ${
                    formData.storage_type === value
                      ? 'border-primary-500 bg-primary-500/10'
                      : 'border-dark-700 hover:border-dark-600'
                  }`}
                >
                  <Icon className={`w-6 h-6 mb-2 ${formData.storage_type === value ? 'text-primary-400' : 'text-dark-400'}`} />
                  <p className={`font-medium ${formData.storage_type === value ? 'text-white' : 'text-dark-300'}`}>{label}</p>
                  <p className="text-xs text-dark-500">{desc}</p>
                </button>
              ))}
            </div>
          </div>

          {/* Filesystem Configuration (for file workloads) */}
          {formData.storage_type === 'file' && (
            <div className="border-t border-dark-700/50 pt-4">
              <h3 className="text-white font-medium mb-3">Filesystem Configuration</h3>
              
              <div className="grid grid-cols-2 gap-4 mb-4">
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Filesystem Type *</label>
                  <select
                    value={formData.filesystem_type}
                    onChange={(e) => setFormData({ ...formData, filesystem_type: e.target.value })}
                    className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  >
                    <option value="cephfs">CephFS</option>
                    <option value="nfs">NFS</option>
                    <option value="glusterfs">GlusterFS</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Mount Point *</label>
                  <input
                    type="text"
                    value={formData.mount_point}
                    onChange={(e) => setFormData({ ...formData, mount_point: e.target.value })}
                    className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    placeholder="/mnt/scale_test"
                    required
                  />
                </div>
              </div>

              {/* CephFS Options */}
              {formData.filesystem_type === 'cephfs' && (
                <div className="p-3 bg-dark-800/50 rounded-lg space-y-3">
                  <div className="grid grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm text-dark-400 mb-1">CephFS Path</label>
                      <input
                        type="text"
                        value={formData.cephfs_path}
                        onChange={(e) => setFormData({ ...formData, cephfs_path: e.target.value })}
                        className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                        placeholder="/"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-dark-400 mb-1">CephFS User</label>
                      <input
                        type="text"
                        value={formData.cephfs_user}
                        onChange={(e) => setFormData({ ...formData, cephfs_user: e.target.value })}
                        className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                        placeholder="admin"
                      />
                    </div>
                    <div>
                      <label className="block text-sm text-dark-400 mb-1">Mount Method</label>
                      <select
                        value={formData.cephfs_mount_method}
                        onChange={(e) => setFormData({ ...formData, cephfs_mount_method: e.target.value })}
                        className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      >
                        <option value="kernel">Kernel (mount -t ceph)</option>
                        <option value="fuse">FUSE (ceph-fuse)</option>
                      </select>
                    </div>
                  </div>
                  <p className="text-xs text-dark-500">
                    {formData.cephfs_mount_method === 'kernel' 
                      ? 'Kernel mount uses: mount -t ceph mon1:6789,mon2:6789:/ /mnt -o name=user,secretfile=/etc/ceph/...'
                      : 'FUSE mount uses: ceph-fuse --id user -k /etc/ceph/keyring -m mon1:6789 /mnt'
                    }
                  </p>
                </div>
              )}

              {/* NFS Options */}
              {formData.filesystem_type === 'nfs' && (
                <div className="grid grid-cols-3 gap-4 p-3 bg-dark-800/50 rounded-lg">
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">NFS Server *</label>
                    <input
                      type="text"
                      value={formData.nfs_server}
                      onChange={(e) => setFormData({ ...formData, nfs_server: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      placeholder="192.168.1.100"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">NFS Export *</label>
                    <input
                      type="text"
                      value={formData.nfs_export}
                      onChange={(e) => setFormData({ ...formData, nfs_export: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      placeholder="/export/data"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">NFS Version</label>
                    <select
                      value={formData.nfs_version}
                      onChange={(e) => setFormData({ ...formData, nfs_version: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    >
                      <option value="3">NFSv3</option>
                      <option value="4">NFSv4</option>
                      <option value="4.1">NFSv4.1</option>
                      <option value="4.2">NFSv4.2</option>
                    </select>
                  </div>
                </div>
              )}

              {/* GlusterFS Options */}
              {formData.filesystem_type === 'glusterfs' && (
                <div className="grid grid-cols-2 gap-4 p-3 bg-dark-800/50 rounded-lg">
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Volume Name *</label>
                    <input
                      type="text"
                      value={formData.gluster_volume}
                      onChange={(e) => setFormData({ ...formData, gluster_volume: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      placeholder="gv0"
                      required
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Servers (comma-separated) *</label>
                    <input
                      type="text"
                      value={formData.gluster_servers}
                      onChange={(e) => setFormData({ ...formData, gluster_servers: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-900 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      placeholder="192.168.1.10,192.168.1.11"
                      required
                    />
                  </div>
                </div>
              )}

              <div className="mt-4">
                <label className="block text-sm text-dark-400 mb-1">Additional Mount Options</label>
                <input
                  type="text"
                  value={formData.mount_options}
                  onChange={(e) => setFormData({ ...formData, mount_options: e.target.value })}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  placeholder="e.g., noatime,nodiratime"
                />
              </div>
            </div>
          )}

          {/* Network Suggestions Panel */}
          {formData.cluster_name && formData.tool !== 'fill_cluster' && (
            <div className="border-t border-dark-700/50 pt-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-white font-medium flex items-center gap-2">
                  <svg className="w-4 h-4 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Network Suggestions
                </h3>
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={runNetworkProfile}
                    className="text-xs text-cyan-400 hover:text-cyan-300 flex items-center gap-1 px-2 py-1 bg-cyan-500/10 rounded hover:bg-cyan-500/20 transition-colors"
                  >
                    <Wifi className="w-3 h-3" />
                    Run Full Profile
                  </button>
                  <button
                    type="button"
                    onClick={() => refetchNetwork()}
                    disabled={networkLoading}
                    className="text-xs text-dark-400 hover:text-white flex items-center gap-1"
                  >
                    {networkLoading ? (
                      <>
                        <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Analyzing...
                      </>
                    ) : (
                      <>Refresh</>
                    )}
                  </button>
                </div>
              </div>

              {networkSuggestions?.suggestions ? (
                <div className="p-4 bg-gradient-to-r from-cyan-500/10 to-blue-500/10 border border-cyan-500/20 rounded-lg">
                  <div className="grid grid-cols-4 gap-4 mb-4">
                    <div>
                      <span className="text-xs text-dark-400">Est. Bandwidth</span>
                      <p className="text-lg font-mono text-cyan-400">
                        {/* Convert Mbps to GB/s: Mbps / 8 / 1000 */}
                        {(networkSuggestions.suggestions.max_theoretical_throughput_mbps / 8 / 1000) >= 1
                          ? `${(networkSuggestions.suggestions.max_theoretical_throughput_mbps / 8 / 1000).toFixed(2)} GB/s`
                          : `${(networkSuggestions.suggestions.max_theoretical_throughput_mbps / 8).toFixed(0)} MB/s`}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-dark-400">Achievable Throughput</span>
                      <p className="text-lg font-mono text-emerald-400">
                        {/* Convert Mbps to GB/s: Mbps / 8 / 1000 */}
                        {(networkSuggestions.suggestions.estimated_achievable_throughput_mbps / 8 / 1000) >= 1
                          ? `${(networkSuggestions.suggestions.estimated_achievable_throughput_mbps / 8 / 1000).toFixed(2)} GB/s`
                          : `${(networkSuggestions.suggestions.estimated_achievable_throughput_mbps / 8).toFixed(0)} MB/s`}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-dark-400">Online Clients</span>
                      <p className="text-lg font-mono text-white">{networkSuggestions.client_count || 0}</p>
                    </div>
                    <div>
                      <span className="text-xs text-dark-400">Bottleneck</span>
                      <p className="text-sm font-mono text-amber-400">
                        {networkSuggestions.suggestions.bottleneck === 'none_detected' 
                          ? '✓ None' 
                          : networkSuggestions.suggestions.bottleneck}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-4 p-3 bg-dark-800/50 rounded-lg">
                    <div className="flex-1 grid grid-cols-3 gap-4 text-sm">
                      <div>
                        <span className="text-dark-400">Suggested I/O Depth:</span>
                        <span className="ml-2 font-mono text-white">{networkSuggestions.suggestions.recommended_io_depth}</span>
                      </div>
                      <div>
                        <span className="text-dark-400">Suggested Jobs:</span>
                        <span className="ml-2 font-mono text-white">{networkSuggestions.suggestions.recommended_num_jobs}</span>
                      </div>
                      <div>
                        <span className="text-dark-400">Suggested Block Size:</span>
                        <span className="ml-2 font-mono text-white">{networkSuggestions.suggestions.recommended_block_size}</span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={applyNetworkSuggestions}
                      className="px-4 py-2 bg-cyan-500 hover:bg-cyan-600 text-white rounded-lg text-sm font-medium transition-colors flex items-center gap-2"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      Apply
                    </button>
                  </div>

                  {networkSuggestions.suggestions.notes?.length > 0 && (
                    <div className="mt-3 text-xs text-dark-400">
                      {networkSuggestions.suggestions.notes.map((note: string, i: number) => (
                        <p key={i} className="flex items-start gap-1">
                          <span className="text-cyan-400">•</span> {note}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ) : networkLoading ? (
                <div className="p-4 bg-dark-800/50 rounded-lg text-center text-dark-400">
                  <svg className="w-6 h-6 animate-spin mx-auto mb-2" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  Analyzing network between clients and cluster...
                </div>
              ) : (
                <div className="p-4 bg-dark-800/50 rounded-lg text-center text-dark-400">
                  <p>Network analysis not available. Make sure clients are online.</p>
                </div>
              )}
            </div>
          )}

          {/* I/O Configuration (hidden for fill_cluster) */}
          <div className="border-t border-dark-700/50 pt-4">
            <h3 className="text-white font-medium mb-3">{formData.tool === 'fill_cluster' ? 'Workload Type' : 'I/O Configuration'}</h3>
            <div className="grid grid-cols-3 gap-4">
              <div>
                <label className="block text-sm text-dark-400 mb-1">Tool</label>
                <select
                  value={formData.tool}
                  onChange={(e) => setFormData({ ...formData, tool: e.target.value })}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                >
                  <option value="fio">FIO (Benchmark)</option>
                  <option value="fill_cluster">Fill Cluster</option>
                  <option value="dd">dd</option>
                  <option value="iozone">IOzone</option>
                </select>
              </div>
              {formData.tool !== 'fill_cluster' && (
                <>
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Pattern</label>
                    <select
                      value={formData.pattern}
                      onChange={(e) => setFormData({ ...formData, pattern: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    >
                      <option value="random">Random</option>
                      <option value="sequential">Sequential</option>
                      <option value="mixed">Mixed</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Block Size</label>
                    <select
                      value={formData.block_size}
                      onChange={(e) => setFormData({ ...formData, block_size: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    >
                      <option value="4k">4K</option>
                      <option value="8k">8K</option>
                      <option value="16k">16K</option>
                      <option value="32k">32K</option>
                      <option value="64k">64K</option>
                      <option value="128k">128K</option>
                      <option value="256k">256K</option>
                      <option value="512k">512K</option>
                      <option value="1m">1M</option>
                    </select>
                  </div>
                </>
              )}
            </div>

            {formData.tool !== 'fill_cluster' && (
              <div className="grid grid-cols-4 gap-4 mt-4">
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Read %</label>
                  <input
                    type="number"
                    value={formData.read_percent}
                    onChange={(e) => setFormData({ ...formData, read_percent: parseInt(e.target.value) || 0 })}
                    className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    min={0}
                    max={100}
                  />
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-1">I/O Depth</label>
                  <input
                    type="number"
                    value={formData.io_depth}
                    onChange={(e) => setFormData({ ...formData, io_depth: parseInt(e.target.value) || 1 })}
                    className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    min={1}
                    max={256}
                  />
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Num Jobs</label>
                  <input
                    type="number"
                    value={formData.num_jobs}
                    onChange={(e) => setFormData({ ...formData, num_jobs: parseInt(e.target.value) || 1 })}
                    className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    min={1}
                    max={64}
                  />
                </div>
                <div className="flex items-end">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.direct_io}
                      onChange={(e) => setFormData({ ...formData, direct_io: e.target.checked })}
                      className="w-4 h-4 rounded border-dark-700 bg-dark-800 text-primary-500 focus:ring-primary-500"
                    />
                    <span className="text-sm text-white">Direct I/O</span>
                  </label>
                </div>
              </div>
            )}
          </div>

          {/* Fill Cluster Configuration */}
          {formData.tool === 'fill_cluster' && (
            <div className="border-t border-dark-700/50 pt-4">
              <h3 className="text-white font-medium mb-3">Fill Cluster Configuration</h3>
              
              {/* Cluster capacity info */}
              {capacity && (
                <div className="mb-4 p-3 bg-dark-800/50 rounded-lg">
                  <div className="grid grid-cols-4 gap-4 text-sm">
                    <div>
                      <span className="text-dark-400">Total Capacity:</span>
                      <p className="text-white font-mono">{capacity.total_tb?.toFixed(2)} TB</p>
                    </div>
                    <div>
                      <span className="text-dark-400">Used:</span>
                      <p className="text-white font-mono">{capacity.used_gb?.toFixed(2)} GB ({capacity.used_percent}%)</p>
                    </div>
                    <div>
                      <span className="text-dark-400">Available:</span>
                      <p className="text-emerald-400 font-mono">{capacity.avail_gb?.toFixed(2)} GB</p>
                    </div>
                    <div>
                      <span className="text-dark-400">Target Fill:</span>
                      <p className="text-amber-400 font-mono">{formData.fill_target_percent}%</p>
                    </div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-3 gap-4">
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Storage Type</label>
                  <select
                    value={formData.fill_storage_type}
                    onChange={(e) => setFormData({ ...formData, fill_storage_type: e.target.value })}
                    className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  >
                    <option value="cephfs">CephFS</option>
                    <option value="rbd">RBD (Block)</option>
                    <option value="rgw">RGW (Object)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Target Fill %</label>
                  <input
                    type="number"
                    value={formData.fill_target_percent}
                    onChange={(e) => setFormData({ ...formData, fill_target_percent: parseInt(e.target.value) || 50 })}
                    className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    min={1}
                    max={100}
                  />
                </div>
                <div>
                  <label className="block text-sm text-dark-400 mb-1">File Size per Write</label>
                  <select
                    value={formData.fill_file_size}
                    onChange={(e) => setFormData({ ...formData, fill_file_size: e.target.value })}
                    className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  >
                    <option value="100M">100 MB</option>
                    <option value="500M">500 MB</option>
                    <option value="1G">1 GB</option>
                    <option value="5G">5 GB</option>
                    <option value="10G">10 GB</option>
                  </select>
                </div>
              </div>

              {/* CephFS specific options */}
              {formData.fill_storage_type === 'cephfs' && (
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Filesystem</label>
                    <select
                      value={formData.fill_filesystem_name}
                      onChange={(e) => setFormData({ ...formData, fill_filesystem_name: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    >
                      <option value="">Select filesystem...</option>
                      {filesystems?.filesystems?.map((fs: any) => (
                        <option key={fs.name} value={fs.name}>{fs.name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Parallel Writes</label>
                    <input
                      type="number"
                      value={formData.fill_parallel_writes}
                      onChange={(e) => setFormData({ ...formData, fill_parallel_writes: parseInt(e.target.value) || 4 })}
                      className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      min={1}
                      max={64}
                    />
                  </div>
                </div>
              )}

              {/* RBD specific options */}
              {formData.fill_storage_type === 'rbd' && (
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Pool</label>
                    <select
                      value={formData.fill_pool_name}
                      onChange={(e) => setFormData({ ...formData, fill_pool_name: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    >
                      <option value="">Select pool...</option>
                      {pools?.pools?.filter((p: any) => p.type === 'replicated').map((pool: any) => (
                        <option key={pool.name} value={pool.name}>
                          {pool.name} (size: {pool.size}x)
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Parallel Writes</label>
                    <input
                      type="number"
                      value={formData.fill_parallel_writes}
                      onChange={(e) => setFormData({ ...formData, fill_parallel_writes: parseInt(e.target.value) || 4 })}
                      className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      min={1}
                      max={64}
                    />
                  </div>
                </div>
              )}

              {/* RGW specific options */}
              {formData.fill_storage_type === 'rgw' && (
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Bucket Name</label>
                    <input
                      type="text"
                      value={formData.fill_bucket_name}
                      onChange={(e) => setFormData({ ...formData, fill_bucket_name: e.target.value })}
                      className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      placeholder="fill-test-bucket"
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-dark-400 mb-1">Parallel Uploads</label>
                    <input
                      type="number"
                      value={formData.fill_parallel_writes}
                      onChange={(e) => setFormData({ ...formData, fill_parallel_writes: parseInt(e.target.value) || 4 })}
                      className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                      min={1}
                      max={64}
                    />
                  </div>
                </div>
              )}

              {/* Replication info */}
              {formData.fill_pool_name && pools?.pools && (
                <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
                  <p className="text-sm text-amber-400">
                    <strong>Note:</strong> Pool "{formData.fill_pool_name}" has 
                    <span className="font-mono mx-1">
                      {pools.pools.find((p: any) => p.name === formData.fill_pool_name)?.size || 3}x
                    </span>
                    replication. Writing 1 GB will consume 
                    <span className="font-mono mx-1">
                      {pools.pools.find((p: any) => p.name === formData.fill_pool_name)?.size || 3} GB
                    </span>
                    of raw storage.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Test Configuration */}
          {formData.tool !== 'fill_cluster' && (
          <div className="border-t border-dark-700/50 pt-4">
            <h3 className="text-white font-medium mb-3">Test Configuration</h3>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm text-dark-400 mb-1">Duration (seconds)</label>
                <input
                  type="number"
                  value={formData.duration}
                  onChange={(e) => setFormData({ ...formData, duration: parseInt(e.target.value) || 60 })}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                  min={1}
                />
              </div>
              <div>
                <label className="block text-sm text-dark-400 mb-1">File Size</label>
                <select
                  value={formData.file_size}
                  onChange={(e) => setFormData({ ...formData, file_size: e.target.value })}
                  className="w-full px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                >
                  <option value="1G">1 GB</option>
                  <option value="5G">5 GB</option>
                  <option value="10G">10 GB</option>
                  <option value="50G">50 GB</option>
                  <option value="100G">100 GB</option>
                </select>
              </div>
            </div>
          </div>
          )}

          {/* Client Selection */}
          <div className="border-t border-dark-700/50 pt-4">
            <h3 className="text-white font-medium mb-3">Client Selection</h3>
            <div className="space-y-3">
              <div className="flex items-center gap-4">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="client_mode"
                    value="all"
                    checked={formData.client_mode === 'all'}
                    onChange={() => setFormData({ ...formData, client_mode: 'all' })}
                    className="text-primary-500"
                  />
                  <span className="text-sm text-white">All Clients</span>
                  <span className="text-xs text-dark-400">({clientsData?.total || 0} available)</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="client_mode"
                    value="count"
                    checked={formData.client_mode === 'count'}
                    onChange={() => setFormData({ ...formData, client_mode: 'count' })}
                    className="text-primary-500"
                  />
                  <span className="text-sm text-white">Specific Count</span>
                </label>
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="radio"
                    name="client_mode"
                    value="specific"
                    checked={formData.client_mode === 'specific'}
                    onChange={() => setFormData({ ...formData, client_mode: 'specific' })}
                    className="text-primary-500"
                  />
                  <span className="text-sm text-white">Specific Clients</span>
                </label>
              </div>

              {formData.client_mode === 'count' && (
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Number of Clients</label>
                  <input
                    type="number"
                    value={formData.client_count}
                    onChange={(e) => setFormData({ ...formData, client_count: parseInt(e.target.value) || 1 })}
                    className="w-32 px-3 py-2 bg-dark-800 border border-dark-700 rounded-lg text-white focus:outline-none focus:border-primary-500"
                    min={1}
                    max={clientsData?.total || 100}
                  />
                  <p className="text-xs text-dark-500 mt-1">
                    First {formData.client_count} clients will be used
                  </p>
                </div>
              )}

              {formData.client_mode === 'specific' && (
                <div>
                  <label className="block text-sm text-dark-400 mb-1">Select Clients</label>
                  {clientsData?.clients?.length > 0 ? (
                    <div className="flex flex-wrap gap-2 p-3 bg-dark-800/50 rounded-lg max-h-32 overflow-y-auto">
                      {clientsData.clients.map((client: any) => (
                        <label
                          key={client.id}
                          className={`flex items-center gap-2 px-3 py-1.5 rounded-lg cursor-pointer transition-colors ${
                            formData.client_ids.includes(client.id)
                              ? 'bg-primary-500/20 border border-primary-500'
                              : 'bg-dark-700 border border-transparent hover:bg-dark-600'
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={formData.client_ids.split(',').map(s => s.trim()).includes(client.id)}
                            onChange={(e) => {
                              const currentIds = formData.client_ids.split(',').map(s => s.trim()).filter(Boolean)
                              if (e.target.checked) {
                                setFormData({ ...formData, client_ids: [...currentIds, client.id].join(', ') })
                              } else {
                                setFormData({ ...formData, client_ids: currentIds.filter(id => id !== client.id).join(', ') })
                              }
                            }}
                            className="hidden"
                          />
                          <span className="text-sm text-white font-mono">{client.id}</span>
                          <span className={`w-2 h-2 rounded-full ${client.status === 'online' ? 'bg-emerald-400' : 'bg-dark-500'}`} />
                        </label>
                      ))}
                    </div>
                  ) : (
                    <p className="text-sm text-dark-400">No clients registered</p>
                  )}
                </div>
              )}
            </div>
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
              disabled={createMutation.isPending || updateMutation.isPending}
              className="px-4 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg font-medium transition-colors disabled:opacity-50"
            >
              {editingWorkload 
                ? (updateMutation.isPending ? 'Updating...' : 'Update Workload')
                : (createMutation.isPending ? 'Creating...' : 'Create Workload')}
            </button>
          </div>

          {(createMutation.isError || updateMutation.isError) && (
            <p className="text-red-400 text-sm">
              Failed to {editingWorkload ? 'update' : 'create'} workload: {
                ((editingWorkload ? updateMutation.error : createMutation.error) as Error)?.message || 'Unknown error'
              }
            </p>
          )}
        </form>
      </Modal>

      {/* Network Profile Modal */}
      <Modal 
        isOpen={networkModalOpen} 
        onClose={() => { setNetworkModalOpen(false); setNetworkProfilingStatus('idle'); setNetworkResults(null); }} 
        title={`Network Profile: ${formData.cluster_name}`}
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
                  
                  {/* Apply button */}
                  <button
                    type="button"
                    onClick={() => {
                      setFormData(prev => ({
                        ...prev,
                        io_depth: networkResults.suggestions.recommended_io_depth,
                        num_jobs: networkResults.suggestions.recommended_num_jobs,
                        block_size: networkResults.suggestions.recommended_block_size,
                      }))
                      setNetworkModalOpen(false)
                    }}
                    className="mt-4 w-full py-2 bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 rounded-lg transition-colors flex items-center justify-center gap-2"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                    </svg>
                    Apply Recommendations
                  </button>
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
                  type="button"
                  onClick={runNetworkProfile}
                  className="px-4 py-2 text-sm bg-cyan-500/20 text-cyan-400 hover:bg-cyan-500/30 rounded-lg transition-colors flex items-center gap-2"
                >
                  <Wifi className="w-4 h-4" />
                  Re-run Test
                </button>
                <button
                  type="button"
                  onClick={() => { setNetworkModalOpen(false); setNetworkProfilingStatus('idle'); setNetworkResults(null); }}
                  className="px-4 py-2 text-sm bg-dark-700 text-white hover:bg-dark-600 rounded-lg transition-colors"
                >
                  Close
                </button>
              </div>
            </>
          ) : null}
        </div>
      </Modal>
    </div>
  )
}

interface WorkloadCardProps {
  workload: any
  isTemplate: boolean
  onDelete: () => void
  onEdit: () => void
}

function WorkloadCard({ workload, isTemplate, onDelete, onEdit }: WorkloadCardProps) {
  const io = workload.io || {}
  const test = workload.test || {}
  const mount = workload.mount || {}

  const getStorageIcon = () => {
    switch (workload.storage_type) {
      case 'file': return <FolderOpen className="w-5 h-5 text-primary-400" />
      case 'object': return <Cloud className="w-5 h-5 text-primary-400" />
      default: return <HardDrive className="w-5 h-5 text-primary-400" />
    }
  }

  const handleRun = async () => {
    try {
      const response = await api.post('/api/v1/executions/', {
        workload_name: workload.name,
        run_prechecks: true,
      })
      window.location.href = `/executions/${response.execution_id}`
    } catch (error) {
      console.error('Failed to start execution:', error)
    }
  }

  return (
    <div className="card card-hover p-5">
      <div className="flex items-start justify-between mb-3">
        <div className="w-10 h-10 rounded-lg bg-primary-500/20 flex items-center justify-center">
          {getStorageIcon()}
        </div>
        <div className="flex items-center gap-2">
          {workload.storage_type === 'file' && mount.filesystem_type && (
            <span className="px-2 py-0.5 rounded text-xs bg-blue-500/20 text-blue-400 uppercase">
              {mount.filesystem_type}
            </span>
          )}
          {isTemplate && (
            <span className="px-2 py-0.5 rounded text-xs bg-purple-500/20 text-purple-400">
              Template
            </span>
          )}
        </div>
      </div>

      <h3 className="font-display font-semibold text-white mb-1">
        {workload.name}
      </h3>
      <p className="text-sm text-dark-400 mb-4 line-clamp-2">
        {workload.description || 'No description'}
      </p>

      <div className="grid grid-cols-2 gap-2 text-xs mb-4">
        <div className="p-2 rounded bg-dark-800/50">
          <p className="text-dark-500">Pattern</p>
          <p className="text-white capitalize">{io.pattern || '—'}</p>
        </div>
        <div className="p-2 rounded bg-dark-800/50">
          <p className="text-dark-500">Block Size</p>
          <p className="text-white">{io.block_size || '—'}</p>
        </div>
        <div className="p-2 rounded bg-dark-800/50">
          <p className="text-dark-500">Read/Write</p>
          <p className="text-white">{io.read_percent ?? 100}/{io.write_percent ?? 0}</p>
        </div>
        <div className="p-2 rounded bg-dark-800/50">
          <p className="text-dark-500">Duration</p>
          <p className="text-white">{test.duration || 60}s</p>
        </div>
      </div>

      <div className="flex items-center gap-2 pt-3 border-t border-dark-700/50">
        <button 
          onClick={handleRun}
          className="flex-1 flex items-center justify-center gap-1 px-3 py-2 bg-primary-500 hover:bg-primary-600 text-white rounded-lg text-sm font-medium transition-colors"
        >
          <Play className="w-4 h-4" />
          Run
        </button>
        {!isTemplate && (
          <button 
            onClick={onEdit}
            className="p-2 hover:bg-dark-800 text-dark-400 hover:text-white rounded-lg transition-colors"
            title="Edit workload"
          >
            <Settings className="w-4 h-4" />
          </button>
        )}
        <button className="p-2 hover:bg-dark-800 text-dark-400 hover:text-white rounded-lg transition-colors" title="Duplicate">
          <Copy className="w-4 h-4" />
        </button>
        {!isTemplate && (
          <button 
            onClick={onDelete}
            className="p-2 hover:bg-red-500/20 text-dark-400 hover:text-red-400 rounded-lg transition-colors"
            title="Delete workload"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
    </div>
  )
}
