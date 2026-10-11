"""Example: command an asset by id on a Zequent 3.0 platform.

ZQNT_CLIENT_TOKEN=... ASSET_SN=DOCK-1 uv run python main.py
"""

import asyncio
import logging
import os

from client_sdk import CommandError, ZequentClient
from client_sdk.commands import to_dict

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    asset_sn = os.environ.get("ASSET_SN", "DOCK-1")
    async with ZequentClient.from_env() as client:
        capabilities = await client.commands.list_capabilities(asset_sn)
        for capability in capabilities.capabilities:
            print(capability.command_id, capability.display_name)

        try:
            async with asyncio.timeout(300):
                result = await client.commands.execute_and_wait(asset_sn, "dock.open_cover")
        except CommandError as error:
            print("not carried out:", error.category_name, error.code, error)
            return
        print("succeeded:", to_dict(result.result))


if __name__ == "__main__":
    asyncio.run(main())
