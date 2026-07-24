"""Sensors for Up Bank: per-account balances, totals, and latest txn info."""

from __future__ import annotations

import re
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import UpDataCoordinator
from .entity import UpBaseEntity

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

    # Latest txn sensor, one per ownership type actually present
    for ownership_type in ("INDIVIDUAL", "JOINT"):
        if ownership_type not in ownership_types_present:
            continue
        entities.append(UpLatestTransactionSensor(coordinator, entry, ownership_type))

    async_add_entities(entities, update_before_add=True)


# ---------- Base ----------
class _BaseUpSensor(UpBaseEntity, SensorEntity):
    pass


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
class UpLatestTransactionSensor(_BaseUpSensor):
    """State = latest transaction amount; description/message/timestamp/category/tags as attributes."""

    def __init__(
        self, coordinator: UpDataCoordinator, entry: ConfigEntry, ownership_type: str
    ) -> None:
        is_joint = ownership_type == "JOINT"
        super().__init__(coordinator, entry, is_joint=is_joint)
        self._ownership_type = ownership_type
        id_prefix = "2up_" if is_joint else ""
        name_prefix = "2Up " if is_joint else "Up "
        self._attr_unique_id = f"{entry.entry_id}_latest_txn_{id_prefix}transaction"
        self._attr_name = f"{name_prefix}Latest Transaction"
        self._attr_icon = "mdi:bank-transfer"
        self._attr_native_unit_of_measurement = "AUD"

    @property
    def _latest(self) -> dict[str, Any] | None:
        return self.coordinator.latest_transaction_for(self._ownership_type)

    @property
    def native_value(self) -> float | None:
        lt = self._latest
        if not lt:
            return None
        try:
            return float(lt["attributes"]["amount"]["value"])
        except Exception:
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        lt = self._latest
        if not lt:
            return {}
        attributes = lt.get("attributes") or {}
        created_at = attributes.get("createdAt")
        category_rel = ((lt.get("relationships") or {}).get("category") or {}).get(
            "data"
        ) or {}
        tag_rel = ((lt.get("relationships") or {}).get("tags") or {}).get(
            "data"
        ) or []
        return {
            "description": attributes.get("description"),
            "message": attributes.get("message"),
            "timestamp": dt_util.parse_datetime(created_at) if created_at else None,
            "category": category_rel.get("id"),
            "tags": [t.get("id") for t in tag_rel if isinstance(t, dict) and t.get("id")],
        }
