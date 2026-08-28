# GrowAsist standalone architecture

## Product boundary

GrowAsist Core is the primary product. It runs on Raspberry Pi OS or another
Linux host and owns cultivation identity, plant profiles, the append-only
journal, device assignments, sensor history, deterministic safety rules, and
the read-only Grow Assistant context.

Home Assistant becomes an optional adapter. It may supply entities or receive
GrowAsist state, but GrowAsist Core must start, preserve its journal, and expose
its local API without Home Assistant being installed or reachable.

## Initial runtime

The standalone product intentionally contains no equipment command API yet. It
provides:

- a Python service with no Home Assistant runtime dependency;
- an authenticated local web panel and versioned mutation/read API;
- cultivation start, stage transition, finish, custom-species, system setup,
  and append-only journal application services;
- SQLite WAL storage with `synchronous=FULL`;
- immutable journal-event rows enforced by SQLite triggers;
- immutable full-state revisions for recovery;
- checksummed Home Assistant journal import and compatible export;
- a consistent online SQLite backup command;
- a Raspberry Pi-compatible Docker image and Compose service;
- a flashable Raspberry Pi 5 appliance image based on Raspberry Pi OS Lite
  64-bit / Debian 13 Trixie, with a hardened systemd service and backup timer.

The existing custom integration remains operational while the standalone UI
and device adapters are built. Both use journal schema 6, so migration does not
discard cultivation records or events.

## Runtime layout

```text
Browser (Overview / Journal / Library / System)
  │
  ▼
GrowAsist local API and web panel
  ├── cultivation/profile service
  ├── append-only journal store
  ├── sensor history service
  ├── deterministic rules and safety engine (disabled initially)
  └── device registry
       ├── Shelly local RPC/mDNS adapter
       ├── Tuya local adapter (qualified per model)
       ├── TP-Link/Tapo local adapter
       ├── MQTT adapter
       ├── Bluetooth adapter
       ├── Atlas EZO/PCA9685 I²C gateway
       └── optional Home Assistant adapter
```

Discovery and control remain separate. mDNS, SSDP, UDP broadcasts, Bluetooth
advertisements, and address scans can identify candidates. A device is not
controllable until an adapter authenticates it, reads its capabilities, and the
user assigns those capabilities to a grow-system role.

## Storage guarantees

The database is stored outside the container at `/data/growasist.db`. Every
state save and every newly observed journal event are committed in one
transaction. A journal event ID cannot be updated or deleted. Saving a stale
state merges missing historical events back in rather than removing them.

Full state revisions are append-only. They protect against application-level
replacement and allow recovery if the current-state row fails checksum
validation. They do not protect against loss of the storage device, so scheduled
off-device backups remain mandatory.

## Application release model

The base image and application lifecycle are independent. The image installs an
initial release under `/opt/growasist/releases`; an atomic `current` symlink
selects what systemd runs. Development and product updates install a sibling
release without changing `/var/lib/growasist`.

Before activation, the release manager creates an online SQLite backup and runs
the candidate against a disposable copy of the live journal. It then restarts
the service and requires the local health endpoint to succeed. Failure switches
the symlink back automatically. The previous successful release remains
available for an explicit rollback.

## Delivery order

1. Standalone core, durable storage, HA export import, health API. **Complete.**
2. Standalone web shell, authentication, setup flow, cultivation and journal UI.
   **Usable first slice complete.**
3. Device registry plus read-only Shelly/Tapo identity discovery and explicit
   candidate enrolment. **Discovery and enrolment complete; monitoring pending.**
4. Atlas EZO/PCA9685 hardware gateway and sensor history.
5. Qualified Shelly, Tapo, and Tuya-local telemetry/control adapters; optional
   Home Assistant adapter for remaining vendor integrations.
6. Read-only Grow Assistant provider abstraction.
7. Deterministic automation with interlocks, watchdogs, audit events, manual
   override, and fail-safe states.

AI is never an actuator authority. It may summarize and recommend; only the
deterministic safety engine may request device commands.
