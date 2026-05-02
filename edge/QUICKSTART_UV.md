# Quick Start with uv

Get started with the Edge Python SDK using `uv` (fast Python package installer and manager).

## ⚡ 5-Minute Setup

### 1. Install uv (if not already installed)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone and setup

```bash
git clone https://github.com/Zequent/zqnt-framework.git
cd sdks/edge/edge-python-sdk

# One-command setup
bash scripts/setup-dev.sh
```

### 3. Run tests

```bash
# Quick test
uv run pytest tests/ -v

# Or use our script
bash scripts/test.sh
```

That's it! 🎉

---

## 🚀 Common Tasks

### Run all tests with coverage

```bash
uv run pytest tests/ -v --cov=edge_sdk --cov-report=html
```

### Lint and format code

```bash
# Check for issues
uv run ruff check .

# Auto-format code
uv run ruff format .

# Check formatting (without changes)
uv run ruff format --check .
```

### Run specific tests

```bash
# Run one file
uv run pytest tests/unit/test_adapter.py -v

# Run one test
uv run pytest tests/unit/test_adapter.py::test_take_off -v

# Run tests matching pattern
uv run pytest tests/ -k "adapter" -v
```

### Full CI checks (what GitHub Actions runs)

```bash
bash scripts/ci.sh
```

### Enter virtual environment shell

```bash
uv shell

# Now you can run commands directly
pytest tests/ -v
ruff check .
```

### Exit virtual environment

```bash
exit
# or just type 'exit'
```

### Add new dependency

```bash
# Add to main dependencies
uv add requests

# Add to dev dependencies
uv add --dev pytest-xdist

# Add from git
uv add "my-package @ git+https://github.com/user/repo"
```

### Update lock file

```bash
uv lock --upgrade
```

---

## 🔧 Installing zqnt_utils

### Option 1: Git URL (Recommended for Development)

Add to `pyproject.toml`:

```toml
[project]
dependencies = [
    "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@main",
]
```

Then install:

```bash
uv sync --all-extras
```

### Option 2: GitHub Token for Private Repos

If the repo is private, set your token:

```bash
export GITHUB_TOKEN="ghp_your_token_here"
uv sync --all-extras
```

Or configure git permanently:

```bash
git config --global credential.helper store
# Then git will ask for your credentials once and cache them
```

### Option 3: Specific Version/Release

```toml
[project]
dependencies = [
    "zqnt-utils @ git+https://github.com/Zequent/zqnt-utils-python@v1.0.0",
]
```

---

## 🐛 Troubleshooting

### "zqnt_utils not found"

**Solution:** Set GitHub token

```bash
export GITHUB_TOKEN="your_token"
uv sync
```

### "Repository not found"

**Solution:** 
- Make sure the repo URL is correct
- Verify the repo is public or you have access
- Check GitHub token permissions

### "Module not found when running tests"

**Solution:** Always use `uv run` for tests

```bash
# ✅ Correct
uv run pytest tests/ -v

# ❌ Wrong (might use wrong environment)
pytest tests/ -v
```

### Clear cache and reinstall

```bash
uv cache purge
uv sync
```

---

## 📚 Learn More

- **UV_SETUP.md** - Detailed guide for private packages
- **DEVELOPMENT.md** - Full development guide
- **README.md** - SDK usage and API reference
- **uv documentation** - https://docs.astral.sh/uv/

---

## ✨ Why uv?

- ⚡ **Fast** - 10-100x faster than pip
- 🔒 **Reliable** - Lock files for reproducible installs
- 🛠️ **Tool management** - Manages Python versions too
- 📦 **Simple** - Just `uv sync` to install everything
- 🚀 **Modern** - Written in Rust, actively maintained

---

**Ready to start? Run:** `bash scripts/setup-dev.sh`
