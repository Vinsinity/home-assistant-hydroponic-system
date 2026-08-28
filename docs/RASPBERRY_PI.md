# Raspberry Pi 5 standalone installation

GrowAsist now has a flashable appliance image. The target Raspberry Pi does
not need Home Assistant, Docker, Python package installation, or a repository
checkout. The image contains Raspberry Pi OS Lite 64-bit / Debian 13 Trixie,
GrowAsist, its systemd services, I2C configuration, and backup timer.

## Safe HAOS cutover

Do not format the HAOS boot medium first. A safe cutover uses a second USB SSD,
NVMe drive, or high-endurance microSD card:

1. Start the old HAOS installation one last time.
2. Download a full Home Assistant backup to another computer.
3. Download the checksummed GrowAsist journal JSON from the existing panel.
4. Confirm both files are non-empty and keep a second copy off the Raspberry Pi.
5. Shut the Raspberry Pi down and physically remove or disconnect the HAOS
   medium. Label it with the date; it is the rollback copy.
6. Flash and test GrowAsist on the second medium.
7. Keep the HAOS medium unchanged until the imported cultivation data, network,
   sensors, and off-device backup have all been verified.

If HAOS is unreachable, stop here and keep its medium intact. An unavailable
source cannot be considered backed up.

## Build the image

On Apple Silicon macOS or ARM64 Linux with Docker:

```sh
GROWASIST_SSH_PUBLIC_KEY_FILE="$HOME/.ssh/id_ed25519.pub" \
./image/build-image-docker.sh
```

For a native Raspberry Pi OS build, follow [`image/README.md`](../image/README.md).
The output used for flashing is:

```text
dist/image/growasist-pi5.img.zst
```

## Flash and first boot

1. Open Raspberry Pi Imager and choose **Use Custom**.
2. Select `growasist-pi5.img.zst` and the new, disposable target medium.
3. Double-check the target name and capacity before writing it.
4. Put the new medium in the Raspberry Pi 5, connect Ethernet, and boot.
5. Wait a few minutes for filesystem expansion and first-boot setup.

The image already contains the SSH public key supplied at build time. Password
login and SSH root login are disabled. Connect with the matching private key:

```sh
ssh growasist-admin@growasist.local
sudo growasistctl token
sudo growasistctl check
```

Open `http://growasist.local` and enter the printed panel token. If mDNS is
not resolved by the client, use the Raspberry Pi address from the router, for
example `http://10.1.1.x`.

To move from Ethernet to Wi-Fi:

```sh
sudo iwctl station wlan0 scan
sudo iwctl station wlan0 get-networks
sudo iwctl station wlan0 connect "YOUR_SSID"
```

The current private appliance preset uses the `Europe/Istanbul` timezone and
Turkey Wi-Fi regulatory domain.

## Daily development without reflashing

The appliance image is only the operating-system bootstrap. Application builds
live under `/opt/growasist/releases`, while `/opt/growasist/current` atomically
selects the active version. Cultivation data remains separately under
`/var/lib/growasist`.

From the Mac repository, deploy a development release with:

```sh
GROWASIST_SSH_IDENTITY_FILE="$HOME/.ssh/id_ed25519" \
./scripts/deploy-dev.sh growasist-admin@growasist.local
```

The command runs the local test suite, synchronizes only application files,
creates a new release directory, takes a consistent database backup, and opens
the new code against a copy of the real journal. Only then does it switch the
active symlink and restart the service. A failed health check restores the old
release automatically.

Useful release commands on the Raspberry Pi:

```sh
sudo growasistctl releases
sudo growasistctl rollback
sudo growasistctl status
```

Set `GROWASIST_SKIP_TESTS=1` only during an intentional diagnostic iteration.
Rebuild the complete image only for operating-system, kernel, boot, base
dependency, or recovery changes.

## Import the HA journal

Copy the exported JSON to the new Raspberry Pi and import it only after the
standalone integrity check succeeds:

```sh
scp hydroponic-journal.json growasist-admin@growasist.local:/tmp/
ssh growasist-admin@growasist.local
sudo growasistctl import-ha /tmp/hydroponic-journal.json
sudo growasistctl check
sudo growasistctl backup
```

Import merges by cultivation and event ID. It does not treat a missing imported
event as a deletion, and conflicting immutable event content is rejected.

## Journal durability

The live database is `/var/lib/growasist/growasist.db`. It uses SQLite WAL with
`synchronous=FULL`, immutable journal-event triggers, and append-only full-state
revisions. A consistent backup runs every day around 03:15 and retains 30 days
under `/var/backups/growasist`.

Those daily files are on the same physical medium and therefore do not protect
against media loss. Before starting a cultivation, copy backups automatically
to a second physical disk or another host. A database can be called durable only
after a restore from that second destination has been tested.

Useful commands:

```sh
sudo growasistctl status
sudo growasistctl check
sudo growasistctl backup
sudo growasistctl releases
sudo growasistctl rollback
sudo growasistctl logs
sudo growasistctl restart
```

## Current hardware boundary

The image enables `/dev/i2c-1` and grants the GrowAsist service only that device.
The standalone product still does not issue automatic commands to lights,
pumps, humidifiers, CO2 valves, or dosing hardware. It loads `i2c-dev` during
boot and uses read-only Atlas identity and PCA9685 register checks to discover
physically attached devices. Candidates enter the registry only after explicit
user enrolment; a PCA9685 response also requires manual board-type confirmation.
The only actuator operation is an explicitly confirmed, bounded pump test or
calibration run. It verifies the controller immediately before the action,
serializes motor access, and stops the channel in a `finally` path. System →
Hardware also provides a read-only LAN scan for Shelly, TP-Link/Tapo, Tuya
candidates, and SSDP devices. Network authentication, telemetry adapters, and
deterministic safety control remain subsequent delivery slices.
