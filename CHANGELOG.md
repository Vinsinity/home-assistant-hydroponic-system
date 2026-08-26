# Changelog

## 0.26.0

- Add a deterministic, read-only sensor health and confidence model.
- Normalize configured Home Assistant sensors and enrolled Atlas I2C readings into one measurement snapshot.
- Track data age, unavailable/stale/suspect states, sudden spikes, multi-probe divergence, profile-target duration, and calibration age.
- Add a live sensor trust dashboard and editable freshness/calibration settings to the panel.
- Timestamp native I2C observations and automatically record successful Atlas calibration actions.
- Keep sensor-health configuration changes covered by the journal recovery write path.

## 0.25.0

- Add permanent, ID-based cultivation history instead of replacing the previous cultivation.
- Add a versioned append-only event journal and lossless migration of legacy journal fields.
- Mirror cultivations and events to a checksummed Home Assistant recovery storage document.
- Add checksummed JSON journal export from the panel.
- Add cultivation identity fields and a complete start form.
- Add daily note, water, nutrient, pH, volume, calibration, maintenance, and photo URL events.
- Add idempotency IDs to cultivation start, finish, and journal event requests.
- Remove the synthetic 1 ml/s pump calibration; only measured, timestamped calibration is accepted as ready.
