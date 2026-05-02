#!/bin/bash
# Final verification script for Edge Python SDK cleanup and setup

set -e

echo "🔍 EDGE PYTHON SDK - FINAL VERIFICATION"
echo "========================================"
echo ""

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✅${NC} File exists: $1"
        return 0
    else
        echo -e "${RED}❌${NC} File missing: $1"
        return 1
    fi
}

check_no_file() {
    if [ ! -f "$1" ]; then
        echo -e "${GREEN}✅${NC} File removed: $1"
        return 0
    else
        echo -e "${RED}❌${NC} File still exists: $1"
        return 1
    fi
}

check_directory() {
    if [ -d "$1" ]; then
        echo -e "${GREEN}✅${NC} Directory exists: $1"
        return 0
    else
        echo -e "${RED}❌${NC} Directory missing: $1"
        return 1
    fi
}

check_content() {
    if grep -q "$2" "$1"; then
        echo -e "${GREEN}✅${NC} Content found in $1: '$2'"
        return 0
    else
        echo -e "${RED}❌${NC} Content NOT found in $1: '$2'"
        return 1
    fi
}

# Run checks
echo "📝 Documentation Files:"
check_file "README.md"
check_file "DEVELOPMENT.md"
check_file "PROJECT_SUMMARY.md"
check_file "CLEANUP_CHECKLIST.md"
echo ""

echo "📋 Configuration Files:"
check_file "pyproject.toml"
check_file ".gitignore"
check_file ".gitattributes"
echo ""

echo "🔄 GitHub Workflows:"
check_file ".github/workflows/pr.yml"
check_file ".github/workflows/main.yml"
echo ""

echo "🧹 Code Cleanup:"
check_no_file "main.py"
echo ""

echo "📦 Project Structure:"
check_directory "edge_sdk"
check_directory "tests"
check_directory "zqnt-protos"
check_directory "scripts"
echo ""

echo "⚙️ Dependencies:"
check_content "pyproject.toml" "zqnt-utils>=1.0.0"
check_content "pyproject.toml" "ruff>=0.15.12"
echo ""

echo "🎯 Workflow Configuration:"
check_content ".github/workflows/pr.yml" "pull_request"
check_content ".github/workflows/main.yml" "push"
check_content ".github/workflows/pr.yml" "ruff check"
check_content ".github/workflows/main.yml" "GitHub Release"
echo ""

echo "========================================"
echo "✨ VERIFICATION COMPLETE ✨"
echo ""
echo "The Edge Python SDK is ready for:"
echo "  ✅ Development (DEVELOPMENT.md)"
echo "  ✅ Usage (README.md)"
echo "  ✅ Continuous Integration (GitHub Workflows)"
echo "  ✅ Automated Releases"
echo ""
echo "📚 Documentation:"
echo "  • README.md - User guide and installation"
echo "  • DEVELOPMENT.md - Developer setup and contribution"
echo "  • PROJECT_SUMMARY.md - Project status and workflows"
echo "  • CLEANUP_CHECKLIST.md - Verification checklist"
echo ""
echo "🚀 Next Steps:"
echo "  1. Review the documentation files"
echo "  2. Commit and push the changes"
echo "  3. Update version in pyproject.toml when ready to release"
echo "  4. GitHub Actions will handle the rest automatically"
echo ""
