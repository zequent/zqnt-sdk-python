#!/bin/bash
# Quick test script using uv
set -e

echo "Running tests with uv..."
uv run pytest tests/ -v --cov=client_sdk --cov-report=html

echo ""
echo "Tests passed."
echo "Coverage report: htmlcov/index.html"
