#!/usr/bin/env bash
set -euo pipefail

image_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd "$image_dir/.." && pwd)
image_gen_dir=${RPI_IMAGE_GEN_DIR:-"$project_dir/../rpi-image-gen"}
public_key_file=${GROWASIST_SSH_PUBLIC_KEY_FILE:-"$HOME/.ssh/id_ed25519.pub"}

if [[ $(uname -s) != Linux || $(uname -m) != aarch64 ]]; then
  echo "Build this image on 64-bit Raspberry Pi OS Trixie/Bookworm (Linux arm64)." >&2
  exit 2
fi
if [[ ! -x "$image_gen_dir/rpi-image-gen" ]]; then
  echo "Set RPI_IMAGE_GEN_DIR to an rpi-image-gen v2.6.0 checkout." >&2
  exit 2
fi
if [[ ! -f "$public_key_file" ]]; then
  echo "Set GROWASIST_SSH_PUBLIC_KEY_FILE to your SSH public key." >&2
  exit 2
fi
if ! grep -Eq '^(ssh-(ed25519|rsa)|ecdsa-sha2-)' "$public_key_file"; then
  echo "The SSH public key file is not recognised." >&2
  exit 2
fi

version=$(PYTHONPATH="$project_dir" python3 -c 'from growasist import __version__; print(__version__)')
source_date_epoch=$(git -C "$project_dir" log -1 --format=%ct)

"$image_gen_dir/rpi-image-gen" build \
  -S "$image_dir" \
  -c growasist-pi5.yaml \
  -- \
  "IGconf_ssh_pubkey_user1=$public_key_file" \
  "IGconf_artefact_version=$version" \
  "SOURCE_DATE_EPOCH=$source_date_epoch"

echo "Image output: $project_dir/dist/image"
