# Using Private GitHub Dependencies with uv

This guide explains how to install your private `zqnt_utils` repository and run tests using `uv`.

## 🚀 Quick Start

**Just want to get started fast?** See [QUICKSTART_UV.md](QUICKSTART_UV.md)

**TL;DR:**
```bash
# 1. Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Setup
bash scripts/setup-dev.sh

# 3. Run tests
uv run pytest tests/ -v
```

---

## 🔑 Prerequisites

1. **GitHub Personal Access Token (PAT)**
   - Go to: https://github.com/settings/tokens
   - Create a new token with `read:packages` scope
   - Copy the token (you'll need it)

2. **uv installed**
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   # or
   pip install uv
   ```

3. **Git credentials configured** (recommended)
   ```bash
   git config --global credential.helper store
   ```

---

## 📦 Option 1: Direct GitHub URL (Easiest for Development)

This is the **simplest approach** for local development without needing to publish to PyPI.

### Setup

#### 1. Add to `pyproject.toml`

```toml
[project]
dependencies = [
    "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@v1.0.0",
]
```

Or use `main` branch for latest:

```toml
[project]
dependencies = [
    "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main",
]
```

**If the repo is private**, uv will use your git credentials:

```bash
# Using uv with private repo
uv add "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main"
```

#### 2. Install dependencies

```bash
uv sync
```

Or with all extras:

```bash
uv sync --all-extras
```

### Advantages
✅ Simple and straightforward
✅ No special configuration needed
✅ Works with private repos using git credentials
✅ Always uses latest code from branch or specific tag
✅ Perfect for development workflow

### Disadvantages
❌ Slower than wheel files (needs to clone and build)
❌ Requires git to be available
❌ Can't use `.whl` releases you've created

---

## 📦 Option 2: GitHub Releases (.whl) - RECOMMENDED

This is the **best practice** approach using your pre-built wheel files from GitHub Releases.

### Setup

#### 1. Configure GitHub authentication for uv

Create or update `~/.config/uv/uv.toml`:

```toml
[index]
# Use private index
default = "private"

[[index]]
name = "private"
url = "https://github.com/Zequent/zqnt-utils-python/releases/download/v{version}"
type = "direct"
credentials = "bearertoken"
token = "github_token_here"  # Replace with your PAT

# Fall back to PyPI
[[index]]
name = "pypi"
url = "https://pypi.org/simple"
default-fallback = true
```

**Better approach:** Use environment variable instead of hardcoding token:

```toml
[index]
default = "private"

[[index]]
name = "private"
url = "https://github.com/Zequent/zqnt-utils-python/releases/download/v{version}"
type = "direct"

[[index]]
name = "pypi"
url = "https://pypi.org/simple"
default-fallback = true
```

Then set environment variable:

```bash
export GITHUB_TOKEN="your_pat_token_here"
```

#### 2. Add to `pyproject.toml`

```toml
[project]
dependencies = [
    "zqnt-utils>=1.0.0",
]
```

#### 3. Install

```bash
uv sync
```

### Advantages
✅ Uses pre-built `.whl` files (fast)
✅ More reliable and reproducible
✅ Follows Python packaging best practices
✅ Works with CI/CD easily
✅ Secure with tokens

### Disadvantages
❌ Requires GitHub token setup
❌ More complex initial configuration
❌ Token management needed

---

## 📦 Option 3: GitHub Packages Registry (Enterprise Solution)

If you want to publish `zqnt_utils` to GitHub Packages for all projects.

### Setup

#### 1. Publish to GitHub Packages

In `zqnt_utils` project, add workflow to publish:

```yaml
# .github/workflows/publish.yml
name: Publish to GitHub Packages

on:
  release:
    types: [published]

jobs:
  publish:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      
      - run: |
          pip install build twine
          python -m build
      
      - run: |
          python -m twine upload dist/* \
            --repository-url https://npm.pkg.github.com \
            -u __token__ \
            -p ${{ secrets.GITHUB_TOKEN }}
```

#### 2. Configure uv for GitHub Packages

```toml
# ~/.config/uv/uv.toml
[[index]]
name = "github"
url = "https://npm.pkg.github.com/Zequent/zqnt-utils-python/simple"
credentials = "username-password"
username = "__token__"
password = "YOUR_GITHUB_TOKEN"

# Or use env var:
# password = { env = "GITHUB_TOKEN" }
```

#### 3. Add to `pyproject.toml`

```toml
[project]
dependencies = [
    "zqnt-utils>=1.0.0",
]

[tool.uv]
index = [
    { name = "github", url = "https://npm.pkg.github.com/Zequent/zqnt-utils-python/simple", priority = "primary" },
]
```

#### 4. Install

```bash
export GITHUB_TOKEN="your_token"
uv sync
```

---

## 🏆 RECOMMENDED SOLUTION FOR YOUR CASE

Since you have `.whl` releases on GitHub, here's what I recommend:

### Best Practice Setup

#### Step 1: Create `.uv.toml` (in project root)

```toml
# .uv.toml
[pip]
# Primary index: GitHub releases
index = [
    "https://github.com/Zequent/zqnt-utils-python/releases/download/v{version}/zqnt_utils-{version}-py3-none-any.whl",
]

# Fall back to PyPI for other packages
index-fallback = true
```

#### Step 2: Update `pyproject.toml`

```toml
[project]
name = "edge-python-sdk"
version = "1.0.0"
dependencies = [
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
    "grpcio-health-checking>=1.60.0",
    "zqnt-utils>=1.0.0",
]

[project.optional-dependencies]
redis = ["redis[asyncio]>=5.0.0"]
dev = [
    "grpcio-tools>=1.60.0",
    "grpc-stubs>=1.53.0",
    "mypy-protobuf>=3.6.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "fakeredis[aioredis]>=2.26.0",
    "ruff>=0.15.12",
]
```

#### Step 3: Install dependencies

```bash
uv sync --all-extras
```

#### Step 4: Add authentication (if repo is private)

```bash
# Set GitHub token
export GITHUB_TOKEN="ghp_your_token_here"

# Or configure in git
git config --global credential.https://github.com.username your_username
git config --global credential.https://github.com.password your_token
```

---

## 🧪 Running Tests with uv

### Option 1: Run tests directly with uv

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ -v --cov=edge_sdk --cov-report=html

# Run specific test file
uv run pytest tests/unit/test_adapter.py -v

# Run specific test
uv run pytest tests/unit/test_adapter.py::test_take_off -v
```

### Option 2: Use uv shell

```bash
# Enter virtual environment
uv venv
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Then run pytest directly
pytest tests/ -v
pytest tests/ -v --cov=edge_sdk
```

### Option 3: Create test script with uv

Create `scripts/test.sh`:

```bash
#!/bin/bash
set -e

echo "🧪 Running tests with uv..."
uv run pytest tests/ -v --cov=edge_sdk --cov-report=html
echo "✅ Tests passed!"
echo "📊 Coverage report: htmlcov/index.html"
```

Then run:

```bash
chmod +x scripts/test.sh
./scripts/test.sh
```

### Option 4: Run linting + tests (full CI locally)

Create `scripts/ci.sh`:

```bash
#!/bin/bash
set -e

echo "🔍 Running CI checks with uv..."

echo "📝 Linting with ruff..."
uv run ruff check .

echo "🎨 Formatting check..."
uv run ruff format --check .

echo "🧪 Running tests..."
uv run pytest tests/ -v --cov=edge_sdk --cov-report=html

echo "✅ All checks passed!"
```

Then run:

```bash
chmod +x scripts/ci.sh
./scripts/ci.sh
```

---

## 📝 Full Example Setup

### Update `pyproject.toml`

```toml
[project]
name = "edge-python-sdk"
version = "1.0.0"
description = "Python SDK for implementing ZQNT Edge Adapters"
requires-python = ">=3.12"
dependencies = [
    "grpcio>=1.60.0",
    "protobuf>=4.25.0",
    "grpcio-health-checking>=1.60.0",
    "zqnt-utils>=1.0.0",
]

[project.optional-dependencies]
redis = ["redis[asyncio]>=5.0.0"]
dev = [
    "grpcio-tools>=1.60.0",
    "grpc-stubs>=1.53.0",
    "mypy-protobuf>=3.6.0",
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "fakeredis[aioredis]>=2.26.0",
    "ruff>=0.15.12",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 120
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "N"]
ignore = ["E501"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["edge_sdk"]

# uv configuration
[tool.uv]
dev-dependencies = [
    "pytest-cov>=7.0.0",
]
```

### Create `.uv.toml` in project root

```toml
[pip]
# Use GitHub releases for zqnt-utils
index = [
    "https://github.com/Zequent/zqnt-utils-python/releases/download/v{version}/zqnt_utils-{version}-py3-none-any.whl",
]

# Or use git URL for development
# index = ["git+https://github.com/Zequent/zqnt-utils-python"]

# Fall back to PyPI for other packages
index-fallback = true
```

### Setup script (`.setup-dev.sh`)

```bash
#!/bin/bash
set -e

echo "🚀 Setting up development environment..."

# Export GitHub token (if private repo)
# export GITHUB_TOKEN="your_token_here"

# Create virtual environment
uv venv

# Activate it
source .venv/bin/activate

# Install all dependencies
uv sync --all-extras

echo "✅ Development environment ready!"
echo ""
echo "📚 Quick commands:"
echo "  uv run pytest tests/ -v          # Run tests"
echo "  uv run pytest tests/ --cov       # With coverage"
echo "  uv run ruff check .              # Lint"
echo "  uv run ruff format .             # Format"
echo "  uv shell                         # Enter venv"
```

---

## 🔐 GitHub Token Management

### Option 1: Environment Variable (Temporary)

```bash
export GITHUB_TOKEN="ghp_your_token_here"
uv sync
```

### Option 2: Git Credentials (Persistent)

```bash
git config --global credential.helper store
# Then git will ask for credentials once and cache them
```

### Option 3: SSH Keys (Most Secure)

```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "your_email@example.com"

# Add to GitHub: https://github.com/settings/keys

# Configure git to use SSH
git config --global url."git@github.com:".insteadOf "https://github.com/"
```

### Option 4: `~/.netrc` (Unix/Mac)

```bash
# Create ~/.netrc with
machine github.com
login your_username
password your_token

# Set permissions
chmod 600 ~/.netrc
```

---

## 🐛 Troubleshooting

### Error: "could not find package zqnt_utils"

**Solution 1:** Check GitHub token

```bash
export GITHUB_TOKEN="your_token"
uv sync
```

**Solution 2:** Use git URL instead

```toml
# In pyproject.toml
dependencies = [
    "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main",
]
```

### Error: "Repository not found"

**Solution:** 
- Ensure repo URL is correct
- Check GitHub token has `read:packages` scope
- Verify private repo settings

### Error: "Module not found after install"

**Solution:**

```bash
# Clear cache and reinstall
uv cache purge
uv sync
```

### Tests not finding zqnt_utils

**Solution:**

```bash
# Make sure you're using uv to run tests
uv run pytest tests/ -v

# NOT just pytest
# (which might use different environment)
```

---

## 📋 Quick Reference

### Common uv commands

```bash
# Create/update virtual environment
uv sync

# Install with all optional dependencies
uv sync --all-extras

# Install with specific extra
uv sync --extra redis

# Add new dependency
uv add package-name

# Add from git
uv add "package @ git+https://github.com/user/repo"

# Enter virtual environment
uv shell

# Run command in environment
uv run pytest tests/

# Update all dependencies
uv lock --upgrade

# Show dependency tree
uv pip show zqnt-utils

# Remove dependency
uv remove package-name

# Export requirements.txt
uv pip compile -o requirements.txt pyproject.toml
```

### Quick test commands

```bash
# All tests
uv run pytest

# Verbose
uv run pytest -v

# With coverage
uv run pytest --cov=edge_sdk

# Specific file
uv run pytest tests/unit/test_adapter.py

# Specific test
uv run pytest tests/unit/test_adapter.py::test_name

# Stop on first failure
uv run pytest -x

# Show print statements
uv run pytest -s

# Parallel execution
uv run pytest -n auto
```

---

## ✅ Recommended Setup Summary

For your use case with `zqnt_utils` .whl releases on GitHub:

**1. Use Git URL for simplicity:**
```toml
dependencies = ["zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main"]
```

**2. Install and run tests:**
```bash
uv sync --all-extras
uv run pytest tests/ -v --cov=edge_sdk
```

**3. For CI/CD, set token:**
```bash
export GITHUB_TOKEN=${{ secrets.GITHUB_TOKEN }}
uv sync
uv run pytest tests/
```

This is the **simplest, most maintainable approach** that works for both local development and CI/CD! 🚀

---

**Best Practice:** Use Option 1 (Git URL) for development simplicity. It's fast, requires minimal configuration, and works seamlessly with `uv`.
