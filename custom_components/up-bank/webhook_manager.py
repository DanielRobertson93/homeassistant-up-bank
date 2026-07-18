from __future__ import annotations
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import get_url
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from aiohttp import web
from .coordinator import UpDataCoordinator
from .const import DOMAIN
from .up import UP

_LOGGER = logging.getLogger(__name__)

async def async_handle_webhook(hass: HomeAssistant, webhook_id: str, request: web.Request, entry_id: str) -> web.Response:

    payload = await request.json()

    hass.async_create_task(process_webhook_event(hass, payload, entry_id))

    return web.Response(status=200)

async def process_webhook_event(hass: HomeAssistant, payload: dict[str, Any], entry_id: str) -> None:

    coordinator: UpDataCoordinator = hass.data[DOMAIN][entry_id]["coordinator"]

    event_type = payload["data"]["attributes"]["eventType"]

    if event_type == "TRANSACTION_DELETED":
        await coordinator.async_request_refresh()
    else:
        transaction_id = payload["data"]["attributes"]["transaction"]["data"]["id"]
        data = await coordinator._async_partial_refresh_data(transaction_id)
        coordinator.async_set_updated_data(data)

async def async_setup_webhook(
    hass: HomeAssistant,
    entry: ConfigEntry,
    api: UP,
) -> str:
    """Ensure a webhook exists at Up, register our HA handler for it, and return the HA webhook_id."""

    # 1. Reuse the HA webhook id from a previous setup if we have one, so the
    # callback URL registered with Up stays valid across reloads/restarts.
    ha_webhook_id = entry.data.get("ha_webhook_id") or webhook.async_generate_id()

    # 2. Build callback URL
    base_url = get_url(hass, prefer_external=True)
    callback_url = f"{base_url}/api/webhook/{ha_webhook_id}"

    _LOGGER.debug("Up webhook callback URL: %s", callback_url)

    # 3. Check if we already stored an Up webhook id
    # when we create the Webhook, it's ID is stored along with its secret
    # checking here if we already have one saved and then if it is reachable
    existing_up_id = entry.data.get("up_webhook_id")
    up_webhook_valid = False

    if existing_up_id:
        try:
            up_webhook_valid = await api.webhook_exists(existing_up_id)
        except Exception:
            _LOGGER.warning("Failed checking existing webhook, recreating")

    if up_webhook_valid:
        _LOGGER.debug("Existing Up webhook still valid")
    else:
        # 4. Create webhook at Up
        up_webhook_data = await api.create_webhook(callback_url)

        up_webhook_id = up_webhook_data["id"]

        # todo figure out how to save this secret key to use as auth whenever a webhook arrives
        up_webhook_secret_key = up_webhook_data["attributes"]["secretKey"]

        # 5. Persist
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data,
                  "up_webhook_id": up_webhook_id,
                  "ha_webhook_id": ha_webhook_id,
                  "up_secretKey": up_webhook_secret_key},
        )

        _LOGGER.info("Created Up webhook %s", up_webhook_id)

    # 6. Register our handler so incoming requests to the callback URL reach us.
    async def _handler(hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response:
        return await async_handle_webhook(hass, webhook_id, request, entry.entry_id)

    webhook.async_register(hass, DOMAIN, "Up Bank", ha_webhook_id, _handler)
    entry.async_on_unload(lambda: webhook.async_unregister(hass, ha_webhook_id))

    return ha_webhook_id


async def async_delete_webhook(
    api: UP,
    up_webhook_id: str,
) -> None:
    """Delete webhook when integration removed."""

    try:
        await api.delete_webhook(up_webhook_id)
        _LOGGER.info("Deleted Up webhook %s", up_webhook_id)
    except Exception:
        _LOGGER.warning("Failed deleting Up webhook")
