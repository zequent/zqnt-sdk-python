# Zequent SDK for Python

Two packages in one uv workspace, released together under one version:

| Directory | Package | Import | For |
|---|---|---|---|
| [`edge/`](edge) | `edge-python-sdk` | `edge_sdk` | adapters that connect devices to the platform |
| [`client/`](client) | `zqnt-client-sdk` | `client_sdk` | applications that use the platform |

Both build on the public API package `zqnt-api` ([zqnt-api](https://github.com/zequent/zqnt-api), directory `python/`).

## Installation

Consumers take a package from git with `subdirectory`, at a release tag `vX.Y.Z` or a PR preview tag
`pr-<n>-<sha>`:

```toml
[project]
dependencies = ["edge-python-sdk", "zqnt-api"]          # or "zqnt-client-sdk"

[tool.uv.sources]
edge-python-sdk = { git = "https://github.com/zequent/zqnt-sdk-python", subdirectory = "edge", tag = "v3.0.0" }
zqnt-client-sdk = { git = "https://github.com/zequent/zqnt-sdk-python", subdirectory = "client", tag = "v3.0.0" }
zqnt-api = { git = "https://github.com/zequent/zqnt-api", subdirectory = "python", rev = "<the rev the SDK pins>" }
```

uv allows one source URL per package in a graph: pin `zqnt-api` to the same rev as the SDK
(`edge/pyproject.toml`, `client/pyproject.toml`) and move SDK and API together.

## Development

```bash
uv sync --all-packages --all-extras
(cd edge && uv run pytest && uv run ruff check . && uv run ruff format --check .)
(cd client && uv run pytest && uv run ruff check . && uv run ruff format --check .)
uv build --all-packages
```

## Edge SDK


A Python SDK for implementing ZQNT Edge Adapters. This SDK provides a high-level abstraction over gRPC, allowing you to implement edge adapters without protobuf knowledge.

### Overview

The ZQNT Edge Python SDK makes it easy to:

- **Implement edge adapters** for drones, docks, and other hardware
- **Handle gRPC communication** automatically
- **Manage telemetry publishing** to the ZQNT platform
- **Execute missions and tasks** with full control and feedback

### Features

- Simple Python API - no protobuf knowledge required
- Async/await support for high-performance applications
- Built-in gRPC server with health checks
- Real-time telemetry publishing
- Support for Redis-based registration (optional)
- Comprehensive test utilities
- Ready for CI/CD with GitHub Actions

### Installation

#### From GitHub

Add to your `pyproject.toml`:

```toml
[project]
dependencies = [
    "edge-python-sdk @ git+https://github.com/zequent/zqnt-sdk-python@v3.0.0#subdirectory=edge",
]
```

Or install directly:

```bash
pip install "edge-python-sdk @ git+https://github.com/zequent/zqnt-sdk-python@v3.0.0#subdirectory=edge"
```

#### From source

```bash
pip install -e .
```

#### Development mode with all dev tools

```bash
pip install -e ".[dev,redis]"
```

### Quick Start

#### 1. Create an Adapter

Subclass `EdgeAdapter` and implement the methods for your hardware:

```python
from edge_sdk import EdgeAdapter, EdgeResponse, AssetType, Capabilities
from edge_sdk.models import RequestContext, Coordinates


class MyDroneAdapter(EdgeAdapter):
    """Adapter for a custom drone platform."""

    async def get_capabilities(self, sn: str, asset_id: str | None) -> Capabilities:
        """Return capabilities supported by this asset."""
        return self._auto_capabilities(sn, AssetType.AIRCRAFT)

    async def take_off(
        self, ctx: RequestContext, coordinates: Coordinates
    ) -> EdgeResponse:
        """Handle take-off command."""
        # Call your drone SDK here
        await hardware.take_off(
            coordinates.latitude, coordinates.longitude, coordinates.altitude
        )
        return EdgeResponse.ok(ctx.tid, ctx.sn, "Take-off initiated")

    async def go_to(
        self, ctx: RequestContext, coordinates: Coordinates
    ) -> EdgeResponse:
        """Handle go-to command."""
        await hardware.fly_to(coordinates)
        return EdgeResponse.ok(ctx.tid, ctx.sn)

    async def start_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
        """Execute a mission task."""
        task = await self.connector.get_task(task_id)
        await hardware.upload_mission(task)
        return EdgeResponse.ok(ctx.tid, ctx.sn)
```

#### 2. Start the Server

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

### Core Concepts

#### EdgeAdapter

The base class for all edge adapters. Only `get_capabilities()` is required; all other methods have defaults that return "not supported".

**Key methods:**
- `get_capabilities(sn, asset_id)` - **Required**. Describe what operations this asset supports
- `take_off(ctx, coordinates)` - Launch drone
- `go_to(ctx, coordinates)` - Fly to a location
- `start_task(ctx, task_id)` - Execute a mission
- `enter_manual_control(ctx, request)` - Manual pilot mode
- `start_live_stream(ctx, request)` - Video streaming
- And many more...

#### EdgeResponse

Represents the response to a command from the platform.

```python
# Success response
EdgeResponse.ok(tid, sn, message="Optional status")

# Error response
EdgeResponse.fail(tid, sn, ErrorMessage("Error details", ErrorCode.CLIENT_ERROR))

# With optional data
EdgeResponse.ok(tid, sn, stream_url="rtmp://...")
```

#### RequestContext

Contains request metadata:

```python
ctx.tid  # Transaction ID (for tracing)
ctx.sn  # Asset serial number
ctx.timestamp  # Request timestamp
```

#### TelemetryPublisher

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

### Capabilities & Commands

Declare each command once; the registration is both what the platform discovers and what runs:

```python
from edge_sdk import (
    EdgeAdapter,
    AssetType,
    CustomCommandResponse,
    TelemetryValueType,
    schema,
)


class MyDockAdapter(EdgeAdapter):
    def __init__(self):
        self.register_command("dock.open_cover", self._open_cover)
        self.register_command(
            "vendor.acme.spray",
            self._spray,
            input_schema=schema(
                {"seconds": {"type": "integer", "minimum": 1}}, ["seconds"]
            ),
        )
        self.declare_standard_telemetry_field("dock.cover_state")
        self.declare_telemetry_field(
            "vendor.acme.tank_level", TelemetryValueType.NUMBER, unit="%"
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

- `set_payloads(sn, [Payload(ref="speaker-1", kind="speaker", ...)])` sets the devices mounted on
  an asset; they go out with the capabilities as a full snapshot, so a payload left out is detached.
  A command acting on one is registered with `target=CapabilityTarget(type=PAYLOAD, target_ref=ref)`.
- `EdgeServer` serves `zqnt.edge.v3.EdgeAdapterService` (`ExecuteCommand`) and v2 side by side
  from the same registrations. The typed methods (`take_off`, `open_cover`, ...) are the v2
  compatibility layer: overriding one still works but is deprecated.
- Params are validated against the command's input schema before the handler runs. Integral
  doubles become `int` where the schema says `integer`; invalid params come back as `REJECTED`
  with `command.invalid_params`. Omitted coordinates arrive as NaN: NaN is a number, but never
  satisfies `required`. v3 params are validated as sent; on v2 the SDK first converts text the
  schema does not accept as text (`"13.405"` for a number, `"true"` for a boolean, `"pitch_down"`
  for the enum value `PITCH_DOWN`), exact conversions only. Enum aliases (a DJI name such as
  `SDR_ONLY` or `IRONBOW1` for a standard value) are not converted: a 2.x platform must send the
  standard value.
- A handler sees the platform's run id as `ctx.command_execution_id`.
- Every capability carries its risk (`CommandSafety`). A standard id gets the rating of the
  platform's command catalog (`catalog_safety`, e.g. `flight.takeoff` MOVE, `flight.land` CRITICAL);
  `register_command(..., safety=CommandRisk.CRITICAL)` or a full `CommandSafety` overrides it. A
  `vendor.*` command that moves or affects the asset must declare its own: an id outside the catalog
  declares none, and the platform then falls back to the 2.x prefix rule.
- With `REMOTE_CONTROL_HOST` set, capabilities (with `telemetry_fields`) are reported via
  `EdgeGatewayService.ReportCapabilities` on start and whenever the registry changes
  (`notify_capabilities_changed(sn)` for anything else). An older core gets v2 `ReportAssetRuntime`.

#### Command events

A command that keeps running returns an `external_execution_id` (v3: `ACCEPTED`) and reports its
outcome later, as before:

```python
await notifier.publish_command_execution_event(
    CommandExecutionEvent(
        external_execution_id="vendor-42",
        status=CommandExecutionStatus.SUCCEEDED,
        sn="DOCK-1",
        output={"photos": 12},
    )
)
```

With a gateway (`REMOTE_CONTROL_HOST`, or `NotificationPublisher(..., gateway=EdgeGatewayClient(...))`)
this goes to `EdgeGatewayService.PublishCommandEvent` under the platform's `command_execution_id`
(looked up from the external id, or set `command_execution_id` yourself). `occurred_at` is always
set (now() if omitted). A core without v3 answers UNIMPLEMENTED: the event goes over v2 and v3 is
not tried again for 10 minutes.

#### v3 live data

```python
from edge_sdk import (
    Alert,
    AlertSeverity,
    DetectionBatch,
    TelemetryIngestPublisher,
    TelemetrySample,
)

ingest = TelemetryIngestPublisher(host="live-data", port=8003)
await ingest.publish_sample(
    TelemetrySample(
        sn="DOCK-1", latitude=47.5, longitude=9.7, details={"dock.cover_state": "OPEN"}
    )
)
await ingest.publish_detections(DetectionBatch(sn="RADAR-1", detections=[...]))
await ingest.publish_alert(
    Alert(sn="DOCK-1", code="dock.rain", severity=AlertSeverity.WARNING)
)
```

Long-lived streams to `TelemetryIngestService`, opened on first use and reconnected with backoff.
`None`/NaN values are not sent. Against a core without v3 samples and detections go over v2
`ProduceTelemetry`/`ProduceDetection`, mapped by `zqnt_api.telemetry`: keys of the platform's
catalog (`dock.mode`, `wind.speed`, `drone.gear`, …; declare them with
`declare_standard_telemetry_field`) land in their v2 fields, **other `details` keys are dropped**. A
sample with a speed or an aircraft key becomes sub-asset (aircraft) telemetry, one with dock keys or
only a battery asset telemetry. Alerts have no v2 counterpart and are dropped. The v2 `TelemetryPublisher` is unchanged.

### Advanced Usage

#### Custom Task Handling

```python
async def prepare_task(self, ctx: RequestContext, task_id: str) -> EdgeResponse:
    """Prepare a task before execution."""
    task = await self.connector.get_task(task_id)

    # Upload waypoints to hardware
    for waypoint in task.waypoint_config.waypoints:
        await hardware.add_waypoint(waypoint)

    return EdgeResponse.ok(ctx.tid, ctx.sn, "Task prepared")
```

#### Error Handling

```python
from edge_sdk import ErrorMessage, ErrorCode


async def some_operation(self, ctx: RequestContext) -> EdgeResponse:
    try:
        result = await hardware.do_something()
        return EdgeResponse.ok(ctx.tid, ctx.sn)
    except HardwareError as e:
        return EdgeResponse.fail(
            ctx.tid, ctx.sn, ErrorMessage(str(e), ErrorCode.HARDWARE_ERROR)
        )
```

#### Server Registration (with Redis)

```python
from edge_sdk import EdgeServer, RegistrationConfig

config = RegistrationConfig(
    redis_host="redis-host",
    redis_port=6379,
    ttl_seconds=30,
)

server = EdgeServer(adapter=adapter, port=50051, registration_config=config)
```

### Testing

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

### Logging

The SDK uses Python's standard `logging` module. Enable debug logging:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("edge_sdk")
logger.setLevel(logging.DEBUG)
```

### Architecture

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

### Environment Variables

The SDK respects the following environment variables:

- `EDGE_LOG_LEVEL` - Logging level (DEBUG, INFO, WARNING, ERROR)
- `EDGE_SERVER_PORT` - Port for the gRPC server (default: 50051)
- `EDGE_TELEMETRY_HOST` - Host for telemetry (default: localhost)
- `EDGE_TELEMETRY_PORT` - Port for telemetry (default: 50052)
- `REMOTE_CONTROL_HOST` / `REMOTE_CONTROL_PORT` - remote-control (`EdgeGatewayService`: capability
  reports, v3 command events; port default 8002). Unset: no capability push, events over v2.

#### Authentication

Both directions of an adapter's gRPC traffic are authenticated (see `edge_sdk/auth.py`):

- `ZQNT_EDGE_TOKEN` - the adapter's edge credential, attached to every call into the platform.
  Issue one in the console (Edge Credentials, `POST /api/admin-console/edge-credentials`) or with
  `core/scripts/mint-edge-credential.py`. The platform refuses calls without it, except claim
  redemption (`ZQNT_CLAIM_CODE`).
- `ZQNT_PLATFORM_KEYS_URL` - the platform's published signing keys, a JWK set
  (`http://<admin-console>:8005/api/admin-console/auth/service-keys`). `EdgeServer` verifies every
  command's token with the key its `kid` names. The set is fetched at start (retried until it
  answers), refreshed every 5 minutes and, at most every 30 seconds, when a token names a key it
  does not know yet, so the platform can rotate its keys without touching the adapter. A token
  signed with a key the set does not list is refused.
- `ZQNT_PLATFORM_PUBLIC_KEY` (alias `SERVICE_AUTH_PUBLIC_KEY`) - the platform's service public key,
  for tokens without `kid`. Optional with `ZQNT_PLATFORM_KEYS_URL`: without it, the key the set
  lists without `kid` is used. Without either variable `EdgeServer` refuses everything.
- `ZQNT_EDGE_AUTH_DISABLED=true` - accept unauthenticated commands. Local SITL/simulators only.

### API Reference

Full API documentation is available in the module docstrings:

```python
from edge_sdk import EdgeAdapter, EdgeServer, TelemetryPublisher

help(EdgeAdapter)
help(EdgeServer)
help(TelemetryPublisher)
```

### Requirements

- Python 3.12+
- gRPC 1.60+
- Protobuf 4.25+

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write tests for your changes
4. Run linting: `ruff check .`
5. Run tests: `pytest tests/`
6. Commit and push to your branch
7. Open a Pull Request

### Testing Locally

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


## Client SDK


Python client SDK for Zequent 3.0. Every asset is commanded the same way, by command id, through
`client.commands`; live telemetry, detections and alerts come from `client.telemetry`, the live video streams from
`client.live_streams`;
Applications, Skill executions and schedulers from `client.mission_autonomy` and
`client.connector`.

- Python 3.12+
- Async-first (`asyncio` / `grpc.aio`)
- Type hints throughout (`py.typed` marker shipped)
- Built-in retry / circuit-breaker resilience

---

### Installation

```bash
uv add "zqnt-client-sdk @ git+https://github.com/zequent/zqnt-sdk-python@v3.0.0#subdirectory=client"
```

or with pip:

```bash
pip install "zqnt-client-sdk @ git+https://github.com/zequent/zqnt-sdk-python@v3.0.0#subdirectory=client"
```

After installation you can verify the version:

```python
import client_sdk

print(client_sdk.__version__)  # "3.0.0"
```

---

### Quick start

```python
import asyncio
from client_sdk import ZequentClient


async def main():
    async with ZequentClient.from_env() as client:
        await client.commands.execute_command(
            "DRONE-1", "flight.takeoff", {"altitude": 40}
        )

        async for item in client.telemetry.watch_telemetry(["DRONE-1"]):
            print(item)


asyncio.run(main())
```

`ZequentClient.from_env()` reads connection settings from environment variables — the same names the
Java and Go client SDKs read, so one `.env` works for every language. Nothing set is the local
development stack (`quarkus:dev` or `docker-compose.local.yml`):

| Variable                                                        | Local default (nothing set)   |
| --------------------------------------------------------------- | ----------------------------- |
| `CONNECTOR_SERVICE_HOST` / `_PORT` / `_USE_PLAINTEXT`           | `localhost` / `8010` / `true` |
| `REMOTE_CONTROL_SERVICE_HOST` / `_PORT` / `_USE_PLAINTEXT`      | `localhost` / `8002` / `true` |
| `LIVE_DATA_SERVICE_HOST` / `_PORT` / `_USE_PLAINTEXT`           | `localhost` / `8003` / `true` |
| `MISSION_AUTONOMY_SERVICE_HOST` / `_PORT` / `_USE_PLAINTEXT`    | `localhost` / `8004` / `true` |
| `ZQNT_CLIENT_TOKEN`                                             | none — issue one in your local console too |

A deployment sets the hosts, `_USE_PLAINTEXT=false` for TLS whenever traffic leaves a private
network, and `ZQNT_CLIENT_TOKEN` from its secret store — never from a committed file. There is
deliberately no built-in development credential: the local platform refuses anonymous calls too.
`from_env(**overrides)` passes `client_token=`, `interceptors=` or a single `*_config=` through.

You can also build a client manually:

```python
from client_sdk import ZequentClient
from client_sdk.config import ServiceConfig

async with ZequentClient(
    connector_config=ServiceConfig(
        "connector", host="connector.example.com", port=8010
    ),
    remote_control_config=ServiceConfig(
        "remote-control", host="rc.example.com", port=8002
    ),
    mission_autonomy_config=ServiceConfig(
        "mission-autonomy", host="ma.example.com", port=8004
    ),
    live_data_config=ServiceConfig("live-data", host="ld.example.com", port=8003),
) as client:
    ...
```

---

### Commands

Every asset is commanded the same way: list what it can do, then run a command by
its dotted id with a dict of params. There are no typed methods per command.

```python
from client_sdk import CommandError
from client_sdk.commands import to_dict

async with ZequentClient.from_env() as client:
    capabilities = await client.commands.list_capabilities("DOCK-1")
    for capability in capabilities.capabilities:
        print(capability.command_id, capability.safety.risk, capability.input_schema)

    try:
        async with asyncio.timeout(300):
            result = await client.commands.execute_and_wait(
                "DOCK-1",
                "navigation.go_to",
                {"latitude": 47.7760, "longitude": 9.2671, "altitude": 60},
            )
    except CommandError as error:
        print(
            error.category_name, error.code, error
        )  # e.g. ERROR_CATEGORY_INVALID_ARGUMENT command.invalid_params
    else:
        print(to_dict(result.result))

    started = await client.commands.execute_command("DOCK-1", "dock.open_cover")
    async for event in client.commands.watch_command(started.command_execution_id):
        print(event.state, event.progress, event.message)
```

| Method | Purpose |
| --- | --- |
| `list_capabilities(asset_sn)` | The asset's `CapabilitySet`: command ids, input/output JSON schemas, risk, declared errors and events |
| `execute_command(asset_sn, command_id, params=None, *, asset_id, target, timeout, reason, no_fly_zone_override, idempotency_key)` | Run a command; returns the `CommandResult` (`ACCEPTED`/`RUNNING` with a `command_execution_id` while underway, or the final state) |
| `execute_and_wait(asset_sn, command_id, params=None, *, target, timeout, reason, no_fly_zone_override, idempotency_key)` | Run a command and wait for its outcome; returns the `SUCCEEDED` result. Bound the wait with `asyncio.timeout` |
| `watch_command(command_execution_id)` | Async iterator of that run's events from now on, ending after its terminal event |
| `watch_asset(asset_sn)` | Async iterator of every command event on the asset until you leave the loop |
| `cancel_command(command_execution_id, reason=None)` | Cancel a run |
| `stream_manual_control(asset_sn)` | A `ManualControlStream` for stick input on the asset (see below) |

- A refused call, or a command rejected before it started, raises `CommandError` (`category`,
  `category_name`, `code` such as `command.invalid_params`, `status`, `result`). From
  `execute_command`, a command that started and failed is returned with state
  `COMMAND_STATE_FAILED` and its `error`; `execute_and_wait` raises `CommandError` for a run that
  ends `FAILED`, `CANCELLED` or `TIMED_OUT`, with that final `result`.
- `execute_and_wait` watches the asset before it sends the command, so a run that finishes right
  away is not missed, and ignores the events of other runs. A watch opened after
  `execute_command` returns can miss the end of a fast run. Leaving the wait early (timeout,
  cancellation) closes the watch and leaves the command running; `cancel_command` stops it.
- `navigation.go_to` altitude is metres above the **takeoff point**. Leave a param out when you
  have no value; never send `0` for "not given". `None` values are left out.
- Results and events are the generated `zqnt.capability.v3` messages; `to_dict(...)` turns a result
  payload into a plain dict.
- `client.commands` uses the remote-control connection, credential and interceptors the client
  already has; nothing else to set up. [`main.py`](client/main.py) is a runnable example.

#### Manual control

Stick input goes over one stream per asset. Put the asset in manual control first, then send
inputs (roll, pitch, yaw, throttle from -1 to 1) at your control rate:

```python
await client.commands.execute_and_wait("DRONE-1", "flight.manual.enter")
async with client.commands.stream_manual_control("DRONE-1") as stick:
    await stick.send(pitch=0.2, throttle=0.5)
    await stick.send(throttle=0.5, gimbal_pitch=-30)
print(stick.accepted_inputs)
await client.commands.execute_and_wait("DRONE-1", "flight.manual.exit")
```

The first input names the asset; one stream controls one asset. Leaving the block normally ends
the session and waits for the platform's answer: `accepted_inputs` is the number of inputs passed
on to the asset (`await stick.close()` returns it too). Leaving it with an exception aborts the
stream. `send` and `close` raise `CommandError` when the platform refused the session (no adapter
reachable, an asset of another organization) or the adapter dropped it.

#### Telemetry, detections and alerts

```python
from zqnt_api.generated.zqnt.telemetry.v3 import telemetry_pb2

async for item in client.telemetry.watch_telemetry(["DOCK-1"], min_interval=1.0):
    if isinstance(item, telemetry_pb2.TelemetrySample):
        print(item.asset.sn, item.position, item.battery_percent, to_dict(item.details))
    else:
        print(item.asset.sn, telemetry_pb2.SourceState.Name(item.state))
```

`watch_telemetry(asset_sns=None, *, min_interval=None, heartbeat_timeout=35s)` streams
`TelemetrySample`s from the live-data service: the shared fields (position, relative altitude,
heading, speeds, battery) and the device-specific `details` under the keys of the capabilities'
`telemetry_fields`. No asset watches every asset of the caller's organization; a dock's serial
includes its drone. `min_interval` keeps at most one sample per asset per interval. A
`SourceStatus` comes first for every watched asset, then on each change to online, stale or no
data. The platform sends heartbeats on a quiet stream; when neither a sample nor a heartbeat
arrives within `heartbeat_timeout`, the loop raises a retryable `CommandError` (`SERVICE`). A
watch does not reconnect: watch again.

```python
async for batch in client.telemetry.watch_detections(["DRONE-1"]):
    print(batch.asset.sn, batch.stream_url, len(batch.detections))

async for alert in client.telemetry.watch_alerts(
    min_severity=telemetry_pb2.ALERT_SEVERITY_WARNING
):
    print(
        alert.asset.sn,
        telemetry_pb2.AlertSeverity.Name(alert.severity),
        alert.code,
        alert.message,
    )
```

`watch_detections(asset_sns=None, *, heartbeat_timeout=35s)` yields `DetectionBatch`es,
`watch_alerts(asset_sns=None, *, min_severity=ALERT_SEVERITY_UNSPECIFIED, heartbeat_timeout=35s)`
yields `Alert`s (stable `code` such as `dock.rain`, `message`, `details`) of at least
`min_severity`. Heartbeats, refusals and a dropped stream behave as for `watch_telemetry`.

#### Live video streams

```python
for stream in await client.live_streams.list_live_streams():
    print(stream.asset.sn, stream.path, stream.since.ToDatetime(), stream.viewers)
```

`list_live_streams()` returns every `LiveStream` of the caller's organization that is live right
now: the asset publishing it (for a docked aircraft, the aircraft), the media server's `path`,
`since` when it is received and how many `viewers` read it. It raises `CommandError` with the gRPC
`status` `PERMISSION_DENIED` when the organization's license does not include live streams and
`UNAVAILABLE` when the platform has no current answer from the media server.

**Upgrading from 2.x:** the typed per-command methods (`client.remote_control`) and the 2.x live
data client (`client.live_data`) are removed in 3.0. [MIGRATION.md](client/MIGRATION.md) maps every typed
call to its command id and params.

---

### Mission autonomy and connector

`client.mission_autonomy` manages Applications (upsert, get, list, delete, environments, promote a
version), runs them (`execute_application`, `execute_skill`, `execute_simple`, the
`create_*_execution` variants), drives a run (`start_`, `pause_`, `resume_`, `cancel_`,
`signal_skill_execution`), reads runs (`get_skill_execution`, `list_skill_executions`) and
schedulers. `client.connector` reads and registers assets, sub-assets and payloads, organizations,
policies, technical configs, the skill registry and schedulers, and `asset_monitoring(sn, on_data)`
streams asset monitoring updates (a `StreamHandle`; `await handle.stop()`).

---

### Authentication

The platform refuses every call that carries no credential. An organization administrator issues a
**client credential** in the console under **Deploy → Access & Integrations → Credentials** (kind
**client**). It is shown once, belongs to that one organization, and reaches only that
organization's assets, Applications and runs — never users, organizations or other administration.

```bash
export ZQNT_CLIENT_TOKEN=eyJhbGciOiJFZERTQSIs...   # read by ZequentClient(...) and from_env()
```

```python
client = ZequentClient(
    connector_config=...,
    remote_control_config=...,
    mission_autonomy_config=...,
    live_data_config=...,
    client_token=token,
)  # or pass it explicitly
```

It is sent as `authorization: Bearer <token>` on every call, unary and streaming. A refusal is raised
as `client_sdk.auth.ZequentAuthError` — a `grpc.aio.AioRpcError` with the same `code()` and a
`details()` that says what to do: `UNAUTHENTICATED` (no credential, or an expired/revoked one) or
`PERMISSION_DENIED` (an asset of another organization, or an administrative call). Neither is retried.

#### A credential that is not one fixed token

A service that forwards its own caller's token, or rotates a short-lived one, passes its own
`grpc.aio` interceptors: `ZequentClient(..., interceptors=[...])` or
`ZequentClient.from_env(interceptors=[...])`. They go on every channel (all four services, unary and
streaming calls), in the order given, before the SDK's credential interceptor. An `authorization`
header they set wins, and the fixed client token is then not sent.

### Error handling

All client errors derive from `ZequentClientError`:

```python
from client_sdk import CommandError, ZequentClientError

try:
    await client.commands.execute_command("DOCK-1", "flight.takeoff", {"altitude": 40})
except CommandError as e:
    # Refused or rejected: e.category_name, e.code, e.status, e.retryable
    print("command error:", e.code, e)
except ZequentClientError as e:
    print("client error:", e)
```

`client.commands` and `client.telemetry` raise `CommandError` for every refusal, including
exhausted retries (`retryable=True`) and authentication (`ERROR_CATEGORY_PERMISSION_DENIED`).
`client.connector` and `client.mission_autonomy` raise `ZequentRetryExhaustedError` when retries
give up.

The SDK also exposes `CircuitBreakerOpen` (in `client_sdk.grpc_.resilience`)
raised when the per-method breaker is open.

---

### Resilience

Unary RPCs are wrapped with retry + circuit-breaker policies. Defaults are sane;
override them via `ResilienceConfig`:

```python
from client_sdk import ZequentClient
from client_sdk.config.resilience import ResilienceConfig

client = ZequentClient.from_env(
    resilience=ResilienceConfig(
        max_retry_attempts=5,
        retry_delay_millis=200,
        circuit_breaker_failure_threshold=10,
        circuit_breaker_wait_duration_millis=30_000,
    )
)
```

Streaming RPCs do not retry transparently — re-subscribe at the application
level when needed.

---

### Architecture

```
ZequentClient
 |- CommandsClient        -> zqnt.control.v3 RemoteControlService (remote-control channel)
 |- TelemetryClient       -> zqnt.telemetry.v3 TelemetryService (live-data channel)
 |- ConnectorClient       -> ConnectorService (connector channel)
 |- MissionAutonomyClient -> MissionAutonomyService (mission-autonomy channel)
```

Each channel that is closed when the parent
`ZequentClient` exits its `async with` block.

---

### Development

See [DEVELOPMENT.md](client/DEVELOPMENT.md) for setup, testing, linting and release
instructions.

---


## Moving from the old repositories

This repository replaces `zequent/zqnt-edge-sdk-python` and `zequent/zqnt-client-sdk-python` from 3.0
on; their history is kept here under `edge/` and `client/`. The 2.x line stays in the old repositories.

| Before (2.x) | Now (3.0) |
|---|---|
| `edge-python-sdk = { git = "https://github.com/zequent/zqnt-edge-sdk-python", ... }` | `edge-python-sdk = { git = "https://github.com/zequent/zqnt-sdk-python", subdirectory = "edge", ... }` |
| `zqnt-client-sdk = { git = "https://github.com/zequent/zqnt-client-sdk-python", ... }` | `zqnt-client-sdk = { git = "https://github.com/zequent/zqnt-sdk-python", subdirectory = "client", ... }` |
| `zqnt-api = { git = "https://github.com/zequent/zqnt-api-python", ... }` | `zqnt-api = { git = "https://github.com/zequent/zqnt-api", subdirectory = "python", ... }` |

Package and module names (`edge_sdk`, `client_sdk`) are unchanged: no import changes. Moving from
the 2.x typed calls to commands: [client/MIGRATION.md](client/MIGRATION.md).

## License

Licensed under the [Apache License, Version 2.0](LICENSE); see [NOTICE](NOTICE).
