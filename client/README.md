# zqnt-client-sdk (Python)

Python client for the Zequent platform gRPC services.

## Install

```bash
uv add zqnt-client-sdk
```

Python 3.12+.

## Example

```python
import asyncio
from client_sdk import ZequentClient, TakeoffRequest

async def main():
    async with ZequentClient.from_env() as client:
        await client.remote_control.takeoff(TakeoffRequest(sn="DOCK-1"))
        task = await client.mission_autonomy.get_task("task-uuid")

asyncio.run(main())
```

`from_env()` reads `REMOTE_CONTROL_SERVICE_HOST`, `MISSION_AUTONOMY_SERVICE_HOST`,
`LIVE_DATA_SERVICE_HOST` (defaults: `localhost`, ports `8002`/`8004`/`8003`).

## Sub-clients

- `client.remote_control` — flight, manual control, dock ops
- `client.mission_autonomy` — mission / task / scheduler CRUD + start/stop
- `client.live_data` — live stream, camera, telemetry stream

## Build

```bash
uv build
```
