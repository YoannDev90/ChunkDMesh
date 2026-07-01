#!/usr/bin/env bash
# Build mcmap binary for the current host architecture.
# Usage: ./scripts/build_mcmap.sh [--release]
#
# For multi-arch builds, use the CI workflow (build-mcmap.yml).

set -euo pipefail

export PATH="$HOME/.cargo/bin:$PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
RUST_DIR="$PROJECT_DIR/tiler"
OUTPUT_DIR="$PROJECT_DIR/bin"
MODE="${1:---release}"

mkdir -p "$OUTPUT_DIR"

echo "=== mcmap build (host) ==="
cargo build $MODE --manifest-path "$RUST_DIR/Cargo.toml" 2>&1 | tail -3

binary_path="$RUST_DIR/target/release/mcmap"
if [ -f "$binary_path" ]; then
    cp "$binary_path" "$OUTPUT_DIR/mcmap"
    chmod +x "$OUTPUT_DIR/mcmap"
    size=$(stat -c%s "$OUTPUT_DIR/mcmap" 2>/dev/null || stat -f%z "$OUTPUT_DIR/mcmap" 2>/dev/null || echo "?")
    echo "✓ $OUTPUT_DIR/mcmap ($size bytes)"
else
    echo "✗ build failed"
    exit 1
fi
