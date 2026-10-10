"""Example: command an asset by id on a Zequent 3.0 platform.

ZQNT_CLIENT_TOKEN=... ASSET_SN=DOCK-1 uv run python main.py
"""

import asyncio
import logging
import os

from zqnt_utils.generated.zqnt.capability.v3 import command_pb2

from client_sdk import CommandError, ZequentClient
from client_sdk.commands import to_dict

logging.basicConfig(level=logging.INFO)

TERMINAL = {
    command_pb2.COMMAND_STATE_SUCCEEDED,
    command_pb2.COMMAND_STATE_FAILED,
    command_pb2.COMMAND_STATE_CANCELLED,
    command_pb2.COMMAND_STATE_TIMED_OUT,
}


async def main() -> None:
    asset_sn = os.environ.get("ASSET_SN", "DOCK-1")
    async with ZequentClient.from_env() as client:
        capabilities = await client.commands.list_capabilities(asset_sn)
        for capability in capabilities.capabilities:
            print(capability.command_id, capability.display_name)

        try:
            result = await client.commands.execute_command(asset_sn, "dock.open_cover")
        except CommandError as error:
            print("refused:", error.category_name, error.code, error)
            return

        if result.state not in TERMINAL:
            async for event in client.commands.watch_command(result.command_execution_id):
                print(command_pb2.CommandState.Name(event.state), event.message)
                if event.state in TERMINAL:
                    print("result:", to_dict(event.result))
        else:
            print(command_pb2.CommandState.Name(result.state), to_dict(result.result))


if __name__ == "__main__":
    asyncio.run(main())
