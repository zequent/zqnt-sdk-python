# Development guide

Reference for contributing to `zqnt-client-sdk` (Python).

## Prerequisites

- Python **3.12+**
- [`uv`](https://docs.astral.sh/uv/) for dependency and virtualenv management
- (Optional) `protoc` is **not** required — `grpcio-tools` ships its own

Install `uv` if you don't already have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## One-shot setup

```bash
bash scripts/setup-dev.sh
```

This creates the virtualenv, installs dev dependencies, and regenerates the
protobuf stubs.

## Manual setup

```bash
uv sync --all-extras
uv run bash scripts/generate_protos.sh
```

The protobuf stubs land in `client_sdk/generated/`. They are regenerated from
the shared `.proto` files in the framework repo.

## Running tests

```bash
uv run pytest tests/ -v
```

With coverage:

```bash
bash scripts/test.sh
# Open htmlcov/index.html
```

The suite uses `pytest-asyncio` in `auto` mode — async test functions need no
decorator.

## Linting and formatting

```bash
uv run ruff check .          # Lint
uv run ruff check . --fix    # Auto-fix
uv run ruff format .         # Format
uv run ruff format --check . # Verify formatting (CI)
```

Configuration lives in [pyproject.toml](pyproject.toml) under `[tool.ruff]`:

- `line-length = 120`
- `target-version = "py312"`
- Selected rules: `E`, `F`, `W`, `I`, `N`
- Generated protobuf code is excluded

## Full CI checks locally

```bash
bash scripts/ci.sh
```

Equivalent to what runs in GitHub Actions: lint + format check + tests with
coverage.

## Project layout

```
client-python-sdk/
├── client_sdk/                 # Library source
│   ├── __init__.py             # Public exports + __version__
│   ├── zequent_client.py       # Top-level ZequentClient
│   ├── config/                 # Connection + resilience config
│   ├── exceptions.py
│   ├── generated/              # Generated protobuf (gitignored at build)
│   ├── grpc_/                  # gRPC plumbing (channels, resilience)
│   ├── live_data/              # LiveData sub-client + converters
│   ├── mission_autonomy/       # MissionAutonomy sub-client + converters
│   ├── models/                 # Pydantic-style request/response models
│   └── remote_control/         # RemoteControl sub-client
├── tests/
│   └── unit/                   # Async unit tests w/ mocked stubs
├── scripts/
│   ├── setup-dev.sh
│   ├── test.sh
│   ├── ci.sh
│   └── generate_protos.sh
├── .github/workflows/
│   ├── pr.yml                  # PR checks (lint + tests + build)
│   └── main.yml                # Release on push to main
├── DEVELOPMENT.md
├── README.md
└── pyproject.toml
```

## Adding a new RPC

1. Update the relevant `.proto` (in the shared proto repo) and regenerate stubs:
   ```bash
   uv run bash scripts/generate_protos.sh
   ```
2. Add the typed request / response models in `client_sdk/models/`.
3. Implement the method on the sub-client (e.g. `remote_control/client.py`).
   Wrap unary calls with `GrpcResilience` so they get retry + breaker behaviour
   for free.
4. Re-export from `client_sdk/__init__.py` if it is part of the public API.
5. Add a unit test in `tests/unit/` using the mocked-stub pattern already in
   place (see `test_remote_control_client.py` for examples).

## Releasing

Releases are driven by GitHub Actions (`.github/workflows/main.yml`).

1. Bump the version in [pyproject.toml](pyproject.toml) and in
   `client_sdk/__init__.py` fallback.
2. Commit and merge to `main`.
3. The workflow lints, tests, builds, and creates a GitHub Release tagged
   `vX.Y.Z` with the wheel + sdist attached.

The package version is exposed at runtime via `client_sdk.__version__`, which
reads from installed package metadata when available.

## Troubleshooting

- **`ModuleNotFoundError: client_sdk.generated`** — run
  `uv run bash scripts/generate_protos.sh`. The generated package is created
  by the build script and is not committed.
- **`pytest: command not found`** — run `uv sync --all-extras` first; the dev
  group installs pytest into the project venv.
- **Ruff complains about generated code** — generated files are excluded via
  `tool.ruff.exclude` in `pyproject.toml`. Re-run `uv run ruff check .` after
  regenerating.

## Code style

- Public APIs ship with type hints; we ship `py.typed`.
- Async functions everywhere on the I/O path. Avoid mixing sync `grpc` calls.
- Keep proto-to-model conversion in `_converters.py` modules so client code
  stays focused on RPC orchestration.
- Tests must not require a running gRPC server — use the existing
  `MagicMock`-based stub pattern.
