#!/usr/bin/env bash
# Install dragon-tui from the built dist directory.
# Usage: ./install.sh [prefix]
#   Default prefix: /usr/local (needs sudo) or ~/.local

set -euo pipefail

PREFIX="${1:-$HOME/.local}"
BIN_DIR="$PREFIX/bin"
LIB_DIR="$PREFIX/lib/dragon-tui"

echo "dragon-tui installer"
echo "  prefix: $PREFIX"

# Create directories
mkdir -p "$BIN_DIR"
rm -rf "$LIB_DIR"
mkdir -p "$LIB_DIR"

# Copy the onedir build
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cp -R "$SCRIPT_DIR/dist/DeepSeekTUI/"* "$LIB_DIR/"

# Create wrapper script
cat > "$BIN_DIR/dragon-tui" << 'WRAPPER'
#!/usr/bin/env bash
exec "$(dirname "$(readlink -f "$0")")/../lib/dragon-tui/dragon-tui" "$@"
WRAPPER
chmod +x "$BIN_DIR/dragon-tui"

echo "  binary: $BIN_DIR/dragon-tui"
echo "  lib:    $LIB_DIR"

# Add to PATH if needed
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    echo ""
    echo "Add to your shell config:"
    echo "  export PATH=\"$BIN_DIR:\$PATH\""
fi

echo ""
echo "✅ Installation complete. Run: dragon-tui"
