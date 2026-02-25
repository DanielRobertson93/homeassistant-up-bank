"""Up Bank integration bootstrap (polling, options, coordinator)."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict, Optional

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_API_KEY
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

DOMAIN = "up-bank"                 # must match folder name
PLATFORMS: list[str] = ["sensor"]

DEFAULT_REFRESH_MIN = 10           # safe default
MAX_TX_PER_PAGE = 50               # page size for /transactions
API_BASE = "https://api.up.com.au/api/v1"

_LOGGER = logging.getLogger(__name__)


# ---------- Tiny API client using HA's shared aiohttp session ----------
class UpApi:
    def __init__(self, hass: HomeAssistant, token: str) -> None:
        self._session = async_get_clientsession(hass)
        self._headers = {"Authorization": f"Bearer {token}"}

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{API_BASE}{path}"
        async with self._session.get(url, headers=self._headers, params=params, timeout=30) as resp:
            text = await resp.text()
            if resp.status == 401:
                raise UpdateFailed("Unauthorized (401). Check your Up API token.")
            if resp.status >= 400:
                raise UpdateFailed(f"Up API error {resp.status}: {text[:200]}")
            # Attempt JSON decode only after status checks
            return await resp.json()

    async def get_accounts(self) -> Dict[str, Any]:
        return await self._get("/accounts")

    async def get_transactions(self, page_size: int = MAX_TX_PER_PAGE) -> Dict[str, Any]:
        # Most recent first; one page is plenty for dashboards & notifications.
        return await self._get("/transactions", params={"page[size]": str(page_size)})

    async def get_categories(self) -> Dict[str, Any]:
        return await self._get("/categories")

    async def get_tags(self) -> Dict[str, Any]:
        return await self._get("/tags")
    
    async def ping(self) -> bool:
        return await self._get("/util/ping")


# ---------- DataUpdateCoordinator ----------
class UpDataCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    """Fetch accounts, recent transactions, categories, tags on a schedule."""

    def __init__(self, hass: HomeAssistant, api: UpApi, update_interval: timedelta) -> None:
        super().__init__(hass, _LOGGER, name="Up Bank Coordinator", update_interval=update_interval)
        self.api = api

    async def _async_update_data(self) -> Dict[str, Any]:
        try:
            # Fetch concurrently while staying very cheap (4 requests per cycle).
            accounts_resp, tx_resp, cats_resp, tags_resp = await asyncio.gather(
                self.api.get_accounts(),
                self.api.get_transactions(page_size=MAX_TX_PER_PAGE),
                self.api.get_categories(),
                self.api.get_tags(),
            )
        except Exception as exc:
            raise UpdateFailed(f"Error fetching Up data: {exc}") from exc

        accounts = accounts_resp.get("data") or []
        transactions = tx_resp.get("data") or []
        categories = cats_resp.get("data") or []
        tags = tags_resp.get("data") or []

        # Compute total balance safely
        total = 0.0
        for a in accounts:
            try:
                total += float(a["attributes"]["balance"]["value"])
            except Exception:
                continue

        return {
            "accounts": accounts,
            "transactions": transactions,
            "categories": categories,
            "tags": tags,
            "summary": {
                "total_balance": total,
                "account_count": len(accounts),
                "transaction_count": len(transactions),
            },
        }


# ---------- Setup / Options handling ----------
async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload when options (e.g., refresh interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    token = entry.data.get(CONF_API_KEY) or entry.data.get("token") or entry.data.get("api_key")
    if not token:
        raise ConfigEntryNotReady("No API token found in config entry.")

    refresh_min = entry.options.get("refresh_minutes", DEFAULT_REFRESH_MIN)
    if not isinstance(refresh_min, int) or refresh_min <= 0:
        refresh_min = DEFAULT_REFRESH_MIN

    api = UpApi(hass, token)
    coordinator = UpDataCoordinator(hass, api, timedelta(minutes=refresh_min))

    # First refresh must succeed before platforms are forwarded.
    await coordinator.async_config_entry_first_refresh()
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Initial Up API fetch failed.")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {"coordinator": coordinator, "api": api}

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Up Bank setup complete (interval=%s min)", refresh_min)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unload_ok
