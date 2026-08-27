# GrowAsist Raspberry Pi image

This directory builds a flashable Raspberry Pi 5 appliance image with the
official `rpi-image-gen` tool. The image is based on Raspberry Pi OS Lite
64-bit / Debian 13 (Trixie) and runs GrowAsist directly under systemd. Home
Assistant and Docker are not required on the target device.

## Included

- native GrowAsist web/API service on standard HTTP port 80;
- SQLite WAL data under `/var/lib/growasist`;
- a unique 256-bit API token generated on first boot;
- SSH public-key-only access for `growasist-admin`;
- I2C bus 1 enabled and bounded `/dev/i2c-1` service access;
- daily consistent database backups retained for 30 days;
- root filesystem expansion on first boot;
- mDNS discovery at `http://growasist.local`.

The current appliance preset uses the `Europe/Istanbul` timezone and Turkey
Wi-Fi regulatory domain. Public release builds will expose these as build or
first-boot choices.

Automatic device control remains disabled.

## Build on macOS or Linux with Docker

Docker Desktop on Apple Silicon builds the image in an ARM64 Linux filesystem,
so macOS filesystem semantics cannot corrupt the Debian root filesystem being
assembled. The builder is pinned to `rpi-image-gen` v2.6.0.

```sh
GROWASIST_SSH_PUBLIC_KEY_FILE="$HOME/.ssh/id_ed25519.pub" \
./image/build-image-docker.sh
```

The first build downloads and caches the builder toolchain. Later builds reuse
that builder image.

## Build natively

Use an up-to-date 64-bit Raspberry Pi OS Bookworm or Trixie host. Keep the
HAOS boot medium untouched and use a separate build host/media.

```sh
git clone --branch v2.6.0 https://github.com/raspberrypi/rpi-image-gen.git
cd rpi-image-gen
sudo ./install_deps.sh
cd /path/to/GrowAsist
RPI_IMAGE_GEN_DIR=/path/to/rpi-image-gen \
GROWASIST_SSH_PUBLIC_KEY_FILE="$HOME/.ssh/id_ed25519.pub" \
./image/build-image.sh
```

The compressed image and checksums are written under `dist/image/`. Flash the
image with Raspberry Pi Imager using **Use Custom**. Prefer a separate USB SSD,
NVMe drive, or microSD card for the first cutover test.

## First boot

Connect Ethernet before booting. Then:

```sh
ssh growasist-admin@growasist.local
sudo growasistctl token
sudo growasistctl check
```

Open `http://growasist.local` and enter the printed token. Useful commands
are `sudo growasistctl status`, `backup`, `logs`, `restart`, and
`import-ha /path/to/journal.json`.

Routine application development does not require another image build. From the
development checkout, run:

```sh
GROWASIST_SSH_IDENTITY_FILE="$HOME/.ssh/id_ed25519" \
./scripts/deploy-dev.sh growasist-admin@growasist.local
```

Each deployment is installed beside the current release. Activation happens
only after a backup and a preflight check against a copy of the live journal;
failed service health automatically restores the previous release. Manual
recovery is available with `sudo growasistctl rollback`.

The daily backups are on the same physical disk. Configure an off-device backup
before treating the appliance as the only copy of a cultivation journal.
