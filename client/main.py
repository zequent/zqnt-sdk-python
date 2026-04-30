"""Example usage of the ZQNT Python Client SDK.

This is a placeholder until the sub-clients are wired in. Run with:

    python main.py
"""

import asyncio
import logging

from client_sdk import ZequentClient

logging.basicConfig(level=logging.INFO)


async def main() -> None:
    async with ZequentClient.from_env() as client:
        # Sub-clients (remote_control, mission_autonomy, live_data) will be
        # added in upcoming phases.
        _ = client


if __name__ == "__main__":
    asyncio.run(main())
