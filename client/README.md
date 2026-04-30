# Zequent Client SDK (Python)

Python client library for the Zequent Framework. The Python equivalent
of the Java client SDK (`com.zequent.framework.client.sdk`).

This is a **library**, not a standalone application. You add it as a
dependency to your own Python application (FastAPI, Django, asyncio
script, ...) and use it to call the Zequent platform's gRPC services.

## Architecture

```
+------------------------------+
|  Your Python application     |
|  client = ZequentClient(...) |---+
+------------------------------+   |
                                   |
                          +--------+--------+
                          |  This SDK       |
                          +--------+--------+
                                   |
        +--------------------------+--------------------------+
        v                          v                          v
+----------------+        +----------------+         +----------------+
| Remote Control |        | Mission        |         | Live Data      |
| (port 8002)    |        | Autonomy 8004  |         | (port 8003)    |
+----------------+        +----------------+         +----------------+
```

## Install

Requires Python 3.12+. Built and managed with [uv](https://docs.astral.sh/uv/).

```bash
uv sync
bash scripts/generate_protos.sh
```

The proto definitions live in the `zqnt-protos` git submodule. Run the
generation script once after cloning to produce the gRPC stubs.

## Usage

```python
import asyncio
from client_sdk import ZequentClient, TakeoffRequest

async def main():
    async with ZequentClient.from_env() as client:
        await client.remote_control.takeoff(
            TakeoffRequest(sn="DOCK-1", latitude=37.7, longitude=-122.4, altitude=20)
        )

asyncio.run(main())
```

`ZequentClient` exposes three async sub-clients:

- `client.remote_control` — flight commands, dock and asset operations,
  manual-control client-streaming session.
- `client.mission_autonomy` — mission, task and scheduler CRUD plus
  task lifecycle.
- `client.live_data` — live-stream control, camera operations,
  server-streaming telemetry with auto-reconnect.

## Configuration

Reads the same environment variables as the Java SDK. See
`core/docs/client-sdk/CONFIGURATION.md` for the full list.

## Resilience

Every unary RPC is wrapped in retry + circuit breaker. On transient
errors (`UNAVAILABLE`, `DEADLINE_EXCEEDED`, ...) calls are retried
with exponential backoff. When retries are exhausted, the SDK raises
`ZequentRetryExhaustedError`.

## Tests

```bash
uv run pytest tests/unit -q
```

Integration tests under `tests/integration/` require the dockerised
core stack to be running.

## License

Copyright Zequent Framework.
