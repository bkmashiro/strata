#!/usr/bin/env bash
# Strata Demo - Environment Archaeology Tool
# This script demonstrates the core workflow.

set -e

DEMO_DB="/tmp/strata-demo-$$.db"
DEMO_DIR=$(mktemp -d)
trap 'rm -rf "$DEMO_DIR" "$DEMO_DB"' EXIT

echo "============================================="
echo "  Strata Demo - Environment Archaeology Tool"
echo "============================================="
echo ""

# Install if needed
if ! command -v strata &>/dev/null; then
    echo "[*] Installing strata..."
    pip install -e "$(dirname "$0")/.." --quiet
fi

echo "[1/6] Taking a baseline snapshot..."
echo "  \$ strata --db $DEMO_DB snap -l baseline --root $DEMO_DIR"
strata --db "$DEMO_DB" snap -l "baseline" --root "$DEMO_DIR"
echo ""

echo "[2/6] Simulating environment changes..."

# Create some config files
echo '{"database": "postgres://localhost:5432/app"}' > "$DEMO_DIR/config.json"
echo 'port: 8080' > "$DEMO_DIR/app.yaml"

# Set a new env var
export STRATA_DEMO_VAR="hello-world"

echo "  - Created config.json and app.yaml"
echo "  - Set STRATA_DEMO_VAR=hello-world"
echo ""

echo "[3/6] Taking a second snapshot..."
echo "  \$ strata --db $DEMO_DB snap -l after-changes --root $DEMO_DIR"
strata --db "$DEMO_DB" snap -l "after-changes" --root "$DEMO_DIR"
echo ""

echo "[4/6] Listing all snapshots..."
echo "  \$ strata --db $DEMO_DB ls"
strata --db "$DEMO_DB" ls
echo ""

echo "[5/6] Diffing the two snapshots..."
echo "  \$ strata --db $DEMO_DB diff baseline after-changes"
strata --db "$DEMO_DB" diff "baseline" "after-changes"
echo ""

echo "[6/6] Searching for our new env var..."
echo "  \$ strata --db $DEMO_DB search envvars STRATA_DEMO"
strata --db "$DEMO_DB" search envvars "STRATA_DEMO"
echo ""

echo "[*] Checking status..."
echo "  \$ strata --db $DEMO_DB status"
strata --db "$DEMO_DB" status
echo ""

# Clean up env
unset STRATA_DEMO_VAR

echo "============================================="
echo "  Demo complete!"
echo "============================================="
