# Migrating from the 2.x client SDK to 3.0

Zequent 3.0 commands every asset the same way: ask the asset what it can do, then run a command by
its dotted id with a dict of params.

```python
capabilities = await client.commands.list_capabilities("DOCK-1")
result = await client.commands.execute_command(
    "DOCK-1", "navigation.go_to", {"latitude": 52.52, "longitude": 13.405, "altitude": 60}
)
```

3.0 removes the 2.x typed command calls: `client.remote_control` (every typed command, the
capability snapshot, custom commands, the 2.x manual control session) and `client.live_data`
(camera and live stream calls, the 2.x telemetry and notification streams), together with their
request/response models (`TakeoffRequest`, `GoToRequest`, `DockOperationRequest`,
`RemoteControlResponse`, `StreamTelemetryRequest`, `ChangeLensRequest`, ...). The tables below
map each of them to its 3.0 replacement. `client.connector` and `client.mission_autonomy` are
unchanged.

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
| `live_data.change_lens(ChangeLensRequest)` | `camera.change_lens` | `lens`, `videoId` |
| `live_data.change_zoom(ChangeZoomRequest)` | `camera.change_zoom` | `lens`, `payloadIndex`, `zoom` |
| `live_data.start_live_stream(LiveDataStartLiveStreamRequest)` | `stream.start` | as in the capability's `input_schema` |
| `live_data.stop_live_stream(LiveDataStopLiveStreamRequest)` | `stream.stop` | as in the capability's `input_schema` |

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
| waiting for the outcome | `await client.commands.execute_and_wait(...)`: the `SUCCEEDED` result, or `CommandError` with the final `result` |
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

## Manual control

| 2.x | 3.0 |
|---|---|
| `remote_control.start_manual_control_input(sn)` | `commands.stream_manual_control(asset_sn)` |
| `remote_control.enter_manual_control(...)` / `exit_manual_control(...)` | `commands.execute_and_wait(asset_sn, "flight.manual.enter")` / `"flight.manual.exit"` |
| `session.send_input(ManualControlInput(...))` | `await stick.send(roll, pitch, yaw, throttle, gimbal_pitch=...)` |
| `session.complete()` (a response) | leave the `async with` block or `await stick.close()`: the number of inputs passed on to the asset |
| a broken stream | `CommandError` from `send` / `close` |

Enter and leave manual control with the commands `flight.manual.enter` and `flight.manual.exit`.

## Telemetry, detections and alerts

| 2.x | 3.0 |
|---|---|
| `live_data.stream_telemetry(...)` | `async for item in telemetry.watch_telemetry(asset_sns, min_interval=...)` |
| `live_data.stream_notifications(...)` | `async for alert in telemetry.watch_alerts(asset_sns, min_severity=...)`; command progress via `commands.watch_asset(asset_sn)` |
| a `StreamHandle` and callbacks | an async iterator: leave the loop to stop |
| per-vendor telemetry types | `TelemetrySample`: position, relative altitude, heading, speeds, battery; the rest in `details` under the capabilities' `telemetry_fields` |
| reconnects on its own | raises `CommandError` on a refusal, a dropped stream or missing heartbeats; watch again |
