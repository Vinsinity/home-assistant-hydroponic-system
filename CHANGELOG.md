# Changelog

## 0.25.0

- Add permanent, ID-based cultivation history instead of replacing the previous cultivation.
- Add a versioned append-only event journal and lossless migration of legacy journal fields.
- Mirror cultivations and events to a checksummed Home Assistant recovery storage document.
- Add checksummed JSON journal export from the panel.
- Add cultivation identity fields and a complete start form.
- Add daily note, water, nutrient, pH, volume, calibration, maintenance, and photo URL events.
- Add idempotency IDs to cultivation start, finish, and journal event requests.
- Remove the synthetic 1 ml/s pump calibration; only measured, timestamped calibration is accepted as ready.
