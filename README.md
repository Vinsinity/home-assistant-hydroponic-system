# Hydroponic System

Home Assistant profile manager and dedicated control surface for a staged indoor grow system.

## Current scope (0.32.0)

### Grow tracking and Assistant

- Stores every cultivation under a permanent unique ID; starting a new cultivation does not replace completed history.
- Keeps an append-only event journal for stage transitions, notes, water work, nutrient/pH doses, reservoir volume, calibration, maintenance, photos, alarms, and future read-only assistant records.
- Mirrors the complete cultivation journal to a second Home Assistant storage document and can download a checksummed JSON backup from the Calendar tab.
- Stores a persistent Plant Library with editable Tomato, Lettuce, Cannabis, Basil, Strawberry, Pepper, and Cucumber starting profiles, plus user-created species.
- Keeps per-species stage targets for schedule, photoperiod, light, temperature, humidity, VPD, CO2, pH, EC, water temperature, and dissolved oxygen.
- Labels built-in targets as editable starting examples rather than universal recipes; crop and cultivar differences remain the user's responsibility.
- Stores Cannabis growth type (Photoperiod or Autoflower), breeder/seed bank, and breeder-specific strain records separately instead of treating them as one cultivar string.
- Ships a versioned, editable catalog snapshot with 249 breeder-specific Cannabis offerings from official Royal Queen Seeds, Barney's Farm, Dutch Passion, Sensi Seeds, and Fast Buds catalogs; Amnesia Seeds remains available as a custom source entry.
- Provides a four-step grow-start wizard that captures plant/genetics, editable starting profile and initial stage, selected nutrient products/program, grow area/method/medium/light context, start date, and notes before a final review.
- Stores a reusable grow setup with area dimensions, plant capacity, cultivation method, growing medium, conditional hydroponic volumes, fixture identity/power/count, dimmer, height, and daily light schedule.
- Takes immutable snapshots of the selected plant profile, selected genetics/breeder identity, chosen nutrient products, and grow area/medium/light profile when a cultivation starts, so later library or configuration edits cannot rewrite historical grow context. Large catalogs remain separate; only the selected cultivar is copied into each cultivation.
- Adds a product-focused Overview with grow/stage day, today's light plan, recent journal records, and quick actions for notes, water, nutrients, and photos.
- Hides unconfigured metric and security panels behind compact setup prompts instead of filling the Overview with empty technical cards.
- Adds a read-only Grow Assistant powered by Home Assistant's official AI Task providers. The selected model receives grow context but no Home Assistant control API or tools.
- Lets the user choose 24-hour or 7-day sensor summaries, response language/detail, optional camera snapshots, and optional persistent notifications.
- Appends every generated Assistant report to the same immutable cultivation journal as an `ai_recommendation` event.

### Monitoring and local hardware

- Optionally discovers Atlas Scientific EZO pH, EC, DO, and RTD circuits directly on Raspberry Pi I2C bus 1.
- Creates native Home Assistant sensor entities and polls them locally every 30 seconds.
- Shows `/dev/i2c-1` availability, discovered circuit addresses, types, and firmware under Setup → Hardware.
- Keeps automatic hardware control disabled; administrators can run an explicitly confirmed, bounded 1-30 second Motor HAT calibration test.
- Separates read-only I2C discovery candidates from enrolled devices; nothing is activated until the user adds it.
- Provides one device list plus a discovery/add pane without vendor-specific auto-enable toggles.
- Supports persistent manual I2C addresses and a 10-300 second polling interval.
- Exposes guarded pH, EC, DO, and RTD calibration commands after an explicit confirmation.
- Discovers PCA9685 Motor HATs at `0x40`-`0x4f` using register reads only and lists them with outputs locked.

- Stores six editable example stage profiles in one Home Assistant storage document.
- Provides a dedicated responsive profile editor panel.
- Uses Home Assistant cards, controls, spacing, and theme variables in the panel.
- Keeps daily product navigation focused on Overview, Journal, Album, Area & Light, Assistant, and Setup. Connections, Plant Library, profiles, nutrients, hardware, and dosing use dedicated nested `/setup/...` routes beneath Setup.
- Shows current readings with 24-hour Recorder history charts.
- Lets administrators change device, sensor, and equipment mappings without opening the integration options dialog.
- Supports unlimited camera and moisture-sensor mappings with a security overview and water-alarm state.
- Shows configured cameras and safety sensors on the Overview while keeping the empty state compact.
- Maps an RDWC water-level sensor and RDWC circulation pump; air-circulation fans remain outside automatic control.
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

The profile editors, entity mappings, grow journal, and Grow Assistant are intentionally separate from the control engine. Saving a profile, selecting a stage, adding a journal event, generating an AI report, or mapping equipment in version 0.32.0 does not operate equipment.

Grow Assistant requires a Home Assistant integration that exposes an `ai_task` entity (for example, a supported local or cloud AI provider). Model choice and API credentials remain in that provider's Home Assistant configuration. Hydroponic System sends no LLM tools, service-call access, or device-control API with the task.

## Journal durability

The integration writes cultivation records, their plant/system snapshots, and append-only events to the primary Home Assistant storage document and a checksummed recovery document. Completed cultivations remain in the archive when another cultivation starts. The Journal tab can also download the complete journal and current Plant Library as checksummed JSON.

These protections cover application errors and accidental replacement. They cannot protect against loss of the entire storage device, so keep regular Home Assistant backups and download the journal JSON to another device periodically.

## Raspberry Pi 5 and native Atlas I2C

The safest migration is a second microSD card:

1. Shut the Raspberry Pi down completely and label the existing MyCodo card. Do not erase it.
2. Flash the Raspberry Pi 5 Home Assistant OS image to a different microSD card.
3. Keep the InterLink i3 and probes physically connected, then boot the new HAOS card.
4. Enable I2C in HAOS by adding `dtparam=i2c1=on` and `dtparam=i2c_arm=on` to `config.txt`.
5. Load the `i2c-dev` and `i2c-bcm2708` host modules as documented by Home Assistant OS.
6. Install Hydroponic System and open Hydroponic System → Setup → Hardware.

If `/dev/i2c-1` is not available to Home Assistant Core, the integration remains usable and reports the exact diagnostic instead of failing setup. The old installation can be restored by powering down and reinserting the untouched MyCodo microSD card.
