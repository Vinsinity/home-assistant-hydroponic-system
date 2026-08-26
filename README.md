# Hydroponic System

Home Assistant profile manager and dedicated control surface for a staged indoor grow system.

## Current scope (0.25.0)

- Stores every cultivation under a permanent unique ID; starting a new cultivation does not replace completed history.
- Keeps an append-only event journal for stage transitions, notes, water work, nutrient/pH doses, reservoir volume, calibration, maintenance, photos, alarms, and future read-only assistant records.
- Mirrors the complete cultivation journal to a second Home Assistant storage document and can download a checksummed JSON backup from the Calendar tab.
- Captures plant species, cultivar, source, plant count, grow method, reservoir/system volume, photoperiod source, nutrient program, start date, and notes when cultivation starts.

- Optionally discovers Atlas Scientific EZO pH, EC, DO, and RTD circuits directly on Raspberry Pi I2C bus 1.
- Creates native Home Assistant sensor entities and polls them locally every 30 seconds.
- Shows `/dev/i2c-1` availability, discovered circuit addresses, types, and firmware in the panel Settings tab.
- Keeps automatic hardware control disabled; administrators can run an explicitly confirmed, bounded 1-30 second Motor HAT calibration test.
- Separates read-only I2C discovery candidates from enrolled devices; nothing is activated until the user adds it.
- Provides one device list plus a discovery/add pane without vendor-specific auto-enable toggles.
- Supports persistent manual I2C addresses and a 10-300 second polling interval.
- Exposes guarded pH, EC, DO, and RTD calibration commands after an explicit confirmation.
- Discovers PCA9685 Motor HATs at `0x40`-`0x4f` using register reads only and lists them with outputs locked.

- Stores six editable example stage profiles in one Home Assistant storage document.
- Provides a dedicated responsive profile editor panel.
- Uses Home Assistant cards, controls, spacing, and theme variables in the panel.
- Provides Overview, Profiles, and Settings tabs directly inside the panel.
- Shows current readings with 24-hour Recorder history charts.
- Lets administrators change device, sensor, and equipment mappings without opening the integration options dialog.
- Supports unlimited camera and moisture-sensor mappings with a security overview and water-alarm state.
- Uses a fixed four-camera desktop grid and keeps security directly below the stage tabs.
- Maps an RDWC water-level sensor and RDWC circulation pump; air-circulation fans remain outside automatic control.
- Lists incomplete required mappings in the panel header.
- Shows live sensor values beside the selected profile targets.
- Maps multiple environmental devices, automatically discovers their CO2, temperature, and humidity entities, and averages available readings.
- Calculates live VPD from the discovered average temperature and humidity.
- Maps VPD, nutrient PPM, pH, dissolved oxygen, and water-temperature sensors.
- Maps lights, CO2 valve, exhaust/inline/circulation fans, climate, dehumidifier, and chiller controls.
- Keeps the control engine disabled by default.
- Does not create dozens of `input_number` helpers.

## Install with HACS

1. In HACS, open **Integrations**.
2. Select the three-dot menu → **Custom repositories**.
3. Add `https://github.com/Vinsinity/home-assistant-hydroponic-system` as an **Integration**.
4. Search for **Hydroponic System** and download it.
5. Restart Home Assistant.
6. Add **Hydroponic System** from Settings → Devices & services.

The **Hydroponic System** panel is registered automatically. Monitoring through existing Home Assistant entities requires no YAML or SSH access after installation. Direct local I2C still requires the host to expose the selected `/dev/i2c-N` device to Home Assistant Core.

## Manual development install

Copy `custom_components/hydroponic_system` into Home Assistant's `config/custom_components` directory, restart Home Assistant, and add the integration from Settings → Devices & services.

The profile editor and entity mappings are intentionally separate from the control engine. Saving a profile, selecting a stage, adding a journal event, or mapping equipment in version 0.25.0 does not operate equipment.

## Journal durability

The integration writes cultivation records and append-only events to the primary Home Assistant storage document and a checksummed recovery document. Completed cultivations remain in the archive when another cultivation starts. The Calendar tab can also download the complete journal as checksummed JSON.

These protections cover application errors and accidental replacement. They cannot protect against loss of the entire storage device, so keep regular Home Assistant backups and download the journal JSON to another device periodically.

## Raspberry Pi 5 and native Atlas I2C

The safest migration is a second microSD card:

1. Shut the Raspberry Pi down completely and label the existing MyCodo card. Do not erase it.
2. Flash the Raspberry Pi 5 Home Assistant OS image to a different microSD card.
3. Keep the InterLink i3 and probes physically connected, then boot the new HAOS card.
4. Enable I2C in HAOS by adding `dtparam=i2c1=on` and `dtparam=i2c_arm=on` to `config.txt`.
5. Load the `i2c-dev` and `i2c-bcm2708` host modules as documented by Home Assistant OS.
6. Install Hydroponic System and open Hydroponic System → Settings → Local Raspberry Pi hardware.

If `/dev/i2c-1` is not available to Home Assistant Core, the integration remains usable and reports the exact diagnostic instead of failing setup. The old installation can be restored by powering down and reinserting the untouched MyCodo microSD card.
