"""Event entity for Up Bank: fires once per new/settled transaction.

Unlike a plain sensor, this reliably fires even when two consecutive
transactions share the same amount - detection is keyed on
(transaction id, status), not on the entity's displayed value.
"""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import UpDataCoordinator, ownership_types_present
from .entity import UpBaseEntity

_STATUS_TO_EVENT_TYPE = {
    "HELD": "transaction_created",
    "SETTLED": "transaction_settled",
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    wrapper = hass.data[DOMAIN][entry.entry_id]
    coordinator: UpDataCoordinator = wrapper["coordinator"]

    present = ownership_types_present(coordinator.data)
    entities = [
        UpLatestTransactionEvent(coordinator, entry, ownership_type)
        for ownership_type in ("INDIVIDUAL", "JOINT")
        if ownership_type in present
    ]
    async_add_entities(entities)


class UpLatestTransactionEvent(UpBaseEntity, EventEntity):
    def __init__(
        self, coordinator: UpDataCoordinator, entry: ConfigEntry, ownership_type: str
    ) -> None:
        is_joint = ownership_type == "JOINT"
        super().__init__(coordinator, entry, is_joint=is_joint)
        self._ownership_type = ownership_type
        id_prefix = "2up_" if is_joint else ""
        name_prefix = "2Up " if is_joint else "Up "
        self._attr_unique_id = f"{entry.entry_id}_latest_txn_{id_prefix}event"
        self._attr_name = f"{name_prefix}Latest Transaction"
        self._attr_icon = "mdi:bank-transfer"
        self._attr_event_types = list(_STATUS_TO_EVENT_TYPE.values())
        self._last_key = self._current_key()

    def _current_key(self) -> tuple[str, str | None] | None:
        lt = self.coordinator.latest_transaction_for(self._ownership_type)
        if not lt:
            return None
        return (lt["id"], (lt.get("attributes") or {}).get("status"))

    @callback
    def _handle_coordinator_update(self) -> None:
        key = self._current_key()
        if key is not None and key != self._last_key:
            lt = self.coordinator.latest_transaction_for(self._ownership_type)
            attributes = (lt or {}).get("attributes") or {}
            status = attributes.get("status")
            event_type = _STATUS_TO_EVENT_TYPE.get(status) if status else None
            if event_type:
                self._trigger_event(
                    event_type,
                    {
                        "transaction_id": key[0],
                        "description": attributes.get("description"),
                        "message": attributes.get("message"),
                        "amount": (attributes.get("amount") or {}).get("value"),
                    },
                )
        self._last_key = key
        super()._handle_coordinator_update()
