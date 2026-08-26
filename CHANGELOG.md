# Changelog

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
