#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check for venv
if [ ! -f .venv/bin/python3 ]; then
    echo ""
    echo "  No virtual environment found. Run setup first:"
    echo "    ./setup.sh"
    echo ""
    exit 1
fi

# Check for .env
if [ ! -f .env ]; then
    echo ""
    echo "  No .env found. Run setup first:"
    echo "    ./setup.sh"
    echo ""
    exit 1
fi

exec .venv/bin/python3 -m cmas "$@"
