import pytest

from edge_sdk import EdgeAdapterConfig, EdgeNodeConfig, MissionAutonomyClient


def test_require_before_entering_the_runtime_says_so():
    runtime = EdgeAdapterConfig().runtime()

    with pytest.raises(RuntimeError, match=r"EdgeAdapterRuntime\.connector is not set: enter the runtime first"):
        runtime.require_connector()


def test_require_on_an_edge_node_names_the_missing_client():
    runtime = EdgeAdapterConfig(edge_node=EdgeNodeConfig("/tmp/node.sock", "/tmp/adapter.sock")).runtime()

    for require, name in (
        (runtime.require_connector, "connector"),
        (runtime.require_telemetry, "telemetry"),
        (runtime.require_mission_autonomy, "mission_autonomy"),
    ):
        with pytest.raises(RuntimeError, match=rf"EdgeAdapterRuntime\.{name} is not available .* on an Edge Node"):
            require()


def test_require_returns_the_client_when_set():
    runtime = EdgeAdapterConfig().runtime()
    client = MissionAutonomyClient(host="localhost", token="t")
    runtime.mission_autonomy = client

    assert runtime.require_mission_autonomy() is client
