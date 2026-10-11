# zqnt-client-sdk (Python)

Python client SDK for Zequent 3.0. Every asset is commanded the same way, by command id, through
`client.commands`; live telemetry, detections and alerts come from `client.telemetry`;
Applications, Skill executions and schedulers from `client.mission_autonomy` and
`client.connector`.

- Python 3.12+
- Async-first (`asyncio` / `grpc.aio`)
- Type hints throughout (`py.typed` marker shipped)
- Built-in retry / circuit-breaker resilience

---

## Installation

```bash
uv add zqnt-client-sdk
```

or with pip:

```bash
pip install zqnt-client-sdk
```

After installation you can verify the version:

```python
import client_sdk

print(client_sdk.__version__)  # "3.0.0"
```

---

## Quick start

```python
import asyncio
from client_sdk import ZequentClient


async def main():
    async with ZequentClient.from_env() as client:
        await client.commands.execute_command("DRONE-1", "flight.takeoff", {"altitude": 40})

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
    connector_config=ServiceConfig("connector", host="connector.example.com", port=8010),
    remote_control_config=ServiceConfig("remote-control", host="rc.example.com", port=8002),
    mission_autonomy_config=ServiceConfig("mission-autonomy", host="ma.example.com", port=8004),
    live_data_config=ServiceConfig("live-data", host="ld.example.com", port=8003),
) as client:
    ...
```

---

## Commands

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
                "DOCK-1", "navigation.go_to", {"latitude": 47.7760, "longitude": 9.2671, "altitude": 60}
            )
    except CommandError as error:
        print(error.category_name, error.code, error)  # e.g. ERROR_CATEGORY_INVALID_ARGUMENT command.invalid_params
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
  already has; nothing else to set up. [`main.py`](main.py) is a runnable example.

### Manual control

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

### Telemetry, detections and alerts

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

async for alert in client.telemetry.watch_alerts(min_severity=telemetry_pb2.ALERT_SEVERITY_WARNING):
    print(alert.asset.sn, telemetry_pb2.AlertSeverity.Name(alert.severity), alert.code, alert.message)
```

`watch_detections(asset_sns=None, *, heartbeat_timeout=35s)` yields `DetectionBatch`es,
`watch_alerts(asset_sns=None, *, min_severity=ALERT_SEVERITY_UNSPECIFIED, heartbeat_timeout=35s)`
yields `Alert`s (stable `code` such as `dock.rain`, `message`, `details`) of at least
`min_severity`. Heartbeats, refusals and a dropped stream behave as for `watch_telemetry`.

**Upgrading from 2.x:** the typed per-command methods (`client.remote_control`) and the 2.x live
data client (`client.live_data`) are removed in 3.0. [MIGRATION.md](MIGRATION.md) maps every typed
call to its command id and params.

---

## Mission autonomy and connector

`client.mission_autonomy` manages Applications (upsert, get, list, delete, environments, promote a
version), runs them (`execute_application`, `execute_skill`, `execute_simple`, the
`create_*_execution` variants), drives a run (`start_`, `pause_`, `resume_`, `cancel_`,
`signal_skill_execution`), reads runs (`get_skill_execution`, `list_skill_executions`) and
schedulers. `client.connector` reads and registers assets, sub-assets and payloads, organizations,
policies, technical configs, the skill registry and schedulers, and `asset_monitoring(sn, on_data)`
streams asset monitoring updates (a `StreamHandle`; `await handle.stop()`).

---

## Authentication

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

### A credential that is not one fixed token

A service that forwards its own caller's token, or rotates a short-lived one, passes its own
`grpc.aio` interceptors: `ZequentClient(..., interceptors=[...])` or
`ZequentClient.from_env(interceptors=[...])`. They go on every channel (all four services, unary and
streaming calls), in the order given, before the SDK's credential interceptor. An `authorization`
header they set wins, and the fixed client token is then not sent.

## Error handling

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

## Resilience

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

## Architecture

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

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for setup, testing, linting and release
instructions.

---

## License

Licensed under the [Apache License, Version 2.0](LICENSE); see [NOTICE](NOTICE).
