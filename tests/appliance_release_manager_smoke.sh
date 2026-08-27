#!/bin/sh
set -eu

project_dir=/project
release_root=/opt/growasist/releases
initial_release="$release_root/image-test"
candidate_release="$release_root/dev-candidate"
failed_release="$release_root/dev-failed"

install_release() {
    destination=$1
    install -d -m 0755 "$destination"
    cp -a "$project_dir/growasist" "$destination/"
    cp -a "$project_dir/custom_components" "$destination/"
    install -m 0644 "$project_dir/pyproject.toml" "$destination/"
    install -m 0644 "$project_dir/README.md" "$destination/"
    install -m 0644 "$project_dir/LICENSE" "$destination/"
}

groupadd --system growasist
useradd --system --gid growasist --home-dir /var/lib/growasist \
    --create-home --shell /usr/sbin/nologin growasist
install -d -m 0755 /usr/local/libexec /usr/local/bin "$release_root"
install -d -m 0750 -o growasist -g growasist \
    /var/lib/growasist /var/backups/growasist
ln -s /usr/local/bin/python3 /usr/bin/python3
ln -s /bin/true /usr/local/bin/systemctl
ln -s /bin/true /usr/local/bin/curl
install -m 0755 "$project_dir/image/assets/growasist-backup" \
    /usr/local/libexec/growasist-backup
install -m 0755 "$project_dir/image/assets/growasist-release-manager" \
    /usr/local/libexec/growasist-release-manager

install_release "$initial_release"
install_release "$candidate_release"
install_release "$failed_release"
ln -s "$initial_release" /opt/growasist/current

runuser -u growasist -- env PYTHONPATH=/opt/growasist/current \
    /usr/bin/python3 -m growasist --data-dir /var/lib/growasist check >/dev/null

/usr/local/libexec/growasist-release-manager deploy "$candidate_release"
test "$(readlink -f /opt/growasist/current)" = "$candidate_release"
test "$(readlink -f /opt/growasist/previous)" = "$initial_release"
test "$(find /var/backups/growasist -type f -name 'growasist-*.db' | wc -l)" -ge 1

/usr/local/libexec/growasist-release-manager rollback
test "$(readlink -f /opt/growasist/current)" = "$initial_release"
test "$(readlink -f /opt/growasist/previous)" = "$candidate_release"

ln -sfn /bin/false /usr/local/bin/curl
if GROWASIST_HEALTH_ATTEMPTS=1 \
    /usr/local/libexec/growasist-release-manager deploy "$failed_release"; then
    echo "Expected failed health check" >&2
    exit 1
fi
test "$(readlink -f /opt/growasist/current)" = "$initial_release"

echo "release-manager smoke: OK"
