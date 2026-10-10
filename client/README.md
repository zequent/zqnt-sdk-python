# zqnt-client-sdk (Python)

Python client SDK for the Zequent Framework. Provides an async interface over gRPC
to the Remote Control, Mission Autonomy and Live Data services. On Zequent 3.0 every asset is
commanded by id through `client.commands` (see [Commands](#commands-zequent-30)).

- Python 3.12+
- Async-first (`asyncio` / `grpc.aio`)
- Type hints throughout (`py.typed` marker shipped)
- Built-in retry / circuit-breaker resilience
- Strongly-typed request/response models

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

print(client_sdk.__version__)  # "1.0.1"
```

---

## Quick start

```python
import asyncio
from client_sdk import ZequentClient


async def main():
    async with ZequentClient.from_env() as client:
        # Commands (Zequent 3.0)
        await client.commands.execute_command("DOCK-1", "flight.takeoff", {"altitude": 40})

        # Mission Autonomy
        task = await client.mission_autonomy.get_task("task-uuid")
        print(task)

        # Live Data (server-streaming)
        async for telemetry in client.live_data.stream_telemetry(asset_sn="DOCK-1"):
            print(telemetry)


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

## Commands (Zequent 3.0)

On a 3.0 platform every asset is commanded the same way: list what it can do, then run a command by
its dotted id with a dict of params. There are no typed methods per command.

```python
from client_sdk import CommandError
from client_sdk.commands import to_dict

async with ZequentClient.from_env() as client:
    capabilities = await client.commands.list_capabilities("DOCK-1")
    for capability in capabilities.capabilities:
        print(capability.command_id, capability.safety.risk, capability.input_schema)

    try:
        result = await client.commands.execute_command(
            "DOCK-1", "navigation.go_to", {"latitude": 47.7760, "longitude": 9.2671, "altitude": 60}
        )
    except CommandError as error:
        print(error.category_name, error.code, error)  # e.g. ERROR_CATEGORY_INVALID_ARGUMENT command.invalid_params
    else:
        async for event in client.commands.watch_command(result.command_execution_id):
            print(event.state, event.progress, to_dict(event.result))
```

| Method | Purpose |
| --- | --- |
| `list_capabilities(asset_sn)` | The asset's `CapabilitySet`: command ids, input/output JSON schemas, risk, declared errors and events |
| `execute_command(asset_sn, command_id, params=None, *, asset_id, target, timeout, reason, no_fly_zone_override, idempotency_key)` | Run a command; returns the `CommandResult` (`ACCEPTED`/`RUNNING` with a `command_execution_id` while underway, or the final state) |
| `watch_command(command_execution_id)` | Async iterator of that run's events from now on, ending after its terminal event |
| `watch_asset(asset_sn)` | Async iterator of every command event on the asset until you leave the loop |
| `cancel_command(command_execution_id, reason=None)` | Cancel a run |

- A refused call, or a command rejected before it started, raises `CommandError` (`category`,
  `category_name`, `code` such as `command.invalid_params`, `status`, `result`). A command that
  started and failed is returned with state `COMMAND_STATE_FAILED` and its `error`.
- Start watching before a run can finish, or read the final state from `execute_command`.
- `navigation.go_to` altitude is metres above the **takeoff point**. Leave a param out when you
  have no value; never send `0` for "not given". `None` values are left out.
- Results and events are the generated `zqnt.capability.v3` messages; `to_dict(...)` turns a result
  payload into a plain dict.
- `client.commands` uses the remote-control connection, credential and interceptors the client
  already has; nothing else to set up. [`main.py`](main.py) is a runnable example.

**Upgrading from 2.x:** the typed methods on `client.remote_control` are deprecated (they emit a
`DeprecationWarning` naming the command id) and keep working against 2.x platforms.
[MIGRATION.md](MIGRATION.md) maps every typed call to its command id and params.

---

## Sub-clients

The top-level `ZequentClient` exposes sub-clients matching the underlying gRPC
services. Each method maps 1:1 to the Java client SDK.

### `client.remote_control` (2.x, deprecated on 3.0)

Flight, manual control, dock and asset operations for 2.x platforms. On 3.0 use `client.commands`;
`start_manual_control_input` stays the way to fly by hand.

| Method                         | Purpose                                  |
| ------------------------------ | ---------------------------------------- |
| `takeoff(req)`                 | Launch an asset                          |
| `go_to(req, *, no_fly_zone_override=False)` | Fly-to; the override (org admin / system admin only) flies through a no-fly zone that would refuse it |
| `return_to_home(req)`          | Trigger RTH                              |
| `look_at(req)`                 | Point camera at coordinate               |
| `manual_control(req)`          | Send a single manual-control input       |
| `manual_control_session(...)`  | Open a streaming manual-control session  |
| `dock_operation(req)`          | Open / close / lock / unlock dock        |
| `boot_sub_asset(req)`          | Power on a payload sub-asset             |
| `change_ac_mode(req)`          | Change air-conditioning mode on a dock   |
| `debug_mode(req)`              | Enter / exit debug mode                  |

### `client.mission_autonomy`

Mission, task and scheduler CRUD plus lifecycle operations.

| Method                                                                      | Purpose                          |
| --------------------------------------------------------------------------- | -------------------------------- |
| `create_mission` / `update_mission` / `get_mission` / `delete_mission`      | Mission CRUD                     |
| `create_task` / `update_task` / `get_task` / `delete_task`                  | Task CRUD                        |
| `get_task_by_flight_id(flight_id)`                                          | Lookup by external flight id     |
| `start_task(task_id)` / `stop_task(task_id)`                                | Task lifecycle                   |
| `create_scheduler` / `update_scheduler` / `get_scheduler` / `delete_scheduler` | Scheduler CRUD                |
| `get_all_schedulers()`                                                      | List all schedulers              |

### `client.live_data`

Camera control and live telemetry streaming.

| Method                            | Purpose                                |
| --------------------------------- | -------------------------------------- |
| `start_live_stream(req)`          | Start live stream                      |
| `stop_live_stream(req)`           | Stop live stream                       |
| `change_lens(req)`                | Switch camera lens                     |
| `change_zoom(req)`                | Set zoom factor                        |
| `stream_telemetry(asset_sn, ...)` | Async iterator of telemetry responses  |

---

## Streaming

Server-streaming RPCs return an async iterator. Cancellation happens automatically
when you `break` out of the loop or the surrounding `async with` exits.

```python
async with ZequentClient.from_env() as client:
    async for tel in client.live_data.stream_telemetry(asset_sn="DOCK-1"):
        if tel.battery_percentage < 20:
            break
```

Bi-directional manual control:

```python
async with client.remote_control.manual_control_session(sn="DOCK-1") as session:
    await session.send(ManualControlInput(throttle=0.5, yaw=0.1))
    response = await session.recv()
```

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

`client.commands` raises `CommandError` for every refusal, including exhausted retries
(`retryable=True`) and authentication (`ERROR_CATEGORY_PERMISSION_DENIED`). The 2.x sub-clients
raise `ZequentRetryExhaustedError` when retries give up.

The SDK also exposes `CircuitBreakerOpen` (in `client_sdk.grpc_.resilience`)
raised when the per-method breaker is open.

---

## Resilience

Unary RPCs are wrapped with retry + circuit-breaker policies. Defaults are sane;
override them via `ResilienceConfig`:

```python
from client_sdk.config import ZequentClientConfig
from client_sdk.config.resilience import ResilienceConfig

config = ZequentClientConfig.from_env()
config.resilience = ResilienceConfig(
    max_attempts=5,
    initial_backoff_ms=200,
    max_backoff_ms=5_000,
    breaker_failure_threshold=10,
    breaker_reset_seconds=30,
)
```

Streaming RPCs do not retry transparently — re-subscribe at the application
level when needed.

---

## Architecture

```
ZequentClient
 |- CommandsClient        -> zqnt.control.v3 RemoteControlServiceStub (remote-control channel)
 |- RemoteControlClient   -> remote_control_pb2_grpc.RemoteControlServiceStub
 |- MissionAutonomyClient -> mission_autonomy_pb2_grpc.MissionAutonomyServiceStub
 |- LiveDataClient        -> live_data_pb2_grpc.LiveDataServiceStub
```

Each sub-client owns an `aio` gRPC channel that is closed when the parent
`ZequentClient` exits its `async with` block.

---

## Development

See [DEVELOPMENT.md](DEVELOPMENT.md) for setup, testing, linting and release
instructions.

---

## License

Proprietary - ZQNT Organization
