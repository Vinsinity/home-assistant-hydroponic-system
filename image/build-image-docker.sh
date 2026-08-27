#!/usr/bin/env bash
set -euo pipefail

image_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd "$image_dir/.." && pwd)
public_key_file=${GROWASIST_SSH_PUBLIC_KEY_FILE:-"$HOME/.ssh/id_ed25519.pub"}
builder_image=${GROWASIST_IMAGE_BUILDER:-growasist/rpi-image-builder:2.6.0}

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop or Docker Engine is required." >&2
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

docker build \
  --platform linux/arm64 \
  --tag "$builder_image" \
  --file "$image_dir/Dockerfile.builder" \
  "$image_dir"

docker run --rm --privileged \
  --platform linux/arm64 \
  --volume "$project_dir:/project" \
  --volume "$public_key_file:/build-key.pub:ro" \
  "$builder_image" \
  ./rpi-image-gen build \
    -S /project/image \
    -c growasist-pi5.yaml \
    -- \
    IGconf_ssh_pubkey_user1=/build-key.pub \
    "IGconf_artefact_version=$version" \
    "SOURCE_DATE_EPOCH=$source_date_epoch"

echo "Image output: $project_dir/dist/image"
