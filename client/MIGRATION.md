# Migrating from 2.x typed calls to `execute_command`

Zequent 3.0 commands every asset the same way: ask the asset what it can do, then run a command by
its dotted id with a dict of params.

```python
capabilities = await client.commands.list_capabilities("DOCK-1")
result = await client.commands.execute_command(
    "DOCK-1", "navigation.go_to", {"latitude": 52.52, "longitude": 13.405, "altitude": 60}
)
```

The 2.x typed methods on `client.remote_control` still work against 2.x platforms; they are
deprecated and emit a `DeprecationWarning` naming the command id to use instead.
`remote_control.start_manual_control_input(...)` (stick input) is not deprecated.

## Typed call → command id + params

The capability's `input_schema` from `list_capabilities` is authoritative for an asset; the params
below are the ones the built-in commands of every Zequent adapter accept.

| 2.x typed call | Command id | Params |
|---|---|---|
| `takeoff(TakeoffRequest)` | `flight.takeoff` | `latitude`, `longitude`, `altitude` |
| `go_to(GoToRequest)` | `navigation.go_to` | `latitude`, `longitude`, `altitude` (metres above the **takeoff point**; left out = 40 m) |
| `go_to(request, no_fly_zone_override=True)` | `navigation.go_to` | as above, plus `no_fly_zone_override=True` |
| `return_to_home(ReturnToHomeRequest)` | `flight.return_to_home` | `altitude` (optional) |
| `look_at(LookAtRequest)` | `gimbal.look_at` | `latitude`, `longitude`, `altitude`, `locked`, `payloadIndex` |
| `enter_manual_control(...)` | `flight.manual.enter` | none |
| `exit_manual_control(...)` | `flight.manual.exit` | none |
| `open_cover(...)` | `dock.open_cover` | none |
| `close_cover(DockOperationRequest(value=force))` | `dock.close_cover` | `force` (bool, optional) |
| `start_charging(...)` | `dock.start_charging` | none |
| `stop_charging(...)` | `dock.stop_charging` | none |
| `reboot_asset(...)` | `asset.reboot` | none |
| `boot_sub_asset(DockOperationRequest(value=...))` | `asset.boot_sub_asset` | `enabled` (bool: `True` boots, `False` shuts down) |
| `debug_mode(DockOperationRequest(value=...))` | `asset.remote_debug` | `enabled` (bool) |
| `change_ac_mode(...)` | `asset.change_ac_mode` | `mode` (one of the values in the capability's schema; 2.x could not choose one) |

The camera calls on `client.live_data` (`change_lens`, `change_zoom`) are also commands on 3.0:
`camera.change_lens` (`lens`, `videoId`) and `camera.change_zoom` (`lens`, `payloadIndex`, `zoom`).
`camera.take_photo` and `stream.split_screen` (`enabled`) had no typed call in the Python SDK.

**Leave a param out when you have no value.** The platform reads a missing coordinate as "not
given"; sending `0` means latitude 0 / longitude 0 / ground level. A `None` value is left out for you.

## Responses

| 2.x | 3.0 |
|---|---|
| `RemoteControlResponse.success` | `result.state`: `COMMAND_STATE_ACCEPTED`/`_RUNNING` (still underway), `_SUCCEEDED`, `_FAILED`, `_CANCELLED`, `_TIMED_OUT` |
| `error.error_code` / `error_message` | `result.error`: `category`, stable `code` (e.g. `flight.not_airborne`), `message`, `retryable` |
| a refused call (`grpc.aio.AioRpcError`, `ZequentAuthError`) | `CommandError` with `category`, `code`, `status` |
| a command refused before it started | `CommandError` with the rejected `result` (e.g. `ERROR_CATEGORY_INVALID_ARGUMENT` / `command.invalid_params`) |
| `progress` | `async for event in client.commands.watch_command(result.command_execution_id)`: `progress`, `remaining`, `message`, the final `result` |
| `tid` | `result.command_execution_id`: watch it, cancel it with `cancel_command(id, reason)` |
| a result payload | `to_dict(result.result)` (`from client_sdk.commands import to_dict`) |

## Options

```python
await client.commands.execute_command(
    "DOCK-1",
    "flight.return_to_home",
    {"altitude": 80},
    timeout=timedelta(minutes=10),
    reason="battery low",
    idempotency_key=my_request_id,
)
```

`reason` is required for commands whose capability is `COMMAND_RISK_CRITICAL`. The same
`idempotency_key` sent twice runs the command once. `asset_id=` names the asset by its platform id
instead of its serial number, `target=` a payload or sub-asset (`capability_pb2.Target`).
