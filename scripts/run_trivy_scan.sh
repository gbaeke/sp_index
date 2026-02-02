#!/usr/bin/env bash
set -euo pipefail

# Helper to ensure trivy is available for filesystem scans.
install_trivy() {
  local os_raw arch_raw os_name arch_name download_url tmp_dir trivy_root trivy_binary
  os_raw=$(uname -s)
  case "$os_raw" in
    Linux) os_name=Linux ;;
    Darwin) os_name=macOS ;;
    *)
      echo "Unsupported OS: $os_raw" >&2
      exit 1
      ;;
  esac
  arch_raw=$(uname -m)
  case "$arch_raw" in
    x86_64|amd64) arch_name=64bit ;;
    arm64|aarch64) arch_name=ARM64 ;;
    *)
      echo "Unsupported architecture: $arch_raw" >&2
      exit 1
      ;;
  esac

  download_url=$(python - "$os_name" "$arch_name" <<'PY'
import json
import sys
import urllib.request

if len(sys.argv) < 3:
    raise SystemExit("missing os/arch arguments")
os_name, arch_name = sys.argv[1], sys.argv[2]
with urllib.request.urlopen('https://api.github.com/repos/aquasecurity/trivy/releases/latest') as resp:
    release = json.load(resp)
for asset in release.get('assets', []):
    name = asset.get('name', '')
    if name.endswith(f"_{os_name}-{arch_name}.tar.gz"):
        print(asset['browser_download_url'])
        break
else:
    raise SystemExit(f"no release for {os_name}-{arch_name}")
PY
  )
  if [[ -z "$download_url" ]]; then
    echo "unable to determine trivy download url" >&2
    exit 1
  fi

  tmp_dir=$(mktemp -d)
  trap 'rm -rf "$tmp_dir"' EXIT
  curl -fsSL "$download_url" -o "$tmp_dir/trivy.tar.gz"
  mkdir -p "$tmp_dir/extracted"
  tar -xzf "$tmp_dir/trivy.tar.gz" -C "$tmp_dir/extracted"

  trivy_binary=$(find "$tmp_dir/extracted" -name trivy -type f -print -quit)
  if [[ -z "$trivy_binary" ]]; then
    echo "unable to locate trivy binary" >&2
    exit 1
  fi

  trivy_root="${XDG_CACHE_HOME:-$HOME/.cache}/trivy/bin"
  mkdir -p "$trivy_root"
  mv "$trivy_binary" "$trivy_root/trivy"
  chmod +x "$trivy_root/trivy"

  trap - EXIT
  echo "$trivy_root/trivy"
}

trivy_bin=$(command -v trivy || true)
if [[ -z "$trivy_bin" ]]; then
  echo "🔧 Trivy CLI missing; downloading latest release"
  trivy_bin=$(install_trivy)
fi

cache_dir=".trivycache"
mkdir -p "$cache_dir"
severity=${TRIVY_SEVERITY:-HIGH,CRITICAL}

echo "🔍 Running trivy filesystem scan (severity=$severity)"
"$trivy_bin" fs --cache-dir "$cache_dir" --severity "$severity" "$@"
