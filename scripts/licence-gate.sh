#!/usr/bin/env bash
# Licence gate: installs each workspace member's locked dependencies (all extras, so test and
# dev tools too) into a scratch environment, lists them with pip-licenses and checks them
# against licences/policy.yaml. Writes THIRD_PARTY.md; with --check (CI) it fails instead when
# THIRD_PARTY.md is out of date.
set -euo pipefail

PIP_LICENSES_VERSION=5.5.5

cd "$(dirname "$0")/.."
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT

reports=()
for member in edge client; do
  package=$(sed -n 's/^name = "\(.*\)"/\1/p' "$member/pyproject.toml" | head -1)
  UV_PROJECT_ENVIRONMENT="$WORK/$member" uv sync --quiet --frozen --python 3.12 --package "$package" \
    --all-extras --no-install-workspace
  uvx --quiet --from "pip-licenses==$PIP_LICENSES_VERSION" pip-licenses \
    --python "$WORK/$member/bin/python" --from=mixed --format=json >"$WORK/$member.json"
  reports+=("$WORK/$member.json=$member")
done

uv run --quiet --no-project --with pyyaml==6.0.3 python scripts/licence_gate.py \
  --ecosystem python "$@" "${reports[@]}"
