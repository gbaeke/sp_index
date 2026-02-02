#!/usr/bin/env bash
set -euo pipefail

# Safety CLI scan wrapper for this repository.
# Assumes you've already run `safety auth login` or otherwise authenticated.
echo "🔍 Running safety scan"
uv run safety scan --file=uv.lock --full-report
