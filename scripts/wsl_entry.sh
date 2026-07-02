#!/usr/bin/env bash
# Invoked by build_release.bat inside WSL:
#   bash -c "tr -d '\r' < .../wsl_entry.sh | bash -s -- <version> <safe-version> <repo-wsl-path>"
# Strips CRLF from the real scripts (the repo checkout is CRLF on Windows),
# provisions the distro if needed, then runs the Linux build.
set -euo pipefail

VERSION="${1:?version required}"
SAFE_VERSION="${2:?file-safe version required}"
REPO="${3:?repo root (WSL path) required}"

tr -d '\r' < "$REPO/scripts/wsl_provision.sh" > /tmp/etvr_provision.sh
tr -d '\r' < "$REPO/scripts/build_linux.sh" > /tmp/etvr_build_linux.sh

bash /tmp/etvr_provision.sh
bash /tmp/etvr_build_linux.sh "$VERSION" "$SAFE_VERSION" "$REPO" "$REPO/release/$SAFE_VERSION"
