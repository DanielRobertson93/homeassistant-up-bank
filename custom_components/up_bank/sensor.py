"""Sensors for Up Bank: per-account balances, totals, and latest txn info."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import UpDataCoordinator

_2UP_PREFIX_RE = re.compile(r"^2up[:\s-]*", re.IGNORECASE)


def _strip_2up_prefix(name: str) -> str:
    """Up's own displayName sometimes already leads with '2up' - normalize it away
    so prefix is applied consistently regardless of Up's naming."""
    return _2UP_PREFIX_RE.sub("", name).strip() or name


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    wrapper = hass.data[DOMAIN][entry.entry_id]
    coordinator: UpDataCoordinator = wrapper["coordinator"]

    entities: list[SensorEntity] = []

    # Per-account balances
    ownership_types_present: set[str | None] = set()
    for acct in coordinator.data.get("accounts", []):
        acct_id = acct.get("id")
        attributes = acct.get("attributes") or {}
        display_name = attributes.get("displayName") or "Up Account"
        ownership_type = attributes.get("ownershipType")
        ownership_types_present.add(ownership_type)
        if acct_id:
            entities.append(
                UpAccountBalanceSensor(
                    coordinator, entry, acct_id, display_name, ownership_type
                )
            )

    # Summary sensors (whole-of-account aggregates, not split by ownership type)
    entities.append(UpTotalBalanceSensor(coordinator, entry))
    entities.append(UpAccountCountSensor(coordinator, entry))
    entities.append(UpTransactionsTodaySensor(coordinator, entry))
    entities.append(UpTransactionsThisWeekSensor(coordinator, entry))
    entities.append(UpTransactionsThisMonthSensor(coordinator, entry))

    # Latest txn sensors, one set per ownership type actually present
    for ownership_type in ("INDIVIDUAL", "JOINT"):
        if ownership_type not in ownership_types_present:
            continue
        entities.append(
            UpLatestTxnDescriptionSensor(coordinator, entry, ownership_type)
        )
        entities.append(UpLatestTxnAmountSensor(coordinator, entry, ownership_type))
        entities.append(UpLatestTxnTimeSensor(coordinator, entry, ownership_type))
        entities.append(UpLatestTxnCategorySensor(coordinator, entry, ownership_type))
        entities.append(UpLatestTxnTagsSensor(coordinator, entry, ownership_type))

    async_add_entities(entities, update_before_add=True)


# ---------- Base ----------
class _BaseUpSensor(CoordinatorEntity[UpDataCoordinator], SensorEntity):
    _attr_should_poll = False

    def __init__(
        self, coordinator: UpDataCoordinator, entry: ConfigEntry, is_joint: bool = False
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        if is_joint:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{entry.entry_id}_2up")},
                name="Up Bank (2Up)",
                manufacturer="Up",
            )
        else:
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, entry.entry_id)},
                name="Up Bank",
                manufacturer="Up",
            )


# ---------- Per-account ----------
class UpAccountBalanceSensor(_BaseUpSensor):
    """Balance for a specific account."""

    def __init__(
        self,
        coordinator: UpDataCoordinator,
        entry: ConfigEntry,
        account_id: str,
        display_name: str,
        ownership_type: str | None,
    ) -> None:
        is_joint = ownership_type == "JOINT"
        super().__init__(coordinator, entry, is_joint=is_joint)
        clean_name = _strip_2up_prefix(display_name)
        slug = slugify(clean_name) or account_id
        self._account_id = account_id
        self._attr_unique_id = f"{entry.entry_id}_acct_{account_id}_balance"
        self._attr_icon = "mdi:bank"
        self._attr_native_unit_of_measurement = "AUD"
        if is_joint:
            self._attr_name = f"2Up {clean_name} Balance"
            self.entity_id = f"sensor.2up_{slug}_balance"
        else:
            self._attr_name = f"{clean_name} Balance"
            # Provide a friendly default entity_id like sensor.spending_balance
            self.entity_id = f"sensor.{slug}_balance"

    @property
    def native_value(self) -> float | None:
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
    def native_value(self) -> float | None:
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
    def native_value(self) -> int | None:
        return len(self.coordinator.data.get("accounts", []))


class _WindowedTransactionCountSensor(_BaseUpSensor):
    def __init__(
        self,
        coordinator: UpDataCoordinator,
        entry: ConfigEntry,
        suffix: str,
        unique_suffix: str,
        summary_key: str,
    ) -> None:
        super().__init__(coordinator, entry)
        self._summary_key = summary_key
        self._attr_unique_id = f"{entry.entry_id}_{unique_suffix}"
        self._attr_name = f"Up Transactions {suffix}"
        self._attr_icon = "mdi:counter"

    @property
    def native_value(self) -> int | None:
        summary = self.coordinator.data.get("summary") or {}
        return summary.get(self._summary_key)


class UpTransactionsTodaySensor(_WindowedTransactionCountSensor):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator, entry, "Today", "transactions_today", "transactions_today"
        )


class UpTransactionsThisWeekSensor(_WindowedTransactionCountSensor):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "This Week",
            "transactions_this_week",
            "transactions_this_week",
        )


class UpTransactionsThisMonthSensor(_WindowedTransactionCountSensor):
    def __init__(self, coordinator: UpDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(
            coordinator,
            entry,
            "This Month",
            "transactions_this_month",
            "transactions_this_month",
        )


# ---------- Latest transaction (per ownership type) ----------
class _LatestTxnBase(_BaseUpSensor):
    def __init__(
        self,
        coordinator: UpDataCoordinator,
        entry: ConfigEntry,
        ownership_type: str,
        suffix: str,
        unique_suffix: str,
        icon: str,
    ) -> None:
        is_joint = ownership_type == "JOINT"
        super().__init__(coordinator, entry, is_joint=is_joint)
        self._ownership_type = ownership_type
        id_prefix = "2up_" if is_joint else ""
        name_prefix = "2Up " if is_joint else "Up "
        self._attr_unique_id = f"{entry.entry_id}_latest_txn_{id_prefix}{unique_suffix}"
        self._attr_name = f"{name_prefix}Latest Transaction {suffix}"
        self._attr_icon = icon

    @property
    def _latest(self) -> dict[str, Any] | None:
        ownership = {
            a["id"]: (a.get("attributes") or {}).get("ownershipType")
            for a in self.coordinator.data.get("accounts", [])
        }
        transactions: list[dict[str, Any]] = self.coordinator.data.get(
            "transactions", []
        )
        for tx in transactions:
            rel = ((tx.get("relationships") or {}).get("account") or {}).get(
                "data"
            ) or {}
            if ownership.get(rel.get("id")) == self._ownership_type:
                return tx
        return None


class UpLatestTxnDescriptionSensor(_LatestTxnBase):
    def __init__(
        self, coordinator: UpDataCoordinator, entry: ConfigEntry, ownership_type: str
    ) -> None:
        super().__init__(
            coordinator, entry, ownership_type, "Description", "description", "mdi:text"
        )

    @property
    def native_value(self) -> str | None:
        lt = self._latest
        if not lt:
            return None
        return (lt.get("attributes") or {}).get("description")


class UpLatestTxnAmountSensor(_LatestTxnBase):
    def __init__(
        self, coordinator: UpDataCoordinator, entry: ConfigEntry, ownership_type: str
    ) -> None:
        super().__init__(
            coordinator, entry, ownership_type, "Amount", "amount", "mdi:cash"
        )
        self._attr_native_unit_of_measurement = "AUD"

    @property
    def native_value(self) -> float | None:
        lt = self._latest
        if not lt:
            return None
        try:
            return float(lt["attributes"]["amount"]["value"])
        except Exception:
            return None


class UpLatestTxnTimeSensor(_LatestTxnBase):
    def __init__(
        self, coordinator: UpDataCoordinator, entry: ConfigEntry, ownership_type: str
    ) -> None:
        super().__init__(
            coordinator, entry, ownership_type, "Time", "time", "mdi:clock-outline"
        )
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> datetime | None:
        lt = self._latest
        if not lt:
            return None
        created_at = (lt.get("attributes") or {}).get("createdAt")
        if not created_at:
            return None
        return dt_util.parse_datetime(created_at)


class UpLatestTxnCategorySensor(_LatestTxnBase):
    def __init__(
        self, coordinator: UpDataCoordinator, entry: ConfigEntry, ownership_type: str
    ) -> None:
        super().__init__(
            coordinator,
            entry,
            ownership_type,
            "Category",
            "category",
            "mdi:shape-outline",
        )

    @property
    def native_value(self) -> str | None:
        lt = self._latest
        if not lt:
            return None
        rel = (lt.get("relationships") or {}).get("category") or {}
        data = rel.get("data") or {}
        return data.get(
            "id"
        )  # returns category id (can be mapped to name via categories)


class UpLatestTxnTagsSensor(_LatestTxnBase):
    def __init__(
        self, coordinator: UpDataCoordinator, entry: ConfigEntry, ownership_type: str
    ) -> None:
        super().__init__(
            coordinator, entry, ownership_type, "Tags", "tags", "mdi:tag-multiple"
        )

    @property
    def native_value(self) -> str | None:
        lt = self._latest
        if not lt:
            return None
        rel = (lt.get("relationships") or {}).get("tags") or {}
        data = rel.get("data") or []
        # Return comma-separated tag IDs (Up's API returns ids for tags)
        if not data:
            return ""
        return ", ".join([d.get("id", "") for d in data if isinstance(d, dict)])
