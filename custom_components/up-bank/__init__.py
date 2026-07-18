"""Up Bank integration bootstrap (polling, options, coordinator)."""
from __future__ import annotations
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_API_KEY
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .webhook_manager import async_setup_webhook
from .webhook_manager import async_delete_webhook
from .up import UP
from .coordinator import UpDataCoordinator
from .const import DOMAIN, PLATFORMS, DEFAULT_REFRESH_MIN

_LOGGER = logging.getLogger(__name__)

# ---------- Setup / Options handling ----------
async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options (e.g., refresh interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api_key = entry.data.get(CONF_API_KEY)

    if not api_key:
        raise ConfigEntryNotReady("No API token found in config entry.")

    refresh_min = entry.options.get("refresh_minutes", DEFAULT_REFRESH_MIN)
    if not isinstance(refresh_min, int) or refresh_min <= 0:
        refresh_min = DEFAULT_REFRESH_MIN

    api = UP(session=async_get_clientsession(hass), api_key=api_key)

    coordinator = UpDataCoordinator(hass, api, timedelta(minutes=refresh_min))

    # First refresh must succeed before platforms are forwarded.
    await coordinator.async_config_entry_first_refresh()
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Initial Up API fetch failed.")
    
    # Webhooks are a nice-to-have, so try to setup if the user has a valid calback url for UP to use
    try:
        webhook_id = await async_setup_webhook(hass, entry, api)
    except Exception:
        _LOGGER.warning("Up webhook setup failed; continuing with polling only", exc_info=True)
        webhook_id = None

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator, "api": api, "up_webhook_id": webhook_id}

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Up Bank setup complete (interval=%s min)", refresh_min)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    # Clean up webhook

    api_key = entry.data.get(CONF_API_KEY)

    api = UP(session=async_get_clientsession(hass), api_key=api_key)

    up_webhook_id = entry.data.get("up_webhook_id")

    if up_webhook_id:
        _LOGGER.debug("Deleting Up webhook %s", up_webhook_id)
        await async_delete_webhook(api, up_webhook_id)

    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok