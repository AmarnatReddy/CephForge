# CephForge

A scalable testing framework for storage products supporting Block, File, and Object storage with dynamic client scaling and centralized management.

## Features

- **Multi-Storage Support**: Test Block (Ceph RBD, iSCSI), File (NFS, CephFS), and Object (S3, Swift) storage
- **Dynamic Scaling**: Scale client nodes up/down during test execution
- **Centralized Control**: Manager node orchestrates all client agents
- **Comprehensive Prechecks**: Cluster health, client connectivity, and network validation
- **Real-time Metrics**: IOPS, throughput, latency with live streaming
- **Multiple Workload Tools**: FIO, IOzone, dd, COSBench, and custom scripts
- **Web UI**: Interactive dashboard for configuration and monitoring
- **Lightweight Storage**: SQLite + file-based storage (no PostgreSQL required)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Manager Node                             │
│  ┌───────────┐ ┌───────────┐ ┌───────────┐ ┌───────────────────┐│
│  │ REST API  │ │ Execution │ │ Precheck  │ │   Data Store      ││
│  │ (FastAPI) │ │  Engine   │ │  Runner   │ │(SQLite + Files)   ││
│  └───────────┘ └───────────┘ └───────────┘ └───────────────────┘│
│                         │                                        │
│                    Redis Pub/Sub                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        ▼                    ▼                    ▼
┌───────────────┐   ┌───────────────┐   ┌───────────────┐
│    Agent 1    │   │    Agent 2    │   │    Agent N    │
│ ┌───────────┐ │   │ ┌───────────┐ │   │ ┌───────────┐ │
│ │ Executor  │ │   │ │ Executor  │ │   │ │ Executor  │ │
│ │(FIO/dd/..)│ │   │ │(FIO/dd/..)│ │   │ │(FIO/dd/..)│ │
│ └───────────┘ │   │ └───────────┘ │   │ └───────────┘ │
│ ┌───────────┐ │   │ ┌───────────┐ │   │ ┌───────────┐ │
│ │ Reporter  │ │   │ │ Reporter  │ │   │ │ Reporter  │ │
│ └───────────┘ │   │ └───────────┘ │   │ └───────────┘ │
└───────────────┘   └───────────────┘   └───────────────┘
        │                    │                    │
        └────────────────────┴────────────────────┘
                             │
                    ┌────────▼────────┐
                    │  Storage Under  │
                    │      Test       │
                    │ (Ceph/NFS/S3)   │
                    └─────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- Redis server
- Node.js 18+ (for UI)

### Installation

1. **Clone and install dependencies**:
```bash
cd scale_framework
pip install -r requirements.txt
```

2. **Start Redis**:
```bash
# Using Docker
docker run -d --name redis -p 6379:6379 redis:7-alpine

# Or using system Redis
sudo systemctl start redis
```

3. **Start the Manager**:
```bash
python -m manager.main
```

4. **Start the Agent** (on each client node):
```bash
SCALE_AGENT_REDIS_URL=redis://manager-ip:6379 python -m agent.main
```

5. **Start the UI** (optional):
```bash
cd ui
npm install
npm run dev
```

### Using Docker Compose

```bash
cd docker
docker-compose up -d

# To include a local agent for testing
docker-compose --profile agent up -d
```

## Configuration

### Cluster Configuration

Create a cluster configuration in `data/config/clusters/`:

```yaml
# data/config/clusters/my_ceph.yaml
name: my_ceph
storage_type: block
backend: ceph_rbd

ceph:
  monitors:
    - "192.168.1.10:6789"
  user: admin
  keyring_path: "/etc/ceph/ceph.client.admin.keyring"
  conf_path: "/etc/ceph/ceph.conf"
  pool: "rbd"
```

### Client Configuration

Configure clients in `data/config/clients/clients.yaml`:

```yaml
defaults:
  ssh_user: root
  ssh_key_path: /path/to/key

clients:
  - id: client-01
    hostname: 192.168.1.101
  - id: client-02
    hostname: 192.168.1.102
```

### Workload Templates

Use predefined templates or create custom workloads:

```yaml
# data/config/workloads/custom/my_test.yaml
name: my_test
cluster_name: my_ceph
tool: fio

io:
  pattern: random
  block_size: "4k"
  read_percent: 70
  io_depth: 32
  num_jobs: 8

test:
  duration: 300
  file_size: "10G"

prechecks:
  cluster_health: true
  client_health: true
```

## API Reference

### Clusters
- `GET /api/v1/clusters` - List all clusters
- `POST /api/v1/clusters` - Register a cluster
- `GET /api/v1/clusters/{name}` - Get cluster details
- `GET /api/v1/clusters/{name}/health` - Get cluster health

### Clients
- `GET /api/v1/clients` - List all clients
- `POST /api/v1/clients` - Register clients
- `POST /api/v1/clients/health/all` - Check all clients

### Workloads
- `GET /api/v1/workloads` - List workloads
- `POST /api/v1/workloads` - Create workload
- `GET /api/v1/workloads/templates` - List templates

### Executions
- `GET /api/v1/executions` - List executions
- `POST /api/v1/executions` - Start execution
- `GET /api/v1/executions/{id}` - Get execution status
- `POST /api/v1/executions/{id}/stop` - Stop execution
- `POST /api/v1/executions/{id}/scale` - Scale clients

### Metrics
- `GET /api/v1/metrics/{id}` - Get metrics
- `GET /api/v1/metrics/{id}/latest` - Get latest metrics
- `WS /api/v1/metrics/live/{id}` - Live metrics stream

## Project Structure

```
scale_framework/
├── manager/                 # Manager service
│   ├── api/                 # REST API routes
│   ├── core/                # Execution engine
│   ├── prechecks/           # Health checks
│   ├── storage/             # Data store
│   ├── config.py
│   └── main.py
├── agent/                   # Agent service
│   ├── core/                # Executor & reporter
│   ├── network/             # Network profiling
│   ├── config.py
│   └── main.py
├── common/                  # Shared code
│   ├── models/              # Pydantic models
│   ├── messaging/           # Redis client
│   └── utils.py
├── ui/                      # React frontend
├── data/                    # Configuration & data
│   ├── config/
│   │   ├── clusters/
│   │   ├── clients/
│   │   └── workloads/
│   ├── executions/
│   └── logs/
├── docker/                  # Docker configs
├── requirements.txt
└── pyproject.toml
```

## Development

### Running Tests

#### Using pytest directly:
```bash
# Install test dependencies
pip install -e ".[dev]"

# Run all tests
pytest tests/

# Run with coverage
pytest tests/ --cov=. --cov-report=html

# Run specific test file
pytest tests/test_utils.py

# Run with verbose output
pytest tests/ -v
```

#### Using tox (recommended):
```bash
# Install tox
pip install tox

# Run tests for all Python versions
tox

# Run tests for specific Python version
tox -e py312

# Run tests with coverage
tox -e py312-cov

# Run linting
tox -e lint

# Run type checking
tox -e typecheck

# Run all checks (tests, lint, typecheck)
tox -e all

# Fast test run (single version, stop on first failure)
tox -e fast
```

### Code Formatting
```bash
# Format code
black manager/ agent/ common/ tests/

# Check formatting
black --check manager/ agent/ common/ tests/

# Lint code
ruff check manager/ agent/ common/ tests/

# Fix linting issues
ruff check --fix manager/ agent/ common/ tests/
```

## Environment Variables

### Manager
- `SCALE_DATA_PATH` - Data directory (default: `./data`)
- `SCALE_REDIS_URL` - Redis URL (default: `redis://localhost:6379`)
- `SCALE_HOST` - Bind host (default: `0.0.0.0`)
- `SCALE_PORT` - Bind port (default: `8000`)
- `SCALE_LOG_LEVEL` - Log level (default: `INFO`)

### Agent
- `SCALE_AGENT_ID` - Agent identifier (default: hostname)
- `SCALE_AGENT_REDIS_URL` - Redis URL
- `SCALE_AGENT_PORT` - Agent port (default: `8080`)
- `SCALE_AGENT_WORK_DIR` - Work directory (default: `/tmp/scale_agent`)

## License

MIT License
