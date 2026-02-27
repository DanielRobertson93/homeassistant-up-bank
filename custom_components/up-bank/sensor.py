"""Sensors for Up Bank: per-account balances, totals, and latest txn info."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify
from .coordinator import UpDataCoordinator
from .const import DOMAIN

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    wrapper = hass.data[DOMAIN][entry.entry_id]
    coordinator: UpDataCoordinator = wrapper["coordinator"]

    entities: List[SensorEntity] = []

    # Per-account balances
    for acct in coordinator.data.get("accounts", []):
        acct_id = acct.get("id")
        display_name = (acct.get("attributes") or {}).get("displayName") or "Up Account"
        if acct_id:
            entities.append(UpAccountBalanceSensor(coordinator, entry, acct_id, display_name))

    # Summary sensors
    entities.append(UpTotalBalanceSensor(coordinator, entry))
    entities.append(UpAccountCountSensor(coordinator, entry))
    entities.append(UpTransactionCountSensor(coordinator, entry))

    # Latest txn sensors (description, amount, time, category, tags)
    entities.append(UpLatestTxnDescriptionSensor(coordinator, entry))
    entities.append(UpLatestTxnAmountSensor(coordinator, entry))
    entities.append(UpLatestTxnTimeSensor(coordinator, entry))
    entities.append(UpLatestTxnCategorySensor(coordinator, entry))
    entities.append(UpLatestTxnTagsSensor(coordinator, entry))

    async_add_entities(entities, update_before_add=True)


# ---------- Base ----------
class _BaseUpSensor(CoordinatorEntity[UpDataCoordinator], SensorEntity):
    _attr_should_poll = False

    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Up Bank",
            manufacturer="Up",
        )


# ---------- Per-account ----------
class UpAccountBalanceSensor(_BaseUpSensor):
    """Balance for a specific account."""

    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry, account_id: str, display_name: str) -> None:
        super().__init__(coordinator, entry)
        slug = slugify(display_name) or account_id
        self._account_id = account_id
        self._attr_unique_id = f"{entry.entry_id}_acct_{account_id}_balance"
        self._attr_name = f"{display_name} Balance"
        self._attr_icon = "mdi:bank"
        self._attr_native_unit_of_measurement = "AUD"
        # Provide a friendly default entity_id like sensor.spending_balance
        self.entity_id = f"sensor.{slug}_balance"

    @property
    def native_value(self) -> Optional[float]:
        for acct in self.coordinator.data.get("accounts", []):
            if acct.get("id") == self._account_id:
                try:
                    return float(acct["attributes"]["balance"]["value"])
                except Exception:
                    return None
        return None


# ---------- Summary ----------
class UpTotalBalanceSensor(_BaseUpSensor):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_total_balance"
        self._attr_name = "Up Total Balance"
        self._attr_icon = "mdi:cash-multiple"
        self._attr_native_unit_of_measurement = "AUD"
        self.entity_id = "sensor.up_total_balance"

    @property
    def native_value(self) -> Optional[float]:
        summary = self.coordinator.data.get("summary") or {}
        val = summary.get("total_balance")
        try:
            return float(val) if val is not None else None
        except Exception:
            return None


class UpAccountCountSensor(_BaseUpSensor):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_account_count"
        self._attr_name = "Up Account Count"
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> Optional[int]:
        return len(self.coordinator.data.get("accounts", []))


class UpTransactionCountSensor(_BaseUpSensor):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_transaction_count"
        self._attr_name = "Up Transaction Count"
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> Optional[int]:
        return len(self.coordinator.data.get("transactions", []))


# ---------- Latest transaction ----------
class _LatestTxnBase(_BaseUpSensor):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry, suffix: str, unique_suffix: str, icon: str) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_latest_txn_{unique_suffix}"
        self._attr_name = f"Up Latest Transaction {suffix}"
        self._attr_icon = icon

    @property
    def _latest(self) -> Optional[Dict[str, Any]]:
        tx = self.coordinator.data.get("transactions", [])
        return tx[0] if tx else None


class UpLatestTxnDescriptionSensor(_LatestTxnBase):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "Description", "description", "mdi:text")

    @property
    def native_value(self) -> Optional[str]:
        lt = self._latest
        if not lt:
            return None
        return (lt.get("attributes") or {}).get("description")


class UpLatestTxnAmountSensor(_LatestTxnBase):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "Amount", "amount", "mdi:cash")
        self._attr_native_unit_of_measurement = "AUD"

    @property
    def native_value(self) -> Optional[float]:
        lt = self._latest
        if not lt:
            return None
        try:
            return float(lt["attributes"]["amount"]["value"])
        except Exception:
            return None


class UpLatestTxnTimeSensor(_LatestTxnBase):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "Time", "time", "mdi:clock-outline")

    @property
    def native_value(self) -> Optional[str]:
        lt = self._latest
        if not lt:
            return None
        return (lt.get("attributes") or {}).get("createdAt")


class UpLatestTxnCategorySensor(_LatestTxnBase):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "Category", "category", "mdi:shape-outline")

    @property
    def native_value(self) -> Optional[str]:
        lt = self._latest
        if not lt:
            return None
        rel = (lt.get("relationships") or {}).get("category") or {}
        data = rel.get("data") or {}
        return data.get("id")  # returns category id (can be mapped to name via categories)


class UpLatestTxnTagsSensor(_LatestTxnBase):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "Tags", "tags", "mdi:tag-multiple")

    @property
    def native_value(self) -> Optional[str]:
        lt = self._latest
        if not lt:
            return None
        rel = (lt.get("relationships") or {}).get("tags") or {}
        data = rel.get("data") or []
        # Return comma-separated tag IDs (Up's API returns ids for tags)
        if not data:
            return ""
        return ", ".join([d.get("id", "") for d in data if isinstance(d, dict)])
