from __future__ import annotations
import logging
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import get_url
from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from aiohttp import web
from .coordinator import UpDataCoordinator
from .const import DOMAIN
from .up import UP

_LOGGER = logging.getLogger(__name__)

async def async_handle_webhook(hass: HomeAssistant, request):
    
    payload = await request.json()

    hass.async_create_task(process_webhook_event(hass, payload))

    return web.Response(status=200)

async def process_webhook_event(hass, payload):

    coordinator: UpDataCoordinator = hass.data[DOMAIN]["coordinator"]

    event_type = payload["data"]["attributes"]["eventType"]

    if event_type == "TRANSACTION_DELETED":
        data = await coordinator.async_request_refresh()
    else:
        transactionID = payload["data"]["attributes"]["transaction"]["data"]["id"]
        data = await coordinator._async_partial_refresh_data(transactionID)

    coordinator.async_set_updated_data(data)

async def async_setup_webhook(
    hass: HomeAssistant,
    entry: ConfigEntry,
    api: UP,
) -> str:
    """Ensure a webhook exists at Up and return webhook_id."""

    # 1. Create HA webhook id (stable per config entry)
    ha_webhook_id = webhook.async_generate_id()

    # 2. Build callback URL
    base_url = get_url(hass, prefer_external=True)
    callback_url = f"{base_url}/api/webhook/{ha_webhook_id}"

    _LOGGER.debug("Up webhook callback URL: %s", callback_url)

    # 3. Check if we already stored an Up webhook id
    # when we create the Webhook, it's ID is stored along with its secret
    # checking here if we already have one saved and then if it is reachable
    existing_up_id = entry.data.get("up_webhook_id")

    if existing_up_id:
        try:
            exists = await api.webhook_exists(existing_up_id)
            if exists:
                _LOGGER.debug("Existing Up webhook still valid")
                return ha_webhook_id
        except Exception:
            _LOGGER.warning("Failed checking existing webhook, recreating")

    # 4. Create webhook at Up
    #callback_url = "https://140fc224-237f-474c-8f66-735f73447612.mock.pstmn.io"
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
