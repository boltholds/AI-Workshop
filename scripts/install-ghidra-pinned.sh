#!/usr/bin/env bash
set -Eeuo pipefail

# Pin the official binary release and verify its published SHA-256.
RELEASE='Ghidra_12.1.4_build'
ARCHIVE='ghidra_12.1.4_PUBLIC_20260921.zip'
SHA256='ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db'
URL="https://github.com/NationalSecurityAgency/ghidra/releases/download/$RELEASE/$ARCHIVE"
BASE="${AI_WORKSHOP_GHIDRA_BASE:-/opt/ai-workshop}"
VERSION_DIR="$BASE/ghidra_12.1.4_PUBLIC"
ACTIVE="$BASE/ghidra"

if (( EUID != 0 )); then
  echo 'Run this installer as root.' >&2
  exit 1
fi
for command in curl unzip sha256sum mktemp; do
  command -v "$command" >/dev/null || { echo "Missing utility: $command" >&2; exit 1; }
done
[[ -d "$BASE" ]] || { echo "Missing installation directory: $BASE" >&2; exit 1; }

if [[ -e "$ACTIVE" || -L "$ACTIVE" ]]; then
  if [[ -x "$ACTIVE/support/analyzeHeadless" ]]; then
    echo "Existing Ghidra installation preserved: $ACTIVE"
    exit 0
  fi
  echo "Refusing to overwrite an existing non-working Ghidra path: $ACTIVE" >&2
  exit 1
fi

if [[ -d "$VERSION_DIR" ]]; then
  [[ -x "$VERSION_DIR/support/analyzeHeadless" ]] || {
    echo "Refusing to overwrite incomplete installation: $VERSION_DIR" >&2
    exit 1
  }
  ln -s "$(basename "$VERSION_DIR")" "$ACTIVE"
  echo "Activated existing verified Ghidra directory: $ACTIVE"
  exit 0
fi

free_kb="$(df -Pk "$BASE" | awk 'NR == 2 { print $4 }')"
if [[ ! "$free_kb" =~ ^[0-9]+$ ]] || (( free_kb < 2400000 )); then
  echo 'At least 2.4 GB free space is required for installation.' >&2
  exit 1
fi

STAGING="$(mktemp -d "$BASE/.ghidra-install.XXXXXXXX")"
cleanup() { rm -rf -- "$STAGING"; }
trap cleanup EXIT

echo "Downloading verified official Ghidra 12.1.4 release..."
curl --proto '=https' --tlsv1.2 --fail --location --retry 3 \
  --output "$STAGING/$ARCHIVE" "$URL"
printf '%s  %s\n' "$SHA256" "$STAGING/$ARCHIVE" | sha256sum --check --status || {
  echo 'Ghidra SHA-256 mismatch. Aborting without installation.' >&2
  exit 1
}

unzip -q "$STAGING/$ARCHIVE" -d "$STAGING"
EXTRACTED="$STAGING/ghidra_12.1.4_PUBLIC"
[[ -x "$EXTRACTED/support/analyzeHeadless" ]] || {
  echo "Release does not contain executable support/analyzeHeadless." >&2
  exit 1
}
mv -- "$EXTRACTED" "$VERSION_DIR"
ln -s "$(basename "$VERSION_DIR")" "$ACTIVE"
echo "Ghidra installed at $ACTIVE (SHA-256 verified)."
