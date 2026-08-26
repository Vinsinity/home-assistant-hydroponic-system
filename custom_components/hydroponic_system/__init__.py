"""Hydroponic System."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from .const import DOMAIN, PANEL_COMPONENT, PANEL_MODULE_URL, PANEL_PATH, PANEL_URL
from .entity_map import resolve_entities
from .hardware.coordinator import AtlasI2CCoordinator
from .store import HydroponicSystemStore
from .websocket_api import async_register

PLATFORMS = [Platform.SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the API once."""
    hass.data.setdefault(DOMAIN, {})
    async_register(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Load profiles and expose the panel asset."""
    if entry.title != "Hydroponic System":
        hass.config_entries.async_update_entry(entry, title="Hydroponic System")
    store = HydroponicSystemStore(hass)
    await store.async_load()
    hass.data[DOMAIN]["store"] = store
    configured = {**entry.data, **entry.options}
    hass.data[DOMAIN]["entry"] = entry
    hass.data[DOMAIN]["configured_entities"] = configured
    hass.data[DOMAIN]["entities"] = resolve_entities(hass, configured)

    hardware = store.data.get("hardware", {})
    atlas = AtlasI2CCoordinator(
        hass,
        bus_number=int(hardware.get("i2c_bus", 1)),
        hardware=hardware,
    )
    hass.data[DOMAIN]["atlas_i2c"] = atlas
    if await atlas.async_initialize():
        await atlas.async_config_entry_first_refresh()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _async_options_updated(hass: HomeAssistant, updated: ConfigEntry) -> None:
        configured = {**updated.data, **updated.options}
        hass.data[DOMAIN]["configured_entities"] = configured
        hass.data[DOMAIN]["entities"] = resolve_entities(hass, configured)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))

    panel_path = Path(__file__).parent / "frontend" / "hydroponic-system-panel.js"
    if not hass.data[DOMAIN].get("panel_static_registered"):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(PANEL_URL, str(panel_path), False)]
        )
        hass.data[DOMAIN]["panel_static_registered"] = True
    await panel_custom.async_register_panel(
        hass,
        frontend_url_path=PANEL_PATH,
        webcomponent_name=PANEL_COMPONENT,
        sidebar_title="Hydroponic System",
        sidebar_icon="mdi:sprout",
        module_url=PANEL_MODULE_URL,
        require_admin=True,
        handle_safe_area=True,
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the integration."""
    atlas = hass.data[DOMAIN].get("atlas_i2c")
    if atlas is not None and atlas.devices:
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    frontend.async_remove_panel(hass, PANEL_PATH)
    hass.data[DOMAIN].pop("store", None)
    hass.data[DOMAIN].pop("entry", None)
    hass.data[DOMAIN].pop("configured_entities", None)
    hass.data[DOMAIN].pop("entities", None)
    hass.data[DOMAIN].pop("sensor_runtime", None)
    coordinator = hass.data[DOMAIN].pop("atlas_i2c", None)
    if coordinator is not None:
        await coordinator.async_shutdown()
    return True
