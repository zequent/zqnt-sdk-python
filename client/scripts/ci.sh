#!/bin/bash
# Full CI checks script using uv (linting + testing)
set -e

echo "Running full CI checks with uv..."
echo ""

echo "Linting with ruff..."
uv run ruff check .

echo ""
echo "Formatting check..."
uv run ruff format --check .

echo ""
echo "Running tests..."
uv run pytest tests/ -v --cov=client_sdk --cov-report=html

echo ""
echo "All checks passed."
echo "Coverage report: htmlcov/index.html"
