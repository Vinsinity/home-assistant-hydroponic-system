# Changelog

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
