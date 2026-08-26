# Raspberry Pi standalone development

## First boot target

Use 64-bit Raspberry Pi OS Bookworm on Raspberry Pi 5. Keep the current HAOS
microSD card untouched until the standalone journal has been imported, backed
up, and verified on a separate storage device.

Install Docker Engine and the Compose plugin, clone the repository, then create
the local environment file:

```sh
cp .env.example .env
openssl rand -hex 32
```

Put the generated value in `.env`, then start GrowAsist:

```sh
mkdir -p growasist-data
sudo chown 10001:10001 growasist-data
docker compose up --build -d
docker compose ps
curl http://127.0.0.1:8080/api/v1/health
```

The standalone panel is available at `http://<raspberry-pi-ip>:8080`. Enter the
same token in the sign-in screen; it remains only in that browser tab's session
storage. API endpoints containing cultivation data require `Authorization:
Bearer <token>`.

The panel can start and finish cultivations, append journal events, change the
active stage, and save grow-area/media/light context. It does not send commands
to lights, pumps, humidifiers, or dosing hardware.

The persistent database is stored in `./growasist-data`. Back it up to another
disk or host; merely recreating the container must not remove this directory.

## Importing the existing journal

Download a checksummed JSON journal from the current Hydroponic System panel.
Copy it to the Raspberry Pi and stop write activity during the one-time cutover.
Run:

```sh
docker compose exec growasist growasist import-ha /data/hydroponic-journal.json
docker compose exec growasist growasist check
docker compose exec growasist growasist backup /data/backups/after-import.db
```

Import merges by cultivation and event ID. It never treats an absent event in
the import as a deletion. An event ID whose content changed is rejected.

## Hardware access

The first standalone slice does not operate I²C or network actuators. Later the
hardware-gateway service will receive explicit `/dev/i2c-1` access and the
minimum Linux group permissions. It will not require privileged container mode.
Network discovery requires the service and devices to share a reachable LAN;
the base Compose service therefore uses host networking.
