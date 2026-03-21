#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Activate venv if it exists
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
fi

# Check for .env
if [ ! -f .env ]; then
    echo ""
    echo "  No .env found. Run setup first:"
    echo "    ./setup.sh"
    echo ""
    exit 1
fi

# Add src to Python path
export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:$PYTHONPATH}"

exec python3 -m cmas "$@"
