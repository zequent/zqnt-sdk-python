# Development Guide

This guide provides instructions for developing and contributing to the ZQNT Edge Python SDK.

## Prerequisites

- Python 3.12+
- pip or uv (for package management)
- Git
- Docker (optional, for running Redis tests)

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/Zequent/zqnt-framework.git
cd sdks/edge/edge-python-sdk
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate # On Windows: .venv\Scripts\activate
```

Or with uv:

```bash
uv venv
```

### 3. Install dependencies

For development with all tools:

```bash
pip install -e ".[dev,redis]"
```

Or with uv:

```bash
uv sync --all-extras
```

## Protobuf Code Generation

The SDK includes pre-generated gRPC stubs from the `zqnt-protos` submodule. If you need to regenerate them after proto changes:

```bash
bash scripts/generate_protos.sh
```

This script:
1. Compiles `.proto` files to Python
2. Fixes import paths for relative imports
3. Creates necessary `__init__.py` markers
4. Ensures IDE compatibility

## Running Tests

### All tests

```bash
pytest tests/ -v
```

### With coverage

```bash
pytest tests/ -v --cov=edge_sdk --cov-report=html
```

Then open `htmlcov/index.html` to view the report.

### Specific test file

```bash
pytest tests/unit/test_adapter.py -v
```

### Specific test

```bash
pytest tests/unit/test_adapter.py::test_auto_capabilities_only_includes_overridden -v
```

### Integration tests only

```bash
pytest tests/integration/ -v
```

### Unit tests only

```bash
pytest tests/unit/ -v
```

## Code Quality

### Linting with ruff

Check for style violations:

```bash
ruff check .
```

### Formatting with ruff

Auto-fix style issues:

```bash
ruff format .
```

### Full check (lint + format check)

```bash
ruff check .
ruff format --check .
```

### Type checking (optional)

The SDK includes type hints. For static type checking:

```bash
pip install mypy
mypy edge_sdk/
```

## Project Structure

```
edge-python-sdk/
├── .github/workflows/ # GitHub Actions workflows
│ ├── pr.yml # PR checks (lint, test, build)
│ └── main.yml # Release workflow (lint, test, build, publish)
├── edge_sdk/ # Main SDK package
│ ├── __init__.py # Public API exports
│ ├── adapter/ # EdgeAdapter base class
│ │ └── base.py
│ ├── client/ # gRPC client implementations
│ │ ├── connector_client.py # Task/mission queries
│ │ └── telemetry_publisher.py # Telemetry streaming
│ ├── server/ # gRPC server implementation
│ │ ├── edge_server.py # Main server
│ │ └── _converters.py # Protobuf ↔ Python model conversion
│ ├── models/ # Data models
│ │ ├── common.py # RequestContext, EdgeResponse, etc.
│ │ ├── asset.py # Asset, SubAsset models
│ │ ├── task.py # Task, Mission, Waypoint models
│ │ └── telemetry.py # Telemetry models
│ └── generated/ # Auto-generated gRPC stubs (protobuf)
├── tests/ # Test suite
│ ├── conftest.py # Shared fixtures
│ ├── unit/ # Unit tests (no network)
│ └── integration/ # Integration tests (real gRPC)
├── zqnt-protos/ # Protobuf definitions (git submodule)
├── scripts/
│ └── generate_protos.sh # Proto compilation script
├── README.md # User documentation
├── DEVELOPMENT.md # This file
├── pyproject.toml # Project configuration
└── .gitignore
```

## Making Changes

### Workflow for new features

1. **Create a branch** ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make your changes** - Edit the relevant files in `edge_sdk/`
   - Add or update tests in `tests/`

3. **Verify your changes** ```bash
   ruff check . && ruff format .
   pytest tests/ -v --cov=edge_sdk
   ```

4. **Commit and push** ```bash
   git add .
   git commit -m "feat: brief description of your changes"
   git push origin feature/your-feature-name
   ```

5. **Open a Pull Request** - The CI/CD pipeline will automatically run tests, linting, and build checks
   - Address any feedback from reviewers

### Workflow for bugfixes

Same as features, but:
- Use `bugfix/your-bug-name` or `fix/your-bug-name` for the branch
- Commit message: `fix: brief description`

## Testing Guidelines

### Unit Tests

Test SDK logic without network:

```python
import pytest
from edge_sdk import EdgeAdapter, EdgeResponse, AssetType

class TestMyAdapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

def test_my_feature():
    adapter = TestMyAdapter()
    # Test your logic
```

### Integration Tests

Test end-to-end gRPC communication:

```python
import pytest
import grpc
from edge_sdk.generated import edge_pb2, edge_pb2_grpc

@pytest.mark.asyncio
async def test_grpc_integration(server_port):
    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.GetCapabilities(
            edge_pb2.EdgeGetCapabilitiesRequest(sn="TEST-001")
        )
    assert resp.HasField("capabilities")
```

## Debugging

### Enable debug logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("edge_sdk")
logger.setLevel(logging.DEBUG)
```

### Run server locally

Create a test script:

```python
import asyncio
from edge_sdk import EdgeAdapter, EdgeServer, AssetType

class TestAdapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

async def main():
    server = EdgeServer(adapter=TestAdapter(), port=50051)
    await server.serve()

if __name__ == "__main__":
    asyncio.run(main())
```

Then run:

```bash
python test_script.py
```

### Test with grpcurl

If you have `grpcurl` installed:

```bash
# Get capabilities
grpcurl -plaintext \
  -d '{"sn": "TEST-001"}' \
  localhost:50051 \
  EdgeAdapterService.GetCapabilities
```

## Continuous Integration

The repository uses GitHub Actions for CI/CD:

### On Pull Request
- Linting with ruff
- Unit and integration tests
- Package build
- Generates pre-release version: `{version}+pr{number}.{commit_hash}`

### On Push to main
- All PR checks
- Creates GitHub Release with tag `v{version}`
- Publishes to GitHub Packages
- Marks as production release (not pre-release)

## Publishing a New Release

1. Update the version in `pyproject.toml`:
   ```toml
   [project]
   version = "1.1.0"
   ```

2. Commit and push to main:
   ```bash
   git commit -am "chore: bump version to 1.1.0"
   git push origin main
   ```

3. The CI/CD pipeline will automatically:
   - Run all tests
   - Build the package
   - Create a GitHub Release
   - Publish to GitHub Packages

## Dependencies

### Core Dependencies
- `grpcio>=1.60.0` - gRPC framework
- `protobuf>=4.25.0` - Protobuf serialization
- `grpcio-health-checking>=1.60.0` - Health checks
- `zqnt-utils>=1.0.0` - Zequent utility library (private package)

### Optional Dependencies
- `redis[asyncio]>=5.0.0` - Redis client (for registration service)

### Development Dependencies
- `pytest>=8.0.0` - Testing framework
- `pytest-asyncio>=0.24.0` - Async test support
- `grpcio-tools>=1.60.0` - Protobuf code generation
- `mypy-protobuf>=3.6.0` - Type hints for protobuf
- `grpc-stubs>=1.53.0` - gRPC type stubs
- `fakeredis>=2.26.0` - Fake Redis for testing
- `ruff>=0.15.12` - Linting and formatting

## Troubleshooting

### Import errors in generated modules

If you see `ImportError` in `edge_sdk/generated/`:

```bash
# Regenerate the stubs
bash scripts/generate_protos.sh
```

### PyCharm/IntelliJ not recognizing generated modules

Run the proto generation script to fix namespace packages:

```bash
bash scripts/generate_protos.sh
```

### Tests failing with "module not found"

Ensure dev dependencies are installed:

```bash
pip install -e ".[dev,redis]"
```

### gRPC connection refused

- Ensure the server is running on the expected port
- Check port availability: `lsof -i :50051`
- Verify firewall settings

## Resources

- [ZQNT Framework Repository](https://github.com/Zequent/zqnt-framework)
- [gRPC Python Documentation](https://grpc.io/docs/languages/python/)
- [Protocol Buffers Documentation](https://developers.google.com/protocol-buffers)
- [pytest Documentation](https://docs.pytest.org/)

## Code Style

The project follows PEP 8 with enforced rules via ruff:

- Line length: 120 characters
- Target Python version: 3.12
- Import sorting: enabled
- Naming conventions: enforced

Before committing, always run:

```bash
ruff format .
ruff check .
```

## License

All code is proprietary to ZQNT Organization.
