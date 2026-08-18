# ZQNT Edge Python SDK

A Python SDK for implementing ZQNT Edge Adapters. This SDK provides a high-level abstraction over gRPC, allowing you to implement edge adapters without protobuf knowledge.

## Overview

The ZQNT Edge Python SDK makes it easy to:

- **Implement edge adapters** for drones, docks, and other hardware
- **Handle gRPC communication** automatically
- **Manage telemetry publishing** to the ZQNT platform
- **Execute missions and tasks** with full control and feedback

## Features

- Simple Python API - no protobuf knowledge required
- Async/await support for high-performance applications
- Built-in gRPC server with health checks
- Real-time telemetry publishing
- Support for Redis-based registration (optional)
- Comprehensive test utilities
- Ready for CI/CD with GitHub Actions

## Installation

### From GitHub Packages

Add to your `pyproject.toml`:

```toml
[project]
dependencies = [
    "edge-python-sdk @ git+https://github.com/Zequent/zqnt-framework@main#egg=edge-python-sdk&subdirectory=sdks/edge/edge-python-sdk",
]
```

Or install directly:

```bash
pip install git+https://github.com/Zequent/zqnt-framework@main#egg=edge-python-sdk&subdirectory=sdks/edge/edge-python-sdk
```

### From source

```bash
pip install -e .
```

### Development mode with all dev tools

```bash
pip install -e ".[dev,redis]"
```

## Quick Start

### 1. Create an Adapter

Subclass `EdgeAdapter` and implement the methods for your hardware:

```python
from edge_sdk import EdgeAdapter, EdgeResponse, AssetType, Capabilities
from edge_sdk.models import RequestContext, Coordinates


class MyDroneAdapter(EdgeAdapter):
    """Adapter for a custom drone platform."""

    async def get_capabilities(self, sn: str, asset_id: str | None) -> Capabilities:
        """Return capabilities supported by this asset."""
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def take_off(self, ctx: RequestContext, coordinates: Coordinates) -> EdgeResponse:
        """Handle take-off command."""
        # Call your drone SDK here
        await hardware.take_off(coordinates.latitude, coordinates.longitude, coordinates.altitude)
        return EdgeResponse.ok(ctx.tid, ctx.sn, "Take-off initiated")

    async def go_to(self, ctx: RequestContext, coordinates: Coordinates) -> EdgeResponse:
        """Handle go-to command."""
        await hardware.fly_to(coordinates)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def start_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        """Execute a mission task."""
        task = await self.connector.get_task(task_id)
        await hardware.upload_mission(task)
        return EdgeResponse.ok(ctx.tid, ctx.sn)
```

### 2. Start the Server

```python
import asyncio
from edge_sdk import EdgeServer, TelemetryPublisher


async def main():
    # Create your adapter
    adapter = MyDroneAdapter()

    # Start the gRPC server
    server = EdgeServer(adapter=adapter, port=50051)

    # Optionally publish telemetry
    publisher = TelemetryPublisher(host="platform-host", port=50052, sn="DRONE-001")
    await publisher.connect()

    async with asyncio.TaskGroup() as tg:
        tg.create_task(server.serve())
        tg.create_task(telemetry_loop(publisher))


async def telemetry_loop(publisher):
    """Publish telemetry every second."""
    while True:
        await publisher.publish_asset_telemetry(
            AssetTelemetry(
                id="DRONE-001",
                latitude=47.5162,
                longitude=9.7765,
                absolute_altitude=420.0,
            )
        )
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
```

## Core Concepts

### EdgeAdapter

The base class for all edge adapters. Only `get_capabilities()` is required; all other methods have defaults that return "not supported".

**Key methods:**
- `get_capabilities(sn, asset_id)` - **Required**. Describe what operations this asset supports
- `take_off(ctx, coordinates)` - Launch drone
- `go_to(ctx, coordinates)` - Fly to a location
- `start_task(ctx, task_id)` - Execute a mission
- `enter_manual_control(ctx, request)` - Manual pilot mode
- `start_live_stream(ctx, request)` - Video streaming
- And many more...

### EdgeResponse

Represents the response to a command from the platform.

```python
# Success response
EdgeResponse.ok(tid, sn, message="Optional status")

# Error response
EdgeResponse.fail(tid, sn, ErrorMessage("Error details", ErrorCode.CLIENT_ERROR))

# With optional data
EdgeResponse.ok(tid, sn, stream_url="rtmp://...")
```

### RequestContext

Contains request metadata:

```python
ctx.tid  # Transaction ID (for tracing)
ctx.sn  # Asset serial number
ctx.timestamp  # Request timestamp
```

### TelemetryPublisher

Publish real-time telemetry to the platform:

```python
publisher = TelemetryPublisher(host="...", port=50052, sn="DRONE-001")
await publisher.connect()

# Publish asset telemetry
await publisher.publish_asset_telemetry(
    AssetTelemetry(
        id="DRONE-001",
        latitude=47.5,
        longitude=9.7,
        absolute_altitude=100.0,
        battery_percentage=85.0,
    )
)

# Publish sub-asset telemetry (e.g., camera payload)
await publisher.publish_sub_asset_telemetry(
    SubAssetTelemetry(
        parent_id="DRONE-001",
        id="CAMERA-001",
        battery_percentage=100.0,
    )
)
```

## Capabilities & Commands

The SDK automatically detects which commands your adapter supports by checking which methods you override.

Supported commands include:

**Flight Control:**
- TakeOff, GoTo, ReturnToHome

**Manual Control:**
- EnterManualControl, ExitManualControl, ManualControlInput

**Gimbal & Camera:**
- LookAt, TakePhoto, EnableGimbalTracking, ChangeLens, ChangeZoom, CapturePhoto, StartRecording, StopRecording

**Dock Operations:**
- OpenCover, CloseCover, StartCharging, StopCharging

**Asset Management:**
- RebootAsset, BootUpSubAsset, BootDownSubAsset, RegisterAsset, DeRegisterAsset

**Task Execution:**
- PrepareTask, StartTask, StopTask

**Video Streaming:**
- StartLiveStream, StopLiveStream

**And more...** ## Advanced Usage

### Custom Task Handling

```python
async def prepare_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
    """Prepare a task before execution."""
    task = await self.connector.get_task(task_id)

    # Upload waypoints to hardware
    for waypoint in task.waypoint_config.waypoints:
        await hardware.add_waypoint(waypoint)

    return EdgeResponse.ok(ctx.tid, ctx.sn, "Task prepared")
```

### Error Handling

```python
from edge_sdk import ErrorMessage, ErrorCode


async def some_operation(self, ctx: RequestContext) -> EdgeResponse:
    try:
        result = await hardware.do_something()
        return EdgeResponse.ok(ctx.tid, ctx.sn)
    except HardwareError as e:
        return EdgeResponse.fail(ctx.tid, ctx.sn, ErrorMessage(str(e), ErrorCode.HARDWARE_ERROR))
```

### Server Registration (with Redis)

```python
from edge_sdk import EdgeServer, RegistrationConfig

config = RegistrationConfig(
    redis_host="redis-host",
    redis_port=6379,
    ttl_seconds=30,
)

server = EdgeServer(adapter=adapter, port=50051, registration_config=config)
```

## Testing

The SDK includes test utilities for writing integration tests:

```python
import pytest
from edge_sdk import EdgeAdapter, EdgeResponse, AssetType
from tests.conftest import test_adapter, server_port


class MyTestAdapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def take_off(self, ctx, coordinates):
        return EdgeResponse.ok(ctx.tid, ctx.sn)


@pytest.mark.asyncio
async def test_take_off(server_port):
    """Test take-off via gRPC."""
    import grpc
    from edge_sdk.generated import edge_pb2, edge_pb2_grpc

    async with grpc.aio.insecure_channel(f"localhost:{server_port}") as ch:
        stub = edge_pb2_grpc.EdgeAdapterServiceStub(ch)
        resp = await stub.TakeOff(edge_pb2.EdgeTakeOffRequest(...))

    assert resp.hasErrors is False
```

## Logging

The SDK uses Python's standard `logging` module. Enable debug logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("edge_sdk")
logger.setLevel(logging.DEBUG)
```

## Architecture

```
┌─────────────────────────────────────────────┐
│ ZQNT Platform │
│ (Command requests, telemetry collection) │
└──────────────┬──────────────────────────────┘
               │ gRPC (port 50051)
               │ gRPC (port 50052)
               ▼
┌─────────────────────────────────────────────┐
│ EdgeServer (Your Application) │
│ ┌───────────────────────────────────────┐ │
│ │ EdgeAdapter (your subclass) │ │
│ │ • get_capabilities() │ │
│ │ • take_off() │ │
│ │ • start_task() │ │
│ │ • ... (your implementations) │ │
│ └───────────────────────────────────────┘ │
│ ┌───────────────────────────────────────┐ │
│ │ TelemetryPublisher │ │
│ │ • publish_asset_telemetry() │ │
│ │ • publish_sub_asset_telemetry() │ │
│ └───────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
               │ Hardware APIs
               ▼
        Your Hardware (Drone, Dock, etc.)
```

## Environment Variables

The SDK respects the following environment variables:

- `EDGE_LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `EDGE_SERVER_PORT` - Port for the gRPC server (default: 50051)
- `EDGE_TELEMETRY_HOST` - Host for telemetry (default: localhost)
- `EDGE_TELEMETRY_PORT` - Port for telemetry (default: 50052)

## API Reference

Full API documentation is available in the module docstrings:

```python
from edge_sdk import EdgeAdapter, EdgeServer, TelemetryPublisher

help(EdgeAdapter)
help(EdgeServer)
help(TelemetryPublisher)
```

## Requirements

- Python 3.12+
- gRPC 1.60+
- Protobuf 4.25+

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write tests for your changes
4. Run linting: `ruff check .`
5. Run tests: `pytest tests/`
6. Commit and push to your branch
7. Open a Pull Request

## Testing Locally

```bash
# Install dev dependencies
pip install -e ".[dev,redis]"

# Run linting
ruff check .
ruff format .

# Run tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=edge_sdk --cov-report=html
```

## License

Proprietary - ZQNT Organization

## Support

For issues, questions, or contributions, please open an issue in the [GitHub repository](https://github.com/Zequent/zqnt-framework).

---

**Last updated**: 2024
