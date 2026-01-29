"""Workload configuration models."""

from __future__ import annotations

from enum import Enum
from typing import Optional, Literal, List, Dict
from pydantic import BaseModel, Field, field_validator


class StorageWorkloadType(str, Enum):
    """Type of storage for the workload."""
    BLOCK = "block"
    FILE = "file"
    OBJECT = "object"


class FilesystemType(str, Enum):
    """Supported filesystem types for file workloads."""
    CEPHFS = "cephfs"
    NFS = "nfs"
    GLUSTERFS = "glusterfs"


class IOPattern(str, Enum):
    """I/O access pattern."""
    RANDOM = "random"
    SEQUENTIAL = "sequential"
    MIXED = "mixed"


class WorkloadTool(str, Enum):
    """I/O benchmark tools."""
    FIO = "fio"
    IOZONE = "iozone"
    DD = "dd"
    COSBENCH = "cosbench"
    S3BENCH = "s3bench"
    WARP = "warp"
    FILL_CLUSTER = "fill_cluster"  # Special workload for filling cluster
    CUSTOM = "custom"


class FillStorageType(str, Enum):
    """Storage type for fill cluster workload."""
    CEPHFS = "cephfs"
    RBD = "rbd"
    RGW = "rgw"


class FillClusterConfig(BaseModel):
    """Configuration for fill cluster workload."""
    storage_type: FillStorageType = Field(..., description="Storage type to fill")
    target_fill_percent: int = Field(
        default=50, ge=1, le=100,
        description="Target cluster fill percentage"
    )
    
    # CephFS specific
    filesystem_name: Optional[str] = Field(default=None, description="CephFS filesystem name")
    cephfs_path: str = Field(default="/", description="Path within CephFS to write data")
    
    # RBD specific
    pool_name: Optional[str] = Field(default=None, description="RBD pool name")
    image_prefix: str = Field(default="fill_test", description="RBD image name prefix")
    
    # RGW specific
    bucket_name: Optional[str] = Field(default=None, description="RGW bucket name")
    
    # Write parameters
    file_size: str = Field(default="1G", description="Size of each file/object written")
    num_parallel_writes: int = Field(default=4, ge=1, le=64, description="Parallel write threads")
    
    # Replication factor (auto-discovered or manual)
    replication_factor: Optional[int] = Field(
        default=None, 
        description="Pool replication factor (auto-discovered if not set)"
    )


class BlockSize(str, Enum):
    """Common block sizes."""
    BS_4K = "4k"
    BS_8K = "8k"
    BS_16K = "16k"
    BS_32K = "32k"
    BS_64K = "64k"
    BS_128K = "128k"
    BS_256K = "256k"
    BS_512K = "512k"
    BS_1M = "1m"
    BS_4M = "4m"


class IOConfig(BaseModel):
    """I/O workload configuration."""
    pattern: IOPattern = Field(default=IOPattern.RANDOM, description="I/O access pattern")
    block_size: str = Field(default="4k", description="Block size (e.g., 4k, 64k, 1m)")
    read_percent: int = Field(default=100, ge=0, le=100, description="Read percentage")
    write_percent: int = Field(default=0, ge=0, le=100, description="Write percentage")
    io_depth: int = Field(default=32, ge=1, le=256, description="I/O queue depth")
    num_jobs: int = Field(default=1, ge=1, le=64, description="Number of parallel jobs")
    direct_io: bool = Field(default=True, description="Use direct I/O (bypass page cache)")
    verify_data: bool = Field(default=False, description="Verify written data")
    sync_io: bool = Field(default=False, description="Use synchronous I/O")
    
    @field_validator("write_percent")
    @classmethod
    def validate_rw_percent(cls, v, info):
        """Ensure read + write = 100."""
        read_pct = info.data.get("read_percent", 100)
        if read_pct + v != 100:
            # Auto-adjust write_percent
            return 100 - read_pct
        return v


class TestConfig(BaseModel):
    """Test execution parameters."""
    duration: int = Field(default=60, ge=1, description="Test duration in seconds")
    ramp_time: int = Field(default=0, ge=0, description="Ramp-up time in seconds")
    file_size: str = Field(default="1G", description="Test file size per client")
    warmup_time: int = Field(default=0, ge=0, description="Warmup time (excluded from results)")


class ClientSelection(BaseModel):
    """Client selection for workload."""
    mode: Literal["all", "count", "specific"] = Field(
        default="all",
        description="Client selection mode"
    )
    count: Optional[int] = Field(
        default=None,
        ge=1,
        description="Number of clients (for 'count' mode)"
    )
    client_ids: list[str] = Field(
        default_factory=list,
        description="Specific client IDs (for 'specific' mode)"
    )


class ScalingConfig(BaseModel):
    """Dynamic scaling configuration."""
    enabled: bool = Field(default=False)
    mode: Literal["manual", "bandwidth_target", "iops_target"] = Field(default="manual")
    target_bandwidth_gbps: Optional[float] = Field(default=None)
    target_iops: Optional[int] = Field(default=None)
    min_clients: int = Field(default=1, ge=1)
    max_clients: int = Field(default=100, ge=1)
    scale_up_threshold: float = Field(default=0.95, ge=0, le=1)
    scale_down_threshold: float = Field(default=0.5, ge=0, le=1)


class NetworkConfig(BaseModel):
    """Network optimization configuration."""
    profile: Literal["auto", "manual"] = Field(default="auto")
    target_bandwidth: Optional[str] = Field(default=None, description="Target bandwidth (e.g., '100Gbps')")
    
    # Auto-tuning options
    run_iperf_baseline: bool = Field(default=True)
    adjust_io_params: bool = Field(default=True)
    apply_system_tuning: bool = Field(default=False)


class PrecheckConfig(BaseModel):
    """Pre-test validation configuration."""
    enabled: bool = Field(default=True)
    
    # Cluster checks
    cluster_health: bool = Field(default=True)
    fail_on_health_warn: bool = Field(default=False)
    fail_on_health_err: bool = Field(default=True)
    
    # Client checks
    client_health: bool = Field(default=True)
    exclude_failed_clients: bool = Field(default=True)
    min_healthy_clients: int = Field(default=1, ge=1)
    
    # Network checks
    network_baseline: bool = Field(default=False)
    
    # Custom commands
    custom_commands: list[dict] = Field(default_factory=list)


class CephFSMountMethod(str, Enum):
    """CephFS mount method."""
    KERNEL = "kernel"  # mount -t ceph (default, faster)
    FUSE = "fuse"      # ceph-fuse (more portable)


class MountConfig(BaseModel):
    """Filesystem mount configuration for file workloads."""
    filesystem_type: FilesystemType = Field(..., description="Type of filesystem to mount")
    mount_point: str = Field(default="/mnt/scale_test", description="Local mount point on clients")
    
    # CephFS specific
    cephfs_path: Optional[str] = Field(default="/", description="CephFS subpath to mount")
    cephfs_user: str = Field(default="admin", description="CephFS user")
    cephfs_secret_file: Optional[str] = Field(default=None, description="Path to secret file")
    mount_method: CephFSMountMethod = Field(
        default=CephFSMountMethod.KERNEL, 
        description="Mount method: kernel (mount -t ceph) or fuse (ceph-fuse)"
    )
    
    # NFS specific
    nfs_server: Optional[str] = Field(default=None, description="NFS server address")
    nfs_export: Optional[str] = Field(default=None, description="NFS export path")
    nfs_version: str = Field(default="4.1", description="NFS version")
    
    # GlusterFS specific
    gluster_volume: Optional[str] = Field(default=None, description="Gluster volume name")
    gluster_servers: list[str] = Field(default_factory=list, description="Gluster server addresses")
    
    # Common options
    mount_options: str = Field(default="", description="Additional mount options")
    auto_unmount: bool = Field(default=True, description="Unmount after test completion")


class WorkloadConfig(BaseModel):
    """Complete workload configuration."""
    name: str = Field(..., description="Workload name")
    description: Optional[str] = Field(default=None)
    
    # Cluster reference
    cluster_name: str = Field(..., description="Target cluster name")
    
    # Storage type
    storage_type: StorageWorkloadType = Field(
        default=StorageWorkloadType.BLOCK,
        description="Type of storage workload"
    )
    
    # Mount configuration (for file workloads)
    mount: Optional[MountConfig] = Field(
        default=None,
        description="Filesystem mount configuration (required for file workloads)"
    )
    
    # Tool selection
    tool: WorkloadTool = Field(default=WorkloadTool.FIO)
    
    # Fill cluster configuration (for fill_cluster workload)
    fill_cluster: Optional[FillClusterConfig] = Field(
        default=None,
        description="Fill cluster workload configuration"
    )
    
    # I/O configuration
    io: IOConfig = Field(default_factory=IOConfig)
    
    # Test parameters
    test: TestConfig = Field(default_factory=TestConfig)
    
    # Client selection
    clients: ClientSelection = Field(default_factory=ClientSelection)
    
    # Optional configurations
    scaling: Optional[ScalingConfig] = Field(default=None)
    network: Optional[NetworkConfig] = Field(default=None)
    prechecks: PrecheckConfig = Field(default_factory=PrecheckConfig)
    
    # Custom FIO options (passed directly to FIO)
    fio_extra_options: dict[str, str] = Field(default_factory=dict)
    
    # Tags
    tags: dict[str, str] = Field(default_factory=dict)
    
    # Network baseline (captured during workload creation for performance comparison)
    network_baseline: Optional[dict] = Field(
        default=None,
        description="Network profiling baseline for performance comparison"
    )
    
    @property
    def is_block_workload(self) -> bool:
        """Check if this is a block storage workload."""
        return self.storage_type == StorageWorkloadType.BLOCK
    
    @property
    def is_file_workload(self) -> bool:
        """Check if this is a file storage workload."""
        return self.storage_type == StorageWorkloadType.FILE
    
    @property
    def is_object_workload(self) -> bool:
        """Check if this is an object storage workload."""
        return self.storage_type == StorageWorkloadType.OBJECT
    
    @property
    def fio_directory(self) -> str:
        """Get the directory for FIO test files."""
        if self.is_file_workload and self.mount:
            return self.mount.mount_point
        return "/tmp/fio_test"
