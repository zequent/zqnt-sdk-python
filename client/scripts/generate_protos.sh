#!/bin/bash
# Generates Python protobuf + gRPC stubs from the zqnt-protos submodule.
# Requires: pip install grpcio-tools  (or pip install -e ".[dev]")
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PROTO_DIR="$PROJECT_DIR/zqnt-protos"
OUT_DIR="$PROJECT_DIR/client_sdk/generated"

echo "Generating Python gRPC stubs..."
echo "  Proto source : $PROTO_DIR"
echo "  Output       : $OUT_DIR"

mkdir -p "$OUT_DIR"

python -m grpc_tools.protoc \
    -I "$PROTO_DIR" \
    --python_out="$OUT_DIR" \
    --grpc_python_out="$OUT_DIR" \
    "$PROTO_DIR"/*.proto

# grpc_tools emits absolute-style imports (e.g. `import common_pb2 as ...`).
# Fix them to relative so the generated package works as client_sdk.generated.*
echo "Fixing imports in generated files..."
for f in "$OUT_DIR"/*_pb2.py "$OUT_DIR"/*_pb2_grpc.py; do
    [ -f "$f" ] || continue
    # `import foo_pb2 as foo__pb2`  →  `from . import foo_pb2 as foo__pb2`
    sed -i -E 's/^import ([a-zA-Z_]+_pb2) as/from . import \1 as/g' "$f"
done

# Ensure the package marker exists
touch "$OUT_DIR/__init__.py"

# Fix google namespace package for IntelliJ/PyCharm (no __init__.py = unresolvable)
GOOGLE_NS="$PROJECT_DIR/.venv/lib/python3.12/site-packages/google/__init__.py"
if [ -d "$(dirname "$GOOGLE_NS")" ] && [ ! -f "$GOOGLE_NS" ]; then
    touch "$GOOGLE_NS"
    echo "Fixed google namespace package for IDE."
fi

echo "Done. Generated files:"
ls -1 "$OUT_DIR"/*.py 2>/dev/null | sed 's|.*/||'
