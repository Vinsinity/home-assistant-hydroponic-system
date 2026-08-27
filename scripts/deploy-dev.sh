#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd "$script_dir/.." && pwd)
remote=${1:-}
ssh_port=${GROWASIST_SSH_PORT:-22}
identity_file=${GROWASIST_SSH_IDENTITY_FILE:-}

if [[ -z "$remote" ]]; then
  echo "Usage: $0 growasist-admin@growasist.local" >&2
  exit 2
fi
for command_name in git python3 rsync ssh; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command is missing: $command_name" >&2
    exit 2
  fi
done
if [[ -n "$identity_file" && ! -f "$identity_file" ]]; then
  echo "SSH identity file does not exist: $identity_file" >&2
  exit 2
fi

if [[ ${GROWASIST_SKIP_TESTS:-0} != 1 ]]; then
  python3 -m pytest -q "$project_dir/tests"
fi

commit=$(git -C "$project_dir" rev-parse --short=12 HEAD)
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
release_id="dev-${timestamp}-${commit}"
remote_staging="/tmp/growasist-${release_id}"
remote_release="/opt/growasist/releases/${release_id}"

ssh_args=(
  -p "$ssh_port"
  -o BatchMode=yes
  -o ConnectTimeout=10
  -o ServerAliveInterval=5
  -o ServerAliveCountMax=3
)
if [[ -n "$identity_file" ]]; then
  ssh_args+=(-i "$identity_file")
fi

printf -v rsync_shell 'ssh'
for argument in "${ssh_args[@]}"; do
  printf -v quoted_argument '%q' "$argument"
  rsync_shell+=" $quoted_argument"
done

ssh "${ssh_args[@]}" "$remote" \
  "install -d -m 0700 '$remote_staging'"

RSYNC_RSH="$rsync_shell" rsync \
  --archive \
  --compress \
  --delete \
  --exclude='__pycache__/' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  "$project_dir/growasist" \
  "$project_dir/custom_components" \
  "$project_dir/pyproject.toml" \
  "$project_dir/README.md" \
  "$project_dir/LICENSE" \
  "$remote:$remote_staging/"

ssh "${ssh_args[@]}" "$remote" \
  "sudo install -d -m 0755 '$remote_release' && sudo rsync -a --delete '$remote_staging/' '$remote_release/' && sudo chmod 0755 '$remote_release' && find '$remote_staging' -mindepth 1 -delete && rmdir '$remote_staging' && sudo growasistctl deploy-release '$remote_release'"

echo "Deployed $release_id to $remote"
echo "Rollback: ssh -p $ssh_port $remote 'sudo growasistctl rollback'"
