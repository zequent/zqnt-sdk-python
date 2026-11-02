"""
Attaching an adapter to a local Edge Node instead of the platform.

An Edge Node (``zqnt-edge-node``) runs next to the adapters on the device and owns the link to the
platform: it queues live data while the link is down and runs the platform's commands on the
adapters. An attached adapter talks to the node only, over two Unix sockets:

* the **node socket** (``ZQNT_EDGE_NODE_SOCKET``): the adapter calls
  ``zqnt.telemetry.v3.TelemetryIngestService``, ``zqnt.edge.v3.EdgeGatewayService`` and the node's
  ``NodeQueueService`` there, with the same v3 messages it would send to the platform;
* the **adapter socket** (``ZQNT_ADAPTER_SOCKET``): the adapter serves its
  ``zqnt.edge.v3.EdgeAdapterService`` there, and the node calls it for every command. The adapter
  names this socket to the node in the ``zqnt-adapter-endpoint`` header of every call.

Attached, the adapter has no access to core: it writes nothing to Redis, and it does not verify the
platform's service token on commands from a Unix socket peer, because the node does not sign them
yet (zqnt-api#40). The socket's permissions (owner and group, 0660) are the access control. No TCP
port is served, and a call over TCP would still be verified.
"""

from __future__ import annotations

import dataclasses
import logging
import os
import stat
import tempfile
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

import grpc
import grpc.aio
from google.protobuf import empty_pb2, struct_pb2

logger = logging.getLogger(__name__)

NODE_SOCKET_ENV = "ZQNT_EDGE_NODE_SOCKET"
ADAPTER_SOCKET_ENV = "ZQNT_ADAPTER_SOCKET"
ADAPTER_ENDPOINT_HEADER = "zqnt-adapter-endpoint"
QUEUE_SERVICE = "zqnt.edgenode.local.v1.NodeQueueService"
DEFAULT_SOCKET_MODE = 0o660


@dataclasses.dataclass(frozen=True)
class EdgeNodeConfig:
    """
    Where the node and this adapter listen.

    Attributes:
        node_socket:    The node's socket (``ZQNT_EDGE_NODE_SOCKET``), e.g. ``/run/zqnt-edge-node/node.sock``.
        adapter_socket: This adapter's socket (``ZQNT_ADAPTER_SOCKET``), e.g. ``/run/zqnt-adapter/dji.sock``.
        socket_mode:    Permission bits of the adapter socket; the owner and the group only.
    """

    node_socket: str
    adapter_socket: str
    socket_mode: int = DEFAULT_SOCKET_MODE

    def __post_init__(self) -> None:
        if not self.node_socket or not self.adapter_socket:
            raise ValueError(f"an Edge Node attach needs both {NODE_SOCKET_ENV} and {ADAPTER_SOCKET_ENV}")
        if self.socket_mode & 0o007 or self.socket_mode & ~0o777:
            raise ValueError(f"socket mode {self.socket_mode:#o}: only owner and group may have access")
        object.__setattr__(self, "node_socket", os.path.abspath(self.node_socket))
        object.__setattr__(self, "adapter_socket", os.path.abspath(self.adapter_socket))

    @classmethod
    def from_env(cls) -> "EdgeNodeConfig | None":
        """The attach from the environment; None when neither socket is set (direct mode)."""
        node = os.getenv(NODE_SOCKET_ENV) or ""
        adapter = os.getenv(ADAPTER_SOCKET_ENV) or ""
        if not node and not adapter:
            return None
        return cls(node_socket=node, adapter_socket=adapter)

    @property
    def node_target(self) -> str:
        """The gRPC target of the node socket."""
        return f"unix:{self.node_socket}"

    @property
    def adapter_endpoint(self) -> str:
        """This adapter's socket as the node dials it: ``unix:///abs/path``."""
        return f"unix://{self.adapter_socket}"

    def channel(self) -> grpc.aio.Channel:
        """A channel to the node that names this adapter's socket on every call."""
        return grpc.aio.insecure_channel(
            self.node_target, interceptors=metadata_interceptors([(ADAPTER_ENDPOINT_HEADER, self.adapter_endpoint)])
        )


class _Metadata:
    def __init__(self, pairs: Sequence[tuple[str, str]]) -> None:
        self._pairs = list(pairs)

    def _details(self, details):
        return details._replace(metadata=list(details.metadata or []) + self._pairs)


# One class per call type, each with exactly one grpc.aio base (see edge_sdk.auth._Bearer).


class _MetadataUnaryUnary(_Metadata, grpc.aio.UnaryUnaryClientInterceptor):
    async def intercept_unary_unary(self, continuation, client_call_details, request):
        return await continuation(self._details(client_call_details), request)


class _MetadataUnaryStream(_Metadata, grpc.aio.UnaryStreamClientInterceptor):
    async def intercept_unary_stream(self, continuation, client_call_details, request):
        return await continuation(self._details(client_call_details), request)


class _MetadataStreamUnary(_Metadata, grpc.aio.StreamUnaryClientInterceptor):
    async def intercept_stream_unary(self, continuation, client_call_details, request_iterator):
        return await continuation(self._details(client_call_details), request_iterator)


class _MetadataStreamStream(_Metadata, grpc.aio.StreamStreamClientInterceptor):
    async def intercept_stream_stream(self, continuation, client_call_details, request_iterator):
        return await continuation(self._details(client_call_details), request_iterator)


def metadata_interceptors(pairs: Sequence[tuple[str, str]]) -> list:
    """Interceptors that add ``pairs`` to every call type of a grpc.aio channel."""
    return [
        _MetadataUnaryUnary(pairs),
        _MetadataUnaryStream(pairs),
        _MetadataStreamUnary(pairs),
        _MetadataStreamStream(pairs),
    ]


def bind_adapter_socket(server: grpc.aio.Server, config: EdgeNodeConfig) -> str:
    """
    Binds ``server`` to the adapter socket with its mode set before the socket appears at its path:
    it is bound in a fresh private directory next to it and renamed into place. A stale socket at
    the path is replaced; any other file there is an error. Returns the socket path.
    """
    path = config.adapter_socket
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    if existing is not None and not stat.S_ISSOCK(existing.st_mode):
        raise RuntimeError(f"{path} exists and is not a socket")
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o750, exist_ok=True)
    private = tempfile.mkdtemp(prefix=".zqnt-sock-", dir=directory)
    try:
        bound = os.path.join(private, "s")
        server.add_insecure_port(f"unix:{bound}")
        os.chmod(bound, config.socket_mode)
        os.replace(bound, path)
    finally:
        try:
            os.rmdir(private)
        except OSError:
            pass
    return path


def remove_adapter_socket(config: EdgeNodeConfig) -> None:
    try:
        if stat.S_ISSOCK(os.lstat(config.adapter_socket).st_mode):
            os.remove(config.adapter_socket)
    except FileNotFoundError:
        pass


@dataclasses.dataclass(frozen=True)
class LaneStats:
    """One lane of the node's queue, and how hard the adapter should push into it."""

    lane: str
    items: int
    bytes: int
    max_items: int
    max_bytes: int
    fill: float
    dropped: int
    oldest: datetime | None
    throttle: float


@dataclasses.dataclass(frozen=True)
class QueueStats:
    """The node's queue as an adapter sees it."""

    connected: bool
    lanes: tuple[LaneStats, ...]

    def lane(self, name: str) -> LaneStats | None:
        """The stats of a lane, e.g. ``"LANE_TELEMETRY"``."""
        for lane in self.lanes:
            if lane.lane == name:
                return lane
        return None

    def throttle(self, name: str) -> float:
        """The share of its normal rate the adapter should send into a lane at (1 when unknown)."""
        lane = self.lane(name)
        return lane.throttle if lane is not None else 1.0

    @classmethod
    def from_struct(cls, s: struct_pb2.Struct) -> "QueueStats":
        fields = s.fields
        lanes = []
        for value in fields["lanes"].list_value.values if "lanes" in fields else ():
            f = value.struct_value.fields
            oldest = f["oldest"].string_value if "oldest" in f else ""
            lanes.append(
                LaneStats(
                    lane=f["lane"].string_value,
                    items=int(f["items"].number_value),
                    bytes=int(f["bytes"].number_value),
                    max_items=int(f["max_items"].number_value),
                    max_bytes=int(f["max_bytes"].number_value),
                    fill=f["fill"].number_value,
                    dropped=int(f["dropped"].number_value),
                    oldest=datetime.fromisoformat(oldest) if oldest else None,
                    throttle=f["throttle"].number_value,
                )
            )
        return cls(connected=fields["connected"].bool_value if "connected" in fields else False, lanes=tuple(lanes))


class NodeQueueClient:
    """
    Reads the node's queue (``zqnt.edgenode.local.v1.NodeQueueService``): how full each lane is,
    whether the node has a link to the platform, and the throttle the adapter should apply::

        stats = await runtime.node_queue.get()
        rate = base_rate * stats.throttle("LANE_TELEMETRY")

        async for stats in runtime.node_queue.watch():
            ...
    """

    def __init__(self, config: EdgeNodeConfig) -> None:
        self._config = config
        self._channel: grpc.aio.Channel | None = None
        self._latest: QueueStats | None = None

    @property
    def latest(self) -> QueueStats | None:
        """The stats last read by :meth:`get` or :meth:`watch`."""
        return self._latest

    def _open(self) -> grpc.aio.Channel:
        if self._channel is None:
            self._channel = self._config.channel()
        return self._channel

    async def get(self, timeout: float = 5.0) -> QueueStats:
        call = self._open().unary_unary(
            f"/{QUEUE_SERVICE}/GetQueueStats",
            request_serializer=empty_pb2.Empty.SerializeToString,
            response_deserializer=struct_pb2.Struct.FromString,
        )
        self._latest = QueueStats.from_struct(await call(empty_pb2.Empty(), timeout=timeout))
        return self._latest

    async def watch(self) -> AsyncIterator[QueueStats]:
        """The stats at once, then whenever a throttle or the link changes (at least every 10 s)."""
        call = self._open().unary_stream(
            f"/{QUEUE_SERVICE}/WatchQueueStats",
            request_serializer=empty_pb2.Empty.SerializeToString,
            response_deserializer=struct_pb2.Struct.FromString,
        )
        async for message in call(empty_pb2.Empty()):
            self._latest = QueueStats.from_struct(message)
            yield self._latest

    async def close(self) -> None:
        if self._channel is not None:
            await self._channel.close()
            self._channel = None


def warn_unverified_commands(config: EdgeNodeConfig) -> None:
    logger.warning(
        "Attached to the Edge Node at %s: commands on %s are NOT verified -- the node does not sign them yet "
        "(zqnt-api#40). The socket's permissions (%#o) are the only access control.",
        config.node_socket,
        config.adapter_socket,
        config.socket_mode,
    )
