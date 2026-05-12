# Private GitHub Packages with uv - Complete Answer

This document answers your specific questions about installing `zqnt_utils` and running tests with `uv`.

## Your Questions Answered

### Q1: How can I install zqnt_utils from private GitHub?

**Answer: 3 options, from simplest to most advanced** #### OPTION 1: Git URL (RECOMMENDED - Simplest)

**Best for:** Local development, CI/CD, everyone who wants simplicity

**How to set it up:** 1. Update `pyproject.toml`:
```toml
[project]
dependencies = [
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
    "grpcio-health-checking>=1.60.0",
    "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main", # ← Add this
]
```

2. Install with uv:
```bash
uv sync --all-extras
```

**If private repo:**
```bash
export GITHUB_TOKEN="ghp_your_pat_token"
uv sync --all-extras
```

**Why this is best:**
- Simple to understand
- Works with private repos using git credentials
- No special configuration needed
- Always gets latest code from branch or specific tag
- Perfect for development

---

#### OPTION 2: GitHub Releases (.whl) - Production Ready

**Best for:** Using pre-built packages, production deployments

**Setup:** 1. Create `.uv.toml` in project root:
```toml
[pip]
index = [
    "https://github.com/Zequent/zqnt-utils-python/releases/download/v{version}/zqnt_utils-{version}-py3-none-any.whl",
]
index-fallback = true
```

2. Update `pyproject.toml`:
```toml
[project]
dependencies = [
    "zqnt-utils>=1.0.0", # Just specify version, no git URL
]
```

3. Install:
```bash
export GITHUB_TOKEN="ghp_your_token"
uv sync --all-extras
```

**Why use this:**
- Uses pre-built .whl files (faster)
- Follows Python packaging best practices
- Good for CI/CD when you want stability

---

#### OPTION 3: GitHub Packages Registry - Enterprise

**Best for:** Organizations publishing multiple private packages

Not recommended for your use case (more complex setup). See `UV_SETUP.md` if needed.

---

### Q2: What's the easiest way to install with uv add or uv install?

**Answer: Use `uv add` for git URLs** ```bash
# Add directly from git
uv add "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main"

# Or from a specific tag
uv add "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@v1.0.0"
```

This automatically updates `pyproject.toml` and creates `uv.lock`.

**For private repos:**
```bash
export GITHUB_TOKEN="your_token"
uv add "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main"
```

---

### Q3: How do I run tests with uv?

**Answer: Super simple!** #### Basic test commands:

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage report
uv run pytest tests/ -v --cov=edge_sdk --cov-report=html

# Run specific test file
uv run pytest tests/unit/test_adapter.py -v

# Run specific test
uv run pytest tests/unit/test_adapter.py::test_take_off -v

# Run matching pattern
uv run pytest tests/ -k "adapter" -v
```

#### Or use our helper script:

```bash
# Quick test
bash scripts/test.sh

# Full CI checks (lint + test)
bash scripts/ci.sh
```

#### For interactive shell:

```bash
# Enter the virtual environment
uv shell

# Now run pytest directly
pytest tests/ -v
pytest tests/ --cov=edge_sdk

# Exit shell
exit
```

---

## Complete Setup Example

### Step 1: Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Step 2: Add zqnt_utils

Option A (automatic):
```bash
export GITHUB_TOKEN="ghp_your_token"
uv add "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main"
```

Option B (manual - edit pyproject.toml):
```toml
[project]
dependencies = [
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
    "grpcio-health-checking>=1.60.0",
    "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main",
]
```

### Step 3: Install all dependencies

```bash
uv sync --all-extras
```

### Step 4: Run tests

```bash
uv run pytest tests/ -v --cov=edge_sdk
```

**That's it!** ---

## GitHub Token Management

### Option 1: Temporary (for current session)
```bash
export GITHUB_TOKEN="ghp_your_token"
uv sync
```

### Option 2: Permanent (git credentials storage)
```bash
git config --global credential.helper store
# Next time git asks for password, use your token
# It will be cached automatically
```

### Option 3: SSH Keys (most secure)
```bash
# Generate key
ssh-keygen -t ed25519 -C "your_email@example.com"

# Add to GitHub: https://github.com/settings/keys

# Configure git
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

---

## Speed Comparison

| Method | Install Time | Why |
|--------|-------------|-----|
| `pip install` | ~30 seconds | Standard Python |
| `uv sync` | ~2-5 seconds | Compiled in Rust |
| **uv (cached)** | **<1 second** | Parallel downloads |

---

## Test Running Examples

```bash
# All of these work with uv

# Quick smoke test
uv run pytest tests/unit/test_adapter.py::test_auto_capabilities_only_includes_overridden -v

# All unit tests
uv run pytest tests/unit/ -v

# All integration tests
uv run pytest tests/integration/ -v

# With coverage report (creates htmlcov/index.html)
uv run pytest tests/ --cov=edge_sdk --cov-report=html

# Stop on first failure
uv run pytest tests/ -x

# Show print statements
uv run pytest tests/ -s

# Parallel execution (if pytest-xdist installed)
uv add --dev pytest-xdist
uv run pytest tests/ -n auto
```

---

## Quick Reference

### uv Commands

```bash
# Create/update dependencies
uv sync

# With all extras (dev, redis, etc.)
uv sync --all-extras

# Just dev dependencies
uv sync --only-dev

# Add new package
uv add requests

# Add to dev dependencies
uv add --dev pytest-xdist

# Add from git
uv add "package @ git+https://github.com/user/repo"

# Install specific version
uv add requests==2.31.0

# Remove package
uv remove requests

# Update lock file
uv lock --upgrade

# Enter shell
uv shell

# Run command in environment
uv run python -m pytest
```

### pytest Commands (with uv)

```bash
uv run pytest [options]

# Useful options:
-v # Verbose
-s # Show print statements
-x # Stop on first failure
-k pattern # Run tests matching pattern
--co # List tests without running
--cov=module # Coverage report
--cov-report=html # Generate HTML coverage report
-n auto # Parallel execution (requires pytest-xdist)
```

---

## Recommended Workflow

### For Development:

```bash
# One-time setup
bash scripts/setup-dev.sh

# Run tests while developing
uv run pytest tests/ -v -s

# Before commit
bash scripts/ci.sh # Runs lint + test

# Or manually
uv run ruff format .
uv run ruff check .
uv run pytest tests/ -v
```

### For CI/CD:

```bash
# Install
uv sync --all-extras

# Test
uv run pytest tests/ -v

# Lint
uv run ruff check .
```

---

## Best Practices

### DO:
- Use `uv sync` instead of `pip install`
- Use `uv run pytest` to run tests in correct environment
- Use git URLs for development (`@git+https://...`)
- Set `GITHUB_TOKEN` for private repos
- Commit `uv.lock` file to version control

### DON'T:
- Don't use `pip install` - use `uv add` or `uv sync`
- Don't run `pytest` directly - use `uv run pytest`
- Don't hardcode tokens in `pyproject.toml`
- Don't ignore `uv.lock` in git

---

## Troubleshooting

### "zqnt_utils not found"

```bash
# Set GitHub token
export GITHUB_TOKEN="your_token"
uv sync

# Or
git config --global credential.helper store
# Then git will ask for credentials
```

### "Repository not found"

- Verify repo URL is correct
- Check GitHub token has correct permissions
- Verify you have access to the private repo

### "Module not found after sync"

```bash
# Clear cache and reinstall
uv cache purge
uv sync
```

### Tests can't find zqnt_utils

```bash
# Correct - uses uv's environment
uv run pytest tests/ -v

# Wrong - might use system Python
pytest tests/ -v

# Alternative - enter shell first
uv shell
pytest tests/ -v
```

---

## Documentation

For more details, see:
- **QUICKSTART_UV.md** - 5-minute quick start
- **UV_SETUP.md** - Deep dive on uv and private packages
- **README.md** - SDK usage guide
- **DEVELOPMENT.md** - Development setup

---

## What You Get

With this setup:
- Private `zqnt_utils` package from GitHub
- Fast dependency installation with uv
- One-command test running
- Coverage reports
- CI/CD ready
- Works on Windows, Mac, Linux

---

**Summary:**
- **Simplest install:** `uv add "zqnt-utils @ git+https://github.com/...@main"`
- **Easiest test run:** `uv run pytest tests/ -v`
- **Fastest setup:** `bash scripts/setup-dev.sh`

Happy coding!
# Private GitHub Packages with uv - Complete Answer

This document answers your specific questions about installing `zqnt_utils` and running tests with `uv`.

## Your Questions Answered

### Q1: How can I install zqnt_utils from private GitHub?

**Answer: 3 options, from simplest to most advanced** #### OPTION 1: Git URL (RECOMMENDED - Simplest)

**Best for:** Local development, CI/CD, everyone who wants simplicity

**How to set it up:** 1. Update `pyproject.toml`:
```toml
[project]
dependencies = [
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
    "grpcio-health-checking>=1.60.0",
    "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main", # ← Add this
]
```

2. Install with uv:
```bash
uv sync --all-extras
```

**If private repo:**
```bash
export GITHUB_TOKEN="ghp_your_pat_token"
uv sync --all-extras
```

**Why this is best:**
- Simple to understand
- Works with private repos using git credentials
- No special configuration needed
- Always gets latest code from branch or specific tag
- Perfect for development

---

#### OPTION 2: GitHub Releases (.whl) - Production Ready

**Best for:** Using pre-built packages, production deployments

**Setup:** 1. Create `.uv.toml` in project root:
```toml
[pip]
index = [
    "https://github.com/Zequent/zqnt-utils-python/releases/download/v{version}/zqnt_utils-{version}-py3-none-any.whl",
]
index-fallback = true
```

2. Update `pyproject.toml`:
```toml
[project]
dependencies = [
    "zqnt-utils>=1.0.0", # Just specify version, no git URL
]
```

3. Install:
```bash
export GITHUB_TOKEN="ghp_your_token"
uv sync --all-extras
```

**Why use this:**
- Uses pre-built .whl files (faster)
- Follows Python packaging best practices
- Good for CI/CD when you want stability

---

#### OPTION 3: GitHub Packages Registry - Enterprise

**Best for:** Organizations publishing multiple private packages

Not recommended for your use case (more complex setup). See `UV_SETUP.md` if needed.

---

### Q2: What's the easiest way to install with uv add or uv install?

**Answer: Use `uv add` for git URLs** ```bash
# Add directly from git
uv add "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main"

# Or from a specific tag
uv add "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@v1.0.0"
```

This automatically updates `pyproject.toml` and creates `uv.lock`.

**For private repos:**
```bash
export GITHUB_TOKEN="your_token"
uv add "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main"
```

---

### Q3: How do I run tests with uv?

**Answer: Super simple!** #### Basic test commands:

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage report
uv run pytest tests/ -v --cov=edge_sdk --cov-report=html

# Run specific test file
uv run pytest tests/unit/test_adapter.py -v

# Run specific test
uv run pytest tests/unit/test_adapter.py::test_take_off -v

# Run matching pattern
uv run pytest tests/ -k "adapter" -v
```

#### Or use our helper script:

```bash
# Quick test
bash scripts/test.sh

# Full CI checks (lint + test)
bash scripts/ci.sh
```

#### For interactive shell:

```bash
# Enter the virtual environment
uv shell

# Now run pytest directly
pytest tests/ -v
pytest tests/ --cov=edge_sdk

# Exit shell
exit
```

---

## Complete Setup Example

### Step 1: Install uv

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Step 2: Add zqnt_utils

Option A (automatic):
```bash
export GITHUB_TOKEN="ghp_your_token"
uv add "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main"
```

Option B (manual - edit pyproject.toml):
```toml
[project]
dependencies = [
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
    "grpcio-health-checking>=1.60.0",
    "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main",
]
```

### Step 3: Install all dependencies

```bash
uv sync --all-extras
```

### Step 4: Run tests

```bash
uv run pytest tests/ -v --cov=edge_sdk
```

**That's it!** ---

## GitHub Token Management

### Option 1: Temporary (for current session)
```bash
export GITHUB_TOKEN="ghp_your_token"
uv sync
```

### Option 2: Permanent (git credentials storage)
```bash
git config --global credential.helper store
# Next time git asks for password, use your token
# It will be cached automatically
```

### Option 3: SSH Keys (most secure)
```bash
# Generate key
ssh-keygen -t ed25519 -C "your_email@example.com"

# Add to GitHub: https://github.com/settings/keys

# Configure git
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

---

## Speed Comparison

| Method | Install Time | Why |
|--------|-------------|-----|
| `pip install` | ~30 seconds | Standard Python |
| `uv sync` | ~2-5 seconds | Compiled in Rust |
| **uv (cached)** | **<1 second** | Parallel downloads |

---

## Test Running Examples

```bash
# All of these work with uv

# Quick smoke test
uv run pytest tests/unit/test_adapter.py::test_auto_capabilities_only_includes_overridden -v

# All unit tests
uv run pytest tests/unit/ -v

# All integration tests
uv run pytest tests/integration/ -v

# With coverage report (creates htmlcov/index.html)
uv run pytest tests/ --cov=edge_sdk --cov-report=html

# Stop on first failure
uv run pytest tests/ -x

# Show print statements
uv run pytest tests/ -s

# Parallel execution (if pytest-xdist installed)
uv add --dev pytest-xdist
uv run pytest tests/ -n auto
```

---

## Quick Reference

### uv Commands

```bash
# Create/update dependencies
uv sync

# With all extras (dev, redis, etc.)
uv sync --all-extras

# Just dev dependencies
uv sync --only-dev

# Add new package
uv add requests

# Add to dev dependencies
uv add --dev pytest-xdist

# Add from git
uv add "package @ git+https://github.com/user/repo"

# Install specific version
uv add requests==2.31.0

# Remove package
uv remove requests

# Update lock file
uv lock --upgrade

# Enter shell
uv shell

# Run command in environment
uv run python -m pytest
```

### pytest Commands (with uv)

```bash
uv run pytest [options]

# Useful options:
-v # Verbose
-s # Show print statements
-x # Stop on first failure
-k pattern # Run tests matching pattern
--co # List tests without running
--cov=module # Coverage report
--cov-report=html # Generate HTML coverage report
-n auto # Parallel execution (requires pytest-xdist)
```

---

## Recommended Workflow

### For Development:

```bash
# One-time setup
bash scripts/setup-dev.sh

# Run tests while developing
uv run pytest tests/ -v -s

# Before commit
bash scripts/ci.sh # Runs lint + test

# Or manually
uv run ruff format .
uv run ruff check .
uv run pytest tests/ -v
```

### For CI/CD:

```bash
# Install
uv sync --all-extras

# Test
uv run pytest tests/ -v

# Lint
uv run ruff check .
```

---

## Best Practices

### DO:
- Use `uv sync` instead of `pip install`
- Use `uv run pytest` to run tests in correct environment
- Use git URLs for development (`@git+https://...`)
- Set `GITHUB_TOKEN` for private repos
- Commit `uv.lock` file to version control

### DON'T:
- Don't use `pip install` - use `uv add` or `uv sync`
- Don't run `pytest` directly - use `uv run pytest`
- Don't hardcode tokens in `pyproject.toml`
- Don't ignore `uv.lock` in git

---

## Troubleshooting

### "zqnt_utils not found"

```bash
# Set GitHub token
export GITHUB_TOKEN="your_token"
uv sync

# Or
git config --global credential.helper store
# Then git will ask for credentials
```

### "Repository not found"

- Verify repo URL is correct
- Check GitHub token has correct permissions
- Verify you have access to the private repo

### "Module not found after sync"

```bash
# Clear cache and reinstall
uv cache purge
uv sync
```

### Tests can't find zqnt_utils

```bash
# Correct - uses uv's environment
uv run pytest tests/ -v

# Wrong - might use system Python
pytest tests/ -v

# Alternative - enter shell first
uv shell
pytest tests/ -v
```

---

## Documentation

For more details, see:
- **QUICKSTART_UV.md** - 5-minute quick start
- **UV_SETUP.md** - Deep dive on uv and private packages
- **README.md** - SDK usage guide
- **DEVELOPMENT.md** - Development setup

---

## What You Get

With this setup:
- Private `zqnt_utils` package from GitHub
- Fast dependency installation with uv
- One-command test running
- Coverage reports
- CI/CD ready
- Works on Windows, Mac, Linux

---

**Summary:**
- **Simplest install:** `uv add "zqnt-utils @ git+https://github.com/...@main"`
- **Easiest test run:** `uv run pytest tests/ -v`
- **Fastest setup:** `bash scripts/setup-dev.sh`

Happy coding!
