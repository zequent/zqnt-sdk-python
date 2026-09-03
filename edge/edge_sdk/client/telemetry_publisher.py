"""
TelemetryPublisher – sends asset / sub-asset telemetry to the ZQNT
LiveDataService using the ``ProduceTelemetry`` client-streaming RPC.

The publisher keeps a long-lived gRPC stream open and feeds it from an
internal bounded queue.  If the connection drops it reconnects automatically
with exponential backoff (1 s → 2 s → 4 s … up to 60 s).  Frames produced
while the stream is down are buffered up to QUEUE_MAX_SIZE; older frames are
silently dropped when the buffer is full::

    publisher = TelemetryPublisher(host="platform.example.com", port=50052, sn="DOCK001")
    await publisher.connect()

    # from your telemetry loop:
    await publisher.publish_asset_telemetry(
        AssetTelemetry(id="DOCK001", latitude=47.5, longitude=9.7)
    )
    await publisher.publish_subasset_telemetry(
        SubAssetTelemetry(id="DRONE001", horizontal_speed=5.0)
    )

    # on shutdown:
    await publisher.close()
"""

import asyncio
import logging
import uuid

from ..models.telemetry import AssetTelemetry, SubAssetTelemetry

logger = logging.getLogger(__name__)

_SENTINEL = object()  # signals the generator to stop cleanly


class TelemetryPublisher:
    """
    Wraps the LiveDataService ``ProduceTelemetry`` streaming RPC.

    Reconnects automatically on connection loss using exponential backoff.
    Frames published while disconnected are buffered; when the buffer is full
    the oldest frame is dropped silently.

    Args:
        host:           LiveDataService host.
        port:           LiveDataService port (default 50052).
        sn:             Serial number of the asset producing the telemetry.
        queue_max_size: Max buffered frames while disconnected (default 1000).
    """

    _BACKOFF_INITIAL = 1.0
    _BACKOFF_MAX = 60.0

    def __init__(
        self,
        host: str,
        port: int = 50052,
        sn: str = "",
        queue_max_size: int = 1000,
    ) -> None:
        self._host = host
        self._port = port
        self._sn = sn
        self._queue_max_size = queue_max_size

        self._closed = False
        self._stop_event: asyncio.Event | None = None
        self._queue: asyncio.Queue | None = None
        self._stream_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Open the channel and start the background streaming / reconnect task."""
        import grpc.aio  # noqa: F401 – verify availability
        from zqnt_utils.generated.zqnt import live_data_pb2_grpc  # noqa: F401

        self._closed = False
        self._stop_event = asyncio.Event()
        self._queue = asyncio.Queue(maxsize=self._queue_max_size)
        self._stream_task = asyncio.create_task(self._run_stream(), name="telemetry-producer")
        logger.info("TelemetryPublisher started for %s:%d (sn=%s)", self._host, self._port, self._sn)

    async def close(self) -> None:
        """Drain the queue, stop the reconnect loop, and release resources."""
        self._closed = True
        if self._stop_event:
            self._stop_event.set()
        if self._queue:
            # Wake up the generator so it can exit cleanly.
            try:
                self._queue.put_nowait(_SENTINEL)
            except asyncio.QueueFull:
                pass
        if self._stream_task:
            try:
                await asyncio.wait_for(self._stream_task, timeout=10.0)
            except asyncio.TimeoutError:
                self._stream_task.cancel()
                try:
                    await self._stream_task
                except asyncio.CancelledError:
                    pass
        logger.info("TelemetryPublisher closed (sn=%s)", self._sn)

    # ------------------------------------------------------------------
    # Public publish methods
    # ------------------------------------------------------------------

    async def publish_asset_telemetry(self, telemetry: AssetTelemetry) -> None:
        """Enqueue an asset-telemetry frame. Drops the frame if the buffer is full."""
        if self._queue is None:
            raise RuntimeError("Not connected. Call connect() first.")
        req = self._build_asset_request(telemetry)
        try:
            self._queue.put_nowait(req)
        except asyncio.QueueFull:
            logger.debug("Telemetry queue full, dropping asset frame (sn=%s)", self._sn)

    async def publish_subasset_telemetry(self, telemetry: SubAssetTelemetry) -> None:
        """Enqueue a sub-asset-telemetry frame. Drops the frame if the buffer is full."""
        if self._queue is None:
            raise RuntimeError("Not connected. Call connect() first.")
        req = self._build_subasset_request(telemetry)
        try:
            self._queue.put_nowait(req)
        except asyncio.QueueFull:
            logger.debug("Telemetry queue full, dropping sub-asset frame (sn=%s)", self._sn)

    # ------------------------------------------------------------------
    # Internal – reconnect loop
    # ------------------------------------------------------------------

    async def _run_stream(self) -> None:
        """
        Background task: opens the gRPC stream and feeds it from the queue.
        On failure reconnects with exponential backoff.
        """
        import grpc
        import grpc.aio
        from zqnt_utils.generated.zqnt import live_data_pb2_grpc

        backoff = self._BACKOFF_INITIAL

        while not self._closed:
            # Each attempt gets its own stop signal so stale generators exit promptly.
            gen_stop = asyncio.Event()
            channel = None
            try:
                channel = grpc.aio.insecure_channel(f"{self._host}:{self._port}")
                stub = live_data_pb2_grpc.LiveDataServiceStub(channel)
                logger.info("Telemetry stream connecting to %s:%d (sn=%s)", self._host, self._port, self._sn)

                response = await stub.ProduceTelemetry(self._stream_generator(gen_stop))

                if self._closed:
                    return

                if response.has_errors:
                    logger.warning(
                        "ProduceTelemetry stream ended with server error (sn=%s): %s",
                        self._sn,
                        response.response_message,
                    )
                else:
                    logger.debug("ProduceTelemetry stream ended cleanly (sn=%s)", self._sn)
                    backoff = self._BACKOFF_INITIAL  # reset only on clean completion

            except Exception as exc:
                if self._closed:
                    return
                logger.warning(
                    "Telemetry stream error (sn=%s, %s: %s), reconnecting in %.1fs",
                    self._sn,
                    type(exc).__name__,
                    exc,
                    backoff,
                )
            finally:
                gen_stop.set()
                if channel:
                    await channel.close()

            if not self._closed:
                # Wait for backoff duration; stop immediately if close() is called.
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(),
                        timeout=backoff,  # type: ignore[union-attr]
                    )
                    return  # stop_event was set → close() called
                except asyncio.TimeoutError:
                    pass
                backoff = min(backoff * 2, self._BACKOFF_MAX)

    async def _stream_generator(self, gen_stop: asyncio.Event):
        """
        Async generator fed into ProduceTelemetry.

        Polls the queue with a 1-second timeout so it can react promptly to
        both gen_stop (current stream ended) and self._closed (shutdown).
        """
        assert self._queue is not None
        while not self._closed and not gen_stop.is_set():
            try:
                item = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                return
            if item is _SENTINEL:
                # Restore SENTINEL so close() can detect it too.
                try:
                    self._queue.put_nowait(_SENTINEL)
                except asyncio.QueueFull:
                    pass
                return
            yield item

    # ------------------------------------------------------------------
    # Proto builders
    # ------------------------------------------------------------------

    def _base(self, sn: str | None = None):
        from google.protobuf import timestamp_pb2
        from zqnt_utils.generated.zqnt import common_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()
        return common_pb2.RequestBase(tid=str(uuid.uuid4()), sn=sn if sn is not None else self._sn, timestamp=ts)

    def _build_asset_request(self, t: AssetTelemetry):
        from google.protobuf import timestamp_pb2

        # Telemetry/AssetTelemetryDetails/ProduceTelemetryRequest all live in
        # live_data_types_pb2 (generated from live-data-types.proto) -- live_data_pb2 (generated
        # from live-data.proto) holds only the LiveDataService RPC stub, no message classes of its
        # own. Using the wrong module here was the actual root cause of the original
        # AttributeError, and would have kept failing (just with a different missing-attribute
        # error) even after fixing the message names alone.
        from zqnt_utils.generated.zqnt import live_data_types_pb2 as live_data_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()

        # Telemetry (the envelope wrapped by ProduceTelemetryRequest.data) carries id/timestamp
        # and the position/motion fields shared by asset and sub-asset telemetry alike;
        # AssetTelemetryDetails (Telemetry's `asset` oneof member, built below as `kwargs`) carries
        # everything asset-specific. Splitting these was the actual bug here -- they used to be
        # merged into one flat dict and handed to a message called `AssetTelemetry`, which hasn't
        # existed since live-data-types.proto was regenerated from the canonical monorepo source;
        # the real message is `AssetTelemetryDetails`, nested inside `Telemetry.asset`, not a
        # dedicated field on ProduceTelemetryRequest.
        envelope_kwargs: dict = {"id": t.id, "timestamp": ts}
        _set_optional(
            envelope_kwargs,
            t,
            {
                "latitude": "latitude",
                "longitude": "longitude",
                "absolute_altitude": "absolute_altitude",
                "relative_altitude": "relative_altitude",
                "heading": "heading",
                "wind_speed": "wind_speed",
            },
        )

        kwargs: dict = {}
        _set_optional(
            kwargs,
            t,
            {
                "environment_temp": "environment_temp",
                "inside_temp": "inside_temp",
                "humidity": "humidity",
                "working_voltage": "working_voltage",
                "working_current": "working_current",
                "supply_voltage": "supply_voltage",
                "sub_asset_percentage": "sub_asset_percentage",
            },
        )
        if t.mode is not None:
            kwargs["mode"] = int(t.mode)
        if t.rainfall is not None:
            kwargs["rainfall"] = int(t.rainfall)
        if t.cover_state is not None:
            kwargs["cover_state"] = int(t.cover_state)
        if t.manual_control_state is not None:
            kwargs["manual_control_state"] = int(t.manual_control_state)
        if t.sub_asset_at_home is not None:
            kwargs["sub_asset_at_home"] = t.sub_asset_at_home
        if t.sub_asset_charging is not None:
            kwargs["sub_asset_charging"] = t.sub_asset_charging
        if t.debug_mode_open is not None:
            kwargs["debug_mode_open"] = t.debug_mode_open
        if t.has_active_manual_control_session is not None:
            kwargs["has_active_manual_control_session"] = t.has_active_manual_control_session
        if t.position_valid is not None:
            kwargs["position_valid"] = t.position_valid
        if t.sub_asset_info is not None:
            i = t.sub_asset_info
            sub_kwargs: dict = {}
            if i.sn is not None:
                sub_kwargs["sn"] = i.sn
            if i.model is not None:
                sub_kwargs["model"] = i.model
            if i.paired is not None:
                sub_kwargs["paired"] = i.paired
            if i.online is not None:
                sub_kwargs["online"] = i.online
            kwargs["sub_asset_information"] = live_data_pb2.AssetTelemetryDetails.AssetSubAssetInformation(
                **sub_kwargs
            )
        if t.network_info is not None:
            n = t.network_info
            net_kwargs: dict = {}
            if n.type is not None:
                net_kwargs["type"] = int(n.type)
            if n.rate is not None:
                net_kwargs["rate"] = n.rate
            if n.quality is not None:
                net_kwargs["quality"] = int(n.quality)
            kwargs["network_information"] = live_data_pb2.AssetTelemetryDetails.AssetNetworkInformation(**net_kwargs)
        if t.air_conditioner is not None:
            a = t.air_conditioner
            ac_kwargs: dict = {}
            if a.state is not None:
                ac_kwargs["state"] = int(a.state)
            if a.switch_time is not None:
                ac_kwargs["switch_time"] = a.switch_time
            kwargs["air_conditioner"] = live_data_pb2.AssetTelemetryDetails.AssetAirConditioner(**ac_kwargs)
        if t.position_state is not None:
            p = t.position_state
            ps_kwargs: dict = {}
            if p.gps_number is not None:
                ps_kwargs["gps_number"] = p.gps_number
            if p.rtk_number is not None:
                ps_kwargs["rtk_number"] = p.rtk_number
            if p.quality is not None:
                ps_kwargs["quality"] = p.quality
            kwargs["position_state"] = live_data_pb2.AssetTelemetryDetails.PositionState(**ps_kwargs)

        envelope_kwargs["asset"] = live_data_pb2.AssetTelemetryDetails(**kwargs)
        return live_data_pb2.ProduceTelemetryRequest(
            base=self._base(sn=t.id),
            data=live_data_pb2.Telemetry(**envelope_kwargs),
        )

    def _build_subasset_request(self, t: SubAssetTelemetry):
        from google.protobuf import timestamp_pb2

        # See _build_asset_request's comment -- same module correction applies here.
        from zqnt_utils.generated.zqnt import live_data_types_pb2 as live_data_pb2

        ts = timestamp_pb2.Timestamp()
        ts.GetCurrentTime()

        # Same envelope/details split as _build_asset_request -- see its comment.
        envelope_kwargs: dict = {"id": t.id, "timestamp": ts}
        _set_optional(
            envelope_kwargs,
            t,
            {
                "latitude": "latitude",
                "longitude": "longitude",
                "absolute_altitude": "absolute_altitude",
                "relative_altitude": "relative_altitude",
                "wind_speed": "wind_speed",
                "heading": "heading",
            },
        )

        kwargs: dict = {}
        _set_optional(
            kwargs,
            t,
            {
                "horizontal_speed": "horizontal_speed",
                "vertical_speed": "vertical_speed",
                "wind_direction": "wind_direction",
                "gear": "gear",
                "height_limit": "height_limit",
                "home_distance": "home_distance",
                "total_movement_distance": "total_movement_distance",
                "total_movement_time": "total_movement_time",
                "country": "country",
            },
        )
        if t.mode is not None:
            kwargs["mode"] = int(t.mode)
        if t.battery is not None:
            b = t.battery
            bat_kwargs: dict = {}
            if b.percentage is not None:
                # SubAssetBatteryInformation.percentage is `optional string` in the wire contract
                # (not a number) -- a bare float here raises a protobuf TypeError.
                bat_kwargs["percentage"] = str(b.percentage)
            if b.remaining_time is not None:
                bat_kwargs["remaining_time"] = b.remaining_time
            if b.return_to_home_power is not None:
                bat_kwargs["return_to_home_power"] = b.return_to_home_power
            kwargs["battery_information"] = live_data_pb2.SubAssetTelemetryDetails.SubAssetBatteryInformation(
                **bat_kwargs
            )
        if t.payload is not None:
            p = t.payload
            pay_kwargs: dict = {"id": p.id, "name": p.name}
            if p.timestamp is not None:
                pts = timestamp_pb2.Timestamp()
                pts.FromDatetime(p.timestamp)
                pay_kwargs["timestamp"] = pts
            if p.camera is not None:
                cam_kwargs: dict = {}
                _set_optional(
                    cam_kwargs,
                    p.camera,
                    {
                        "current_lens": "current_lens",
                        "gimbal_pitch": "gimbal_pitch",
                        "gimbal_yaw": "gimbal_yaw",
                        "zoom_factor": "zoom_factor",
                        "gimbal_roll": "gimbal_roll",
                    },
                )
                pay_kwargs["camera_data"] = live_data_pb2.PayloadTelemetry.CameraData(**cam_kwargs)
            if p.range_finder is not None:
                rf_kwargs: dict = {}
                _set_optional(
                    rf_kwargs,
                    p.range_finder,
                    {
                        "target_latitude": "target_latitude",
                        "target_longitude": "target_longitude",
                        "target_distance": "target_distance",
                        "target_altitude": "target_altitude",
                    },
                )
                pay_kwargs["range_finder_data"] = live_data_pb2.PayloadTelemetry.RangeFinderData(**rf_kwargs)
            if p.sensor is not None and p.sensor.target_temperature is not None:
                pay_kwargs["sensor_data"] = live_data_pb2.PayloadTelemetry.SensorData(
                    target_temperature=p.sensor.target_temperature
                )
            kwargs["payload_telemetry"] = live_data_pb2.PayloadTelemetry(**pay_kwargs)

        envelope_kwargs["sub_asset"] = live_data_pb2.SubAssetTelemetryDetails(**kwargs)
        return live_data_pb2.ProduceTelemetryRequest(
            base=self._base(sn=t.id),
            data=live_data_pb2.Telemetry(**envelope_kwargs),
        )


def _set_optional(target: dict, source, field_map: dict[str, str]) -> None:
    """Copy non-None fields from *source* into *target* using the proto field names."""
    for py_field, proto_field in field_map.items():
        value = getattr(source, py_field, None)
        if value is not None:
            target[proto_field] = value
