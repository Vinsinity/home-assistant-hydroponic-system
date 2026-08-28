# Changelog

## Unreleased

- Start the Home Assistant-independent GrowAsist Core for Raspberry Pi OS.
- Add a read-only versioned HTTP service and Raspberry Pi-compatible container.
- Add SQLite WAL persistence with full synchronous commits, immutable journal
  event rows, immutable state revisions, checksum validation, and online backup.
- Add checksummed Home Assistant journal import that merges historical records
  and events instead of replacing them.
- Add an authenticated, responsive standalone web panel with focused Overview,
  Journal, Library, and System workspaces and no Home Assistant frontend components.
- Replace duplicated Setup navigation with one ownership-based hierarchy:
  cultivation work, reusable Library records, and physical System setup.
  Preserve stable `#setup/...` routes, with a compact module switcher only on
  mobile where the full sidebar is unavailable.
- Remove user-owned product IDs from the Plant Library editor. Plant profiles
  now own crop-specific stage targets only, while nutrients remain independent
  catalogue/inventory records selected separately for one cultivation.
- Add a versioned SQLite manufacturer nutrient catalogue with 367 products from
  20 major brands. The Nutrients workspace now supports brand/product search,
  product details with official source links, and idempotent one-click copying
  into the user's own product list while preserving custom products.
- Add 79 catalogue-derived nutrient product-set mappings, including explicit
  medium/water variants for manufacturer lines where products are alternatives.
  Filter choices by hydroponic, coco, or soil setup without treating a product
  set as a grow profile or dose chart.
- Give Profiles its own route and keep Nutrients limited to the manufacturer
  product catalogue and the user's owned products. Legacy nutrient IDs are
  removed from plant stages during normalization.
- Connect grow start to independent profile and nutrient choices. Snapshot the
  selected catalogue version, product identities, and per-stage product mapping
  into that cultivation without mutating the reusable profile or owned inventory.
- Move Dosing out of System setup and into top-level cultivation navigation;
  keep physical pump mapping, bounded tests, calibration, and safety limits
  together without enabling automatic control.
- Reduce the visible grow-start and setup fields to the decisions needed now;
  keep product selection, physical measurements, device connection values,
  pump calibration, and safety limits in clearly labelled optional sections.
- Let Area & Light select an explicitly enrolled light switch or dimmer instead
  of treating free-text fixture details as the device connection.
- Replace development-facing UI copy about the runtime, database, and migration
  status with short product language; keep those diagnostics in service checks.
- Add bounded, read-only LAN discovery for Shelly mDNS/RPC, TP-Link/Tapo UDP,
  Tuya candidates, and SSDP; require an explicit name and grow-system role
  before moving any candidate into the persistent device registry.
- Replace manually typed I2C address/driver records with Raspberry Pi bus
  discovery, verified Atlas identities, explicit PCA9685 board confirmation,
  removable assignments with retained recovery snapshots, and honest online,
  credential-required, and adapter-pending device states.
- Add dependency-free Linux `/dev/i2c-N` access, persistent `i2c-dev` module
  loading, and a two-step physical pump calibration that can only save ml/s
  after a confirmed bounded motor run. Serialize all motor actions and always
  stop the selected channel when the run ends or fails.
- Include profiles, hardware, dosing fluids, safety policy, and Assistant
  settings in checksummed exports so moving away from Home Assistant does not
  hide or discard the system configuration.
- Add standalone application services and API routes for starting/finishing a
  cultivation, stage transitions, custom plants, physical setup, and immutable
  journal events.
- Snapshot the selected Plant Library profile, Cannabis genetics, method,
  growing medium, fixture context, and nutrient-program name at grow start.
- Let grow start select a compatible manufacturer program instead of manually
  checking user-specific products, then snapshot complete product identities
  and the program stage map into the immutable cultivation record.
- Validate the complete browser flow on desktop and mobile while keeping all
  automatic equipment control disabled.
- Add a reproducible Raspberry Pi 5 appliance image based on Raspberry Pi OS
  Lite 64-bit / Debian 13 Trixie, with systemd startup, SSH key-only access,
  I2C bus access, first-boot token generation, mDNS, and daily SQLite backups.
- Separate application releases from the base image with atomic activation,
  live-journal-copy preflight checks, health-gated rollback, and a one-command
  Mac-to-Raspberry Pi development deployment flow.
- Serve the Raspberry Pi appliance on standard HTTP port 80 without running as
  root, start reliably after first-boot setup has already completed, and keep
  development release directories traversable by the unprivileged service user.
- Keep the automatic control engine disabled while standalone device adapters
  and deterministic safety rules are built.

## 0.32.0

- Replace the Cabin name/location form with only grow-area dimensions and plant capacity.
- Replace the misleading Water System card with cultivation method and growing-medium selection.
- Show reservoir and solution volumes only for methods that actually use a reservoir.
- Carry the selected growing medium into cultivation identity, immutable system snapshots, Overview, the grow-start review, and read-only Assistant context.
- Migrate system profiles to schema 2 and the append-only journal to schema 6 without deleting legacy fields, cultivations, or events.

## 0.31.0

- Move Connections, Plant Library, profiles, nutrients, hardware, and dosing into dedicated nested routes beneath Setup while keeping the daily navigation compact.
- Replace the sparse cultivation dialog with a four-step start flow covering plant/genetics, editable example targets and initial stage, nutrient program/products, cabin/water/light context, and final review.
- Snapshot the chosen nutrient products and program into the cultivation and immutable start event without issuing any dose or equipment command.
- Preserve only the selected cultivar in each cultivation snapshot so the 249-record Cannabis catalog cannot exceed journal record limits; the complete editable catalog remains in Plant Library storage.
- Migrate the append-only journal to schema 5 without replacing existing cultivations or events.

## 0.30.0

- Move the built-in Cannabis offerings into a separate, versioned catalog snapshot instead of embedding a short list in Python code.
- Expand the library to 249 breeder-specific offerings: 143 Photoperiod and 106 Autoflower records across five official catalog sources.
- Preserve existing edits during Plant Library schema 3 migration while adding newly shipped built-in records by stable ID.
- Add catalog version, total strain count, source counts, and Photoperiod/Autoflower totals to the Plant Library.
- Add strain text search plus growth-type and breeder filters, with a bounded 60-row editing window for a responsive dialog.
- Simplify new cultivation genetics to one searchable strain field that also accepts a custom name.
- Keep selected genetics snapshotted into the cultivation and append-only journal so future catalog changes cannot rewrite history.

## 0.29.0

- Separate Cannabis growth type, breeder/seed bank, cultivar identity, and purchase source in the persistent data model.
- Add Photoperiod and Autoflower as structured growth types rather than cultivar suggestions.
- Add an editable breeder/seed-bank library with Royal Queen Seeds, Barney's Farm, Amnesia Seeds, Dutch Passion, Sensi Seeds, and Fast Buds.
- Add initial breeder-specific strain records from official catalogs, including Northern Light(s), Purple Haze, Amnesia Haze, and autoflower variants.
- Add cascading growth-type, breeder, and strain selection to the three-step cultivation wizard while retaining a custom-strain path.
- Add breeder and strain editing to the Plant Library without exposing delete operations for built-in records.
- Snapshot selected genetics and breeder data into the cultivation record and append-only cultivation-start event.
- Migrate the append-only journal to schema 4 and the Plant Library to schema 2 without replacing existing cultivations or events.

## 0.28.0

- Add a versioned, persistent Plant Library with Tomato, Lettuce, Cannabis, Basil, Strawberry, Pepper, and Cucumber.
- Add editable per-species stage targets for schedule, photoperiod, light, environment, pH, EC, water temperature, and dissolved oxygen.
- Mark every built-in profile as an editable starting example and retain its reference URLs in storage.
- Add custom plant creation; starting an unlisted species automatically creates a reusable custom library record.
- Replace free-text-only plant selection with a library picker and cultivar suggestions in the grow wizard.
- Build each new cultivation calendar from the selected species profile and omit disabled stages.
- Snapshot the full selected plant profile into the cultivation and immutable start event.
- Feed the snapshotted plant and active-stage profile to the read-only Grow Assistant.
- Include the Plant Library in checksummed JSON exports and the Setup hub.
- Migrate the append-only journal to schema 3 without replacing existing cultivations or events.

## 0.27.0

- Add a reusable, validated cabin, water-system, and lighting profile.
- Snapshot the physical system profile into each new cultivation and its start event.
- Replace the long cultivation form with a three-step plant/start/review wizard.
- Add an active-grow workspace with light schedule, recent journal, and quick journal actions.
- Add a read-only Grow Assistant using Home Assistant AI Task providers without LLM control tools.
- Add 24-hour/7-day sensor summaries, optional camera context, language/detail preferences, and optional notifications.
- Store every Assistant report as an immutable `ai_recommendation` journal event.
- Simplify the primary navigation and compact unconfigured sensor/security empty states.
- Add normalization, migration, prompt-safety, system-snapshot, and storage durability tests.

## 0.25.0

- Add permanent, ID-based cultivation history instead of replacing the previous cultivation.
- Add a versioned append-only event journal and lossless migration of legacy journal fields.
- Mirror cultivations and events to a checksummed Home Assistant recovery storage document.
- Add checksummed JSON journal export from the panel.
- Add cultivation identity fields and a complete start form.
- Add daily note, water, nutrient, pH, volume, calibration, maintenance, and photo URL events.
- Add idempotency IDs to cultivation start, finish, and journal event requests.
- Remove the synthetic 1 ml/s pump calibration; only measured, timestamped calibration is accepted as ready.
