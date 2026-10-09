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

Declare each command once; the registration is both what the platform discovers and what runs:

```python
from edge_sdk import EdgeAdapter, AssetType, CustomCommandResponse, TelemetryValueType, schema


class MyDockAdapter(EdgeAdapter):
    def __init__(self):
        self.register_command("dock.open_cover", self._open_cover)
        self.register_command(
            "vendor.acme.spray",
            self._spray,
            input_schema=schema({"seconds": {"type": "integer", "minimum": 1}}, ["seconds"]),
        )
        self.declare_telemetry_field(
            "dock.cover_state", TelemetryValueType.STRING, allowed_values=["OPEN", "CLOSED", "OPENING", "CLOSING"]
        )

    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.DOCK)

    def reported_asset_sns(self):
        return ["DOCK-1"]

    async def _open_cover(self, ctx, params):
        await hardware.open_cover()
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "dock.open_cover")

    async def _spray(self, ctx, params):
        await hardware.spray(params["seconds"])
        return CustomCommandResponse.ok(ctx.tid, ctx.sn, "vendor.acme.spray")
```

- `EdgeServer` serves `zqnt.edge.v3.EdgeAdapterService` (`ExecuteCommand`) and v2 side by side
  from the same registrations. The typed methods (`take_off`, `open_cover`, ...) are the v2
  compatibility layer: overriding one still works but is deprecated.
- Params are validated against the command's input schema before the handler runs. Integral
  doubles become `int` where the schema says `integer`; invalid params come back as `REJECTED`
  with `command.invalid_params`. Omitted coordinates arrive as NaN: NaN is a number, but never
  satisfies `required`.
- A handler sees the platform's run id as `ctx.command_execution_id`.
- With `REMOTE_CONTROL_HOST` set, capabilities (with `telemetry_fields`) are reported via
  `EdgeGatewayService.ReportCapabilities` on start and whenever the registry changes
  (`notify_capabilities_changed(sn)` for anything else). An older core gets v2 `ReportAssetRuntime`.

### Command events

A command that keeps running returns an `external_execution_id` (v3: `ACCEPTED`) and reports its
outcome later, as before:

```python
await notifier.publish_command_execution_event(
    CommandExecutionEvent(
        external_execution_id="vendor-42", status=CommandExecutionStatus.SUCCEEDED, sn="DOCK-1", output={"photos": 12}
    )
)
```

With a gateway (`REMOTE_CONTROL_HOST`, or `NotificationPublisher(..., gateway=EdgeGatewayClient(...))`)
this goes to `EdgeGatewayService.PublishCommandEvent` under the platform's `command_execution_id`
(looked up from the external id, or set `command_execution_id` yourself). `occurred_at` is always
set (now() if omitted). A core without v3 answers UNIMPLEMENTED: the event goes over v2 and v3 is
not tried again for 10 minutes.

### v3 live data

```python
from edge_sdk import Alert, AlertSeverity, DetectionBatch, TelemetryIngestPublisher, TelemetrySample

ingest = TelemetryIngestPublisher(host="live-data", port=8003)
await ingest.publish_sample(
    TelemetrySample(sn="DOCK-1", latitude=47.5, longitude=9.7, details={"dock.cover_state": "OPEN"})
)
await ingest.publish_detections(DetectionBatch(sn="RADAR-1", detections=[...]))
await ingest.publish_alert(Alert(sn="DOCK-1", code="dock.rain", severity=AlertSeverity.WARNING))
```

Long-lived streams to `TelemetryIngestService`, opened on first use and reconnected with backoff.
`None`/NaN values are not sent. Against a core without v3 samples and detections go over v2
`ProduceTelemetry`/`ProduceDetection` with the shared fields only: **`details` is dropped**, a
sample with a speed or battery value becomes sub-asset (aircraft) telemetry, any other asset
telemetry. Alerts have no v2 counterpart and are dropped. The v2 `TelemetryPublisher` is unchanged.

## Advanced Usage

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

Run the conformance kit in your adapter's tests -- every advertised id is executable, every
executable id is advertised, schemas parse, completion events carry `occurred_at`:

```python
from edge_sdk.testing import RecordingGateway, assert_conformant


async def test_adapter_is_conformant():
    await assert_conformant(MyDockAdapter(), sn="SIM-1")
    # also runs every advertised command with minimal params -- fake/simulated devices only
    await assert_conformant(MyDockAdapter(), sn="SIM-1", execute=True)


async def test_completion_events():
    gateway = RecordingGateway()
    ...  # NotificationPublisher(..., gateway=gateway), run a command
    gateway.assert_events_complete()
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
- `REMOTE_CONTROL_HOST` / `REMOTE_CONTROL_PORT` - remote-control (`EdgeGatewayService`: capability
  reports, v3 command events; port default 8002). Unset: no capability push, events over v2.

### Authentication

Both directions of an adapter's gRPC traffic are authenticated (see `edge_sdk/auth.py`):

- `ZQNT_EDGE_TOKEN` - the adapter's edge credential, attached to every call into the platform.
  Issue one in the console (Edge Credentials, `POST /api/admin-console/edge-credentials`) or with
  `core/scripts/mint-edge-credential.py`. The platform refuses calls without it, except claim
  redemption (`ZQNT_CLAIM_CODE`).
- `ZQNT_PLATFORM_PUBLIC_KEY` (alias `SERVICE_AUTH_PUBLIC_KEY`) - the platform's service public key.
  `EdgeServer` refuses every command that does not carry a token signed with it; without the key
  it refuses everything.
- `ZQNT_EDGE_AUTH_DISABLED=true` - accept unauthenticated commands. Local SITL/simulators only.

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
