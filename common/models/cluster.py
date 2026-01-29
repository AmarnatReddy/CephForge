"""Cluster and storage configuration models."""

from __future__ import annotations

from enum import Enum
from typing import Optional, Union
from pydantic import BaseModel, Field


class StorageType(str, Enum):
    """Type of storage being tested."""
    BLOCK = "block"
    FILE = "file"
    OBJECT = "object"


class StorageBackend(str, Enum):
    """Storage backend implementation."""
    # Block storage
    CEPH_RBD = "ceph_rbd"
    ISCSI = "iscsi"
    NVMEOF = "nvmeof"
    
    # File storage
    NFS = "nfs"
    CEPHFS = "cephfs"
    GLUSTERFS = "glusterfs"
    
    # Object storage
    S3 = "s3"
    SWIFT = "swift"
    MINIO = "minio"


class CephConnection(BaseModel):
    """Ceph cluster connection configuration."""
    monitors: list[str] = Field(..., description="List of monitor addresses")
    user: str = Field(default="admin", description="Ceph user name")
    keyring_path: str = Field(
        default="/etc/ceph/ceph.client.admin.keyring",
        description="Path to keyring file"
    )
    conf_path: str = Field(
        default="/etc/ceph/ceph.conf",
        description="Path to ceph.conf"
    )
    pool: Optional[str] = Field(default=None, description="Default pool name")
    repo_url: Optional[str] = Field(
        default=None, 
        description="Ceph yum/dnf repo URL for installing ceph-common on clients"
    )


class NFSConnection(BaseModel):
    """NFS connection configuration."""
    server: str = Field(..., description="NFS server hostname or IP")
    export_path: str = Field(..., description="NFS export path")
    mount_options: str = Field(
        default="rw,sync,hard,intr",
        description="Mount options"
    )
    mount_point: str = Field(
        default="/mnt/nfs_test",
        description="Local mount point"
    )


class S3Connection(BaseModel):
    """S3/Object storage connection configuration."""
    endpoint: str = Field(..., description="S3 endpoint URL")
    access_key: str = Field(..., description="Access key")
    secret_key: str = Field(..., description="Secret key")
    bucket: str = Field(..., description="Bucket name")
    region: str = Field(default="us-east-1", description="Region")
    use_ssl: bool = Field(default=True, description="Use SSL/TLS")
    verify_ssl: bool = Field(default=True, description="Verify SSL certificate")


class InstallerNode(BaseModel):
    """Installer/admin node connection for cluster management."""
    host: str = Field(..., description="Installer node IP or hostname")
    username: str = Field(default="root", description="SSH username")
    password: Optional[str] = Field(default=None, description="SSH password")
    key_path: Optional[str] = Field(default=None, description="Path to SSH private key")
    port: int = Field(default=22, description="SSH port")


class ClusterConfig(BaseModel):
    """Storage cluster configuration."""
    name: str = Field(..., description="Cluster name")
    storage_type: StorageType = Field(..., description="Type of storage")
    backend: StorageBackend = Field(..., description="Storage backend")
    description: Optional[str] = Field(default=None, description="Description")
    
    # Connection details (one of these based on backend)
    ceph: Optional[CephConnection] = Field(default=None)
    nfs: Optional[NFSConnection] = Field(default=None)
    s3: Optional[S3Connection] = Field(default=None)
    
    # Installer node for SSH-based operations
    installer_node: Optional[InstallerNode] = Field(default=None)
    
    # Additional metadata
    tags: dict[str, str] = Field(default_factory=dict)
    
    def get_connection(self) -> CephConnection | NFSConnection | S3Connection:
        """Get the appropriate connection config based on backend."""
        if self.backend in [StorageBackend.CEPH_RBD, StorageBackend.CEPHFS]:
            if not self.ceph:
                raise ValueError("Ceph connection config required")
            return self.ceph
        elif self.backend == StorageBackend.NFS:
            if not self.nfs:
                raise ValueError("NFS connection config required")
            return self.nfs
        elif self.backend in [StorageBackend.S3, StorageBackend.SWIFT, StorageBackend.MINIO]:
            if not self.s3:
                raise ValueError("S3 connection config required")
            return self.s3
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")
