"""Unified data storage layer using SQLite and file-based storage."""

from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional, Any, List, Tuple, Dict

import aiosqlite
import yaml

from common.models.client import Client
from common.models.cluster import ClusterConfig
from common.models.execution import Execution, ExecutionStatus
from common.models.workload import WorkloadConfig
from common.utils import generate_execution_id, ensure_dir

logger = logging.getLogger(__name__)

# SQLite schema
SCHEMA_SQL = """
-- Registered clients
CREATE TABLE IF NOT EXISTS clients (
    id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    ip_address TEXT,
    status TEXT DEFAULT 'unknown',
    agent_version TEXT,
    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_heartbeat TIMESTAMP,
    error_message TEXT,
    deployment_status TEXT,
    deployment_step TEXT,
    metadata JSON
);

CREATE INDEX IF NOT EXISTS idx_clients_status ON clients(status);
CREATE INDEX IF NOT EXISTS idx_clients_hostname ON clients(hostname);

-- Execution history
CREATE TABLE IF NOT EXISTS executions (
    id TEXT PRIMARY KEY,
    name TEXT,
    status TEXT DEFAULT 'pending',
    workload_type TEXT,
    storage_backend TEXT,
    cluster_name TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_seconds INTEGER,
    client_count INTEGER,
    total_iops INTEGER,
    avg_latency_us REAL,
    total_throughput_mbps REAL,
    config_path TEXT,
    metrics_path TEXT,
    report_path TEXT,
    error_message TEXT,
    network_baseline JSON,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_executions_status ON executions(status);
CREATE INDEX IF NOT EXISTS idx_executions_started ON executions(started_at);

-- Precheck history
CREATE TABLE IF NOT EXISTS prechecks (
    id TEXT PRIMARY KEY,
    execution_id TEXT,
    status TEXT,
    cluster_health TEXT,
    clients_online INTEGER,
    clients_total INTEGER,
    report_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (execution_id) REFERENCES executions(id)
);
"""


class DataStore:
    """Unified data access layer using files + SQLite."""
    
    def __init__(self, base_path: str | Path):
        self.base_path = Path(base_path)
        self.db_path = self.base_path / "scale.db"
        self._init_directories()
        self._init_database_sync()
    
    def _init_directories(self) -> None:
        """Create required directories."""
        dirs = [
            "config/clusters",
            "config/clients",
            "config/workloads/templates",
            "config/workloads/custom",
            "executions",
            "logs",
        ]
        for d in dirs:
            ensure_dir(self.base_path / d)
        logger.info(f"Initialized data directories at {self.base_path}")
    
    def _init_database_sync(self) -> None:
        """Initialize SQLite database synchronously."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(SCHEMA_SQL)
            conn.commit()
            
            # Run migrations for existing databases
            self._run_migrations_sync(conn)
            
            logger.info(f"Initialized SQLite database at {self.db_path}")
        finally:
            conn.close()
    
    def _run_migrations_sync(self, conn: sqlite3.Connection) -> None:
        """Run database migrations for schema updates."""
        cursor = conn.cursor()
        
        # Check if error_message column exists in executions table
        cursor.execute("PRAGMA table_info(executions)")
        columns = {row[1] for row in cursor.fetchall()}
        
        if 'error_message' not in columns:
            logger.info("Adding error_message column to executions table")
            cursor.execute("ALTER TABLE executions ADD COLUMN error_message TEXT")
            conn.commit()
        
        # Check if error_message column exists in clients table
        cursor.execute("PRAGMA table_info(clients)")
        client_columns = {row[1] for row in cursor.fetchall()}
        
        if 'error_message' not in client_columns:
            logger.info("Adding error_message column to clients table")
            cursor.execute("ALTER TABLE clients ADD COLUMN error_message TEXT")
            conn.commit()
        
        if 'deployment_status' not in client_columns:
            logger.info("Adding deployment_status column to clients table")
            cursor.execute("ALTER TABLE clients ADD COLUMN deployment_status TEXT")
            conn.commit()
        
        if 'deployment_step' not in client_columns:
            logger.info("Adding deployment_step column to clients table")
            cursor.execute("ALTER TABLE clients ADD COLUMN deployment_step TEXT")
            conn.commit()
        
        # Add network_baseline column to executions table
        if 'network_baseline' not in columns:
            logger.info("Adding network_baseline column to executions table")
            cursor.execute("ALTER TABLE executions ADD COLUMN network_baseline JSON")
            conn.commit()
    
    @contextmanager
    def _get_db_sync(self):
        """Get a synchronous database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    @contextmanager
    def _get_db_context(self):
        """Synchronous database context manager."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()
    
    # ==================== Clusters ====================
    
    def get_clusters(self) -> list[ClusterConfig]:
        """Get all registered clusters."""
        clusters = []
        cluster_dir = self.base_path / "config/clusters"
        
        for f in cluster_dir.glob("*.yaml"):
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)
                    if data:
                        clusters.append(ClusterConfig(**data))
            except Exception as e:
                logger.error(f"Error loading cluster config {f}: {e}")
        
        return clusters
    
    def get_cluster(self, name: str) -> Optional[ClusterConfig]:
        """Get a cluster by name."""
        path = self.base_path / f"config/clusters/{name}.yaml"
        if not path.exists():
            return None
        
        with open(path) as f:
            data = yaml.safe_load(f)
            return ClusterConfig(**data) if data else None
    
    def save_cluster(self, cluster: ClusterConfig) -> str:
        """Save a cluster configuration."""
        path = self.base_path / f"config/clusters/{cluster.name}.yaml"
        with open(path, 'w') as f:
            # Use mode='json' to serialize enums as strings
            yaml.dump(cluster.model_dump(exclude_none=True, mode='json'), f, default_flow_style=False)
        logger.info(f"Saved cluster config: {cluster.name}")
        return str(path)
    
    def delete_cluster(self, name: str) -> bool:
        """Delete a cluster configuration."""
        path = self.base_path / f"config/clusters/{name}.yaml"
        if path.exists():
            path.unlink()
            logger.info(f"Deleted cluster config: {name}")
            return True
        return False
    
    # ==================== Clients ====================
    
    def get_clients_config(self) -> list[dict]:
        """Get client configurations from YAML file."""
        clients_file = self.base_path / "config/clients/clients.yaml"
        if not clients_file.exists():
            return []
        
        with open(clients_file) as f:
            data = yaml.safe_load(f) or {}
        
        return data.get("clients", [])
    
    def save_clients_config(self, clients: list[dict], defaults: dict = None) -> None:
        """Save client configurations to YAML file."""
        clients_file = self.base_path / "config/clients/clients.yaml"
        
        data = {"clients": clients}
        if defaults:
            data["defaults"] = defaults
        
        with open(clients_file, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
        
        logger.info(f"Saved {len(clients)} client configurations")
    
    async def get_clients(self) -> list[dict]:
        """Get all clients with their current status from DB."""
        clients_config = self.get_clients_config()
        
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT id, status, agent_version, last_heartbeat, error_message, deployment_status, deployment_step FROM clients"
            )
            rows = await cursor.fetchall()
            status_map = {row["id"]: dict(row) for row in rows}
        
        # Merge config with status
        for client in clients_config:
            client_id = client.get("id")
            if client_id in status_map:
                client.update(status_map[client_id])
        
        return clients_config
    
    async def update_client_status(
        self,
        client_id: str,
        status: str,
        agent_version: str = None,
        hostname: str = None,
        error_message: str = None
    ) -> None:
        """Update client status in SQLite."""
        async with aiosqlite.connect(self.db_path) as conn:
            # Clear error message if status is online/busy
            if status in ["online", "busy"] and error_message is None:
                error_message = ""
            
            await conn.execute("""
                INSERT INTO clients (id, hostname, status, agent_version, last_heartbeat, registered_at, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    agent_version = COALESCE(excluded.agent_version, agent_version),
                    last_heartbeat = excluded.last_heartbeat,
                    error_message = COALESCE(excluded.error_message, error_message)
            """, (
                client_id,
                hostname or client_id,
                status,
                agent_version,
                datetime.utcnow().isoformat(),
                datetime.utcnow().isoformat(),
                error_message
            ))
            await conn.commit()
    
    async def update_deployment_status(
        self,
        client_id: str,
        deployment_status: str,
        deployment_step: str = None,
    ) -> None:
        """Update client deployment status."""
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                UPDATE clients SET
                    deployment_status = ?,
                    deployment_step = ?,
                    last_heartbeat = ?
                WHERE id = ?
            """, (
                deployment_status,
                deployment_step,
                datetime.utcnow().isoformat(),
                client_id,
            ))
            await conn.commit()

    async def get_client_status(self, client_id: str) -> Optional[dict]:
        """Get client status from SQLite."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM clients WHERE id = ?", (client_id,)
            )
            row = await cursor.fetchone()
            return dict(row) if row else None
    
    # ==================== Workloads ====================
    
    def get_workload_templates(self) -> list[dict]:
        """Get all workload templates."""
        templates = []
        templates_dir = self.base_path / "config/workloads/templates"
        
        for f in templates_dir.glob("*.yaml"):
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)
                    if data:
                        data["_path"] = str(f)
                        data["_is_template"] = True
                        templates.append(data)
            except Exception as e:
                logger.error(f"Error loading template {f}: {e}")
        
        return templates
    
    def get_workloads(self) -> list[dict]:
        """Get all workloads (templates + custom)."""
        workloads = self.get_workload_templates()
        
        custom_dir = self.base_path / "config/workloads/custom"
        for f in custom_dir.glob("*.yaml"):
            try:
                with open(f) as file:
                    data = yaml.safe_load(file)
                    if data:
                        data["_path"] = str(f)
                        data["_is_template"] = False
                        workloads.append(data)
            except Exception as e:
                logger.error(f"Error loading workload {f}: {e}")
        
        return workloads
    
    def get_workload(self, name: str) -> Optional[dict]:
        """Get a workload by name."""
        # Check templates first, then custom
        for subdir in ["templates", "custom"]:
            path = self.base_path / f"config/workloads/{subdir}/{name}.yaml"
            if path.exists():
                with open(path) as f:
                    return yaml.safe_load(f)
        return None
    
    def save_workload(
        self,
        name: str,
        config: dict,
        is_template: bool = False
    ) -> str:
        """Save a workload configuration."""
        subdir = "templates" if is_template else "custom"
        path = self.base_path / f"config/workloads/{subdir}/{name}.yaml"
        
        with open(path, 'w') as f:
            yaml.dump(config, f, default_flow_style=False)
        
        logger.info(f"Saved workload: {name}")
        return str(path)
    
    def delete_workload(self, name: str) -> bool:
        """Delete a workload configuration."""
        for subdir in ["custom", "templates"]:
            path = self.base_path / f"config/workloads/{subdir}/{name}.yaml"
            if path.exists():
                path.unlink()
                logger.info(f"Deleted workload: {name}")
                return True
        return False
    
    # ==================== Executions ====================
    
    async def create_execution(
        self,
        name: str,
        workload_config: dict,
        cluster_name: str,
        network_baseline: dict = None
    ) -> tuple[str, Path]:
        """Create a new execution and return (id, path)."""
        execution_id = generate_execution_id()
        exec_dir = self.base_path / f"executions/{execution_id}"
        
        # Create directories
        ensure_dir(exec_dir)
        ensure_dir(exec_dir / "metrics")
        ensure_dir(exec_dir / "metrics/clients")
        
        # Save config snapshot
        config_path = exec_dir / "config.yaml"
        with open(config_path, 'w') as f:
            yaml.dump(workload_config, f, default_flow_style=False)
        
        # Record in SQLite
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute("""
                INSERT INTO executions (
                    id, name, status, workload_type, storage_backend, cluster_name,
                    config_path, metrics_path, network_baseline, created_at
                )
                VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?)
            """, (
                execution_id,
                name,
                workload_config.get("storage", {}).get("type"),
                workload_config.get("storage", {}).get("backend"),
                cluster_name,
                str(config_path),
                str(exec_dir / "metrics"),
                json.dumps(network_baseline) if network_baseline else None,
                datetime.utcnow().isoformat()
            ))
            await conn.commit()
        
        logger.info(f"Created execution: {execution_id}")
        return execution_id, exec_dir
    
    async def update_execution_status(
        self,
        execution_id: str,
        status: str,
        **kwargs
    ) -> None:
        """Update execution status and optional fields."""
        fields = ["status = ?"]
        values = [status]
        
        if status == ExecutionStatus.RUNNING.value and "started_at" not in kwargs:
            kwargs["started_at"] = datetime.utcnow().isoformat()
        
        if status in [ExecutionStatus.COMPLETED.value, ExecutionStatus.FAILED.value, 
                      ExecutionStatus.CANCELLED.value]:
            kwargs["completed_at"] = datetime.utcnow().isoformat()
        
        for key, value in kwargs.items():
            fields.append(f"{key} = ?")
            values.append(value)
        
        values.append(execution_id)
        
        async with aiosqlite.connect(self.db_path) as conn:
            await conn.execute(
                f"UPDATE executions SET {', '.join(fields)} WHERE id = ?",
                values
            )
            await conn.commit()
    
    async def get_executions(self, limit: int = 50) -> list[dict]:
        """Get recent executions."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute("""
                SELECT * FROM executions 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]
    
    async def get_execution(self, execution_id: str) -> Optional[dict]:
        """Get execution by ID."""
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            cursor = await conn.execute(
                "SELECT * FROM executions WHERE id = ?",
                (execution_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            
            result = dict(row)
            # Parse network_baseline JSON
            if result.get("network_baseline"):
                try:
                    result["network_baseline"] = json.loads(result["network_baseline"])
                except (json.JSONDecodeError, TypeError):
                    result["network_baseline"] = None
            return result
    
    # ==================== Metrics ====================
    
    def append_metrics(self, execution_id: str, metrics: dict) -> None:
        """Append aggregated metrics to JSON Lines file."""
        metrics_file = self.base_path / f"executions/{execution_id}/metrics/aggregate.jsonl"
        with open(metrics_file, 'a') as f:
            f.write(json.dumps(metrics) + "\n")
    
    def append_client_metrics(
        self,
        execution_id: str,
        client_id: str,
        metrics: dict
    ) -> None:
        """Append per-client metrics to JSON Lines file."""
        metrics_file = (
            self.base_path / f"executions/{execution_id}/metrics/clients/{client_id}.jsonl"
        )
        with open(metrics_file, 'a') as f:
            f.write(json.dumps(metrics) + "\n")
    
    def read_metrics(
        self,
        execution_id: str,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> list[dict]:
        """Read metrics from JSON Lines file."""
        metrics_file = self.base_path / f"executions/{execution_id}/metrics/aggregate.jsonl"
        if not metrics_file.exists():
            return []
        
        metrics = []
        with open(metrics_file) as f:
            for line in f:
                if line.strip():
                    try:
                        m = json.loads(line)
                        # Filter by time if specified
                        if start_time or end_time:
                            ts = datetime.fromisoformat(m.get("ts", "").replace("Z", "+00:00"))
                            if start_time and ts < start_time:
                                continue
                            if end_time and ts > end_time:
                                continue
                        metrics.append(m)
                    except json.JSONDecodeError:
                        continue
        
        return metrics
    
    # ==================== Summary & Reports ====================
    
    def save_summary(self, execution_id: str, summary: dict) -> None:
        """Save execution summary."""
        summary_file = self.base_path / f"executions/{execution_id}/summary.json"
        with open(summary_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        logger.info(f"Saved summary for execution: {execution_id}")
    
    def get_summary(self, execution_id: str) -> Optional[dict]:
        """Get execution summary."""
        summary_file = self.base_path / f"executions/{execution_id}/summary.json"
        if not summary_file.exists():
            return None
        
        with open(summary_file) as f:
            return json.load(f)
    
    def save_command_log(self, execution_id: str, commands: list[dict]) -> None:
        """Save executed commands log."""
        log_file = self.base_path / f"executions/{execution_id}/commands.json"
        with open(log_file, 'w') as f:
            json.dump(commands, f, indent=2, default=str)
        
        logger.info(f"Saved {len(commands)} commands for execution: {execution_id}")
    
    def get_command_log(self, execution_id: str) -> list[dict]:
        """Get executed commands log."""
        log_file = self.base_path / f"executions/{execution_id}/commands.json"
        if not log_file.exists():
            return []
        
        with open(log_file) as f:
            return json.load(f)
    
    def save_precheck_report(self, execution_id: str, report: dict) -> None:
        """Save precheck report."""
        report_file = self.base_path / f"executions/{execution_id}/precheck_report.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)
        
        # Also record in SQLite for quick queries
        with self._get_db_sync() as conn:
            conn.execute("""
                INSERT INTO prechecks (id, execution_id, status, cluster_health,
                                      clients_online, clients_total, report_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                f"precheck_{execution_id}",
                execution_id,
                report.get("overall_status"),
                report.get("cluster", {}).get("health"),
                report.get("clients", {}).get("online"),
                report.get("clients", {}).get("total"),
                str(report_file)
            ))
        
        logger.info(f"Saved precheck report for execution: {execution_id}")
    
    def get_precheck_report(self, execution_id: str) -> Optional[dict]:
        """Get precheck report."""
        report_file = self.base_path / f"executions/{execution_id}/precheck_report.json"
        if not report_file.exists():
            return None
        
        with open(report_file) as f:
            return json.load(f)
    
    # ==================== Logs ====================
    
    def get_log_path(self, execution_id: str = None) -> Path:
        """Get log file path."""
        if execution_id:
            return self.base_path / f"logs/executions/{execution_id}.log"
        return self.base_path / "logs/manager.log"
    
    def write_log(self, execution_id: str, message: str) -> None:
        """Write to execution log file."""
        log_file = self.get_log_path(execution_id)
        ensure_dir(log_file.parent)
        
        timestamp = datetime.utcnow().isoformat()
        with open(log_file, 'a') as f:
            f.write(f"[{timestamp}] {message}\n")
