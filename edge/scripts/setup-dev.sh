#!/bin/bash
# Setup development environment with uv
set -e

echo "Setting up development environment..."
echo ""

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "uv is not installed"
    echo ""
    echo "Install uv with:"
    echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

echo "uv is installed"
echo ""

# Optional: Set GitHub token for private repos
echo "Setting up GitHub token (optional, for private repos)..."
if [ -z "$GITHUB_TOKEN" ]; then
    echo "(skipped - GITHUB_TOKEN not set)"
    echo "To use private repos, set: export GITHUB_TOKEN=your_token"
else
    echo "GITHUB_TOKEN is set"
fi

echo ""
echo "Installing dependencies..."
uv sync --all-extras

echo ""
echo "Development environment ready!"
echo ""
echo "Quick commands:"
echo "uv run pytest tests/ -v # Run all tests"
echo "uv run pytest tests/ --cov # With coverage"
echo "uv run ruff check . # Lint code"
echo "uv run ruff format . # Format code"
echo "uv shell # Enter virtual environment"
echo "bash scripts/test.sh # Run tests (full)"
echo "bash scripts/ci.sh # Run full CI checks"
echo ""
echo "GitHub Packages:"
echo "If using private zqnt_utils, set token:"
echo "export GITHUB_TOKEN=your_pat_token"
echo ""
echo "For more info, see:"
echo "- README.md (Usage)"
echo "- DEVELOPMENT.md (Development)"
echo "- UV_SETUP.md (uv & private packages)"
