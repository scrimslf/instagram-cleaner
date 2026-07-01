#!/usr/bin/env bash
# setup.sh - one-time install on macOS / Linux.
# Run:  bash setup.sh
set -e

echo "== Instagram non-follower cleaner - setup =="

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Install it from https://www.python.org/downloads/"
  exit 1
fi
python3 --version

if [ ! -d ".venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv .venv
fi

echo "Installing dependencies..."
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

echo ""
echo "Setup complete!"
echo "Next: run a dry-run (nothing gets removed):"
echo "  ./.venv/bin/python clean_followers.py"
