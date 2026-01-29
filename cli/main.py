"""Scale Framework CLI - Command line interface."""

import argparse
import json
import sys
from typing import Optional

import httpx


def get_client(base_url: str = "http://localhost:8000") -> httpx.Client:
    """Get HTTP client for API calls."""
    return httpx.Client(base_url=base_url, timeout=30.0)


def cmd_status(args):
    """Show system status."""
    with get_client(args.url) as client:
        try:
            # Get health
            health = client.get("/api/v1/system/health").json()
            print(f"System Status: {health.get('status', 'unknown').upper()}")
            
            # Get clients
            clients = client.get("/api/v1/clients").json()
            print(f"Clients: {clients.get('online', 0)}/{clients.get('total', 0)} online")
            
            # Get clusters
            clusters = client.get("/api/v1/clusters").json()
            print(f"Clusters: {clusters.get('total', 0)} registered")
            
            # Get executions
            executions = client.get("/api/v1/executions?limit=5").json()
            running = [e for e in executions.get('executions', []) if e.get('status') == 'running']
            if running:
                print(f"\nActive Executions:")
                for e in running:
                    print(f"  - {e.get('name')} ({e.get('id')})")
            
        except httpx.ConnectError:
            print(f"Error: Cannot connect to manager at {args.url}")
            sys.exit(1)


def cmd_clusters(args):
    """List clusters."""
    with get_client(args.url) as client:
        clusters = client.get("/api/v1/clusters").json()
        
        if not clusters.get('clusters'):
            print("No clusters registered")
            return
        
        print(f"{'Name':<20} {'Type':<10} {'Backend':<15} {'Status':<10}")
        print("-" * 60)
        for c in clusters.get('clusters', []):
            print(f"{c.get('name', ''):<20} {c.get('storage_type', ''):<10} {c.get('backend', ''):<15} {'OK':<10}")


def cmd_clients(args):
    """List clients."""
    with get_client(args.url) as client:
        clients = client.get("/api/v1/clients").json()
        
        if not clients.get('clients'):
            print("No clients registered")
            return
        
        print(f"{'ID':<15} {'Hostname':<20} {'Status':<10} {'Agent':<10}")
        print("-" * 60)
        for c in clients.get('clients', []):
            print(f"{c.get('id', ''):<15} {c.get('hostname', ''):<20} {c.get('status', 'unknown'):<10} {c.get('agent_version', '—'):<10}")


def cmd_check_clients(args):
    """Check client health."""
    with get_client(args.url) as client:
        print("Checking all clients...")
        result = client.post("/api/v1/clients/health/all").json()
        
        summary = result.get('summary', {})
        print(f"\nResults: {summary.get('online', 0)}/{summary.get('total_clients', 0)} online")
        
        for r in result.get('results', []):
            status = "✓" if r.get('status') == 'online' else "✗"
            print(f"  {status} {r.get('hostname', '')} ({r.get('client_id', '')})")


def cmd_workloads(args):
    """List workloads."""
    with get_client(args.url) as client:
        workloads = client.get("/api/v1/workloads").json()
        
        print("Templates:")
        for w in workloads.get('workloads', []):
            if w.get('_is_template'):
                print(f"  - {w.get('name')}: {w.get('description', 'No description')}")
        
        print("\nCustom Workloads:")
        custom = [w for w in workloads.get('workloads', []) if not w.get('_is_template')]
        if custom:
            for w in custom:
                print(f"  - {w.get('name')}: {w.get('description', 'No description')}")
        else:
            print("  (none)")


def cmd_executions(args):
    """List executions."""
    with get_client(args.url) as client:
        executions = client.get(f"/api/v1/executions?limit={args.limit}").json()
        
        if not executions.get('executions'):
            print("No executions found")
            return
        
        print(f"{'ID':<30} {'Name':<25} {'Status':<12} {'IOPS':<12} {'Duration':<10}")
        print("-" * 90)
        for e in executions.get('executions', []):
            iops = e.get('total_iops', 0)
            iops_str = f"{iops:,}" if iops else "—"
            duration = e.get('duration_seconds', 0)
            duration_str = f"{duration}s" if duration else "—"
            print(f"{e.get('id', ''):<30} {e.get('name', ''):<25} {e.get('status', ''):<12} {iops_str:<12} {duration_str:<10}")


def cmd_run(args):
    """Start a new execution."""
    with get_client(args.url) as client:
        data = {
            "workload_name": args.workload,
            "name": args.name,
            "run_prechecks": not args.skip_prechecks,
        }
        
        print(f"Starting execution with workload: {args.workload}")
        result = client.post("/api/v1/executions", json=data).json()
        
        print(f"Execution started: {result.get('execution_id')}")
        print(f"Status: {result.get('status')}")


def cmd_stop(args):
    """Stop an execution."""
    with get_client(args.url) as client:
        result = client.post(f"/api/v1/executions/{args.id}/stop").json()
        print(result.get('message', 'Stop signal sent'))


def cmd_prechecks(args):
    """Run prechecks."""
    with get_client(args.url) as client:
        data = {
            "cluster_name": args.cluster,
            "check_cluster": True,
            "check_clients": True,
        }
        
        print(f"Running prechecks for cluster: {args.cluster}")
        result = client.post("/api/v1/prechecks/run", json=data).json()
        
        print(f"\nStatus: {result.get('overall_status', 'unknown').upper()}")
        print(f"Can Proceed: {'Yes' if result.get('can_proceed') else 'No'}")
        
        if result.get('warnings'):
            print("\nWarnings:")
            for w in result.get('warnings', []):
                print(f"  ⚠ {w}")
        
        if result.get('blocking_issues'):
            print("\nBlocking Issues:")
            for i in result.get('blocking_issues', []):
                print(f"  ✗ {i}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Scale Testing Framework CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-u", "--url",
        default="http://localhost:8000",
        help="Manager URL (default: http://localhost:8000)"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # status
    status_parser = subparsers.add_parser("status", help="Show system status")
    status_parser.set_defaults(func=cmd_status)
    
    # clusters
    clusters_parser = subparsers.add_parser("clusters", help="List clusters")
    clusters_parser.set_defaults(func=cmd_clusters)
    
    # clients
    clients_parser = subparsers.add_parser("clients", help="List clients")
    clients_parser.set_defaults(func=cmd_clients)
    
    # check-clients
    check_parser = subparsers.add_parser("check-clients", help="Check client health")
    check_parser.set_defaults(func=cmd_check_clients)
    
    # workloads
    workloads_parser = subparsers.add_parser("workloads", help="List workloads")
    workloads_parser.set_defaults(func=cmd_workloads)
    
    # executions
    exec_parser = subparsers.add_parser("executions", help="List executions")
    exec_parser.add_argument("-l", "--limit", type=int, default=20, help="Limit results")
    exec_parser.set_defaults(func=cmd_executions)
    
    # run
    run_parser = subparsers.add_parser("run", help="Start new execution")
    run_parser.add_argument("workload", help="Workload name")
    run_parser.add_argument("-n", "--name", help="Execution name")
    run_parser.add_argument("--skip-prechecks", action="store_true", help="Skip prechecks")
    run_parser.set_defaults(func=cmd_run)
    
    # stop
    stop_parser = subparsers.add_parser("stop", help="Stop execution")
    stop_parser.add_argument("id", help="Execution ID")
    stop_parser.set_defaults(func=cmd_stop)
    
    # prechecks
    precheck_parser = subparsers.add_parser("prechecks", help="Run prechecks")
    precheck_parser.add_argument("cluster", help="Cluster name")
    precheck_parser.set_defaults(func=cmd_prechecks)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == "__main__":
    main()
