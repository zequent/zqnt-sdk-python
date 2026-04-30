# edge-python-sdk (Python)

Python SDK for building Zequent edge adapters.

You implement one class; the SDK runs the gRPC server.

## Install

```bash
uv add edge-python-sdk
```

Python 3.12+.

## Example

```python
import asyncio
from edge_sdk import (
    EdgeAdapter, EdgeServer, AssetType,
    Coordinates, EdgeResponse, RequestContext,
)


class MyAdapter(EdgeAdapter):
    async def get_capabilities(self, sn, asset_id):
        return self._auto_capabilities(sn, AssetType.DOCK)

    async def take_off(self, ctx: RequestContext, coords: Coordinates) -> EdgeResponse:
        # call your hardware here
        return EdgeResponse.ok(ctx.tid, ctx.sn)


asyncio.run(EdgeServer(adapter=MyAdapter(), port=50051).serve())
```

Override only the methods your hardware supports. Anything you don't
override is reported as `UNIMPLEMENTED` automatically.

## Build

```bash
uv build
```
