#!/bin/sh
# Emerager0DB installer for Linux and macOS.
#   curl -fsSL https://falks.cyou/get | sh
#
# Environment overrides (optional):
#   EMERAGER0DB_API_URL      release manifest URL
#   EMERAGER0DB_INSTALL_DIR  where the binary is installed (default ~/.local/bin)
#   EMERAGER0DB_HOME         data directory (default ~/.emerager0db)
set -eu

API_URL="${EMERAGER0DB_API_URL:-https://falks.cyou/api/version}"
INSTALL_DIR="${EMERAGER0DB_INSTALL_DIR:-$HOME/.local/bin}"
DATA_DIR="${EMERAGER0DB_HOME:-$HOME/.emerager0db}"

say() { printf '%s\n' "$*"; }
die() { printf 'Error: %s\n' "$*" >&2; exit 1; }
need() { command -v "$1" >/dev/null 2>&1 || die "'$1' is required but was not found"; }

need curl
need awk

case "$(uname -s)" in
  Linux) OS=linux ;;
  Darwin) OS=macos ;;
  *) die "unsupported operating system: $(uname -s)" ;;
esac

case "$(uname -m)" in
  x86_64|amd64) ARCH=x86_64 ;;
  arm64|aarch64) ARCH=arm64 ;;
  *) die "unsupported CPU architecture: $(uname -m)" ;;
esac

KEY="$OS-$ARCH"
say "Detected $KEY"

MANIFEST="$(curl -fsSL "$API_URL")" || die "could not reach $API_URL"
# The manifest is small JSON. Flatten it and pull out one string value by key.
FLAT="$(printf '%s' "$MANIFEST" | tr -d ' \n\r\t')"
value_for() { printf '%s' "$FLAT" | sed -n "s/.*\"$1\":\"\([^\"]*\)\".*/\1/p"; }

BIN_URL="$(value_for "$KEY")"
SUMS_URL="$(value_for checksums)"
[ -n "$BIN_URL" ] || die "no release is published for $KEY yet"
[ -n "$SUMS_URL" ] || die "the release manifest has no checksum file"

ASSET="Emerager0DB-$KEY"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

say "Downloading Emerager0DB..."
curl -fsSL -o "$TMP/$ASSET" "$BIN_URL" || die "download failed"
curl -fsSL -o "$TMP/SHA256SUMS" "$SUMS_URL" || die "could not download the checksum file"

EXPECTED="$(awk -v f="$ASSET" '$2 == f || $2 == "*" f { print $1 }' "$TMP/SHA256SUMS")"
[ -n "$EXPECTED" ] || die "no checksum is listed for $ASSET. Installation aborted."

if command -v sha256sum >/dev/null 2>&1; then
  ACTUAL="$(sha256sum "$TMP/$ASSET" | awk '{ print $1 }')"
else
  ACTUAL="$(shasum -a 256 "$TMP/$ASSET" | awk '{ print $1 }')"
fi
[ "$ACTUAL" = "$EXPECTED" ] || die "checksum mismatch. The download was discarded and nothing was installed."
say "Checksum verified."

mkdir -p "$INSTALL_DIR" "$DATA_DIR"
chmod 0755 "$TMP/$ASSET"
mv -f "$TMP/$ASSET" "$INSTALL_DIR/Emerager0DB"
say "Installed to $INSTALL_DIR/Emerager0DB"

case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *)
    case "${SHELL:-}" in
      */zsh) RC="$HOME/.zshrc" ;;
      */bash) RC="$HOME/.bashrc" ;;
      *) RC="$HOME/.profile" ;;
    esac
    printf '\nexport PATH="%s:$PATH"  # added by the Emerager0DB installer\n' "$INSTALL_DIR" >> "$RC"
    say "Added $INSTALL_DIR to PATH in $RC"
    ;;
esac

# Run the setup wizard from the terminal. Under `curl | sh`, stdin is the script, so read /dev/tty.
if [ -r /dev/tty ]; then
  "$INSTALL_DIR/Emerager0DB" setup </dev/tty || die "setup did not complete. Run: Emerager0DB setup"
else
  say "No terminal detected. Run 'Emerager0DB setup' to create the root account."
fi

say ""
say "Completed!"
say ""
say "Restart your shell asap and do:"
say ""
say "    Emerager0DB"
