#!/bin/bash
# Setup development environment with uv
set -e

echo "Setting up development environment..."
echo ""

if ! command -v uv &> /dev/null; then
    echo "uv is not installed"
    echo ""
    echo "Install uv with:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "uv is installed"
echo ""

echo "Installing dependencies..."
uv sync --all-extras

echo ""
echo "Generating protobuf stubs..."
uv run bash scripts/generate_protos.sh

echo ""
echo "Development environment ready."
echo ""
echo "Quick commands:"
echo "  uv run pytest tests/ -v                # Run all tests"
echo "  uv run pytest tests/ --cov             # With coverage"
echo "  uv run ruff check .                    # Lint code"
echo "  uv run ruff format .                   # Format code"
echo "  bash scripts/test.sh                   # Run tests (full)"
echo "  bash scripts/ci.sh                     # Run full CI checks"
